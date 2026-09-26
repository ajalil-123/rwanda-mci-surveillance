# NHIC MCI Surveillance

Media-based surveillance of civilian Mass Casualty Incidents (MCI, 3+ deaths) in Rwanda,
for the National Health Intelligence Centre (NHIC).

| Folder | What it is | Runs on |
|---|---|---|
| `frontend/` | Next.js dashboard + login | Vercel |
| `scraper/` | Python scraper, NLP and AI checks (Gemini or Claude) | GitHub Actions, hourly |
| — | Postgres database | Neon |

---

## Run it locally (Windows / PowerShell)

### You need
- **Node.js 20.9+** and **Python 3.12+**
- A **Neon** connection string (use a `dev` branch in Neon so tests don't touch live data)

### 1. One-time setup

Run these from the project folder:

```powershell
# 1. Settings — one .env file for everything
copy .env.example .env
#    Open .env and fill in: DATABASE_URL, NEXTAUTH_SECRET, GEMINI_API_KEY

# 2. Python (scraper)
python -m venv venv
venv\Scripts\activate
pip install -r scraper\requirements.txt

# 3. Database tables (safe to re-run)
cd scraper
python jobs.py init-db
cd ..

# 4. Node (dashboard)
cd frontend
npm install
cd ..
```

Need a `NEXTAUTH_SECRET`? Generate one with:
```powershell
node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"
```

### 2. Start the dashboard

```powershell
cd frontend
npm run dev -- -p 3001
```

Open **http://localhost:3001/signup**, create an account, then sign in.
Stop it with `Ctrl+C`.

> Always use `npm run dev` (not `npx next dev`) — only the npm script loads the root `.env`.
> Port 3001 is used because Metabase already uses 3000 on this machine.

### 3. Get fresh data (optional — GitHub does this every hour)

In a second terminal:

```powershell
venv\Scripts\activate
cd scraper
python jobs.py scrape
```

The dashboard picks up new incidents within a minute.

---

## Useful commands

All scraper commands run from `scraper\` with the venv active:

| Command | What it does |
|---|---|
| `python jobs.py scrape` | Fetch new articles (a few minutes) |
| `python jobs.py scrape --historical` | Full backfill from 2010 (slow — only for an empty database) |
| `python jobs.py verify --all` | Re-check every incident with the AI (Rwanda + in scope?) |
| `python jobs.py summarize` | Write AI summaries for incidents without one |
| `python jobs.py eval-ai` | Test the AI against 16 labelled examples |
| `python jobs.py migrate-sqlite ..\data\mci_rwanda.db` | One-time import of the old SQLite data |
| `python jobs.py --help` | List everything |

Before pushing frontend changes:

```powershell
cd frontend
npm run type-check; npm run lint; npm run build
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "DATABASE_URL is not set" | Fill it in the root `.env`, then restart with `npm run dev` |
| Opening the site shows Metabase | You're on port 3000 — use **http://localhost:3001** |
| "Could not create the account" | Run `python jobs.py init-db` (creates the `users` table) |
| AI checks skipped | Add `GEMINI_API_KEY` to `.env` (and `AI_PROVIDER=gemini`) |
| Password-reset email not sent | Locally the reset link is printed in the `npm run dev` terminal |

---

## Deploy

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Neon → GitHub secrets → Vercel.
How it fits together: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
