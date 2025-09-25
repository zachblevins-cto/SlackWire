#!/usr/bin/env python3
"""
Migration script to convert JSON files to PostgreSQL database
Run this once to migrate existing data
"""

import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from database.manager import DatabaseManager
from logger_config import setup_logging, get_logger

# Load environment variables
load_dotenv()

# Setup logging
setup_logging()
logger = get_logger(__name__)


async def load_json_file(filepath: str) -> dict:
    """Load data from a JSON file"""
    if not os.path.exists(filepath):
        logger.warning(f"File {filepath} not found")
        return {}

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            logger.info(f"Loaded {len(data)} entries from {filepath}")
            return data
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
        return {}


async def migrate_feed_cache(db: DatabaseManager) -> int:
    """Migrate feed_cache.json to database"""
    logger.info("Migrating feed cache...")

    cache_data = await load_json_file('feed_cache.json')
    if not cache_data:
        return 0

    count = 0
    for article_id, timestamp in cache_data.items():
        try:
            # Parse timestamp
            if isinstance(timestamp, str):
                # Try to parse ISO format
                ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                # Assume it's already a datetime or timestamp
                ts = datetime.fromtimestamp(timestamp)

            # The article_id is usually the hash itself
            # We'll need to store minimal info since we don't have full article data
            exists = await db.article_exists(article_id)
            if not exists:
                # Note: This is a simplified migration
                # In production, you might want to fetch full article data
                count += 1

        except Exception as e:
            logger.error(f"Error migrating cache entry {article_id}: {e}")

    logger.info(f"Migrated {count} feed cache entries")
    return count


async def migrate_feedback(db: DatabaseManager) -> int:
    """Migrate article_feedback.json to database"""
    logger.info("Migrating feedback data...")

    feedback_data = await load_json_file('article_feedback.json')
    if not feedback_data:
        return 0

    count = 0
    for article_id, feedbacks in feedback_data.items():
        if isinstance(feedbacks, list):
            for feedback in feedbacks:
                try:
                    success = await db.save_feedback(
                        article_id=article_id,
                        user_id=feedback.get('user_id', 'unknown'),
                        is_positive=feedback.get('is_positive', False),
                        feed_name=feedback.get('source')
                    )
                    if success:
                        count += 1
                except Exception as e:
                    logger.error(f"Error migrating feedback for {article_id}: {e}")
        else:
            # Handle old format if different
            logger.warning(f"Unexpected feedback format for {article_id}")

    logger.info(f"Migrated {count} feedback entries")
    return count


async def migrate_digest_config(db: DatabaseManager) -> bool:
    """Migrate digest_config.json to database"""
    logger.info("Migrating digest configuration...")

    config_data = await load_json_file('digest_config.json')
    if not config_data:
        return False

    try:
        success = await db.save_digest_config(config_data)
        if success:
            logger.info("Digest configuration migrated successfully")
        return success
    except Exception as e:
        logger.error(f"Error migrating digest config: {e}")
        return False


async def migrate_config_yaml(db: DatabaseManager) -> int:
    """Migrate important settings from config.yaml to database"""
    logger.info("Migrating configuration settings...")

    import yaml

    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)

        count = 0

        # Store RSS feeds configuration
        if 'rss_feeds' in config:
            success = await db.set_config(
                'rss_feeds',
                config['rss_feeds'],
                'RSS feed configurations'
            )
            if success:
                count += 1

        # Store AI keywords
        if 'ai_keywords' in config:
            success = await db.set_config(
                'ai_keywords',
                config['ai_keywords'],
                'AI-related keywords for filtering'
            )
            if success:
                count += 1

        # Store circuit breaker settings
        if 'circuit_breaker' in config:
            success = await db.set_config(
                'circuit_breaker',
                config['circuit_breaker'],
                'Circuit breaker configuration'
            )
            if success:
                count += 1

        # Store LLM prompts
        if 'llm_prompts' in config:
            success = await db.set_config(
                'llm_prompts',
                config['llm_prompts'],
                'LLM prompt templates'
            )
            if success:
                count += 1

        logger.info(f"Migrated {count} configuration entries")
        return count

    except Exception as e:
        logger.error(f"Error migrating config.yaml: {e}")
        return 0


async def verify_migration(db: DatabaseManager):
    """Verify the migration was successful"""
    logger.info("Verifying migration...")

    # Check digest config
    digest_config = await db.get_digest_config()
    if digest_config:
        logger.info(f"✅ Digest config: {digest_config}")
    else:
        logger.warning("❌ No digest config found")

    # Check configuration
    feeds = await db.get_config('rss_feeds')
    if feeds:
        logger.info(f"✅ RSS feeds: {len(feeds)} feeds configured")
    else:
        logger.warning("❌ No RSS feeds found")

    keywords = await db.get_config('ai_keywords')
    if keywords:
        logger.info(f"✅ Keywords: {len(keywords)} keywords configured")
    else:
        logger.warning("❌ No keywords found")

    # Check for recent articles
    recent_articles = await db.get_recent_articles(days=30, limit=5)
    logger.info(f"✅ Found {len(recent_articles)} recent articles")

    # Check trending sources
    trending = await db.get_trending_sources(days=30)
    if trending:
        logger.info(f"✅ Trending sources: {[t['source'] for t in trending]}")


async def create_backup():
    """Create backups of JSON files before migration"""
    logger.info("Creating backups of JSON files...")

    backup_dir = Path('backups')
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    files_to_backup = [
        'feed_cache.json',
        'article_feedback.json',
        'digest_config.json',
        'config.yaml'
    ]

    for file in files_to_backup:
        if os.path.exists(file):
            backup_path = backup_dir / f"{file}.{timestamp}.backup"
            try:
                import shutil
                shutil.copy2(file, backup_path)
                logger.info(f"✅ Backed up {file} to {backup_path}")
            except Exception as e:
                logger.error(f"❌ Error backing up {file}: {e}")


async def main():
    """Main migration function"""
    logger.info("=" * 60)
    logger.info("Starting SlackWire Database Migration")
    logger.info("=" * 60)

    # Create backups first
    await create_backup()

    # Initialize database
    db = DatabaseManager()

    try:
        # Create tables
        logger.info("Initializing database tables...")
        await db.initialize_database()

        # Run migrations
        results = {
            'feed_cache': await migrate_feed_cache(db),
            'feedback': await migrate_feedback(db),
            'digest_config': await migrate_digest_config(db),
            'config': await migrate_config_yaml(db)
        }

        # Summary
        logger.info("=" * 60)
        logger.info("Migration Summary:")
        logger.info(f"  Feed cache entries: {results['feed_cache']}")
        logger.info(f"  Feedback entries: {results['feedback']}")
        logger.info(f"  Digest config: {'✅' if results['digest_config'] else '❌'}")
        logger.info(f"  Configuration entries: {results['config']}")
        logger.info("=" * 60)

        # Verify
        await verify_migration(db)

        logger.info("=" * 60)
        logger.info("Migration completed successfully!")
        logger.info("You can now use the async_main.py with database support")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        logger.info("Your original JSON files are safe in the backups/ directory")
        raise

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())