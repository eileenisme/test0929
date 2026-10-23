import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_home_page(client):
    """測試首頁是否正常回傳 200 且包含關鍵字"""
    response = client.get('/')
    assert response.status_code == 200
    assert "Hello, World!" in response.data.decode('utf-8')
