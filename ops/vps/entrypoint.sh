#!/bin/sh
set -e
# Create/migrate the database and seed the LPU subject registry and the curated
# MCQ bank on every boot. Idempotent: seed_topics renames legacy codes in place
# and refreshes metadata; seed_mcq_bank upserts questions on their stable key
# and retires (never deletes) any that left the JSON.
python - <<'PY'
import os
from recall.api.app import bootstrap
from recall.db import connect
from recall.mcq.seed import seed_mcq_bank
from recall.seed import seed_topics

db = os.environ.get("RECALL_DB", "/data/recall.db")
bootstrap(db)
conn = connect(db)
conn.execute("INSERT OR IGNORE INTO users (id, name) VALUES (1, 'yash')")
conn.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (1)")
conn.commit()
print("topics:", seed_topics(conn))
print("mcq:", seed_mcq_bank(conn))
print(f"database ready at {db}")
PY
exec uvicorn recall.api.app:app --host 0.0.0.0 --port 8000 --log-level info
