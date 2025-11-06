"""Session manager for storing conversation history per session."""
import logging
from typing import Dict, List, Optional
from datetime import datetime
import uuid
import sqlite3
import os
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages conversation sessions with SQLite-based storage."""
    
    def __init__(self, db_path: str = None):
        # Default database path in data directory
        if db_path is None:
            data_dir = Path("data")
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "conversations.db")
        
        self.db_path = db_path
        # In-memory cache: stores last 5 messages per session for fast LLM context retrieval
        # Format: {session_id: [message1, message2, ...]} (max 5 messages per session)
        self._message_cache: Dict[str, List[Dict]] = {}
        self._max_cached_messages = 5
        self._init_database()
        logger.info(f"SessionManager initialized with database: {db_path}")
    
    def _get_connection(self):
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_database(self):
        """Initialize the database with required tables."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Create sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'New conversation',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
            ''')
            
            # Create index for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_messages_session_id 
                ON messages(session_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp 
                ON messages(timestamp)
            ''')
            
            # Create feedback table for storing user feedback on responses
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    message_content TEXT NOT NULL,
                    rating TEXT NOT NULL CHECK(rating IN ('thumbs_up', 'thumbs_down')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
            ''')
            
            # Create index for feedback queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_feedback_session_id 
                ON feedback(session_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_feedback_rating 
                ON feedback(rating)
            ''')
            
            conn.commit()
            logger.info("Database tables initialized")
        finally:
            conn.close()
    
    def create_session(self, title: str = "New conversation") -> str:
        """Create a new session and return session_id."""
        session_id = str(uuid.uuid4())
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sessions (session_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            ''', (session_id, title, datetime.now().isoformat(), datetime.now().isoformat()))
            conn.commit()
            logger.info(f"📝 Created new session: {session_id} with title: {title}")
        finally:
            conn.close()
        return session_id
    
    def get_history(self, session_id: str) -> List[Dict]:
        """Get full conversation history for a session from SQLite. Returns empty list if session doesn't exist."""
        conn = self._get_connection()
        try:
            # First check if session exists
            cursor = conn.cursor()
            cursor.execute('SELECT session_id FROM sessions WHERE session_id = ?', (session_id,))
            if not cursor.fetchone():
                logger.info(f"📖 Session {session_id} not found, returning empty history")
                return []
            
            cursor.execute('''
                SELECT role, content, timestamp
                FROM messages
                WHERE session_id = ?
                ORDER BY timestamp ASC
            ''', (session_id,))
            
            rows = cursor.fetchall()
            history = [
                {
                    'role': row['role'],
                    'content': row['content'],
                    'timestamp': row['timestamp']
                }
                for row in rows
            ]
            
            logger.info(f"📖 Retrieved history for session {session_id}: {len(history)} messages")
            return history
        finally:
            conn.close()
    
    def get_recent_history(self, session_id: str) -> List[Dict]:
        """
        Get the last 5 messages from in-memory cache for LLM context.
        This is faster than querying SQLite for full history.
        If cache is empty but SQLite has messages (e.g., after server restart),
        populates cache from SQLite and returns the last 5 messages.
        Returns empty list if session doesn't exist.
        """
        if session_id not in self._message_cache or len(self._message_cache[session_id]) == 0:
            # Cache is empty, try to populate from SQLite if messages exist
            full_history = self.get_history(session_id)
            if full_history:
                # Populate cache with last 5 messages from SQLite
                self._message_cache[session_id] = full_history[-self._max_cached_messages:]
                logger.debug(f"📦 Populated cache for session {session_id} from SQLite ({len(self._message_cache[session_id])} messages)")
                return self._message_cache[session_id].copy()
            else:
                # No messages in SQLite either, return empty
                logger.debug(f"📦 Session {session_id} not in cache and no SQLite history, returning empty")
                return []
        
        cached_messages = self._message_cache[session_id]
        logger.debug(f"📦 Retrieved {len(cached_messages)} cached messages for session {session_id} (LLM context)")
        return cached_messages.copy()  # Return a copy to prevent external modification
    
    def add_message(self, session_id: str, role: str, content: str):
        """Add a message to the conversation history."""
        conn = self._get_connection()
        try:
            # Ensure session exists
            cursor = conn.cursor()
            cursor.execute('SELECT session_id FROM sessions WHERE session_id = ?', (session_id,))
            if not cursor.fetchone():
                logger.warning(f"⚠️  Session {session_id} not found when adding message, creating new session")
                cursor.execute('''
                    INSERT INTO sessions (session_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                ''', (session_id, "New conversation", datetime.now().isoformat(), datetime.now().isoformat()))
            
            # If this is the first user message, update title to truncated message
            if role == 'user':
                cursor.execute('''
                    SELECT COUNT(*) as count
                    FROM messages
                    WHERE session_id = ? AND role = 'user'
                ''', (session_id,))
                user_message_count = cursor.fetchone()['count']
                
                if user_message_count == 0:  # First user message (before inserting)
                    # Truncate to 50 characters for title
                    truncated_title = content[:50] + "..." if len(content) > 50 else content
                    cursor.execute('''
                        UPDATE sessions
                        SET title = ?
                        WHERE session_id = ?
                    ''', (truncated_title, session_id))
                    logger.info(f"📝 Updated session {session_id} title to: {truncated_title}")
            
            # Insert message
            timestamp = datetime.now().isoformat()
            cursor.execute('''
                INSERT INTO messages (session_id, role, content, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (session_id, role, content, timestamp))
            
            # Update session's updated_at timestamp
            cursor.execute('''
                UPDATE sessions
                SET updated_at = ?
                WHERE session_id = ?
            ''', (timestamp, session_id))
            
            conn.commit()
            
            # Update in-memory cache: add new message and keep only last 5
            message_dict = {
                'role': role,
                'content': content,
                'timestamp': timestamp
            }
            
            if session_id not in self._message_cache:
                self._message_cache[session_id] = []
            
            self._message_cache[session_id].append(message_dict)
            # Keep only the last max_cached_messages messages
            if len(self._message_cache[session_id]) > self._max_cached_messages:
                self._message_cache[session_id] = self._message_cache[session_id][-self._max_cached_messages:]
            
            content_preview = content[:200] + "..." if len(content) > 200 else content
            logger.info(f"💬 Added {role} message to session {session_id}")
            logger.info(f"   Content: {content_preview}")
            logger.debug(f"   Cache now has {len(self._message_cache.get(session_id, []))} messages for session {session_id}")
        finally:
            conn.close()
    
    def update_history(self, session_id: str, history: List[Dict]):
        """Update the entire conversation history for a session."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Delete existing messages
            cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
            # Insert new messages
            for msg in history:
                cursor.execute('''
                    INSERT INTO messages (session_id, role, content, timestamp)
                    VALUES (?, ?, ?, ?)
                ''', (session_id, msg.get('role', 'user'), msg.get('content', ''), 
                      msg.get('timestamp', datetime.now().isoformat())))
            conn.commit()
            
            # Update in-memory cache with last 5 messages
            if history:
                self._message_cache[session_id] = history[-self._max_cached_messages:]
            elif session_id in self._message_cache:
                del self._message_cache[session_id]
            
            logger.debug(f"Updated history for session {session_id} with {len(history)} messages")
        finally:
            conn.close()
    
    def clear_session(self, session_id: str):
        """Clear conversation history for a session."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
            # Reset title
            cursor.execute('''
                UPDATE sessions
                SET title = 'New conversation', updated_at = ?
                WHERE session_id = ?
            ''', (datetime.now().isoformat(), session_id))
            conn.commit()
            
            # Clear in-memory cache for this session
            if session_id in self._message_cache:
                del self._message_cache[session_id]
                logger.debug(f"🗑️  Cleared cache for session {session_id}")
            
            logger.info(f"🗑️  Cleared session {session_id}")
        finally:
            conn.close()
    
    def delete_session(self, session_id: str):
        """Delete a session entirely."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Delete messages first (due to foreign key constraint, though CASCADE should handle it)
            cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
            # Delete session
            cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
            conn.commit()
            
            # Remove from in-memory cache
            if session_id in self._message_cache:
                del self._message_cache[session_id]
                logger.debug(f"🗑️  Removed session {session_id} from cache")
            
            logger.info(f"🗑️  Deleted session {session_id}")
        finally:
            conn.close()
    
    def get_session_count(self) -> int:
        """Get the number of active sessions."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM sessions')
            return cursor.fetchone()['count']
        finally:
            conn.close()
    
    def list_sessions(self, limit: int = 100) -> List[Dict]:
        """List all sessions ordered by most recent update."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    s.session_id,
                    s.title,
                    s.created_at,
                    s.updated_at,
                    COUNT(m.id) as message_count
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.session_id
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            sessions = [
                {
                    'session_id': row['session_id'],
                    'title': row['title'],
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                    'message_count': row['message_count']
                }
                for row in rows
            ]
            
            logger.info(f"📋 Listed {len(sessions)} sessions")
            return sessions
        finally:
            conn.close()
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session details."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    s.session_id,
                    s.title,
                    s.created_at,
                    s.updated_at,
                    COUNT(m.id) as message_count
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.session_id
                WHERE s.session_id = ?
                GROUP BY s.session_id
            ''', (session_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'session_id': row['session_id'],
                    'title': row['title'],
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                    'message_count': row['message_count']
                }
            return None
        finally:
            conn.close()
    
    def add_feedback(self, session_id: str, message_content: str, rating: str) -> bool:
        """
        Add feedback for a message.
        rating should be 'thumbs_up' or 'thumbs_down'
        """
        if rating not in ['thumbs_up', 'thumbs_down']:
            logger.warning(f"Invalid rating: {rating}, must be 'thumbs_up' or 'thumbs_down'")
            return False
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO feedback (session_id, message_content, rating, created_at)
                VALUES (?, ?, ?, ?)
            ''', (session_id, message_content, rating, datetime.now().isoformat()))
            conn.commit()
            
            logger.info(f"👍 Feedback recorded: {rating} for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding feedback: {e}")
            return False
        finally:
            conn.close()
    
    def get_negative_feedback_messages(self, session_id: str, limit: int = 10) -> List[Dict]:
        """
        Get recent negative feedback messages for a session.
        Returns list of dicts with 'message_content' and 'created_at'.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT message_content, created_at
                FROM feedback
                WHERE session_id = ? AND rating = 'thumbs_down'
                ORDER BY created_at DESC
                LIMIT ?
            ''', (session_id, limit))
            
            rows = cursor.fetchall()
            return [
                {
                    'message': row['message_content'],
                    'timestamp': row['created_at']
                }
                for row in rows
            ]
        finally:
            conn.close()
    
    def get_feedback_stats(self, session_id: str = None) -> Dict:
        """
        Get feedback statistics.
        If session_id is provided, returns stats for that session.
        Otherwise returns overall stats.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            if session_id:
                cursor.execute('''
                    SELECT 
                        SUM(CASE WHEN rating = 'thumbs_up' THEN 1 ELSE 0 END) as thumbs_up_count,
                        SUM(CASE WHEN rating = 'thumbs_down' THEN 1 ELSE 0 END) as thumbs_down_count,
                        COUNT(*) as total_count
                    FROM feedback
                    WHERE session_id = ?
                ''', (session_id,))
            else:
                cursor.execute('''
                    SELECT 
                        SUM(CASE WHEN rating = 'thumbs_up' THEN 1 ELSE 0 END) as thumbs_up_count,
                        SUM(CASE WHEN rating = 'thumbs_down' THEN 1 ELSE 0 END) as thumbs_down_count,
                        COUNT(*) as total_count
                    FROM feedback
                ''')
            
            row = cursor.fetchone()
            if row and row['total_count']:
                return {
                    'thumbs_up': row['thumbs_up_count'] or 0,
                    'thumbs_down': row['thumbs_down_count'] or 0,
                    'total': row['total_count'] or 0
                }
            return {'thumbs_up': 0, 'thumbs_down': 0, 'total': 0}
        finally:
            conn.close()


# Global session manager instance
session_manager = SessionManager()

