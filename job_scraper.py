"""
Job Alert Scraper
Scrapes YC Work at a Startup + Welcome to the Jungle for matching roles
Sends Telegram alerts for new matches
"""

import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

# --- Config ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SEEN_JOBS_FILE = "seen_jobs.json"

KEYWORDS = [
    "data scientist",
    "analytics engineer",
    "data engineer",
    "machine learning",
    "ai",
    "nlp",
    "semantic layer",
    "llm",
    "bi engineer",
    "data platform",
]

EXCLUDE_KEYWORDS = [
    "senior director",
    "vp of",
    "vice president",
    "head of sales",
    "account executive",
    "marketing",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


# --- State management ---
def load_seen_jobs() -> set:
    if Path(SEEN_JOBS_FILE).exists():
        with open(SEEN_JOBS_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen_jobs(seen: set):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(list(seen), f)


def job_id(title: str, company: str) -> str:
    return hashlib.md5(f"{title.lower()}{company.lower()}".encode()).hexdigest()


# --- Matching ---
def is_match(title: str, description: str = "") -> bool:
    text = (title + " " + description).lower()
    if any(ex in text for ex in EXCLUDE_KEYWORDS):
        return False
    return any(kw in text for kw in KEYWORDS)


# --- YC Work at a Startup ---
def scrape_yc() -> list[dict]:
    """Scrape YC jobs board - data/AI roles, London or remote"""
    jobs = []
    urls = [
        "https://www.workatastartup.com/jobs?role=data&remote=true",
        "https://www.workatastartup.com/jobs?role=data&remote=false&country=GB",
        "https://www.workatastartup.com/jobs?role=eng&keyword=machine+learning&country=GB",
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            # YC renders job cards with these classes
            job_cards = soup.select("div.job-name") or soup.select("[class*='JobItem']")

            for card in job_cards:
                title_el = card.select_one("a") or card
                title = title_el.get_text(strip=True)
                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = "https://www.workatastartup.com" + link

                company_el = card.find_next("div", class_=lambda c: c and "company" in c.lower()) if card else None
                company = company_el.get_text(strip=True) if company_el else "YC Startup"

                if title and is_match(title):
                    jobs.append({
                        "title": title,
                        "company": company,
                        "url": link,
                        "source": "YC",
                    })
        except Exception as e:
            print(f"YC scrape error for {url}: {e}")

    return jobs


# --- Welcome to the Jungle ---
def scrape_wttj() -> list[dict]:
    """Scrape WTTJ for data/AI roles in London/remote"""
    jobs = []
    searches = [
        "data+scientist",
        "analytics+engineer",
        "machine+learning+engineer",
        "data+platform",
        "ai+engineer",
    ]

    for query in searches:
        url = (
            f"https://www.welcometothejungle.com/en/jobs"
            f"?query={query}&refinementList[offices.country_code][]=GB"
            f"&refinementList[contract_type_names.en][]=Full-Time"
        )
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            # WTTJ job cards
            cards = soup.select("li[data-testid='search-results-list-item-wrapper']")
            if not cards:
                # fallback selector
                cards = soup.select("article") or soup.select("[class*='JobCard']")

            for card in cards:
                title_el = card.select_one("h3, h2, [class*='title']")
                company_el = card.select_one("[class*='company'], [class*='organization']")
                link_el = card.select_one("a[href*='/jobs/']") or card.select_one("a")

                title = title_el.get_text(strip=True) if title_el else ""
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                link = link_el.get("href", "") if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://www.welcometothejungle.com" + link

                if title and is_match(title):
                    jobs.append({
                        "title": title,
                        "company": company,
                        "url": link,
                        "source": "WTTJ",
                    })

        except Exception as e:
            print(f"WTTJ scrape error for {query}: {e}")

    return jobs


# --- Telegram ---
def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured, printing instead:")
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    })


def format_job_message(jobs: list[dict]) -> str:
    lines = [f"🔍 *{len(jobs)} new job match{'es' if len(jobs) > 1 else ''}*\n"]
    for job in jobs:
        source_emoji = "🚀" if job["source"] == "YC" else "🌴"
        lines.append(
            f"{source_emoji} *{job['title']}*\n"
            f"   {job['company']}\n"
            f"   [{job['source']}]({job['url']})\n"
        )
    lines.append(f"\n_Checked at {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC_")
    return "\n".join(lines)


# --- Main ---
def main():
    seen = load_seen_jobs()
    print(f"Loaded {len(seen)} previously seen jobs")

    all_jobs = scrape_yc() + scrape_wttj()
    print(f"Found {len(all_jobs)} matching jobs total")

    new_jobs = []
    for job in all_jobs:
        jid = job_id(job["title"], job["company"])
        if jid not in seen:
            new_jobs.append(job)
            seen.add(jid)

    print(f"{len(new_jobs)} new jobs")

    if new_jobs:
        message = format_job_message(new_jobs)
        send_telegram(message)
    else:
        print("No new matches, nothing sent")

    save_seen_jobs(seen)


if __name__ == "__main__":
    main()
