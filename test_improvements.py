#!/usr/bin/env python3
"""Test script to verify the improvements work correctly."""

import asyncio
import sys
from datetime import datetime, timezone
from typing import List

# Test imports
try:
    from models import Article, RSSFeed, FeedCategory
    from models_v2 import Article as ArticleV2, AppConfig, CircuitBreakerConfig as CBConfig
    from rss_parser import AsyncRSSParser
    from circuit_breaker import CircuitBreaker
    print("✅ All imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)


def test_article_models():
    """Test Article model functionality."""
    print("\n🧪 Testing Article models...")

    # Test basic Article creation
    article = Article(
        id="test123",
        title="Test Article",
        link="https://example.com/article",
        feed_name="TestFeed",
        summary="This is a test article",
        published=datetime.now(timezone.utc),
        category=FeedCategory.NEWS
    )

    # Test serialization
    article_dict = article.to_dict()
    assert article_dict['title'] == "Test Article"
    assert article_dict['category'] == "news"

    # Test deserialization
    article2 = Article.from_dict(article_dict)
    assert article2.title == article.title
    assert article2.category == article.category

    print("  ✅ Basic Article model works")

    # Test Pydantic Article with validation
    try:
        article_v2 = ArticleV2(
            id="test456",
            title="Test Article V2",
            link="https://example.com/article2",
            feed_name="TestFeed",
            priority_score=0.75
        )
        assert article_v2.priority_score == 0.75
        assert article_v2.category == FeedCategory.GENERAL  # Default value
        print("  ✅ Pydantic Article model with validation works")
    except Exception as e:
        print(f"  ❌ Pydantic Article failed: {e}")
        return False

    # Test validation failure
    try:
        bad_article = ArticleV2(
            id="",  # Empty ID should fail
            title="Test",
            link="not-a-url",  # Invalid URL should fail
            feed_name="Test"
        )
        print("  ❌ Validation should have failed but didn't")
        return False
    except Exception:
        print("  ✅ Validation correctly rejects invalid data")

    return True


def test_circuit_breaker():
    """Test circuit breaker functionality."""
    print("\n🧪 Testing Circuit Breaker...")

    from circuit_breaker import CircuitBreakerConfig, CircuitState

    # Create circuit breaker
    config = CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=2,
        exception_types=(ValueError,)
    )
    cb = CircuitBreaker(config)

    # Test successful calls
    def good_function():
        return "success"

    result = cb.call(good_function)
    assert result == "success"
    assert cb.state == CircuitState.CLOSED
    print("  ✅ Circuit breaker allows successful calls")

    # Test failure tracking
    def bad_function():
        raise ValueError("Test error")

    for i in range(3):
        try:
            cb.call(bad_function)
        except ValueError:
            pass

    assert cb.state == CircuitState.OPEN
    print("  ✅ Circuit breaker opens after threshold failures")

    # Test that open circuit rejects calls
    try:
        cb.call(good_function)
        print("  ❌ Open circuit should reject calls")
        return False
    except Exception:
        print("  ✅ Open circuit correctly rejects calls")

    return True


async def test_rss_parser_with_circuit_breaker():
    """Test RSS parser with circuit breaker integration."""
    print("\n🧪 Testing RSS Parser with Circuit Breaker...")

    parser = AsyncRSSParser()

    # Check that circuit breakers are initialized
    test_url = "https://example.com/feed.xml"
    cb = parser._get_circuit_breaker(test_url)
    assert isinstance(cb, CircuitBreaker)
    print("  ✅ Circuit breaker initialized for domain")

    # The actual feed fetching would require a real RSS feed
    # For now, we just verify the structure is in place
    assert hasattr(parser, 'circuit_breakers')
    assert isinstance(parser.circuit_breakers, dict)
    print("  ✅ RSS parser has circuit breaker integration")

    return True


def test_app_config():
    """Test application configuration with validation."""
    print("\n🧪 Testing App Configuration...")

    from models_v2 import RSSFeed as RSSFeedV2

    try:
        config = AppConfig(
            rss_feeds=[
                RSSFeedV2(
                    url="https://example.com/feed1.xml",
                    name="Feed1",
                    category=FeedCategory.NEWS
                ),
                RSSFeedV2(
                    url="https://example.com/feed2.xml",
                    name="Feed2",
                    category=FeedCategory.ACADEMIC
                )
            ],
            ai_keywords=["AI", "machine learning", "neural networks"],
            check_interval_minutes=30,
            max_articles_per_update=15
        )

        assert len(config.rss_feeds) == 2
        assert len(config.ai_keywords) == 3
        print("  ✅ App configuration with validation works")

        # Test duplicate feed names validation
        try:
            bad_config = AppConfig(
                rss_feeds=[
                    RSSFeedV2(url="https://example.com/feed1.xml", name="Feed1"),
                    RSSFeedV2(url="https://example.com/feed2.xml", name="Feed1")  # Duplicate name
                ]
            )
            print("  ❌ Should have rejected duplicate feed names")
            return False
        except Exception:
            print("  ✅ Correctly rejects duplicate feed names")

    except Exception as e:
        print(f"  ❌ App configuration failed: {e}")
        return False

    return True


async def main():
    """Run all tests."""
    print("🚀 Starting SlackWire Improvements Test Suite\n")

    all_passed = True

    # Run synchronous tests
    if not test_article_models():
        all_passed = False

    if not test_circuit_breaker():
        all_passed = False

    if not test_app_config():
        all_passed = False

    # Run async tests
    if not await test_rss_parser_with_circuit_breaker():
        all_passed = False

    print("\n" + "="*50)
    if all_passed:
        print("✅ All tests passed! The improvements are working correctly.")
    else:
        print("❌ Some tests failed. Please review the output above.")

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)