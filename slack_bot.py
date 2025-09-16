import os
import logging
from typing import List, Dict
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from datetime import datetime

logger = logging.getLogger(__name__)


class AINewsSlackBot:
    def __init__(self, bot_token: str, app_token: str, channel_id: str):
        self.app = App(token=bot_token)
        self.app_token = app_token
        self.channel_id = channel_id
        
        # Register event handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register Slack event handlers"""
        
        @self.app.event("app_mention")
        def handle_mention(event, say):
            """Handle when the bot is mentioned"""
            say(
                text="Hi! I'm the AI News Bot. I monitor RSS feeds from top AI labs and news sources to keep you updated on the latest in AI.",
                thread_ts=event.get("ts")
            )
        
        @self.app.command("/ai-news-status")
        def handle_status_command(ack, command, respond):
            """Handle status check command"""
            ack()
            respond("AI News Bot is running and monitoring feeds!")
    
    def format_article_block(self, article: Dict) -> List[Dict]:
        """Format article as Slack block"""
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*<{article['link']}|{article['title']}>*"
                }
            }
        ]
        
        # Add summary if available
        if article.get('summary'):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": article['summary']
                }
            })
        
        # Add metadata
        metadata_parts = []
        if article.get('feed_name'):
            metadata_parts.append(f"*Source:* {article['feed_name']}")
        if article.get('category'):
            metadata_parts.append(f"*Category:* {article['category']}")
        if article.get('published'):
            pub_date = article['published'].strftime("%Y-%m-%d %H:%M UTC")
            metadata_parts.append(f"*Published:* {pub_date}")
        
        if metadata_parts:
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": " | ".join(metadata_parts)
                }]
            })
        
        # Add divider
        blocks.append({"type": "divider"})
        
        return blocks
    
    def post_articles(self, articles: List[Dict], batch_size: int = 5):
        """Post articles to Slack channel"""
        if not articles:
            logger.info("No new articles to post")
            return
        
        try:
            # Post in batches to avoid rate limits
            for i in range(0, len(articles), batch_size):
                batch = articles[i:i + batch_size]
                blocks = []
                
                # Add header for first batch
                if i == 0:
                    blocks.append({
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"🤖 AI News Update - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
                        }
                    })
                    blocks.append({"type": "divider"})
                
                # Add articles
                for article in batch:
                    blocks.extend(self.format_article_block(article))
                
                # Remove last divider
                if blocks and blocks[-1].get("type") == "divider":
                    blocks.pop()
                
                # Post to Slack
                self.app.client.chat_postMessage(
                    channel=self.channel_id,
                    blocks=blocks,
                    text=f"AI News: {len(batch)} new articles"
                )
                
                logger.info(f"Posted batch of {len(batch)} articles")
                
        except Exception as e:
            logger.error(f"Error posting to Slack: {e}")
    
    def post_single_article(self, article: Dict):
        """Post a single article immediately"""
        try:
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🔔 Breaking AI News"
                    }
                },
                {"type": "divider"}
            ]
            blocks.extend(self.format_article_block(article))
            
            # Remove last divider
            if blocks[-1].get("type") == "divider":
                blocks.pop()
            
            self.app.client.chat_postMessage(
                channel=self.channel_id,
                blocks=blocks,
                text=f"Breaking: {article['title']}"
            )
            
            logger.info(f"Posted breaking news: {article['title']}")
            
        except Exception as e:
            logger.error(f"Error posting single article: {e}")
    
    def start(self):
        """Start the Slack bot in socket mode"""
        handler = SocketModeHandler(self.app, self.app_token)
        logger.info("Starting Slack bot...")
        handler.start()