#!/bin/sh
set -e
# Create the database and seed topics on first boot. Idempotent.
python - <<'PY'
import os
from recall.api.app import bootstrap
from recall.db import connect
db = os.environ.get("RECALL_DB", "/data/recall.db")
bootstrap(db)
conn = connect(db)
conn.execute("INSERT OR IGNORE INTO users (id, name) VALUES (1, 'yash')")
conn.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (1)")
for code, label in (("MATHS", "Mathematics"), ("CSE111", "CSE111"),
                    ("INT108", "INT108"), ("INT335", "INT335"), ("HTML", "HTML")):
    conn.execute("INSERT OR IGNORE INTO topics (user_id, code, label) VALUES (1,?,?)",
                 (code, label))
conn.commit()
print(f"database ready at {db}")
PY
exec uvicorn recall.api.app:app --host 0.0.0.0 --port 8000 --log-level info
