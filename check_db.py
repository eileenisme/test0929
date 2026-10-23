import sqlite3
import os
import sys

# 自動處理 Windows 繁體中文終端機編碼，防止亂碼與崩潰
if sys.platform == "win32":
    try:
        # 強制標準輸出為 utf-8
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

DB_FILE = "orders.db"

def print_separator(title):
    print("\n" + "=" * 25 + f" 【{title}】 " + "=" * 25)

def check_database():
    if not os.path.exists(DB_FILE):
        print(f"[錯誤] 找不到資料庫檔案：{DB_FILE}，請先執行 init_db.py！")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. 查詢 customer
    print_separator("1. customer 客戶資料表")
    cursor.execute("SELECT * FROM customer;")
    rows = cursor.fetchall()
    print(f"{'客戶編號':<8} | {'客戶姓名':<8} | {'連絡電話':<15} | {'建檔日期':<12} | {'地址'}")
    print("-" * 80)
    for r in rows:
        print(f"{r['customer_id']:<8} | {r['name']:<8} | {r['phone']:<15} | {r['created_date']:<12} | {r['address']}")

    # 2. 查詢 product
    print_separator("2. product 商品資料表")
    cursor.execute("SELECT * FROM product;")
    rows = cursor.fetchall()
    print(f"{'商品編號':<8} | {'商品名稱':<25} | {'單價':<6} | {'庫存':<6} | {'商品分類'}")
    print("-" * 80)
    for r in rows:
        print(f"{r['product_id']:<8} | {r['name']:<25} | {r['unit_price']:<6} | {r['stock']:<6} | {r['category']}")

    # 3. 查詢 orders
    print_separator("3. orders 訂單資料表")
    cursor.execute("""
    SELECT o.order_id, o.order_date, o.status, o.sales_person, c.name AS customer_name
    FROM orders o
    JOIN customer c ON o.customer_id = c.customer_id;
    """)
    rows = cursor.fetchall()
    print(f"{'訂單編號':<14} | {'訂購客戶':<8} | {'訂單日期':<12} | {'狀態':<8} | {'業務人員'}")
    print("-" * 65)
    for r in rows:
        print(f"{r['order_id']:<14} | {r['customer_name']:<8} | {r['order_date']:<12} | {r['status']:<8} | {r['sales_person']}")

    # 4. 查詢 order_item
    print_separator("4. order_item 訂單明細資料表")
    cursor.execute("""
    SELECT oi.order_id, oi.product_id, p.name AS product_name, oi.quantity, oi.unit_price,
           (oi.quantity * oi.unit_price) AS subtotal
    FROM order_item oi
    JOIN product p ON oi.product_id = p.product_id
    ORDER BY oi.order_id, oi.product_id;
    """)
    rows = cursor.fetchall()
    print(f"{'訂單編號':<14} | {'商品編號':<8} | {'商品名稱':<25} | {'數量':<4} | {'下單單價':<8} | {'小計'}")
    print("-" * 85)
    for r in rows:
        print(f"{r['order_id']:<14} | {r['product_id']:<8} | {r['product_name']:<25} | {r['quantity']:<4} | {r['unit_price']:<8} | {r['subtotal']}")

    # 5. 彙整統計各訂單總金額
    print_separator("訂單總額統計（驗證多項商品案例）")
    cursor.execute("""
    SELECT o.order_id, c.name AS customer_name, COUNT(oi.product_id) AS item_count,
           SUM(oi.quantity * oi.unit_price) AS total_amount
    FROM orders o
    JOIN customer c ON o.customer_id = c.customer_id
    JOIN order_item oi ON o.order_id = oi.order_id
    GROUP BY o.order_id;
    """)
    rows = cursor.fetchall()
    print(f"{'訂單編號':<14} | {'訂購客戶':<8} | {'商品項數':<8} | {'訂單總金額'}")
    print("-" * 55)
    for r in rows:
        print(f"{r['order_id']:<14} | {r['customer_name']:<8} | {r['item_count']:<8} | NT$ {r['total_amount']:,}")

    conn.close()

if __name__ == "__main__":
    check_database()
