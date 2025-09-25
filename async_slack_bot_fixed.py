"""
Async Slack Bot Implementation using slack_bolt.async_app
This properly handles slash commands with the Bolt framework
"""

import asyncio
import logging
from typing import List, Dict, Optional, Callable, Any
from datetime import datetime

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from config_manager import ConfigManager
from feedback_manager import FeedbackManager
from models_v2 import Article, SlackConfig

logger = logging.getLogger(__name__)


class AsyncSlackBot:
    """Async Slack bot using slack_bolt.async_app for proper slash command handling"""

    def __init__(self, config: SlackConfig, db_manager: Optional['DatabaseManager'] = None):
        """Initialize async Slack bot with Bolt framework"""
        self.config = config
        self.db_manager = db_manager

        # Initialize Bolt app (async version)
        self.app = AsyncApp(token=config.bot_token)
        self.handler = AsyncSocketModeHandler(self.app, config.app_token)

        # Initialize managers
        self.config_manager = ConfigManager()
        self.feedback_manager = FeedbackManager()

        # Callbacks for external handlers
        self.get_latest_callback: Optional[Callable] = None
        self.reload_config_callback: Optional[Callable] = None
        self.set_digest_callback: Optional[Callable] = None

        # Register handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register async event handlers using Bolt decorators"""

        @self.app.event("app_mention")
        async def handle_mention(event, say):
            """Handle when the bot is mentioned"""
            await say(
                text="Hi! I'm the AI News Bot. I monitor RSS feeds from top AI labs and news sources to keep you updated on the latest in AI.",
                thread_ts=event.get("ts")
            )

        @self.app.command("/ai-news-status")
        async def handle_status_command(ack, command, respond):
            """Handle status check command"""
            await ack()  # Acknowledge immediately

            status_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🟢 AI News Bot Status"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Bot is running and monitoring feeds!"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Last check: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
                        }
                    ]
                }
            ]

            await respond(blocks=status_blocks, text="AI News Bot Status")

        @self.app.command("/ai-news-latest")
        async def handle_latest_command(ack, command, respond):
            """Handle request for latest articles"""
            await ack()  # Acknowledge immediately

            if self.get_latest_callback:
                logger.info(f"Processing /ai-news-latest from user {command.get('user_id')}")
                try:
                    # Call the async callback with command dict
                    await self.get_latest_callback(command)
                except Exception as e:
                    logger.error(f"Error in get_latest_callback: {e}", exc_info=True)
                    await respond("❌ An error occurred while fetching articles. Please try again.")
            else:
                await respond("⚠️ Latest articles feature is initializing. Please try again in a moment.")

        @self.app.command("/ai-news-add-feed")
        async def handle_add_feed(ack, command, respond):
            """Add a new RSS feed"""
            await ack()

            text = command.get('text', '').strip()
            parts = text.split(maxsplit=2)

            if len(parts) < 2:
                await respond("Usage: /ai-news-add-feed <url> <name> [category]")
                return

            url, name = parts[0], parts[1]
            category = parts[2] if len(parts) > 2 else "news"

            success, message = self.config_manager.add_feed(url, name, category)
            await respond(f"{'✅' if success else '❌'} {message}")

            if success and self.reload_config_callback:
                await self.reload_config_callback()

        @self.app.command("/ai-news-remove-feed")
        async def handle_remove_feed(ack, command, respond):
            """Remove a feed"""
            await ack()

            name = command.get('text', '').strip()

            if not name:
                await respond("Usage: /ai-news-remove-feed <name>")
                return

            success, message = self.config_manager.remove_feed(name)
            await respond(f"{'✅' if success else '❌'} {message}")

            if success and self.reload_config_callback:
                await self.reload_config_callback()

        @self.app.command("/ai-news-list-feeds")
        async def handle_list_feeds(ack, command, respond):
            """List all feeds"""
            await ack()

            feeds = self.config_manager.list_feeds()

            if not feeds:
                await respond("No feeds configured.")
                return

            blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "📡 RSS Feeds"}
                },
                {"type": "divider"}
            ]

            for feed in feeds:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{feed['name']}*\n{feed['url']}\nCategory: {feed.get('category', 'news')}"
                    }
                })

            await respond(blocks=blocks, text="RSS Feeds List")

        @self.app.command("/ai-news-add-keyword")
        async def handle_add_keyword(ack, command, respond):
            """Add a keyword"""
            await ack()

            keyword = command.get('text', '').strip()

            if not keyword:
                await respond("Usage: /ai-news-add-keyword <keyword>")
                return

            success, message = self.config_manager.add_keyword(keyword)
            await respond(f"{'✅' if success else '❌'} {message}")

            if success and self.reload_config_callback:
                await self.reload_config_callback()

        @self.app.command("/ai-news-remove-keyword")
        async def handle_remove_keyword(ack, command, respond):
            """Remove a keyword"""
            await ack()

            keyword = command.get('text', '').strip()

            if not keyword:
                await respond("Usage: /ai-news-remove-keyword <keyword>")
                return

            success, message = self.config_manager.remove_keyword(keyword)
            await respond(f"{'✅' if success else '❌'} {message}")

            if success and self.reload_config_callback:
                await self.reload_config_callback()

        @self.app.command("/ai-news-list-keywords")
        async def handle_list_keywords(ack, command, respond):
            """List keywords"""
            await ack()

            keywords = self.config_manager.list_keywords()

            if not keywords:
                await respond("No keywords configured.")
                return

            keyword_list = ", ".join(f"`{k}`" for k in keywords)
            await respond(f"🔍 AI Keywords: {keyword_list}")

        @self.app.command("/ai-news-digest")
        async def handle_digest(ack, command, respond):
            """Configure digest"""
            await ack()

            schedule = command.get('text', '').strip().lower()

            if schedule not in ["daily", "weekly", "off"]:
                await respond("Usage: /ai-news-digest <daily|weekly|off>")
                return

            if self.set_digest_callback:
                await self.set_digest_callback(schedule)
                await respond(f"✅ Digest schedule updated: {schedule}")
            else:
                await respond("Digest feature not configured.")

        @self.app.command("/ai-news-reload")
        async def handle_reload(ack, command, respond):
            """Reload configuration"""
            await ack()

            if self.reload_config_callback:
                await self.reload_config_callback()
                await respond("✅ Configuration reloaded successfully!")
            else:
                await respond("Reload feature not configured.")

        @self.app.action({"action_id": {"$regex": "^feedback_.*"}})
        async def handle_feedback(ack, body, client):
            """Handle feedback button clicks"""
            await ack()

            action = body["actions"][0]
            action_id = action["action_id"]
            user_id = body["user"]["id"]

            # Parse action_id: feedback_positive_articleid or feedback_negative_articleid
            parts = action_id.split("_", 2)
            if len(parts) == 3:
                _, feedback_type, article_id = parts
                is_positive = feedback_type == "positive"

                # Record feedback
                if self.db_manager:
                    # Use database
                    await self.db_manager.save_feedback(
                        article_id=article_id,
                        user_id=user_id,
                        is_positive=is_positive
                    )
                else:
                    # Use file-based feedback
                    self.feedback_manager.record_feedback(
                        article_id, user_id, is_positive
                    )

                # Add reaction to message
                channel = body["channel"]["id"]
                timestamp = body["message"]["ts"]

                await client.reactions_add(
                    channel=channel,
                    timestamp=timestamp,
                    name="white_check_mark"
                )

    def format_article_block(self, article: Article) -> List[Dict]:
        """Format article as Slack blocks"""
        blocks = []

        # Title and link
        title_text = f"*<{article.link}|{article.title}>*"
        if hasattr(article, 'feed_category') and article.feed_category:
            title_text = f"[{article.feed_category}] {title_text}"
        elif article.category:
            title_text = f"[{article.category}] {title_text}"

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": title_text
            }
        })

        # AI Summary if available
        if article.ai_summary:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🤖 *AI Summary:* {article.ai_summary}"
                }
            })

        # Original summary
        if article.summary:
            summary = article.summary[:500] + "..." if len(article.summary) > 500 else article.summary
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": summary
                }
            })

        # Metadata
        metadata_parts = [f"📰 *{article.feed_name}*"]
        if article.published:
            metadata_parts.append(article.published.strftime('%Y-%m-%d %H:%M UTC'))

        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": " | ".join(metadata_parts)}
            ]
        })

        # Feedback buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "👍 Interesting"},
                    "action_id": f"feedback_positive_{article.id}",
                    "style": "primary"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "👎 Not Relevant"},
                    "action_id": f"feedback_negative_{article.id}"
                }
            ]
        })

        blocks.append({"type": "divider"})

        return blocks

    async def post_articles(self, articles: List[Article]):
        """Post articles to Slack channel"""
        if not articles:
            return

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🔥 AI News Update - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
                }
            },
            {"type": "divider"}
        ]

        for article in articles[:10]:  # Limit to avoid hitting block limits
            blocks.extend(self.format_article_block(article))

        # Remove last divider
        if blocks[-1].get("type") == "divider":
            blocks.pop()

        try:
            await self.app.client.chat_postMessage(
                channel=self.config.channel_id,
                blocks=blocks,
                text=f"AI News Update - {len(articles)} new articles"
            )
            logger.info(f"Posted {len(articles)} articles to Slack")
        except Exception as e:
            logger.error(f"Error posting articles: {e}")

    async def _send_response(self, channel: str, text: str):
        """Send a simple text response to a channel"""
        try:
            await self.app.client.chat_postMessage(
                channel=channel,
                text=text
            )
        except Exception as e:
            logger.error(f"Error sending response: {e}")

    async def start(self):
        """Start the async Slack bot"""
        logger.info("Starting async Slack bot with Bolt framework...")

        try:
            # Start the Socket Mode handler
            await self.handler.start_async()
            logger.info("Connected to Slack via Socket Mode (Bolt)")

        except Exception as e:
            logger.error(f"Error in async Slack bot: {e}")
            raise

    async def stop(self):
        """Stop the async Slack bot"""
        logger.info("Stopping async Slack bot...")
        await self.handler.close_async()