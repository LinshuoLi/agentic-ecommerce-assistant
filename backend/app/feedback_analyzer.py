"""Feedback analyzer for improving agent prompts based on user feedback."""
import logging
from typing import Dict, List, Optional
from app.session_manager import session_manager

logger = logging.getLogger(__name__)


class FeedbackAnalyzer:
    """Analyzes user feedback to improve agent prompts and responses."""
    
    def __init__(self):
        self.min_feedback_threshold = 2  # Minimum feedbacks needed to generate insights
    
    def analyze_session_feedback(self, session_id: str) -> Dict:
        """
        Analyze feedback for a specific session and generate improvement suggestions.
        Returns a dict with feedback insights and prompt enhancements.
        """
        try:
            # Get feedback stats for this session
            stats = session_manager.get_feedback_stats(session_id)
            
            if stats['total'] < self.min_feedback_threshold:
                # Not enough feedback to generate insights
                return {
                    'has_insights': False,
                    'feedback_ratio': None,
                    'enhancements': []
                }
            
            # Calculate feedback ratio
            total = stats['total']
            thumbs_up = stats['thumbs_up']
            thumbs_down = stats['thumbs_down']
            positive_ratio = thumbs_up / total if total > 0 else 0
            
            # Retrieve recent negative feedback messages to analyze patterns
            negative_patterns = self._get_negative_feedback_patterns(session_id)
            
            # Generate prompt enhancements based on patterns
            enhancements = self._generate_enhancements(negative_patterns, positive_ratio)
            
            return {
                'has_insights': True,
                'feedback_ratio': positive_ratio,
                'thumbs_up': thumbs_up,
                'thumbs_down': thumbs_down,
                'total': total,
                'negative_patterns': negative_patterns,
                'enhancements': enhancements
            }
        except Exception as e:
            logger.error(f"Error analyzing feedback: {e}")
            return {
                'has_insights': False,
                'enhancements': []
            }
    
    def _get_negative_feedback_patterns(self, session_id: str) -> List[Dict]:
        """Retrieve recent negative feedback messages to identify patterns."""
        try:
            return session_manager.get_negative_feedback_messages(session_id, limit=10)
        except Exception as e:
            logger.error(f"Error retrieving negative feedback: {e}")
            return []
    
    def _generate_enhancements(self, negative_patterns: List[Dict], positive_ratio: float) -> List[str]:
        """
        Generate prompt enhancements based on negative feedback patterns.
        Returns a list of enhancement strings to add to the system prompt.
        """
        enhancements = []
        
        # If positive ratio is low (< 50%), add general improvement guidance
        if positive_ratio < 0.5:
            enhancements.append(
                "IMPORTANT: Recent feedback indicates responses need improvement. "
                "Be more thorough, provide complete information, and avoid asking for details you can extract or scrape yourself."
            )
        
        # Analyze message patterns (simple keyword-based analysis)
        if negative_patterns:
            message_texts = [p['message'].lower() for p in negative_patterns]
            combined_text = ' '.join(message_texts)
            
            # Check for common issues
            if any(word in combined_text for word in ['need', 'require', 'ask', 'provide', 'missing']):
                enhancements.append(
                    "CRITICAL: Do NOT ask users for information you can obtain yourself. "
                    "Always extract part numbers and model numbers from queries and scrape immediately. "
                    "Never say 'I need' or 'Please provide' - just do it."
                )
            
            if any(word in combined_text for word in ['incomplete', 'partial', 'more', 'detail']):
                enhancements.append(
                    "Provide complete, comprehensive answers. Include all relevant details: "
                    "part numbers, prices, compatibility, installation instructions, and specifications."
                )
            
            if any(word in combined_text for word in ['wrong', 'incorrect', 'error', 'mistake']):
                enhancements.append(
                    "Double-check all information before responding. Verify part numbers and model numbers are correct. "
                    "Ensure compatibility information is accurate."
                )
            
            if any(word in combined_text for word in ['unclear', 'confusing', 'understand']):
                enhancements.append(
                    "Be clear and concise in responses. Use simple language and structure information clearly. "
                    "Break down complex instructions into step-by-step format."
                )
        
        return enhancements
    
    def enhance_system_prompt(self, base_prompt: str, feedback_insights: Dict) -> str:
        """
        Enhance the system prompt with feedback-based improvements.
        """
        if not feedback_insights.get('has_insights'):
            return base_prompt
        
        enhancements = feedback_insights.get('enhancements', [])
        if not enhancements:
            return base_prompt
        
        # Add feedback-based enhancements at the beginning of the prompt
        feedback_section = "\n\n=== FEEDBACK-BASED IMPROVEMENTS ===\n"
        feedback_section += "\n".join(f"- {enhancement}\n" for enhancement in enhancements)
        feedback_section += "\nApply these improvements to your response.\n"
        
        # Insert after the initial description but before the main instructions
        insertion_point = base_prompt.find("CRITICAL:")
        if insertion_point > 0:
            enhanced_prompt = (
                base_prompt[:insertion_point] + 
                feedback_section + 
                base_prompt[insertion_point:]
            )
        else:
            # Fallback: append at the end
            enhanced_prompt = base_prompt + feedback_section
        
        logger.info(f"📊 Enhanced prompt with {len(enhancements)} feedback-based improvements")
        return enhanced_prompt


# Global feedback analyzer instance
feedback_analyzer = FeedbackAnalyzer()

