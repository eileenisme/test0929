import os
import io
import base64
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
import qrcode

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-key-test0929-orders")

DB_FILE = os.path.join(os.path.dirname(__file__), "orders.db")

# 若在雲端部署環境且資料庫檔案尚未存在，自動初始化資料庫與測試資料
if not os.path.exists(DB_FILE):
    try:
        from init_db import init_db
        init_db()
    except Exception as e:
        print(f"初始化資料庫失敗: {e}")

# 管理員帳密（驗收條件 10）
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

# 登入保護裝飾器 (需求 5: 管理員登入後可維護客戶、商品、訂單)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            flash("請先登入管理員帳號！", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# ==================== 認證功能 (Auth) ====================
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("orders_list"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            session["username"] = username
            flash("管理員登入成功！歡迎使用訂單管理系統。", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("orders_list"))
        else:
            flash("帳號或密碼錯誤，請重新輸入！", "error")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("已成功登出系統。", "info")
    return redirect(url_for("login"))

@app.route("/")
def index():
    if session.get("logged_in"):
        return redirect(url_for("orders_list"))
    return redirect(url_for("login"))

# ==================== 訂單管理 (Orders) ====================
# 需求 8: 訂單狀態（處理中 / 已出貨 / 已完成 / 已取消），可在列表直接更新
@app.route("/orders")
@login_required
def orders_list():
    status_filter = request.args.get("status")
    conn = get_db_connection()
    
    query = """
        SELECT o.order_id, o.customer_id, o.order_date, o.status, o.sales_person,
               c.name AS customer_name,
               COUNT(oi.product_id) AS item_count,
               COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_amount
        FROM orders o
        LEFT JOIN customer c ON o.customer_id = c.customer_id
        LEFT JOIN order_item oi ON o.order_id = oi.order_id
    """
    params = []
    if status_filter:
        query += " WHERE o.status = ?"
        params.append(status_filter)
        
    query += " GROUP BY o.order_id ORDER BY o.order_date DESC, o.order_id DESC"
    
    orders = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("orders_list.html", orders=orders, current_status=status_filter)

# 需求 6 & 7: 新增訂單（客戶下拉選單、商品勾選與數量、存下單當下價格）
@app.route("/orders/new", methods=["GET", "POST"])
@login_required
def new_order():
    conn = get_db_connection()
    if request.method == "POST":
        order_id = request.form.get("order_id", "").strip()
        customer_id = request.form.get("customer_id", "").strip()
        order_date = request.form.get("order_date", "").strip()
        sales_person = request.form.get("sales_person", "").strip()
        status = request.form.get("status", "處理中").strip()
        product_ids = request.form.getlist("product_ids")

        if not order_id or not customer_id or not sales_person or not order_date:
            flash("請填寫所有必填欄位！", "danger")
            conn.close()
            return redirect(url_for("new_order"))

        if not product_ids:
            flash("請至少勾選一項訂購商品！", "danger")
            conn.close()
            return redirect(url_for("new_order"))

        try:
            # 檢查訂單編號是否重複
            existing = conn.execute("SELECT order_id FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if existing:
                flash(f"訂單編號 {order_id} 已存在，請使用其他編號！", "danger")
                conn.close()
                return redirect(url_for("new_order"))

            # 插入訂單主檔
            conn.execute("""
                INSERT INTO orders (order_id, customer_id, order_date, status, sales_person)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, customer_id, order_date, status, sales_person))

            # 查詢勾選商品目前的單價，寫入 order_item (需求 7: 保存下單當時單價)
            for pid in product_ids:
                qty_str = request.form.get(f"qty_{pid}", "1").strip()
                try:
                    qty = int(qty_str)
                    if qty <= 0:
                        qty = 1
                except ValueError:
                    qty = 1

                product = conn.execute("SELECT unit_price FROM product WHERE product_id = ?", (pid,)).fetchone()
                if product:
                    current_price = product["unit_price"]
                    conn.execute("""
                        INSERT INTO order_item (order_id, product_id, quantity, unit_price)
                        VALUES (?, ?, ?, ?)
                    """, (order_id, pid, qty, current_price))

            conn.commit()
            flash(f"訂單 {order_id} 建立成功！已依下單時價格保存明細。", "success")
            return redirect(url_for("order_detail", order_id=order_id))
        except Exception as e:
            conn.rollback()
            flash(f"建立訂單失敗：{str(e)}", "danger")
        finally:
            conn.close()

    # GET 頁面
    customers = conn.execute("SELECT customer_id, name, phone FROM customer ORDER BY customer_id").fetchall()
    products = conn.execute("SELECT product_id, name, unit_price, stock, category FROM product ORDER BY product_id").fetchall()
    conn.close()

    today = datetime.now().strftime("%Y-%m-%d")
    default_order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    return render_template("new_order.html", 
                           customers=customers, 
                           products=products, 
                           today=today, 
                           default_order_id=default_order_id)

# 需求 8: 在列表直接更新訂單狀態
@app.route("/orders/<order_id>/status", methods=["POST"])
@login_required
def update_order_status(order_id):
    new_status = request.form.get("status", "").strip()
    valid_statuses = ["處理中", "已出貨", "已完成", "已取消"]
    if new_status in valid_statuses:
        conn = get_db_connection()
        conn.execute("UPDATE orders SET status = ? WHERE order_id = ?", (new_status, order_id))
        conn.commit()
        conn.close()
        flash(f"訂單 {order_id} 狀態已即時更新為「{new_status}」！", "success")
    else:
        flash("不支援的訂單狀態！", "danger")
    return redirect(request.referrer or url_for("orders_list"))

# 刪除訂單
@app.route("/orders/<order_id>/delete", methods=["POST"])
@login_required
def delete_order(order_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
    conn.commit()
    conn.close()
    flash(f"訂單 {order_id} 已成功刪除！", "info")
    return redirect(url_for("orders_list"))

# 需求 9: 每張訂單有專屬頁面 /order/<訂單編號>, 並產生出貨單 QRCode
@app.route("/order/<order_id>")
@login_required
def order_detail(order_id):
    conn = get_db_connection()
    # 查詢訂單與客戶資訊
    order = conn.execute("""
        SELECT o.order_id, o.customer_id, o.order_date, o.status, o.sales_person,
               c.name AS customer_name, c.phone AS customer_phone, c.address AS customer_address
        FROM orders o
        LEFT JOIN customer c ON o.customer_id = c.customer_id
        WHERE o.order_id = ?
    """, (order_id,)).fetchone()

    if not order:
        conn.close()
        abort(404, description="找不到指定的訂單")

    # 查詢訂單明細（以 order_item 的 unit_price 為準，即使 product 改價亦不受影響）
    items = conn.execute("""
        SELECT oi.product_id, oi.quantity, oi.unit_price,
               (oi.quantity * oi.unit_price) AS subtotal,
               p.name AS product_name, p.category
        FROM order_item oi
        LEFT JOIN product p ON oi.product_id = p.product_id
        WHERE oi.order_id = ?
        ORDER BY oi.product_id
    """, (order_id,)).fetchall()
    conn.close()

    total_amount = sum(item["subtotal"] for item in items)
    total_qty = sum(item["quantity"] for item in items)

    # 產生專屬出貨單 QRCode (編碼內容為該訂單的完整 URL)
    target_url = request.url
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1e293b", back_color="#ffffff")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qrcode_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return render_template("order_detail.html",
                           order=order,
                           items=items,
                           total_amount=total_amount,
                           total_qty=total_qty,
                           qrcode_b64=qrcode_b64)

# ==================== 客戶維護 (Customers) ====================
# 需求 5: 管理員維護客戶
@app.route("/customers")
@login_required
def customers_list():
    conn = get_db_connection()
    customers = conn.execute("SELECT * FROM customer ORDER BY customer_id").fetchall()
    conn.close()
    return render_template("customers_list.html", customers=customers)

@app.route("/customers/new", methods=["POST"])
@login_required
def customer_new():
    cid = request.form.get("customer_id", "").strip()
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()

    if not cid or not name or not phone or not address:
        flash("請完整填寫客戶資料！", "danger")
        return redirect(url_for("customers_list"))

    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO customer (customer_id, name, phone, address) VALUES (?, ?, ?, ?)",
                     (cid, name, phone, address))
        conn.commit()
        flash(f"客戶 {name} ({cid}) 新增成功！", "success")
    except Exception as e:
        flash(f"新增失敗，編號可能已重複：{str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("customers_list"))

@app.route("/customers/edit", methods=["POST"])
@login_required
def customer_edit_post():
    cid = request.form.get("customer_id", "").strip()
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()

    conn = get_db_connection()
    try:
        conn.execute("UPDATE customer SET name = ?, phone = ?, address = ? WHERE customer_id = ?",
                     (name, phone, address, cid))
        conn.commit()
        flash(f"客戶 {cid} 資料更新成功！", "success")
    except Exception as e:
        flash(f"更新失敗：{str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("customers_list"))

@app.route("/customers/<customer_id>/delete", methods=["POST"])
@login_required
def customer_delete(customer_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM customer WHERE customer_id = ?", (customer_id,))
        conn.commit()
        flash(f"客戶 {customer_id} 已刪除！", "info")
    except sqlite3.IntegrityError:
        flash(f"無法刪除客戶 {customer_id}：此客戶尚有現存訂單紀錄！", "danger")
    except Exception as e:
        flash(f"刪除失敗：{str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("customers_list"))

# ==================== 商品維護 (Products) ====================
# 需求 5: 管理員維護商品
@app.route("/products")
@login_required
def products_list():
    conn = get_db_connection()
    products = conn.execute("SELECT * FROM product ORDER BY product_id").fetchall()
    conn.close()
    return render_template("products_list.html", products=products)

@app.route("/products/new", methods=["POST"])
@login_required
def product_new():
    pid = request.form.get("product_id", "").strip()
    name = request.form.get("name", "").strip()
    price = request.form.get("unit_price", "0").strip()
    stock = request.form.get("stock", "0").strip()
    category = request.form.get("category", "").strip()

    try:
        price_val = int(price)
        stock_val = int(stock)
        if price_val < 0 or stock_val < 0:
            raise ValueError()
    except ValueError:
        flash("單價與庫存必須為非負整數！", "danger")
        return redirect(url_for("products_list"))

    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO product (product_id, name, unit_price, stock, category) VALUES (?, ?, ?, ?, ?)",
                     (pid, name, price_val, stock_val, category))
        conn.commit()
        flash(f"商品 {name} ({pid}) 新增成功！", "success")
    except Exception as e:
        flash(f"新增失敗，編號可能已重複：{str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("products_list"))

@app.route("/products/edit", methods=["POST"])
@login_required
def product_edit_post():
    pid = request.form.get("product_id", "").strip()
    name = request.form.get("name", "").strip()
    price = request.form.get("unit_price", "0").strip()
    stock = request.form.get("stock", "0").strip()
    category = request.form.get("category", "").strip()

    try:
        price_val = int(price)
        stock_val = int(stock)
        if price_val < 0 or stock_val < 0:
            raise ValueError()
    except ValueError:
        flash("單價與庫存必須為非負整數！", "danger")
        return redirect(url_for("products_list"))

    conn = get_db_connection()
    try:
        conn.execute("UPDATE product SET name = ?, unit_price = ?, stock = ?, category = ? WHERE product_id = ?",
                     (name, price_val, stock_val, category, pid))
        conn.commit()
        flash(f"商品 {pid} 資料已更新！(注意：已成立的歷史訂單價格不受影響)", "success")
    except Exception as e:
        flash(f"更新失敗：{str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("products_list"))

@app.route("/products/<product_id>/delete", methods=["POST"])
@login_required
def product_delete(product_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM product WHERE product_id = ?", (product_id,))
        conn.commit()
        flash(f"商品 {product_id} 已刪除！", "info")
    except sqlite3.IntegrityError:
        flash(f"無法刪除商品 {product_id}：已有歷史訂單購買過此商品！", "danger")
    except Exception as e:
        flash(f"刪除失敗：{str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("products_list"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)
