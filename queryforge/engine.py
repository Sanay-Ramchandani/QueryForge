"""Compile schema-grounded intents to parameterized, read-only SQL."""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3
from difflib import get_close_matches
from pathlib import Path
from .parser import SemanticParser, ParseError, Intent
from .schema import Schema, quote, Column


class QueryError(ValueError):
    pass


@dataclass
class QueryResult:
    question: str
    sql: str
    parameters: list[object]
    columns: list[str]
    rows: list[dict]
    reasoning: list[str]

    def as_dict(self) -> dict:
        return vars(self)


class QueryEngine:
    def __init__(self, database: str | Path):
        self.database = Path(database).resolve()
        if not self.database.is_file():
            raise FileNotFoundError(self.database)

    def _connection(self):
        # SQLite URI mode=ro prevents database writes even if application code changes.
        conn = sqlite3.connect(self.database.as_uri() + '?mode=ro', uri=True, timeout=2)
        conn.execute('PRAGMA query_only=ON')
        conn.row_factory = sqlite3.Row
        return conn

    def ask(self, question: str) -> QueryResult:
        with self._connection() as conn:
            schema = Schema(conn)
            try:
                intent = SemanticParser(schema).parse(question)
                repair_notes = self.repair_categorical_values(conn, schema, intent)
                sql, params, notes = self.compile(schema, intent)
                notes.extend(repair_notes)
                # Stop runaway queries; benchmark database is small, but enforce a limit.
                count = 0
                def progress():
                    nonlocal count
                    count += 1
                    return 1 if count > 2000 else 0
                conn.set_progress_handler(progress, 2000)
                rows = conn.execute(sql, params).fetchmany(101)
                if len(rows) > 100:
                    raise QueryError('Query returned more than 100 rows; refine the question')
                cols = list(rows[0].keys()) if rows else [part.split(' AS ')[-1].strip('" ') for part in sql.split(' FROM ')[0].split('SELECT ')[1].split(', ')]
                return QueryResult(question, sql, params, cols, [dict(row) for row in rows], notes)
            except (ParseError, sqlite3.DatabaseError, ValueError) as exc:
                raise QueryError(str(exc)) from exc
            finally:
                conn.set_progress_handler(None, 0)

    @staticmethod
    def repair_categorical_values(conn: sqlite3.Connection, schema: Schema, intent: Intent) -> list[str]:
        """Execution-aware value grounding, with high-threshold typo correction.

        Corrections are suggested only from values actually in the referenced
        database column. They never become SQL syntax; all values stay bound.
        """
        messages=[]
        for condition in intent.conditions:
            if not isinstance(condition.value, str) or condition.column.name not in ('sector', 'country', 'name'):
                continue
            qualifier=schema.qualify(condition.column)
            options=[row[0] for row in conn.execute(f'SELECT DISTINCT {qualifier} FROM {quote(condition.column.table)} WHERE {qualifier} IS NOT NULL LIMIT 1000')]
            actual={value.lower():value for value in options}
            if condition.value.lower() in actual:
                condition.value=actual[condition.value.lower()]
                continue
            matched=get_close_matches(condition.value.lower(), list(actual), n=1, cutoff=0.76)
            if matched:
                old=condition.value
                condition.value=actual[matched[0]]
                messages.append(f"Resolved value '{old}' to known {condition.column.name} '{condition.value}'")
        return messages

    @staticmethod
    def compile(schema: Schema, intent: Intent) -> tuple[str, list[object], list[str]]:
        involved = set()
        for c in (intent.target, intent.select, intent.group, intent.order[0] if intent.order else None):
            if c:
                involved.add(c.table)
        for cond in intent.conditions:
            involved.add(cond.column.table)
        if not intent.aggregation and intent.select and intent.select.name not in ('name','id') and 'companies' in schema.columns and 'financials' in involved:
            involved.add('companies')
        if not involved:
            involved = {next(iter(schema.columns))}
        primary = 'companies' if 'companies' in involved else sorted(involved)[0]
        joined = {primary}
        joins = []
        for target in sorted(involved - joined):
            for edge in schema.join_path(primary, target):
                if edge.from_table in joined and edge.to_table not in joined:
                    next_table = edge.to_table
                elif edge.to_table in joined and edge.from_table not in joined:
                    next_table = edge.from_table
                else:
                    continue
                joins.append(' JOIN ' + quote(next_table) + ' ON ' + schema.qualify(schema.lookup(edge.from_column, edge.from_table)[0]) + ' = ' + schema.qualify(schema.lookup(edge.to_column, edge.to_table)[0]))
                joined.add(next_table)
        if not involved.issubset(joined):
            raise QueryError('Disconnected table reference')
        clauses = []
        notes = list(intent.notes)
        metric = schema.qualify(intent.target) if intent.target else '*'
        if intent.aggregation:
            expression = f'{intent.aggregation}({metric})' if metric != '*' else 'COUNT(*)'
            clauses = ([f'{schema.qualify(intent.group)} AS category'] if intent.group else []) + [expression + ' AS value']
        else:
            assert intent.select
            # If metric, attach identifying name when joined to companies.
            if intent.select.name not in ('name', 'id') and 'companies' in joined:
                names = schema.lookup('name', 'companies')
                if names:
                    clauses.append(schema.qualify(names[0]) + ' AS entity')
            clauses.append(schema.qualify(intent.select) + (' AS entity' if intent.select.name == 'name' else ' AS value'))
        sql = 'SELECT ' + ', '.join(clauses) + ' FROM ' + quote(primary) + ''.join(joins)
        params = []
        if intent.conditions:
            sql += ' WHERE ' + ' AND '.join(schema.qualify(c.column) + ' ' + c.op + ' ?' + (' COLLATE NOCASE' if isinstance(c.value, str) else '') for c in intent.conditions)
            params = [c.value for c in intent.conditions]
            notes.append(f'Applied {len(intent.conditions)} parameterized filter(s)')
        if intent.group:
            sql += ' GROUP BY ' + schema.qualify(intent.group)
        if intent.order:
            order_column, direction = intent.order
            sql += ' ORDER BY ' + ('value' if intent.aggregation and intent.target == order_column else schema.qualify(order_column)) + ' ' + direction
        if intent.limit:
            sql += ' LIMIT ' + str(int(intent.limit))
        elif not intent.aggregation:
            sql += ' LIMIT 100'
        notes.insert(0, 'Resolved tables: ' + ', '.join(sorted(joined)))
        return sql, params, notes
