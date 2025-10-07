from fyers_apiv3 import fyersModel
from flask import Flask, request, render_template_string, jsonify, redirect, session, url_for
import webbrowser
import os
import hashlib
import json
from functools import wraps

# ---- Nifty 50 Stocks ----
NIFTY_50_STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR",
    "ICICIBANK", "KOTAKBANK", "SBIN", "BHARTIARTL", "ITC",
    "AXISBANK", "LT", "ASIANPAINT", "MARUTI", "BAJFINANCE",
    "HCLTECH", "SUNPHARMA", "TITAN", "ULTRACEMCO", "WIPRO",
    "NESTLEIND", "ONGC", "NTPC", "TECHM", "POWERGRID",
    "BAJAJFINSV", "TATAMOTORS", "ADANIPORTS", "COALINDIA", "TATASTEEL",
    "M&M", "INDUSINDBK", "DIVISLAB", "DRREDDY", "EICHERMOT",
    "CIPLA", "APOLLOHOSP", "BAJAJ-AUTO", "HDFCLIFE", "HINDALCO",
    "HEROMOTOCO", "BRITANNIA", "GRASIM", "SBILIFE", "JSWSTEEL",
    "SHREECEM", "UPL", "TATACONSUM", "LTIM", "ADANIENT"
]

# ---- User Management File ----
USERS_FILE = "users_data.txt"

# ---- Flask ----
app = Flask(__name__)
app.secret_key = "sajid_secret_key_2024"

# ---- User Sessions Storage ----
user_sessions = {}

# ---- Helper Functions ----
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    users = {}
    try:
        with open(USERS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    users[data['username']] = data
    except Exception as e:
        print(f"Error loading users: {e}")
    return users

def save_user(username, password, email, phone):
    user_data = {
        'username': username,
        'password': hash_password(password),
        'email': email,
        'phone': phone
    }
    with open(USERS_FILE, 'a') as f:
        f.write(json.dumps(user_data) + '\n')

def verify_user(username, password):
    users = load_users()
    if username in users:
        return users[username]['password'] == hash_password(password)
    return False

def get_user_info(username):
    users = load_users()
    return users.get(username, {})

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('signin'))
        return f(*args, **kwargs)
    return decorated_function

def get_fyers_session(username):
    if username not in user_sessions:
        return None, None
    return user_sessions[username].get('fyers'), user_sessions[username].get('token')

def set_fyers_session(username, fyers, token):
    if username not in user_sessions:
        user_sessions[username] = {}
    user_sessions[username]['fyers'] = fyers
    user_sessions[username]['token'] = token

# ---- Fyers Session Setup ----
def create_fyers_session(client_id, secret_key):
    redirect_uri = "http://127.0.0.1:5000/callback"
    return fyersModel.SessionModel(
        client_id=client_id,
        secret_key=secret_key,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code",
        state="sample"
    )

