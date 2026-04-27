
import sqlite3
import os

DB_PATH = '/Users/artembutko/Desktop/fz_parser/sql_app.db'

def upgrade_db():
    print(f"Connecting to {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tables: {tables}")

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN telegram_id INTEGER")
        print("Added telegram_id column")
    except sqlite3.OperationalError as e:
        print(f"Skipping telegram_id: {e}")

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN telegram_connect_code VARCHAR")
        print("Added telegram_connect_code column")
    except sqlite3.OperationalError as e:
        print(f"Skipping telegram_connect_code: {e}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    upgrade_db()
