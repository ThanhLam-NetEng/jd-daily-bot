import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Bỏ sysadmin vì 404, thêm system-engineer
KEYWORDS = ["devops", "network", "cloud", "aws", "linux", "infrastructure", "system-engineer"]

def fetch_itviec_jobs(keyword, max_jobs=3):
    url = f"https://itviec.com/it-jobs/{keyword}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        if res.status_code != 200:
            print(f"[{keyword}] Skipped — status {res.status_code}")
            return []

        cards = soup.select("div.job-card")
        print(f"[{keyword}] Cards found: {len(cards)}")

        jobs = []
        seen_slugs = set()

        for card in cards:
            # Title + Link
            title_tag = card.select_one("h3[data-search--job-selection-target='jobTitle']")
            if not title_tag:
                continue

            title = title_tag.text.strip()
            link  = title_tag.get("data-url", "")
            if not link.startswith("http"):
                link = "https://itviec.com" + link

            # Dedup theo slug
            slug = card.get("data-search--job-selection-job-slug-value", title)
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            # Company
            company_tag = card.select_one("a.logo-employer-card")
            company = company_tag.get("title", "N/A").strip() if company_tag else "N/A"

            # Location
            location_tag = card.select_one("svg[class*='location'] ~ span") \
                        or card.select_one("span[class*='location']") \
                        or card.select_one("div[class*='location']")
            location = location_tag.text.strip() if location_tag else "Vietnam"

            # Salary
            salary_tag = card.select_one("span[class*='salary']") \
                      or card.select_one("div[class*='salary']") \
                      or card.select_one("span[class*='sign-in-view-salary']")
            salary = salary_tag.text.strip() if salary_tag else "Thoả thuận"

            # Posted time
            posted_tag = card.select_one("span.small-text.text-dark-grey")
            posted = posted_tag.text.strip().replace("\n", " ") if posted_tag else ""

            jobs.append({
                "title":   title,
                "company": company,
                "location": location,
                "salary":  salary,
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
    today   = datetime.now().strftime("%d/%m/%Y")
    message = f"☀️ <b>JD sáng nay — {today}</b>\n{'─'*30}\n\n"

    total = 0
    for kw in KEYWORDS:
        jobs = fetch_itviec_jobs(kw, max_jobs=3)
        if not jobs:
            continue

        message += f"🔍 <b>#{kw.upper()}</b>\n\n"
        for i, job in enumerate(jobs, 1):
            message += (
                f"<b>{i}. {job['title']}</b>\n"
                f"🏢 {job['company']}\n"
                f"📍 {job['location']}  💰 {job['salary']}\n"
                f"🕐 {job['posted']}\n"
                f"🔗 <a href='{job['link']}'>Xem JD</a>\n\n"
            )
        total += len(jobs)

    if total == 0:
        message += "⚠️ Không tìm thấy job nào hôm nay."
    else:
        message += f"📊 <i>Tổng: {total} jobs từ {len(KEYWORDS)} từ khoá</i>\n"

    message += f"<i>🤖 Bot tự động — 8h sáng mỗi ngày</i>"
    send_telegram(message)


if __name__ == "__main__":
    main()