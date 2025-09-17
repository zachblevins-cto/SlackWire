import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class FeedbackManager:
    """Manages article feedback data"""
    
    def __init__(self, feedback_file: str = "article_feedback.json"):
        self.feedback_file = feedback_file
        self.feedback_data = self._load_feedback()
    
    def _load_feedback(self) -> dict:
        """Load feedback data from file"""
        if os.path.exists(self.feedback_file):
            try:
                with open(self.feedback_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading feedback data: {e}")
        return {
            'articles': {},
            'user_preferences': {},
            'source_scores': defaultdict(lambda: {'interesting': 0, 'not_relevant': 0})
        }
    
    def _save_feedback(self):
        """Save feedback data to file"""
        try:
            # Convert defaultdict to regular dict for JSON serialization
            data = self.feedback_data.copy()
            data['source_scores'] = dict(data['source_scores'])
            
            with open(self.feedback_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving feedback data: {e}")
    
    def add_feedback(self, article_id: str, user_id: str, 
                    feedback_type: str, article_metadata: Optional[Dict] = None):
        """Add feedback for an article"""
        timestamp = datetime.now().isoformat()
        
        # Initialize article feedback if not exists
        if article_id not in self.feedback_data['articles']:
            self.feedback_data['articles'][article_id] = {
                'metadata': article_metadata or {},
                'feedback': []
            }
        
        # Add feedback
        self.feedback_data['articles'][article_id]['feedback'].append({
            'user_id': user_id,
            'type': feedback_type,
            'timestamp': timestamp
        })
        
        # Update user preferences
        if user_id not in self.feedback_data['user_preferences']:
            self.feedback_data['user_preferences'][user_id] = {
                'sources': defaultdict(lambda: {'interesting': 0, 'not_relevant': 0}),
                'categories': defaultdict(lambda: {'interesting': 0, 'not_relevant': 0}),
                'total_feedback': 0
            }
        
        user_prefs = self.feedback_data['user_preferences'][user_id]
        user_prefs['total_feedback'] += 1
        
        # Update source and category scores if metadata provided
        if article_metadata:
            source = article_metadata.get('feed_name')
            category = article_metadata.get('category')
            
            if source:
                user_prefs['sources'][source][feedback_type] += 1
                
                # Update global source scores
                if source not in self.feedback_data['source_scores']:
                    self.feedback_data['source_scores'][source] = {'interesting': 0, 'not_relevant': 0}
                self.feedback_data['source_scores'][source][feedback_type] += 1
            
            if category:
                user_prefs['categories'][category][feedback_type] += 1
        
        self._save_feedback()
        logger.info(f"Added {feedback_type} feedback for article {article_id} from user {user_id}")
    
    def get_article_feedback_summary(self, article_id: str) -> Dict:
        """Get feedback summary for a specific article"""
        if article_id not in self.feedback_data['articles']:
            return {'interesting': 0, 'not_relevant': 0}
        
        feedback_list = self.feedback_data['articles'][article_id]['feedback']
        summary = {'interesting': 0, 'not_relevant': 0}
        
        for feedback in feedback_list:
            feedback_type = feedback['type']
            if feedback_type in summary:
                summary[feedback_type] += 1
        
        return summary
    
    def get_source_scores(self) -> Dict[str, Dict]:
        """Get aggregated scores for all sources"""
        return dict(self.feedback_data['source_scores'])
    
    def get_user_preferences(self, user_id: str) -> Optional[Dict]:
        """Get preferences for a specific user"""
        return self.feedback_data['user_preferences'].get(user_id)
    
    def get_trending_sources(self, limit: int = 5) -> List[tuple]:
        """Get sources with the best interesting/not_relevant ratio"""
        source_scores = []
        
        for source, scores in self.feedback_data['source_scores'].items():
            interesting = scores.get('interesting', 0)
            not_relevant = scores.get('not_relevant', 0)
            total = interesting + not_relevant
            
            if total > 0:
                ratio = interesting / total
                source_scores.append((source, ratio, total))
        
        # Sort by ratio (descending) and then by total feedback (descending)
        source_scores.sort(key=lambda x: (x[1], x[2]), reverse=True)
        
        return source_scores[:limit]
    
    def should_prioritize_article(self, article_metadata: Dict, user_id: Optional[str] = None) -> float:
        """
        Calculate priority score for an article based on feedback data
        Returns a score between 0 and 1
        """
        score = 0.5  # Base score
        
        # Adjust based on global source performance
        source = article_metadata.get('feed_name')
        if source and source in self.feedback_data['source_scores']:
            scores = self.feedback_data['source_scores'][source]
            interesting = scores.get('interesting', 0)
            not_relevant = scores.get('not_relevant', 0)
            total = interesting + not_relevant
            
            if total > 0:
                source_ratio = interesting / total
                # Weight source score (0.3 weight)
                score = 0.7 * score + 0.3 * source_ratio
        
        # Adjust based on user preferences if provided
        if user_id and user_id in self.feedback_data['user_preferences']:
            user_prefs = self.feedback_data['user_preferences'][user_id]
            
            # Check user's preference for this source
            if source and source in user_prefs['sources']:
                user_source_scores = user_prefs['sources'][source]
                interesting = user_source_scores.get('interesting', 0)
                not_relevant = user_source_scores.get('not_relevant', 0)
                total = interesting + not_relevant
                
                if total > 0:
                    user_source_ratio = interesting / total
                    # Give more weight to user preference (0.5 weight)
                    score = 0.5 * score + 0.5 * user_source_ratio
        
        return max(0, min(1, score))  # Ensure score is between 0 and 1