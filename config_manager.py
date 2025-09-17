import yaml
import os
import logging
from typing import List, Dict, Optional
from datetime import datetime
import shutil

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration file operations with backup and validation"""
    
    def __init__(self, config_file: str = "config.yaml"):
        self.config_file = config_file
        self.backup_dir = "config_backups"
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def _create_backup(self):
        """Create a backup of the current config file"""
        if os.path.exists(self.config_file):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(self.backup_dir, f"config_{timestamp}.yaml")
            shutil.copy2(self.config_file, backup_file)
            logger.info(f"Config backup created: {backup_file}")
            
            # Keep only last 10 backups
            self._cleanup_old_backups()
    
    def _cleanup_old_backups(self, keep_count: int = 10):
        """Remove old backup files, keeping only the most recent ones"""
        backup_files = sorted([
            f for f in os.listdir(self.backup_dir) 
            if f.startswith("config_") and f.endswith(".yaml")
        ])
        
        if len(backup_files) > keep_count:
            for old_file in backup_files[:-keep_count]:
                os.remove(os.path.join(self.backup_dir, old_file))
                logger.debug(f"Removed old backup: {old_file}")
    
    def load_config(self) -> dict:
        """Load configuration from YAML file"""
        try:
            with open(self.config_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}
    
    def save_config(self, config: dict) -> bool:
        """Save configuration to YAML file with backup"""
        try:
            # Create backup first
            self._create_backup()
            
            # Write new config
            with open(self.config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
            logger.info("Configuration saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False
    
    def add_feed(self, url: str, name: str, category: str = "general") -> tuple[bool, str]:
        """Add a new RSS feed to the configuration"""
        try:
            config = self.load_config()
            
            # Check if feed already exists
            feeds = config.get('rss_feeds', [])
            for feed in feeds:
                if feed['url'] == url:
                    return False, f"Feed already exists: {feed['name']}"
            
            # Add new feed
            new_feed = {
                'url': url,
                'name': name,
                'category': category
            }
            feeds.append(new_feed)
            config['rss_feeds'] = feeds
            
            # Save config
            if self.save_config(config):
                return True, f"Successfully added feed: {name}"
            else:
                return False, "Failed to save configuration"
                
        except Exception as e:
            logger.error(f"Error adding feed: {e}")
            return False, f"Error: {str(e)}"
    
    def remove_feed(self, name: str) -> tuple[bool, str]:
        """Remove an RSS feed from the configuration"""
        try:
            config = self.load_config()
            feeds = config.get('rss_feeds', [])
            
            # Find and remove feed
            original_count = len(feeds)
            feeds = [f for f in feeds if f['name'].lower() != name.lower()]
            
            if len(feeds) == original_count:
                return False, f"Feed not found: {name}"
            
            config['rss_feeds'] = feeds
            
            # Save config
            if self.save_config(config):
                return True, f"Successfully removed feed: {name}"
            else:
                return False, "Failed to save configuration"
                
        except Exception as e:
            logger.error(f"Error removing feed: {e}")
            return False, f"Error: {str(e)}"
    
    def list_feeds(self) -> List[Dict]:
        """Get list of all configured feeds"""
        config = self.load_config()
        return config.get('rss_feeds', [])
    
    def add_keyword(self, keyword: str) -> tuple[bool, str]:
        """Add a new AI keyword to the configuration"""
        try:
            config = self.load_config()
            keywords = config.get('ai_keywords', [])
            
            # Check if keyword already exists
            keyword_lower = keyword.lower()
            if any(k.lower() == keyword_lower for k in keywords):
                return False, f"Keyword already exists: {keyword}"
            
            # Add new keyword
            keywords.append(keyword)
            config['ai_keywords'] = keywords
            
            # Save config
            if self.save_config(config):
                return True, f"Successfully added keyword: {keyword}"
            else:
                return False, "Failed to save configuration"
                
        except Exception as e:
            logger.error(f"Error adding keyword: {e}")
            return False, f"Error: {str(e)}"
    
    def remove_keyword(self, keyword: str) -> tuple[bool, str]:
        """Remove an AI keyword from the configuration"""
        try:
            config = self.load_config()
            keywords = config.get('ai_keywords', [])
            
            # Find and remove keyword (case-insensitive)
            original_count = len(keywords)
            keywords = [k for k in keywords if k.lower() != keyword.lower()]
            
            if len(keywords) == original_count:
                return False, f"Keyword not found: {keyword}"
            
            config['ai_keywords'] = keywords
            
            # Save config
            if self.save_config(config):
                return True, f"Successfully removed keyword: {keyword}"
            else:
                return False, "Failed to save configuration"
                
        except Exception as e:
            logger.error(f"Error removing keyword: {e}")
            return False, f"Error: {str(e)}"
    
    def list_keywords(self) -> List[str]:
        """Get list of all configured keywords"""
        config = self.load_config()
        return config.get('ai_keywords', [])