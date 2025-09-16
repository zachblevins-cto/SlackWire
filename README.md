# AI News Slack Bot

A Slack bot that monitors RSS feeds from top AI research labs and news sources, automatically posting updates to your Slack channel when new articles are published.

## Features

- 📰 Monitors RSS feeds from major AI labs (OpenAI, DeepMind, Google AI, Meta AI, Microsoft Research, Anthropic)
- 🗞️ Tracks reputable AI news sources (MIT Tech Review, The Verge, VentureBeat, etc.)
- 🔍 Filters content by AI-related keywords
- 🚀 Real-time updates as articles are published
- 📦 Batched posting to avoid rate limits
- 💾 Persistent cache to avoid duplicate posts
- 🔧 Configurable check intervals

## Prerequisites

- Python 3.8+
- A Slack workspace where you can create apps
- Admin permissions to install apps in your Slack workspace

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ai-news-slack-bot
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up your Slack app (see [SLACK_APP_SETUP.md](SLACK_APP_SETUP.md) for detailed instructions)

5. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your Slack tokens and channel ID
   ```

## Configuration

### Environment Variables

- `SLACK_BOT_TOKEN`: Your bot's OAuth token (xoxb-...)
- `SLACK_APP_TOKEN`: Your app-level token for Socket Mode (xapp-...)
- `SLACK_CHANNEL_ID`: The channel ID where the bot will post (C...)
- `CHECK_INTERVAL_MINUTES`: How often to check feeds (default: 30)
- `DEBUG`: Enable debug logging (default: False)

### RSS Feeds

Edit `feeds_config.py` to add or remove RSS feeds:

```python
RSS_FEEDS = [
    {
        "name": "Feed Name",
        "url": "https://example.com/rss",
        "category": "Category"
    },
    # Add more feeds...
]
```

### Keywords

Modify `AI_KEYWORDS` in `feeds_config.py` to customize content filtering.

## Usage

1. Start the bot:
   ```bash
   python main.py
   ```

2. The bot will:
   - Connect to Slack via Socket Mode
   - Post a startup message
   - Check RSS feeds immediately
   - Continue checking at the configured interval

3. Interact with the bot:
   - Mention the bot: `@AI News Bot`
   - Use slash command: `/ai-news-status`

## Features in Detail

### RSS Parsing
- Supports multiple date formats
- Extracts title, link, summary, and publication date
- Removes HTML from summaries
- Generates unique IDs to prevent duplicates

### Slack Integration
- Uses Socket Mode for easy deployment (no public URL needed)
- Formats articles with rich Slack blocks
- Includes source, category, and publication date
- Batches posts to respect rate limits

### Caching
- Maintains a persistent cache of seen articles
- Survives bot restarts
- Prevents duplicate posts

## Monitoring

The bot logs to both console and `ai_news_bot.log` file. Monitor logs for:
- Feed parsing errors
- New articles found
- Slack posting status
- Rate limit warnings

## Troubleshooting

### Bot not posting
1. Check logs for errors
2. Verify Slack tokens in `.env`
3. Ensure bot is invited to the channel
4. Check internet connectivity

### Missing articles
1. Verify RSS feed URLs are correct
2. Check if articles match keyword filters
3. Look for parsing errors in logs

### Rate limiting
1. Increase `CHECK_INTERVAL_MINUTES`
2. Reduce batch size in `slack_bot.py`

## Contributing

1. Add new RSS feeds to `feeds_config.py`
2. Improve keyword filtering
3. Add new Slack commands
4. Enhance article formatting

## License

MIT License