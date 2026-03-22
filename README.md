# NBA 2K Legacy Vault (Phase C in Progress)

This repo has active runtime code in:
- `frontend/` → Vite + React
- `backend/` → restored legacy-capable FastAPI backend

## Local run

### 1) Start PostgreSQL

```bash
docker compose up -d db
```

### 2) Start backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3) Start frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Frontend URL: `http://localhost:5173`
Backend URL: `http://localhost:8000`
Admin URL: `http://localhost:5173/admin`

## Auth and environment

`backend/.env`:
- `DATABASE_URL`
- `ADMIN_PASSWORD`
- `ADMIN_TOKEN` (must match admin header token returned by login)
- `PORT` (set by cloud providers like Railway; app now honors this automatically)
- `CORS_ORIGINS` (comma-separated allowed front-end origins)
- `EDITOR_ALLOW_RUN_COMMAND` (`false` by default for safety)
- optional AI/deploy/storage credentials

`frontend/.env`:
- `VITE_API_BASE_URL=http://localhost:8000`

## Final local verification checklist (simple mode)

Use this exact checklist in order.

### A) Exact env vars to set

1. Copy the sample env files:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

2. Confirm these required values exist in `backend/.env`:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/nba_vault
ADMIN_PASSWORD=CHANGE_ME_STRONG_PASSWORD
ADMIN_TOKEN=CHANGE_ME_RANDOM_ADMIN_TOKEN
PYTHON_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
EDITOR_ALLOW_RUN_COMMAND=false
```

3. Confirm this exists in `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

### B) Exact commands to start everything

Run these in 3 terminals.

**Terminal 1 (Postgres):**

```bash
cd /workspace/Aidanisthatguy77-NBA2K-Legacy-Vault-Frontend
docker compose up -d db
docker compose ps
```

**Terminal 2 (backend):**

```bash
cd /workspace/Aidanisthatguy77-NBA2K-Legacy-Vault-Frontend/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 3 (frontend):**

```bash
cd /workspace/Aidanisthatguy77-NBA2K-Legacy-Vault-Frontend/frontend
npm install
npm run dev
```

### C) Exact URLs to open

Open these URLs in your browser:
- Homepage: `http://localhost:5173/`
- Admin: `http://localhost:5173/admin`
- Backend docs: `http://localhost:8000/docs`

### D) Step-by-step manual tests + what success looks like

#### 1) Homepage

Steps:
1. Open `http://localhost:5173/`.
2. Verify hero/title area renders.
3. Verify sections load without white screen.

Success looks like:
- Page loads and is readable.
- No crash overlay in browser.
- Backend terminal shows normal requests (no 500 spam).

Known failure cases:
- Blank page with frontend error overlay.
- CORS/API errors in browser console.
- Repeating 500s in backend log.

#### 2) Admin login

Steps:
1. Open `http://localhost:5173/admin`.
2. Enter password from `backend/.env` (`ADMIN_PASSWORD`).
3. Click **Login**.

Success looks like:
- Login succeeds.
- Admin tabs appear (Content, Games, Community, Creator, Health, Doctor, etc.).
- You are not stuck on login form.

Known failure cases:
- `Invalid password` (wrong `ADMIN_PASSWORD`).
- `401 Unauthorized` on admin calls (token mismatch or missing token).
- Network error if backend is not running on `:8000`.

#### 3) Content tab

Steps:
1. Click **Content**.
2. Click an existing key from the list.
3. Change value text.
4. Click **Save Content**.
5. Click **Seed Defaults** once.
6. Click **Content** again to refresh.

Success looks like:
- Save action completes without error toast.
- Updated key/value appears after refresh.
- Seed action repopulates defaults.

Known failure cases:
- Save returns 4xx/5xx.
- Content list empty and never repopulates.
- Button click does nothing because backend request fails.

#### 4) Games tab

Steps:
1. Click **Games**.
2. Create a game using the form.
3. Verify new game appears in the list.
4. Click **Update** on that game.
5. Click **Delete** on that game.

Success looks like:
- New game appears immediately after create.
- Update call returns success and list refreshes.
- Deleted game disappears from list.

Known failure cases:
- Validation errors for missing required fields.
- Update/Delete fails due to stale/nonexistent ID.
- UI list does not refresh after mutation.

#### 5) Community tab

Steps:
1. Click **Community**.
2. Fill post form (platform, author, handle, content).
3. Click **Create Community Post**.
4. Verify it appears in list.
5. Click **Delete** on that post.

