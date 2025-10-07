from fyers_apiv3 import fyersModel
from flask import Flask, request, render_template_string, jsonify, redirect
import webbrowser
import os

# ---- Credentials ----
client_id = "VMS68P9EK0-100"
secret_key = "ZJ0CFWZEL1"
redirect_uri = "http://127.0.0.1:5000/callback"
grant_type = "authorization_code"
response_type = "code"
state = "sample"

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

# ---- Session ----
appSession = fyersModel.SessionModel(
    client_id=client_id,
    secret_key=secret_key,
    redirect_uri=redirect_uri,
    response_type=response_type,
    grant_type=grant_type,
    state=state
)

# ---- Flask ----
app = Flask(__name__)
app.secret_key = "sajid_secret"

# ---- Globals ----
access_token_global = None
fyers = None

# ---- HTML Template ----
TEMPLATE = """
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
        h2 {
            color: #333;
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
        a {
            display: inline-block;
            padding: 10px 20px;
            background: #2196F3;
            color: white;
            text-decoration: none;
            border-radius: 3px;
            margin: 10px 0;
        }
        a:hover {
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
    <h2>Sajid Shaikh Algo Software : +91 9834370368</h2>
    <a href="/login" target="_blank">🔑 Login to Fyers</a>
    
    <div class="controls">
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
        
        function fetchData() {
            document.getElementById('stockData').innerHTML = '<tr><td colspan="10" class="loading">Loading data...</td></tr>';
            
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
                    document.getElementById('stockData').innerHTML = '<tr><td colspan="10" class="error">Failed to fetch data</td></tr>';
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
            tbody.innerHTML = '';
            
            if (!stocks || stocks.length === 0) {
                tbody.innerHTML = '<tr><td colspan="10" class="loading">No stocks match the filter criteria</td></tr>';
                return;
            }
            
            stocks.forEach((stock, index) => {
                const changeClass = stock.change > 0 ? 'positive' : stock.change < 0 ? 'negative' : 'neutral';
                const changeSymbol = stock.change > 0 ? '▲' : stock.change < 0 ? '▼' : '•';
                
                const tr = document.createElement('tr');
                tr.innerHTML = `
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
                tbody.appendChild(tr);
            });
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
            fetchData();
            autoRefreshInterval = setInterval(fetchData, 30000);
            alert('Auto refresh started (every 30 seconds)');
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

@app.route("/", methods=["GET", "POST"])
def index():
    return render_template_string(TEMPLATE)

@app.route("/login")
def login():
    login_url = appSession.generate_authcode()
    webbrowser.open(login_url, new=1)
    return redirect(login_url)

@app.route("/callback")
def callback():
    global access_token_global, fyers
    auth_code = request.args.get("auth_code")
    if auth_code:
        appSession.set_token(auth_code)
        token_response = appSession.generate_token()
        access_token_global = token_response.get("access_token")
        fyers = fyersModel.FyersModel(client_id=client_id, token=access_token_global, is_async=False, log_path="")
        return "<h2>✅ Authentication Successful! You can return to the app 🚀</h2>"
    return "❌ Authentication failed. Please retry."

@app.route("/fetch")
def fetch_nifty_50_data():
    global fyers
    if fyers is None:
        return jsonify({"error": "⚠ Please login first!"})
    
    try:
        # Prepare symbols in Fyers format
        symbols = [f"NSE:{stock}-EQ" for stock in NIFTY_50_STOCKS]
        
        # Fetch quotes for all symbols
        data = {"symbols": ",".join(symbols)}
        response = fyers.quotes(data=data)
        
        if response and response.get("s") == "ok":
            quotes_data = response.get("d", [])
            
            # Process stock data
            stocks_list = []
            for quote in quotes_data:
                symbol = quote.get("n", "").replace("NSE:", "").replace("-EQ", "")
                ltp = quote.get("v", {}).get("lp", 0)
                open_price = quote.get("v", {}).get("open_price", 0)
                high = quote.get("v", {}).get("high_price", 0)
                low = quote.get("v", {}).get("low_price", 0)
                prev_close = quote.get("v", {}).get("prev_close_price", 0)
                volume = quote.get("v", {}).get("volume", 0)
                
                change = ltp - prev_close
                change_pct = (change / prev_close * 100) if prev_close > 0 else 0
                
                stocks_list.append({
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
            
            # Sort by change percentage (descending)
            stocks_list.sort(key=lambda x: x["change_pct"], reverse=True)
            
            return jsonify({"stocks": stocks_list})
        else:
            error_msg = response.get("message", "Failed to fetch stock data")
            return jsonify({"error": f"API Error: {error_msg}"})
            
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
