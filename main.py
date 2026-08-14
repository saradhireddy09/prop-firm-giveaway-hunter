import os
import json
import hashlib
import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import quote

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SEEN_FILE = "seen.json"

PROP_FIRMS = [
    "FXIFY",
    "The5ers",
    "E8 Markets",
    "FundingPips",
    "FundedNext",
    "Funded Trading Plus",
    "Hola Prime",
    "Funded Trading Markets",
    "Funded Firm",
    "FTUK",
    "Topstep",
    "Apex Trader Funding",
    "Tradeify",
    "MyFundedFX",
]

SEARCHES = [
    '"prop firm" giveaway',
    '"funded account" giveaway',
    '"free challenge" prop firm',
    '"free funded account" trading',
    '"prop firm" contest',
    '"trading account" giveaway',
    '"funded trader" giveaway',
]

POSITIVE = [
    "giveaway",
    "contest",
    "sweepstakes",
    "free challenge",
    "free account",
    "free funded account",
    "win a funded account",
    "win a challenge",
    "funded account",
    "prize",
]

ENTRY_WORDS = [
    "enter",
    "entry",
    "join",
    "register",
    "sign up",
    "follow",
    "retweet",
    "deadline",
    "ends",
]

NOISE = [
    "nasdaq trading",
    "live trading",
    "day trading",
    "scalping",
    "trading stream",
    "youtube",
    "webinar",
    "expo",
    "conference",
    "biden",
    "wall street",
    "stock market news",
    "market analysis",
    "technical analysis",
]


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-3000:], f)


def clean(text):
    return BeautifulSoup(text or "", "html.parser").get_text(
        " ", strip=True
    )


def item_id(title, link):
    return hashlib.sha256(
        f"{title}|{link}".encode()
    ).hexdigest()


def identify_prop_firm(text):
    for firm in PROP_FIRMS:
        if firm.lower() in text.lower():
            return firm
    return None


def score(title, summary):
    text = f"{title} {summary}".lower()

    firm = identify_prop_firm(text)

    positive_hits = sum(
        1 for word in POSITIVE if word in text
    )

    entry_hits = sum(
        1 for word in ENTRY_WORDS if word in text
    )

    noise_hits = sum(
        1 for word in NOISE if word in text
    )

    score = 0

    if firm:
        score += 40

    score += min(positive_hits * 15, 45)
    score += min(entry_hits * 5, 15)

    if "$" in text:
        score += 10

    if "funded account" in text:
        score += 20

    if "free challenge" in text:
        score += 20

    score -= noise_hits * 25

    return max(score, 0), firm


def google_news(query):
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:
        r = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as e:
        print("Feed error:", e)
        return None


def send_telegram(message):
    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    r = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    r.raise_for_status()


def main():

    seen = load_seen()
    alerts = {}

    for query in SEARCHES:

        print(f"Searching: {query}")

        feed = google_news(query)

        if not feed:
            continue

        for entry in feed.entries:

            title = clean(entry.get("title", ""))
            summary = clean(entry.get("summary", ""))
            link = entry.get("link", "")

            if not title or not link:
                continue

            text = f"{title} {summary}"

            uid = item_id(title, link)

            if uid in seen:
                continue

            result_score, firm = score(title, summary)

            print(
                f"{result_score:3} | "
                f"{firm or 'Unknown'} | "
                f"{title}"
            )

            # Strict qualification
            if firm and result_score >= 60:

                alerts[uid] = {
                    "title": title,
                    "summary": summary[:700],
                    "link": link,
                    "firm": firm,
                    "score": result_score,
                }

    print(f"\nQualified alerts: {len(alerts)}")

    for uid, alert in alerts.items():

        message = (
            "🚨 NEW PROP-FIRM GIVEAWAY\n\n"
            f"🏢 Prop Firm: {alert['firm']}\n\n"
            f"🎁 {alert['title']}\n\n"
            f"⭐ Confidence Score: {alert['score']}\n\n"
            f"📝 {alert['summary']}\n\n"
            f"🔗 {alert['link']}"
        )

        try:

            send_telegram(message)

            print(
                f"Telegram alert sent: "
                f"{alert['firm']}"
            )

            seen.add(uid)

        except Exception as e:
            print("Telegram error:", e)

    save_seen(seen)


if __name__ == "__main__":
    main()
