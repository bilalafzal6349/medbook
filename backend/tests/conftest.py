import os
import sys
import tempfile
from pathlib import Path

# Fixed clock (Monday 23 Nov 2026, 9:00 PKT) and a throwaway database, set before any import.
os.environ["MEDBOOK_NOW"] = "2026-11-23T09:00"
os.environ.pop("DATABASE_URL", None)   # tests always use SQLite and in-memory sessions
os.environ.pop("REDIS_URL", None)
os.environ["MEDBOOK_DB"] = str(Path(tempfile.mkdtemp()) / "test.db")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
