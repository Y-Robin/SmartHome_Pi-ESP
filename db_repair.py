import os
import shutil
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def repair_sqlite_database(db_path: str) -> Dict[str, object]:
    if not os.path.exists(db_path):
        return {
            'ok': False,
            'message': 'Datenbankdatei wurde nicht gefunden.',
            'db_path': db_path,
        }

    stamp = _utc_stamp()
    backup_path = f"{db_path}.corrupt.{stamp}.bak"
    repaired_path = f"{db_path}.repaired.{stamp}"

    shutil.copy2(db_path, backup_path)

    copied_tables: List[str] = []
    failed_tables: List[Dict[str, str]] = []

    source = sqlite3.connect(db_path)
    target = sqlite3.connect(repaired_path)
    try:
        source.execute('PRAGMA query_only=ON;')

        table_rows = source.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
        ).fetchall()

        for table_name, create_sql in table_rows:
            if not create_sql:
                continue
            try:
                target.execute(create_sql)
                rows = source.execute(f"SELECT * FROM {_quote_identifier(table_name)}").fetchall()
                if rows:
                    placeholders = ','.join(['?'] * len(rows[0]))
                    target.executemany(
                        f"INSERT INTO {_quote_identifier(table_name)} VALUES ({placeholders})",
                        rows,
                    )
                copied_tables.append(table_name)
            except Exception as error:
                failed_tables.append({'table': table_name, 'error': str(error)})

        target.commit()
    finally:
        source.close()
        target.close()

    os.replace(repaired_path, db_path)

    return {
        'ok': True,
        'message': 'SQLite-Reparatur abgeschlossen (Best-Effort).',
        'db_path': db_path,
        'backup_path': backup_path,
        'copied_tables': copied_tables,
        'failed_tables': failed_tables,
    }
