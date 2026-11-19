import sqlite3
import json
from typing import List, Optional
from app.models import CaseFile
from app.config import settings

def get_connection():
    conn = sqlite3.connect(settings.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id TEXT PRIMARY KEY,
            borrower_name TEXT,
            phone TEXT,
            language TEXT,
            amount_due REAL,
            due_date TEXT,
            dpd INTEGER,
            loan_id TEXT,
            status TEXT,
            version INTEGER,
            data_json TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS case_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT,
            version INTEGER,
            data_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_case(case: CaseFile):
    conn = get_connection()
    cursor = conn.cursor()
    data_json = case.model_dump_json()
    
    cursor.execute("""
        INSERT INTO cases (id, borrower_name, phone, language, amount_due, due_date, dpd, loan_id, status, version, data_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            borrower_name=excluded.borrower_name,
            phone=excluded.phone,
            language=excluded.language,
            amount_due=excluded.amount_due,
            due_date=excluded.due_date,
            dpd=excluded.dpd,
            loan_id=excluded.loan_id,
            status=excluded.status,
            version=excluded.version,
            data_json=excluded.data_json,
            updated_at=CURRENT_TIMESTAMP
    """, (
        case.id,
        case.borrower_name,
        case.phone,
        case.language,
        case.amount_due,
        case.due_date,
        case.dpd,
        case.loan_id,
        case.status,
        case.version,
        data_json
    ))
    
    # Save to history for versioning
    cursor.execute("""
        INSERT INTO case_history (case_id, version, data_json)
        VALUES (?, ?, ?)
    """, (case.id, case.version, data_json))

    conn.commit()
    conn.close()

def get_case(case_id: str) -> Optional[CaseFile]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT data_json FROM cases WHERE id = ?", (case_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return CaseFile.model_validate_json(row["data_json"])
    return None

def get_all_cases() -> List[CaseFile]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT data_json FROM cases ORDER BY CAST(id AS INTEGER) ASC")
    rows = cursor.fetchall()
    conn.close()
    return [CaseFile.model_validate_json(r["data_json"]) for r in rows]

def clear_all_cases():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cases")
    cursor.execute("DELETE FROM case_history")
    conn.commit()
    conn.close()
