import pytest
import os
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
    """測試未登入導向登入頁，以及管理員正確登入"""
    # 未登入訪問訂單頁應被重定向至登入頁
    response = client.get('/orders')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']

    # 執行登入
    login_resp = client.post('/login', data={
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert login_resp.status_code == 200
    assert "訂單管理" in login_resp.data.decode('utf-8')

def test_orders_and_qr_code(client):
    """測試登入後查看訂單詳情與 QRCode 顯示"""
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['username'] = 'admin'

    # 查看 ORD-20261001 詳情
    response = client.get('/order/ORD-20261001')
    assert response.status_code == 200
    content = response.data.decode('utf-8')
    assert "ORD-20261001" in content
    assert "陳建宏" in content
    assert "data:image/png;base64," in content # 驗證 QRCode 產生

def test_price_immutability(client):
    """驗證商品改價後，歷史訂單中的下單單價不受影響 (需求 7)"""
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['username'] = 'admin'

    # 取得原始訂單 ORD-20261001 內容 (原本 P101 單價為 450)
    resp1 = client.get('/order/ORD-20261001')
    assert "450" in resp1.data.decode('utf-8')

    # 修改商品 P101 單價為 9999
    client.post('/products/edit', data={
        'product_id': 'P101',
        'name': '台灣極品凍頂烏龍茶 (75g)',
        'unit_price': '9999',
        'stock': '100',
        'category': '茶葉飲品'
    })

    # 再次檢查歷史訂單 ORD-20261001，單價應依然為 450
    resp2 = client.get('/order/ORD-20261001')
    assert "450" in resp2.data.decode('utf-8')
