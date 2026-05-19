import html
import json
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

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

SEEN_JOBS_FILE = "data/seen_jobs.json"
MAX_SEEN_DAYS = 7
TELEGRAM_MAX_CHARS = 4096
MESSAGE_SOFT_LIMIT = 3600


def now_vn():
    return datetime.now(VN_TZ)


def require_env():
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


def esc_text(value):
    return html.escape(str(value or ""), quote=False)


def esc_attr(value):
    return html.escape(str(value or ""), quote=True)


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
    except Exception:
        pass
    return False


def is_hcm_job(card):
    card_text = card.get_text(separator=" ").lower()
    if any(kw in card_text for kw in HCM_KEYWORDS):
        return True
    if any(kw in card_text for kw in NON_HCM_KEYWORDS):
        return False
    return True


def fetch_itviec_jobs(keyword, max_jobs=5):
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
    print(f"[{keyword}] Total cards: {len(cards)}")

    if not cards:
        print(f"[{keyword}] No job cards found. ITviec markup may have changed.")

    jobs = []
    for card in cards:
        title_tag = card.select_one("h3[data-search--job-selection-target='jobTitle']")
        if not title_tag:
            continue

        title = title_tag.text.strip()
        link = title_tag.get("data-url", "")
        if link and not link.startswith("http"):
            link = "https://itviec.com" + link

        slug = card.get("data-search--job-selection-job-slug-value", title)
        posted_tag = card.select_one("span.small-text.text-dark-grey")
        posted = posted_tag.text.strip().replace("\n", " ") if posted_tag else ""

        if is_senior_job(title):
            print(f"  Skip senior: {title}")
            continue
        if is_irrelevant_job(title):
            print(f"  Skip irrelevant: {title}")
            continue
        if is_too_old(posted):
            print(f"  Skip old job: {title} ({posted})")
            continue
        if not is_hcm_job(card):
            print(f"  Skip non-HCM: {title}")
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
        print("Telegram response:", res.status_code, res.text[:500])

        if res.status_code == 429 and attempt < 2:
            retry_after = 5
            try:
                retry_after = int(res.json().get("parameters", {}).get("retry_after", retry_after))
            except ValueError:
                pass
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


def main():
    require_env()

    today = now_vn().strftime("%d/%m/%Y")
    seen_jobs = load_seen_jobs()
    seen_slugs = {j["slug"] for j in seen_jobs if "slug" in j}

    print(f"Loaded {len(seen_slugs)} seen slugs from history")

    header = f"☀️ <b>JD HCM sáng nay - {today}</b>\n{'─' * 30}\n\n"
    footer = "<i>🤖 Bot tự động - 08:07 sáng T2-T6</i>"
    sections = []
    fetch_errors = []
    total = 0
    session_slugs = set()
    new_seen = []

    for kw in KEYWORDS:
        try:
            jobs = fetch_itviec_jobs(kw, max_jobs=5)
        except Exception as exc:
            print(f"[{kw}] Fetch error: {exc}")
            fetch_errors.append(f"#{kw.upper()}: {esc_text(exc)}")
            continue

        unique_jobs = []
        for job in jobs:
            slug = job["slug"]
            if slug in seen_slugs or slug in session_slugs:
                print(f"  Already seen: {job['title']}")
                continue
            session_slugs.add(slug)
            unique_jobs.append(job)
            if len(unique_jobs) >= 3:
                break

        if not unique_jobs:
            continue

        section = f"🔍 <b>#{esc_text(kw.upper())}</b>\n\n"
        for i, job in enumerate(unique_jobs, 1):
            section += (
                f"<b>{i}. {esc_text(job['title'])}</b>\n"
                f"🏢 {esc_text(job['company'])}\n"
                f"🕐 {esc_text(job['posted'])}\n"
                f"🔗 <a href=\"{esc_attr(job['link'])}\">Xem JD</a>\n\n"
            )
            new_seen.append({
                "slug": job["slug"],
                "title": job["title"],
                "seen_at": now_vn().isoformat(),
            })
        sections.append(section)
        total += len(unique_jobs)

    if total == 0:
        sections.append("✅ Không có job mới hôm nay - tất cả đã gửi rồi!\n\n")
    else:
        sections.append(f"📊 <i>Tổng: {total} jobs mới · HCM only · Fresher-friendly</i>\n")

    if fetch_errors:
        sections.append(
            "\n⚠️ <b>Lỗi fetch cần kiểm tra</b>\n"
            + "\n".join(fetch_errors)
            + "\n\n"
        )

    for message in split_messages(header, sections, footer):
        send_telegram(message)

    all_seen = seen_jobs + new_seen
    save_seen_jobs(all_seen)
    print(f"Saved {len(all_seen)} total seen jobs")

    if fetch_errors and total == 0:
        raise RuntimeError("All fetched job results were empty or failed. Check ITviec responses above.")


if __name__ == "__main__":
    main()
