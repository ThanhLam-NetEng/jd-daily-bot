import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KEYWORDS = ["devops", "network", "cloud", "aws", "linux", "sysadmin", "infrastructure"]

def fetch_itviec_jobs(keyword, max_jobs=3):
    url = f"https://itviec.com/it-jobs/{keyword}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        res = requests.get(url, headers=headers, timeout=15)
        print(f"[{keyword}] Status code: {res.status_code}")

        soup = BeautifulSoup(res.text, "html.parser")

        # Debug: in ra các class đang có để xác định đúng selector
        all_divs = soup.find_all("div", class_=True)
        classes = set()
        for d in all_divs[:80]:
            for c in d.get("class", []):
                if "job" in c.lower():
                    classes.add(c)
        print(f"[{keyword}] Job-related classes found: {classes}")

        jobs = []

        # Thử nhiều selector phổ biến của ITviec
        cards = (
            soup.select("div.job-card")
            or soup.select("div[data-job-id]")
            or soup.select("article.job")
            or soup.select("div.job_content")
            or soup.select("div.job-listing")
            or soup.select("div[class*='JobCard']")
            or soup.select("div[class*='job-item']")
        )

        print(f"[{keyword}] Cards found: {len(cards)}")
        if cards:
            print(f"[{keyword}] First card HTML:\n{cards[0].prettify()[:2000]}")
        

        for card in cards[:max_jobs]:
            # Tìm title linh hoạt
            title_tag = (
                card.select_one("h3 a")
                or card.select_one("h2 a")
                or card.select_one("a[class*='title']")
                or card.select_one("a[class*='job']")
            )
            company_tag  = card.select_one("a[class*='company']") or card.select_one("span[class*='company']")
            location_tag = card.select_one("span[class*='location']") or card.select_one("div[class*='location']")
            salary_tag   = card.select_one("span[class*='salary']") or card.select_one("div[class*='salary']")

            if not title_tag:
                continue

            href = title_tag.get("href", "")
            link = href if href.startswith("http") else "https://itviec.com" + href

            jobs.append({
                "title":    title_tag.text.strip(),
                "company":  company_tag.text.strip()  if company_tag  else "N/A",
                "location": location_tag.text.strip() if location_tag else "N/A",
                "salary":   salary_tag.text.strip()   if salary_tag   else "Thoả thuận",
                "link":     link,
            })

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
                f"🔗 <a href='{job['link']}'>Xem JD</a>\n\n"
            )
        total += len(jobs)

    if total == 0:
        message += "⚠️ Không scrape được job — có thể ITviec đã thay đổi HTML.\n"
        message += "Kiểm tra log trong GitHub Actions để debug."

    message += f"\n<i>🤖 Bot tự động chạy lúc 8h sáng</i>"
    send_telegram(message)


if __name__ == "__main__":
    main()
