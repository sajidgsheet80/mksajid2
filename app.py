from fyers_apiv3 import fyersModel
from flask import Flask, request, render_template_string, jsonify, redirect, session, url_for
import webbrowser
import pandas as pd
import os
import threading
import time
from datetime import datetime
import hashlib
import json
import uuid
from functools import wraps

# ---- User Management File ----
USERS_FILE = "users_data.txt"
ACTIVE_SESSIONS_FILE = "active_sessions.txt"

# ---- Flask ----
app = Flask(__name__)
app.secret_key = "sajid_secret_key_2024"

# ---- User Sessions Storage ----
user_sessions = {}
active_user_sessions = {}  # Track one session per user

# ---- Fixed Thresholds ----
FIXED_CE_THRESHOLD = 20
FIXED_PE_THRESHOLD = 20

# ---- User-specific Globals (stored per user) ----
def init_user_data(username):
    """Initialize user-specific data"""
    if username not in user_sessions:
        user_sessions[username] = {
            'fyers': None,
            'token': None,
            'app_session': None,
            'atm_strike': None,
            'initial_data': None,
            'symbol_prefix': "NSE:NIFTY25",
            'ce_strike_offset': -300,
            'pe_strike_offset': 300,
            'signals': [],
            'placed_orders': set(),
            'bot_running': False,
            'bot_thread': None,
            'session_id': None
        }

