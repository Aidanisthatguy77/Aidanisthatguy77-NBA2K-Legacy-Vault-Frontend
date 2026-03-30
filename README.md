# NBA 2K Legacy Vault — Official GitHub Source

This repository now keeps the **full NBA 2K Legacy Vault source on GitHub** with a clear split between:

- `legacy_export/` → the original legacy front-end/app files preserved as the canonical archive
- `frontend/` → the modern Vite + React interface
- `backend/` → the FastAPI API/admin backend

If your goal is to confirm the project is officially present on GitHub in full, the legacy code has been retained in-repo instead of removed.

## Project layout

```text
.
├── backend/                 # FastAPI API + admin services
├── frontend/                # Vite + React frontend
├── legacy_export/           # Original legacy vault files (full archive)
├── scripts/predeploy_check.sh
├── docker-compose.yml
└── DEPLOY_NOW.md
```

## Quick local run

### 1) Start PostgreSQL

```bash
docker compose up -d db
```

### 2) Run backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3) Run frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`


## Deployment status

Yes — the codebase is now in GitHub and deployment-ready. At this stage, it is essentially **"sitting on GitHub waiting to be deployed"** once you connect hosting for:

1. PostgreSQL database
2. `backend/` service
3. `frontend/` static site

Use `DEPLOY_NOW.md` for the exact launch sequence.

## Legacy archive notes

- All legacy UI/component files are preserved under `legacy_export/`.
- A recovered legacy social preview asset is now present at `legacy_export/opengraph.jpg`.
- Legacy code is intentionally separated to keep the modern runtime (`frontend/` + `backend/`) clean while still preserving the historical codebase in full.

## Pre-deploy check

```bash
./scripts/predeploy_check.sh
```

This verifies backend syntax and frontend script readiness before deploy.

## Deploy

See `DEPLOY_NOW.md` for the fastest path to publish.


## Free deploy (all-in)

If you want the fastest no-cost launch path, follow `FREE_DEPLOY_ALLIN.md` (Render free backend+DB + Vercel hobby frontend).


## Frontend only (get it up right now)

If you want the frontend running immediately without waiting on backend setup, use `FRONTEND_NOW.md`.
