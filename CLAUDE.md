# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SlackWire is a Slack bot that aggregates AI news from multiple RSS feeds and posts them to a designated Slack channel. It monitors 11 RSS feeds from major AI labs and news sources, filters content by AI-related keywords, and prevents duplicate posts using a persistent cache.

## Common Development Commands

### Running the Bot
```bash
# Start the bot
python main.py

# Run with debug logging
DEBUG=true python main.py
```

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment (creates .env from template)
./setup.sh
```

### Testing and Development
```bash
# No formal test suite exists yet
# Test RSS parsing independently
python -c "from rss_parser import RSSParser; p = RSSParser(); print(p.parse_feed('https://example.com/feed.xml'))"

# Test Slack connection
python -c "from slack_bot import AINewsSlackBot; bot = AINewsSlackBot(); bot.post_message('Test message')"
```

## Architecture Overview

The application follows a modular architecture with three main components:

1. **main.py**: Orchestrates the bot lifecycle
   - Initializes components with environment configuration
   - Runs feed checking on a schedule (default: 30 minutes)
   - Manages the main event loop

2. **rss_parser.py**: Handles RSS feed processing
   - Fetches and parses feeds defined in feeds_config.py
   - Filters articles by AI keywords
   - Maintains feed_cache.json to prevent duplicates
   - Returns sorted, deduplicated article lists

3. **slack_bot.py**: Manages Slack integration
   - Uses Socket Mode (no public URL required)
   - Formats messages with rich Slack blocks
   - Handles slash commands and bot mentions
   - Implements rate limiting protection

## Key Configuration Points

- **feeds_config.py**: Add/modify RSS feeds and AI keywords here
- **.env**: Contains Slack credentials and runtime settings
  - SLACK_BOT_TOKEN: OAuth token (xoxb-...)
  - SLACK_APP_TOKEN: Socket Mode token (xapp-...)
  - SLACK_CHANNEL_ID: Target channel (C0123456789)
  - CHECK_INTERVAL_MINUTES: Feed check frequency

## Important Implementation Details

- The bot uses Slack Socket Mode, eliminating the need for public webhooks
- Feed cache persists across restarts in feed_cache.json
- Articles are batched to avoid Slack rate limits
- The bot runs Slack handling in a separate thread from the scheduler
- All dates are parsed with python-dateutil for timezone handling
- BeautifulSoup cleans HTML in article descriptions

## Common Modifications

When adding new RSS feeds:
1. Add the feed URL to RSS_FEEDS in feeds_config.py
2. Optionally add new AI keywords to AI_KEYWORDS
3. No code changes needed - feeds are dynamically loaded

When changing Slack formatting:
1. Modify format_article_block() in slack_bot.py:124
2. Use Slack Block Kit Builder to design new layouts

When adjusting scheduling:
1. Change CHECK_INTERVAL_MINUTES in .env
2. Or modify the schedule logic in main.py:64