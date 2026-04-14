"""
Job Alert Scraper
Scrapes YC Work at a Startup + Welcome to the Jungle for matching roles
Sends Telegram alerts for new matches
"""

import os
import json
import hashlib
import smtplib
import requests
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

# --- Config ---
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
ALERT_RECIPIENT = os.environ.get("ALERT_RECIPIENT", "") or SMTP_EMAIL
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


# --- Email ---
def send_email(subject: str, body: str):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print("Email not configured, printing instead:")
        print(subject)
        print(body)
        return

    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = SMTP_EMAIL
    msg["To"] = ALERT_RECIPIENT

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SMTP_EMAIL, SMTP_PASSWORD)
        smtp.send_message(msg)
    print(f"Email sent to {ALERT_RECIPIENT}")


def format_job_message(jobs: list[dict]) -> tuple[str, str]:
    subject = f"🔍 {len(jobs)} new job match{'es' if len(jobs) > 1 else ''}"
    rows = ""
    for job in jobs:
        source_emoji = "🚀" if job["source"] == "YC" else "🌴"
        rows += f"""
        <tr>
            <td style="padding:8px 0">{source_emoji} <strong>{job['title']}</strong><br>
            <span style="color:#666">{job['company']}</span><br>
            <a href="{job['url']}">{job['source']} →</a></td>
        </tr>"""

    body = f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:auto">
        <h2>🔍 {len(jobs)} new job match{'es' if len(jobs) > 1 else ''}</h2>
        <table width="100%">{rows}</table>
        <p style="color:#999;font-size:12px">Checked {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</p>
    </body></html>"""

    return subject, body


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
        subject, body = format_job_message(new_jobs)
        send_email(subject, body)
    else:
        print("No new matches, nothing sent")

    save_seen_jobs(seen)


if __name__ == "__main__":
    main()
