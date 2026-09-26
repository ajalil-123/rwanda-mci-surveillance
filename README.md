# NHIC MCI Surveillance

Media-based surveillance of civilian Mass Casualty Incidents (MCI, ≥ 3 deaths) in Rwanda,
for Rwanda's National Health Intelligence Centre (NHIC).

```
frontend/   Next.js 16 dashboard — deployed on Vercel, reads Neon directly
scraper/    Python scraper + NLP + AI checks (Gemini/Claude) — runs hourly in GitHub Actions
docs/       ARCHITECTURE.md, DEPLOYMENT.md
.github/    scrape.yml — the scheduled scrape job
```

## Run locally

**Prerequisites:** Node 20.9+, Python 3.12+, a Neon project (a `dev` branch keeps local work
away from production data).

### 0. One `.env` for everything

```powershell
copy .env.example .env      # then fill in DATABASE_URL and NEXTAUTH_SECRET
```

Both the scraper and the dashboard read this single file at the repo root.

### 1. Scraper (fills the database)

```powershell
python -m venv venv
venv\Scripts\activate      # macOS/Linux: source venv/bin/activate
pip install -r scraper\requirements.txt
cd scraper
python jobs.py init-db                               # tables, view, users
python jobs.py migrate-sqlite ..\data\mci_rwanda.db  # one-time: copy the old SQLite data
python jobs.py scrape                                # incremental scrape (a few minutes)
cd ..
```

Other jobs: `python jobs.py --help` (`verify`, `summarize`, `reclassify`, `reprocess`,
`scrape --historical`). AI jobs need `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY`) in `.env`; `python jobs.py eval-ai` tests the AI gate.

### 2. Dashboard

```powershell
cd frontend
npm install
npm run dev                  # http://localhost:3000 → /signup to create an account
```

### 3. Quality checks (what CI should run)

```bash
cd frontend
npm run type-check && npm run lint && npm run build
npx react-doctor@latest .
```

## Deploy

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): Neon database → GitHub secrets → Vercel project.
