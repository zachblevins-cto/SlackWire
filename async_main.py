"""
Async Main Module for SlackWire
Fully async architecture without threading
"""

import os
import asyncio
import signal
import sys
from datetime import datetime, timezone, time, timedelta
from dotenv import load_dotenv
import json
from typing import List, Dict, Optional, Any

from rss_parser import AsyncRSSParser
from models_v2 import Article, SlackConfig, DigestSchedule
from async_slack_bot_fixed import AsyncSlackBot
from llm_summarizer import create_summarizer
from logger_config import setup_logging, get_logger
from utils.single_instance import SingleInstance
from utils.cache_manager import CacheManager
from database.manager import DatabaseManager

# Load environment variables
load_dotenv()

# Configure structured logging
setup_logging()
logger = get_logger(__name__)


class AsyncAINewsBot:
    """Fully async AI News Bot without threading"""

    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.cache_manager = CacheManager(max_entries=5000, expiry_days=7)
        self.db_manager = DatabaseManager()  # Initialize database manager

        # Load Slack configuration with validation
        self.slack_config = SlackConfig(
            bot_token=os.getenv('SLACK_BOT_TOKEN', ''),
            app_token=os.getenv('SLACK_APP_TOKEN', ''),
            channel_id=os.getenv('SLACK_CHANNEL_ID', '')
        )

        # Other configuration
        self.check_interval = int(os.getenv('CHECK_INTERVAL_MINUTES', 30))

        # LLM configuration
        self.llm_backend = os.getenv('LLM_BACKEND', 'ollama')
        self.llm_model = os.getenv('LLM_MODEL', 'llama3.2')
        self.llm_base_url = os.getenv('LLM_BASE_URL', 'http://localhost:11434')
        self.enable_summaries = os.getenv('ENABLE_LLM_SUMMARIES', 'true').lower() == 'true'

        # Initialize components
        self.rss_parser = AsyncRSSParser()
        self.slack_bot = AsyncSlackBot(self.slack_config, db_manager=self.db_manager)

        # Set up slash command callback
        self.slack_bot.get_latest_callback = self.handle_latest_articles_request

        # Get feeds and keywords from config
        self.rss_feeds = self.rss_parser.get_feeds_from_config()
        self.ai_keywords = self.rss_parser.get_keywords_from_config()

        # Initialize LLM summarizer if enabled
        self.summarizer = None
        if self.enable_summaries:
            try:
                if self.llm_backend in ['transformer', 'flan-t5']:
                    self.summarizer = create_summarizer(
                        backend=self.llm_backend,
                        model_name=self.llm_model
                    )
                else:
                    self.summarizer = create_summarizer(
                        backend=self.llm_backend,
                        base_url=self.llm_base_url,
                        model=self.llm_model if self.llm_backend == 'ollama' else None
                    )
                logger.info(f"LLM summarizer initialized with {self.llm_backend}")
            except Exception as e:
                logger.warning(f"Could not initialize LLM summarizer: {e}")
                self.summarizer = None

        # Set up callbacks
        self.slack_bot.get_latest_callback = self.handle_latest_articles_request
        self.slack_bot.reload_config_callback = self.reload_configuration
        self.slack_bot.set_digest_callback = self.set_digest_schedule

        # Digest feature settings
        self.digest_config = self._load_digest_config()
        self.digest_task: Optional[asyncio.Task] = None

        logger.info_with_context(
            "Async AI News Bot initialized",
            feeds_count=len(self.rss_feeds),
            keywords_count=len(self.ai_keywords),
            llm_backend=self.llm_backend,
            summaries_enabled=self.enable_summaries
        )

    def _load_digest_config(self) -> Dict[str, Any]:
        """Load digest configuration from file"""
        digest_file = "digest_config.json"
        if os.path.exists(digest_file):
            try:
                with open(digest_file, 'r') as f:
                    data = json.load(f)
                    return data
            except Exception as e:
                logger.error(f"Error loading digest config: {e}")
        return {'enabled': False, 'schedule': None, 'time': '09:00'}

    def _save_digest_config(self):
        """Save digest configuration to file"""
        try:
            with open("digest_config.json", 'w') as f:
                json.dump(self.digest_config, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving digest config: {e}")

    async def set_digest_schedule(self, schedule: str):
        """Update digest schedule"""
        if schedule == 'off':
            self.digest_config['enabled'] = False
            self.digest_config['schedule'] = None
            if self.digest_task:
                self.digest_task.cancel()
                self.digest_task = None
        else:
            self.digest_config['enabled'] = True
            self.digest_config['schedule'] = schedule
            # Restart digest task
            if self.digest_task:
                self.digest_task.cancel()
            self.digest_task = asyncio.create_task(self._run_digest_scheduler())

        self._save_digest_config()
        logger.info(f"Digest schedule updated: {schedule}")

    async def reload_configuration(self):
        """Reload configuration from file"""
        logger.info("Reloading configuration...")
        try:
            # Reload feeds and keywords
            self.rss_feeds = self.rss_parser.get_feeds_from_config()
            self.ai_keywords = self.rss_parser.get_keywords_from_config()
            logger.info_with_context(
                "Configuration reloaded",
                feeds_count=len(self.rss_feeds),
                keywords_count=len(self.ai_keywords)
            )
        except Exception as e:
            logger.error_with_context(
                "Error reloading configuration",
                error=str(e),
                error_type=type(e).__name__
            )

    def _get_diverse_articles(self, articles: List[Article], max_articles: int) -> List[Article]:
        """Get a diverse selection of articles across different sources"""
        # Group articles by source
        articles_by_source: Dict[str, List[Article]] = {}
        for article in articles:
            source = article.feed_name
            if source not in articles_by_source:
                articles_by_source[source] = []
            articles_by_source[source].append(article)

        # Sort each source's articles by date
        for source in articles_by_source:
            articles_by_source[source].sort(
                key=lambda x: x.published or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True
            )

        # Round-robin selection from each source
        selected = []
        source_indices = {source: 0 for source in articles_by_source}

        while len(selected) < max_articles:
            added_this_round = False
            for source in sorted(articles_by_source.keys()):  # Sort for consistent ordering
                if source_indices[source] < len(articles_by_source[source]):
                    selected.append(articles_by_source[source][source_indices[source]])
                    source_indices[source] += 1
                    added_this_round = True
                    if len(selected) >= max_articles:
                        break

            # If no articles were added this round, all sources are exhausted
            if not added_this_round:
                break

        logger.info(f"Selected {len(selected)} articles from {len(articles_by_source)} sources")
        return selected

    async def generate_summaries_batch(self, articles: List[Article]) -> None:
        """Generate summaries for articles"""
        if not self.summarizer:
            return

        logger.info(f"Generating AI summaries for {len(articles)} articles...")

        # Process summaries sequentially
        for article in articles:
            try:
                # Convert Article to dict for summarizer compatibility
                article_dict = {
                    'id': article.id,
                    'title': article.title,
                    'summary': article.summary,
                    'feed_name': article.feed_name,
                    'category': article.category
                }
                summary = self.summarizer.summarize(article_dict)
                if summary:
                    article.ai_summary = summary
            except Exception as e:
                logger.warning_with_context(
                    "Failed to summarize article",
                    article_title=article.title[:50],
                    article_id=article.id,
                    error=str(e)
                )

    async def handle_latest_articles_request(self, command: Dict):
        """Handle slash command request for latest articles"""
        try:
            channel_id = command.get("channel_id")
            user_id = command.get("user_id")
            logger.info(f"Handling /ai-news-latest command from user {user_id} in channel {channel_id}")

            # Send initial response
            logger.info(f"Sending initial response to channel {channel_id}")
            await self.slack_bot._send_response(channel_id, "🔄 Fetching latest AI articles...")
            logger.info("Initial response sent successfully")

            # Fetch latest articles WITH cache but clear cache first for fresh results
            # This is more efficient than use_cache=False which fetches ALL historical articles
            self.rss_parser.seen_entries.clear()  # Clear cache for fresh results

            all_articles = await self.rss_parser.parse_multiple_feeds_async(
                keywords=self.ai_keywords,
                use_cache=True  # Use cache to avoid duplicates within this fetch
            )

            # The RSS parser already returns Article objects, no conversion needed

            if not all_articles:
                await self.slack_bot._send_response(
                    channel_id,
                    "📭 No articles found at this time. Please try again later."
                )
                return

            # Filter articles from the last 48 hours for /ai-news-latest command
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=48)
            recent_articles = [
                article for article in all_articles
                if article.published and article.published > cutoff_time
            ]

            if not recent_articles:
                # If no articles in last 48 hours, get the 5 most recent regardless
                recent_articles = sorted(
                    all_articles,
                    key=lambda x: x.published or datetime.min.replace(tzinfo=timezone.utc),
                    reverse=True
                )[:10]  # Get top 10 most recent

            # Sort by date (newest first)
            recent_articles.sort(
                key=lambda x: x.published or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True
            )

            # Limit to top 20 articles to avoid timeouts
            recent_articles = recent_articles[:20]

            # Get top 5 diverse articles
            diverse_articles = self._get_diverse_articles(recent_articles, 5)

            # Generate summaries
            await self.generate_summaries_batch(diverse_articles)

            # Save articles to database
            for article in diverse_articles:
                await self.db_manager.save_article(article)

            # Post articles
            await self.slack_bot.post_articles(diverse_articles)

            logger.info(f"Posted {len(diverse_articles)} latest articles via slash command")

        except Exception as e:
            logger.error(f"Error handling latest articles request: {e}")
            await self.slack_bot._send_response(
                command.get("channel_id"),
                "❌ Sorry, an error occurred while fetching articles."
            )

    async def check_feeds_async(self):
        """Check all RSS feeds for new articles"""
        logger.info("Checking RSS feeds for new articles...")

        try:
            # Parse all feeds concurrently
            new_articles = await self.rss_parser.parse_multiple_feeds_async(
                keywords=self.ai_keywords,
                use_cache=True
            )

            # The RSS parser already returns Article objects, no conversion needed

            if new_articles:
                logger.info_with_context(
                    "Found new articles",
                    articles_count=len(new_articles),
                    sources=list(set(a.feed_name for a in new_articles))
                )

                # Limit articles per update
                max_articles_per_update = int(os.getenv('MAX_ARTICLES_PER_UPDATE', 10))

                # Get diverse selection across sources
                diverse_articles = self._get_diverse_articles(new_articles, max_articles_per_update)

                # Generate summaries
                await self.generate_summaries_batch(diverse_articles)

                # Save articles to database
                for article in diverse_articles:
                    await self.db_manager.save_article(article)

                # Post to Slack
                await self.slack_bot.post_articles(diverse_articles)
            else:
                logger.info("No new articles found")

        except Exception as e:
            logger.error(f"Error checking feeds: {e}")

    async def generate_digest(self, period: str = "daily"):
        """Generate a digest of top articles"""
        logger.info(f"Generating {period} digest...")

        try:
            # Fetch all articles without cache
            all_articles = await self.rss_parser.parse_multiple_feeds_async(
                keywords=self.ai_keywords,
                use_cache=False
            )

            # The RSS parser already returns Article objects, no conversion needed

            if not all_articles:
                logger.info("No articles found for digest")
                return

            # Filter articles based on period
            cutoff_time = datetime.now(timezone.utc)
            if period == "daily":
                cutoff_time -= timedelta(days=1)
            elif period == "weekly":
                cutoff_time -= timedelta(days=7)

            recent_articles = [
                article for article in all_articles
                if article.published and article.published > cutoff_time
            ]

            if not recent_articles:
                logger.info(f"No articles in the {period} period")
                return

            # Prioritize articles based on feedback from database
            for article in recent_articles:
                # Get feedback stats from database
                positive, negative = await self.db_manager.get_article_feedback_stats(article.id)
                total = positive + negative
                if total > 0:
                    article.priority_score = positive / total
                else:
                    # Check feed-level feedback for new articles
                    trending = await self.db_manager.get_trending_sources(days=30, limit=10)
                    feed_scores = {t['source']: t['ratio'] for t in trending}
                    article.priority_score = feed_scores.get(article.feed_name, 0.5)

            # Sort by priority score and date
            recent_articles.sort(
                key=lambda x: (x.priority_score, x.published or datetime.min.replace(tzinfo=timezone.utc)),
                reverse=True
            )

            # Get top articles
            max_articles = 10 if period == "daily" else 20
            top_articles = recent_articles[:max_articles]

            # Generate summaries
            await self.generate_summaries_batch(top_articles)

            # Format and post digest
            await self._post_digest(top_articles, period)

            logger.info_with_context(
                "Posted digest",
                period=period,
                articles_count=len(top_articles)
            )

        except Exception as e:
            logger.error(f"Error generating digest: {e}")

    async def _post_digest(self, articles: List[Article], period: str):
        """Post digest to Slack"""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📅 {period.title()} AI News Digest - {datetime.now().strftime('%Y-%m-%d')}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Here are the top {len(articles)} AI articles from the past {period}:"
                }
            },
            {"type": "divider"}
        ]

        # Add articles
        for i, article in enumerate(articles, 1):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{i}.* <{article.link}|{article.title}>"
                }
            })

            if article.ai_summary:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🤖 {article.ai_summary}"
                    }
                })

            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f"{article.feed_name} | {(article.published or datetime.now(timezone.utc)).strftime('%Y-%m-%d %H:%M UTC')}"
                }]
            })

            blocks.append({"type": "divider"})

        # Add trending sources from database
        trending_data = await self.db_manager.get_trending_sources(days=7, limit=3)
        if trending_data:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🔥 *Trending Sources* (based on your feedback):"
                }
            })

            for trend in trending_data:
                percentage = int(trend['ratio'] * 100)
                blocks.append({
                    "type": "context",
                    "elements": [{
                        "type": "mrkdwn",
                        "text": f"• {trend['source']}: {percentage}% interesting ({trend['total']} ratings)"
                    }]
                })

        # Post digest
        await self.slack_bot._send_response(
            self.slack_config.channel_id,
            f"{period.title()} AI News Digest"
        )

    async def _run_digest_scheduler(self):
        """Run digest scheduler"""
        last_digest_date = None

        while not self.shutdown_event.is_set():
            if self.digest_config.get('enabled'):
                now = datetime.now(timezone.utc)
                today_date = now.date()
                digest_time_str = self.digest_config.get('time', '09:00')

                try:
                    # Parse digest time
                    hour, minute = map(int, digest_time_str.split(':'))
                    digest_time = time(hour, minute)

                    # Check if it's time for daily digest
                    if (self.digest_config['schedule'] == 'daily' and
                        now.time() >= digest_time and
                        last_digest_date != today_date):

                        await self.generate_digest('daily')
                        last_digest_date = today_date

                    # Check if it's time for weekly digest (on Mondays)
                    elif (self.digest_config['schedule'] == 'weekly' and
                          now.weekday() == 0 and  # Monday
                          now.time() >= digest_time and
                          last_digest_date != today_date):

                        await self.generate_digest('weekly')
                        last_digest_date = today_date

                except Exception as e:
                    logger.error(f"Error in digest scheduler: {e}")

            # Wait before next check
            await asyncio.sleep(300)  # Check every 5 minutes

    async def run_scheduler_async(self):
        """Run the feed checker on schedule"""
        # Run initial check
        await self.check_feeds_async()

        logger.info(f"Scheduler started. Checking feeds every {self.check_interval} minutes.")

        # Start digest scheduler if enabled
        if self.digest_config.get('enabled'):
            self.digest_task = asyncio.create_task(self._run_digest_scheduler())

        # Keep running
        while not self.shutdown_event.is_set():
            # Wait for the specified interval or shutdown signal
            try:
                await asyncio.wait_for(
                    self.shutdown_event.wait(),
                    timeout=self.check_interval * 60
                )
            except asyncio.TimeoutError:
                # Normal timeout, check feeds
                await self.check_feeds_async()

    async def start(self):
        """Start the bot with fully async architecture"""
        logger.info("Starting Async AI News Bot...")

        # Initialize database
        await self.db_manager.initialize_database()
        logger.info("Database initialized")

        # Clean cache on startup
        logger.info("Cleaning feed cache...")
        self.cache_manager.clean_feed_cache("feed_cache.json")

        # Clean expired database cache
        await self.db_manager.clean_expired_cache()

        # Create tasks for parallel execution
        tasks = [
            asyncio.create_task(self.slack_bot.start()),
            asyncio.create_task(self.run_scheduler_async())
        ]

        # Post startup message
        await asyncio.sleep(2)  # Give Slack bot time to connect
        try:
            await self.slack_bot._send_response(
                self.slack_config.channel_id,
                "🚀 AI News Bot is now online with fully async architecture!"
            )
        except Exception as e:
            logger.error(f"Error posting startup message: {e}")

        # Wait for tasks
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Tasks cancelled, shutting down...")
        except Exception as e:
            logger.error(f"Error in async bot: {e}")
            raise

    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down Async AI News Bot...")
        self.shutdown_event.set()

        # Cancel digest task if running
        if self.digest_task:
            self.digest_task.cancel()

        # Stop Slack bot
        await self.slack_bot.stop()

        # Close database connections
        await self.db_manager.close()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(self.shutdown())


async def main():
    """Main entry point for async bot"""
    bot = AsyncAINewsBot()

    # Set up signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(bot.shutdown())
        )

    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    # Ensure single instance
    with SingleInstance('/tmp/slackwire.lock'):
        asyncio.run(main())