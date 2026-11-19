import sqlite3
import json
from typing import List, Optional
from app.models import JourneyRecord, CaseFile
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
            id TEXT,
            workflow_id TEXT DEFAULT 'collections',
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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id, workflow_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS case_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT,
            workflow_id TEXT,
            version INTEGER,
            data_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_case(record: JourneyRecord):
    conn = get_connection()
    cursor = conn.cursor()
    data_json = record.model_dump_json()
    
    cursor.execute("""
        INSERT INTO cases (id, workflow_id, borrower_name, phone, language, amount_due, due_date, dpd, loan_id, status, version, data_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id, workflow_id) DO UPDATE SET
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
        record.id,
        record.workflow_id or "collections",
        record.customer_name,
        record.phone,
        record.language,
        record.amount_due,
        record.due_date,
        record.dpd,
        record.loan_id,
        record.status,
        record.version,
        data_json
    ))
    
    cursor.execute("""
        INSERT INTO case_history (case_id, workflow_id, version, data_json)
        VALUES (?, ?, ?, ?)
    """, (record.id, record.workflow_id, record.version, data_json))

    conn.commit()
    conn.close()

def get_case(case_id: str, workflow_id: str = "collections") -> Optional[JourneyRecord]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT data_json FROM cases WHERE id = ? AND workflow_id = ?", (case_id, workflow_id))
    row = cursor.fetchone()
    conn.close()
    if row:
        return JourneyRecord.model_validate_json(row["data_json"])
    return None

def get_all_cases(workflow_id: Optional[str] = "collections") -> List[JourneyRecord]:
    conn = get_connection()
    cursor = conn.cursor()
    if workflow_id:
        cursor.execute("SELECT data_json FROM cases WHERE workflow_id = ? ORDER BY CAST(id AS INTEGER) ASC", (workflow_id,))
    else:
        cursor.execute("SELECT data_json FROM cases ORDER BY CAST(id AS INTEGER) ASC")
    rows = cursor.fetchall()
    conn.close()
    return [JourneyRecord.model_validate_json(r["data_json"]) for r in rows]

def clear_all_cases(workflow_id: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    if workflow_id:
        cursor.execute("DELETE FROM cases WHERE workflow_id = ?", (workflow_id,))
        cursor.execute("DELETE FROM case_history WHERE workflow_id = ?", (workflow_id,))
    else:
        cursor.execute("DELETE FROM cases")
        cursor.execute("DELETE FROM case_history")
    conn.commit()
    conn.close()
