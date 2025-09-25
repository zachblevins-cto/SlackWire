"""
SQLAlchemy database models for SlackWire
PostgreSQL database models with async support
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, Text, DateTime, Boolean,
    Float, Integer, Index, UniqueConstraint, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class ArticleDB(Base):
    """Article database model"""
    __tablename__ = 'articles'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_hash = Column(String(255), unique=True, nullable=False)  # Hash for deduplication
    title = Column(String(500), nullable=False)
    link = Column(Text, nullable=False, unique=True)
    feed_name = Column(String(255), nullable=False)
    feed_category = Column(String(50), default='general')
    summary = Column(Text, default='')
    ai_summary = Column(Text, nullable=True)
    published = Column(TIMESTAMP(timezone=True), nullable=True)
    priority_score = Column(Float, default=0.0)
    article_metadata = Column(JSONB, nullable=True)  # PostgreSQL JSONB for flexible metadata
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())

    # Indexes for common queries
    __table_args__ = (
        Index('idx_published', 'published'),
        Index('idx_feed_name', 'feed_name'),
        Index('idx_priority', 'priority_score'),
        Index('idx_created', 'created_at'),
    )

    def to_dict(self):
        """Convert to dictionary for compatibility"""
        return {
            'id': str(self.id),
            'article_hash': self.article_hash,
            'title': self.title,
            'link': self.link,
            'feed_name': self.feed_name,
            'feed_category': self.feed_category,
            'summary': self.summary,
            'ai_summary': self.ai_summary,
            'published': self.published.isoformat() if self.published else None,
            'priority_score': self.priority_score,
            'metadata': self.article_metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class FeedCacheDB(Base):
    """Feed cache database model - replaces feed_cache.json"""
    __tablename__ = 'feed_cache'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_hash = Column(String(255), unique=True, nullable=False)
    feed_name = Column(String(255), nullable=False)
    title = Column(String(500), nullable=False)
    link = Column(Text, nullable=False)
    first_seen = Column(TIMESTAMP(timezone=True), server_default=func.now())
    last_seen = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    posted_to_slack = Column(Boolean, default=False)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=True)  # For cache expiration

    # Indexes
    __table_args__ = (
        Index('idx_feed_cache_feed', 'feed_name'),
        Index('idx_feed_cache_seen', 'first_seen'),
        Index('idx_feed_cache_posted', 'posted_to_slack'),
        Index('idx_feed_cache_hash', 'article_hash'),
        Index('idx_feed_cache_expires', 'expires_at'),
    )


class FeedbackDB(Base):
    """Article feedback database model - replaces article_feedback.json"""
    __tablename__ = 'feedback'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(String(255), nullable=False)
    is_positive = Column(Boolean, nullable=False)
    feed_name = Column(String(255), nullable=True)
    feedback_metadata = Column(JSONB, nullable=True)  # Store additional context
    timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Ensure one feedback per user per article
    __table_args__ = (
        UniqueConstraint('article_id', 'user_id', name='unique_user_article_feedback'),
        Index('idx_feedback_article', 'article_id'),
        Index('idx_feedback_user', 'user_id'),
        Index('idx_feedback_feed', 'feed_name'),
        Index('idx_feedback_time', 'timestamp'),
    )


class DigestConfigDB(Base):
    """Digest configuration database model - replaces digest_config.json"""
    __tablename__ = 'digest_config'

    id = Column(Integer, primary_key=True, default=1)  # Single row table
    enabled = Column(Boolean, default=False)
    schedule = Column(String(20), nullable=True)  # 'daily', 'weekly', or null
    time = Column(String(10), default='09:00')  # HH:MM format
    last_sent = Column(TIMESTAMP(timezone=True), nullable=True)
    recipients = Column(JSONB, nullable=True)  # Future: multiple recipients
    settings = Column(JSONB, nullable=True)  # Additional settings
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())

    def to_dict(self):
        """Convert to dictionary for compatibility"""
        return {
            'enabled': self.enabled,
            'schedule': self.schedule,
            'time': self.time,
            'last_sent': self.last_sent.isoformat() if self.last_sent else None,
            'recipients': self.recipients
        }


class ConfigDB(Base):
    """General configuration storage"""
    __tablename__ = 'config'

    key = Column(String(100), primary_key=True)
    value = Column(JSONB, nullable=False)  # PostgreSQL JSONB for better query performance
    description = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())


class MetricsDB(Base):
    """Metrics storage for monitoring"""
    __tablename__ = 'metrics'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    labels = Column(JSONB, nullable=True)  # Additional labels/tags with JSONB
    timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_metrics_name', 'metric_name'),
        Index('idx_metrics_time', 'timestamp'),
    )