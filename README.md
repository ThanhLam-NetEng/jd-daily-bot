# JD Daily Bot

[![Daily JD Fetch](https://github.com/ThanhLam-NetEng/jd-daily-bot/actions/workflows/fetch_jd.yml/badge.svg)](https://github.com/ThanhLam-NetEng/jd-daily-bot/actions/workflows/fetch_jd.yml)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/Automation-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)
![Claude](https://img.shields.io/badge/AI-Claude%20Haiku%204.5-D97757)
![Telegram](https://img.shields.io/badge/Delivery-Telegram-26A5E4?logo=telegram&logoColor=white)
![Schedule](https://img.shields.io/badge/Schedule-08%3A07%20VN%20Mon--Fri-success)

AI-assisted job matching bot for fresher-friendly IT roles in Ho Chi Minh City. The bot fetches ITviec job listings, filters noisy results, reads full JD pages, optionally scores each JD against a private CV with Claude, and sends a concise Telegram digest every weekday morning.

## Demo

![Telegram digest preview](docs/demo.PNG)

## Why This Project Matters

This project is built like a small production automation system, not a one-off script. It combines scheduled CI, web scraping, rule-based filtering, LLM-based JD/CV matching, private secret management, state persistence, and failure-aware Telegram delivery.

## Features

- Runs automatically at **08:07 Vietnam time, Monday to Friday**.
- Searches ITviec for DevOps, Network, Cloud, Linux, and Infrastructure roles.
- Filters by location, seniority, relevance, posting age, duplicate history, and experience requirements.
- Fetches full JD pages to catch requirements that are not visible in search cards.
- Uses Claude Haiku 4.5 to score JD/CV fit when `ANTHROPIC_API_KEY` and `CV_TEXT` are configured.
- Sends Telegram digest with match score, required skills, fit, gap, experience level, verdict, posted time, and JD link.
- Falls back to a rule-based digest if Claude is not configured or the API call fails.
- Updates `data/seen_jobs.json` only after Telegram delivery succeeds.

## Output

With Claude enabled, each item is formatted like this:

```text
1. Network - Hardware Engineer (Firewall, Window Server)
Company: Allexceed Viet Nam
Match: 72% [███████░░░]
Skills: Firewall Configuration, Network Engineering, Windows Server
Fit: Strong firewall and network security project experience.
Gap: No explicit Windows Server administration experience.
Level: fresher-friendly · Worth applying
Posted: 13 days ago
Link: Xem JD
```

Without Claude, the bot still sends a deterministic rule-based summary:

```text
Company: ...
Location: Ho Chi Minh
Salary: ...
Matched: NETWORK, Firewall
Posted: ...
Link: Xem JD
```

## Architecture

```mermaid
flowchart TD
    A[GitHub Actions<br/>schedule + manual dispatch] --> B[Install dependencies]
    B --> C[Run scripts/fetch_jd.py]
    C --> D[Fetch ITviec search cards]
    D --> E[Parse title, company, posted time, link]
    E --> F[Rule filters<br/>location, seniority, relevance, age]
    F --> G[Fetch full JD detail page]
    G --> H[Experience filter<br/>EN + VI patterns]
    H --> I[Deduplicate with seen_jobs.json]
    I --> J{Claude enabled?}
    J -->|Yes| K[Claude Messages API<br/>JD + CV -> JSON analysis]
    J -->|No| L[Rule-based summary]
    K --> M[Score threshold filter]
    L --> N[Telegram formatter]
    M --> N
    N --> O[Telegram Bot API]
    O --> P[Telegram chat]
    P --> Q[Persist seen_jobs.json]
    Q --> R[Commit state back to GitHub]
```

## Filtering Strategy

| Layer | Purpose |
| --- | --- |
| Keyword search | Starts from `devops`, `network`, `cloud`, `linux`, and `infrastructure`. |
| Location filter | Keeps HCM-focused listings and removes clearly non-HCM results. |
| Seniority filter | Removes senior, lead, manager, architect, staff, and similar titles. |
| Experience filter | Removes postings that clearly require more than 2 years, including English and Vietnamese patterns. |
| Relevance filter | Removes unrelated tracks such as mobile, frontend, embedded, AI/ML, blockchain, and game roles. |
| Claude threshold | When enabled, sends only jobs with `match_score >= 60`. |
| Deduplication | Skips jobs already sent in the last 7 days. |

## Repository Structure

```text
.
|-- .github/workflows/fetch_jd.yml   # Scheduled GitHub Actions workflow
|-- data/seen_jobs.json              # Lightweight state for duplicate prevention
|-- docs/demo.PNG                    # Telegram demo screenshot
|-- docs/demo-placeholder.svg        # Earlier placeholder asset
|-- scripts/fetch_jd.py              # Fetch, filter, analyze, format, and send logic
|-- requirements.txt                 # Python dependencies
|-- .gitignore                       # Local/cache file exclusions
`-- README.md                        # Project documentation
```

## Configuration

Add these repository secrets before running the workflow:

| Secret | Required | Description |
| --- | --- | --- |
| `TELEGRAM_TOKEN` | Yes | Telegram bot token from BotFather. |
| `TELEGRAM_CHAT_ID` | Yes | Telegram chat, group, or channel ID that receives the digest. |
| `ANTHROPIC_API_KEY` | No | Enables Claude-powered JD/CV matching. |
| `CV_TEXT` | No | Plain-text CV used for Claude matching. Keep this private in GitHub Secrets. |
| `CLAUDE_MODEL` | No | Optional model override. Defaults to `claude-haiku-4-5-20251001`. |

GitHub path:

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

## Schedule

GitHub Actions cron runs in UTC. Vietnam is UTC+7, so the workflow uses:

```yaml
7 1 * * 1-5
```

That maps to **08:07 Vietnam time, Monday to Friday**. The minute is intentionally not `00` to reduce the risk of top-of-hour GitHub Actions congestion.

## Local Setup

```bash
git clone https://github.com/ThanhLam-NetEng/jd-daily-bot.git
cd jd-daily-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
git clone https://github.com/ThanhLam-NetEng/jd-daily-bot.git
cd jd-daily-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run Locally

Rule-based mode:

```bash
export TELEGRAM_TOKEN="your-token"
export TELEGRAM_CHAT_ID="your-chat-id"
python scripts/fetch_jd.py
```

Claude matching mode:

```bash
export TELEGRAM_TOKEN="your-token"
export TELEGRAM_CHAT_ID="your-chat-id"
export ANTHROPIC_API_KEY="your-anthropic-key"
export CV_TEXT="your plain-text CV"
python scripts/fetch_jd.py
```

Windows PowerShell:

```powershell
$env:TELEGRAM_TOKEN="your-token"
$env:TELEGRAM_CHAT_ID="your-chat-id"
$env:ANTHROPIC_API_KEY="your-anthropic-key"
$env:CV_TEXT="your plain-text CV"
python scripts/fetch_jd.py
```

## Manual Run

Use GitHub Actions when you want to test the live workflow:

```text
Actions -> Daily JD Fetch -> Run workflow
```

## Reliability

- Telegram responses are checked. Failed sends make the workflow fail instead of silently passing.
- Telegram HTML content is escaped before sending to avoid malformed message errors.
- Telegram rate-limit responses are retried.
- Claude output is requested as raw JSON and parsed before formatting.
- Claude matching is capped per run to control API cost and latency.
- If Claude is not configured or returns an error, the bot falls back to the rule-based digest.
- `seen_jobs.json` is updated only after Telegram delivery succeeds.
- The workflow has a 20-minute timeout and concurrency control to avoid overlapping runs.

## Security And Cost

- Telegram credentials, Claude API key, and CV text are read from GitHub Actions secrets.
- CV content is not committed to the repository.
- Local `.env` files and virtual environments are ignored by Git.
- `data/seen_jobs.json` is intentionally versioned because it is workflow state, not a secret.
- Claude analysis is limited by `MAX_ANALYZE` in code to avoid accidental high API usage.

## Roadmap

- Add unit tests for experience filtering, Claude JSON parsing, and Telegram formatting.
- Add a dry-run mode that prints the digest without sending Telegram messages.
- Move tunables such as match threshold, max analysis count, and keywords to environment variables.
- Store historical match scores for trend review.
- Add structured logs for fetch, filter, Claude analysis, send, and state-update steps.
