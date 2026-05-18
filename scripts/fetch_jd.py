import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime

TELEGRAM_TOKEN  = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KEYWORDS = ["devops", "network", "cloud", "aws", "linux", "sysadmin", "infrastructure"]

def fetch_itviec_jobs(keyword, max_jobs=3):
    url = f"https://itviec.com/it-jobs/{keyword}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        jobs = []
        cards = soup.select("div.job-card")[:max_jobs]

        for card in cards:
            title_tag    = card.select_one("h3.job-card__title a")
            company_tag  = card.select_one("div.job-card__employer a")
            location_tag = card.select_one("div.job-card__location")
            salary_tag   = card.select_one("div.job-card__salary")

            if not title_tag:
                continue

            jobs.append({
                "title":    title_tag.text.strip(),
                "company":  company_tag.text.strip()  if company_tag  else "N/A",
                "location": location_tag.text.strip() if location_tag else "N/A",
                "salary":   salary_tag.text.strip()   if salary_tag   else "Thoả thuận",
                "link":     "https://itviec.com" + title_tag.get("href", ""),
            })

        return jobs

    except Exception as e:
        print(f"Lỗi fetch {keyword}: {e}")
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
    message = f"☀️ <b>JD DevOps sáng nay — {today}</b>\n{'─'*30}\n\n"

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
                f"🔗 <a href='{job['link']}'>Xem JD</a>\n\n"
            )
        total += len(jobs)

    if total == 0:
        message += "Không tìm thấy job nào hôm nay 😴"

    message += f"<i>Bot tự động chạy lúc 8h sáng 🤖</i>"
    send_telegram(message)


if __name__ == "__main__":
    main()