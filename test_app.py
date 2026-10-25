import pytest
import os
import sqlite3
from app import app, DB_FILE
from init_db import init_db

@pytest.fixture
def client():
    # 初始化資料庫測試資料
    init_db()
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    with app.test_client() as client:
        yield client

def test_login_flow(client):
    """測試未登入導向登入頁，以及管理員正確登入（使用 werkzeug 雜湊比對）"""
    # 未登入訪問後台頁面應被重定向至登入頁
    response = client.get('/orders')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']

    # 錯誤密碼登入失敗
    bad_login = client.post('/login', data={
        'username': 'admin',
        'password': 'wrongpassword'
    }, follow_redirects=True)
    assert bad_login.status_code == 200
    assert "帳號或密碼錯誤" in bad_login.data.decode('utf-8')

    # 正確密碼登入成功
    login_resp = client.post('/login', data={
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert login_resp.status_code == 200
    assert "訂單管理" in login_resp.data.decode('utf-8')

    # 驗證登入後 session 角色為 admin
    with client.session_transaction() as sess:
        assert sess.get('logged_in') is True
        assert sess.get('role') == 'admin'

def test_admin_role_protection(client):
    """測試登入但角色非 admin 時無法進入後台各頁面"""
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['role'] = 'guest' # 非 admin 角色

    for url in ['/orders', '/orders/new', '/order/SO20261001', '/customers', '/products']:
        resp = client.get(url)
        assert resp.status_code == 302
        assert '/login' in resp.headers['Location']

def test_order_id_format_validation(client):
    """測試訂單編號 SO+數字 格式驗證 (符合 vs 不符合)"""
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['role'] = 'admin'

    # 不符合格式：如 ORD-9999 或 SOABC
    resp_invalid = client.post('/orders/new', data={
        'order_id': 'ORD-99999',
        'customer_id': 'C001',
        'sales_person': 'admin',
        'order_date': '2026-10-25',
        'status': '處理中',
        'product_id[]': ['P101'],
        'quantity[]': ['1']
    }, follow_redirects=True)
    assert "訂單編號格式不正確" in resp_invalid.data.decode('utf-8')

    # 符合格式：SO20261025888
    resp_valid = client.post('/orders/new', data={
        'order_id': 'SO20261025888',
        'customer_id': 'C001',
        'sales_person': 'admin',
        'order_date': '2026-10-25',
        'status': '處理中',
        'product_id[]': ['P101'],
        'quantity[]': ['2']
    }, follow_redirects=True)
    assert "建立成功" in resp_valid.data.decode('utf-8')

def test_quantity_positive_integer_backend_validation(client):
    """測試數量必須是正整數，後端攔截 0、負數、小數及非整數"""
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['role'] = 'admin'

    invalid_quantities = ['0', '-5', '2.5', 'abc']
    for bad_qty in invalid_quantities:
        resp = client.post('/orders/new', data={
            'order_id': f'SO2026109999{bad_qty.replace(".", "").replace("-", "")}',
            'customer_id': 'C001',
            'sales_person': 'admin',
            'order_date': '2026-10-25',
            'status': '處理中',
            'product_id[]': ['P101'],
            'quantity[]': [bad_qty]
        }, follow_redirects=True)
        assert "必須是正整數" in resp.data.decode('utf-8') or "有效的正整數" in resp.data.decode('utf-8')

def test_database_check_constraint_for_quantity(client):
    """測試資料庫 order_item 表的 CHECK (quantity > 0) 約束層"""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # 嘗試直接向 SQLite 寫入 quantity <= 0 的資料，驗證 DB CHECK 會拋出 IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                     ("SO20261001", "P102", 0, 180))
        conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                     ("SO20261001", "P102", -3, 180))
        conn.commit()

    conn.close()

def test_orders_and_qr_code(client):
    """測試登入後查看訂單詳情與 QRCode 顯示"""
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['role'] = 'admin'
        sess['username'] = 'admin'

    # 查看 SO20261001 詳情
    response = client.get('/order/SO20261001')
    assert response.status_code == 200
    content = response.data.decode('utf-8')
    assert "SO20261001" in content
    assert "陳建宏" in content
    assert "data:image/png;base64," in content # 驗證 QRCode 產生

def test_price_immutability(client):
    """驗證商品改價後，歷史訂單中的下單單價不受影響 (需求 7)"""
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['role'] = 'admin'
        sess['username'] = 'admin'

    # 取得原始訂單 SO20261001 內容 (原本 P101 單價為 450)
    resp1 = client.get('/order/SO20261001')
    assert "450" in resp1.data.decode('utf-8')

    # 修改商品 P101 單價為 9999
    client.post('/products/edit', data={
        'product_id': 'P101',
        'name': '台灣極品凍頂烏龍茶 (75g)',
        'unit_price': '9999',
        'stock': '100',
        'category': '茶葉飲品'
    })

    # 再次檢查歷史訂單 SO20261001，單價應依然為 450
    resp2 = client.get('/order/SO20261001')
    assert "450" in resp2.data.decode('utf-8')
