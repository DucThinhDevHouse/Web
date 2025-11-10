import pandas as pd
import sqlite3

# ---- ??c d? li?u CSV ----
csv_file = "hotels.csv"   # ??t file CSV c?a b?n cùng th? m?c v?i file Python
df = pd.read_csv(csv_file)

# ---- K?t n?i / t?o database ----
conn = sqlite3.connect("hotel.db")
cursor = conn.cursor()

# ---- T?o b?ng (n?u ch?a có) ----
cursor.execute("""
CREATE TABLE IF NOT EXISTS hotels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    city TEXT,
    price REAL,
    stars INTEGER,
    rating REAL,
    image_url TEXT,
    buffet BOOLEAN,
    pool BOOLEAN,
    sea BOOLEAN,
    view BOOLEAN,
    review TEXT
)
""")

# ---- Xóa d? li?u c? ----
cursor.execute("DELETE FROM hotels")

# ---- Chèn d? li?u t? CSV vào database ----
for _, row in df.iterrows():
    cursor.execute("""
        INSERT INTO hotels (name, city, price, stars, rating, image_url, buffet, pool, sea, view, review)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row["name"],
        row["city"],
        float(row["price"]),
        int(row["stars"]),
        float(row["rating"]),
        row["image_url"],
        bool(row["buffet"]),
        bool(row["pool"]),
        bool(row["sea"]),
        bool(row["view"]),
        row["review"]
    ))

conn.commit()
conn.close()

print(f" ?ã nh?p {len(df)} khach san tu '{csv_file}' vao database 'hotel.db'")
