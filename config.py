"""Shared application configuration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "database" / "settlements.sqlite3"
OUTPUT_DIR = ROOT / "output"
CENT = "0.01"
