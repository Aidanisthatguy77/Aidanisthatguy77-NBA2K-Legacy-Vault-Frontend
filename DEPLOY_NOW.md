## Deploy status

Yes — this repository is ready and waiting on GitHub. Deployment is the last step.

# Deploy Now (No-Code Gap Closer)

Use this exact quick flow.

## 1) Run predeploy checks

```bash
./scripts/predeploy_check.sh
```

## 2) Push latest main

```bash
git checkout main
git pull --ff-only
git push
```

## 3) Deploy backend + DB

- Host backend with `backend/` as root.
- Start command:

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

- Set backend env vars:
  - `DATABASE_URL`
  - `ADMIN_PASSWORD`
  - `ADMIN_TOKEN`
  - `CORS_ORIGINS`
  - `EDITOR_ALLOW_RUN_COMMAND=false`

## 4) Deploy frontend

- Host `frontend/`.
- Build command: `npm run build`
- Env:
  - `VITE_API_BASE_URL=https://<your-backend-domain>`

## 5) Smoke test (2 minutes)

- `GET /api/health` returns JSON.
- Open frontend homepage.
- Open `/admin` and login.
- In admin: trigger Health check and load Mission Control plan mode.


## Final done-state

Deployment is complete when all are true:
- Backend health endpoint responds: `GET /api/health`
- Frontend URL loads publicly
- Admin page (`/admin`) accepts your admin password
- CORS and env vars are set for your public domains


## Want the free-first deploy path?

Use `FREE_DEPLOY_ALLIN.md` for the all-in free setup (Render + Vercel).
