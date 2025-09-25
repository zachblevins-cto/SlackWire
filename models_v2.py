"""Enhanced data models with Pydantic validation for SlackWire application."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class FeedCategory(str, Enum):
    """Categories for RSS feeds."""
    ACADEMIC = "academic"
    COMPANY = "company"
    NEWS = "news"
    GENERAL = "general"


class DigestSchedule(str, Enum):
    """Digest scheduling options."""
    DAILY = "daily"
    WEEKLY = "weekly"
    OFF = "off"


class SlackConfig(BaseModel):
    """Slack bot configuration with validation."""
    bot_token: str = Field(..., min_length=1, pattern="^xoxb-", description="Slack bot OAuth token")
    app_token: str = Field(..., min_length=1, pattern="^xapp-", description="Slack app token for Socket Mode")
    channel_id: str = Field(..., min_length=1, pattern="^[CG][A-Z0-9]+", description="Slack channel ID")

    @field_validator('bot_token', 'app_token')
    @classmethod
    def validate_token(cls, v: str) -> str:
        """Ensure tokens are properly formatted."""
        if not v or v == "your-token-here":
            raise ValueError("Invalid Slack token")
        return v


class Article(BaseModel):
    """Represents an article from an RSS feed with validation."""
    id: str = Field(..., min_length=1, description="Unique article identifier")
    title: str = Field(..., min_length=1, max_length=500, description="Article title")
    link: HttpUrl = Field(..., description="Article URL")
    feed_name: str = Field(..., min_length=1, description="Source feed name")
    summary: str = Field(default="", max_length=2000, description="Article summary")
    published: Optional[datetime] = Field(default=None, description="Publication date")
    category: FeedCategory = Field(default=FeedCategory.GENERAL, description="Feed category")
    feed_category: Optional[FeedCategory] = Field(default=None, description="Feed category for display")
    ai_summary: Optional[str] = Field(default=None, max_length=1000, description="AI-generated summary")
    priority_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Priority score")

    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            HttpUrl: lambda v: str(v)
        }

    @field_validator('title', 'summary')
    @classmethod
    def clean_text(cls, v: str) -> str:
        """Remove excessive whitespace and newlines."""
        if v:
            return ' '.join(v.split())
        return v

    @field_validator('published')
    @classmethod
    def ensure_timezone(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Ensure datetime has timezone info."""
        if v and v.tzinfo is None:
            from datetime import timezone
            return v.replace(tzinfo=timezone.utc)
        return v

    def to_slack_block(self) -> List[Dict[str, Any]]:
        """Generate Slack block format for this article."""
        blocks = []

        # Title and link
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*<{self.link}|{self.title}>*"
            }
        })

        # Summary or AI summary
        summary_text = self.ai_summary or self.summary
        if summary_text:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{'🤖 ' if self.ai_summary else ''}{summary_text[:500]}"
                }
            })

        # Metadata
        published_str = self.published.strftime('%Y-%m-%d %H:%M UTC') if self.published else 'Unknown date'
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"📰 {self.feed_name} | 🏷️ {self.category} | 📅 {published_str}"
            }]
        })

        blocks.append({"type": "divider"})
        return blocks


class RSSFeed(BaseModel):
    """Configuration for an RSS feed with validation."""
    url: HttpUrl = Field(..., description="RSS feed URL")
    name: str = Field(..., min_length=1, max_length=100, description="Feed name")
    category: FeedCategory = Field(default=FeedCategory.GENERAL, description="Feed category")
    enabled: bool = Field(default=True, description="Whether feed is active")
    last_fetched: Optional[datetime] = Field(default=None, description="Last successful fetch")
    error_count: int = Field(default=0, ge=0, description="Consecutive error count")

    class Config:
        use_enum_values = True

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name doesn't contain special characters."""
        import re
        if not re.match(r'^[\w\s\-\.]+$', v):
            raise ValueError('Feed name can only contain letters, numbers, spaces, hyphens, and dots')
        return v

    @model_validator(mode='after')
    def check_error_threshold(self):
        """Disable feed if too many errors."""
        if self.error_count > 10:
            self.enabled = False
        return self


