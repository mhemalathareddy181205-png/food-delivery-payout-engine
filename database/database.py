import sqlite3
from config import DB_PATH, ROOT

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript((ROOT / "database" / "schema.sql").read_text(encoding="utf-8"))
    # Keep existing project databases usable as the documented ledger gains columns.
    migrations = {
        "settlements": {"platform_discounts": "TEXT NOT NULL DEFAULT '0.00'", "delivery_fees": "TEXT NOT NULL DEFAULT '0.00'", "platform_fees": "TEXT NOT NULL DEFAULT '0.00'", "platform_refunds": "TEXT NOT NULL DEFAULT '0.00'"},
        "settlement_audit": {"platform_fee": "TEXT NOT NULL DEFAULT '0.00'", "delivery_fee": "TEXT NOT NULL DEFAULT '0.00'", "breakup_json": "TEXT NOT NULL DEFAULT '{}'"},
        "disputes": {"refund_amount": "TEXT NOT NULL DEFAULT '0.00'", "refund_reason": "TEXT NOT NULL DEFAULT ''"},
    }
    for table, columns in migrations.items():
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    return db
