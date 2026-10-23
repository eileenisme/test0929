from flask import Flask, render_template_string

app = Flask(__name__)

# HTML 模板（包含簡單美觀的樣式）
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hello World - Flask 一頁式網站</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
        }
        .card {
            background: white;
            padding: 2.5rem 3rem;
            border-radius: 16px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
            text-align: center;
            max-width: 420px;
            width: 90%;
        }
        h1 {
            color: #4a5568;
            margin-bottom: 0.5rem;
            font-size: 2.2rem;
        }
        p {
            color: #718096;
            font-size: 1.1rem;
            margin-top: 0;
        }
        .badge {
            display: inline-block;
            background-color: #edf2f7;
            color: #4a5568;
            padding: 0.35rem 0.8rem;
            border-radius: 9999px;
            font-size: 0.875rem;
            font-weight: 500;
            margin-top: 1rem;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>👋 Hello, World!</h1>
        <p>這是一個使用 Python Flask 建立的一頁式網站。</p>
        <span class="badge">Powered by Flask</span>
    </div>
</body>
</html>
"""

@app.route("/")
def hello_world():
    return render_template_string(HTML_TEMPLATE)

if __name__ == "__main__":
    # debug=True 可以在開發時自動重新載入並顯示詳細錯誤
    app.run(debug=True, port=5000)
