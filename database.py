import sqlite3
import json
from datetime import datetime

DB_PATH = "data/fx_monitor.db"


def init_db():
    """테이블 초기화 (최초 실행 시)"""
    import os
    os.makedirs("data", exist_ok=True)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS exchange_rates (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            usd_krw   REAL,
            jpy_krw   REAL,
            eur_krw   REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            filepath    TEXT,
            changes     TEXT,
            analysis    TEXT
        )
    """)

    con.commit()
    con.close()


def save_rates(rates: dict):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO exchange_rates (timestamp, usd_krw, jpy_krw, eur_krw) VALUES (?,?,?,?)",
        (datetime.now().isoformat(), rates.get("USD"), rates.get("JPY"), rates.get("EUR"))
    )
    con.commit()
    con.close()


def save_report(filepath: str, changes: dict, analysis: str):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO reports (timestamp, filepath, changes, analysis) VALUES (?,?,?,?)",
        (datetime.now().isoformat(), filepath, json.dumps(changes), analysis)
    )
    con.commit()
    con.close()


def get_history(limit: int = 60) -> list:
    """최근 N건 환율 이력 조회"""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT timestamp, usd_krw, jpy_krw, eur_krw FROM exchange_rates "
        "ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()

    return [
        {"timestamp": r[0], "USD": r[1], "JPY": r[2], "EUR": r[3]}
        for r in reversed(rows)
    ]
