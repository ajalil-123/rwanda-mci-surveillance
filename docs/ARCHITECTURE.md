# Architecture

```
 GitHub Actions (hourly cron)            Neon Postgres                 Vercel
 ┌──────────────────────────┐   write   ┌──────────────────┐   read   ┌──────────────────────────┐
 │ scraper/jobs.py scrape   │ ────────► │ incidents        │ ◄─────── │ Next.js 16               │
 │  RSS, Google News,       │           │ scrape_log       │          │  /api/data/[resource]    │
 │  ReliefWeb, AllAfrica…   │           │ scrape_cursor    │          │  (session-checked)       │
 │  → NLP → AI check        │           │ verified_incidents│         │  dashboard pages (SWR)   │
 └──────────────────────────┘           └──────────────────┘          │  email + password sign-in │
                                                                       └──────────────────────────┘
```

There is no always-on server. Nothing sleeps, so there are no cold starts.

## scraper/ (Python, GitHub Actions)

| File | Role |
|---|---|
| `jobs.py` | CLI entry point for every task (scrape, verify, summarize, reclassify, reprocess, migrate) |
| `scraper.py` | Source fetchers; `should_store()` gate (blocked sources → casualties → Claude check) |
| `nlp.py` | Rwanda geo-tagging, casualty extraction, incident classification |
| `source_registry.py` | 3-tier source credibility + blocked-source list |
| `ai.py` | AI checks (Gemini or Claude, same prompts/schemas): Rwanda scope gate + type, summaries |
| `eval_ai.py` | Labelled test set for the scope gate — `python jobs.py eval-ai` |
| `database.py` | Postgres access; exact + semantic dedup on insert |
| `schema.sql` | Tables, indexes, `verified_incidents` view — applied idempotently each run |
| `reprocess_db.py` | Re-run the latest NLP over every stored record |
| `migrate_sqlite.py` | One-time import of the old SQLite database |

Data flow per article: `is_blocked_source` → Rwanda / civilian-MCI filters → `enrich()` (NLP)
→ `should_store()` (needs casualties; the AI gate verifies when an AI key is set — failures stay unverified)
→ semantic + exact dedup → insert.

## frontend/ (Next.js, Vercel)

- `src/server/queries.ts` — all analytics SQL (server-only). Reads `verified_incidents`,
  which hides rows Claude rejected and derives `occurred_at` (event date, else detection date).
- `src/app/api/data/[resource]/route.ts` — one handler; checks the NextAuth session, returns JSON.
- `src/lib/api.ts` — client fetchers used by the SWR hooks (60 s refresh).
- `src/proxy.ts` — redirects unauthenticated visitors from `/dashboard/*` to `/login`.

## Security

- `DATABASE_URL`, `NEXTAUTH_SECRET` and the AI keys are server-side only (never `NEXT_PUBLIC_*`).
- Every data route checks the session; passwords are scrypt-hashed; 5 failed logins lock an account for 15 minutes.
- Security headers on every route (no framing, nosniff, strict referrer).
- CSV export neutralises spreadsheet formulas in scraped text.
