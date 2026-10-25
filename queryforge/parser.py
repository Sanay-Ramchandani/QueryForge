"""Rule-based, schema-grounded semantic parsing with explicit uncertainty checks.

This is a transparent baseline and improvement platform, not a pretrained LLM
or a faithful reproduction of Seq2SQL or ColloQL.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import re
from difflib import SequenceMatcher
from .schema import Schema, Column

TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?", re.I)
STOPWORDS = {"the", "a", "an", "of", "for", "in", "with", "from", "which", "what", "show", "me", "list", "find", "get", "is", "are", "were", "was", "all", "companies", "company", "records", "record", "their", "who", "whose", "and", "to", "by", "each", "per", "that", "had", "have", "has", "than", "during", "please", "us"}
AGGS = [(r'\b(?:average|mean|avg)\b', 'AVG'), (r'\b(?:total|sum)\b', 'SUM'), (r'\b(?:how many|number of|count)\b', 'COUNT'), (r'\b(?:maximum|max|highest)\b', 'MAX'), (r'\b(?:minimum|min|lowest)\b', 'MIN')]
OP_MAP = [(r'\b(?:at least|no less than|greater than or equal to)\b', '>='), (r'\b(?:at most|no more than|less than or equal to)\b', '<='), (r'\b(?:greater than|more than|above|over|exceeding)\b', '>'), (r'\b(?:less than|below|under|fewer than)\b', '<'), (r'\b(?:not equal to|other than|except)\b', '!='), (r'\b(?:equal to|equals|exactly|is|in|for|during|from)\b', '=')]

ALIASES = {
    "companies.name": ["companies", "company", "company name", "firm", "firms", "business", "businesses"],
    "companies.sector": ["sector", "industry", "industries"],
    "companies.country": ["country", "nation", "location", "based in"],
    "financials.year": ["year", "fiscal year", "fy"],
    "financials.revenue": ["revenue", "sales", "turnover"],
    "financials.profit": ["profit", "earnings", "income"],
    "financials.employees": ["employees", "staff", "headcount", "workers", "workforce"],
}


@dataclass
class Condition:
    column: Column
    op: str
    value: object


@dataclass
class Intent:
    target: Column | None = None
    select: Column | None = None
    aggregation: str | None = None
    group: Column | None = None
    conditions: list[Condition] = field(default_factory=list)
    order: tuple[Column, str] | None = None
    limit: int | None = None
    notes: list[str] = field(default_factory=list)


class ParseError(ValueError):
    pass


class SemanticParser:
    def __init__(self, schema: Schema, aliases: dict[str, list[str]] | None = None):
        self.schema = schema
        self.aliases = aliases or ALIASES

    def _phrases(self, column: Column) -> list[str]:
        return list(dict.fromkeys([column.name.replace('_', ' ')] + self.aliases.get(f"{column.table}.{column.name}", [])))

    def _hits(self, text: str) -> list[tuple[Column, int, int, str]]:
        hits = []
        for cols in self.schema.columns.values():
            for c in cols:
                for phrase in self._phrases(c):
                    for m in re.finditer(r'(?<!\w)' + re.escape(phrase.lower()) + r'(?!\w)', text):
                        hits.append((c, m.start(), m.end(), phrase))
        return hits

    def parse(self, question: str) -> Intent:
        text = question.lower().strip().replace(',', '')
        if not text or len(text) > 500:
            raise ParseError("Ask a non-empty question of at most 500 characters")
        hits = self._hits(text)
        intent = Intent()
        if not hits:
            raise ParseError("No database field could be linked to your question")
        # Detect aggregation first, prioritizing explicit summary intent.
        agg_match = next(((m, agg) for pattern, agg in AGGS if (m := re.search(pattern, text))), None)
        if agg_match:
            agg_token, intent.aggregation = agg_match
        else:
            agg_token = None
        # "top/highest/lowest N" expresses ORDER BY, not an aggregate.
        order_head = re.search(r'\b(?:top|highest|largest|biggest|lowest|smallest|bottom)\s+(\d+)\b', text)
        if order_head and intent.aggregation in ('MAX', 'MIN'):
            intent.aggregation = None
        # Gather conditions by searching local column mentions followed by comparisons.
        consumed: set[tuple[str, int]] = set()
        for col, start, end, phrase in sorted(hits, key=lambda x: (-len(x[3]), x[1])):
            if (col.table + '.' + col.name, start) in consumed:
                continue
            # only a short local window, stop at another explicit conjunction
            tail = text[end:end + 88]
            tail = re.split(r'\b(?:and|or|ordered|sorted|grouped|per|each)\b', tail)[0]
            condition = self._condition(col, tail)
            if condition:
                if condition not in intent.conditions:
                    intent.conditions.append(condition)
                consumed.add((col.table + '.' + col.name, start))
        # Handle "in 2024" after fields, even without an explicit "year" token.
        # Implied attributes such as "technology companies" and "companies in the UK".
        if 'companies' in self.schema.columns:
            if not any(c.column.name == 'sector' for c in intent.conditions):
                sector = next((v for v in ('technology', 'healthcare', 'energy', 'retail', 'automotive') if re.search(r'\b' + v + r'\b', text)), None)
                if sector:
                    intent.conditions.append(Condition(self.schema.lookup('sector', 'companies')[0], '=', sector.title()))
            if not any(c.column.name == 'country' for c in intent.conditions):
                country = re.search(r'\b(?:in|from|based in)\s+(?:the\s+)?(uk|us|germany|norway|canada)\b', text)
                if country:
                    region = country.group(1)
                    intent.conditions.append(Condition(self.schema.lookup('country', 'companies')[0], '=', region.upper() if region in ('uk', 'us') else region.title()))
        if 'financials' in self.schema.columns and 'year' in [c.name for c in self.schema.columns['financials']]:
            yrs = re.findall(r'\b(?:in|during|for)\s+(20\d\d)\b', text)
            if yrs and not any(c.column.name == 'year' for c in intent.conditions):
                intent.conditions.append(Condition(self.schema.lookup('year', 'financials')[0], '=', int(yrs[-1])))
        if 'financials' in self.schema.columns:
            # "2024 revenue" also means year=2024.
            years = re.findall(r'\b(20\d\d)\b', text)
            if years and not any(c.column.name == 'year' for c in intent.conditions):
                intent.conditions.append(Condition(self.schema.lookup('year', 'financials')[0], '=', int(years[0])))
        # GROUP BY signals, e.g. "average revenue by sector".
        gm = re.search(r'\b(?:by|per|for each|grouped by)\s+(\w+)', text)
        if gm and (intent.aggregation or 'group' in text):
            candidates = [h for h in hits if h[1] >= gm.start() and h[1] <= gm.end() + 26]
            if candidates:
                intent.group = max(candidates, key=lambda h: len(h[3]))[0]
        # Find selected quantity from mentions excluding columns used ONLY in filter clauses.
        cond_columns = {c.column for c in intent.conditions}
        pre = text[:agg_token.start()] if agg_token else text
        post = text[agg_token.end():] if agg_token else text
        preposition_stop = re.search(r'\b(?:where|with|whose|that|in|during|for the year)\b', post)
        target_window = (post[:preposition_stop.start()] if preposition_stop else post) if agg_token else (text.split(' where ')[0].split(' with ')[0].split(' whose ')[0].split(' that ')[0])
        target_hits = self._hits(target_window)
        if intent.group:
            target_hits = [x for x in target_hits if x[0] != intent.group]
        metrics = [h for h in target_hits if h[0].name not in ('name','id','company_id','year','country','sector')]
        if metrics and not (re.match(r'^(?:which|list|find|show me|show all)\s+companies\b', text) and not re.search(r'\b(?:top|highest|bottom|lowest|largest|smallest)\b', text) and not intent.aggregation):
            intent.target = metrics[0][0]
        elif intent.aggregation == 'COUNT':
            intent.target = None
        else:
            # names preferred for questions about which companies
            name = self.schema.lookup('name', 'companies')
            intent.target = name[0] if name else (target_hits[0][0] if target_hits else None)
        # A count is count of companies/rows, not count of the numeric metric.
        if intent.aggregation == 'COUNT':
            intent.target = None
        if not intent.aggregation:
            intent.select = intent.target
            if intent.select and intent.select.name not in ('name', 'id'):
                # For "show revenue" return both company name and numeric metric.
                intent.notes.append('Including entity name beside the requested metric')
        # Sort controls. For "top 5 companies by revenue" prefer metric after by.
        sort_match = re.search(r'\b(?:top|highest|largest|biggest|lowest|smallest|bottom)\s+(\d+)\b', text)
        if sort_match:
            intent.limit = min(int(sort_match.group(1)), 100)
            ascending = bool(re.search(r'\b(?:lowest|smallest|bottom)\b', text[:sort_match.end()]))
            sorted_hits = [h for h in hits if h[0].name not in ('name','id','company_id','year','country','sector')]
            if sorted_hits:
                intent.order = (sorted_hits[0][0], 'ASC' if ascending else 'DESC')
            elif intent.group and intent.aggregation:
                pass
            else:
                raise ParseError('Specify the numeric field to rank (for example: top 5 by revenue)')
        if not intent.order and re.search(r'\b(?:descending|ascending|sort by|order by)\b', text):
            sorted_hits = [h for h in hits if h[0].name not in ('name','id','company_id','year','country','sector')]
            if sorted_hits:
                intent.order = (sorted_hits[0][0], 'ASC' if 'ascending' in text else 'DESC')
        if not intent.select and not intent.aggregation:
            raise ParseError("Could not determine which database field to return")
        # Identical column with contradictory conditions is unsupported; refuse ambiguous grammar.
        seen = {}
        for c in intent.conditions:
            key = c.column.table, c.column.name
            if key in seen and seen[key] != (c.op, c.value):
                raise ParseError("Multiple constraints on the same field are not supported")
            seen[key] = (c.op, c.value)
        return intent

    def _condition(self, column: Column, tail: str) -> Condition | None:
        # Strip spaces/articles, and allow optional "was/is" before comparison.
        numeric = ('INT' in column.type or 'REAL' in column.type or 'NUM' in column.type or 'FLOAT' in column.type)
        rest = tail.lstrip(' :')
        if not rest:
            return None
        if numeric:
            # A date after another metric is a year filter, not a metric comparison.
            if column.name != 'year' and re.match(r'\s*(?:in|during|for|from)\s+20\d\d\b', rest):
                return None
            for pattern, op in OP_MAP:
                m = re.match(r'\s*(?:is\s+|was\s+|were\s+)?' + pattern + r'\s+([-+]?\d+(?:\.\d+)?)\s*(billion|million|thousand|bn|m|k)?\b', rest)
                if m:
                    number = float(m.group(1))
                    multiplier = {'billion': 1e9, 'bn': 1e9, 'million': 1e6, 'm': 1e6, 'thousand': 1e3, 'k': 1e3}.get(m.group(2), 1)
                    number *= multiplier
                    return Condition(column, op, int(number) if number.is_integer() else number)
            m = re.match(r'\s*(?:=|:)\s*(\d+(?:\.\d+)?)', rest)
            if m:
                return Condition(column, '=', float(m.group(1)))
            return None
        # Text attributes: "sector technology", "sector is healthcare", "country UK".
        if column.name not in ('sector', 'country', 'name'):
            return None
        if column.name == 'name' and not re.match(r'\s+(?:is|named|equals|equal to)\b', rest):
            return None
        m = re.match(r'\s*(?:is|equals|equal to|in|=|:)?\s*(the\s+)?([a-z][a-z ]{1,26})', rest)
        if not m:
            return None
        phrase = m.group(2).strip()
        phrase = re.split(r'\b(?:and|with|where|whose|in|for|during|by|above|below|over|under|more|less|greater|than|sorted|ordered)\b', phrase)[0].strip()
        if not phrase or phrase in STOPWORDS:
            return None
        # Limit text values to 1-2 tokens; uses equality only, never raw SQL.
        words = phrase.split()
        if column.name == 'name' and words[0] in ('of','named'):
            words = words[1:]
        if not words:
            return None
        value = ' '.join(words[:2]).strip()
        return Condition(column, '=', value.title() if column.name != 'country' else value.upper())
