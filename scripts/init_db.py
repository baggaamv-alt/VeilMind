"""Create the SQLite schema (idempotent)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import db  # noqa: E402
from app.config import settings  # noqa: E402

db.conn()
print(f"SQLite schema ready at {settings.db_path}")
