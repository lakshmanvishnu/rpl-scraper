# Daily RPL scraper — automation setup

The scraper (`rugby_data_scraping/rugby_match_scrap.py`) does a **full refresh** on every
run: it re-reads the fixtures, re-scrapes all completed matches, overwrites the CSVs, and
(if credentials are present) overwrites the Google Sheet tabs. Scheduling it daily is all
that's needed to keep everything current — there's no incremental/append logic to maintain.

The GitHub Actions workflow `.github/workflows/daily.yml` runs it once a day in the cloud.

## What you do once (the parts only you can do)

### 1. Put this project in a GitHub repo
From the project root:
```bash
git init
git add .
git commit -m "Initial commit"
# create an empty repo on github.com, then:
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### 2. Create a Google service account (the "robot" that writes the Sheet)
1. Go to https://console.cloud.google.com/ → create (or pick) a project.
2. **APIs & Services → Library →** enable **Google Sheets API**.
3. **APIs & Services → Credentials → Create credentials → Service account.** Name it
   anything (e.g. `rpl-updater`). Skip the optional role steps → Done.
4. Open the new service account → **Keys → Add key → Create new key → JSON.** A `.json`
   file downloads. This is the credentials file — keep it private.

### 3. Share your Google Sheet with the service account
- Open the JSON key; copy the `client_email` (looks like
  `rpl-updater@your-project.iam.gserviceaccount.com`).
- In your Google Sheet → **Share** → paste that email → give it **Editor** → Send.
- The sheet must contain the four tabs (exact names):
  `matches_men`, `player_stats_men`, `matches_women`, `player_stats_women`.
  (They'll be created automatically if missing, but matching your existing tabs means
  your preliminary data is refreshed in place.)

### 4. Add two GitHub repo secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret:**
- `GOOGLE_SHEET_ID` — the long ID from the sheet URL
  (`https://docs.google.com/spreadsheets/d/`**`THIS_PART`**`/edit`)
- `GOOGLE_CREDENTIALS` — paste the **entire contents** of the downloaded JSON key file

### 5. Done
- The job runs daily on the schedule in `daily.yml`.
- To test immediately: repo → **Actions → Daily RPL scrape → Run workflow**.

## Turning it off when the league ends
The league runs only a short window, so the workflow is set to **self-expire**: the
`STOP_AFTER` date in `.github/workflows/daily.yml` (currently `20260630`) makes the job
no-op after the league finishes. Edit that date if the schedule changes.

To stop it completely (optional): repo → **Actions → Daily RPL scrape → ⋯ → Disable
workflow**, or just delete `.github/workflows/daily.yml`. (GitHub also auto-disables
scheduled workflows after 60 days of no repo activity.)

## Running locally
Without the env vars set, the Sheets step is skipped and you just get refreshed CSVs:
```bash
cd rugby_data_scraping
python3 rugby_match_scrap.py
```
To also push to Sheets locally, set `GOOGLE_SHEET_ID` and `GOOGLE_CREDENTIALS`
(the latter as the JSON string) in your environment first.
