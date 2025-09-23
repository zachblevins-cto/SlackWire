import os
import logging
from typing import List, Dict, Optional
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from datetime import datetime
import json
from config_manager import ConfigManager
from feedback_manager import FeedbackManager

logger = logging.getLogger(__name__)


class AINewsSlackBot:
    def __init__(self, bot_token: str, app_token: str, channel_id: str):
        self.app = App(token=bot_token)
        self.app_token = app_token
        self.channel_id = channel_id
        
        # Initialize managers
        self.config_manager = ConfigManager()
        self.feedback_manager = FeedbackManager()
        
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
        
        @self.app.command("/ai-news-latest")
        def handle_latest_command(ack, command, respond):
            """Handle request for latest articles"""
            ack()
            # This will be populated by the main bot
            if hasattr(self, 'get_latest_callback') and self.get_latest_callback:
                self.get_latest_callback(respond)
            else:
                respond("⚠️ Latest articles feature is initializing. Please try again in a moment.")
        
        @self.app.command("/ai-news-add-feed")
        def handle_add_feed(ack, command, respond):
            """Add a new RSS feed"""
            ack()
            text = command.get('text', '').strip()
            
            if not text:
                respond("❌ Usage: `/ai-news-add-feed <url> <name> [category]`\nExample: `/ai-news-add-feed https://example.com/feed.xml ExampleAI company`")
                return
            
            parts = text.split(maxsplit=2)
            if len(parts) < 2:
                respond("❌ Please provide both URL and name. Usage: `/ai-news-add-feed <url> <name> [category]`")
                return
            
            url = parts[0]
            name = parts[1]
            category = parts[2] if len(parts) > 2 else "general"
            
            success, message = self.config_manager.add_feed(url, name, category)
            if success:
                respond(f"✅ {message}")
                if hasattr(self, 'reload_config_callback') and self.reload_config_callback:
                    self.reload_config_callback()
            else:
                respond(f"❌ {message}")
        
        @self.app.command("/ai-news-remove-feed")
        def handle_remove_feed(ack, command, respond):
            """Remove an RSS feed"""
            ack()
            name = command.get('text', '').strip()
            
            if not name:
                respond("❌ Usage: `/ai-news-remove-feed <name>`")
                return
            
            success, message = self.config_manager.remove_feed(name)
            if success:
                respond(f"✅ {message}")
                if hasattr(self, 'reload_config_callback') and self.reload_config_callback:
                    self.reload_config_callback()
            else:
                respond(f"❌ {message}")
        
        @self.app.command("/ai-news-list-feeds")
        def handle_list_feeds(ack, command, respond):
            """List all configured feeds"""
            ack()
            feeds = self.config_manager.list_feeds()
            
            if not feeds:
                respond("📭 No feeds configured yet.")
                return
            
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "📡 Configured RSS Feeds"
                    }
                },
                {"type": "divider"}
            ]
            
            for feed in feeds:
                blocks.append({
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Name:* {feed['name']}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Category:* {feed.get('category', 'general')}"
                        }
                    ]
                })
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*URL:* `{feed['url']}`"
                    }
                })
                blocks.append({"type": "divider"})
            
            # Remove last divider
            if blocks[-1].get("type") == "divider":
                blocks.pop()
            
            respond(blocks=blocks, text=f"Found {len(feeds)} configured feeds")
        
        @self.app.command("/ai-news-add-keyword")
        def handle_add_keyword(ack, command, respond):
            """Add a new keyword"""
            ack()
            keyword = command.get('text', '').strip()
            
            if not keyword:
                respond("❌ Usage: `/ai-news-add-keyword <keyword>`")
                return
            
            success, message = self.config_manager.add_keyword(keyword)
            if success:
                respond(f"✅ {message}")
                if hasattr(self, 'reload_config_callback') and self.reload_config_callback:
                    self.reload_config_callback()
            else:
                respond(f"❌ {message}")
        
        @self.app.command("/ai-news-remove-keyword")
        def handle_remove_keyword(ack, command, respond):
            """Remove a keyword"""
            ack()
            keyword = command.get('text', '').strip()
            
            if not keyword:
                respond("❌ Usage: `/ai-news-remove-keyword <keyword>`")
                return
            
            success, message = self.config_manager.remove_keyword(keyword)
            if success:
                respond(f"✅ {message}")
                if hasattr(self, 'reload_config_callback') and self.reload_config_callback:
                    self.reload_config_callback()
            else:
                respond(f"❌ {message}")
        
        @self.app.command("/ai-news-list-keywords")
        def handle_list_keywords(ack, command, respond):
            """List all configured keywords"""
            ack()
            keywords = self.config_manager.list_keywords()
            
            if not keywords:
                respond("📭 No keywords configured yet.")
                return
            
            keywords_text = "\n".join([f"• {keyword}" for keyword in sorted(keywords)])
            respond(f"🔍 *AI Keywords ({len(keywords)} total):*\n{keywords_text}")
        
        @self.app.command("/ai-news-digest")
        def handle_digest_command(ack, command, respond):
            """Handle digest configuration"""
            ack()
            text = command.get('text', '').strip().lower()
            
            if text not in ['daily', 'weekly', 'off']:
                respond("❌ Usage: `/ai-news-digest <daily|weekly|off>`")
                return
            
            # Update digest configuration
            if hasattr(self, 'set_digest_callback') and self.set_digest_callback:
                self.set_digest_callback(text)
                
            if text == 'off':
                respond("📅 Digest notifications have been turned off.")
            else:
                respond(f"📅 Digest mode set to: {text}. You'll receive a summary {text} at 09:00 UTC.")
        
        @self.app.action("article_interesting")
        def handle_interesting(ack, body, client):
            """Handle 'interesting' button click"""
            ack()
            self._handle_article_feedback(body, client, "interesting")
        
        @self.app.action("article_not_relevant")
        def handle_not_relevant(ack, body, client):
            """Handle 'not relevant' button click"""
            ack()
            self._handle_article_feedback(body, client, "not_relevant")
    
    def _handle_article_feedback(self, body, client, feedback_type: str):
        """Process article feedback"""
        try:
            # Extract data
            user = body["user"]["id"]
            action_value = body["actions"][0]["value"]
            article_data = json.loads(action_value)
            
            # Record feedback
            self.feedback_manager.add_feedback(
                article_id=article_data['id'],
                user_id=user,
                feedback_type=feedback_type,
                article_metadata=article_data
            )
            
            # Update message to show feedback was recorded
            blocks = body["message"]["blocks"]
            
            # Find and update the feedback buttons
            for i, block in enumerate(blocks):
                if block.get("type") == "actions" and block.get("block_id", "").startswith("article_feedback_"):
                    # Get current feedback stats
                    feedback_summary = self.feedback_manager.get_article_feedback_summary(article_data['id'])
                    
                    # Update the context block that follows the actions
                    if i + 1 < len(blocks) and blocks[i + 1].get("type") == "context":
                        blocks[i + 1] = {
                            "type": "context",
                            "elements": [{
                                "type": "mrkdwn",
                                "text": f"👍 {feedback_summary.get('interesting', 0)} | 👎 {feedback_summary.get('not_relevant', 0)}"
                            }]
                        }
                    break
            
            # Update the message
            client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                blocks=blocks
            )
            
            # Send ephemeral confirmation
            emoji = "👍" if feedback_type == "interesting" else "👎"
            client.chat_postEphemeral(
                channel=body["channel"]["id"],
                user=user,
                text=f"{emoji} Thanks for your feedback!"
            )
            
        except Exception as e:
            logger.error(f"Error handling feedback: {e}")
    
    def format_article_block(self, article: Dict, include_feedback: bool = True) -> List[Dict]:
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
        
        # Add AI summary if available, otherwise use original summary
        if article.get('ai_summary'):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🤖 *AI Summary:* {article['ai_summary']}"
                }
            })
        elif article.get('summary'):
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
        
        # Add feedback buttons if requested
        if include_feedback and article.get('id'):
            # Prepare article data for feedback tracking
            feedback_data = {
                'id': article['id'],
                'title': article.get('title', ''),
                'feed_name': article.get('feed_name', ''),
                'category': article.get('category', '')
            }
            
            blocks.append({
                "type": "actions",
                "block_id": f"article_feedback_{article['id'][:8]}",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "👍 Interesting",
                            "emoji": True
                        },
                        "value": json.dumps(feedback_data),
                        "action_id": "article_interesting",
                        "style": "primary"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "👎 Not Relevant",
                            "emoji": True
                        },
                        "value": json.dumps(feedback_data),
                        "action_id": "article_not_relevant"
                    }
                ]
            })
            
            # Add feedback stats if available
            feedback_summary = self.feedback_manager.get_article_feedback_summary(article['id'])
            if any(feedback_summary.values()):
                blocks.append({
                    "type": "context",
                    "elements": [{
                        "type": "mrkdwn",
                        "text": f"👍 {feedback_summary.get('interesting', 0)} | 👎 {feedback_summary.get('not_relevant', 0)}"
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