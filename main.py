import os
import json
import hashlib
import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import quote

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

MIN_SCORE = int(os.getenv("MIN_SCORE", "50"))

SEEN_FILE = "seen.json"

KEYWORDS = [
    "prop firm giveaway",
    "prop firm free challenge",
    "funded account giveaway",
    "free funded account",
    "free prop firm challenge",
    "prop firm contest",
    "trading account giveaway",
    "funded trader giveaway",
]

POSITIVE_WORDS = [
    "giveaway",
    "free challenge",
    "free account",
    "funded account",
    "contest",
    "raffle",
    "promo",
    "win",
]

NEGATIVE_WORDS = [
    "review",
    "comparison",
    "coupon",
    "discount",
    "affiliate",
    "how to",
]


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-2000:], f, indent=2)


def make_id(title, link):
    raw = f"{title}|{link}"
    return hashlib.sha256(raw.encode()).hexdigest()


def score_item(title, summary):
    text = f"{title} {summary}".lower()

    score = 0

    for word in POSITIVE_WORDS:
        if word in text:
            score += 20

    for word in NEGATIVE_WORDS:
        if word in text:
            score -= 15

    if "prop firm" in text:
        score += 20

    if "funded" in text:
        score += 15

    if "$" in text:
        score += 10

    return score


def clean_text(text):
    soup = BeautifulSoup(text or "", "html.parser")
    return soup.get_text(" ", strip=True)


def google_news_feed(query):
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:
        response = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        response.raise_for_status()
        return feedparser.parse(response.content)
    except Exception as e:
        print(f"Feed error: {e}")
        return None


def send_telegram(message):
    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    response.raise_for_status()


def main():
    seen = load_seen()
    found = []

    for query in KEYWORDS:
        print(f"Searching: {query}")

        feed = google_news_feed(query)

        if not feed:
            continue

        for item in feed.entries:
            title = clean_text(item.get("title", ""))
            summary = clean_text(item.get("summary", ""))
            link = item.get("link", "")

            if not title or not link:
                continue

            item_id = make_id(title, link)

            if item_id in seen:
                continue

            score = score_item(title, summary)

            print(f"{score} | {title}")

            if score >= MIN_SCORE:
                found.append({
                    "id": item_id,
                    "title": title,
                    "summary": summary[:500],
                    "link": link,
                    "score": score,
                })

    # Remove duplicates found across multiple searches
    unique = {}

    for item in found:
        unique[item["id"]] = item

    found = list(unique.values())

    print(f"New alerts: {len(found)}")

    for item in found:
        message = (
            "🚨 PROP-FIRM GIVEAWAY FOUND\n\n"
            f"🏢 {item['title']}\n\n"
            f"⭐ Score: {item['score']}\n\n"
            f"📝 {item['summary']}\n\n"
            f"🔗 {item['link']}"
        )

        try:
            send_telegram(message)
            print("Telegram alert sent")

            seen.add(item["id"])

        except Exception as e:
            print(f"Telegram error: {e}")

    save_seen(seen)


if __name__ == "__main__":
    main()
