import asyncio
import aiohttp
import feedparser
from datetime import datetime, timezone
from dateutil import parser as date_parser
from typing import List, Dict, Optional
import hashlib
import json
import os
import yaml
import time
from bs4 import BeautifulSoup

from logger_config import get_logger
from utils.file_lock import atomic_json_file, safe_json_read, safe_json_write
from utils.cache_manager import CacheManager

logger = get_logger(__name__)


class AsyncRSSParser:
    def __init__(self, cache_file: str = "feed_cache.json", config_file: str = "config.yaml"):
        self.cache_file = cache_file
        self.config_file = config_file
        self.config = self._load_config()
        self.seen_entries = self._load_cache()
        
    def _load_config(self) -> dict:
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
    
    def _save_cache(self):
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
    
    def _generate_entry_id(self, entry: dict) -> str:
        """Generate unique ID for an entry"""
        # Use combination of title and link for uniqueness
        content = f"{entry.get('title', '')}{entry.get('link', '')}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _parse_published_date(self, entry: dict) -> Optional[datetime]:
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
    
    async def _fetch_feed_with_retry(self, session: aiohttp.ClientSession, 
                                   feed_url: str, feed_name: str) -> Optional[bytes]:
        """Fetch RSS feed with retry logic using async"""
        fetch_config = self.config.get('rss_fetch', {})
        timeout = fetch_config.get('timeout', 30)
        max_retries = fetch_config.get('max_retries', 3)
        retry_delay = fetch_config.get('retry_delay', 5)
        
        headers = {'User-Agent': 'SlackWire RSS Bot 1.0'}
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching feed: {feed_name} (attempt {attempt + 1}/{max_retries})")
                
                async with session.get(feed_url, headers=headers, 
                                     timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    
                    if response.status == 200:
                        return await response.read()
                    elif response.status == 404:
                        logger.error(f"Feed not found (404): {feed_name} at {feed_url}")
                        return None
                    elif response.status == 503:
                        logger.warning(f"Service temporarily unavailable (503) for {feed_name}")
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                            logger.info(f"Waiting {wait_time} seconds before retry...")
                            await asyncio.sleep(wait_time)
                            continue
                    elif response.status == 429:
                        logger.warning(f"Rate limited (429) for {feed_name}")
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (2 ** attempt) * 2  # Longer wait for rate limits
                            logger.info(f"Waiting {wait_time} seconds before retry...")
                            await asyncio.sleep(wait_time)
                            continue
                    else:
                        logger.warning(f"HTTP {response.status} for {feed_name}")
                        
            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching {feed_name}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
            except aiohttp.ClientError as e:
                logger.warning(f"Connection error for {feed_name}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
            except Exception as e:
                logger.error(f"Unexpected error fetching {feed_name}: {e}")
                return None
        
        logger.error(f"Failed to fetch {feed_name} after {max_retries} attempts")
        return None
    
    def _process_feed_entries(self, feed_data: bytes, feed_url: str, feed_name: str, 
                            category: str, keywords: List[str] = None, 
                            use_cache: bool = True) -> List[Dict]:
        """Process feed entries from raw data"""
        new_entries = []
        
        try:
            feed = feedparser.parse(feed_data)
            
            if feed.bozo:
                logger.warning(f"Feed parsing issue for {feed_name}: {feed.bozo_exception}")
            
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
                
                new_entry = {
                    'id': entry_id,
                    'title': title,
                    'link': link,
                    'summary': summary,
                    'published': published,
                    'feed_name': feed_name,
                    'category': category
                }
                
                new_entries.append(new_entry)
                if use_cache:
                    self.seen_entries[entry_id] = datetime.now(timezone.utc)
            
            logger.info(f"Found {len(new_entries)} new entries from {feed_name}")
            
        except Exception as e:
            logger.error(f"Error processing feed {feed_name}: {e}", exc_info=True)
        
        return new_entries
    
    async def parse_feed_async(self, session: aiohttp.ClientSession, 
                              feed_dict: Dict, keywords: List[str] = None,
                              use_cache: bool = True) -> List[Dict]:
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
    
    async def parse_multiple_feeds_async(self, keywords: List[str] = None,
                                       use_cache: bool = True) -> List[Dict]:
        """Parse multiple RSS feeds concurrently"""
        feeds = self.config.get('rss_feeds', [])
        if not feeds:
            logger.warning("No feeds configured in config.yaml")
            return []
        
        all_entries = []
        
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
            key=lambda x: x['published'] or datetime.min.replace(tzinfo=timezone.utc), 
            reverse=True
        )
        
        logger.info(f"Total entries found across all feeds: {len(all_entries)}")
        return all_entries
    
    def get_feeds_from_config(self) -> List[Dict]:
        """Get RSS feeds from configuration file"""
        return self.config.get('rss_feeds', [])
    
    def get_keywords_from_config(self) -> List[str]:
        """Get AI keywords from configuration file"""
        return self.config.get('ai_keywords', [])