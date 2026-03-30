# All-In Free App Deployer (NBA 2K Legacy Vault)

This is the **free-first deployment plan** so the app is fully online with no paid tier required to start.

## Recommended free stack

1. **Backend API + Postgres DB**: Render (Free web service + Free Postgres)
2. **Frontend**: Vercel (Hobby)

This keeps setup simple while staying in free tiers.

---

## 1) Prepare GitHub repo

Make sure `main` is up to date:

```bash
git checkout main
git pull --ff-only
git push
```

---

## 2) Deploy backend + DB on Render (Free)

### Create database

- In Render dashboard: **New → Postgres → Free**
- Save the generated internal/external DB URL.

### Create backend web service

- **New → Web Service → select this repo**
- Root directory: `backend`
- Build command:

```bash
pip install -r requirements.txt
```

- Start command:

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Backend env vars

Set these in Render:

- `DATABASE_URL` = your Render Postgres URL
- `ADMIN_PASSWORD` = strong admin password
- `ADMIN_TOKEN` = random long token
- `CORS_ORIGINS` = include your Vercel frontend URL (and local URLs if needed)
- `EDITOR_ALLOW_RUN_COMMAND` = `false`

After deploy, copy the backend URL, e.g. `https://nba2k-legacy-api.onrender.com`

---

## 3) Deploy frontend on Vercel (Hobby)

- Import this repo in Vercel.
- Set **Root Directory** to `frontend`.
- Framework preset: Vite (auto-detected).
- Env var:

```env
VITE_API_BASE_URL=https://<your-render-backend-domain>
```

Deploy and copy your public frontend URL.

---

## 4) Final wiring check

1. Open backend health endpoint:
   - `https://<backend-domain>/api/health`
2. Open frontend URL and verify homepage loads.
3. Open `<frontend>/admin` and login with `ADMIN_PASSWORD`.
4. Ensure browser network calls hit your Render API domain and return 2xx.

---

## 5) Free-tier expectations (important)

- Render free web services can spin down when idle.
- Free tiers are best for launch/testing and may have usage limits.
- If traffic grows, upgrade backend/DB first for reliability.

---

## Quick copy/paste env map

### Render backend

```env
DATABASE_URL=postgresql://...
ADMIN_PASSWORD=change-me
ADMIN_TOKEN=change-me-random
CORS_ORIGINS=https://<frontend-domain>,http://localhost:5173,http://127.0.0.1:5173
EDITOR_ALLOW_RUN_COMMAND=false
```

### Vercel frontend

```env
VITE_API_BASE_URL=https://<backend-domain>
```
