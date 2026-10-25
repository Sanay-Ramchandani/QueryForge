"""SQLite schema introspection and safe identifier handling."""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class Column:
    table: str
    name: str
    type: str


@dataclass(frozen=True)
class ForeignKey:
    from_table: str
    from_column: str
    to_table: str
    to_column: str


class Schema:
    def __init__(self, conn: sqlite3.Connection):
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        self.columns: dict[str, list[Column]] = {}
        self.foreign_keys: list[ForeignKey] = []
        for (table,) in tables:
            self.columns[table] = [Column(table, row[1], row[2].upper()) for row in conn.execute(f"PRAGMA table_info({quote(table)})")]
            for row in conn.execute(f"PRAGMA foreign_key_list({quote(table)})"):
                self.foreign_keys.append(ForeignKey(table, row[3], row[2], row[4]))
        if not self.columns:
            raise ValueError("The database has no user tables")

    def lookup(self, name: str, table: str | None = None) -> list[Column]:
        return [c for t, cols in self.columns.items() for c in cols if c.name == name and (table is None or table == t)]

    def qualify(self, c: Column) -> str:
        return f"{quote(c.table)}.{quote(c.name)}"

    def join_path(self, start: str, destination: str) -> list[ForeignKey]:
        # Join edges may be traversed in either direction; the SQL equality is symmetric.
        if start == destination:
            return []
        from collections import deque
        queue = deque([(start, [])])
        visited = {start}
        while queue:
            node, path = queue.popleft()
            for edge in self.foreign_keys:
                neighbor = edge.to_table if edge.from_table == node else edge.from_table if edge.to_table == node else None
                if neighbor is None or neighbor in visited:
                    continue
                nxt = path + [edge]
                if neighbor == destination:
                    return nxt
                visited.add(neighbor)
                queue.append((neighbor, nxt))
        raise ValueError(f"No foreign-key join connects {start} to {destination}")


def quote(identifier: str) -> str:
    """Quote schema-derived SQLite identifiers; never insert user text as identifiers."""
    return '"' + identifier.replace('"', '""') + '"'
