# Free Prop-Firm Giveaway Hunter — V1

A free starter bot that scans configured RSS/search feeds, scores likely prop-firm giveaways,
deduplicates them, and optionally sends high-scoring alerts to Telegram.

## Free deployment
Use a public GitHub repository + GitHub Actions. Public-repo standard GitHub-hosted runners are free.

## Local test
1. Install Python 3.11+
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env`
4. Run: `python main.py`

## Telegram
Create a bot with BotFather, send it one message from your Telegram account, then obtain the
bot token and chat ID. Put them in GitHub Secrets as TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.

## Important
This V1 only discovers and alerts. It does not automatically follow, like, repost, reply,
or submit giveaway forms.
