import os
import logging
import time
import threading
from datetime import datetime
from dotenv import load_dotenv
import schedule

from rss_parser import RSSParser
from slack_bot import AINewsSlackBot
from feeds_config import RSS_FEEDS, AI_KEYWORDS

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
        
        logger.info("AI News Bot initialized")
    
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