class FeedbackEntry(BaseModel):
    """User feedback for an article with validation."""
    article_id: str = Field(..., min_length=1, description="Article ID")
    source: str = Field(..., min_length=1, description="Source feed name")
    is_interesting: bool = Field(..., description="Whether article is interesting")
    timestamp: datetime = Field(default_factory=datetime.now, description="Feedback timestamp")
    user_id: Optional[str] = Field(default=None, max_length=50, description="User identifier")

    @field_validator('timestamp')
    @classmethod
    def ensure_timezone(cls, v: datetime) -> datetime:
        """Ensure datetime has timezone info."""
        if v and v.tzinfo is None:
            from datetime import timezone
            return v.replace(tzinfo=timezone.utc)
        return v


class DigestConfig(BaseModel):
    """Configuration for digest notifications with validation."""
    enabled: bool = Field(default=False, description="Whether digest is enabled")
    schedule: Optional[DigestSchedule] = Field(default=None, description="Digest schedule")
    time: str = Field(default="09:00", pattern=r'^\d{2}:\d{2}$', description="Time in HH:MM format")
    last_sent: Optional[datetime] = Field(default=None, description="Last digest sent time")

    @field_validator('time')
    @classmethod
    def validate_time(cls, v: str) -> str:
        """Validate time format."""
        try:
            hour, minute = map(int, v.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError('Time must be in HH:MM format (00:00 to 23:59)')
        return v

    @model_validator(mode='after')
    def check_schedule_consistency(self):
        """Ensure schedule is set when enabled."""
        if self.enabled and not self.schedule:
            raise ValueError('Schedule must be set when digest is enabled')
        return self


class SlackMessage(BaseModel):
    """Represents a Slack message to be posted with validation."""
    channel_id: str = Field(..., pattern=r'^[CG][A-Z0-9]+$', description="Slack channel ID")
    text: str = Field(..., min_length=1, max_length=40000, description="Message text")
    blocks: Optional[List[Dict[str, Any]]] = Field(default=None, max_items=50, description="Slack blocks")
    thread_ts: Optional[str] = Field(default=None, description="Thread timestamp")

    @field_validator('blocks')
    @classmethod
    def validate_blocks(cls, v: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """Validate Slack blocks structure."""
        if v:
            for block in v:
                if 'type' not in block:
                    raise ValueError('Each block must have a type')
        return v


class AppConfig(BaseModel):
    """Application configuration with validation."""
    rss_feeds: List[RSSFeed] = Field(default_factory=list, description="RSS feed configurations")
    ai_keywords: List[str] = Field(default_factory=list, description="AI-related keywords")
    check_interval_minutes: int = Field(default=30, ge=1, le=1440, description="Feed check interval")
    max_articles_per_update: int = Field(default=10, ge=1, le=50, description="Max articles per update")
    cache_expiry_days: int = Field(default=7, ge=1, le=30, description="Cache expiry in days")

    class Config:
        use_enum_values = True

    @field_validator('ai_keywords')
    @classmethod
    def clean_keywords(cls, v: List[str]) -> List[str]:
        """Clean and deduplicate keywords."""
        return list(set(k.strip().lower() for k in v if k.strip()))

    @field_validator('rss_feeds')
    @classmethod
    def unique_feed_names(cls, v: List[RSSFeed]) -> List[RSSFeed]:
        """Ensure feed names are unique."""
        names = [feed.name for feed in v]
        if len(names) != len(set(names)):
            raise ValueError('Feed names must be unique')
        return v


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration with validation."""
    failure_threshold: int = Field(default=5, ge=1, le=20, description="Failure threshold")
    recovery_timeout: int = Field(default=60, ge=10, le=600, description="Recovery timeout in seconds")
    half_open_max_calls: int = Field(default=3, ge=1, le=10, description="Max calls in half-open state")

    @model_validator(mode='after')
    def validate_recovery_timeout(self):
        """Ensure recovery timeout is reasonable."""
        if self.recovery_timeout < self.failure_threshold * 5:
            self.recovery_timeout = self.failure_threshold * 10
        return self