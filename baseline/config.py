from __future__ import annotations
import hashlib
import json
import os
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ARTIFACTS = ROOT / "artifacts"
WAREHOUSE = DATA / "warehouse.duckdb"
METRIC_VERSION = "metrics-v2"
KEY_VERSION = "match-v2"

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + "\n")
    tmp.replace(path)

def reserve(required_gb=4):
    free = shutil.disk_usage(ROOT).free / 1024**3
    if free < required_gb + 5:
        raise RuntimeError(f"Build needs {required_gb} GiB working space plus 5 GiB reserve; {free:.1f} GiB free. Free disk space and retry.")

def connect(path=WAREHOUSE, read_only=False):
    con = duckdb.connect(str(path), read_only=read_only)
    con.execute("SET memory_limit='2GB'")
    con.execute("SET threads=2")
    con.execute("SET preserve_insertion_order=true")
    return con

def records(con, sql, params=None):
    cur = con.execute(sql, params or [])
    cols = [x[0] for x in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def serving_path():
    return Path(os.environ.get("BASELINE_DB", DATA / "releases/current/serving.duckdb"))
