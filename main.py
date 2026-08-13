import os, json, re
from urllib.parse import urlparse
import requests
import feedparser
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

CONFIG = json.load(open("config.json", encoding="utf-8"))
SEEN_FILE = "seen.json"
MIN_SCORE = int(os.getenv("MIN_SCORE", "70"))

FREE_TERMS = [
    "free", "100% free", "no cost", "zero cost", "free account",
    "free challenge", "free funded"
]
PROP_TERMS = [
    "prop firm", "funded account", "funded trader", "trading challenge",
    "propfirm", "funding"
]
PAYMENT_TERMS = [
    "buy", "purchase", "pay", "payment", "fee", "deposit",
    "activation fee", "challenge fee", "discount"
]
SCAM_TERMS = [
    "wallet", "seed phrase", "private key", "send crypto",
    "verification payment", "withdrawal fee"
]

def load_seen():
    try:
        return set(json.load(open(SEEN_FILE, encoding="utf-8")))
    except Exception:
        return set()

def save_seen(seen):
    # Keep state bounded.
    data = list(seen)[-3000:]
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def clean(text):
    return re.sub(r"\s+", " ", BeautifulSoup(text or "", "html.parser").get_text(" ")).strip()

def score(title, summary, link):
    text = f"{title} {summary}".lower()
    s = 0
    reasons = []

    if any(x in text for x in FREE_TERMS):
        s += 25; reasons.append("free wording")
    if any(x in text for x in PROP_TERMS):
        s += 25; reasons.append("prop/funded wording")
    if re.search(r"\$\s?(?:5|10|25|50|100)[kK]\b", text):
        s += 15; reasons.append("account size detected")
    if any(x in text for x in ["giveaway", "give away", "win a"]):
        s += 15; reasons.append("giveaway detected")
    if any(x in text for x in ["deadline", "ends", "closing", "expires"]):
        s += 5; reasons.append("deadline wording")
    if "india" in text or "worldwide" in text or "global" in text:
        s += 5; reasons.append("eligibility wording")

    # Penalize language suggesting it is not actually free.
    payment_hits = sum(1 for x in PAYMENT_TERMS if x in text)
    if payment_hits:
        s -= min(35, payment_hits * 7)
        reasons.append("possible payment requirement")

    scam_hits = sum(1 for x in SCAM_TERMS if x in text)
    if scam_hits:
        s -= 50
        reasons.append("high-risk/scam wording")

    domain = urlparse(link).netloc.lower()
    if domain:
        reasons.append(domain)

    return max(0, min(100, s)), reasons

def fetch_feed(url):
    try:
        feed = feedparser.parse(url)
        out = []
        for e in feed.entries[:30]:
            title = clean(getattr(e, "title", ""))
            summary = clean(getattr(e, "summary", ""))
            link = getattr(e, "link", "")
            if title and link:
                out.append((title, summary, link))
        return out
    except Exception as exc:
        print("Feed error:", url, exc)
        return []

def telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("\nTELEGRAM NOT CONFIGURED\n" + message)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=20)
    r.raise_for_status()

def main():
    seen = load_seen()
    new_seen = set(seen)
    alerts = []

    for feed_url in CONFIG["feeds"]:
        for title, summary, link in fetch_feed(feed_url):
            uid = link.split("#")[0]
            if uid in seen:
                continue

            text = f"{title} {summary}".lower()
            if not any(k.lower() in text for k in CONFIG["keywords"]):
                new_seen.add(uid)
                continue

            s, reasons = score(title, summary, link)
            new_seen.add(uid)

            if s >= MIN_SCORE:
                alerts.append((s, title, link, reasons))

    alerts.sort(reverse=True, key=lambda x: x[0])

    for s, title, link, reasons in alerts[:10]:
        msg = (
            f"🚨 PROP-FIRM GIVEAWAY\\n\\n"
            f"⭐ Score: {s}/100\\n"
            f"🎁 {title}\\n\\n"
            f"🔎 {', '.join(reasons[:6])}\\n\\n"
            f"🔗 {link}\\n\\n"
            f"⚠️ Verify the official firm and requirements before entering."
        )
        telegram(msg)

    save_seen(new_seen)
    print(f"Scanned feeds. New alerts: {len(alerts)}")

if __name__ == "__main__":
    main()
