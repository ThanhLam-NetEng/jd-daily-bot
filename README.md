# JD Daily Bot

Daily JD Fetch is a small GitHub Actions bot that fetches fresher-friendly HCM jobs from ITviec and sends a Telegram digest every weekday morning.

## What It Does

- Searches ITviec with these keywords: `devops`, `network`, `cloud`, `linux`, `infrastructure`.
- Keeps HCM jobs and filters out senior-heavy or unrelated roles.
- Sends a Telegram message with title, company, posted time, and JD link.
- Stores sent job slugs in `data/seen_jobs.json` to avoid repeating the same JD within 7 days.

## Schedule

The workflow runs at **08:07 Vietnam time, Monday to Friday**.

GitHub Actions cron uses UTC, so the schedule is:

```yaml
7 1 * * 1-5
```

## Required GitHub Secrets

Add these secrets in GitHub:

- `TELEGRAM_TOKEN`: Telegram bot token from BotFather.
- `TELEGRAM_CHAT_ID`: Chat ID where the digest should be sent.

Path:

```text
GitHub repo -> Settings -> Secrets and variables -> Actions -> New repository secret
```

## Run Locally

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Set environment variables:

```bash
export TELEGRAM_TOKEN="your-token"
export TELEGRAM_CHAT_ID="your-chat-id"
python scripts/fetch_jd.py
```

On Windows PowerShell:

```powershell
$env:TELEGRAM_TOKEN="your-token"
$env:TELEGRAM_CHAT_ID="your-chat-id"
python scripts/fetch_jd.py
```

## Manual Run

You can also trigger it from GitHub:

```text
Actions -> Daily JD Fetch -> Run workflow
```

## Notes

- `data/seen_jobs.json` is intentionally committed because the scheduled workflow uses it as lightweight state.
- If Telegram rejects a message or ITviec returns unexpected errors, the workflow fails visibly instead of silently marking jobs as seen.
