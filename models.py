"""Data models for SlackWire application."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


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


@dataclass
class Article:
    """Represents an article from an RSS feed."""
    id: str
    title: str
    link: str
    feed_name: str
    summary: str = ""
    published: Optional[datetime] = None
    category: FeedCategory = FeedCategory.GENERAL
    ai_summary: Optional[str] = None
    priority_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'title': self.title,
            'link': self.link,
            'summary': self.summary,
            'published': self.published.isoformat() if self.published else None,
            'feed_name': self.feed_name,
            'category': self.category.value,
            'ai_summary': self.ai_summary,
            'priority_score': self.priority_score
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Article':
        """Create from dictionary."""
        published = None
        if data.get('published'):
            if isinstance(data['published'], str):
                published = datetime.fromisoformat(data['published'])
            elif isinstance(data['published'], datetime):
                published = data['published']

        return cls(
            id=data['id'],
            title=data['title'],
            link=data['link'],
            summary=data.get('summary', ''),
            published=published,
            feed_name=data['feed_name'],
            category=FeedCategory(data.get('category', 'general')),
            ai_summary=data.get('ai_summary'),
            priority_score=data.get('priority_score', 0.0)
        )


@dataclass
class RSSFeed:
    """Configuration for an RSS feed."""
    url: str
    name: str
    category: FeedCategory = FeedCategory.GENERAL
    enabled: bool = True
    last_fetched: Optional[datetime] = None
    error_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            'url': self.url,
            'name': self.name,
            'category': self.category.value,
            'enabled': self.enabled
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RSSFeed':
        """Create from dictionary."""
        return cls(
            url=data['url'],
            name=data['name'],
            category=FeedCategory(data.get('category', 'general')),
            enabled=data.get('enabled', True)
        )


@dataclass
class FeedbackEntry:
    """User feedback for an article."""
    article_id: str
    source: str
    is_interesting: bool
    timestamp: datetime = field(default_factory=datetime.now)
    user_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'article_id': self.article_id,
            'source': self.source,
            'is_interesting': self.is_interesting,
            'timestamp': self.timestamp.isoformat(),
            'user_id': self.user_id
        }


@dataclass
class DigestConfig:
    """Configuration for digest notifications."""
    enabled: bool = False
    schedule: Optional[DigestSchedule] = None
    time: str = "09:00"
    last_sent: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'enabled': self.enabled,
            'schedule': self.schedule.value if self.schedule else None,
            'time': self.time,
            'last_sent': self.last_sent.isoformat() if self.last_sent else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DigestConfig':
        """Create from dictionary."""
        return cls(
            enabled=data.get('enabled', False),
            schedule=DigestSchedule(data['schedule']) if data.get('schedule') else None,
            time=data.get('time', '09:00'),
            last_sent=datetime.fromisoformat(data['last_sent']) if data.get('last_sent') else None
        )


@dataclass
class SlackMessage:
    """Represents a Slack message to be posted."""
    channel_id: str
    text: str
    blocks: Optional[List[Dict[str, Any]]] = None
    thread_ts: Optional[str] = None

    def to_api_params(self) -> Dict[str, Any]:
        """Convert to Slack API parameters."""
        params = {
            'channel': self.channel_id,
            'text': self.text
        }
        if self.blocks:
            params['blocks'] = self.blocks
        if self.thread_ts:
            params['thread_ts'] = self.thread_ts
        return params