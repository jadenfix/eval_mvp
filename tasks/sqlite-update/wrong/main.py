import json, sqlite3, sys
updates = json.load(sys.stdin)['updates']
with sqlite3.connect(sys.argv[1]) as conn:
    try:
        conn.execute('BEGIN')
        for key, delta in updates:
            cursor = conn.execute('UPDATE accounts SET balance = balance + ? WHERE id = ?', (delta, key))
            conn.commit()
            if cursor.rowcount != 1:
                raise ValueError()
        conn.commit()
        answer = dict(conn.execute('SELECT id, balance FROM accounts'))
    except ValueError:
        conn.rollback()
        answer = {'error': 'unknown account'}
print(json.dumps(answer))
