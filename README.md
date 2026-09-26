# NHIC MCI Surveillance

Media-based surveillance of civilian **Mass Casualty Incidents (MCIs)** in Rwanda for the
**National Health Intelligence Centre (NHIC)**.

The system continuously collects news reports, identifies incidents that happened in Rwanda and
harmed people — road accidents, floods, landslides, fires, explosions, stampedes, drownings,
building collapses and disease outbreaks — and presents them on a secure dashboard for
public-health decision-making. An incident with **3 or more deaths** is classified as an MCI.

---

## How it works

```
News sources ──► Scraper (hourly, GitHub Actions) ──► Neon Postgres ──► Dashboard (Vercel)
                  • collect articles                                     • MCI classification
                  • extract location & casualties                        • analytics & trends
                  • AI check: in Rwanda? in scope?                       • map & data explorer
                  • de-duplicate & store
```

1. **Collect** — RSS feeds, Google News, ReliefWeb, AllAfrica and Rwandan news sites are scraped every hour.
2. **Extract** — NLP finds the district, casualty counts and incident type in each article.
3. **Verify** — an AI model (Gemini or Claude) confirms the event happened in Rwanda and is in scope,
   rejecting foreign events, commemorations, statistics reports, violence and similar articles.
   If the AI is unavailable, the incident is kept as *unverified* and re-checked later.
4. **Store** — duplicates of the same event from different outlets are merged; results go to Postgres.
5. **Present** — the dashboard reads the database directly; users sign in with email and password.

## Tech stack

| Part | Technology | Hosting |
|---|---|---|
| Dashboard | Next.js 16, React 19, TypeScript, Tailwind CSS, Recharts, Leaflet | Vercel |
| Scraper & AI checks | Python 3.12, BeautifulSoup, Gemini / Claude APIs | GitHub Actions (hourly) |
| Database | PostgreSQL | Neon |
| Authentication | NextAuth (email + password, JWT sessions) | — |

## Project structure

```
frontend/              Next.js dashboard
  src/app/             pages: landing, login/sign-up, dashboard views, API routes
  src/server/          database queries and auth helpers (server-only)
  src/components/      UI components and charts
scraper/               Python data pipeline
  jobs.py              command-line entry point for every task
  scraper.py           source collectors
  nlp.py               location, casualty and incident-type extraction
  ai.py                AI verification and summaries
  database.py          Postgres access and de-duplication
  schema.sql           database schema
docs/                  architecture and deployment guides
.github/workflows/     scheduled scrape job
.env.example           all configuration settings
```

---

## Run locally

### Prerequisites

- Node.js 20.9 or later
- Python 3.12 or later
- A PostgreSQL database — a free [Neon](https://neon.tech) project works well
- Optional: a [Gemini](https://aistudio.google.com/apikey) or [Anthropic](https://console.anthropic.com) API key for the AI checks

### 1. Configure

```bash
cp .env.example .env
```

Fill in `.env` (one file, used by both the scraper and the dashboard):

| Setting | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `NEXTAUTH_SECRET` | Yes | Random secret for login sessions — generate with `openssl rand -base64 32` |
| `NEXTAUTH_URL` | Yes (local) | `http://localhost:3000` |
| `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` | No | Enables AI verification and summaries |
| `AI_PROVIDER` | No | `gemini` or `claude` (defaults to whichever key is set) |
| `RESEND_API_KEY` | No | Sends password-reset emails; without it the link is printed in the server log |

### 2. Set up the scraper and database

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r scraper/requirements.txt

cd scraper
python jobs.py init-db            # creates the tables (safe to re-run)
python jobs.py scrape             # fetches the latest articles
cd ..
```

For a brand-new database, `python jobs.py scrape --historical` backfills incidents from 2010
onwards (this takes a long time).

### 3. Run the dashboard

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000/signup>, create an account, and sign in.

Use `npm run dev` rather than `npx next dev` — the npm script loads the shared `.env` file.

---

## Scraper commands

Run from `scraper/` with the virtual environment active:

| Command | Purpose |
|---|---|
| `python jobs.py scrape` | Fetch new articles |
| `python jobs.py scrape --historical` | Full backfill from 2010 |
| `python jobs.py verify [--all]` | AI-check unverified incidents (`--all` re-checks everything) |
| `python jobs.py summarize` | Generate AI summaries for incidents without one |
| `python jobs.py reclassify` | AI re-typing of incidents classified as "other" |
| `python jobs.py reprocess` | Re-run the NLP extraction on every stored incident |
| `python jobs.py eval-ai` | Test the AI checks against 16 labelled examples |
| `python jobs.py migrate-sqlite <file>` | One-time import from the earlier SQLite version |

## Development checks

```bash
cd frontend
npm run type-check
npm run lint
npm run build
```

## Deployment

The dashboard is deployed on Vercel, the scraper runs as a scheduled GitHub Actions workflow,
and both use the same Neon database. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the
step-by-step setup and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design details.
