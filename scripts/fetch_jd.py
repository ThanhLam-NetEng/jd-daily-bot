import html
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CV_TEXT = os.environ.get("CV_TEXT", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in {"1", "true", "yes", "on"}
MATCH_THRESHOLD = 60
MAX_ANALYZE = 8

KEYWORDS = ["devops", "network", "cloud", "linux", "infrastructure"]
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

SENIOR_KEYWORDS = [
    "senior", "sr.", "lead", "leader", "manager", "principal",
    "head of", "director", "architect", "vp ", "vice president",
    "staff engineer", "cto", "chief", "middle", "engineer ii",
    "engineer iii", "level 2", "level 3",
]

HCM_KEYWORDS = [
    "ho chi minh", "ho chi minh city", "hcm", "district",
    "quan ", "binh thanh", "thu duc",
    "hồ chí minh", "quận", "thủ đức",
]

NON_HCM_KEYWORDS = [
    "ha noi", "hanoi", "hà nội",
    "da nang", "đà nẵng",
]

IRRELEVANT_KEYWORDS = [
    "embedded", "autosar", "automotive", "mobile developer",
    "android", "ios", "flutter", "react native", "frontend",
    "backend developer", "java developer", "php", ".net developer",
    "data scientist", "machine learning", "ai engineer",
    "game developer", "unity", "blockchain developer",
]

SKILL_KEYWORDS = [
    "AWS", "Azure", "GCP", "Kubernetes", "Docker", "Linux", "Terraform",
    "CI/CD", "Jenkins", "GitLab", "Ansible", "Cisco", "Firewall",
    "Windows Server", "Networking", "Cloud", "DevOps", "Monitoring",
]

SEEN_JOBS_FILE = "data/seen_jobs.json"
DIGEST_RUNS_FILE = "data/digest_runs.json"
MAX_SEEN_DAYS = 7
MAX_DIGEST_RUN_DAYS = 30
TELEGRAM_MAX_CHARS = 4096
MESSAGE_SOFT_LIMIT = 3600
MAX_EXPERIENCE_YEARS = 2


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": datetime.now(VN_TZ).isoformat(),
            "level": record.levelname,
            "event": getattr(record, "event", record.getMessage()),
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    logger = logging.getLogger("jd_daily_bot")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    return logger


LOGGER = configure_logging()


def log_event(level, event, **fields):
    LOGGER.log(level, event, extra={"event": event, "fields": fields})


def now_vn():
    return datetime.now(VN_TZ)


def require_env():
    if DRY_RUN:
        return

    missing = [
        name for name, value in {
            "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
            "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required GitHub secret(s): {', '.join(missing)}")


def load_seen_jobs():
    try:
        with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{SEEN_JOBS_FILE} is not valid JSON: {exc}") from exc

    cutoff = (now_vn() - timedelta(days=MAX_SEEN_DAYS)).isoformat()
    return [j for j in data if j.get("seen_at", "") > cutoff]


def save_seen_jobs(seen_jobs):
    os.makedirs("data", exist_ok=True)
    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_jobs, f, ensure_ascii=False, indent=2)


def load_digest_runs():
    try:
        with open(DIGEST_RUNS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{DIGEST_RUNS_FILE} is not valid JSON: {exc}") from exc

    cutoff = (now_vn() - timedelta(days=MAX_DIGEST_RUN_DAYS)).date().isoformat()
    return [run for run in data if run.get("date", "") > cutoff]


def has_digest_run_today(digest_runs):
    today = now_vn().date().isoformat()
    return any(run.get("date") == today for run in digest_runs)


def save_digest_runs(digest_runs):
    os.makedirs("data", exist_ok=True)
    with open(DIGEST_RUNS_FILE, "w", encoding="utf-8") as f:
        json.dump(digest_runs, f, ensure_ascii=False, indent=2)


def mark_digest_run(digest_runs, sent_count):
    digest_runs.append({
        "date": now_vn().date().isoformat(),
        "sent_at": now_vn().isoformat(),
        "job_count": sent_count,
    })
    save_digest_runs(digest_runs)


def esc_text(value):
    return html.escape(str(value or ""), quote=False)


def esc_attr(value):
    return html.escape(str(value or ""), quote=True)


def normalize_space(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def get_card_lines(card):
    return [
        normalize_space(line)
        for line in card.get_text("\n", strip=True).splitlines()
        if normalize_space(line)
    ]


def clean_posted(value):
    return re.sub(r"^posted\s+", "", normalize_space(value), flags=re.IGNORECASE)


def extract_salary(lines):
    for line in lines:
        lower = line.lower()
        if "$" in line or "usd" in lower or "vnd" in lower or "negotiable" in lower:
            return line
    return "N/A"


def extract_location(card_text):
    lower = card_text.lower()
    work_modes = []
    if "remote" in lower:
        work_modes.append("Remote")
    if "hybrid" in lower:
        work_modes.append("Hybrid")
    if "on-site" in lower or "onsite" in lower:
        work_modes.append("On-site")

    suffix = f" ({', '.join(work_modes)})" if work_modes else ""
    return f"Ho Chi Minh{suffix}"


def extract_matches(title, keyword):
    found = [keyword.upper()]
    seen = {keyword.lower()}
    lower_text = title.lower()
    for skill in SKILL_KEYWORDS:
        skill_key = skill.lower()
        if skill_key in lower_text and skill_key not in seen:
            found.append(skill)
            seen.add(skill_key)
    return ", ".join(found[:5]) if found else "N/A"


def is_senior_job(title):
    title_lower = title.lower()
    return any(kw in title_lower for kw in SENIOR_KEYWORDS)


def is_irrelevant_job(title):
    title_lower = title.lower()
    return any(kw in title_lower for kw in IRRELEVANT_KEYWORDS)


def is_too_old(posted_text, max_days=21):
    text = posted_text.lower()
    try:
        if "hour" in text or "minute" in text or "just now" in text:
            return False
        if "day" in text:
            days = int("".join(filter(str.isdigit, text)))
            return days > max_days
    except (TypeError, ValueError):
        return False
    return False


def too_much_experience_reason(text, max_years=MAX_EXPERIENCE_YEARS):
    normalized = normalize_space(text).lower()
    word_numbers = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
    }
    for word, number in word_numbers.items():
        normalized = re.sub(rf"\b{word}\b", number, normalized)

    range_pattern = r"(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?|năm)"
    for match in re.finditer(range_pattern, normalized):
        low = int(match.group(1))
        high = int(match.group(2))
        if low > max_years or (low == high and high > max_years):
            return f"requires {low}-{high} years"
    normalized = re.sub(range_pattern, " ", normalized)

    patterns = [
        r"(\d+)\s*\+\s*(?:years?|yrs?|năm)",
        r"(?:at least|minimum|min\.?|from|over|more than)\s*(\d+)\s*(?:years?|yrs?)",
        r"(?:từ|tren|trên|hon|hơn|ít nhất|it nhat|tối thiểu|toi thieu)\s*(\d+)\s*năm",
        r"(?:experience|kinh nghiệm|kinh nghiem)[^.;:\n]{0,60}?(\d+)\s*\+?\s*(?:years?|yrs?|năm)",
        r"(\d+)\s*(?:years?|yrs?|năm)[^.;:\n]{0,40}(?:experience|kinh nghiệm|kinh nghiem)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            years = int(match.group(1))
            if years > max_years:
                return f"requires {years}+ years"

    return ""


def is_hcm_job(card):
    card_text = card.get_text(separator=" ").lower()
    if any(kw in card_text for kw in HCM_KEYWORDS):
        return True
    if any(kw in card_text for kw in NON_HCM_KEYWORDS):
        return False
    return True


def fetch_job_detail_text(link, headers):
    try:
        res = requests.get(link, headers=headers, timeout=20)
        if res.status_code != 200:
            log_event(logging.WARNING, "job_detail_skipped", status_code=res.status_code, link=link)
            return ""
        soup = BeautifulSoup(res.text, "html.parser")
        return normalize_space(soup.get_text(" ", strip=True))
    except Exception as exc:
        log_event(logging.WARNING, "job_detail_skipped", error=str(exc), link=link)
        return ""


def parse_claude_json(text):
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def analyze_with_claude(title, jd_text, cv_text):
    if not ANTHROPIC_API_KEY or not cv_text:
        return None

    prompt = f"""You are a job matching assistant. Analyze this job against the candidate CV.

JOB TITLE: {title}

JOB DESCRIPTION:
{jd_text[:3000]}

CANDIDATE CV:
{cv_text[:2000]}

Return ONLY a raw JSON object, no markdown, no explanation:
{{
  "match_score": <integer 0-100>,
  "required_skills": [<top 4 required skills from JD>],
  "nice_to_have": [<up to 2 nice-to-have skills>],
  "strength": "<one sentence: candidate strongest fit, max 15 words>",
  "gap": "<one sentence: main missing skill or 'No significant gap', max 15 words>",
  "experience_level": "<fresher-friendly / junior / mid-level>",
  "verdict": "<Worth applying / Consider applying / Skip>"
}}

Rules:
- Base ONLY on what is explicitly in the JD and CV, do not invent
- match_score: 80-100 strong fit, 60-79 decent fit, below 60 weak fit
- If the JD clearly requires more than 2 years of experience, lower the score
"""

    try:
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 400,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        if res.status_code != 200:
            log_event(
                logging.WARNING,
                "claude_api_error",
                status_code=res.status_code,
                response=res.text[:300],
            )
            return None

        content = res.json().get("content", [])
        text = content[0].get("text", "").strip() if content else ""
        if not text:
            log_event(logging.WARNING, "claude_empty_content")
            return None

        analysis = parse_claude_json(text)
        score = int(analysis.get("match_score", 0))
        analysis["match_score"] = max(0, min(100, score))
        return analysis

    except Exception as exc:
        log_event(logging.WARNING, "claude_exception", error=str(exc))
        return None


def fetch_itviec_jobs(keyword, max_jobs=8, max_cards=25):
    url = f"https://itviec.com/it-jobs/{keyword}?city_ids%5B%5D=2"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    res = requests.get(url, headers=headers, timeout=20)
    if res.status_code != 200:
        raise RuntimeError(f"ITviec returned HTTP {res.status_code} for keyword '{keyword}'")

    soup = BeautifulSoup(res.text, "html.parser")
    cards = soup.select("div.job-card")
    log_event(logging.INFO, "itviec_cards_fetched", keyword=keyword, total_cards=len(cards))

    if not cards:
        log_event(logging.WARNING, "itviec_no_cards", keyword=keyword)

    jobs = []
    for card in cards[:max_cards]:
        title_tag = card.select_one("h3[data-search--job-selection-target='jobTitle']")
        if not title_tag:
            continue

        title = title_tag.text.strip()
        link = title_tag.get("data-url", "")
        if link and not link.startswith("http"):
            link = "https://itviec.com" + link

        slug = card.get("data-search--job-selection-job-slug-value", title)
        posted_tag = card.select_one("span.small-text.text-dark-grey")
        posted = clean_posted(posted_tag.text if posted_tag else "")
        lines = get_card_lines(card)
        card_text = normalize_space(card.get_text(" ", strip=True))

        if is_senior_job(title):
            log_event(logging.INFO, "job_skipped", reason="senior", keyword=keyword, title=title)
            continue
        if is_irrelevant_job(title):
            log_event(logging.INFO, "job_skipped", reason="irrelevant", keyword=keyword, title=title)
            continue
        if is_too_old(posted):
            log_event(logging.INFO, "job_skipped", reason="old", keyword=keyword, title=title, posted=posted)
            continue
        if not is_hcm_job(card):
            log_event(logging.INFO, "job_skipped", reason="non_hcm", keyword=keyword, title=title)
            continue
        experience_reason = too_much_experience_reason(f"{title} {card_text}")
        if experience_reason:
            log_event(
                logging.INFO,
                "job_skipped",
                reason="experience",
                keyword=keyword,
                title=title,
                detail=experience_reason,
            )
            continue

        detail_text = fetch_job_detail_text(link or url, headers)
        experience_reason = too_much_experience_reason(f"{title} {card_text} {detail_text}")
        if experience_reason:
            log_event(
                logging.INFO,
                "job_skipped",
                reason="experience",
                keyword=keyword,
                title=title,
                detail=experience_reason,
            )
            continue

        company_tag = card.select_one("a.logo-employer-card")
        if company_tag:
            raw = company_tag.get("title", "N/A").strip()
            for sep in [" - ", " | ", " – ", ". ", ", "]:
                if sep in raw:
                    raw = raw.split(sep)[0].strip()
                    break
            if len(raw) > 40 or (raw and raw[0].islower()):
                href = company_tag.get("href", "")
                if "/companies/" in href:
                    slug_co = href.split("/companies/")[1].split("?")[0]
                    raw = slug_co.replace("-", " ").title()
            company = raw
        else:
            company = "N/A"

        jobs.append({
            "title": title,
            "company": company,
            "slug": slug,
            "posted": posted,
            "salary": extract_salary(lines),
            "location": extract_location(card_text),
            "matches": extract_matches(title, keyword),
            "detail_text": detail_text,
            "link": link or url,
        })

        if len(jobs) >= max_jobs:
            break

    return jobs


def send_telegram(message):
    if len(message) > TELEGRAM_MAX_CHARS:
        raise RuntimeError(f"Telegram message too long: {len(message)} characters")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    for attempt in range(3):
        res = requests.post(url, json=payload, timeout=20)
        log_event(
            logging.INFO,
            "telegram_response",
            status_code=res.status_code,
            response=res.text[:500],
            attempt=attempt + 1,
        )

        if res.status_code == 429 and attempt < 2:
            retry_after = 5
            try:
                retry_after = int(res.json().get("parameters", {}).get("retry_after", retry_after))
            except ValueError:
                log_event(logging.WARNING, "telegram_retry_after_invalid", fallback_seconds=retry_after)
            time.sleep(retry_after)
            continue

        if res.status_code >= 400:
            raise RuntimeError(f"Telegram send failed: HTTP {res.status_code} - {res.text[:500]}")

        data = res.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram send failed: {data}")
        return

    raise RuntimeError("Telegram send failed after retries")


def split_messages(header, sections, footer):
    messages = []
    current = header

    for section in sections:
        if len(current) + len(section) + len(footer) > MESSAGE_SOFT_LIMIT and current != header:
            messages.append(current + footer)
            current = header
        current += section

    messages.append(current + footer)
    return messages


def format_rule_job(job, index):
    return (
        f"<b>{index}. {esc_text(job['title'])}</b>\n"
        f"Company: {esc_text(job['company'])}\n"
        f"Location: {esc_text(job['location'])}\n"
        f"Salary: {esc_text(job['salary'])}\n"
        f"Matched: {esc_text(job['matches'])}\n"
        f"Posted: {esc_text(job['posted'])}\n"
        f"Link: <a href=\"{esc_attr(job['link'])}\">Xem JD</a>\n\n"
    )


def format_ai_job(job, analysis, index):
    score = analysis.get("match_score", 0)
    filled = round(score / 10)
    bar = "█" * filled + "░" * (10 - filled)
    skills = ", ".join(analysis.get("required_skills", [])) or "N/A"
    level = analysis.get("experience_level", "")
    verdict = analysis.get("verdict", "")
    return (
        f"<b>{index}. {esc_text(job['title'])}</b>\n"
        f"Company: {esc_text(job['company'])}\n"
        f"Match: {score}% [{bar}]\n"
        f"Skills: {esc_text(skills)}\n"
        f"Fit: {esc_text(analysis.get('strength', ''))}\n"
        f"Gap: {esc_text(analysis.get('gap', ''))}\n"
        f"Level: {esc_text(level)} · {esc_text(verdict)}\n"
        f"Posted: {esc_text(job['posted'])}\n"
        f"Link: <a href=\"{esc_attr(job['link'])}\">Xem JD</a>\n\n"
    )


def main():
    require_env()

    today = now_vn().strftime("%d/%m/%Y")
    digest_runs = load_digest_runs()
    if not DRY_RUN and has_digest_run_today(digest_runs):
        log_event(logging.INFO, "digest_already_sent")
        return

    seen_jobs = load_seen_jobs()
    seen_slugs = {j["slug"] for j in seen_jobs if "slug" in j}

    log_event(
        logging.INFO,
        "run_started",
        seen_slugs=len(seen_slugs),
        dry_run=DRY_RUN,
        keywords=KEYWORDS,
    )

    header = f"<b>JD HCM - {today}</b>\n{'─' * 30}\n\n"
    footer = "<i>Daily JD Fetch · 08:07 · T2-T6</i>"
    sections = []
    fetch_errors = []
    total = 0
    session_slugs = set()
    new_seen = []
    analyze_count = 0
    use_ai = bool(ANTHROPIC_API_KEY and CV_TEXT)
    log_event(logging.INFO, "ai_analysis_configured", enabled=use_ai, model=CLAUDE_MODEL if use_ai else None)

    for kw in KEYWORDS:
        try:
            jobs = fetch_itviec_jobs(kw, max_jobs=8, max_cards=25)
        except Exception as exc:
            log_event(logging.ERROR, "keyword_fetch_error", keyword=kw, error=str(exc))
            fetch_errors.append(f"#{kw.upper()}: {esc_text(exc)}")
            continue

        unique_jobs = []
        for job in jobs:
            slug = job["slug"]
            if slug in seen_slugs or slug in session_slugs:
                log_event(logging.INFO, "job_skipped", reason="already_seen", keyword=kw, title=job["title"])
                continue
            session_slugs.add(slug)
            unique_jobs.append(job)
            if len(unique_jobs) >= 3:
                break

        if not unique_jobs:
            continue

        section = f"<b>{esc_text(kw.upper())}</b>\n\n"
        sent_count = 0
        for job in unique_jobs:
            analysis = None
            if use_ai and analyze_count < MAX_ANALYZE:
                log_event(logging.INFO, "ai_analysis_started", keyword=kw, title=job["title"])
                analysis = analyze_with_claude(
                    job["title"],
                    job.get("detail_text", ""),
                    CV_TEXT,
                )
                analyze_count += 1
                if analysis:
                    score = analysis.get("match_score", 0)
                    verdict = analysis.get("verdict", "")
                    log_event(
                        logging.INFO,
                        "ai_analysis_completed",
                        keyword=kw,
                        title=job["title"],
                        score=score,
                        verdict=verdict,
                    )
                    if score < MATCH_THRESHOLD:
                        log_event(
                            logging.INFO,
                            "job_skipped",
                            reason="below_ai_threshold",
                            keyword=kw,
                            title=job["title"],
                            score=score,
                            threshold=MATCH_THRESHOLD,
                        )
                        continue

            sent_count += 1
            if analysis:
                score = analysis.get("match_score", 0)
                filled = round(score / 10)
                bar = "█" * filled + "░" * (10 - filled)
                skills = ", ".join(analysis.get("required_skills", [])) or "N/A"
                level = analysis.get("experience_level", "")
                verdict = analysis.get("verdict", "")
                section += (
                    f"<b>{sent_count}. {esc_text(job['title'])}</b>\n"
                    f"Company: {esc_text(job['company'])}\n"
                    f"Match: {score}% [{bar}]\n"
                    f"Skills: {esc_text(skills)}\n"
                    f"Fit: {esc_text(analysis.get('strength', ''))}\n"
                    f"Gap: {esc_text(analysis.get('gap', ''))}\n"
                    f"Level: {esc_text(level)} · {esc_text(verdict)}\n"
                    f"Posted: {esc_text(job['posted'])}\n"
                    f"Link: <a href=\"{esc_attr(job['link'])}\">Xem JD</a>\n\n"
                )
            else:
                section += (
                    f"<b>{sent_count}. {esc_text(job['title'])}</b>\n"
                    f"Company: {esc_text(job['company'])}\n"
                    f"Location: {esc_text(job['location'])}\n"
                    f"Salary: {esc_text(job['salary'])}\n"
                    f"Matched: {esc_text(job['matches'])}\n"
                    f"Posted: {esc_text(job['posted'])}\n"
                    f"Link: <a href=\"{esc_attr(job['link'])}\">Xem JD</a>\n\n"
                )
            new_seen.append({
                "slug": job["slug"],
                "title": job["title"],
                "seen_at": now_vn().isoformat(),
            })

        if sent_count:
            sections.append(section)
            total += sent_count

    if total == 0:
        sections.append("Không có JD mới phù hợp hôm nay.\n\n")
    else:
        sections.append(f"<i>Total: {total} JD mới · HCM · Fresher-friendly</i>\n")

    if fetch_errors:
        sections.append(
            "\n<b>Cần kiểm tra nguồn fetch</b>\n"
            + "\n".join(fetch_errors)
            + "\n\n"
        )

    messages = split_messages(header, sections, footer)

    if DRY_RUN:
        log_event(logging.INFO, "dry_run_completed", messages=len(messages), total_jobs=total)
        for index, message in enumerate(messages, 1):
            print(f"\n--- DRY RUN MESSAGE {index} ---\n{message}")
        return

    for message in messages:
        send_telegram(message)

    all_seen = seen_jobs + new_seen
    save_seen_jobs(all_seen)
    mark_digest_run(digest_runs, total)
    log_event(logging.INFO, "run_completed", total_jobs=total, total_seen_jobs=len(all_seen))

    if fetch_errors and total == 0:
        raise RuntimeError("All fetched job results were empty or failed. Check ITviec responses above.")


if __name__ == "__main__":
    main()
