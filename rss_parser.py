import feedparser
import logging
from datetime import datetime, timezone
from dateutil import parser as date_parser
from typing import List, Dict, Optional
import hashlib
import json
import os

logger = logging.getLogger(__name__)


class RSSParser:
    def __init__(self, cache_file: str = "feed_cache.json"):
        self.cache_file = cache_file
        self.seen_entries = self._load_cache()
    
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
    
    def parse_feed(self, feed_url: str, feed_name: str, 
                   category: str, keywords: List[str] = None) -> List[Dict]:
        """Parse RSS feed and return new entries"""
        new_entries = []
        
        try:
            logger.info(f"Parsing feed: {feed_name}")
            feed = feedparser.parse(feed_url)
            
            if feed.bozo:
                logger.warning(f"Feed parsing issue for {feed_name}: {feed.bozo_exception}")
            
            for entry in feed.entries:
                entry_id = self._generate_entry_id(entry)
                
                # Skip if we've seen this entry
                if entry_id in self.seen_entries:
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
                    from bs4 import BeautifulSoup
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
                self.seen_entries[entry_id] = datetime.now(timezone.utc)
            
            # Save cache after processing
            self._save_cache()
            
            logger.info(f"Found {len(new_entries)} new entries from {feed_name}")
            
        except Exception as e:
            logger.error(f"Error parsing feed {feed_name}: {e}")
        
        return new_entries
    
    def parse_feed_no_cache(self, feed_url: str, feed_name: str, 
                           category: str, keywords: List[str] = None) -> List[Dict]:
        """Parse RSS feed without cache checking (for slash commands)"""
        entries = []
        
        try:
            logger.info(f"Parsing feed (no cache): {feed_name}")
            feed = feedparser.parse(feed_url)
            
            if feed.bozo:
                logger.warning(f"Feed parsing issue for {feed_name}: {feed.bozo_exception}")
            
            for entry in feed.entries:
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
                    from bs4 import BeautifulSoup
                    summary = BeautifulSoup(summary, 'html.parser').get_text()
                    # Limit length
                    if len(summary) > 500:
                        summary = summary[:497] + "..."
                
                new_entry = {
                    'id': self._generate_entry_id(entry),
                    'title': title,
                    'link': link,
                    'summary': summary,
                    'published': published,
                    'feed_name': feed_name,
                    'category': category
                }
                
                entries.append(new_entry)
            
            logger.info(f"Found {len(entries)} entries from {feed_name}")
            
        except Exception as e:
            logger.error(f"Error parsing feed {feed_name}: {e}")
        
        return entries
    
    def parse_multiple_feeds(self, feeds: List[Dict], 
                           keywords: List[str] = None) -> List[Dict]:
        """Parse multiple RSS feeds"""
        all_entries = []
        
        for feed in feeds:
            entries = self.parse_feed(
                feed['url'], 
                feed['name'], 
                feed['category'],
                keywords
            )
            all_entries.extend(entries)
        
        # Sort by published date (newest first)
        all_entries.sort(
            key=lambda x: x['published'] or datetime.min.replace(tzinfo=timezone.utc), 
            reverse=True
        )
        
        return all_entries