import pytest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch
import json
import yaml

# Add the project root to the Python path
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_config_file(temp_dir):
    """Create a mock config.yaml file"""
    config_path = os.path.join(temp_dir, 'config.yaml')
    config_data = {
        'rss_feeds': [
            {
                'url': 'https://example.com/feed1.xml',
                'name': 'Test Feed 1',
                'category': 'test'
            },
            {
                'url': 'https://example.com/feed2.xml',
                'name': 'Test Feed 2',
                'category': 'test'
            }
        ],
        'ai_keywords': ['artificial intelligence', 'machine learning', 'test'],
        'llm_prompts': {
            'test': 'Test prompt for category',
            'default': 'Default test prompt'
        },
        'circuit_breaker': {
            'failure_threshold': 3,
            'recovery_timeout': 60,
            'half_open_attempts': 2
        },
        'rss_fetch': {
            'timeout': 10,
            'max_retries': 2,
            'retry_delay': 1
        }
    }
    
    with open(config_path, 'w') as f:
        yaml.dump(config_data, f)
    
    return config_path


@pytest.fixture
def mock_feed_cache(temp_dir):
    """Create a mock feed cache file"""
    cache_path = os.path.join(temp_dir, 'feed_cache.json')
    cache_data = {
        'abc123': '2024-01-01T00:00:00',
        'def456': '2024-01-02T00:00:00'
    }
    
    with open(cache_path, 'w') as f:
        json.dump(cache_data, f)
    
    return cache_path


@pytest.fixture
def mock_feedback_file(temp_dir):
    """Create a mock feedback file"""
    feedback_path = os.path.join(temp_dir, 'article_feedback.json')
    feedback_data = {
        'articles': {},
        'user_preferences': {},
        'source_scores': {}
    }
    
    with open(feedback_path, 'w') as f:
        json.dump(feedback_data, f)
    
    return feedback_path


@pytest.fixture
def mock_slack_client():
    """Create a mock Slack client"""
    client = Mock()
    client.chat_postMessage = Mock(return_value={'ok': True, 'ts': '1234567890.123456'})
    client.chat_update = Mock(return_value={'ok': True})
    client.chat_postEphemeral = Mock(return_value={'ok': True})
    return client


@pytest.fixture
def sample_article():
    """Create a sample article for testing"""
    from datetime import datetime, timezone
    return {
        'id': 'test123',
        'title': 'Test AI Article',
        'link': 'https://example.com/article',
        'summary': 'This is a test article about AI and machine learning.',
        'published': datetime.now(timezone.utc),
        'feed_name': 'Test Feed',
        'category': 'test'
    }


@pytest.fixture
def mock_aiohttp_session():
    """Create a mock aiohttp session"""
    session = Mock()
    
    # Mock response
    response = Mock()
    response.status = 200
    response.read = Mock(return_value=b'<rss>Mock RSS content</rss>')
    
    # Mock context manager
    async def mock_get(*args, **kwargs):
        return response
    
    response.__aenter__ = Mock(return_value=response)
    response.__aexit__ = Mock(return_value=None)
    
    session.get = Mock(return_value=response)
    
    return session