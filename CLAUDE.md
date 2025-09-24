# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SlackWire is a Slack bot that aggregates AI news from multiple RSS feeds and posts them to a designated Slack channel. It monitors RSS feeds from major AI labs and news sources, filters content by AI-related keywords, and prevents duplicate posts using a persistent cache.

## Common Development Commands

### Running the Bot
```bash
# Start the bot
python main.py

# Run with debug logging
DEBUG=true python main.py
```

### Testing
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
```

### Code Quality
```bash
# Lint code
make lint

# Format code
make format

# Clean generated files
make clean
```

### Dependency Management
```bash
# Install production dependencies
make install

# Install development dependencies
make install-dev

# Update all dependencies
make update-deps

# Compile requirements files from .in files
make compile-deps
```

### Environment Setup
```bash
# Set up environment (creates .env from template)
./setup.sh

# Install dependencies
pip install -r requirements.txt
```

### Service Management
```bash
# Install as systemd service
./install_service.sh

# Monitor bot logs
./monitor_bot.sh

# Uninstall systemd service
./uninstall_service.sh
```

## Architecture Overview

The application follows a modular architecture with these key components:

### Core Components

1. **main.py**: Orchestrates the bot lifecycle
   - Initializes components with environment configuration
   - Runs async feed checking on a schedule (default: 30 minutes)
   - Manages the async event loop for concurrent operations
   - Handles graceful shutdown with signal handlers
   - Implements single instance locking

2. **rss_parser.py**: Handles RSS feed processing with async/await
   - Fetches all feeds concurrently using aiohttp
   - Parses feeds from config.yaml with retry logic
   - Filters articles by AI keywords
   - Maintains feed_cache.json to prevent duplicates
   - Returns sorted, deduplicated article lists
   - Implements connection pooling and rate limiting

3. **slack_bot.py**: Manages Slack integration
   - Uses Socket Mode (no public URL required)
   - Formats messages with rich Slack blocks
   - Handles slash commands and bot mentions
   - Implements rate limiting protection
   - Manages interactive buttons (feedback system)

### Supporting Components

4. **config_manager.py**: Dynamic configuration management
   - Hot-reload configuration from config.yaml
   - Add/remove feeds via Slack commands
   - Backup configuration before changes
   - Thread-safe configuration updates

5. **feedback_manager.py**: Article feedback system
   - Tracks user reactions (👍/👎)
   - Calculates trending sources
   - Prioritizes articles by feedback scores
   - Persistent feedback storage

6. **llm_summarizer.py**: AI-powered summaries
   - Multiple backend support (Ollama, Transformer, FLAN-T5, LlamaCPP)
   - Category-specific prompts
   - Async processing with fallback handling

7. **circuit_breaker.py**: Fault tolerance
   - Prevents cascading failures
   - Automatic recovery after failures
   - Configurable failure thresholds

8. **logger_config.py**: Structured logging
   - JSON format in production
   - Human-readable in development
   - Contextual logging with extra fields
   - Error logs saved to errors.log

### Utility Modules

- **utils/single_instance.py**: Prevents multiple bot instances
- **utils/file_lock.py**: Thread-safe file operations
- **utils/cache_manager.py**: Efficient cache management with expiry

## Key Configuration Points

### config.yaml
Central configuration file containing:
- RSS feeds with categories (academic, company, news)
- AI keywords for filtering
- LLM prompts by category
- Circuit breaker settings
- Retry configurations

### .env
Runtime settings:
- SLACK_BOT_TOKEN: OAuth token (xoxb-...)
- SLACK_APP_TOKEN: Socket Mode token (xapp-...)
- SLACK_CHANNEL_ID: Target channel (C0123456789)
- CHECK_INTERVAL_MINUTES: Feed check frequency
- LLM_BACKEND: AI backend selection
- LLM_MODEL: Model name
- ENABLE_LLM_SUMMARIES: Toggle AI summaries

### Feed Management

When adding new RSS feeds:
1. Add the feed URL to config.yaml under rss_feeds
2. Specify a category (academic, company, news) for better prompts
3. No code changes needed - feeds are dynamically loaded

### Slack Commands

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

## Testing Strategy

The project uses pytest with comprehensive test coverage:

### Test Files
- **test_rss_parser.py**: RSS parsing, caching, async operations
- **test_config_manager.py**: Configuration CRUD operations
- **test_feedback_manager.py**: Feedback tracking and scoring
- **test_circuit_breaker.py**: Fault tolerance mechanisms

### Test Fixtures
- Mock RSS feeds and responses
- Mock Slack API responses
- Temporary file systems for cache testing
- Async test support with pytest-asyncio

## Performance Optimizations

- Async RSS fetching with connection pooling (5-10x faster)
- Efficient cache with automatic expiry (7 days default)
- Batched Slack posting to avoid rate limits
- Circuit breaker prevents API cascading failures
- Thread-safe file operations with atomic writes

## Error Handling

- Retry mechanism with exponential backoff for failed feeds
- Graceful degradation when LLM service unavailable
- Detailed HTTP status code handling (404, 503, timeouts)
- Structured logging for debugging
- Automatic recovery from transient failures

## Digest Feature

Daily/weekly digest configuration stored in digest_config.json:
- Articles prioritized by feedback scores
- Includes trending sources report
- Scheduled at 09:00 UTC (configurable)
- Enable with `/ai-news-digest daily` or `/ai-news-digest weekly`