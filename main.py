import os
import asyncio
import threading
import signal
import sys
from datetime import datetime, timezone, time
from dotenv import load_dotenv
import json

from typing import List, Dict

from rss_parser import AsyncRSSParser
from slack_bot import AINewsSlackBot
from llm_summarizer import create_summarizer
from logger_config import setup_logging, get_logger
from utils.single_instance import SingleInstance
from utils.cache_manager import CacheManager

# Load environment variables
load_dotenv()

# Configure structured logging
setup_logging()
logger = get_logger(__name__)


class AsyncAINewsBot:
    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.cache_manager = CacheManager(max_entries=5000, expiry_days=7)
        self.slack_thread = None
        # Load configuration
        self.slack_bot_token = os.getenv('SLACK_BOT_TOKEN')
        self.slack_app_token = os.getenv('SLACK_APP_TOKEN')
        self.channel_id = os.getenv('SLACK_CHANNEL_ID')
        self.check_interval = int(os.getenv('CHECK_INTERVAL_MINUTES', 30))
        
        # LLM configuration
        self.llm_backend = os.getenv('LLM_BACKEND', 'ollama')
        self.llm_model = os.getenv('LLM_MODEL', 'llama3.2')
        self.llm_base_url = os.getenv('LLM_BASE_URL', 'http://localhost:11434')
        self.enable_summaries = os.getenv('ENABLE_LLM_SUMMARIES', 'true').lower() == 'true'
        
        # Validate configuration
        if not all([self.slack_bot_token, self.slack_app_token, self.channel_id]):
            raise ValueError("Missing required Slack configuration. Check .env file.")
        
        # Initialize components
        self.rss_parser = AsyncRSSParser()
        
        # Get feeds and keywords from config
        self.rss_feeds = self.rss_parser.get_feeds_from_config()
        self.ai_keywords = self.rss_parser.get_keywords_from_config()
        
        self.slack_bot = AINewsSlackBot(
            self.slack_bot_token,
            self.slack_app_token,
            self.channel_id
        )
        
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
        self._schedule_digest_if_enabled()
        
        logger.info_with_context(
            "AI News Bot initialized",
            feeds_count=len(self.rss_feeds),
            keywords_count=len(self.ai_keywords),
            llm_backend=self.llm_backend,
            summaries_enabled=self.enable_summaries
        )
    
    def _get_diverse_articles(self, articles, max_articles):
        """Get a diverse selection of articles across different sources"""
        # Group articles by source
        articles_by_source = {}
        for article in articles:
            source = article.get('feed_name', 'Unknown')
            if source not in articles_by_source:
                articles_by_source[source] = []
            articles_by_source[source].append(article)
        
        # Sort each source's articles by date
        for source in articles_by_source:
            articles_by_source[source].sort(
                key=lambda x: x['published'] or datetime.min.replace(tzinfo=timezone.utc),
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
    
    def reload_configuration(self):
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
    
    def _load_digest_config(self) -> dict:
        """Load digest configuration from file"""
        digest_file = "digest_config.json"
        if os.path.exists(digest_file):
            try:
                with open(digest_file, 'r') as f:
                    return json.load(f)
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
    
    def _schedule_digest_if_enabled(self):
        """Schedule digest based on configuration"""
        if self.digest_config.get('enabled') and self.digest_config.get('schedule'):
            schedule = self.digest_config['schedule']
            digest_time = self.digest_config.get('time', '09:00')
            logger.info(f"Digest enabled: {schedule} at {digest_time}")
    
    def set_digest_schedule(self, schedule: str):
        """Update digest schedule"""
        if schedule == 'off':
            self.digest_config['enabled'] = False
            self.digest_config['schedule'] = None
        else:
            self.digest_config['enabled'] = True
            self.digest_config['schedule'] = schedule
        
        self._save_digest_config()
        logger.info(f"Digest schedule updated: {schedule}")
    
    async def generate_summaries_batch(self, articles: List[Dict]):
        """Generate summaries for articles in parallel (if possible)"""
        if not self.summarizer:
            return
        
        logger.info(f"Generating AI summaries for {len(articles)} articles...")
        
        # For now, we'll process summaries sequentially
        # (Most LLM APIs don't handle concurrent requests well)
        for article in articles:
            try:
                summary = self.summarizer.summarize(article)
                if summary:
                    article['ai_summary'] = summary
            except Exception as e:
                logger.warning_with_context(
                    "Failed to summarize article",
                    article_title=article['title'][:50],
                    article_id=article.get('id'),
                    error=str(e)
                )
    
    def handle_latest_articles_request(self, respond):
        """Handle slash command request for latest articles"""
        # Run the async function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._handle_latest_articles_async(respond))
        finally:
            loop.close()
    
    async def _handle_latest_articles_async(self, respond):
        """Async handler for latest articles request"""
        try:
            logger.info("Handling /ai-news-latest command")
            respond("🔄 Fetching latest AI articles...")
            
            # Fetch latest articles without using cache
            all_articles = await self.rss_parser.parse_multiple_feeds_async(
                keywords=self.ai_keywords,
                use_cache=False
            )
            
            if not all_articles:
                respond("📭 No articles found at this time. Please try again later.")
                return
            
            # Filter articles from the last 7 days
            from datetime import timedelta
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)
            recent_articles = [
                article for article in all_articles
                if article.get('published') and article['published'] > cutoff_time
            ]
            
            if not recent_articles:
                respond("📭 No articles found in the last 7 days. RSS feeds may contain older content.")
                return
            
            # Sort by date (newest first)
            recent_articles.sort(
                key=lambda x: x.get('published', datetime.min.replace(tzinfo=timezone.utc)),
                reverse=True
            )
            
            # Get top 5 diverse articles from recent ones
            diverse_articles = self._get_diverse_articles(recent_articles, 5)
            
            # Generate summaries
            await self.generate_summaries_batch(diverse_articles)
            
            # Format response
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"🔥 Latest AI Articles - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
                    }
                },
                {"type": "divider"}
            ]
            
            for article in diverse_articles:
                blocks.extend(self.slack_bot.format_article_block(article))
            
            # Remove last divider
            if blocks[-1].get("type") == "divider":
                blocks.pop()
            
            respond(blocks=blocks, text="Latest AI articles")
            logger.info(f"Posted {len(diverse_articles)} latest articles via slash command")
            
        except Exception as e:
            logger.error(f"Error handling latest articles request: {e}")
            respond("❌ Sorry, an error occurred while fetching articles. Please try again later.")
    
    async def check_feeds_async(self):
        """Check all RSS feeds for new articles asynchronously"""
        logger.info("Checking RSS feeds for new articles...")
        
        try:
            # Parse all feeds concurrently
            new_articles = await self.rss_parser.parse_multiple_feeds_async(
                keywords=self.ai_keywords,
                use_cache=True
            )
            
            if new_articles:
                logger.info_with_context(
                    "Found new articles",
                    articles_count=len(new_articles),
                    sources=list(set(a['feed_name'] for a in new_articles))
                )
                
                # Limit articles per update
                max_articles_per_update = int(os.getenv('MAX_ARTICLES_PER_UPDATE', 10))
                
                # Get diverse selection across sources
                diverse_articles = self._get_diverse_articles(new_articles, max_articles_per_update)
                new_articles = diverse_articles
                
                # Generate summaries
                await self.generate_summaries_batch(new_articles)
                
                # Post to Slack
                self.slack_bot.post_articles(new_articles)
            else:
                logger.info("No new articles found")
                
        except Exception as e:
            logger.error(f"Error checking feeds: {e}")
    
    async def generate_digest(self, period: str = "daily"):
        """Generate a digest of top articles"""
        logger.info(f"Generating {period} digest...")
        
        try:
            # Fetch all articles without cache to get recent ones
            all_articles = await self.rss_parser.parse_multiple_feeds_async(
                keywords=self.ai_keywords,
                use_cache=False
            )
            
            if not all_articles:
                logger.info("No articles found for digest")
                return
            
            # Filter articles based on period
            from datetime import timedelta
            cutoff_time = datetime.now(timezone.utc)
            if period == "daily":
                cutoff_time -= timedelta(days=1)
            elif period == "weekly":
                cutoff_time -= timedelta(days=7)
            
            recent_articles = [
                article for article in all_articles 
                if article.get('published') and article['published'] > cutoff_time
            ]
            
            if not recent_articles:
                logger.info(f"No articles in the {period} period")
                return
            
            # Prioritize articles based on feedback
            for article in recent_articles:
                article['priority_score'] = self.slack_bot.feedback_manager.should_prioritize_article(
                    article
                )
            
            # Sort by priority score and date
            recent_articles.sort(
                key=lambda x: (x['priority_score'], x.get('published', datetime.min.replace(tzinfo=timezone.utc))),
                reverse=True
            )
            
            # Get top articles (more for weekly)
            max_articles = 10 if period == "daily" else 20
            top_articles = recent_articles[:max_articles]
            
            # Generate summaries
            await self.generate_summaries_batch(top_articles)
            
            # Format digest message
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
                        "text": f"Here are the top {len(top_articles)} AI articles from the past {period}:"
                    }
                },
                {"type": "divider"}
            ]
            
            # Add articles (without feedback buttons for digest)
            for i, article in enumerate(top_articles, 1):
                # Add number
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{i}.* <{article['link']}|{article['title']}>"
                    }
                })
                
                # Add summary if available
                if article.get('ai_summary'):
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🤖 {article['ai_summary']}"
                        }
                    })
                
                # Add metadata
                blocks.append({
                    "type": "context",
                    "elements": [{
                        "type": "mrkdwn",
                        "text": f"{article.get('feed_name', 'Unknown')} | {article.get('published', datetime.now()).strftime('%Y-%m-%d %H:%M UTC')}"
                    }]
                })
                
                blocks.append({"type": "divider"})
            
            # Add trending sources
            trending = self.slack_bot.feedback_manager.get_trending_sources(3)
            if trending:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "🔥 *Trending Sources* (based on your feedback):"
                    }
                })
                
                for source, ratio, total in trending:
                    percentage = int(ratio * 100)
                    blocks.append({
                        "type": "context",
                        "elements": [{
                            "type": "mrkdwn",
                            "text": f"• {source}: {percentage}% interesting ({total} ratings)"
                        }]
                    })
            
            # Post digest
            self.slack_bot.app.client.chat_postMessage(
                channel=self.channel_id,
                blocks=blocks,
                text=f"{period.title()} AI News Digest"
            )
            
            logger.info_with_context(
                "Posted digest",
                period=period,
                articles_count=len(top_articles),
                trending_sources=[s[0] for s in trending[:3]] if trending else []
            )
            
        except Exception as e:
            logger.error(f"Error generating digest: {e}")
    
    async def run_scheduler_async(self):
        """Run the feed checker on schedule using asyncio"""
        # Run initial check
        await self.check_feeds_async()
        
        logger.info(f"Scheduler started. Checking feeds every {self.check_interval} minutes.")
        
        last_digest_date = None
        
        # Keep running
        while True:
            # Check if digest should be sent
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
                    logger.error(f"Error checking digest schedule: {e}")
            
            # Wait for the specified interval or shutdown signal
            try:
                await asyncio.wait_for(
                    self.shutdown_event.wait(),
                    timeout=min(self.check_interval * 60, 300)
                )
                if self.shutdown_event.is_set():
                    logger.info("Shutdown requested, stopping scheduler...")
                    break
            except asyncio.TimeoutError:
                pass  # Normal timeout, continue loop
            
            # Check feeds
            await self.check_feeds_async()
    
    def start(self):
        """Start the bot"""
        logger.info("Starting Async AI News Bot...")
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # Start Slack bot in a separate thread
        self.slack_thread = threading.Thread(target=self.slack_bot.start, daemon=False)
        self.slack_thread.start()
        
        # Give Slack bot time to connect
        import time
        time.sleep(2)
        
        # Post startup message
        try:
            self.slack_bot.app.client.chat_postMessage(
                channel=self.channel_id,
                text="🚀 AI News Bot is now online with improved stability! I'll monitor RSS feeds concurrently for faster updates."
            )
        except Exception as e:
            logger.error(f"Error posting startup message: {e}")
        
        # Clean cache on startup
        logger.info("Cleaning feed cache...")
        self.cache_manager.clean_feed_cache("feed_cache.json")
        
        # Start the async scheduler
        asyncio.run(self.run_scheduler_async())
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutdown_event.set()
        # Slack bot doesn't have a stop method, just exit gracefully
        sys.exit(0)


def main():
    """Main entry point"""
    # Ensure single instance
    with SingleInstance('/tmp/slackwire.lock'):
        try:
            bot = AsyncAINewsBot()
            bot.start()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise


if __name__ == "__main__":
    main()