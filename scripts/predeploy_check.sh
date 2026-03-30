#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/7] Checking required project files..."
for f in backend/app/main.py backend/.env.example frontend/.env.example frontend/package.json docker-compose.yml README.md; do
  [[ -f "$f" ]] || { echo "Missing file: $f"; exit 1; }
done

echo "[2/7] Checking git working tree..."
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is not clean. Commit or stash changes before deploy."
  exit 1
fi

echo "[3/7] Python syntax check..."
python3 -m py_compile backend/app/main.py

echo "[4/7] Verifying backend env keys in backend/.env.example..."
for key in DATABASE_URL ADMIN_PASSWORD ADMIN_TOKEN PYTHON_PORT CORS_ORIGINS EDITOR_ALLOW_RUN_COMMAND; do
  grep -q "^${key}=" backend/.env.example || { echo "Missing backend env key: $key"; exit 1; }
done

echo "[5/7] Verifying frontend env key in frontend/.env.example..."
grep -q '^VITE_API_BASE_URL=' frontend/.env.example || { echo "Missing frontend env key: VITE_API_BASE_URL"; exit 1; }

echo "[6/7] Checking start/build commands exist..."
python3 - <<'PY'
import json
with open('frontend/package.json') as f:
    pkg = json.load(f)
for k in ['dev','build']:
    if k not in pkg.get('scripts', {}):
        raise SystemExit(f"Missing npm script: {k}")
print('frontend scripts ok')
PY

echo "[7/7] Readiness checks passed."
echo "Next: push main branch and deploy backend+db+frontend per README."
