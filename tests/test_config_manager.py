import pytest
import os
import yaml
from unittest.mock import patch

from config_manager import ConfigManager


@pytest.mark.unit
class TestConfigManager:
    def test_init_creates_backup_dir(self, temp_dir):
        """Test that ConfigManager creates backup directory on init"""
        with patch.object(ConfigManager, 'config_file', os.path.join(temp_dir, 'config.yaml')):
            manager = ConfigManager()
            backup_dir = os.path.join(os.path.dirname(manager.config_file), 'config_backups')
            assert os.path.exists(backup_dir)
    
    def test_load_config_success(self, mock_config_file):
        """Test successful config loading"""
        manager = ConfigManager(config_file=mock_config_file)
        config = manager.load_config()
        
        assert 'rss_feeds' in config
        assert len(config['rss_feeds']) == 2
        assert 'ai_keywords' in config
        assert len(config['ai_keywords']) == 3
    
    def test_load_config_file_not_found(self, temp_dir):
        """Test config loading when file doesn't exist"""
        non_existent = os.path.join(temp_dir, 'missing.yaml')
        manager = ConfigManager(config_file=non_existent)
        config = manager.load_config()
        
        assert config == {}
    
    def test_save_config_creates_backup(self, mock_config_file, temp_dir):
        """Test that saving config creates a backup"""
        manager = ConfigManager(config_file=mock_config_file)
        manager.backup_dir = os.path.join(temp_dir, 'backups')
        os.makedirs(manager.backup_dir, exist_ok=True)
        
        # Modify and save config
        config = manager.load_config()
        config['test'] = 'value'
        success = manager.save_config(config)
        
        assert success
        # Check backup was created
        backup_files = os.listdir(manager.backup_dir)
        assert len(backup_files) == 1
        assert backup_files[0].startswith('config_')
    
    def test_add_feed_success(self, mock_config_file):
        """Test adding a new feed"""
        manager = ConfigManager(config_file=mock_config_file)
        success, message = manager.add_feed(
            url='https://example.com/new.xml',
            name='New Feed',
            category='test'
        )
        
        assert success
        assert 'Successfully added feed' in message
        
        # Verify feed was added
        config = manager.load_config()
        assert len(config['rss_feeds']) == 3
        assert any(f['name'] == 'New Feed' for f in config['rss_feeds'])
    
    def test_add_feed_duplicate(self, mock_config_file):
        """Test adding a duplicate feed"""
        manager = ConfigManager(config_file=mock_config_file)
        success, message = manager.add_feed(
            url='https://example.com/feed1.xml',  # Already exists
            name='Duplicate Feed',
            category='test'
        )
        
        assert not success
        assert 'Feed already exists' in message
    
    def test_remove_feed_success(self, mock_config_file):
        """Test removing an existing feed"""
        manager = ConfigManager(config_file=mock_config_file)
        success, message = manager.remove_feed('Test Feed 1')
        
        assert success
        assert 'Successfully removed feed' in message
        
        # Verify feed was removed
        config = manager.load_config()
        assert len(config['rss_feeds']) == 1
        assert not any(f['name'] == 'Test Feed 1' for f in config['rss_feeds'])
    
    def test_remove_feed_not_found(self, mock_config_file):
        """Test removing a non-existent feed"""
        manager = ConfigManager(config_file=mock_config_file)
        success, message = manager.remove_feed('Non-existent Feed')
        
        assert not success
        assert 'Feed not found' in message
    
    def test_list_feeds(self, mock_config_file):
        """Test listing all feeds"""
        manager = ConfigManager(config_file=mock_config_file)
        feeds = manager.list_feeds()
        
        assert len(feeds) == 2
        assert feeds[0]['name'] == 'Test Feed 1'
        assert feeds[1]['name'] == 'Test Feed 2'
    
    def test_add_keyword_success(self, mock_config_file):
        """Test adding a new keyword"""
        manager = ConfigManager(config_file=mock_config_file)
        success, message = manager.add_keyword('deep learning')
        
        assert success
        assert 'Successfully added keyword' in message
        
        # Verify keyword was added
        config = manager.load_config()
        assert 'deep learning' in config['ai_keywords']
    
    def test_add_keyword_duplicate(self, mock_config_file):
        """Test adding a duplicate keyword (case insensitive)"""
        manager = ConfigManager(config_file=mock_config_file)
        success, message = manager.add_keyword('Machine Learning')  # Already exists
        
        assert not success
        assert 'Keyword already exists' in message
    
    def test_remove_keyword_success(self, mock_config_file):
        """Test removing a keyword"""
        manager = ConfigManager(config_file=mock_config_file)
        success, message = manager.remove_keyword('test')
        
        assert success
        assert 'Successfully removed keyword' in message
        
        # Verify keyword was removed
        config = manager.load_config()
        assert 'test' not in config['ai_keywords']
    
    def test_cleanup_old_backups(self, temp_dir):
        """Test that old backups are cleaned up"""
        manager = ConfigManager()
        manager.backup_dir = temp_dir
        
        # Create 15 fake backup files
        for i in range(15):
            backup_file = os.path.join(temp_dir, f'config_2024010{i:02d}_120000.yaml')
            open(backup_file, 'w').close()
        
        # Run cleanup
        manager._cleanup_old_backups(keep_count=10)
        
        # Should only have 10 files left
        remaining_files = [f for f in os.listdir(temp_dir) if f.startswith('config_')]
        assert len(remaining_files) == 10