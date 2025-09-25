import asyncio
import aiohttp
import feedparser
from datetime import datetime, timezone, timedelta
from dateutil import parser as date_parser
from typing import List, Dict, Optional, Any
import hashlib
import json
import os
import yaml
import time
from bs4 import BeautifulSoup

from logger_config import get_logger
from utils.file_lock import atomic_json_file, safe_json_read, safe_json_write
from utils.cache_manager import CacheManager
from models import Article, RSSFeed, FeedCategory
from circuit_breaker import CircuitBreaker, CircuitBreakerConfig

logger = get_logger(__name__)


class AsyncRSSParser:
    def __init__(self, cache_file: str = "feed_cache.json", config_file: str = "config.yaml"):
        self.cache_file: str = cache_file
        self.config_file: str = config_file
        self.config: Dict[str, Any] = self._load_config()
        self.seen_entries: Dict[str, datetime] = self._load_cache()
        # Initialize circuit breakers per domain
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(self.config_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            # Fall back to default config
            return {
                'rss_feeds': [],
                'ai_keywords': [],
                'rss_fetch': {
                    'timeout': 30,
                    'max_retries': 3,
                    'retry_delay': 5
                }
            }
    
    def _load_cache(self) -> Dict[str, datetime]:
        """Load previously seen entries from cache"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                    # Convert string dates back to datetime objects
                    return {
                        k: datetime.fromisoformat(v) 
                        for k, v in cache_data.items()
                    }
            except Exception as e:
                logger.error(f"Error loading cache: {e}")
        return {}
    
    def _save_cache(self) -> None:
        """Save seen entries to cache"""
        try:
            cache_data = {
                k: v.isoformat() 
                for k, v in self.seen_entries.items()
            }
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def _generate_entry_id(self, entry: Dict[str, Any]) -> str:
        """Generate unique ID for an entry"""
        # Use combination of title and link for uniqueness
        content = f"{entry.get('title', '')}{entry.get('link', '')}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _parse_published_date(self, entry: Any) -> Optional[datetime]:
        """Parse various date formats from RSS entries"""
        date_fields = ['published_parsed', 'updated_parsed', 'created_parsed']
        
        for field in date_fields:
            if hasattr(entry, field) and getattr(entry, field):
                try:
                    time_struct = getattr(entry, field)
                    return datetime.fromtimestamp(
                        feedparser._parse_date(time_struct), 
                        tz=timezone.utc
                    )
                except:
                    continue
        
        # Try parsing string dates
        date_strings = ['published', 'updated', 'created']
        for field in date_strings:
            if hasattr(entry, field) and getattr(entry, field):
                try:
                    return date_parser.parse(getattr(entry, field))
                except:
                    continue
        
        return None
    
    def _get_circuit_breaker(self, url: str) -> CircuitBreaker:
        """Get or create circuit breaker for a domain."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        if domain not in self.circuit_breakers:
            cb_config = self.config.get('circuit_breaker', {})
            config = CircuitBreakerConfig(
                failure_threshold=cb_config.get('failure_threshold', 5),
                recovery_timeout=cb_config.get('recovery_timeout', 60),
                exception_types=(aiohttp.ClientError,)
            )
            self.circuit_breakers[domain] = CircuitBreaker(config)
        return self.circuit_breakers[domain]

    async def _fetch_feed_with_retry(self, session: aiohttp.ClientSession,
                                   feed_url: str, feed_name: str) -> Optional[bytes]:
        """Fetch RSS feed with retry logic and circuit breaker."""
        fetch_config = self.config.get('rss_fetch', {})
        timeout = fetch_config.get('timeout', 30)
        max_retries = fetch_config.get('max_retries', 3)
        retry_delay = fetch_config.get('retry_delay', 5)

        headers = {'User-Agent': 'SlackWire RSS Bot 1.0'}
        circuit_breaker = self._get_circuit_breaker(feed_url)

        for attempt in range(max_retries):
            try:
                # Check circuit breaker state
                if circuit_breaker.state == 'open':
                    logger.warning(f"Circuit breaker open for {feed_name}, skipping")
                    return None

                logger.info(f"Fetching feed: {feed_name} (attempt {attempt + 1}/{max_retries})")

                # Circuit breaker doesn't support async directly, check state only
                async with session.get(feed_url, headers=headers,
                                     timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    if response.status == 200:
                        circuit_breaker.record_success()
                        return await response.read()
                    else:
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status
                        )
                    
                    # This block is now handled in the fetch() function above
                    pass
                        
            except aiohttp.ClientResponseError as e:
                if e.status == 404:
                    logger.error(f"Feed not found (404): {feed_name} at {feed_url}")
                    return None
                elif e.status in [429, 503]:
                    logger.warning(f"HTTP {e.status} for {feed_name}")
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt) * (2 if e.status == 429 else 1)
                        logger.info(f"Waiting {wait_time} seconds before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                else:
                    logger.warning(f"HTTP {e.status} for {feed_name}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching {feed_name}")
                circuit_breaker.record_failure()
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
            except aiohttp.ClientError as e:
                logger.warning(f"Connection error for {feed_name}: {e}")
                circuit_breaker.record_failure()
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
            except Exception as e:
                logger.error(f"Unexpected error fetching {feed_name}: {e}")
                return None
        
        logger.error(f"Failed to fetch {feed_name} after {max_retries} attempts")
        return None
    
    def _process_feed_entries(self, feed_data: bytes, feed_url: str, feed_name: str,
                            category: str, keywords: Optional[List[str]] = None,
                            use_cache: bool = True) -> List[Article]:
        """Process feed entries from raw data"""
        new_entries: List[Article] = []

        try:
            feed = feedparser.parse(feed_data)

            if feed.bozo:
                logger.warning(f"Feed parsing issue for {feed_name}: {feed.bozo_exception}")

            # Set a reasonable cutoff time (30 days) to avoid fetching very old articles
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=30)

            for entry in feed.entries:
                entry_id = self._generate_entry_id(entry)

                # Skip if we've seen this entry (when using cache)
                if use_cache and entry_id in self.seen_entries:
                    continue

                # Extract entry data
                title = entry.get('title', 'No title')
                link = entry.get('link', '')
                summary = entry.get('summary', entry.get('description', ''))
                published = self._parse_published_date(entry)

                # Skip very old articles (older than 30 days)
                if published and published < cutoff_time:
                    continue

                # Filter by keywords if provided
                if keywords:
                    content = f"{title} {summary}".lower()
                    if not any(keyword.lower() in content for keyword in keywords):
                        continue
                
                # Clean summary
                if summary:
                    # Remove HTML tags
                    summary = BeautifulSoup(summary, 'html.parser').get_text()
                    # Limit length
                    if len(summary) > 500:
                        summary = summary[:497] + "..."
                
                new_article = Article(
                    id=entry_id,
                    title=title,
                    link=link,
                    summary=summary,
                    published=published,
                    feed_name=feed_name,
                    category=FeedCategory(category) if category in [e.value for e in FeedCategory] else FeedCategory.GENERAL
                )

                new_entries.append(new_article)
                if use_cache:
                    self.seen_entries[entry_id] = datetime.now(timezone.utc)
            
            logger.info(f"Found {len(new_entries)} new entries from {feed_name}")
            
        except Exception as e:
            logger.error(f"Error processing feed {feed_name}: {e}", exc_info=True)
        
        return new_entries
    
    async def parse_feed_async(self, session: aiohttp.ClientSession,
                              feed_dict: Dict[str, Any], keywords: Optional[List[str]] = None,
                              use_cache: bool = True) -> List[Article]:
        """Parse a single RSS feed asynchronously"""
        feed_url = feed_dict['url']
        feed_name = feed_dict['name']
        category = feed_dict.get('category', 'general')
        
        feed_data = await self._fetch_feed_with_retry(session, feed_url, feed_name)
        if not feed_data:
            return []
        
        return self._process_feed_entries(
            feed_data, feed_url, feed_name, category, keywords, use_cache
        )
    
    async def parse_multiple_feeds_async(self, keywords: Optional[List[str]] = None,
                                       use_cache: bool = True) -> List[Article]:
        """Parse multiple RSS feeds concurrently"""
        feeds: List[Dict[str, Any]] = self.config.get('rss_feeds', [])
        if not feeds:
            logger.warning("No feeds configured in config.yaml")
            return []

        all_entries: List[Article] = []
        
        # Create connection pool with reasonable limits
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=2)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            # Create tasks for all feeds
            tasks = [
                self.parse_feed_async(session, feed, keywords, use_cache)
                for feed in feeds
            ]
            
            # Execute all tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error parsing feed {feeds[i]['name']}: {result}")
                else:
                    all_entries.extend(result)
        
        # Save cache after processing all feeds
        if use_cache:
            self._save_cache()
        
        # Sort by published date (newest first)
        all_entries.sort(
            key=lambda x: x.published or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )
        
        logger.info(f"Total entries found across all feeds: {len(all_entries)}")
        return all_entries
    
    def get_feeds_from_config(self) -> List[Dict[str, Any]]:
        """Get RSS feeds from configuration file"""
        return self.config.get('rss_feeds', [])
    
    def get_keywords_from_config(self) -> List[str]:
        """Get AI keywords from configuration file"""
        return self.config.get('ai_keywords', [])