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

### Slack Commands (Phase 2)
```bash
# Feed Management
/ai-news-add-feed <url> <name> [category]     # Add new RSS feed
/ai-news-remove-feed <name>                   # Remove RSS feed
/ai-news-list-feeds                           # List all feeds

# Keyword Management  
/ai-news-add-keyword <keyword>                # Add AI keyword
/ai-news-remove-keyword <keyword>             # Remove keyword
/ai-news-list-keywords                        # List all keywords

# Other Commands
/ai-news-latest                               # Get latest articles
/ai-news-status                               # Check bot status
/ai-news-digest <daily|weekly|off>           # Configure digest notifications
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
# Run unit tests
./run_tests.sh
# or
make test

# Run all tests including integration
./run_tests.sh all
# or
make test-all

# Run tests with coverage report
pytest tests/ -v --cov=. --cov-report=html

# Run specific test file
pytest tests/test_config_manager.py -v

# Run tests matching pattern
pytest tests/ -k "feedback" -v

# Lint code
make lint

# Format code
make format
```

## Architecture Overview

The application follows a modular architecture with three main components:

1. **main.py**: Orchestrates the bot lifecycle
   - Initializes components with environment configuration
   - Runs async feed checking on a schedule (default: 30 minutes)
   - Manages the async event loop for concurrent operations

2. **rss_parser.py**: Handles RSS feed processing with async/await
   - Fetches all feeds concurrently using aiohttp
   - Parses feeds from config.yaml with retry logic
   - Filters articles by AI keywords
   - Maintains feed_cache.json to prevent duplicates
   - Returns sorted, deduplicated article lists

3. **slack_bot.py**: Manages Slack integration
   - Uses Socket Mode (no public URL required)
   - Formats messages with rich Slack blocks
   - Handles slash commands and bot mentions
   - Implements rate limiting protection

## Key Configuration Points

- **config.yaml**: Central configuration file for feeds, keywords, and behavior settings
  - RSS feeds with categories (academic, company, news)
  - AI keywords for filtering
  - LLM prompts by category
  - Circuit breaker settings
  - Retry configurations
- **.env**: Contains Slack credentials and runtime settings
  - SLACK_BOT_TOKEN: OAuth token (xoxb-...)
  - SLACK_APP_TOKEN: Socket Mode token (xapp-...)
  - SLACK_CHANNEL_ID: Target channel (C0123456789)
  - CHECK_INTERVAL_MINUTES: Feed check frequency
- **feeds_config.py**: (Legacy) Now replaced by config.yaml

## Important Implementation Details

- The bot uses Slack Socket Mode, eliminating the need for public webhooks
- Feed cache persists across restarts in feed_cache.json
- Articles are batched to avoid Slack rate limits
- The bot runs Slack handling in a separate thread from the scheduler
- All dates are parsed with python-dateutil for timezone handling
- BeautifulSoup cleans HTML in article descriptions

## Common Modifications

When adding new RSS feeds:
1. Add the feed URL to config.yaml under rss_feeds
2. Specify a category (academic, company, news) for better prompts
3. No code changes needed - feeds are dynamically loaded

When changing Slack formatting:
1. Modify format_article_block() in slack_bot.py:124
2. Use Slack Block Kit Builder to design new layouts

When adjusting scheduling:
1. Change CHECK_INTERVAL_MINUTES in .env
2. Or modify the async schedule logic in main.py

When customizing LLM prompts:
1. Edit llm_prompts section in config.yaml
2. Add category-specific prompts for better summaries

## Performance & Reliability Improvements

### Async Operations (Phase 1 Complete)
- All RSS feeds are now fetched in parallel
- Connection pooling prevents overwhelming servers
- 5-10x faster feed checking vs sequential fetching

### Error Handling & Resilience
- Retry mechanism with exponential backoff for failed feeds
- Circuit breaker pattern prevents LLM API cascading failures
- Detailed HTTP status code handling (404, 503, timeouts)

### Configuration Management
- All settings now in config.yaml (no code changes needed)
- Hot-reload not implemented - restart bot after config changes

## Phase 2 Features (Complete)

### Interactive Feed Management
- Add/remove RSS feeds directly from Slack
- List all configured feeds with categories
- Configuration changes persist to config.yaml
- Automatic config backup before changes

### Keyword Management
- Add/remove AI keywords from Slack
- List all active keywords
- Keywords used for filtering articles

### Article Feedback System
- 👍 Interesting / 👎 Not Relevant buttons on each article
- Feedback data tracked per user and source
- Used to prioritize future articles
- Trending sources based on community feedback

### Digest Feature
- Daily/weekly digest of top articles  
- Articles prioritized by feedback scores
- Includes trending sources report
- Scheduled at 09:00 UTC (configurable in digest_config.json)
- Enable with `/ai-news-digest daily` or `/ai-news-digest weekly`

## Phase 3 Features (Complete)

### Testing Framework
- Comprehensive pytest test suite
- Unit tests for all major components
- Test fixtures for mocking external dependencies
- Coverage reporting with HTML output
- Run tests with `./run_tests.sh` or `make test`

### Dependency Management
- pip-tools for deterministic builds
- Separate requirements.in for source dependencies
- requirements-dev.in for development tools
- Makefile for common tasks:
  - `make install` - Install production deps
  - `make install-dev` - Install dev deps
  - `make update-deps` - Update all dependencies
  - `make test` - Run tests

### Structured JSON Logging
- JSON-formatted logs in production
- Human-readable format in development
- Contextual logging with extra fields
- Error logs saved to errors.log
- Environment-aware configuration
- Use LOG_LEVEL env var to control verbosity