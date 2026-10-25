"""Deterministic fictional business dataset; no company figures are real."""
from __future__ import annotations
import sqlite3
from pathlib import Path

COMPANIES = [
    ('Aster Labs','Technology','UK'),
    ('Beacon Health','Healthcare','US'),
    ('Cobalt Systems','Technology','US'),
    ('Delta Energy','Energy','UK'),
    ('Evergreen Pharma','Healthcare','Germany'),
    ('Fjord Analytics','Technology','Norway'),
    ('Granite Power','Energy','US'),
    ('Harbor Retail','Retail','UK'),
    ('Ion Motors','Automotive','Germany'),
    ('Juniper Stores','Retail','US'),
    ('Kite Mobility','Automotive','UK'),
    ('Lumen Cloud','Technology','Canada'),
    ('Marble Care','Healthcare','Canada'),
    ('Northstar Energy','Energy','Norway'),
    ('Orbit Markets','Retail','Germany'),
]

def make_demo_db(path: str | Path) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    with sqlite3.connect(dest) as db:
        db.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, sector TEXT NOT NULL, country TEXT NOT NULL);
        CREATE TABLE financials (
            id INTEGER PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            year INTEGER NOT NULL,
            revenue INTEGER NOT NULL,
            profit INTEGER NOT NULL,
            employees INTEGER NOT NULL,
            UNIQUE(company_id, year)
        );
        CREATE INDEX idx_financials_year ON financials(year);
        ''')
        for i, (name, sector, country) in enumerate(COMPANIES, start=1):
            db.execute('INSERT INTO companies(name,sector,country) VALUES(?,?,?)',(name,sector,country))
            for year in range(2022, 2026):
                revenue = (20 + i * 17 + (year - 2022) * (i % 5 + 3)) * 1_000_000
                profit = revenue * (6 + i % 17) // 100
                employees = 120 + i * 37 + (year - 2022) * (i + 8)
                db.execute('INSERT INTO financials(company_id,year,revenue,profit,employees) VALUES(?,?,?,?,?)',
                           (i, year, revenue, profit, employees))
    return dest
