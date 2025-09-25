"""
Async Slack Bot Implementation
Replaces the synchronous slack_bot.py with fully async architecture
"""

import asyncio
import logging
from typing import List, Dict, Optional, Callable, Any, TYPE_CHECKING
from datetime import datetime
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.socket_mode.request import SocketModeRequest

from config_manager import ConfigManager
from feedback_manager import FeedbackManager
from models_v2 import Article, SlackConfig

if TYPE_CHECKING:
    from database.manager import DatabaseManager

logger = logging.getLogger(__name__)


class AsyncSlackBot:
    """Fully async Slack bot implementation using async SDK"""

    def __init__(self, config: SlackConfig, db_manager: Optional['DatabaseManager'] = None):
        """Initialize async Slack bot with configuration"""
        self.config = config
        self.web_client = AsyncWebClient(token=config.bot_token)
        self.socket_client = SocketModeClient(
            app_token=config.app_token,
            web_client=self.web_client
        )

        # Database manager (optional for backward compatibility)
        self.db_manager = db_manager

        # Initialize managers
        self.config_manager = ConfigManager()
        self.feedback_manager = FeedbackManager()

        # Callbacks for external handlers
        self.get_latest_callback: Optional[Callable] = None
        self.reload_config_callback: Optional[Callable] = None
        self.set_digest_callback: Optional[Callable] = None

        # Rate limiting
        self.rate_limiter = asyncio.Semaphore(3)  # Max 3 concurrent Slack API calls
        self.message_queue: asyncio.Queue = asyncio.Queue()

        # Register handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register async event handlers"""

        @self.socket_client.socket_mode_request_listeners.append
        async def handle_socket_mode_request(client: SocketModeClient, req: SocketModeRequest):
            """Main socket mode request handler"""
            logger.info(f"Received Socket Mode request: type={req.type}, envelope_id={req.envelope_id}")

            # Acknowledge the request immediately to avoid timeout
            try:
                response = SocketModeResponse(envelope_id=req.envelope_id)
                await client.send_socket_mode_response(response)
                logger.info(f"Acknowledged request {req.envelope_id} successfully")
            except Exception as e:
                logger.error(f"Failed to acknowledge request {req.envelope_id}: {e}")
                raise

            # Process the request asynchronously
            if req.type == "events_api":
                logger.info("Processing events_api request")
                asyncio.create_task(self._handle_event(req))
            elif req.type == "slash_commands":
                command = req.payload.get("command", "unknown")
                logger.info(f"Processing slash_command: {command}")
                asyncio.create_task(self._handle_slash_command(req))
            elif req.type == "interactive":
                logger.info("Processing interactive request")
                asyncio.create_task(self._handle_interactive(req))
            else:
                logger.warning(f"Unknown request type: {req.type}")

    async def _handle_event(self, req: SocketModeRequest):
        """Handle Slack events"""
        event = req.payload.get("event", {})

        if event.get("type") == "app_mention":
            await self._handle_mention(event)

    async def _handle_mention(self, event: Dict):
        """Handle bot mentions"""
        channel = event.get("channel")
        thread_ts = event.get("ts")

        async with self.rate_limiter:
            await self.web_client.chat_postMessage(
                channel=channel,
                text="Hi! I'm the AI News Bot. I monitor RSS feeds from top AI labs and news sources to keep you updated on the latest in AI.",
                thread_ts=thread_ts
            )

    async def _handle_slash_command(self, req: SocketModeRequest):
        """Handle slash commands"""
        command = req.payload
        command_text = command.get("command", "")
        logger.info(f"Handling slash command: {command_text}, user={command.get('user_id')}, channel={command.get('channel_id')}")

        # Command handlers mapping
        handlers = {
            "/ai-news-status": self._handle_status,
            "/ai-news-latest": self._handle_latest,
            "/ai-news-add-feed": self._handle_add_feed,
            "/ai-news-remove-feed": self._handle_remove_feed,
            "/ai-news-list-feeds": self._handle_list_feeds,
            "/ai-news-add-keyword": self._handle_add_keyword,
            "/ai-news-remove-keyword": self._handle_remove_keyword,
            "/ai-news-list-keywords": self._handle_list_keywords,
            "/ai-news-digest": self._handle_digest,
            "/ai-news-reload": self._handle_reload,
        }

        handler = handlers.get(command_text)
        if handler:
            await handler(command)

    async def _handle_status(self, command: Dict):
        """Handle status check command"""
        response_url = command.get("response_url")

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

        async with self.rate_limiter:
            await self.web_client.chat_postMessage(
                channel=command.get("channel_id"),
                blocks=status_blocks,
                text="AI News Bot Status"
            )

    async def _handle_latest(self, command: Dict):
        """Handle request for latest articles"""
        logger.info(f"_handle_latest called for channel {command.get('channel_id')}")
        if self.get_latest_callback:
            logger.info("Calling get_latest_callback")
            try:
                # Call the async callback
                await self.get_latest_callback(command)
                logger.info("get_latest_callback completed successfully")
            except Exception as e:
                logger.error(f"Error in get_latest_callback: {e}", exc_info=True)
                await self._send_response(
                    command.get("channel_id"),
                    "❌ An error occurred while fetching articles. Please try again."
                )
        else:
            logger.error("get_latest_callback not configured!")
            await self._send_response(
                command.get("channel_id"),
                "Latest articles feature not configured."
            )

    async def _handle_add_feed(self, command: Dict):
        """Handle adding a new feed"""
        text = command.get("text", "").strip()
        parts = text.split()

        if len(parts) < 2:
            await self._send_response(
                command.get("channel_id"),
                "Usage: /ai-news-add-feed <url> <name> [category]"
            )
            return

        url, name = parts[0], parts[1]
        category = parts[2] if len(parts) > 2 else "news"

        success, message = self.config_manager.add_feed(url, name, category)
        await self._send_response(command.get("channel_id"), message)

    async def _handle_remove_feed(self, command: Dict):
        """Handle removing a feed"""
        name = command.get("text", "").strip()

        if not name:
            await self._send_response(
                command.get("channel_id"),
                "Usage: /ai-news-remove-feed <name>"
            )
            return

        success, message = self.config_manager.remove_feed(name)
        await self._send_response(command.get("channel_id"), message)

    async def _handle_list_feeds(self, command: Dict):
        """Handle listing all feeds"""
        feeds = self.config_manager.list_feeds()

        if not feeds:
            await self._send_response(command.get("channel_id"), "No feeds configured.")
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

        async with self.rate_limiter:
            await self.web_client.chat_postMessage(
                channel=command.get("channel_id"),
                blocks=blocks,
                text="RSS Feeds List"
            )

    async def _handle_add_keyword(self, command: Dict):
        """Handle adding a keyword"""
        keyword = command.get("text", "").strip()

        if not keyword:
            await self._send_response(
                command.get("channel_id"),
                "Usage: /ai-news-add-keyword <keyword>"
            )
            return

        success, message = self.config_manager.add_keyword(keyword)
        await self._send_response(command.get("channel_id"), message)

    async def _handle_remove_keyword(self, command: Dict):
        """Handle removing a keyword"""
        keyword = command.get("text", "").strip()

        if not keyword:
            await self._send_response(
                command.get("channel_id"),
                "Usage: /ai-news-remove-keyword <keyword>"
            )
            return

        success, message = self.config_manager.remove_keyword(keyword)
        await self._send_response(command.get("channel_id"), message)

    async def _handle_list_keywords(self, command: Dict):
        """Handle listing keywords"""
        keywords = self.config_manager.list_keywords()

        if not keywords:
            await self._send_response(command.get("channel_id"), "No keywords configured.")
            return

        keyword_list = ", ".join(f"`{k}`" for k in keywords)
        await self._send_response(
            command.get("channel_id"),
            f"🔍 AI Keywords: {keyword_list}"
        )

    async def _handle_digest(self, command: Dict):
        """Handle digest configuration"""
        schedule = command.get("text", "").strip().lower()

        if schedule not in ["daily", "weekly", "off"]:
            await self._send_response(
                command.get("channel_id"),
                "Usage: /ai-news-digest <daily|weekly|off>"
            )
            return

        if self.set_digest_callback:
            await self.set_digest_callback(schedule)
            await self._send_response(
                command.get("channel_id"),
                f"✅ Digest schedule updated: {schedule}"
            )
        else:
            await self._send_response(
                command.get("channel_id"),
                "Digest feature not configured."
            )

    async def _handle_reload(self, command: Dict):
        """Handle configuration reload"""
        if self.reload_config_callback:
            await self.reload_config_callback()
            await self._send_response(
                command.get("channel_id"),
                "✅ Configuration reloaded successfully!"
            )
        else:
            await self._send_response(
                command.get("channel_id"),
                "Reload feature not configured."
            )

    async def _handle_interactive(self, req: SocketModeRequest):
        """Handle interactive components (buttons, etc.)"""
        payload = req.payload

        if payload.get("type") == "block_actions":
            await self._handle_block_action(payload)

    async def _handle_block_action(self, payload: Dict):
        """Handle block action (button clicks)"""
        user = payload["user"]["id"]
        actions = payload.get("actions", [])

        for action in actions:
            action_id = action.get("action_id", "")

            if action_id.startswith("feedback_"):
                parts = action_id.split("_", 2)
                if len(parts) == 3:
                    _, feedback_type, article_id = parts
                    is_positive = feedback_type == "positive"

                    # Record feedback to database if available, otherwise use file-based
                    if self.db_manager:
                        # Use database for feedback
                        asyncio.create_task(
                            self.db_manager.save_feedback(
                                article_id=article_id,
                                user_id=user,
                                is_positive=is_positive
                            )
                        )
                    else:
                        # Fall back to file-based feedback
                        self.feedback_manager.record_feedback(
                            article_id, user, is_positive
                        )

                    # Update message
                    channel = payload["channel"]["id"]
                    message_ts = payload["message"]["ts"]

                    await self._update_feedback_message(
                        channel, message_ts, user, is_positive
                    )

    async def _update_feedback_message(self, channel: str, message_ts: str, user: str, is_positive: bool):
        """Update message after feedback"""
        emoji = "👍" if is_positive else "👎"

        async with self.rate_limiter:
            await self.web_client.reactions_add(
                channel=channel,
                timestamp=message_ts,
                name="white_check_mark"
            )

    async def _send_response(self, channel: str, text: str):
        """Send a simple text response"""
        async with self.rate_limiter:
            await self.web_client.chat_postMessage(
                channel=channel,
                text=text
            )

    def format_article_block(self, article: Article) -> List[Dict]:
        """Format article as Slack blocks"""
        blocks = []

        # Title and link
        title_text = f"*<{article.link}|{article.title}>*"
        if article.feed_category:
            title_text = f"[{article.feed_category.value.upper()}] {title_text}"

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

        # Queue articles for posting
        for article in articles:
            await self.message_queue.put(article)

        # Process queue with rate limiting
        await self._process_message_queue()

    async def _process_message_queue(self):
        """Process queued messages with rate limiting"""
        batch_size = 5
        batch = []

        while not self.message_queue.empty():
            try:
                article = await asyncio.wait_for(
                    self.message_queue.get(),
                    timeout=0.1
                )
                batch.append(article)

                if len(batch) >= batch_size:
                    await self._post_batch(batch)
                    batch = []
                    await asyncio.sleep(1)  # Rate limiting delay
            except asyncio.TimeoutError:
                break

        # Post remaining articles
        if batch:
            await self._post_batch(batch)

    async def _post_batch(self, articles: List[Article]):
        """Post a batch of articles"""
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

        for article in articles:
            blocks.extend(self.format_article_block(article))

        # Remove last divider
        if blocks[-1].get("type") == "divider":
            blocks.pop()

        async with self.rate_limiter:
            try:
                await self.web_client.chat_postMessage(
                    channel=self.config.channel_id,
                    blocks=blocks,
                    text=f"AI News Update - {len(articles)} new articles"
                )
                logger.info(f"Posted batch of {len(articles)} articles")
            except Exception as e:
                logger.error(f"Error posting articles: {e}")

    async def start(self):
        """Start the async Slack bot"""
        logger.info("Starting async Slack bot...")

        try:
            # Start socket mode client
            await self.socket_client.connect()
            logger.info("Connected to Slack via Socket Mode")

            # Keep the bot running
            await asyncio.Future()  # Run forever

        except Exception as e:
            logger.error(f"Error in async Slack bot: {e}")
            raise

    async def stop(self):
        """Stop the async Slack bot"""
        logger.info("Stopping async Slack bot...")
        await self.socket_client.disconnect()