# Frontend Up Now (No Waiting)

If you just want the UI running immediately:

## 1) From repo root

```bash
cd frontend
npm install
npm run dev
```

Open: `http://localhost:5173`

## 2) What works without backend

- Public homepage renders.
- Legacy visual theme renders.

## 3) What needs backend

- `/admin` login and all admin tabs.
- Any dynamic content/API-backed data.

If backend is offline, admin now shows a clear "API offline" message instead of generic login failure.
