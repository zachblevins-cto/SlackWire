import pytest
import os
import json
from datetime import datetime

from feedback_manager import FeedbackManager


@pytest.mark.unit
class TestFeedbackManager:
    def test_init_creates_empty_data(self, temp_dir):
        """Test that FeedbackManager initializes with empty data"""
        feedback_file = os.path.join(temp_dir, 'feedback.json')
        manager = FeedbackManager(feedback_file=feedback_file)
        
        assert 'articles' in manager.feedback_data
        assert 'user_preferences' in manager.feedback_data
        assert 'source_scores' in manager.feedback_data
    
    def test_load_existing_feedback(self, mock_feedback_file):
        """Test loading existing feedback data"""
        manager = FeedbackManager(feedback_file=mock_feedback_file)
        
        assert isinstance(manager.feedback_data, dict)
        assert 'articles' in manager.feedback_data
    
    def test_add_feedback_new_article(self, mock_feedback_file, sample_article):
        """Test adding feedback for a new article"""
        manager = FeedbackManager(feedback_file=mock_feedback_file)
        
        manager.add_feedback(
            article_id=sample_article['id'],
            user_id='U12345',
            feedback_type='interesting',
            article_metadata=sample_article
        )
        
        # Check article was added
        assert sample_article['id'] in manager.feedback_data['articles']
        article_data = manager.feedback_data['articles'][sample_article['id']]
        
        assert len(article_data['feedback']) == 1
        assert article_data['feedback'][0]['user_id'] == 'U12345'
        assert article_data['feedback'][0]['type'] == 'interesting'
    
    def test_add_feedback_updates_user_preferences(self, mock_feedback_file, sample_article):
        """Test that feedback updates user preferences"""
        manager = FeedbackManager(feedback_file=mock_feedback_file)
        
        manager.add_feedback(
            article_id=sample_article['id'],
            user_id='U12345',
            feedback_type='interesting',
            article_metadata=sample_article
        )
        
        # Check user preferences
        user_prefs = manager.feedback_data['user_preferences']['U12345']
        assert user_prefs['total_feedback'] == 1
        assert 'Test Feed' in user_prefs['sources']
        assert user_prefs['sources']['Test Feed']['interesting'] == 1
    
    def test_add_feedback_updates_source_scores(self, mock_feedback_file, sample_article):
        """Test that feedback updates global source scores"""
        manager = FeedbackManager(feedback_file=mock_feedback_file)
        
        # Add interesting feedback
        manager.add_feedback(
            article_id=sample_article['id'],
            user_id='U12345',
            feedback_type='interesting',
            article_metadata=sample_article
        )
        
        # Add not_relevant feedback
        sample_article['id'] = 'test456'
        manager.add_feedback(
            article_id=sample_article['id'],
            user_id='U67890',
            feedback_type='not_relevant',
            article_metadata=sample_article
        )
        
        # Check source scores
        source_scores = manager.get_source_scores()
        assert 'Test Feed' in source_scores
        assert source_scores['Test Feed']['interesting'] == 1
        assert source_scores['Test Feed']['not_relevant'] == 1
    
    def test_get_article_feedback_summary(self, mock_feedback_file, sample_article):
        """Test getting feedback summary for an article"""
        manager = FeedbackManager(feedback_file=mock_feedback_file)
        
        # Add multiple feedback
        for i, feedback_type in enumerate(['interesting', 'interesting', 'not_relevant']):
            manager.add_feedback(
                article_id=sample_article['id'],
                user_id=f'U{i}',
                feedback_type=feedback_type,
                article_metadata=sample_article
            )
        
        summary = manager.get_article_feedback_summary(sample_article['id'])
        assert summary['interesting'] == 2
        assert summary['not_relevant'] == 1
    
    def test_get_article_feedback_summary_nonexistent(self, mock_feedback_file):
        """Test getting feedback summary for non-existent article"""
        manager = FeedbackManager(feedback_file=mock_feedback_file)
        
        summary = manager.get_article_feedback_summary('nonexistent')
        assert summary['interesting'] == 0
        assert summary['not_relevant'] == 0
    
    def test_get_trending_sources(self, mock_feedback_file):
        """Test getting trending sources"""
        manager = FeedbackManager(feedback_file=mock_feedback_file)
        
        # Add feedback for multiple sources
        sources_data = [
            ('Source A', 10, 2),  # 83% interesting
            ('Source B', 5, 5),   # 50% interesting
            ('Source C', 2, 8),   # 20% interesting
        ]
        
        for source, interesting, not_relevant in sources_data:
            for i in range(interesting):
                manager.add_feedback(
                    article_id=f'{source}_int_{i}',
                    user_id=f'U{i}',
                    feedback_type='interesting',
                    article_metadata={'feed_name': source, 'category': 'test'}
                )
            for i in range(not_relevant):
                manager.add_feedback(
                    article_id=f'{source}_not_{i}',
                    user_id=f'U{i}',
                    feedback_type='not_relevant',
                    article_metadata={'feed_name': source, 'category': 'test'}
                )
        
        trending = manager.get_trending_sources(limit=2)
        
        assert len(trending) == 2
        assert trending[0][0] == 'Source A'  # Highest ratio
        assert trending[1][0] == 'Source B'  # Second highest
    
    def test_should_prioritize_article_default(self, mock_feedback_file, sample_article):
        """Test article prioritization with default score"""
        manager = FeedbackManager(feedback_file=mock_feedback_file)
        
        score = manager.should_prioritize_article(sample_article)
        assert score == 0.5  # Default score
    
    def test_should_prioritize_article_with_source_data(self, mock_feedback_file, sample_article):
        """Test article prioritization with source feedback"""
        manager = FeedbackManager(feedback_file=mock_feedback_file)
        
        # Add positive feedback for the source
        for i in range(3):
            manager.add_feedback(
                article_id=f'test_{i}',
                user_id='U12345',
                feedback_type='interesting',
                article_metadata=sample_article
            )
        
        # Add one negative feedback
        manager.add_feedback(
            article_id='test_neg',
            user_id='U67890',
            feedback_type='not_relevant',
            article_metadata=sample_article
        )
        
        # New article from same source should have higher priority
        new_article = sample_article.copy()
        new_article['id'] = 'new_article'
        
        score = manager.should_prioritize_article(new_article)
        assert score > 0.5  # Should be higher than default
        assert score < 1.0  # Should not exceed 1
    
    def test_should_prioritize_article_with_user_preference(self, mock_feedback_file, sample_article):
        """Test article prioritization with user-specific preferences"""
        manager = FeedbackManager(feedback_file=mock_feedback_file)
        
        # User loves this source
        for i in range(5):
            manager.add_feedback(
                article_id=f'test_{i}',
                user_id='U12345',
                feedback_type='interesting',
                article_metadata=sample_article
            )
        
        # New article from same source for same user
        new_article = sample_article.copy()
        new_article['id'] = 'new_article'
        
        score = manager.should_prioritize_article(new_article, user_id='U12345')
        assert score > 0.7  # Should be quite high
    
    def test_save_and_load_feedback(self, temp_dir):
        """Test saving and loading feedback data"""
        feedback_file = os.path.join(temp_dir, 'test_feedback.json')
        
        # Create and save data
        manager1 = FeedbackManager(feedback_file=feedback_file)
        manager1.add_feedback(
            article_id='test123',
            user_id='U12345',
            feedback_type='interesting',
            article_metadata={'feed_name': 'Test', 'category': 'test'}
        )
        
        # Load in new instance
        manager2 = FeedbackManager(feedback_file=feedback_file)
        
        assert 'test123' in manager2.feedback_data['articles']
        assert 'U12345' in manager2.feedback_data['user_preferences']