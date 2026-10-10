"""Check the database connection (SQLite or Supabase) and create the tables.  Usage:  python scripts/check_db.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config as C, db, users

print("Backend:", "Supabase / Postgres" if C.USE_POSTGRES else f"SQLite ({C.DATA})")
try:
    if C.USE_POSTGRES:
        users.list_users()          # creates the studypilot.learners registry
        db.init()                   # creates the tables for learner 0 (the 'no learner selected' workspace)
        row = db.admin_q("select current_database() db, current_user usr, version() v")[0]
        print(f"Connected to database '{row['db']}' as '{row['usr']}'.\n{row['v'][:60]}")
        print("Learners:", len(users.list_users()))
    else:
        db.init(); print("SQLite database ready.")
    print("DATABASE OK")
except Exception as e:
    print("DATABASE ERROR:", e)
    print("Check DATABASE_URL in .env (use the Supabase 'Session pooler' string and your database password).")
    sys.exit(1)
