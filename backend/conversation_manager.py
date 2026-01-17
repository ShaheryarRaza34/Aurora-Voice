"""
Conversation Manager

Manages conversation history and context for each session using MySQL database.
"""

import mysql.connector
from mysql.connector import Error
from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict
import os
import json


class ConversationManager:
    """Manages conversation state and history with persistent MySQL database storage"""
    
    def __init__(self):
        """Initialize conversation manager with MySQL database"""
        # Get MySQL connection details from environment variables
        self.mysql_host = os.getenv("MYSQL_HOST", "mysql")
        self.mysql_port = int(os.getenv("MYSQL_PORT", "3306"))
        self.mysql_database = os.getenv("MYSQL_DATABASE", "aurora_assistant")
        self.mysql_user = os.getenv("MYSQL_USER", "aurora_user")
        self.mysql_password = os.getenv("MYSQL_PASSWORD", "aurora_password")
        
        # Store in-memory context for active sessions (faster access)
        self.context: Dict[str, Dict] = defaultdict(dict)
        
        # Connect to database
        self.conn = self._connect()
        
        # Create tables
        self._create_tables()
    
    def _connect(self):
        """Create MySQL connection with retry logic"""
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                conn = mysql.connector.connect(
                    host=self.mysql_host,
                    port=self.mysql_port,
                    database=self.mysql_database,
                    user=self.mysql_user,
                    password=self.mysql_password,
                    autocommit=False,
                    charset='utf8mb4',
                    collation='utf8mb4_unicode_ci'
                )
                return conn
            except Error as e:
                if attempt < max_retries - 1:
                    print(f"[ConversationManager] MySQL connection failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {retry_delay}s...")
                    import time
                    time.sleep(retry_delay)
                else:
                    print(f"[ConversationManager] Failed to connect to MySQL after {max_retries} attempts: {e}")
                    raise
    
    def _create_tables(self):
        """Create database tables if they don't exist"""
        cursor = self.conn.cursor()
        
        try:
            # Messages table - stores conversation history
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    text TEXT NOT NULL,
                    intent VARCHAR(100),
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    entities JSON,
                    INDEX idx_session_timestamp (session_id, timestamp DESC),
                    INDEX idx_intent (intent)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ''')
            
            # Context table - stores long-term context (like last known location)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS context_store (
                    session_id VARCHAR(255) NOT NULL,
                    key_name VARCHAR(255) NOT NULL,
                    value JSON,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (session_id, key_name),
                    INDEX idx_session (session_id),
                    INDEX idx_key (key_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ''')
            
            # Sessions table - tracks session metadata
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id VARCHAR(255) PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ''')
            
            self.conn.commit()
        except Error as e:
            print(f"[ConversationManager] Error creating tables: {e}")
            self.conn.rollback()
            raise
        finally:
            cursor.close()
    
    def add_turn(self, session_id: str, role: str, text: str, intent: Optional[str] = None, entities: Optional[Dict] = None):
        """Add a conversation turn to history using the existing persistent connection"""
        print(f"[ConversationManager.add_turn] START: role={role}, session={session_id[:8]}..., text_len={len(text)}, intent={intent}")
        cursor = None
        try:
# Ensure connection is alive
            print(f"[ConversationManager.add_turn] Step 1: Checking connection...")
            if not self.conn.is_connected():
                print(f"[ConversationManager.add_turn] Step 1: Connection dead, reconnecting...")
                self.conn = self._connect()
                print(f"[ConversationManager.add_turn] Step 1: Reconnected successfully")
            else:
                print(f"[ConversationManager.add_turn] Step 1: Connection is alive")
            
# Create cursor
            print(f"[ConversationManager.add_turn] Step 2: Creating cursor...")
            cursor = self.conn.cursor()
            print(f"[ConversationManager.add_turn] Step 2: Cursor created")
            
# Prepare Data
            print(f"[ConversationManager.add_turn] Step 3: Preparing data...")
            entities_json = json.dumps(entities) if entities else None
            print(f"[ConversationManager.add_turn] Step 3: entities_json={'present' if entities_json else 'None'}, text_len={len(text)}")
            
# Execute Insert
            print(f"[ConversationManager.add_turn] Step 4: Executing INSERT into messages...")
            query = """
                INSERT INTO messages (session_id, role, text, intent, entities, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (session_id, role, text, intent, entities_json, datetime.now()))
            msg_id = cursor.lastrowid
            print(f"[ConversationManager.add_turn] Step 4: INSERT completed, message_id={msg_id}")
            
# Update Session Activity
            print(f"[ConversationManager.add_turn] Step 5: Updating session activity...")
            session_query = """
                INSERT INTO sessions (session_id, last_activity)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE last_activity = %s
            """
            cursor.execute(session_query, (session_id, datetime.now(), datetime.now()))
            print(f"[ConversationManager.add_turn] Step 5: Session activity updated")
            
# THE MOST IMPORTANT STEP: COMMIT
            print(f"[ConversationManager.add_turn] Step 6: COMMITTING transaction (message_id={msg_id})...")
            self.conn.commit()
            print(f"[ConversationManager.add_turn] Step 6: COMMIT completed successfully")
            
# Verify the data was saved
            print(f"[ConversationManager.add_turn] Step 7: Verifying message was saved...")
            verify_cursor = self.conn.cursor()
            verify_cursor.execute('SELECT COUNT(*) FROM messages WHERE id = %s', (msg_id,))
            count = verify_cursor.fetchone()[0]
            verify_cursor.close()
            if count > 0:
                print(f"[ConversationManager.add_turn] Step 7: VERIFICATION SUCCESS - Message ID {msg_id} found in database")
            else:
                print(f"[ConversationManager.add_turn] Step 7: VERIFICATION FAILED - Message ID {msg_id} NOT FOUND in database!")
            
            print(f"[ConversationManager.add_turn] SUCCESS: Saved {role} turn. Session: {session_id}, Message ID: {msg_id}")

        except Error as e:
            print(f"[ConversationManager.add_turn] ERROR: Database Error: {e}")
            import traceback
            traceback.print_exc()
            try:
                print(f"[ConversationManager.add_turn] ERROR: Attempting rollback...")
                self.conn.rollback()
                print(f"[ConversationManager.add_turn] ERROR: Rollback completed")
            except Exception as rollback_err:
                print(f"[ConversationManager.add_turn] ERROR: Rollback failed: {rollback_err}")
        except Exception as e:
            print(f"[ConversationManager.add_turn] ERROR: Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            try:
                self.conn.rollback()
            except:
                pass
        finally:
            print(f"[ConversationManager.add_turn] FINALLY: Closing cursor...")
            if cursor:
                try:
                    cursor.close()
                    print(f"[ConversationManager.add_turn] FINALLY: Cursor closed")
                except Exception as close_err:
                    print(f"[ConversationManager.add_turn] FINALLY: Error closing cursor: {close_err}")
            print(f"[ConversationManager.add_turn] END")
    
    def get_history(self, session_id: str, limit: int = 10) -> List[Dict]:
        """Get conversation history for a session from database"""
        cursor = self.conn.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT role, text, intent, entities, timestamp 
                FROM messages 
                WHERE session_id = %s 
                ORDER BY timestamp DESC 
                LIMIT %s
            ''', (session_id, limit))
            
            rows = cursor.fetchall()
            history = []
            
            for row in reversed(rows):  # Reverse to get chronological order
                turn = {
                    "role": row["role"],
                    "text": row["text"],
                    "intent": row["intent"],
                    "timestamp": str(row["timestamp"])
                }
                
                # Parse entities if present
                if row["entities"]:
                    try:
                        if isinstance(row["entities"], str):
                            turn["entities"] = json.loads(row["entities"])
                        else:
                            turn["entities"] = row["entities"]
                    except:
                        pass
                
                history.append(turn)
            
            return history
        finally:
            cursor.close()
    
    def get_recent_history(self, limit: int = 10) -> List[Dict]:
        """Get recent conversation history across all sessions (for cross-session context)"""
        cursor = self.conn.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT role, text, intent, entities, timestamp, session_id
                FROM messages 
                ORDER BY timestamp DESC 
                LIMIT %s
            ''', (limit,))
            
            rows = cursor.fetchall()
            history = []
            
            for row in reversed(rows):  # Reverse to get chronological order
                entities = None
                if row["entities"]:
                    try:
                        if isinstance(row["entities"], str):
                            entities = json.loads(row["entities"])
                        else:
                            entities = row["entities"]
                    except:
                        pass
                
                history.append({
                    "role": row["role"],
                    "text": row["text"],
                    "intent": row["intent"],
                    "entities": entities,
                    "timestamp": str(row["timestamp"]),
                    "session_id": row["session_id"]
                })
            
            return history
        finally:
            cursor.close()
    
    def get_context(self, session_id: str) -> Dict:
        """Get context/state for a session (from memory and database)
        
        If current session has no context, falls back to most recent context across all sessions.
        This ensures context persists even when WebSocket reconnects with a new session_id.
        """
        # Start with in-memory context
        context = dict(self.context.get(session_id, {}))
        
        # Load from database for current session
        cursor = self.conn.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT key_name, value FROM context_store 
                WHERE session_id = %s
            ''', (session_id,))
            
            rows = cursor.fetchall()
            for row in rows:
                value = row["value"]
                # Try to deserialize JSON (for dict/list values)
                if value:
                    try:
                        if isinstance(value, str):
                            context[row["key_name"]] = json.loads(value)
                        else:
                            context[row["key_name"]] = value
                    except (json.JSONDecodeError, TypeError):
                        # If not JSON, store as string
                        context[row["key_name"]] = value
        finally:
            cursor.close()
        
        # Removed global context fallback - only use session-scoped context
        return context
    
    def set_context(self, session_id: str, key: str, value: any):
        """Set a context value for a session (in memory and database)"""
        # Store in memory for fast access
        if value is None:
            # Remove from memory if None
            if key in self.context[session_id]:
                del self.context[session_id][key]
        else:
            self.context[session_id][key] = value
        
        # Store in database for persistence
        cursor = self.conn.cursor()
        try:
            if value is None:
                # If value is None, delete the key from database
                cursor.execute('''
                    DELETE FROM context_store 
                    WHERE session_id = %s AND key_name = %s
                ''', (session_id, key))
            else:
                # Serialize complex types (dict, list) to JSON
                if isinstance(value, (dict, list)):
                    value_json = json.dumps(value)
                else:
                    value_json = json.dumps(str(value))
                
                cursor.execute('''
                    INSERT INTO context_store (session_id, key_name, value, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE value = %s, updated_at = %s
                ''', (session_id, key, value_json, datetime.now(), value_json, datetime.now()))
            
            self.conn.commit()
        finally:
            cursor.close()
    
    def clear_context(self, session_id: str):
        """Clear context for a session"""
        # Clear from memory
        self.context[session_id] = {}
        
        # Clear from database
        cursor = self.conn.cursor()
        try:
            cursor.execute('DELETE FROM context_store WHERE session_id = %s', (session_id,))
            self.conn.commit()
        finally:
            cursor.close()
    
    def clear_session(self, session_id: str):
        """Clear all data for a session"""
        # Clear from memory
        if session_id in self.context:
            del self.context[session_id]
        
        # Clear from database
        cursor = self.conn.cursor()
        try:
            cursor.execute('DELETE FROM messages WHERE session_id = %s', (session_id,))
            cursor.execute('DELETE FROM context_store WHERE session_id = %s', (session_id,))
            cursor.execute('DELETE FROM sessions WHERE session_id = %s', (session_id,))
            self.conn.commit()
        finally:
            cursor.close()
    
    def get_last_known_location(self, session_id: str) -> Optional[str]:
        """Get the last known location from conversation history (ONLY from current session)"""
        cursor = self.conn.cursor(dictionary=True)
        
        try:
            # First, try to get from context_store (last_location key) - ONLY current session
            cursor.execute('''
                SELECT value, updated_at FROM context_store 
                WHERE session_id = %s AND key_name = 'last_location' AND value IS NOT NULL
                ORDER BY updated_at DESC 
                LIMIT 1
            ''', (session_id,))
            row = cursor.fetchone()
            if row and row["value"]:
                location = row["value"]
                if isinstance(location, str):
                    try:
                        location = json.loads(location)
                    except:
                        pass
                return str(location) if not isinstance(location, str) else location
            
            # If not found in context_store, check recent messages from CURRENT SESSION ONLY
            cursor.execute('''
                SELECT text, entities, intent FROM messages 
                WHERE session_id = %s AND intent = 'weather_query'
                ORDER BY timestamp DESC 
                LIMIT 50
            ''', (session_id,))
            
            rows = cursor.fetchall()
            for row in rows:
                # Try to extract location from entities first (most reliable)
                if row["entities"]:
                    try:
                        if isinstance(row["entities"], str):
                            entities = json.loads(row["entities"])
                        else:
                            entities = row["entities"]
                        if entities.get("location"):
                            location = entities["location"]
                            # Store it for current session for future use
                            self.set_context(session_id, "last_location", location)
                            return location
                    except Exception as e:
                        print(f"[ConversationManager] Error parsing entities: {e}")
                        pass
                
                # Try to extract location from text using improved regex
                import re
                text = row["text"]
                # Better pattern: matches "in Frankfurt", "for Frankfurt", "at Frankfurt", or "Frankfurt" at start
                location_match = re.search(r'\b(?:in|for|at)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b', text)
                if location_match:
                    location = location_match.group(1)
                    # Basic validation: skip common words that might match
                    skip_words = {"Friday", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Today", "Tomorrow"}
                    if location not in skip_words:
                        # Store it for current session for future use
                        self.set_context(session_id, "last_location", location)
                        return location
                # Also try matching location at start of sentence
                location_match = re.search(r'^([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)', text)
                if location_match:
                    location = location_match.group(1)
                    skip_words = {"Friday", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Today", "Tomorrow", "What", "Tell", "Is", "Will", "Can", "Show"}
                    if location not in skip_words and len(location) > 2:
                        self.set_context(session_id, "last_location", location)
                        return location
            
            return None
        finally:
            cursor.close()
    
    def get_last_weather_query(self, session_id: str) -> Optional[Dict]:
        """Get the last weather query details from history"""
        cursor = self.conn.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT text, entities FROM messages 
                WHERE session_id = %s 
                AND intent = 'weather_query'
                ORDER BY timestamp DESC 
                LIMIT 1
            ''', (session_id,))
            
            row = cursor.fetchone()
            if row and row["entities"]:
                try:
                    if isinstance(row["entities"], str):
                        return json.loads(row["entities"])
                    else:
                        return row["entities"]
                except:
                    pass
            
            return None
        finally:
            cursor.close()
