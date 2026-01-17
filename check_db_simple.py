import sqlite3

db_path = 'data/assistant.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute('SELECT COUNT(*) FROM messages')
count = c.fetchone()[0]
print(f'Total messages: {count}')

if count > 0:
    c.execute('SELECT id, session_id, role, text, intent, timestamp FROM messages ORDER BY id DESC LIMIT 10')
    rows = c.fetchall()
    print(f'\nLast {len(rows)} messages:')
    for row in rows:
        print(f'ID {row[0]}: [{row[5]}] session={row[1][:12]}... role={row[2]:8} intent={row[4] or "N/A":15}')
        print(f'  text: {row[3][:70]}')

# Check for recent session
c.execute("SELECT COUNT(*) FROM messages WHERE session_id LIKE '9bce068f%'")
recent_count = c.fetchone()[0]
print(f'\nMessages with session 9bce068f: {recent_count}')

conn.close()

