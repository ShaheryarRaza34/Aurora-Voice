# MySQL Connection Information for Aurora Voice Assistant

## Connection Details

To connect to the MySQL database from a database client (MySQL Workbench, DBeaver, phpMyAdmin, etc.):

**Host:** `localhost` or `127.0.0.1`  
**Port:** `3307` (Note: This is the host port, not 3306)  
**Username:** `root`  
**Password:** `Shary1769175!`  
**Database:** `aurora_assistant`

## Connection String Examples

### MySQL Workbench / Command Line
```
Host: localhost
Port: 3307
Username: root
Password: Shary1769175!
Default Schema: aurora_assistant
```

### JDBC URL (for DBeaver, etc.)
```
jdbc:mysql://localhost:3307/aurora_assistant?useSSL=false
```

### Python (mysql-connector-python)
```python
import mysql.connector

conn = mysql.connector.connect(
    host='localhost',
    port=3307,
    user='root',
    password='Shary1769175!',
    database='aurora_assistant'
)
```

## Database Tables

The database contains three main tables:
1. **messages** - Stores conversation history (session_id, role, text, intent, entities, timestamp)
2. **context_store** - Stores conversation context (session_id, key_name, value, updated_at)
3. **sessions** - Tracks session metadata (session_id, created_at, last_activity)

## Quick Test Query

```sql
-- Check message count
SELECT COUNT(*) FROM messages;

-- View recent messages
SELECT * FROM messages ORDER BY timestamp DESC LIMIT 10;

-- View context entries
SELECT * FROM context_store ORDER BY updated_at DESC LIMIT 10;
```

## Troubleshooting

If you cannot connect:
1. Make sure Docker containers are running: `docker-compose ps`
2. Verify MySQL is healthy: `docker-compose ps` should show MySQL as "healthy"
3. Check if port 3307 is available: The port mapping is `3307:3306` (host:container)
4. Try connecting from command line first: `mysql -h localhost -P 3307 -u root -p`