def load_active_sessions():
    """Load active sessions from file"""
    if not os.path.exists(ACTIVE_SESSIONS_FILE):
        return {}
    try:
        with open(ACTIVE_SESSIONS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading active sessions: {e}")
        return {}

def save_active_sessions():
    """Save active sessions to file"""
    try:
        with open(ACTIVE_SESSIONS_FILE, 'w') as f:
            json.dump(active_user_sessions, f)
    except Exception as e:
        print(f"Error saving active sessions: {e}")

def invalidate_user_session(username):
    """Invalidate any existing session for a user"""
    if username in active_user_sessions:
        old_session_id = active_user_sessions[username]
        # Clear user data for old session
        if username in user_sessions:
            # Stop bot if running
            if user_sessions[username].get('bot_running'):
                user_sessions[username]['bot_running'] = False
            del user_sessions[username]
        # Remove from active sessions
        del active_user_sessions[username]
        save_active_sessions()
        print(f"⚠️ Terminated previous session for user: {username}")
        return old_session_id
    return None

def register_user_session(username, session_id):
    """Register a new session for a user"""
    # Invalidate any existing session first
    invalidate_user_session(username)
    # Register new session
    active_user_sessions[username] = session_id
    save_active_sessions()
    init_user_data(username)
    user_sessions[username]['session_id'] = session_id
    print(f"✅ New session registered for user: {username}")

def cleanup_expired_sessions():
    """Clean up expired sessions (run periodically)"""
    current_time = time.time()
    expired_users = []
    
    for username, session_id in active_user_sessions.items():
        if username in user_sessions:
            # Check if session is still valid (has recent activity)
            last_activity = user_sessions[username].get('last_activity', 0)
            if current_time - last_activity > 3600:  # 1 hour timeout
                expired_users.append(username)
    
    for username in expired_users:
        invalidate_user_session(username)
        print(f"🧹 Cleaned up expired session for: {username}")

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

def save_user(username, password, email, phone, fyers_client_id, fyers_secret_key):
    user_data = {
        'username': username,
        'password': hash_password(password),
        'email': email,
        'phone': phone,
        'fyers_client_id': fyers_client_id,
        'fyers_secret_key': fyers_secret_key
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
        
        # Verify session is still valid
        username = session['username']
        session_id = session.get('session_id')
        
        if not session_id or active_user_sessions.get(username) != session_id:
            session.clear()
            return redirect(url_for('signin', error="Session expired. Please login again."))
        
        # Update last activity
        if username in user_sessions:
            user_sessions[username]['last_activity'] = time.time()
        
        return f(*args, **kwargs)
    return decorated_function

def get_user_fyers_session(username):
    """Get user's Fyers session"""
    init_user_data(username)
    return user_sessions[username].get('fyers'), user_sessions[username].get('token')

def set_user_fyers_session(username, fyers, token):
    """Set user's Fyers session"""
    init_user_data(username)
    user_sessions[username]['fyers'] = fyers
    user_sessions[username]['token'] = token

def get_user_data(username, key):
    """Get user-specific data"""
    init_user_data(username)
    return user_sessions[username].get(key)

def set_user_data(username, key, value):
    """Set user-specific data"""
    init_user_data(username)
    user_sessions[username][key] = value
    user_sessions[username]['last_activity'] = time.time()

def format_in_crores(value):
    """Format a number in crores (1 crore = 10 million)"""
    try:
        num = float(value)
        if num >= 10000000:  # 1 crore or more
            return f"{num/10000000:.2f} Cr"
        elif num >= 100000:  # 1 lakh or more
            return f"{num/100000:.1f} L"
        else:
            return str(int(num))
    except (ValueError, TypeError):
        return str(value)


def create_user_fyers_session(username):
    """Create Fyers session for specific user"""
    user_info = get_user_info(username)
    client_id = user_info.get('fyers_client_id')
    secret_key = user_info.get('fyers_secret_key')
    
    if not client_id or not secret_key:
        return None
    
    redirect_uri = "http://127.0.0.1:5000/callback"
    return fyersModel.SessionModel(
        client_id=client_id,
        secret_key=secret_key,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code",
        state=username  # Use username as state for security
    )


def init_user_fyers(username, auth_code):
    """Initialize Fyers for specific user"""
    try:
        appSession = user_sessions[username].get('app_session')
        if not appSession:
            return False
            
        appSession.set_token(auth_code)
        token_response = appSession.generate_token()
        access_token = token_response.get("access_token")
        
        user_info = get_user_info(username)
        client_id = user_info.get('fyers_client_id')
        
        fyers = fyersModel.FyersModel(
            client_id=client_id,
            token=access_token,
            is_async=False,
            log_path=""
        )
        
        set_user_fyers_session(username, fyers, access_token)
        print(f"✅ Fyers session initialized for user: {username}")
        return True
    except Exception as e:
        print(f"❌ Failed to init Fyers for {username}: {e}")
        return False


def place_order(username, symbol, price, side):
    """Place order for specific user"""
    fyers, _ = get_user_fyers_session(username)
    if fyers is None:
        return None
    
    try:
        data = {
            "symbol": symbol,
            "qty": 75,
            "type": 1,
            "side": side,
            "productType": "INTRADAY",
            "limitPrice": price,
            "stopPrice": 0,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
            "orderTag": f"{username}_signalorder"
        }
        response = fyers.place_order(data=data)
        print(f"✅ Order placed by {username}: {response}")
        return response
    except Exception as e:
        print(f"❌ Order error for {username}: {e}")
        return None


def exit_position(username, symbol, qty, side, productType="INTRADAY"):
    """Exit a specific position for user"""
    fyers, _ = get_user_fyers_session(username)
    if fyers is None:
        return {"error": "⚠️ Please login first!"}
    
    try:
        data = {
            "symbol": symbol,
            "qty": qty,
            "type": 2,  # Market order
            "side": side,
            "productType": productType,
            "limitPrice": 0,
            "stopPrice": 0,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
            "orderTag": f"{username}_exitposition"
        }
        
        response = fyers.place_order(data=data)
        print(f"✅ Exit order placed for {username} - {symbol}: {response}")
        return {
            "message": f"Exit order placed for {symbol}",
            "response": response
        }
        
    except Exception as e:
        print(f"❌ Error exiting position {username} - {symbol}: {e}")
        return {"error": str(e)}


def exit_all_positions(username):
    """Exit all open positions for user"""
    fyers, _ = get_user_fyers_session(username)
    if fyers is None:
        return {"error": "⚠️ Please login first!"}
    
    try:
        positions = fyers.positions()
        
        if not positions or "netPositions" not in positions:
            return {"message": "No open positions found"}
        
        open_positions = positions["netPositions"]
        exit_results = []
        
        for pos in open_positions:
            if int(pos.get("netQty", 0)) != 0:
                symbol = pos["symbol"]
                qty = abs(int(pos["netQty"]))
                side = -1 if int(pos["netQty"]) > 0 else 1
                
                result = exit_position(username, symbol, qty, side, pos.get("productType", "INTRADAY"))
                exit_results.append({
                    "symbol": symbol,
                    "qty": qty,
                    "side": side,
                    "result": result
                })
        
        return {
            "message": f"Exit orders placed for {len(exit_results)} positions",
            "details": exit_results
        }
        
    except Exception as e:
        print(f"❌ Error exiting positions for {username}: {e}")
        return {"error": str(e)}


def background_bot_worker(username):
    """Background thread for specific user"""
    print(f"🤖 Background bot started for {username}")
    
    while get_user_data(username, 'bot_running'):
        fyers, _ = get_user_fyers_session(username)
        if fyers is None:
            print(f"⚠️ {username}: Waiting for login...")
            time.sleep(5)
            continue

        try:
            # Get user-specific settings
            atm_strike = get_user_data(username, 'atm_strike')
            initial_data = get_user_data(username, 'initial_data')
            symbol_prefix = get_user_data(username, 'symbol_prefix')
            ce_strike_offset = get_user_data(username, 'ce_strike_offset')
            pe_strike_offset = get_user_data(username, 'pe_strike_offset')
            signals = get_user_data(username, 'signals')
            placed_orders = get_user_data(username, 'placed_orders')

            data = {"symbol": "NSE:NIFTY50-INDEX", "strikecount": 20, "timestamp": ""}
            response = fyers.optionchain(data=data)

            if "data" not in response or "optionsChain" not in response["data"]:
                print(f"{username}: Invalid response from API")
                time.sleep(2)
                continue

            options_data = response["data"]["optionsChain"]
            if not options_data:
                print(f"{username}: No options data found!")
                time.sleep(2)
                continue

            df = pd.DataFrame(options_data)
            
            ce_df = df[df['option_type'] == 'CE'].copy()
            pe_df = df[df['option_type'] == 'PE'].copy()
            
            df_pivot = pd.merge(
                ce_df[['strike_price', 'ltp', 'oi', 'volume']],
                pe_df[['strike_price', 'ltp', 'oi', 'volume']],
                on='strike_price',
                suffixes=('_CE', '_PE')
            )
            
            df_pivot = df_pivot.rename(columns={
                'ltp_CE': 'CE_LTP',
                'oi_CE': 'CE_OI',
                'volume_CE': 'CE_Volume',
                'ltp_PE': 'PE_LTP',
                'oi_PE': 'PE_OI',
                'volume_PE': 'PE_Volume'
            })

            # ATM detection
            if atm_strike is None:
                nifty_spot = response["data"].get(
                    "underlyingValue",
                    df_pivot["strike_price"].iloc[len(df_pivot) // 2]
                )
                atm_strike = min(df_pivot["strike_price"], key=lambda x: abs(x - nifty_spot))
                initial_data = df_pivot.to_dict(orient="records")
                signals.clear()
                placed_orders.clear()
                set_user_data(username, 'atm_strike', atm_strike)
                set_user_data(username, 'initial_data', initial_data)
                set_user_data(username, 'signals', signals)
                set_user_data(username, 'placed_orders', placed_orders)
                print(f"{username}: 📍 ATM Strike detected: {atm_strike}")

            # Calculate target strikes
            ce_target_strike = atm_strike + ce_strike_offset
            pe_target_strike = atm_strike + pe_strike_offset

            # Order placement for offset strikes
            for row in df_pivot.itertuples():
                strike = row.strike_price
                ce_ltp = getattr(row, "CE_LTP", None)
                pe_ltp = getattr(row, "PE_LTP", None)

                # CE order at offset strike (using fixed threshold)
                if strike == ce_target_strike and ce_ltp is not None:
                    initial_ce = next((item["CE_LTP"] for item in initial_data if item["strike_price"] == strike), None)
                    if initial_ce is not None and ce_ltp > initial_ce + FIXED_CE_THRESHOLD:
                        signal_name = f"CE_OFFSET_{strike}"
                        if signal_name not in placed_orders:
                            signals.append(f"{strike} {ce_ltp} CE Offset Strike")
                            print(f"{username}: 🚨 Signal: {signal_name} - Placing order")
                            place_order(username, f"{symbol_prefix}{strike}CE", ce_ltp, side=1)
                            placed_orders.add(signal_name)
                            set_user_data(username, 'signals', signals)
                            set_user_data(username, 'placed_orders', placed_orders)

                # PE order at offset strike (using fixed threshold)
                if strike == pe_target_strike and pe_ltp is not None:
                    initial_pe = next((item["PE_LTP"] for item in initial_data if item["strike_price"] == strike), None)
                    if initial_pe is not None and pe_ltp > initial_pe + FIXED_PE_THRESHOLD:
                        signal_name = f"PE_OFFSET_{strike}"
                        if signal_name not in placed_orders:
                            signals.append(f"{strike} {pe_ltp} PE Offset Strike")
                            print(f"{username}: 🚨 Signal: {signal_name} - Placing order")
                            place_order(username, f"{symbol_prefix}{strike}PE", pe_ltp, side=1)
                            placed_orders.add(signal_name)
                            set_user_data(username, 'signals', signals)
                            set_user_data(username, 'placed_orders', placed_orders)

        except Exception as e:
            print(f"❌ Background bot error for {username}: {e}")

        time.sleep(2)

    print(f"🤖 Background bot stopped for {username}")


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
        .warning {
            background: #ff9800;
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
        .session-info {
            background: #e3f2fd;
            color: #1976d2;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            font-size: 12px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="auth-container">
        <h2>🔐 Sign In</h2>
        <div class="session-info">
            ℹ️ One session per user. New login will terminate previous session.
        </div>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        {% if success %}
        <div class="success">{{ success }}</div>
        {% endif %}
        {% if warning %}
        <div class="warning">{{ warning }}</div>
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
            width: 450px;
            max-height: 90vh;
            overflow-y: auto;
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
        .info {
            background: #e3f2fd;
            color: #1976d2;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="auth-container">
        <h2>📝 Sign Up</h2>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <div class="info">
            🔑 You need your own Fyers API credentials. Get them from: <a href="https://fyers.in/dev" target="_blank">https://fyers.in/dev</a><br>
            🔒 One session per user. New login will terminate previous session.<br>
            📊 CE/PE thresholds are fixed at 20 points.
        </div>
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
            <div class="form-group">
                <label>Fyers Client ID (e.g., ABC001-100)</label>
                <input type="text" name="fyers_client_id" required placeholder="Your Fyers App ID">
            </div>
            <div class="form-group">
                <label>Fyers Secret Key</label>
                <input type="password" name="fyers_secret_key" required placeholder="Your Fyers Secret Key">
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

# ---- Load active sessions on startup ----
active_user_sessions = load_active_sessions()

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
        fyers_client_id = request.form.get("fyers_client_id")
        fyers_secret_key = request.form.get("fyers_secret_key")
        
        # Validation
        if password != confirm_password:
            return render_template_string(SIGNUP_TEMPLATE, error="Passwords do not match!")
        
        users = load_users()
        if username in users:
            return render_template_string(SIGNUP_TEMPLATE, error="Username already exists!")
        
        # Save user with Fyers credentials
        save_user(username, password, email, phone, fyers_client_id, fyers_secret_key)
        return redirect(url_for('signin', success="Account created successfully! Please sign in."))
    
    return render_template_string(SIGNUP_TEMPLATE)

@app.route("/signin", methods=["GET", "POST"])
def signin():
    success = request.args.get('success')
    error = request.args.get('error')
    warning = request.args.get('warning')
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if verify_user(username, password):
            # Generate unique session ID
            session_id = str(uuid.uuid4())
            
            # Check if user has existing session
            old_session_id = invalidate_user_session(username)
            
            # Register new session
            register_user_session(username, session_id)
            
            # Set Flask session
            session['username'] = username
            session['session_id'] = session_id
            session['login_time'] = time.time()
            
            warning_msg = None
            if old_session_id:
                warning_msg = "Previous session terminated. You are now logged in from this device."
            
            return redirect(url_for('dashboard', warning=warning_msg))
        else:
            return render_template_string(SIGNIN_TEMPLATE, error="Invalid username or password!")
    
    return render_template_string(SIGNIN_TEMPLATE, success=success, error=error, warning=warning)

@app.route("/logout")
def logout():
    username = session.get('username')
    if username:
        # Stop bot if running
        if username in user_sessions and user_sessions[username].get('bot_running'):
            user_sessions[username]['bot_running'] = False
        
        # Invalidate session
        invalidate_user_session(username)
        
        # Clear user session data
        if username in user_sessions:
            del user_sessions[username]
    
    # Clear Flask session
    session.clear()
    return redirect(url_for('signin', success="You have been logged out successfully."))

@app.route("/dashboard")
@login_required
def dashboard():
    username = session.get('username')
    return render_template_string(
        TEMPLATE,
        username=username,
        symbol_prefix=get_user_data(username, 'symbol_prefix'),
        ce_strike_offset=get_user_data(username, 'ce_strike_offset'),
        pe_strike_offset=get_user_data(username, 'pe_strike_offset'),
        bot_running=get_user_data(username, 'bot_running')
    )

@app.route("/login_fyers")
@login_required
def login_fyers():
    username = session.get('username')
    appSession = create_user_fyers_session(username)
    
    if appSession is None:
        return "❌ Fyers credentials not configured for your account!"
    
    login_url = appSession.generate_authcode()
    set_user_data(username, 'app_session', appSession)
    
    webbrowser.open(login_url, new=1)
    return redirect(login_url)

@app.route("/callback")
def callback():
    auth_code = request.args.get("auth_code")
    state = request.args.get("state")  # This will be the username
    
    if not state:
        return "❌ Invalid callback"
    
    username = state
    
    # Verify user session is still valid
    if username not in active_user_sessions:
        return "❌ Session expired. Please login again."
    
    if auth_code:
        if init_user_fyers(username, auth_code):
            return "<h2>✅ Authentication Successful! You can close this window and return to the app 🚀</h2>"
    
    return "❌ Authentication failed. Please retry."

@app.route("/", methods=["GET", "POST"])
def index():
    if 'username' not in session:
        return redirect(url_for('signin'))
    
    username = session.get('username')
    
    if request.method == "POST":
        try:
            set_user_data(username, 'ce_strike_offset', int(request.form.get("ce_strike_offset", get_user_data(username, 'ce_strike_offset'))))
        except (ValueError, TypeError):
            pass
        try:
            set_user_data(username, 'pe_strike_offset', int(request.form.get("pe_strike_offset", get_user_data(username, 'pe_strike_offset'))))
        except (ValueError, TypeError):
            pass
        
        prefix = request.form.get("symbol_prefix")
        if prefix:
            set_user_data(username, 'symbol_prefix', prefix.strip())

    return render_template_string(
        TEMPLATE,
        username=username,
        symbol_prefix=get_user_data(username, 'symbol_prefix'),
        ce_strike_offset=get_user_data(username, 'ce_strike_offset'),
        pe_strike_offset=get_user_data(username, 'pe_strike_offset'),
        bot_running=get_user_data(username, 'bot_running')
    )


@app.route("/fetch")
def fetch_option_chain():
    if 'username' not in session:
        return jsonify({"error": "⚠ Please login first!"})
    
    username = session.get('username')
    
    # Verify session is still valid
    if active_user_sessions.get(username) != session.get('session_id'):
        return jsonify({"error": "Session expired. Please login again."})
    
    fyers, _ = get_user_fyers_session(username)
    
    if fyers is None:
        return jsonify({"error": "⚠ Please login to Fyers first!"})
    
    try:
        # Get user-specific data
        atm_strike = get_user_data(username, 'atm_strike')
        initial_data = get_user_data(username, 'initial_data')
        symbol_prefix = get_user_data(username, 'symbol_prefix')
        ce_strike_offset = get_user_data(username, 'ce_strike_offset')
        pe_strike_offset = get_user_data(username, 'pe_strike_offset')
        signals = get_user_data(username, 'signals')
        placed_orders = get_user_data(username, 'placed_orders')
        bot_running = get_user_data(username, 'bot_running')

        data = {"symbol": "NSE:NIFTY50-INDEX", "strikecount": 20, "timestamp": ""}
        response = fyers.optionchain(data=data)

        if "data" not in response or "optionsChain" not in response["data"]:
            return jsonify({"error": f"Invalid response from API: {response}"})

        options_data = response["data"]["optionsChain"]
        if not options_data:
            return jsonify({"error": "No options data found!"})

        df = pd.DataFrame(options_data)
        
        ce_df = df[df['option_type'] == 'CE'].copy()
        pe_df = df[df['option_type'] == 'PE'].copy()
        
        df_pivot = pd.merge(
            ce_df[['strike_price', 'ltp', 'oi', 'volume']],
            pe_df[['strike_price', 'ltp', 'oi', 'volume']],
            on='strike_price',
            suffixes=('_CE', '_PE')
        )
        
        df_pivot = df_pivot.rename(columns={
            'ltp_CE': 'CE_LTP',
            'oi_CE': 'CE_OI',
            'volume_CE': 'CE_Volume',
            'ltp_PE': 'PE_LTP',
            'oi_PE': 'PE_OI',
            'volume_PE': 'PE_Volume'
        })

        # ATM detection
        if atm_strike is None:
            nifty_spot = response["data"].get(
                "underlyingValue",
                df_pivot["strike_price"].iloc[len(df_pivot) // 2]
            )
            atm_strike = min(df_pivot["strike_price"], key=lambda x: abs(x - nifty_spot))
            initial_data = df_pivot.to_dict(orient="records")
            signals.clear()
            placed_orders.clear()
            set_user_data(username, 'atm_strike', atm_strike)
            set_user_data(username, 'initial_data', initial_data)
            set_user_data(username, 'signals', signals)
            set_user_data(username, 'placed_orders', placed_orders)

        # Calculate target strikes
        ce_target_strike = atm_strike + ce_strike_offset
        pe_target_strike = atm_strike + pe_strike_offset

        # Order placement for offset strikes (only if bot not running)
        if not bot_running:
            for row in df_pivot.itertuples():
                strike = row.strike_price
                ce_ltp = getattr(row, "CE_LTP", None)
                pe_ltp = getattr(row, "PE_LTP", None)

                # CE order at offset strike (using fixed threshold)
                if strike == ce_target_strike and ce_ltp is not None:
                    initial_ce = next((item["CE_LTP"] for item in initial_data if item["strike_price"] == strike), None)
                    if initial_ce is not None and ce_ltp > initial_ce + FIXED_CE_THRESHOLD:
                        signal_name = f"CE_OFFSET_{strike}"
                        if signal_name not in placed_orders:
                            signals.append(f"{strike} {ce_ltp} CE Offset Strike")
                            place_order(username, f"{symbol_prefix}{strike}CE", ce_ltp, side=1)
                            placed_orders.add(signal_name)
                            set_user_data(username, 'signals', signals)
                            set_user_data(username, 'placed_orders', placed_orders)

                # PE order at offset strike (using fixed threshold)
                if strike == pe_target_strike and pe_ltp is not None:
                    initial_pe = next((item["PE_LTP"] for item in initial_data if item["strike_price"] == strike), None)
                    if initial_pe is not None and pe_ltp > initial_pe + FIXED_PE_THRESHOLD:
                        signal_name = f"PE_OFFSET_{strike}"
                        if signal_name not in placed_orders:
                            signals.append(f"{strike} {pe_ltp} PE Offset Strike")
                            place_order(username, f"{symbol_prefix}{strike}PE", pe_ltp, side=1)
                            placed_orders.add(signal_name)
                            set_user_data(username, 'signals', signals)
                            set_user_data(username, 'placed_orders', placed_orders)

        return df_pivot.to_json(orient="records")
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/positions")
def get_positions():
    """Get current positions"""
    if 'username' not in session:
        return jsonify({"error": "⚠ Please login first!"})
    
    username = session.get('username')
    
    # Verify session is still valid
    if active_user_sessions.get(username) != session.get('session_id'):
        return jsonify({"error": "Session expired. Please login again."})
    
    fyers, _ = get_user_fyers_session(username)
    
    if fyers is None:
        return jsonify({"error": "⚠ Please login to Fyers first!"})
    
    try:
        positions = fyers.positions()
        if positions and "netPositions" in positions:
            open_positions = [pos for pos in positions["netPositions"] if int(pos.get("netQty", 0)) != 0]
            return jsonify({"positions": open_positions})
        return jsonify({"positions": []})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/exit_position", methods=["POST"])
def exit_single_position():
    """Exit a single position"""
    if 'username' not in session:
        return jsonify({"error": "⚠ Please login first!"})
    
    username = session.get('username')
    
    # Verify session is still valid
    if active_user_sessions.get(username) != session.get('session_id'):
        return jsonify({"error": "Session expired. Please login again."})
    
    data = request.get_json()
    symbol = data.get("symbol")
    qty = data.get("qty")
    side = data.get("side")
    productType = data.get("productType", "INTRADAY")
    
    result = exit_position(username, symbol, qty, side, productType)
    return jsonify(result)


@app.route("/start_bot", methods=["POST"])
def start_bot():
    if 'username' not in session:
        return jsonify({"error": "⚠️ Please login first!"})
    
    username = session.get('username')
    
    # Verify session is still valid
    if active_user_sessions.get(username) != session.get('session_id'):
        return jsonify({"error": "Session expired. Please login again."})
    
    fyers, _ = get_user_fyers_session(username)
    
    if fyers is None:
        return jsonify({"error": "⚠️ Please login to Fyers first!"})

    if get_user_data(username, 'bot_running'):
        return jsonify({"error": "⚠️ Bot is already running!"})

    set_user_data(username, 'bot_running', True)
    bot_thread = threading.Thread(target=background_bot_worker, args=(username,), daemon=True)
    bot_thread.start()
    set_user_data(username, 'bot_thread', bot_thread)

    return jsonify({"message": "✅ Bot started! Running in background - you can close browser now!"})


@app.route("/stop_bot", methods=["POST"])
def stop_bot():
    if 'username' not in session:
        return jsonify({"error": "⚠️ Please login first!"})
    
    username = session.get('username')
    
    # Verify session is still valid
    if active_user_sessions.get(username) != session.get('session_id'):
        return jsonify({"error": "Session expired. Please login again."})
    
    set_user_data(username, 'bot_running', False)
    return jsonify({"message": "✅ Bot stopped!"})


@app.route("/exit_all", methods=["POST"])
def exit_all():
    """Exit all open positions"""
    if 'username' not in session:
        return jsonify({"error": "⚠ Please login first!"})
    
    username = session.get('username')
    
    # Verify session is still valid
    if active_user_sessions.get(username) != session.get('session_id'):
        return jsonify({"error": "Session expired. Please login again."})
    
    result = exit_all_positions(username)
    return jsonify(result)


@app.route("/bot_status")
def bot_status():
    if 'username' not in session:
        return jsonify({"error": "⚠ Please login first!"})
    
    username = session.get('username')
    
    # Verify session is still valid
    if active_user_sessions.get(username) != session.get('session_id'):
        return jsonify({"error": "Session expired. Please login again."})
    
    return jsonify({
        "running": get_user_data(username, 'bot_running'),
        "signals": get_user_data(username, 'signals'),
        "placed_orders": list(get_user_data(username, 'placed_orders'))
    })


@app.route("/reset", methods=["POST"])
def reset_orders():
    if 'username' not in session:
        return jsonify({"error": "⚠ Please login first!"})
    
    username = session.get('username')
    
    # Verify session is still valid
    if active_user_sessions.get(username) != session.get('session_id'):
        return jsonify({"error": "Session expired. Please login again."})
    
    set_user_data(username, 'placed_orders', set())
    set_user_data(username, 'signals', [])
    set_user_data(username, 'atm_strike', None)
    set_user_data(username, 'initial_data', None)
    return jsonify({"message": "✅ Reset successful! You can trade again."})


# ---- Background cleanup thread ----
def cleanup_worker():
    """Background worker to clean up expired sessions"""
    while True:
        try:
            cleanup_expired_sessions()
            time.sleep(300)  # Run every 5 minutes
        except Exception as e:
            print(f"Cleanup worker error: {e}")
            time.sleep(60)

# Start cleanup worker
cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
cleanup_thread.start()


# ---- HTML Template ----
TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Sajid Shaikh Algo Software</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f4f4f9; padding: 20px; }
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
    h2 { color: #1a73e8; margin: 0; }
    .bot-control {
      background: #fff;
      padding: 15px;
      margin: 20px 0;
      border-radius: 8px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .bot-status {
      display: inline-block;
      padding: 5px 10px;
      border-radius: 4px;
      font-weight: bold;
      margin-right: 10px;
    }
    .status-running { background: #4caf50; color: white; }
    .status-stopped { background: #f44336; color: white; }
    table { border-collapse: collapse; width: 100%; margin-top: 10px; }
    th, td { border: 1px solid #aaa; padding: 8px; text-align: center; }
    th { background-color: #1a73e8; color: white; }
    tr:nth-child(even) { background-color: #f2f2f2; }
    tr.atm { background-color: #ffeb3b; font-weight: bold; }
    tr.ceOffset { background-color: #90ee90; font-weight: bold; }
    tr.peOffset { background-color: #ffb6c1; font-weight: bold; }
    tr.profit { background-color: #d4edda; }
    tr.loss { background-color: #f8d7da; }
    a { text-decoration: none; padding: 8px 12px; background: #4caf50; color: white; border-radius: 4px; }
    a:hover { background: #45a049; }
    button { padding: 8px 12px; color: white; border: none; border-radius: 4px; cursor: pointer; margin-right: 5px; }
    .btn-start { background-color: #4caf50; }
    .btn-start:hover { background-color: #45a049; }
    .btn-stop { background-color: #f44336; }
    .btn-stop:hover { background-color: #da190b; }
    .btn-reset { background-color: #1a73e8; }
    .btn-reset:hover { background-color: #155cb0; }
    .btn-exit { background-color: #ff9800; }
    .btn-exit:hover { background-color: #e68900; }
    .btn-exit-single { background-color: #dc3545; padding: 5px 10px; font-size: 12px; }
    .btn-exit-single:hover { background-color: #c82333; }
    #signals { margin-top: 15px; font-weight: bold; color: red; }
    #profits { margin-top: 8px; font-weight: bold; color: green; }
    form { margin-top: 20px; }
    label { margin-right: 10px; }
    input[type="number"], input[type="text"] { padding: 5px; margin-right: 20px; }
    .oi-change-positive { color: green; }
    .oi-change-negative { color: red; }
    .volume-change-positive { color: green; }
    .volume-change-negative { color: red; }
    .positions-section { margin-top: 20px; }
    .positions-table { margin-top: 10px; }
    .no-positions { color: #666; font-style: italic; }
    .session-warning {
      background: #fff3cd;
      color: #856404;
      padding: 10px;
      border-radius: 5px;
      margin-bottom: 20px;
      text-align: center;
      border: 1px solid #ffeeba;
    }
    .threshold-info {
      background: #e8f5e8;
      color: #2e7d32;
      padding: 10px;
      border-radius: 5px;
      margin-bottom: 20px;
      text-align: center;
      border: 1px solid #c8e6c9;
      font-weight: bold;
    }
  </style>
  <script>
    var atmStrike = null;
    var initialLTP = {};
    var initialOI = {};
    var initialVolume = {};
    var signals = [];

    // Fixed thresholds
    const FIXED_CE_THRESHOLD = 20;
    const FIXED_PE_THRESHOLD = 20;

    // Helper function to format numbers in crores
    function formatInCrores(value) {
        try {
            const num = parseFloat(value);
            if (num >= 10000000) { // 1 crore or more
                return `${(num/10000000).toFixed(2)} Cr`;
            } else if (num >= 100000) { // 1 lakh or more
                return `${(num/100000).toFixed(1)} L`;
            } else {
                return Math.round(num).toString();
            }
        } catch (e) {
            return value;
        }
    }

    async function startBackgroundBot(){
        let res = await fetch("/start_bot", {method: "POST"});
        let data = await res.json();
        if(data.error && data.error.includes("Session expired")) {
            alert("Session expired! Redirecting to login...");
            window.location.href = "/signin";
            return;
        }
        alert(data.message || data.error);
        checkBotStatus();
    }

    async function stopBackgroundBot(){
        let res = await fetch("/stop_bot", {method: "POST"});
        let data = await res.json();
        if(data.error && data.error.includes("Session expired")) {
            alert("Session expired! Redirecting to login...");
            window.location.href = "/signin";
            return;
        }
        alert(data.message);
        checkBotStatus();
    }

    async function exitAllPositions(){
        if(!confirm("⚠️ Are you sure you want to exit ALL positions? This action cannot be undone!")){
            return;
        }
        let res = await fetch("/exit_all", {method: "POST"});
        let data = await res.json();
        if(data.error && data.error.includes("Session expired")) {
            alert("Session expired! Redirecting to login...");
            window.location.href = "/signin";
            return;
        }
        if(data.error){
            alert("❌ Error exiting positions: " + data.error);
        } else {
            alert("✅ " + data.message);
            if(data.details){
                console.log("Exit details:", data.details);
            }
            fetchPositions(); // Refresh positions after exit
        }
    }

    async function exitSinglePosition(symbol, qty, side, productType){
        if(!confirm(`⚠️ Are you sure you want to exit position in ${symbol}?`)){
            return;
        }
        let res = await fetch("/exit_position", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({symbol, qty, side, productType})
        });
        let data = await res.json();
        if(data.error && data.error.includes("Session expired")) {
            alert("Session expired! Redirecting to login...");
            window.location.href = "/signin";
            return;
        }
        if(data.error){
            alert("❌ Error exiting position: " + data.error);
        } else {
            alert("✅ " + data.message);
            fetchPositions(); // Refresh positions after exit
        }
    }

    async function checkBotStatus(){
        let res = await fetch("/bot_status");
        let data = await res.json();
        if(data.error && data.error.includes("Session expired")) {
            alert("Session expired! Redirecting to login...");
            window.location.href = "/signin";
            return;
        }
        let statusDiv = document.getElementById("botStatus");
        if(data.running){
            statusDiv.innerHTML = '<span class="bot-status status-running">🤖 Bot Running (Background)</span>';
            document.getElementById("startBtn").disabled = true;
            document.getElementById("stopBtn").disabled = false;
        } else {
            statusDiv.innerHTML = '<span class="bot-status status-stopped">⏸️ Bot Stopped</span>';
            document.getElementById("startBtn").disabled = false;
            document.getElementById("stopBtn").disabled = true;
        }
    }

    async function fetchPositions(){
        let res = await fetch("/positions");
        let data = await res.json();
        if(data.error && data.error.includes("Session expired")) {
            alert("Session expired! Redirecting to login...");
            window.location.href = "/signin";
            return;
        }
        let positionsDiv = document.getElementById("positionsTable");
        
        if(data.error){
            positionsDiv.innerHTML = `<tr><td colspan="7" class="no-positions">${data.error}</td></tr>`;
            return;
        }
        
        if(!data.positions || data.positions.length === 0){
            positionsDiv.innerHTML = `<tr><td colspan="7" class="no-positions">No open positions</td></tr>`;
            return;
        }
        
        let html = "";
        data.positions.forEach(pos => {
            let pnl = parseFloat(pos.pl) || 0;
            let pnlClass = pnl >= 0 ? "profit" : "loss";
            let sideText = pos.netQty > 0 ? "BUY" : "SELL";
            let exitSide = pos.netQty > 0 ? -1 : 1;
            let exitQty = Math.abs(pos.netQty);
            
            html += `<tr class="${pnlClass}">
                <td>${pos.symbol}</td>
                <td>${pos.productType}</td>
                <td>${sideText}</td>
                <td>${pos.netQty}</td>
                <td>₹${parseFloat(pos.avgPrice).toFixed(2)}</td>
                <td>₹${pnl.toFixed(2)}</td>
                <td>
                    <button class="btn-exit-single" onclick="exitSinglePosition('${pos.symbol}', ${exitQty}, ${exitSide}, '${pos.productType}')">
                        Exit
                    </button>
                </td>
            </tr>`;
        });
        
        positionsDiv.innerHTML = html;
    }

    async function fetchChain(){
        let res = await fetch("/fetch");
        let data = await res.json();
        if(data.error && data.error.includes("Session expired")) {
            alert("Session expired! Redirecting to login...");
            window.location.href = "/signin";
            return;
        }
        let tbl = document.getElementById("chain");
        tbl.innerHTML = "";
        let signalsDiv = document.getElementById("signals");
        let profitsDiv = document.getElementById("profits");

        if(data.error){
            tbl.innerHTML = `<tr><td colspan="7">${data.error}</td></tr>`;
            signalsDiv.innerHTML = "";
            profitsDiv.innerHTML = "";
            return;
        }

        if(atmStrike === null){
            atmStrike = data[Math.floor(data.length/2)].strike_price;
        }

        if(Object.keys(initialLTP).length === 0){
            data.forEach(r => {
                initialLTP[r.strike_price] = {CE: r.CE_LTP, PE: r.PE_LTP};
                initialOI[r.strike_price] = {CE: r.CE_OI, PE: r.PE_OI};
                initialVolume[r.strike_price] = {CE: r.CE_Volume, PE: r.PE_Volume};
            });
        }

        let ceOffsetStrike = atmStrike + parseInt(document.getElementById("ce_strike_offset").value || "-300");
        let peOffsetStrike = atmStrike + parseInt(document.getElementById("pe_strike_offset").value || "300");

        let ceOffsetLive = data.find(r => r.strike_price === ceOffsetStrike);
        let peOffsetLive = data.find(r => r.strike_price === peOffsetStrike);
        signals = [];

        if(ceOffsetLive){
            if(ceOffsetLive.CE_LTP > (initialLTP[ceOffsetStrike]?.CE + FIXED_CE_THRESHOLD)){
                signals.push("CE Offset Strike");
            }
        }

        if(peOffsetLive){
            if(peOffsetLive.PE_LTP > (initialLTP[peOffsetStrike]?.PE + FIXED_PE_THRESHOLD)){
                signals.push("PE Offset Strike");
            }
        }

        signalsDiv.innerHTML = signals.length > 0 ? "📢 Capture Signals: " + signals.join(", ") : "No signals";

        // ---- Profit calculation ----
        let profitsOutput = "";
        signals.forEach(signal => {
            let strike = signal === "CE Offset Strike" ? ceOffsetStrike : peOffsetStrike;
            let initialLtp = null;
            let liveLtp = null;
            let profit = 0;

            if(signal === "CE Offset Strike") {
                initialLtp = initialLTP[ceOffsetStrike]?.CE;
                liveLtp = ceOffsetLive.CE_LTP;
                profit = (liveLtp - initialLtp);
            } else if(signal === "PE Offset Strike") {
                initialLtp = initialLTP[peOffsetStrike]?.PE;
                liveLtp = peOffsetLive.PE_LTP;
                profit = (liveLtp - initialLtp);
            }
            let totalProfit = (profit * 75).toFixed(2);
            profitsOutput += `
                <b>${signal}</b> - Strike: ${strike} | Initial LTP: ${initialLtp?.toFixed(2)} | Live LTP: ${liveLtp?.toFixed(2)} | Profit × 75 = ₹${totalProfit} <br>
            `;
        });

        profitsDiv.innerHTML = profitsOutput || "No profits to show.";

        // ---- Table Build ----
        data.forEach(row=>{
            let cls = "";
            let CE_display = row.CE_LTP;
            let CE_OI_display = formatInCrores(row.CE_OI);
            let CE_Volume_display = formatInCrores(row.CE_Volume);
            let PE_display = row.PE_LTP;
            let PE_OI_display = formatInCrores(row.PE_OI);
            let PE_Volume_display = formatInCrores(row.PE_Volume);

            if(row.strike_price === atmStrike){
                cls = "atm";
                CE_display = `${initialLTP[atmStrike]?.CE} / ${row.CE_LTP}`;
                PE_display = `${initialLTP[atmStrike]?.PE} / ${row.PE_LTP}`;
                
                // Calculate OI change
                let ce_oi_change = row.CE_OI - initialOI[atmStrike]?.CE;
                let pe_oi_change = row.PE_OI - initialOI[atmStrike]?.PE;
                
                // Calculate Volume change
                let ce_volume_change = row.CE_Volume - initialVolume[atmStrike]?.CE;
                let pe_volume_change = row.PE_Volume - initialVolume[atmStrike]?.PE;
                
                CE_OI_display = `${formatInCrores(row.CE_OI)} (${ce_oi_change >= 0 ? '+' : ''}${formatInCrores(ce_oi_change)})`;
                PE_OI_display = `${formatInCrores(row.PE_OI)} (${pe_oi_change >= 0 ? '+' : ''}${formatInCrores(pe_oi_change)})`;
                CE_Volume_display = `${formatInCrores(row.CE_Volume)} (${ce_volume_change >= 0 ? '+' : ''}${formatInCrores(ce_volume_change)})`;
                PE_Volume_display = `${formatInCrores(row.PE_Volume)} (${pe_volume_change >= 0 ? '+' : ''}${formatInCrores(pe_volume_change)})`;
            }

            if(row.strike_price === ceOffsetStrike){
                cls = "ceOffset";
                let base = initialLTP[row.strike_price]?.CE;
                if(base){
                    let gainPct = ((row.CE_LTP - base) / base) * 100;
                    CE_display = `${base} / ${row.CE_LTP} (${gainPct.toFixed(1)}%)`;
                }
                let basePE = initialLTP[row.strike_price]?.PE;
                if(basePE){
                    PE_display = `${basePE} / ${row.PE_LTP}`;
                }
                
                // Calculate OI change
                let ce_oi_change = row.CE_OI - initialOI[row.strike_price]?.CE;
                let pe_oi_change = row.PE_OI - initialOI[row.strike_price]?.PE;
                
                // Calculate Volume change
                let ce_volume_change = row.CE_Volume - initialVolume[row.strike_price]?.CE;
                let pe_volume_change = row.CE_Volume - initialVolume[row.strike_price]?.PE;
                
                CE_OI_display = `${formatInCrores(row.CE_OI)} (${ce_oi_change >= 0 ? '+' : ''}${formatInCrores(ce_oi_change)})`;
                PE_OI_display = `${formatInCrores(row.PE_OI)} (${pe_oi_change >= 0 ? '+' : ''}${formatInCrores(pe_oi_change)})`;
                CE_Volume_display = `${formatInCrores(row.CE_Volume)} (${ce_volume_change >= 0 ? '+' : ''}${formatInCrores(ce_volume_change)})`;
                PE_Volume_display = `${formatInCrores(row.PE_Volume)} (${pe_volume_change >= 0 ? '+' : ''}${formatInCrores(pe_volume_change)})`;
            }

            if(row.strike_price === peOffsetStrike){
                cls = "peOffset";
                let base = initialLTP[row.strike_price]?.PE;
                if(base){
                    let gainPct = ((row.PE_LTP - base) / base) * 100;
                    PE_display = `${base} / ${row.PE_LTP} (${gainPct.toFixed(1)}%)`;
                }
                let baseCE = initialLTP[row.strike_price]?.CE;
                if(baseCE){
                    CE_display = `${baseCE} / ${row.CE_LTP}`;
                }
                
                // Calculate OI change
                let ce_oi_change = row.CE_OI - initialOI[row.strike_price]?.CE;
                let pe_oi_change = row.PE_OI - initialOI[row.strike_price]?.PE;
                
                // Calculate Volume change
                let ce_volume_change = row.CE_Volume - initialVolume[row.strike_price]?.CE;
                let pe_volume_change = row.PE_Volume - initialVolume[row.strike_price]?.PE;
                
                CE_OI_display = `${formatInCrores(row.CE_OI)} (${ce_oi_change >= 0 ? '+' : ''}${formatInCrores(ce_oi_change)})`;
                PE_OI_display = `${formatInCrores(row.PE_OI)} (${pe_oi_change >= 0 ? '+' : ''}${formatInCrores(pe_oi_change)})`;
                CE_Volume_display = `${formatInCrores(row.CE_Volume)} (${ce_volume_change >= 0 ? '+' : ''}${formatInCrores(ce_volume_change)})`;
                PE_Volume_display = `${formatInCrores(row.PE_Volume)} (${pe_volume_change >= 0 ? '+' : ''}${formatInCrores(pe_volume_change)})`;
            }

            tbl.innerHTML += `<tr class="${cls}">
                <td>${row.strike_price}</td>
                <td>${CE_display}</td>
                <td>${CE_OI_display}</td>
                <td>${CE_Volume_display}</td>
                <td>${PE_display}</td>
                <td>${PE_OI_display}</td>
                <td>${PE_Volume_display}</td>
            </tr>`;
        });
    }

    // Check session status periodically
    async function checkSessionStatus(){
        try {
            let res = await fetch("/bot_status");
            let data = await res.json();
            if(data.error && data.error.includes("Session expired")) {
                alert("Your session has expired! Redirecting to login...");
                window.location.href = "/signin";
            }
        } catch(e) {
            // Ignore errors, just continue
        }
    }

    setInterval(fetchChain, 2000);
    setInterval(fetchPositions, 3000);
    setInterval(checkBotStatus, 3000);
    setInterval(checkSessionStatus, 30000); // Check session every 30 seconds
    window.onload = function(){
        fetchChain();
        fetchPositions();
        checkBotStatus();
    };

    async function resetOrders(){
        let res = await fetch("/reset", {method: "POST"});
        let data = await res.json();
        if(data.error && data.error.includes("Session expired")) {
            alert("Session expired! Redirecting to login...");
            window.location.href = "/signin";
            return;
        }
        alert(data.message);
        atmStrike = null;
        initialLTP = {};
        initialOI = {};
        initialVolume = {};
        return false;
    }
  </script>
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

  {% if warning %}
  <div class="session-warning">
    ⚠️ {{ warning }}
  </div>
  {% endif %}

  <div class="threshold-info">
    📊 Wait and Watch and have patience....
  </div>

  <div class="bot-control">
    <div id="botStatus">
      <span class="bot-status status-stopped">⏸️ Bot Stopped</span>
    </div>
    <p style="margin: 10px 0; color: #666;">
      ℹ️ Start background bot to run continuously even when browser is minimized/closed<br>
      🔒 One session per user. New login will terminate this session.
    </p>
    <button id="startBtn" class="btn-start" onclick="startBackgroundBot()">▶️ Start Background Bot</button>
    <button id="stopBtn" class="btn-stop" onclick="stopBackgroundBot()" disabled>⏸️ Stop Bot</button>
    <button class="btn-exit" onclick="exitAllPositions()">🚪 Exit All Positions</button>
    <a href="/login_fyers" target="_blank">🔑 Login to Fyers</a>
  </div>

  <div class="positions-section">
    <h3>Current Positions</h3>
    <table class="positions-table">
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Product Type</th>
          <th>Side</th>
          <th>Quantity</th>
          <th>Avg Price</th>
          <th>P&L</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody id="positionsTable">
        <tr><td colspan="7" class="no-positions">Loading positions...</td></tr>
      </tbody>
    </table>
  </div>

  <form method="POST" action="/">
    <label>CE Strike Offset (from ATM):</label>
    <input type="number" id="ce_strike_offset" name="ce_strike_offset" value="{{ ce_strike_offset }}" required>
    <label>PE Strike Offset (from ATM):</label>
    <input type="number" id="pe_strike_offset" name="pe_strike_offset" value="{{ pe_strike_offset }}" required>
    <br><br>
    <label>Symbol Prefix:</label>
    <input type="text" id="symbol_prefix" name="symbol_prefix" value="{{ symbol_prefix }}" required>
    <button type="submit" class="btn-reset">Update Settings</button>
  </form>

  <form onsubmit="return resetOrders();">
    <button type="submit" class="btn-reset">🔄 Reset Orders</button>
  </form>

  <div id="signals"></div>
  <div id="profits"></div>
  <h3>Option Chain</h3>
  <table>
    <thead>
      <tr>
        <th>Strike</th>
        <th>CE LTP</th>
        <th>CE OI</th>
        <th>CE Volume</th>
        <th>PE LTP</th>
        <th>PE OI</th>
        <th>PE Volume</th>
      </tr>
    </thead>
    <tbody id="chain"></tbody>
  </table>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print("\n" + "="*60)
    print("🚀 Sajid Shaikh Multi-User Algo Trading Bot")
    print("="*60)
    print(f"📍 Server: http://127.0.0.1:{port}")
    print("✅ Multi-user support with individual Fyers credentials!")
    print("✅ ONE SESSION PER USER - New login terminates previous session!")
    print("✅ Each user has isolated trading environment!")
    print("✅ Background bot available per user!")
    print("✅ OI and Volume values displayed in crores!")
    print("✅ CE/PE thresholds FIXED at 20 points!")
    print("✅ Automatic session cleanup and expiration!")
    print("="*60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
