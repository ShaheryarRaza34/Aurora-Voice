import sqlite3
import os

db_path = 'data/assistant.db'
print(f"Database path: {os.path.abspath(db_path)}")
print(f"File exists: {os.path.exists(db_path)}")
if os.path.exists(db_path):
    print(f"File size: {os.path.getsize(db_path)} bytes")

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check all messages
c.execute('SELECT COUNT(*) FROM messages')
msg_count = c.fetchone()[0]
print(f"\nTotal messages: {msg_count}")

if msg_count > 0:
    print("\nAll messages:")
    c.execute('SELECT id, session_id, role, text, intent, timestamp FROM messages ORDER BY timestamp DESC')
    for row in c.fetchall():
        print(f"  ID: {row[0]} | Session: {row[1][:8]}... | Role: {row[2]:8} | Intent: {row[4] or 'N/A':15} | Text: {row[3][:60]}")
        print(f"    Timestamp: {row[5]}")

# Check sessions
c.execute('SELECT COUNT(*) FROM sessions')
sess_count = c.fetchone()[0]
print(f"\nTotal sessions: {sess_count}")

# Check context
c.execute('SELECT COUNT(*) FROM context_store')
ctx_count = c.fetchone()[0]
print(f"Total context entries: {ctx_count}")

conn.close()

