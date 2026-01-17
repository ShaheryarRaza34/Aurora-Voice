import sqlite3

db_path = '/app/data/assistant.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute('SELECT COUNT(*) FROM messages')
count = c.fetchone()[0]
print(f'Total messages: {count}')

c.execute('SELECT id, session_id, role, text, intent, timestamp FROM messages ORDER BY id')
rows = c.fetchall()
print(f'\nAll {len(rows)} messages:')
for row in rows:
    print(f'  ID {row[0]}: session={row[1][:12]}... role={row[2]:8} intent={row[4] or "N/A":15} text={row[3][:50]}')
    print(f'    timestamp: {row[5]}')

# Check for the specific session
c.execute("SELECT COUNT(*) FROM messages WHERE session_id LIKE '6bc1d5f2%'")
match_count = c.fetchone()[0]
print(f'\nMessages with session 6bc1d5f2: {match_count}')

conn.close()

