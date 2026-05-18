import requests
from bs4 import BeautifulSoup
import os
import json
from datetime import datetime, timedelta

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KEYWORDS = ["devops", "network", "cloud", "linux", "infrastructure"]

# Từ khoá loại bỏ job quá cao cho fresher
SENIOR_KEYWORDS = [
    "senior", "sr.", "lead", "leader", "manager", "principal",
    "head of", "director", "architect", "vp ", "vice president",
    "staff engineer", "cto", "chief", "middle", "engineer ii",
    "engineer iii", "level 2", "level 3"
]

# Từ khoá địa điểm HCM hợp lệ
HCM_KEYWORDS = [
    "ho chi minh", "hồ chí minh", "hcm", "district",
    "quan ", "quận", "binh thanh", "thu duc", "thu đức"
]

IRRELEVANT_KEYWORDS = [
    "embedded", "autosar", "automotive", "mobile developer",
    "android", "ios", "flutter", "react native", "frontend",
    "backend developer", "java developer", "php", ".net developer",
    "data scientist", "machine learning", "ai engineer",
    "game developer", "unity", "blockchain developer"
]

SEEN_JOBS_FILE = "data/seen_jobs.json"
MAX_SEEN_DAYS  = 7  # Chỉ nhớ job trong 7 ngày


def load_seen_jobs():
    try:
        with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Xoá job cũ hơn 7 ngày
        cutoff = (datetime.now() - timedelta(days=MAX_SEEN_DAYS)).isoformat()
        data   = [j for j in data if j.get("seen_at", "") > cutoff]
        return data
    except Exception:
        return []


def save_seen_jobs(seen_jobs):
    os.makedirs("data", exist_ok=True)
    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_jobs, f, ensure_ascii=False, indent=2)


def is_senior_job(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in SENIOR_KEYWORDS)

def is_irrelevant_job(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in IRRELEVANT_KEYWORDS)

def is_too_old(posted_text: str, max_days: int = 21) -> bool:
    """Loại job đăng quá lâu — mặc định 21 ngày."""
    text = posted_text.lower()
    try:
        if "hour" in text or "minute" in text or "just now" in text:
            return False
        if "day" in text:
            days = int(''.join(filter(str.isdigit, text)))
            return days > max_days
    except Exception:
        pass
    return False

def is_hcm_job(card) -> bool:
    """Kiểm tra job có ở HCM không — qua text trong card."""
    card_text = card.get_text(separator=" ").lower()
    # Nếu tìm thấy từ khoá HCM → OK
    if any(kw in card_text for kw in HCM_KEYWORDS):
        return True
    # Nếu không có địa điểm rõ ràng → include (để không bỏ sót)
    if "ha noi" in card_text or "hà nội" in card_text or "hanoi" in card_text:
        return False
    if "da nang" in card_text or "đà nẵng" in card_text:
        return False
    return True  # Không rõ địa điểm → giữ lại


def fetch_itviec_jobs(keyword, max_jobs=5):
    # Thêm filter HCM vào URL luôn
    url = f"https://itviec.com/it-jobs/{keyword}?city_ids%5B%5D=2"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"[{keyword}] Skipped — status {res.status_code}")
            return []

        soup  = BeautifulSoup(res.text, "html.parser")
        cards = soup.select("div.job-card")
        print(f"[{keyword}] Total cards: {len(cards)}")

        jobs = []
        for card in cards:
            title_tag = card.select_one("h3[data-search--job-selection-target='jobTitle']")
            if not title_tag:
                continue

            title = title_tag.text.strip()
            link  = title_tag.get("data-url", "")
            if not link.startswith("http"):
                link = "https://itviec.com" + link

            slug = card.get("data-search--job-selection-job-slug-value", title)

            # Filter 1: Loại senior/lead
            if is_senior_job(title):
                print(f"  ⛔ Skip senior: {title}")
                continue

            # Filter 2: Loại job không liên quan
            if is_irrelevant_job(title):
                print(f"  ⛔ Skip irrelevant: {title}")
                continue

            # Filter 3: Loại job quá cũ (> 21 ngày)
            if is_too_old(posted):
                print(f"  ⛔ Skip old job: {title} ({posted})")
                continue

            # Filter : Chỉ lấy HCM
            if not is_hcm_job(card):
                print(f"  ⛔ Skip non-HCM: {title}")
                continue

            # Company
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

            # Posted time
            posted_tag = card.select_one("span.small-text.text-dark-grey")
            posted = posted_tag.text.strip().replace("\n", " ") if posted_tag else ""

            jobs.append({
                "title":   title,
                "company": company,
                "slug":    slug,
                "posted":  posted,
                "link":    link,
            })

            if len(jobs) >= max_jobs:
                break

        return jobs

    except Exception as e:
        print(f"[{keyword}] Lỗi: {e}")
        return []


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    res = requests.post(url, json=payload, timeout=10)
    print("Telegram response:", res.status_code)


def main():
    today      = datetime.now().strftime("%d/%m/%Y")
    seen_jobs  = load_seen_jobs()
    seen_slugs = {j["slug"] for j in seen_jobs}

    print(f"Loaded {len(seen_slugs)} seen slugs from history")

    message = f"☀️ <b>JD HCM sáng nay — {today}</b>\n{'─'*30}\n\n"

    total          = 0
    session_slugs  = set()  # dedup trong session này
    new_seen       = []     # job mới để lưu lại

    for kw in KEYWORDS:
        jobs = fetch_itviec_jobs(kw, max_jobs=5)

        unique_jobs = []
        for job in jobs:
            slug = job["slug"]
            # Bỏ qua nếu đã gửi tuần này hoặc trùng trong session
            if slug in seen_slugs or slug in session_slugs:
                print(f"  ⏭ Already seen: {job['title']}")
                continue
            session_slugs.add(slug)
            unique_jobs.append(job)
            if len(unique_jobs) >= 3:
                break

        if not unique_jobs:
            continue

        message += f"🔍 <b>#{kw.upper()}</b>\n\n"
        for i, job in enumerate(unique_jobs, 1):
            message += (
                f"<b>{i}. {job['title']}</b>\n"
                f"🏢 {job['company']}\n"
                f"🕐 {job['posted']}\n"
                f"🔗 <a href='{job['link']}'>Xem JD</a>\n\n"
            )
            new_seen.append({
                "slug":    job["slug"],
                "title":   job["title"],
                "seen_at": datetime.now().isoformat(),
            })
        total += len(unique_jobs)

    if total == 0:
        message += "✅ Không có job mới hôm nay — tất cả đã gửi rồi!"
    else:
        message += f"📊 <i>Tổng: {total} jobs mới · HCM only · Fresher-friendly</i>\n"

    message += f"<i>🤖 Bot tự động — 8h sáng T2-T6</i>"

    send_telegram(message)

    # Lưu lại danh sách đã gửi
    all_seen = seen_jobs + new_seen
    save_seen_jobs(all_seen)
    print(f"Saved {len(all_seen)} total seen jobs")


if __name__ == "__main__":
    main()