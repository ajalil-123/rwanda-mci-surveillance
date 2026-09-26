# Deployment

Three pieces, all free tier: **Neon** (database), **GitHub Actions** (scraper), **Vercel** (dashboard).

## 1. Neon

1. Create a project at [console.neon.tech](https://console.neon.tech) (region closest to users).
2. Create a `dev` branch for local work; keep `production` for the live app.
3. From **Connect**, copy the production connection string (pooled is fine — the scraper
   disables prepared statements so it works through the pooler).
4. Load the schema and existing data once, from your machine:
   ```bash
   cd scraper
   # repo-root .env → DATABASE_URL=<production string>
   python jobs.py init-db
   python jobs.py migrate-sqlite ../data/mci_rwanda.db
   ```

## 2. GitHub Actions (scraper)

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `DATABASE_URL` | Neon production string |
| `ANTHROPIC_API_KEY` | optional — enables Claude verification |

The workflow `.github/workflows/scrape.yml` runs hourly once it is on the default branch.
Run it by hand from **Actions → Scrape incidents → Run workflow** (tick *historical* only for
a first-time backfill of an empty database).

## 3. Vercel (dashboard)

1. **Add New → Project**, import the repo, set **Root Directory** to `frontend`.
2. Environment variables (Production + Preview):

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | Neon production string (same as above) |
   | `NEXTAUTH_SECRET` | `openssl rand -base64 32` (signs the login JWT) |
   | `NEXTAUTH_URL` | `https://<your-app>.vercel.app` |
   | `RESEND_API_KEY` / `EMAIL_FROM` | password-reset emails (resend.com) |

3. Deploy. Vercel redeploys on every push to the production branch.

## 4. Accounts

Users register at `/signup` with email + password (stored as scrypt hashes in the
Neon `users` table). Forgotten passwords are reset through a single-use emailed link
(30 minutes).

## Retiring Render

After the Vercel site shows data and one scheduled scrape has succeeded, suspend or delete
the Render service. Its disk holds the old SQLite file; download it first if you have not
already migrated that copy.
