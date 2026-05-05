import sqlite3
conn = sqlite3.connect("data/butler.db")
conn.row_factory = sqlite3.Row
print("=== user_memory ===")
for r in conn.execute("SELECT * FROM user_memory").fetchall():
    print(f"  [{r['key']}] {r['value'][:80]}")
print("\n=== chat_history (last 5) ===")
for r in conn.execute("SELECT * FROM chat_history ORDER BY id DESC LIMIT 5").fetchall():
    print(f"  {r['role']}: {r['content'][:60]}")
conn.close()
