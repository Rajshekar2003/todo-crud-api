import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "report.db"

PRODUCTS = ["Widget", "Gadget", "Gizmo", "Doohickey", "Thingamajig", "Contraption"]
CUSTOMERS = [
    "Alice Johnson", "Bob Smith", "Carla Reyes", "David Lee", "Priya Nair",
    "Marco Rossi", "Fatima Khan", "Tom Walker", "Yuki Tanaka", "Sara Ahmed",
]

def seed():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT NOT NULL,
            product TEXT NOT NULL,
            amount REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("DELETE FROM orders")

    now = datetime.now()
    rows = []
    for _ in range(200):
        customer = random.choice(CUSTOMERS)
        product = random.choice(PRODUCTS)
        amount = round(random.uniform(5, 200), 2)
        days_ago = random.randint(0, 29)
        created_at = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        rows.append((customer, product, amount, created_at))

    cur.executemany(
        "INSERT INTO orders (customer, product, amount, created_at) VALUES (?, ?, ?, ?)",
        rows,
    )

    conn.commit()

    count = cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    print(f"Seeded {count} orders into {DB_PATH}")

    conn.close()

if __name__ == "__main__":
    seed()
