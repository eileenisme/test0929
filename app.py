import os
import io
import re
import base64
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
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

@app.template_filter("comma")
def comma_filter(val):
    try:
        if val is None or val == "":
            return "0"
        return f"{int(round(float(val))):,}"
    except (ValueError, TypeError):
        return str(val)

# 管理員帳號與 Werkzeug 雜湊密碼（程式碼與畫面皆不得出現明碼）
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
# 預設為 admin123 雜湊值 (scrypt)
ADMIN_PASSWORD_HASH = os.environ.get(
    "ADMIN_PASSWORD_HASH",
    "scrypt:32768:8:1$CpOhQfDwMhSznhNk$231db8a8a6a1691d6fd8d5eafef9df9a0720e7369b0b7f62fe6a832f6222cae7031bf29f64592d615bc82d51dd5c518658c475db18a4a949a80fd416442df71c"
)

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

# 後台權限保護裝飾器 (需求 2: 後台所有頁面需登入(session)且角色為管理員才能進入)
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in") or session.get("role") != "admin":
            flash("此頁面僅限管理員存取，請先以管理員身分登入！", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# 保留相容別名
login_required = admin_required

# ==================== 認證功能 (Auth) ====================
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in") and session.get("role") == "admin":
        return redirect(url_for("orders_list"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        # 使用 werkzeug check_password_hash 進行安全密碼雜湊比對
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["logged_in"] = True
            session["username"] = username
            session["role"] = "admin"
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
    if session.get("logged_in") and session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("login"))

# ==================== 營運儀表板 (Dashboard) ====================
@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db_connection()

    # 1. KPI 卡片計算 (排除狀態為「已取消」的訂單)
    kpi_query = """
        SELECT 
            COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_revenue,
            COUNT(DISTINCT o.order_id) AS valid_order_count,
            (SELECT COUNT(*) FROM customer) AS total_customers
        FROM orders o
        JOIN order_item oi ON o.order_id = oi.order_id
        WHERE o.status != '已取消'
    """
    kpi_row = conn.execute(kpi_query).fetchone()
    
    total_revenue = kpi_row["total_revenue"] if kpi_row else 0
    valid_order_count = kpi_row["valid_order_count"] if kpi_row else 0
    total_customers = kpi_row["total_customers"] if kpi_row else 0
    avg_order_value = round(total_revenue / valid_order_count) if valid_order_count > 0 else 0

    # 2. 每月營收趨勢 (折線圖，排除已取消訂單，依月份由近到遠或時間軸排序)
    monthly_query = """
        SELECT strftime('%Y-%m', o.order_date) AS month,
               COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS revenue
        FROM orders o
        JOIN order_item oi ON o.order_id = oi.order_id
        WHERE o.status != '已取消'
        GROUP BY month
        ORDER BY month ASC
    """
    monthly_rows = conn.execute(monthly_query).fetchall()
    monthly_labels = [row["month"] for row in monthly_rows]
    monthly_revenues = [row["revenue"] for row in monthly_rows]

    # 3. 訂單狀態分布 (環圈圖，包含所有狀態以完整呈現訂單生命週期狀態)
    status_query = """
        SELECT status, COUNT(*) AS count
        FROM orders
        GROUP BY status
        ORDER BY count DESC
    """
    status_rows = conn.execute(status_query).fetchall()
    # 預設狀態清單與顏色配置
    status_labels = [row["status"] for row in status_rows]
    status_counts = [row["count"] for row in status_rows]

    # 4. 熱銷商品 Top 5 (排除已取消訂單：商品名稱、售出數量、營收)
    top_products_query = """
        SELECT p.product_id, p.name AS product_name, p.category,
               COALESCE(SUM(oi.quantity), 0) AS total_quantity,
               COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_revenue
        FROM order_item oi
        JOIN orders o ON oi.order_id = o.order_id
        JOIN product p ON oi.product_id = p.product_id
        WHERE o.status != '已取消'
        GROUP BY p.product_id, p.name
        ORDER BY total_revenue DESC, total_quantity DESC
        LIMIT 5
    """
    top_products = conn.execute(top_products_query).fetchall()

    # 5. 客戶消費排行 Top 5 (排除已取消訂單：客戶名稱、訂單數、消費金額)
    top_customers_query = """
        SELECT c.customer_id, c.name AS customer_name, c.phone,
               COUNT(DISTINCT o.order_id) AS order_count,
               COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_spent
        FROM orders o
        JOIN customer c ON o.customer_id = c.customer_id
        JOIN order_item oi ON o.order_id = oi.order_id
        WHERE o.status != '已取消'
        GROUP BY c.customer_id, c.name
        ORDER BY total_spent DESC, order_count DESC
        LIMIT 5
    """
    top_customers = conn.execute(top_customers_query).fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        total_revenue=total_revenue,
        valid_order_count=valid_order_count,
        avg_order_value=avg_order_value,
        total_customers=total_customers,
        monthly_labels=monthly_labels,
        monthly_revenues=monthly_revenues,
        status_labels=status_labels,
        status_counts=status_counts,
        top_products=top_products,
        top_customers=top_customers
    )

# ==================== 訂單管理 (Orders) ====================
# 需求 8: 訂單狀態（處理中 / 已出貨 / 已完成 / 已取消），可在列表直接更新
@app.route("/orders")
@admin_required
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

# 需求 4, 5, 6, 7: 新增訂單（客戶/商品下拉選單、SO+數字格式驗證、數量正整數校驗）
@app.route("/orders/new", methods=["GET", "POST"])
@admin_required
def new_order():
    conn = get_db_connection()
    if request.method == "POST":
        order_id = request.form.get("order_id", "").strip()
        customer_id = request.form.get("customer_id", "").strip()
        order_date = request.form.get("order_date", "").strip()
        sales_person = request.form.get("sales_person", "").strip()
        status = request.form.get("status", "處理中").strip()

        # 支援商品下拉選單 product_id[] 與數量 quantity[]，並相容舊格式 product_ids
        raw_product_ids = request.form.getlist("product_id[]")
        raw_quantities = request.form.getlist("quantity[]")

        items_to_add = []
        if raw_product_ids:
            for i, pid in enumerate(raw_product_ids):
                pid = pid.strip()
                if not pid:
                    continue
                qty_str = raw_quantities[i].strip() if i < len(raw_quantities) else "1"
                items_to_add.append((pid, qty_str))
        else:
            legacy_product_ids = request.form.getlist("product_ids")
            for pid in legacy_product_ids:
                pid = pid.strip()
                if not pid:
                    continue
                qty_str = request.form.get(f"qty_{pid}", "1").strip()
                items_to_add.append((pid, qty_str))

        # 基本欄位驗證
        if not order_id or not customer_id or not sales_person or not order_date:
            flash("請填寫所有必填欄位！", "danger")
            conn.close()
            return redirect(url_for("new_order"))

        # 4. 訂單編號加上 SO+數字 的格式驗證 (例如 SO20261025001)
        if not re.match(r"^SO\d+$", order_id):
            flash("訂單編號格式不正確！必須為 'SO' 開頭且後接數字（例如：SO20261025001）。", "danger")
            conn.close()
            return redirect(url_for("new_order"))

        if not items_to_add:
            flash("請至少選擇一項商品！", "danger")
            conn.close()
            return redirect(url_for("new_order"))

        # 驗證不能有重複商品
        pids_seen = set()
        for pid, _ in items_to_add:
            if pid in pids_seen:
                flash(f"訂單內有重複的商品編號 {pid}，請合併數量！", "danger")
                conn.close()
                return redirect(url_for("new_order"))
            pids_seen.add(pid)

        # 5. 後端數量正整數驗證（正整數: > 0 的整數，不能為小數、0 或負數）
        validated_items = []
        for pid, qty_str in items_to_add:
            try:
                # 嚴格整數解析：若包含小數點或非整數字元則拒絕
                if not qty_str.isdigit() or int(qty_str) <= 0:
                    flash(f"商品 {pid} 的數量「{qty_str}」必須是正整數（大於 0 的整數）！", "danger")
                    conn.close()
                    return redirect(url_for("new_order"))
                qty = int(qty_str)
            except (ValueError, TypeError):
                flash(f"商品 {pid} 的數量必須為有效的正整數！", "danger")
                conn.close()
                return redirect(url_for("new_order"))
            validated_items.append((pid, qty))

        try:
            # 檢查訂單編號是否重複
            existing = conn.execute("SELECT order_id FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if existing:
                flash(f"訂單編號 {order_id} 已存在，請使用其他編號！", "danger")
                conn.close()
                return redirect(url_for("new_order"))

            # 插入訂單主檔 (參數化查詢 ?)
            conn.execute("""
                INSERT INTO orders (order_id, customer_id, order_date, status, sales_person)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, customer_id, order_date, status, sales_person))

            # 查詢勾選商品目前的單價，寫入 order_item (需求 7: 保存下單當時單價，參數化查詢 ?)
            for pid, qty in validated_items:
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
    default_order_id = f"SO{datetime.now().strftime('%Y%m%d%H%M%S')}"

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
