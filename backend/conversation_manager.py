"""
Conversation Manager

Manages conversation history and context for each session.
"""

from typing import Dict, List, Optional
from collections import defaultdict


class ConversationManager:
    """Manages conversation state and history"""
    
    def __init__(self):
        # Store conversation history per session
        self.sessions: Dict[str, List[Dict]] = defaultdict(list)
        # Store context/state per session
        self.context: Dict[str, Dict] = defaultdict(dict)
    
    def add_turn(self, session_id: str, role: str, text: str, intent: Optional[str] = None):
        """Add a conversation turn to history"""
        turn = {
            "role": role,  # 'user' or 'assistant'
            "text": text,
            "intent": intent
        }
        self.sessions[session_id].append(turn)
        
        # Keep only last 10 turns to manage memory
        if len(self.sessions[session_id]) > 10:
            self.sessions[session_id] = self.sessions[session_id][-10:]
    
    def get_history(self, session_id: str) -> List[Dict]:
        """Get conversation history for a session"""
        return self.sessions.get(session_id, [])
    
    def get_context(self, session_id: str) -> Dict:
        """Get context/state for a session"""
        return self.context.get(session_id, {})
    
    def set_context(self, session_id: str, key: str, value: any):
        """Set a context value for a session"""
        self.context[session_id][key] = value
    
    def clear_context(self, session_id: str):
        """Clear context for a session"""
        self.context[session_id] = {}
    
    def clear_session(self, session_id: str):
        """Clear all data for a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
        if session_id in self.context:
            del self.context[session_id]