# ---- HTML Templates ----
SIGNIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Sign In - Sajid Shaikh Algo</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .auth-container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            width: 400px;
        }
        h2 {
            text-align: center;
            color: #333;
            margin-bottom: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #555;
            font-weight: bold;
        }
        input {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
            box-sizing: border-box;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            margin-top: 10px;
        }
        button:hover {
            background: #5568d3;
        }
        .error {
            background: #f44336;
            color: white;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            text-align: center;
        }
        .success {
            background: #4CAF50;
            color: white;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            text-align: center;
        }
        .link {
            text-align: center;
            margin-top: 20px;
            color: #666;
        }
        .link a {
            color: #667eea;
            text-decoration: none;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="auth-container">
        <h2>🔐 Sign In</h2>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        {% if success %}
        <div class="success">{{ success }}</div>
        {% endif %}
        <form method="POST">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" required>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">Sign In</button>
        </form>
        <div class="link">
            Don't have an account? <a href="/signup">Sign Up</a>
        </div>
    </div>
</body>
</html>
"""

SIGNUP_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Sign Up - Sajid Shaikh Algo</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }
        .auth-container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            width: 400px;
        }
        h2 {
            text-align: center;
            color: #333;
            margin-bottom: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #555;
            font-weight: bold;
        }
        input {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
            box-sizing: border-box;
        }
        input:focus {
            outline: none;
            border-color: #f5576c;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #f5576c;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            margin-top: 10px;
        }
        button:hover {
            background: #e04555;
        }
        .error {
            background: #f44336;
            color: white;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            text-align: center;
        }
        .link {
            text-align: center;
            margin-top: 20px;
            color: #666;
        }
        .link a {
            color: #f5576c;
            text-decoration: none;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="auth-container">
        <h2>📝 Sign Up</h2>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" required minlength="3">
            </div>
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" required>
            </div>
            <div class="form-group">
                <label>Phone</label>
                <input type="tel" name="phone" required pattern="[0-9]{10}">
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required minlength="6">
            </div>
            <div class="form-group">
                <label>Confirm Password</label>
                <input type="password" name="confirm_password" required>
            </div>
            <button type="submit">Sign Up</button>
        </form>
        <div class="link">
            Already have an account? <a href="/signin">Sign In</a>
        </div>
    </div>
</body>
</html>
"""

MAIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Sajid Shaikh Algo Software - Nifty 50 Stocks</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: white;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .user-info {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .user-badge {
            background: #667eea;
            color: white;
            padding: 8px 15px;
            border-radius: 20px;
            font-weight: bold;
        }
        .logout-btn {
            background: #f44336;
            color: white;
            padding: 8px 15px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }
        .logout-btn:hover {
            background: #d32f2f;
        }
        h2 {
            color: #333;
            margin: 0;
        }
        .controls {
            margin: 20px 0;
            padding: 15px;
            background: white;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .controls button {
            padding: 10px 20px;
            margin: 5px;
            background: #4CAF50;
            color: white;
            border: none;
            border-radius: 3px;
            cursor: pointer;
            font-size: 14px;
        }
        .controls button:hover {
            background: #45a049;
        }
        a.login-btn {
            display: inline-block;
            padding: 10px 20px;
            background: #2196F3;
            color: white;
            text-decoration: none;
            border-radius: 3px;
            margin: 5px;
        }
        a.login-btn:hover {
            background: #0b7dda;
        }
        .stats {
            display: flex;
            gap: 20px;
            margin: 20px 0;
        }
        .stat-card {
            flex: 1;
            padding: 15px;
            background: white;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #4CAF50;
        }
        .stat-label {
            color: #666;
            margin-top: 5px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-top: 20px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border: 1px solid #ddd;
        }
        th {
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
            position: sticky;
            top: 0;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        tr:hover {
            background-color: #f1f1f1;
        }
        .positive {
            color: #4CAF50;
            font-weight: bold;
        }
        .negative {
            color: #f44336;
            font-weight: bold;
        }
        .neutral {
            color: #666;
        }
        .price {
            font-size: 16px;
            font-weight: bold;
            transition: background-color 0.3s ease;
        }
        tr {
            transition: background-color 0.2s ease;
        }
        .updated {
            animation: highlight 0.5s ease;
        }
        @keyframes highlight {
            0% { background-color: #ffeb3b; }
            100% { background-color: transparent; }
        }
        .loading {
            text-align: center;
            padding: 20px;
            color: #666;
        }
        .error {
            color: #f44336;
            padding: 20px;
            text-align: center;
        }
        #lastUpdate {
            text-align: right;
            color: #666;
            font-size: 12px;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h2>Sajid Shaikh Algo Software : +91 9834370368</h2>
        </div>
        <div class="user-info">
            <div class="user-badge">👤 {{ username }}</div>
            <a href="/logout" class="logout-btn">Logout</a>
        </div>
    </div>
    
    <div class="controls">
        <a href="/login_fyers" class="login-btn" target="_blank">🔑 Login to Fyers</a>
        <button onclick="fetchData()">🔄 Fetch Nifty 50 Stocks Data</button>
        <button onclick="startAutoRefresh()">▶️ Start Auto Refresh (30s)</button>
        <button onclick="stopAutoRefresh()">⏸️ Stop Auto Refresh</button>
        <button onclick="filterOL()" style="background: #FF9800;">📊 OL (Open = Low)</button>
        <button onclick="filterOH()" style="background: #9C27B0;">📈 OH (Open = High)</button>
        <button onclick="showAll()" style="background: #607D8B;">🔄 Show All</button>
    </div>
    
    <div class="stats" id="statsContainer" style="display:none;">
        <div class="stat-card">
            <div class="stat-value" id="totalStocks">0</div>
            <div class="stat-label">Total Stocks</div>
        </div>
        <div class="stat-card">
            <div class="stat-value positive" id="gainers">0</div>
            <div class="stat-label">Gainers</div>
        </div>
        <div class="stat-card">
            <div class="stat-value negative" id="losers">0</div>
            <div class="stat-label">Losers</div>
        </div>
    </div>
    
    <h3>Nifty 50 Stocks - Live Data <span id="filterLabel" style="color: #666; font-size: 16px;"></span></h3>
    <div id="lastUpdate"></div>
    <table id="stockTable">
        <thead>
            <tr>
                <th>#</th>
                <th>Symbol</th>
                <th>LTP</th>
                <th>Change</th>
                <th>Change %</th>
                <th>Open</th>
                <th>High</th>
                <th>Low</th>
                <th>Close</th>
                <th>Volume</th>
            </tr>
        </thead>
        <tbody id="stockData">
            <tr><td colspan="10" class="loading">Click "Fetch Nifty 50 Stocks Data" to load data</td></tr>
        </tbody>
    </table>
    
    <script>
        let autoRefreshInterval = null;
        let allStocksData = [];
        let currentFilter = 'all';
        
        function fetchData(silent = false) {
            if (!silent) {
                document.getElementById('stockData').innerHTML = '<tr><td colspan="10" class="loading">Loading data...</td></tr>';
            }
            
            fetch('/fetch')
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        document.getElementById('stockData').innerHTML = `<tr><td colspan="10" class="error">${data.error}</td></tr>`;
                        return;
                    }
                    allStocksData = data.stocks;
                    applyCurrentFilter();
                    updateStats(data);
                    updateLastRefreshTime();
                })
                .catch(error => {
                    console.error('Error:', error);
                    if (!silent) {
                        document.getElementById('stockData').innerHTML = '<tr><td colspan="10" class="error">Failed to fetch data</td></tr>';
                    }
                });
        }
        
        function applyCurrentFilter() {
            let filteredData = allStocksData;
            let filterText = '';
            
            if (currentFilter === 'ol') {
                filteredData = allStocksData.filter(stock => Math.abs(stock.open - stock.low) < 0.01);
                filterText = ' (Filtered: Open = Low)';
            } else if (currentFilter === 'oh') {
                filteredData = allStocksData.filter(stock => Math.abs(stock.open - stock.high) < 0.01);
                filterText = ' (Filtered: Open = High)';
            }
            
            document.getElementById('filterLabel').textContent = filterText;
            displayStocks(filteredData);
        }
        
        function filterOL() {
            currentFilter = 'ol';
            applyCurrentFilter();
        }
        
        function filterOH() {
            currentFilter = 'oh';
            applyCurrentFilter();
        }
        
        function showAll() {
            currentFilter = 'all';
            applyCurrentFilter();
        }
        
        function displayStocks(stocks) {
            const tbody = document.getElementById('stockData');
            
            if (!stocks || stocks.length === 0) {
                tbody.innerHTML = '<tr><td colspan="10" class="loading">No stocks match the filter criteria</td></tr>';
                return;
            }
            
            // Create a map of existing rows by symbol for quick lookup
            const existingRows = new Map();
            Array.from(tbody.children).forEach(row => {
                const symbol = row.dataset.symbol;
                if (symbol) existingRows.set(symbol, row);
            });
            
            // Update or create rows for each stock
            stocks.forEach((stock, index) => {
                const changeClass = stock.change > 0 ? 'positive' : stock.change < 0 ? 'negative' : 'neutral';
                const changeSymbol = stock.change > 0 ? '▲' : stock.change < 0 ? '▼' : '•';
                
                let tr = existingRows.get(stock.symbol);
                
                if (!tr) {
                    // Create new row if it doesn't exist
                    tr = document.createElement('tr');
                    tr.dataset.symbol = stock.symbol;
                    tbody.appendChild(tr);
                }
                
                // Check if data has changed before updating
                const newContent = `
                    <td>${index + 1}</td>
                    <td><strong>${stock.symbol}</strong></td>
                    <td class="price">₹${stock.ltp.toFixed(2)}</td>
                    <td class="${changeClass}">${changeSymbol} ${stock.change.toFixed(2)}</td>
                    <td class="${changeClass}">${stock.change_pct.toFixed(2)}%</td>
                    <td>₹${stock.open.toFixed(2)}</td>
                    <td>₹${stock.high.toFixed(2)}</td>
                    <td>₹${stock.low.toFixed(2)}</td>
                    <td>₹${stock.prev_close.toFixed(2)}</td>
                    <td>${formatVolume(stock.volume)}</td>
                `;
                
                if (tr.innerHTML !== newContent) {
                    tr.innerHTML = newContent;
                    // Add highlight animation for updated rows
                    tr.classList.add('updated');
                    setTimeout(() => tr.classList.remove('updated'), 500);
                }
                
                // Remove from map (remaining items will be deleted)
                existingRows.delete(stock.symbol);
            });
            
            // Remove rows that are no longer in the filtered data
            existingRows.forEach(row => row.remove());
        }
        
        function updateStats(data) {
            const statsContainer = document.getElementById('statsContainer');
            statsContainer.style.display = 'flex';
            
            const gainers = allStocksData.filter(s => s.change > 0).length;
            const losers = allStocksData.filter(s => s.change < 0).length;
            
            document.getElementById('totalStocks').textContent = allStocksData.length;
            document.getElementById('gainers').textContent = gainers;
            document.getElementById('losers').textContent = losers;
        }
        
        function formatVolume(volume) {
            if (volume >= 10000000) return (volume / 10000000).toFixed(2) + ' Cr';
            if (volume >= 100000) return (volume / 100000).toFixed(2) + ' L';
            if (volume >= 1000) return (volume / 1000).toFixed(2) + ' K';
            return volume;
        }
        
        function updateLastRefreshTime() {
            const now = new Date();
            document.getElementById('lastUpdate').textContent = `Last Updated: ${now.toLocaleString()}`;
        }
        
        function startAutoRefresh() {
            if (autoRefreshInterval) return;
            fetchData(true);
            autoRefreshInterval = setInterval(() => fetchData(true), 30000);
            alert('Auto refresh started (every 30 seconds) - Values will update smoothly');
        }
        
        function stopAutoRefresh() {
            if (autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
                autoRefreshInterval = null;
                alert('Auto refresh stopped');
            }
        }
    </script>
</body>
</html>
"""

# ---- Routes ----
@app.route("/")
def home():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('signin'))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        phone = request.form.get("phone")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        # Validation
        if password != confirm_password:
            return render_template_string(SIGNUP_TEMPLATE, error="Passwords do not match!")
        
        users = load_users()
        if username in users:
            return render_template_string(SIGNUP_TEMPLATE, error="Username already exists!")
        
        # Save user
        save_user(username, password, email, phone)
        return redirect(url_for('signin', success="Account created successfully! Please sign in."))
    
    return render_template_string(SIGNUP_TEMPLATE)

@app.route("/signin", methods=["GET", "POST"])
def signin():
    success = request.args.get('success')
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if verify_user(username, password):
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template_string(SIGNIN_TEMPLATE, error="Invalid username or password!")
    
    return render_template_string(SIGNIN_TEMPLATE, success=success)

@app.route("/logout")
def logout():
    username = session.get('username')
    if username and username in user_sessions:
        del user_sessions[username]
    session.pop('username', None)
    return redirect(url_for('signin'))

@app.route("/dashboard")
@login_required
def dashboard():
    username = session.get('username')
    return render_template_string(MAIN_TEMPLATE, username=username)

@app.route("/login_fyers")
@login_required
def login_fyers():
    # For demo, using static credentials
    # In production, each user should have their own credentials
    client_id = "VMS68P9EK0-100"
    secret_key = "ZJ0CFWZEL1"
    
    appSession = create_fyers_session(client_id, secret_key)
    login_url = appSession.generate_authcode()
    
    username = session.get('username')
    if username not in user_sessions:
        user_sessions[username] = {}
    user_sessions[username]['app_session'] = appSession
    
    webbrowser.open(login_url, new=1)
    return redirect(login_url)

@app.route("/callback")
def callback():
    auth_code = request.args.get("auth_code")
    username = session.get('username')
    
    if not username:
        return "❌ Please login first"
    
    if auth_code and username in user_sessions:
        appSession = user_sessions[username].get('app_session')
        if appSession:
            appSession.set_token(auth_code)
            token_response = appSession.generate_token()
            access_token = token_response.get("access_token")
            
            client_id = "VMS68P9EK0-100"
            fyers = fyersModel.FyersModel(client_id=client_id, token=access_token, is_async=False, log_path="")
            
            set_fyers_session(username, fyers, access_token)
            return "<h2>✅ Authentication Successful! You can close this window and return to the app 🚀</h2>"
    
    return "❌ Authentication failed. Please retry."

@app.route("/fetch")
@login_required
def fetch_nifty_50_data():
    username = session.get('username')
    fyers, token = get_fyers_session(username)
    
    if fyers is None:
        return jsonify({"error": "⚠ Please login to Fyers first!"})
    
    try:
        # Fetch quotes for all symbols in batches
        all_stocks = []
        batch_size = 50
        
        for i in range(0, len(NIFTY_50_STOCKS), batch_size):
            batch = NIFTY_50_STOCKS[i:i + batch_size]
            symbols = [f"NSE:{stock}-EQ" for stock in batch]
            
            data = {"symbols": ",".join(symbols)}
            response = fyers.quotes(data=data)
            
            if response and response.get("s") == "ok":
                quotes_data = response.get("d", [])
                
                for quote in quotes_data:
                    try:
                        v = quote.get("v", {})
                        symbol = quote.get("n", "").replace("NSE:", "").replace("-EQ", "")
                        
                        ltp = float(v.get("lp", 0))
                        open_price = float(v.get("open_price", 0))
                        high = float(v.get("high_price", 0))
                        low = float(v.get("low_price", 0))
                        prev_close = float(v.get("prev_close_price", 0))
                        volume = int(v.get("volume", 0))
                        
                        change = ltp - prev_close
                        change_pct = (change / prev_close * 100) if prev_close > 0 else 0
                        
                        all_stocks.append({
                            "symbol": symbol,
                            "ltp": ltp,
                            "change": change,
                            "change_pct": change_pct,
                            "open": open_price,
                            "high": high,
                            "low": low,
                            "prev_close": prev_close,
                            "volume": volume
                        })
                    except (ValueError, TypeError, KeyError) as e:
                        continue
            else:
                error_msg = response.get("message", "Failed to fetch batch")
                print(f"Batch error: {error_msg}")
        
        if not all_stocks:
            return jsonify({"error": "No data received from API"})
        
        # Sort by change percentage (descending)
        all_stocks.sort(key=lambda x: x["change_pct"], reverse=True)
        
        return jsonify({"stocks": all_stocks})
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error: {str(e)}"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