Success looks like:
- Post is created and visible.
- Delete removes post from list.

Known failure cases:
- Required-field validation failures.
- Create succeeds but list does not reload.
- Delete fails with 404 if record already removed.

#### 6) Creator tab

Steps:
1. Click **Creator**.
2. For one submission, click **Approve**.
3. Click **Reject** for another (or same) submission.
4. Click **Pending** to set it back.

Success looks like:
- Status changes persist after tab reload.
- No 401/500 in network responses.

Known failure cases:
- No submissions shown (empty seed data).
- Status action returns error and snaps back.
- Permission/token error blocks updates.

#### 7) Health tab

Steps:
1. Click **Health**.
2. Click **Trigger Health Check**.
3. Wait a few seconds.
4. Click **Refresh**.

Success looks like:
- Health rows show component statuses.
- Latest check timestamp updates.
- No fatal backend errors while checking.

Known failure cases:
- Health table stays empty forever.
- Status remains error for DB/API repeatedly.
- Trigger endpoint returns 500.

#### 8) Doctor tab

Steps:
1. Click **Doctor**.
2. Click **Run Diagnostic**.
3. Enter a short problem (example: `health endpoint returning errors`).
4. Click **Solve**.
5. Click **Reset**.
6. Click **Lock-In Check**.

Success looks like:
- Diagnostic report returns with overall status.
- Solve returns structured result (actions/errors).
- Reset runs steps and returns summary.
- Lock-In returns pass/fail summary without crashing.

Known failure cases:
- Solve fails when AI key is missing/misconfigured.
- Reset partially fails if one subsystem is unavailable.
- Lock-In fails if local compile/test commands fail.

### E) Fast sanity checks (optional but recommended)

```bash
# backend health
curl -sS http://localhost:8000/api/health | jq

# admin login (returns token)
curl -sS -X POST http://localhost:8000/api/admin/login \
  -H 'content-type: application/json' \
  -d '{"password":"CHANGE_ME_STRONG_PASSWORD"}' | jq
```

Expected:
- `/api/health` returns JSON with service status.
- `/api/admin/login` returns `{ "success": true, "token": "..." }`.

## Phase C focus

Core tabs now getting full operator workflows:
- Content
- Games
- Community
- Creator
- Health
- Doctor
- Mission Control (single conversation endpoint for cross-tab planning/execution)

## Mission Control quick commands

Plan only (no execution):

```bash
curl -sS -X POST http://localhost:8000/api/admin/operator-agent/chat \
  -H "content-type: application/json" \
  -H "x-admin-token: CHANGE_ME_RANDOM_ADMIN_TOKEN" \
  -d '{"message":"show dashboard summary and health status","execute":false}' | jq
```

Execute actions:

```bash
curl -sS -X POST http://localhost:8000/api/admin/operator-agent/chat \
  -H "content-type: application/json" \
  -H "x-admin-token: CHANGE_ME_RANDOM_ADMIN_TOKEN" \
  -d '{"message":"run health check and show deploy history","execute":true}' | jq
```

Get exact action capability matrix:

```bash
curl -sS http://localhost:8000/api/admin/operator-agent/capabilities \
  -H "x-admin-token: CHANGE_ME_RANDOM_ADMIN_TOKEN" | jq
```

## Railway transfer setup (from `work` branch)

If you are on phone and cannot use git push buttons in-app, do this from any terminal:

```bash
git remote add origin https://github.com/Aidanisthatguy77/NBA2K-Legacy-Vault.git
git push -u origin work
```

Then in Railway:

1. **New Project** → **Deploy from GitHub repo**
2. Select `Aidanisthatguy77/NBA2K-Legacy-Vault`
3. For backend service, set:
   - **Root Directory:** `backend`
   - **Start Command:** `python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add PostgreSQL plugin/service in Railway
5. Set backend env vars:
   - `DATABASE_URL` (from Railway Postgres)
   - `ADMIN_PASSWORD`
   - `ADMIN_TOKEN`
   - `CORS_ORIGINS` (your frontend domain)
   - `EDITOR_ALLOW_RUN_COMMAND=false`
6. Deploy and test:
   - `GET https://<backend-domain>/api/health`
   - `POST https://<backend-domain>/api/admin/login`

## One-command predeploy check

Run this before pushing/deploying:

```bash
./scripts/predeploy_check.sh
```

If you want a short no-code launch flow, follow `DEPLOY_NOW.md`.
