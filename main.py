import os
import logging
import time
import threading
from datetime import datetime, timezone
from dotenv import load_dotenv
import schedule

from rss_parser import RSSParser
from slack_bot import AINewsSlackBot
from feeds_config import RSS_FEEDS, AI_KEYWORDS
from llm_summarizer import create_summarizer

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ai_news_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AINewsBot:
    def __init__(self):
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
        self.rss_parser = RSSParser()
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
        
        # Set up callback for slash command
        self.slack_bot.get_latest_callback = self.handle_latest_articles_request
        
        logger.info("AI News Bot initialized")
    
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
    
    def handle_latest_articles_request(self, respond):
        """Handle slash command request for latest articles"""
        try:
            logger.info("Handling /ai-news-latest command")
            respond("🔄 Fetching latest AI articles...")
            
            # Fetch latest articles without using cache
            all_articles = []
            for feed in RSS_FEEDS:
                try:
                    feed_articles = self.rss_parser.parse_feed_no_cache(
                        feed['url'], 
                        feed['name'], 
                        feed['category'],
                        AI_KEYWORDS
                    )
                    all_articles.extend(feed_articles)
                except Exception as e:
                    logger.error(f"Error parsing feed {feed['name']}: {e}")
            
            if not all_articles:
                respond("📭 No articles found at this time. Please try again later.")
                return
            
            # Sort by date and get diverse selection
            all_articles.sort(
                key=lambda x: x['published'] or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True
            )
            
            # Get top 5 diverse articles
            diverse_articles = self._get_diverse_articles(all_articles, 5)
            
            # Generate summaries if available
            if self.summarizer:
                for article in diverse_articles:
                    try:
                        summary = self.summarizer.summarize(article)
                        if summary:
                            article['ai_summary'] = summary
                    except Exception as e:
                        logger.warning(f"Failed to summarize: {e}")
            
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
    
    def check_feeds(self):
        """Check all RSS feeds for new articles"""
        logger.info("Checking RSS feeds for new articles...")
        
        try:
            # Parse all feeds
            new_articles = self.rss_parser.parse_multiple_feeds(
                RSS_FEEDS,
                AI_KEYWORDS
            )
            
            if new_articles:
                logger.info(f"Found {len(new_articles)} new articles")
                
                # Limit articles per update
                max_articles_per_update = int(os.getenv('MAX_ARTICLES_PER_UPDATE', 10))
                
                # Get diverse selection across sources
                diverse_articles = self._get_diverse_articles(new_articles, max_articles_per_update)
                new_articles = diverse_articles
                
                # Generate summaries if LLM is available
                if self.summarizer:
                    logger.info("Generating AI summaries for articles...")
                    for article in new_articles:
                        try:
                            summary = self.summarizer.summarize(article)
                            if summary:
                                article['ai_summary'] = summary
                        except Exception as e:
                            logger.warning(f"Failed to summarize article '{article['title'][:50]}...': {e}")
                
                # Post to Slack
                self.slack_bot.post_articles(new_articles)
            else:
                logger.info("No new articles found")
                
        except Exception as e:
            logger.error(f"Error checking feeds: {e}")
    
    def run_scheduler(self):
        """Run the feed checker on schedule"""
        # Schedule regular checks
        schedule.every(self.check_interval).minutes.do(self.check_feeds)
        
        # Run initial check
        self.check_feeds()
        
        logger.info(f"Scheduler started. Checking feeds every {self.check_interval} minutes.")
        
        # Keep running
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def start(self):
        """Start the bot"""
        logger.info("Starting AI News Bot...")
        
        # Start Slack bot in a separate thread
        slack_thread = threading.Thread(target=self.slack_bot.start, daemon=True)
        slack_thread.start()
        
        # Give Slack bot time to connect
        time.sleep(2)
        
        # Post startup message
        try:
            self.slack_bot.app.client.chat_postMessage(
                channel=self.channel_id,
                text="🚀 AI News Bot is now online! I'll monitor RSS feeds and post updates about AI news and research."
            )
        except Exception as e:
            logger.error(f"Error posting startup message: {e}")
        
        # Start the scheduler
        self.run_scheduler()


def main():
    """Main entry point"""
    try:
        bot = AINewsBot()
        bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()