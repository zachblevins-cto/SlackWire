import pytest
import asyncio
import aiohttp
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone
import feedparser

from rss_parser import AsyncRSSParser


@pytest.mark.unit
class TestAsyncRSSParser:
    def test_init_loads_config(self, mock_config_file, mock_feed_cache):
        """Test that parser loads config and cache on init"""
        parser = AsyncRSSParser(
            cache_file=mock_feed_cache,
            config_file=mock_config_file
        )
        
        assert 'rss_feeds' in parser.config
        assert len(parser.config['rss_feeds']) == 2
        assert len(parser.seen_entries) == 2
    
    def test_generate_entry_id(self, mock_config_file):
        """Test entry ID generation"""
        parser = AsyncRSSParser(config_file=mock_config_file)
        
        entry = {
            'title': 'Test Article',
            'link': 'https://example.com/article'
        }
        
        entry_id = parser._generate_entry_id(entry)
        assert isinstance(entry_id, str)
        assert len(entry_id) == 32  # MD5 hex digest length
        
        # Same entry should generate same ID
        entry_id2 = parser._generate_entry_id(entry)
        assert entry_id == entry_id2
    
    def test_parse_published_date(self, mock_config_file):
        """Test parsing various date formats"""
        parser = AsyncRSSParser(config_file=mock_config_file)
        
        # Test with parsed date
        entry = type('Entry', (), {})()
        entry.published_parsed = (2024, 1, 1, 12, 0, 0, 0, 1, 0)
        
        date = parser._parse_published_date(entry)
        assert isinstance(date, datetime)
        assert date.year == 2024
        
        # Test with string date
        entry2 = type('Entry', (), {})()
        entry2.published = "2024-01-01T12:00:00Z"
        
        date2 = parser._parse_published_date(entry2)
        assert isinstance(date2, datetime)
        
        # Test with no date
        entry3 = type('Entry', (), {})()
        date3 = parser._parse_published_date(entry3)
        assert date3 is None
    
    @pytest.mark.asyncio
    async def test_fetch_feed_with_retry_success(self, mock_config_file):
        """Test successful feed fetching"""
        parser = AsyncRSSParser(config_file=mock_config_file)
        
        # Mock session and response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=b'<rss>test</rss>')
        
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()
        
        result = await parser._fetch_feed_with_retry(
            mock_session, 'https://example.com/feed.xml', 'Test Feed'
        )
        
        assert result == b'<rss>test</rss>'
        mock_session.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_fetch_feed_with_retry_404(self, mock_config_file):
        """Test feed fetching with 404 error"""
        parser = AsyncRSSParser(config_file=mock_config_file)
        
        mock_response = AsyncMock()
        mock_response.status = 404
        
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()
        
        result = await parser._fetch_feed_with_retry(
            mock_session, 'https://example.com/404.xml', 'Test Feed'
        )
        
        assert result is None
        mock_session.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_fetch_feed_with_retry_timeout(self, mock_config_file):
        """Test feed fetching with timeout and retries"""
        parser = AsyncRSSParser(config_file=mock_config_file)
        parser.config['rss_fetch']['max_retries'] = 2
        parser.config['rss_fetch']['retry_delay'] = 0.1
        
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=asyncio.TimeoutError())
        
        result = await parser._fetch_feed_with_retry(
            mock_session, 'https://example.com/slow.xml', 'Test Feed'
        )
        
        assert result is None
        assert mock_session.get.call_count == 2  # max_retries
    
    def test_process_feed_entries_with_cache(self, mock_config_file, sample_article):
        """Test processing feed entries with cache"""
        parser = AsyncRSSParser(config_file=mock_config_file)
        
        # Create mock feed data
        feed_data = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Test AI Article</title>
                    <link>https://example.com/article1</link>
                    <description>Article about artificial intelligence</description>
                </item>
                <item>
                    <title>Another Article</title>
                    <link>https://example.com/article2</link>
                    <description>Not about AI</description>
                </item>
            </channel>
        </rss>"""
        
        entries = parser._process_feed_entries(
            feed_data=feed_data,
            feed_url='https://example.com/feed.xml',
            feed_name='Test Feed',
            category='test',
            keywords=['artificial intelligence'],
            use_cache=True
        )
        
        # Should only return AI-related article
        assert len(entries) == 1
        assert 'artificial intelligence' in entries[0]['summary'].lower()
        
        # Entry should be added to cache
        entry_id = parser._generate_entry_id({'title': 'Test AI Article', 'link': 'https://example.com/article1'})
        assert entry_id in parser.seen_entries
    
    def test_process_feed_entries_without_cache(self, mock_config_file):
        """Test processing feed entries without cache"""
        parser = AsyncRSSParser(config_file=mock_config_file)
        parser.seen_entries['abc123'] = datetime.now(timezone.utc)
        
        feed_data = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Cached Article</title>
                    <link>https://example.com/cached</link>
                    <description>This was seen before</description>
                </item>
            </channel>
        </rss>"""
        
        # Create entry that would normally be filtered by cache
        parser.seen_entries[parser._generate_entry_id({
            'title': 'Cached Article',
            'link': 'https://example.com/cached'
        })] = datetime.now(timezone.utc)
        
        entries = parser._process_feed_entries(
            feed_data=feed_data,
            feed_url='https://example.com/feed.xml',
            feed_name='Test Feed',
            category='test',
            keywords=None,
            use_cache=False
        )
        
        # Should return entry even though it's in cache
        assert len(entries) == 1
    
    @pytest.mark.asyncio
    async def test_parse_multiple_feeds_async(self, mock_config_file, mock_feed_cache):
        """Test parsing multiple feeds concurrently"""
        parser = AsyncRSSParser(
            cache_file=mock_feed_cache,
            config_file=mock_config_file
        )
        
        # Mock successful feed data
        feed_data = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>AI News</title>
                    <link>https://example.com/ai-news</link>
                    <description>Latest in artificial intelligence</description>
                </item>
            </channel>
        </rss>"""
        
        # Mock the fetch method
        async def mock_fetch(*args):
            return feed_data
        
        with patch.object(parser, '_fetch_feed_with_retry', side_effect=mock_fetch):
            entries = await parser.parse_multiple_feeds_async(
                keywords=['artificial intelligence']
            )
        
        # Should get 2 entries (one from each feed in config)
        assert len(entries) == 2
        
        # Entries should be sorted by date (newest first)
        if entries[0].get('published') and entries[1].get('published'):
            assert entries[0]['published'] >= entries[1]['published']
    
    @pytest.mark.asyncio
    async def test_parse_multiple_feeds_handles_errors(self, mock_config_file):
        """Test that feed parsing handles individual feed errors"""
        parser = AsyncRSSParser(config_file=mock_config_file)
        
        # Make first feed fail, second succeed
        async def mock_fetch(session, url, name):
            if 'feed1' in url:
                raise Exception("Feed 1 error")
            return b'<rss><channel><item><title>Success</title></item></channel></rss>'
        
        with patch.object(parser, '_fetch_feed_with_retry', side_effect=mock_fetch):
            entries = await parser.parse_multiple_feeds_async()
        
        # Should still get entry from successful feed
        assert len(entries) == 1
        assert entries[0]['title'] == 'Success'
    
    def test_get_feeds_from_config(self, mock_config_file):
        """Test getting feeds from config"""
        parser = AsyncRSSParser(config_file=mock_config_file)
        feeds = parser.get_feeds_from_config()
        
        assert len(feeds) == 2
        assert feeds[0]['name'] == 'Test Feed 1'
        assert feeds[1]['name'] == 'Test Feed 2'
    
    def test_get_keywords_from_config(self, mock_config_file):
        """Test getting keywords from config"""
        parser = AsyncRSSParser(config_file=mock_config_file)
        keywords = parser.get_keywords_from_config()
        
        assert len(keywords) == 3
        assert 'artificial intelligence' in keywords
        assert 'machine learning' in keywords