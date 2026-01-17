import sqlite3

conn = sqlite3.connect('data/assistant.db')
c = conn.cursor()

# Count records
c.execute('SELECT COUNT(*) FROM messages')
msg_count = c.fetchone()[0]

c.execute('SELECT COUNT(*) FROM context_store')
ctx_count = c.fetchone()[0]

c.execute('SELECT COUNT(*) FROM sessions')
sess_count = c.fetchone()[0]

print(f"Total messages: {msg_count}")
print(f"Context entries: {ctx_count}")
print(f"Sessions: {sess_count}")

print("\nRecent messages:")
c.execute('SELECT session_id, role, text, intent, timestamp FROM messages ORDER BY timestamp DESC LIMIT 5')
for row in c.fetchall():
    session_short = row[0][:8] + "..."
    role = row[1]
    text = row[2][:50] + "..." if len(row[2]) > 50 else row[2]
    intent = row[3] or "N/A"
    timestamp = row[4]
    print(f"  [{timestamp}] {session_short} | {role:8} | {intent:15} | {text}")

print("\nContext entries:")
c.execute('SELECT session_id, key, value FROM context_store ORDER BY updated_at DESC LIMIT 5')
for row in c.fetchall():
    session_short = row[0][:8] + "..." if row[0] else "N/A"
    key = row[1]
    value = str(row[2])[:50] + "..." if row[2] and len(str(row[2])) > 50 else (str(row[2]) if row[2] else "NULL")
    print(f"  {session_short} | {key:20} | {value}")

conn.close()

