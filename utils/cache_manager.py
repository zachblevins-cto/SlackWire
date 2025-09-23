"""Cache management with size limits and expiration."""
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Set
from collections import OrderedDict
import logging
from pathlib import Path

from .file_lock import atomic_json_file, safe_json_read, safe_json_write

logger = logging.getLogger(__name__)

class CacheManager:
    """Manages caches with size limits and expiration."""
    
    def __init__(self, max_entries: int = 10000, expiry_days: int = 7):
        self.max_entries = max_entries
        self.expiry_seconds = expiry_days * 24 * 60 * 60
        
    def clean_feed_cache(self, cache_path: str) -> Dict[str, Any]:
        """Clean and optimize feed cache."""
        try:
            with atomic_json_file(cache_path) as cache_data:
                if 'seen_entries' not in cache_data:
                    return cache_data
                    
                seen_entries = cache_data['seen_entries']
                current_time = time.time()
                
                # Convert to ordered dict for LRU behavior
                ordered_entries = OrderedDict()
                expired_count = 0
                
                # Remove expired entries
                for url, timestamp in seen_entries.items():
                    if isinstance(timestamp, (int, float)):
                        age = current_time - timestamp
                        if age < self.expiry_seconds:
                            ordered_entries[url] = timestamp
                        else:
                            expired_count += 1
                
                # Enforce size limit (keep most recent)
                if len(ordered_entries) > self.max_entries:
                    # Sort by timestamp and keep most recent
                    sorted_items = sorted(ordered_entries.items(), 
                                        key=lambda x: x[1], 
                                        reverse=True)[:self.max_entries]
                    ordered_entries = OrderedDict(sorted_items)
                
                cache_data['seen_entries'] = dict(ordered_entries)
                
                logger.info(f"Cache cleanup: removed {expired_count} expired entries, "
                          f"kept {len(ordered_entries)} entries")
                
                return cache_data
                
        except Exception as e:
            logger.error(f"Error cleaning cache: {e}")
            return {}
    
    def add_entry(self, cache_path: str, url: str) -> bool:
        """Add entry to cache with timestamp."""
        try:
            with atomic_json_file(cache_path) as cache_data:
                if 'seen_entries' not in cache_data:
                    cache_data['seen_entries'] = {}
                
                cache_data['seen_entries'][url] = time.time()
                
                # Periodic cleanup every 100 entries
                if len(cache_data['seen_entries']) % 100 == 0:
                    self.clean_feed_cache(cache_path)
                    
                return True
                
        except Exception as e:
            logger.error(f"Error adding cache entry: {e}")
            return False
    
    def is_duplicate(self, cache_path: str, url: str) -> bool:
        """Check if URL exists in cache."""
        try:
            cache_data = safe_json_read(cache_path, {'seen_entries': {}})
            return url in cache_data.get('seen_entries', {})
        except Exception as e:
            logger.error(f"Error checking duplicate: {e}")
            return False
    
    def get_cache_stats(self, cache_path: str) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            cache_data = safe_json_read(cache_path, {'seen_entries': {}})
            seen_entries = cache_data.get('seen_entries', {})
            
            if not seen_entries:
                return {'total_entries': 0, 'oldest_entry': None, 'newest_entry': None}
            
            timestamps = [ts for ts in seen_entries.values() if isinstance(ts, (int, float))]
            
            return {
                'total_entries': len(seen_entries),
                'oldest_entry': datetime.fromtimestamp(min(timestamps)) if timestamps else None,
                'newest_entry': datetime.fromtimestamp(max(timestamps)) if timestamps else None,
                'size_bytes': Path(cache_path).stat().st_size if Path(cache_path).exists() else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {'error': str(e)}