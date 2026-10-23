import sqlite3
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

DB_FILE = "orders.db"

def init_db():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    # 1. customer (客戶編號 PK、名稱、電話、地址)
    cursor.execute("""
    CREATE TABLE customer (
        customer_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        address TEXT NOT NULL
    );
    """)

    # 2. product (商品編號 PK、名稱、單價、庫存、分類)
    cursor.execute("""
    CREATE TABLE product (
        product_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
        stock INTEGER NOT NULL CHECK (stock >= 0),
        category TEXT NOT NULL
    );
    """)

    # 3. orders (訂單編號 PK、客戶編號 FK、訂單日期、狀態、業務人員)
    cursor.execute("""
    CREATE TABLE orders (
        order_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        order_date TEXT NOT NULL,
        status TEXT NOT NULL,
        sales_person TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customer (customer_id) ON DELETE RESTRICT ON UPDATE CASCADE
    );
    """)

    # 4. order_item (訂單編號 FK、商品編號 FK、數量、單價)
    cursor.execute("""
    CREATE TABLE order_item (
        order_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
        PRIMARY KEY (order_id, product_id),
        FOREIGN KEY (order_id) REFERENCES orders (order_id) ON DELETE CASCADE ON UPDATE CASCADE,
        FOREIGN KEY (product_id) REFERENCES product (product_id) ON DELETE RESTRICT ON UPDATE CASCADE
    );
    """)

    # 插入測試資料 (繁體中文各 5 筆)
    customers = [
        ("C001", "陳建宏", "0912-345-678", "台北市信義區忠孝東路五段100號"),
        ("C002", "林怡萱", "0923-456-789", "新北市板橋區縣民大道二段7號"),
        ("C003", "黃品睿", "0934-567-890", "台中市西屯區台灣大道三段99號"),
        ("C004", "張雅婷", "0945-678-901", "台南市東區中華東路一段366號"),
        ("C005", "王家豪", "0956-789-012", "高雄市苓雅區五福三路59號")
    ]
    cursor.executemany("INSERT INTO customer VALUES (?, ?, ?, ?);", customers)

    products = [
        ("P101", "台灣極品凍頂烏龍茶 (75g)", 450, 120, "茶葉飲品"),
        ("P102", "手工日曬關廟麵 (1kg)", 180, 250, "乾貨主食"),
        ("P103", "純天然野生龍眼蜂蜜 (500g)", 680, 60, "養生食品"),
        ("P104", "手炒黑糖鳳梨酥禮盒 (12入)", 520, 80, "伴手禮盒"),
        ("P105", "古法釀造純黑豆蔭油 (420ml)", 260, 150, "傳統醬料")
    ]
    cursor.executemany("INSERT INTO product VALUES (?, ?, ?, ?, ?);", products)

    orders = [
        ("ORD-20261001", "C001", "2026-10-01", "已出貨", "張小明"),
        ("ORD-20261002", "C002", "2026-10-02", "已完成", "李佩珊"),
        ("ORD-20261003", "C003", "2026-10-05", "處理中", "張小明"),
        ("ORD-20261004", "C004", "2026-10-10", "已出貨", "王大偉"),
        ("ORD-20261005", "C005", "2026-10-12", "已取消", "李佩珊")
    ]
    cursor.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?);", orders)

    order_items = [
        # ORD-20261001 (多項商品案例：P101, P103, P104)
        ("ORD-20261001", "P101", 2, 450),
        ("ORD-20261001", "P103", 1, 680),
        ("ORD-20261001", "P104", 3, 520),
        # ORD-20261002 (多項商品案例：P102, P105)
        ("ORD-20261002", "P102", 5, 180),
        ("ORD-20261002", "P105", 2, 260),
        # ORD-20261003
        ("ORD-20261003", "P101", 1, 450),
        # ORD-20261004
        ("ORD-20261004", "P104", 2, 520),
        # ORD-20261005
        ("ORD-20261005", "P105", 4, 260)
    ]
    cursor.executemany("INSERT INTO order_item VALUES (?, ?, ?, ?);", order_items)

    conn.commit()
    conn.close()
    print(f"[OK] 資料庫 {DB_FILE} 建立並初始化成功！")

if __name__ == "__main__":
    init_db()
