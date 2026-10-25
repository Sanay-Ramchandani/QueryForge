"""Nontrivial keyword-template baseline (not the published Seq2SQL model).

Understands basic projection, a single categorical filter, and one year filter.
It deliberately has no numerical inequality parser, GROUP BY, or ranking.
"""
from __future__ import annotations
import re
import sqlite3
from pathlib import Path


def keyword_baseline(dbfile: str|Path, question:str):
    q=question.lower()
    metric=next((m for m in ('revenue','profit','employees') if re.search(r'\b'+m+r'\b',q)),None)
    sector=next((v for v in ('technology','healthcare','energy','retail','automotive') if re.search(r'\b'+v+r'\b',q)),None)
    country=re.search(r'\b(?:in|from)\s+(?:the\s+)?(uk|us|germany|norway|canada)\b',q)
    year=re.search(r'\b(20\d\d)\b',q)
    # Skip unknown structures rather than returning plausibly incorrect queries.
    if re.search(r'\b(?:top|lowest|bottom|above|below|greater than|less than|by sector|by country)\b',q):
        return None
    with sqlite3.connect(dbfile) as conn:
        params=[]
        if re.search(r'how many|number of|count',q) and ('compan' in q):
            sql='SELECT COUNT(*) FROM companies'
            if country:
                sql+=' WHERE country=?';params=[country.group(1).upper() if country.group(1) in ('uk','us') else country.group(1).title()]
            elif sector:
                sql+=' WHERE sector=?';params=[sector.title()]
        elif not metric:
            if not re.search(r'\b(?:companies|company|firms)\b',q):
                return None
            sql='SELECT name FROM companies'
            if country:
                sql+=' WHERE country=?';params=[country.group(1).upper() if country.group(1) in ('uk','us') else country.group(1).title()]
            elif sector:
                sql+=' WHERE sector=?';params=[sector.title()]
        else:
            aggs = [('average','AVG'),('mean','AVG'),('total','SUM'),('sum','SUM')]
            agg=next((sqlop for token,sqlop in aggs if re.search(r'\b'+token+r'\b',q)),None)
            if agg:
                sql=f'SELECT {agg}({metric}) FROM financials'
            elif re.search(r'\b(?:show|get|list)\b',q):
                sql=f'SELECT companies.name, financials.{metric} FROM companies JOIN financials ON financials.company_id=companies.id'
            else:
                return None
            if year:
                sql+=' WHERE year=?';params=[int(year.group(1))]
        try:
            return [tuple(row) for row in conn.execute(sql,params)]
        except sqlite3.Error:
            return None
