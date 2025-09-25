"""
Async Database Manager for SlackWire
Handles all database operations with PostgreSQL
"""

import os
import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update, delete, and_, or_, func, Integer
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.pool import NullPool

from .models import (
    Base, ArticleDB, FeedCacheDB, FeedbackDB,
    DigestConfigDB, ConfigDB, MetricsDB
)
from models_v2 import Article
from logger_config import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """Async database manager for all SlackWire data operations"""

    def __init__(self, database_url: Optional[str] = None):
        """Initialize database manager with connection string"""
        if not database_url:
            # Support both PostgreSQL and SQLite (for development)
            database_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://localhost/slackwire')

        # Convert postgres:// to postgresql:// for compatibility
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)

        # Ensure async driver
        if 'postgresql://' in database_url and '+asyncpg' not in database_url:
            database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://')

        self.engine = create_async_engine(
            database_url,
            echo=os.getenv('DATABASE_ECHO', 'false').lower() == 'true',
            poolclass=NullPool,  # Better for async operations
            future=True
        )

        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        logger.info(f"Database manager initialized with {database_url.split('@')[-1]}")

    async def initialize_database(self):
        """Create all tables if they don't exist"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialized")

    async def close(self):
        """Close database connections"""
        await self.engine.dispose()
        logger.info("Database connections closed")

    @asynccontextmanager
    async def get_session(self):
        """Get an async database session"""
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # Article operations

    async def save_article(self, article: Article) -> bool:
        """Save an article to the database"""
        async with self.get_session() as session:
            try:
                # Generate hash for deduplication
                article_hash = hashlib.md5(
                    f"{article.title}{article.link}".encode()
                ).hexdigest()

                # Check if article already exists
                stmt = select(ArticleDB).where(ArticleDB.article_hash == article_hash)
                existing = await session.execute(stmt)
                if existing.scalar_one_or_none():
                    return False

                # Create new article
                # Use category field, as feed_category might not be set
                feed_cat = getattr(article, 'feed_category', None) or article.category
                db_article = ArticleDB(
                    article_hash=article_hash,
                    title=article.title,
                    link=str(article.link),
                    feed_name=article.feed_name,
                    feed_category=article.category,
                    summary=article.summary or '',
                    ai_summary=article.ai_summary,
                    published=article.published,
                    priority_score=article.priority_score,
                    article_metadata={'feed_category': feed_cat} if feed_cat else None
                )

                session.add(db_article)
                await session.flush()

                # Also add to cache
                cache_entry = FeedCacheDB(
                    article_hash=article_hash,
                    feed_name=article.feed_name,
                    title=article.title,
                    link=str(article.link),
                    posted_to_slack=True,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=7)
                )
                session.add(cache_entry)

                return True

            except Exception as e:
                logger.error(f"Error saving article: {e}")
                return False

    async def get_recent_articles(self, days: int = 7, limit: int = 100) -> List[ArticleDB]:
        """Get recent articles from the database"""
        async with self.get_session() as session:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            stmt = (
                select(ArticleDB)
                .where(ArticleDB.published >= cutoff_date)
                .order_by(ArticleDB.published.desc())
                .limit(limit)
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def article_exists(self, article_id: str) -> bool:
        """Check if an article already exists in cache"""
        async with self.get_session() as session:
            # Generate hash
            article_hash = hashlib.md5(article_id.encode()).hexdigest()

            stmt = select(FeedCacheDB).where(
                FeedCacheDB.article_hash == article_hash
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def bulk_check_articles(self, article_ids: List[str]) -> Dict[str, bool]:
        """Check multiple articles at once for efficiency"""
        async with self.get_session() as session:
            # Generate hashes
            hashes = {
                aid: hashlib.md5(aid.encode()).hexdigest()
                for aid in article_ids
            }

            stmt = select(FeedCacheDB.article_hash).where(
                FeedCacheDB.article_hash.in_(list(hashes.values()))
            )

            result = await session.execute(stmt)
            existing_hashes = {row[0] for row in result}

            return {
                aid: hashes[aid] in existing_hashes
                for aid in article_ids
            }

    # Feedback operations

    async def save_feedback(
        self,
        article_id: str,
        user_id: str,
        is_positive: bool,
        feed_name: Optional[str] = None
    ) -> bool:
        """Save user feedback for an article"""
        async with self.get_session() as session:
            try:
                # Convert article_id to UUID if it's a hash
                if not self._is_uuid(article_id):
                    # Look up article by hash
                    stmt = select(ArticleDB).where(ArticleDB.article_hash == article_id)
                    result = await session.execute(stmt)
                    article = result.scalar_one_or_none()
                    if not article:
                        return False
                    article_uuid = article.id
                else:
                    article_uuid = uuid.UUID(article_id)

                # Upsert feedback
                stmt = insert(FeedbackDB).values(
                    article_id=article_uuid,
                    user_id=user_id,
                    is_positive=is_positive,
                    feed_name=feed_name,
                    feedback_metadata={'timestamp': datetime.now(timezone.utc).isoformat()}
                )

                stmt = stmt.on_conflict_do_update(
                    constraint='unique_user_article_feedback',
                    set_=dict(
                        is_positive=is_positive,
                        timestamp=func.now()
                    )
                )

                await session.execute(stmt)
                return True

            except Exception as e:
                logger.error(f"Error saving feedback: {e}")
                return False

    async def get_article_feedback_stats(self, article_id: str) -> Tuple[int, int]:
        """Get positive and negative feedback counts for an article"""
        async with self.get_session() as session:
            # Convert to UUID if needed
            if not self._is_uuid(article_id):
                stmt = select(ArticleDB.id).where(ArticleDB.article_hash == article_id)
                result = await session.execute(stmt)
                article_uuid = result.scalar_one_or_none()
                if not article_uuid:
                    return 0, 0
            else:
                article_uuid = uuid.UUID(article_id)

            # Count feedback
            stmt = select(
                func.count(FeedbackDB.id).filter(FeedbackDB.is_positive == True),
                func.count(FeedbackDB.id).filter(FeedbackDB.is_positive == False)
            ).where(FeedbackDB.article_id == article_uuid)

            result = await session.execute(stmt)
            positive, negative = result.first() or (0, 0)
            return positive, negative

    async def get_trending_sources(self, days: int = 7, limit: int = 5) -> List[Dict[str, Any]]:
        """Get trending sources based on feedback"""
        async with self.get_session() as session:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            stmt = (
                select(
                    FeedbackDB.feed_name,
                    func.count(FeedbackDB.id).label('total'),
                    func.sum(func.cast(FeedbackDB.is_positive, Integer)).label('positive')
                )
                .where(
                    and_(
                        FeedbackDB.timestamp >= cutoff_date,
                        FeedbackDB.feed_name.isnot(None)
                    )
                )
                .group_by(FeedbackDB.feed_name)
                .having(func.count(FeedbackDB.id) >= 3)  # Min 3 feedbacks
                .order_by(func.sum(func.cast(FeedbackDB.is_positive, Integer)).desc())
                .limit(limit)
            )

            result = await session.execute(stmt)

            trending = []
            for row in result:
                feed_name, total, positive = row
                ratio = positive / total if total > 0 else 0
                trending.append({
                    'source': feed_name,
                    'ratio': ratio,
                    'total': total,
                    'positive': positive
                })

            return trending

    # Digest configuration

    async def get_digest_config(self) -> Optional[Dict[str, Any]]:
        """Get digest configuration"""
        async with self.get_session() as session:
            stmt = select(DigestConfigDB).where(DigestConfigDB.id == 1)
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if config:
                return config.to_dict()
            return None

    async def save_digest_config(self, config: Dict[str, Any]) -> bool:
        """Save digest configuration"""
        async with self.get_session() as session:
            try:
                stmt = insert(DigestConfigDB).values(
                    id=1,
                    enabled=config.get('enabled', False),
                    schedule=config.get('schedule'),
                    time=config.get('time', '09:00'),
                    recipients=config.get('recipients'),
                    settings=config.get('settings')
                )

                stmt = stmt.on_conflict_do_update(
                    constraint=DigestConfigDB.__table__.primary_key,
                    set_=dict(
                        enabled=config.get('enabled', False),
                        schedule=config.get('schedule'),
                        time=config.get('time', '09:00'),
                        recipients=config.get('recipients'),
                        settings=config.get('settings'),
                        updated_at=func.now()
                    )
                )

                await session.execute(stmt)
                return True

            except Exception as e:
                logger.error(f"Error saving digest config: {e}")
                return False

    async def update_digest_last_sent(self) -> bool:
        """Update the last sent timestamp for digest"""
        async with self.get_session() as session:
            try:
                stmt = (
                    update(DigestConfigDB)
                    .where(DigestConfigDB.id == 1)
                    .values(last_sent=func.now())
                )
                await session.execute(stmt)
                return True
            except Exception as e:
                logger.error(f"Error updating digest last sent: {e}")
                return False

    # Configuration storage

    async def get_config(self, key: str) -> Optional[Any]:
        """Get a configuration value"""
        async with self.get_session() as session:
            stmt = select(ConfigDB).where(ConfigDB.key == key)
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if config:
                return config.value
            return None

    async def set_config(self, key: str, value: Any, description: str = None) -> bool:
        """Set a configuration value"""
        async with self.get_session() as session:
            try:
                stmt = insert(ConfigDB).values(
                    key=key,
                    value=value,
                    description=description
                )

                stmt = stmt.on_conflict_do_update(
                    constraint=ConfigDB.__table__.primary_key,
                    set_=dict(
                        value=value,
                        updated_at=func.now()
                    )
                )

                await session.execute(stmt)
                return True

            except Exception as e:
                logger.error(f"Error setting config {key}: {e}")
                return False

    # Metrics operations

    async def record_metric(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Record a metric value"""
        async with self.get_session() as session:
            try:
                metric = MetricsDB(
                    metric_name=name,
                    metric_value=value,
                    labels=labels
                )
                session.add(metric)
                return True

            except Exception as e:
                logger.error(f"Error recording metric {name}: {e}")
                return False

    async def get_metrics(
        self,
        name: str,
        hours: int = 24,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get recent metrics"""
        async with self.get_session() as session:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

            stmt = (
                select(MetricsDB)
                .where(
                    and_(
                        MetricsDB.metric_name == name,
                        MetricsDB.timestamp >= cutoff_time
                    )
                )
                .order_by(MetricsDB.timestamp.desc())
                .limit(limit)
            )

            result = await session.execute(stmt)
            metrics = result.scalars().all()

            return [
                {
                    'name': m.metric_name,
                    'value': m.metric_value,
                    'labels': m.labels,
                    'timestamp': m.timestamp.isoformat()
                }
                for m in metrics
            ]

    # Cache cleanup

    async def clean_expired_cache(self) -> int:
        """Remove expired cache entries"""
        async with self.get_session() as session:
            try:
                stmt = (
                    delete(FeedCacheDB)
                    .where(
                        and_(
                            FeedCacheDB.expires_at.isnot(None),
                            FeedCacheDB.expires_at < func.now()
                        )
                    )
                )

                result = await session.execute(stmt)
                deleted_count = result.rowcount

                if deleted_count > 0:
                    logger.info(f"Cleaned {deleted_count} expired cache entries")

                return deleted_count

            except Exception as e:
                logger.error(f"Error cleaning cache: {e}")
                return 0

    # Migration helpers

    async def migrate_from_json(
        self,
        feed_cache_json: Optional[Dict] = None,
        feedback_json: Optional[Dict] = None,
        digest_config_json: Optional[Dict] = None
    ) -> Dict[str, int]:
        """Migrate data from JSON files to database"""
        results = {
            'cache_entries': 0,
            'feedback_entries': 0,
            'digest_config': 0
        }

        # Migrate feed cache
        if feed_cache_json:
            for article_id, timestamp in feed_cache_json.items():
                try:
                    cache_entry = FeedCacheDB(
                        article_hash=hashlib.md5(article_id.encode()).hexdigest(),
                        feed_name='unknown',  # Will need to be updated
                        title='',  # Will need to be updated
                        link='',  # Will need to be updated
                        first_seen=datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp,
                        posted_to_slack=True
                    )
                    async with self.get_session() as session:
                        session.add(cache_entry)
                    results['cache_entries'] += 1
                except Exception as e:
                    logger.error(f"Error migrating cache entry {article_id}: {e}")

        # Migrate feedback
        if feedback_json:
            for article_id, feedbacks in feedback_json.items():
                for feedback in feedbacks:
                    try:
                        await self.save_feedback(
                            article_id=article_id,
                            user_id=feedback.get('user_id', 'unknown'),
                            is_positive=feedback.get('is_positive', False),
                            feed_name=feedback.get('source')
                        )
                        results['feedback_entries'] += 1
                    except Exception as e:
                        logger.error(f"Error migrating feedback for {article_id}: {e}")

        # Migrate digest config
        if digest_config_json:
            if await self.save_digest_config(digest_config_json):
                results['digest_config'] = 1

        logger.info(f"Migration completed: {results}")
        return results

    def _is_uuid(self, value: str) -> bool:
        """Check if a string is a valid UUID"""
        try:
            uuid.UUID(value)
            return True
        except (ValueError, AttributeError):
            return False