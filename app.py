from fyers_apiv3 import fyersModel
from flask import Flask, request, render_template_string, jsonify, redirect
import webbrowser
import pandas as pd
import os
import threading
import time
from datetime import datetime

# ---- Credentials ----
client_id = "VMS68P9EK0-100"
secret_key = "ZJ0CFWZEL1"
redirect_uri = "http://127.0.0.1:5000/callback"
grant_type = "authorization_code"
response_type = "code"
state = "sample"
auth_file = "auth_code.txt"

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
atm_strike = None
initial_data = None

atm_ce_plus20 = 20
atm_pe_plus20 = 20
symbol_prefix = "NSE:NIFTY25"
ce_strike_offset = -300  # Default offset for CE strike (ATM - 300)
pe_strike_offset = 300   # Default offset for PE strike (ATM + 300)

signals = []
placed_orders = set()

# Background bot control
bot_running = False
bot_thread = None


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


def load_auth_code():
    if os.path.exists(auth_file):
        with open(auth_file, "r") as f:
            return f.read().strip()
    return None


def save_auth_code(auth_code):
    with open(auth_file, "w") as f:
        f.write(auth_code)


def init_fyers(auth_code):
    global access_token_global, fyers
    try:
        appSession.set_token(auth_code)
        token_response = appSession.generate_token()
        access_token_global = token_response.get("access_token")
        fyers = fyersModel.FyersModel(
            client_id=client_id,
            token=access_token_global,
            is_async=False,
            log_path=""
        )
        print("✅ Fyers session initialized from auth code.")
    except Exception as e:
        print("❌ Failed to init Fyers:", e)


def place_order(symbol, price, side):
    try:
        if fyers is None:
            return None
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
            "orderTag": "signalorder"
        }
        response = fyers.place_order(data=data)
        print("✅ Order placed:", response)
        return response
    except Exception as e:
        print("❌ Order error:", e)
        return None


def exit_position(symbol, qty, side, productType="INTRADAY"):
    """Exit a specific position"""
    if fyers is None:
        return {"error": "⚠️ Please login first!"}
    
    try:
        # Place market order for immediate exit
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
            "orderTag": "exitposition"
        }
        
        response = fyers.place_order(data=data)
        print(f"✅ Exit order placed for {symbol}: {response}")
        return {
            "message": f"Exit order placed for {symbol}",
            "response": response
        }
        
    except Exception as e:
        print(f"❌ Error exiting position {symbol}: {e}")
        return {"error": str(e)}


def exit_all_positions():
    """Exit all open positions"""
    if fyers is None:
        return {"error": "⚠️ Please login first!"}
    
    try:
        # Get all open positions
        positions = fyers.positions()
        
        if not positions or "netPositions" not in positions:
            return {"message": "No open positions found"}
        
        open_positions = positions["netPositions"]
        exit_results = []
        
        for pos in open_positions:
            # Only exit if position is open and has quantity
            if int(pos.get("netQty", 0)) != 0:
                symbol = pos["symbol"]
                qty = abs(int(pos["netQty"]))  # Use absolute value
                # Determine side: if netQty is positive, we need to sell (side=-1)
                # if netQty is negative, we need to buy (side=1)
                side = -1 if int(pos["netQty"]) > 0 else 1
                
                result = exit_position(symbol, qty, side, pos.get("productType", "INTRADAY"))
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
        print(f"❌ Error exiting positions: {e}")
        return {"error": str(e)}


def background_bot_worker():
    """Background thread that continuously monitors and places orders"""
    global bot_running, fyers, atm_strike, initial_data, placed_orders, signals
    global atm_ce_plus20, atm_pe_plus20, symbol_prefix, ce_strike_offset, pe_strike_offset

    print("🤖 Background bot started - will run even if browser is closed")

    while bot_running:
        if fyers is None:
            print("⚠️ Waiting for login...")
            time.sleep(5)
            continue

        try:
            data = {"symbol": "NSE:NIFTY50-INDEX", "strikecount": 20, "timestamp": ""}
            response = fyers.optionchain(data=data)

            if "data" not in response or "optionsChain" not in response["data"]:
                print(f"Invalid response from API")
                time.sleep(2)
                continue

            options_data = response["data"]["optionsChain"]
            if not options_data:
                print("No options data found!")
                time.sleep(2)
                continue

            df = pd.DataFrame(options_data)
            
            # Create separate DataFrames for CE and PE options
            ce_df = df[df['option_type'] == 'CE'].copy()
            pe_df = df[df['option_type'] == 'PE'].copy()
            
            # Merge CE and PE data on strike_price
            df_pivot = pd.merge(
                ce_df[['strike_price', 'ltp', 'oi', 'volume']],
                pe_df[['strike_price', 'ltp', 'oi', 'volume']],
                on='strike_price',
                suffixes=('_CE', '_PE')
            )
            
            # Rename columns for clarity
            df_pivot = df_pivot.rename(columns={
                'ltp_CE': 'CE_LTP',
                'oi_CE': 'CE_OI',
                'volume_CE': 'CE_Volume',
                'ltp_PE': 'PE_LTP',
                'oi_PE': 'PE_OI',
                'volume_PE': 'PE_Volume'
            })

            # ---- ATM detection ----
            if atm_strike is None:
                nifty_spot = response["data"].get(
                    "underlyingValue",
                    df_pivot["strike_price"].iloc[len(df_pivot) // 2]
                )
                atm_strike = min(df_pivot["strike_price"], key=lambda x: abs(x - nifty_spot))
                initial_data = df_pivot.to_dict(orient="records")
                signals.clear()
                placed_orders.clear()
                print(f"📍 ATM Strike detected: {atm_strike}")

            # ---- Calculate target strikes ----
            ce_target_strike = atm_strike + ce_strike_offset  # Usually ATM - 300
            pe_target_strike = atm_strike + pe_strike_offset  # Usually ATM + 300

            # ---- Order placement for offset strikes ----
            for row in df_pivot.itertuples():
                strike = row.strike_price
                ce_ltp = getattr(row, "CE_LTP", None)
                pe_ltp = getattr(row, "PE_LTP", None)

                # CE order at offset strike
                if strike == ce_target_strike and ce_ltp is not None:
                    initial_ce = next((item["CE_LTP"] for item in initial_data if item["strike_price"] == strike), None)
                    if initial_ce is not None and ce_ltp > initial_ce + atm_ce_plus20:
                        signal_name = f"CE_OFFSET_{strike}"
                        if signal_name not in placed_orders:
                            signals.append(f"{strike} {ce_ltp} CE Offset Strike")
                            print(f"🚨 Signal: {signal_name} - Placing order")
                            place_order(f"{symbol_prefix}{strike}CE", ce_ltp, side=1)
                            placed_orders.add(signal_name)

                # PE order at offset strike
                if strike == pe_target_strike and pe_ltp is not None:
                    initial_pe = next((item["PE_LTP"] for item in initial_data if item["strike_price"] == strike), None)
                    if initial_pe is not None and pe_ltp > initial_pe + atm_pe_plus20:
                        signal_name = f"PE_OFFSET_{strike}"
                        if signal_name not in placed_orders:
                            signals.append(f"{strike} {pe_ltp} PE Offset Strike")
                            print(f"🚨 Signal: {signal_name} - Placing order")
                            place_order(f"{symbol_prefix}{strike}PE", pe_ltp, side=1)
                            placed_orders.add(signal_name)

        except Exception as e:
            print(f"❌ Background bot error: {e}")

        time.sleep(2)

    print("🤖 Background bot stopped")


# ---- Load auth code on startup ----
auth_code = load_auth_code()
if auth_code:
    init_fyers(auth_code)


@app.route("/", methods=["GET", "POST"])
def index():
    global atm_ce_plus20, atm_pe_plus20, symbol_prefix, ce_strike_offset, pe_strike_offset
    if request.method == "POST":
        try:
            atm_ce_plus20 = float(request.form.get("atm_ce_plus20", atm_ce_plus20))
        except (ValueError, TypeError):
            atm_ce_plus20 = 20
        try:
            atm_pe_plus20 = float(request.form.get("atm_pe_plus20", atm_pe_plus20))
        except (ValueError, TypeError):
            atm_pe_plus20 = 20
        try:
            ce_strike_offset = int(request.form.get("ce_strike_offset", ce_strike_offset))
        except (ValueError, TypeError):
            ce_strike_offset = -300
        try:
            pe_strike_offset = int(request.form.get("pe_strike_offset", pe_strike_offset))
        except (ValueError, TypeError):
            pe_strike_offset = 300
        prefix = request.form.get("symbol_prefix")
        if prefix:
            symbol_prefix = prefix.strip()

    return render_template_string(
        TEMPLATE,
        atm_ce_plus20=atm_ce_plus20,
        atm_pe_plus20=atm_pe_plus20,
        symbol_prefix=symbol_prefix,
        ce_strike_offset=ce_strike_offset,
        pe_strike_offset=pe_strike_offset,
        bot_running=bot_running
    )


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
        save_auth_code(auth_code)
        init_fyers(auth_code)
        return "<h2>✅ Authentication Successful! You can return to the app 🚀</h2>"
    return "❌ Authentication failed. Please retry."


@app.route("/fetch")
def fetch_option_chain():
    global fyers, atm_strike, initial_data, atm_ce_plus20, atm_pe_plus20, signals, placed_orders, symbol_prefix
    global ce_strike_offset, pe_strike_offset
    if fyers is None:
        return jsonify({"error": "⚠ Please login first!"})
    try:
        data = {"symbol": "NSE:NIFTY50-INDEX", "strikecount": 20, "timestamp": ""}
        response = fyers.optionchain(data=data)

        if "data" not in response or "optionsChain" not in response["data"]:
            return jsonify({"error": f"Invalid response from API: {response}"})

        options_data = response["data"]["optionsChain"]
        if not options_data:
            return jsonify({"error": "No options data found!"})

        df = pd.DataFrame(options_data)
        
        # Create separate DataFrames for CE and PE options
        ce_df = df[df['option_type'] == 'CE'].copy()
        pe_df = df[df['option_type'] == 'PE'].copy()
        
        # Merge CE and PE data on strike_price
        df_pivot = pd.merge(
            ce_df[['strike_price', 'ltp', 'oi', 'volume']],
            pe_df[['strike_price', 'ltp', 'oi', 'volume']],
            on='strike_price',
            suffixes=('_CE', '_PE')
        )
        
        # Rename columns for clarity
        df_pivot = df_pivot.rename(columns={
            'ltp_CE': 'CE_LTP',
            'oi_CE': 'CE_OI',
            'volume_CE': 'CE_Volume',
            'ltp_PE': 'PE_LTP',
            'oi_PE': 'PE_OI',
            'volume_PE': 'PE_Volume'
        })

        # ---- ATM detection ----
        if atm_strike is None:
            nifty_spot = response["data"].get(
                "underlyingValue",
                df_pivot["strike_price"].iloc[len(df_pivot) // 2]
            )
            atm_strike = min(df_pivot["strike_price"], key=lambda x: abs(x - nifty_spot))
            initial_data = df_pivot.to_dict(orient="records")
            signals.clear()
            placed_orders.clear()

        # ---- Calculate target strikes ----
        ce_target_strike = atm_strike + ce_strike_offset  # Usually ATM - 300
        pe_target_strike = atm_strike + pe_strike_offset  # Usually ATM + 300

        # ---- Order placement for offset strikes (only if bot not running) ----
        if not bot_running:
            for row in df_pivot.itertuples():
                strike = row.strike_price
                ce_ltp = getattr(row, "CE_LTP", None)
                pe_ltp = getattr(row, "PE_LTP", None)

                # CE order at offset strike
                if strike == ce_target_strike and ce_ltp is not None:
                    initial_ce = next((item["CE_LTP"] for item in initial_data if item["strike_price"] == strike), None)
                    if initial_ce is not None and ce_ltp > initial_ce + atm_ce_plus20:
                        signal_name = f"CE_OFFSET_{strike}"
                        if signal_name not in placed_orders:
                            signals.append(f"{strike} {ce_ltp} CE Offset Strike")
                            place_order(f"{symbol_prefix}{strike}CE", ce_ltp, side=1)
                            placed_orders.add(signal_name)

                # PE order at offset strike
                if strike == pe_target_strike and pe_ltp is not None:
                    initial_pe = next((item["PE_LTP"] for item in initial_data if item["strike_price"] == strike), None)
                    if initial_pe is not None and pe_ltp > initial_pe + atm_pe_plus20:
                        signal_name = f"PE_OFFSET_{strike}"
                        if signal_name not in placed_orders:
                            signals.append(f"{strike} {pe_ltp} PE Offset Strike")
                            place_order(f"{symbol_prefix}{strike}PE", pe_ltp, side=1)
                            placed_orders.add(signal_name)

        return df_pivot.to_json(orient="records")
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/positions")
def get_positions():
    """Get current positions"""
    if fyers is None:
        return jsonify({"error": "⚠ Please login first!"})
    
    try:
        positions = fyers.positions()
        if positions and "netPositions" in positions:
            # Filter only open positions (netQty != 0)
            open_positions = [pos for pos in positions["netPositions"] if int(pos.get("netQty", 0)) != 0]
            return jsonify({"positions": open_positions})
        return jsonify({"positions": []})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/exit_position", methods=["POST"])
def exit_single_position():
    """Exit a single position"""
    data = request.get_json()
    symbol = data.get("symbol")
    qty = data.get("qty")
    side = data.get("side")
    productType = data.get("productType", "INTRADAY")
    
    result = exit_position(symbol, qty, side, productType)
    return jsonify(result)


@app.route("/start_bot", methods=["POST"])
def start_bot():
    global bot_running, bot_thread

    if fyers is None:
        return jsonify({"error": "⚠️ Please login first!"})

    if bot_running:
        return jsonify({"error": "⚠️ Bot is already running!"})

    bot_running = True
    bot_thread = threading.Thread(target=background_bot_worker, daemon=True)
    bot_thread.start()

    return jsonify({"message": "✅ Bot started! Running in background - you can close browser now!"})


@app.route("/stop_bot", methods=["POST"])
def stop_bot():
    global bot_running
    bot_running = False
    return jsonify({"message": "✅ Bot stopped!"})


@app.route("/exit_all", methods=["POST"])
def exit_all():
    """Exit all open positions"""
    result = exit_all_positions()
    return jsonify(result)


@app.route("/bot_status")
def bot_status():
    return jsonify({
        "running": bot_running,
        "signals": signals,
        "placed_orders": list(placed_orders)
    })


@app.route("/reset", methods=["POST"])
def reset_orders():
    global placed_orders, signals, atm_strike, initial_data, ce_strike_offset, pe_strike_offset
    placed_orders.clear()
    signals.clear()
    atm_strike = None
    initial_data = None
    return jsonify({"message": "✅ Reset successful! You can trade again."})


# ---- HTML Template ----
TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Sajid Shaikh Algo Software</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f4f4f9; padding: 20px; }
    h2 { color: #1a73e8; }
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
  </style>
  <script>
    var atmStrike = null;
    var initialLTP = {};
    var initialOI = {};
    var initialVolume = {};
    var signals = [];

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
        alert(data.message || data.error);
        checkBotStatus();
    }

    async function stopBackgroundBot(){
        let res = await fetch("/stop_bot", {method: "POST"});
        let data = await res.json();
        alert(data.message);
        checkBotStatus();
    }

    async function exitAllPositions(){
        if(!confirm("⚠️ Are you sure you want to exit ALL positions? This action cannot be undone!")){
            return;
        }
        let res = await fetch("/exit_all", {method: "POST"});
        let data = await res.json();
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

        let atm_ce_plus20 = parseFloat(document.getElementById("atm_ce_plus20").value) || 20;
        let atm_pe_plus20 = parseFloat(document.getElementById("atm_pe_plus20").value) || 20;

        if(ceOffsetLive){
            if(ceOffsetLive.CE_LTP > (initialLTP[ceOffsetStrike]?.CE + atm_ce_plus20)){
                signals.push("CE Offset Strike");
            }
        }

        if(peOffsetLive){
            if(peOffsetLive.PE_LTP > (initialLTP[peOffsetStrike]?.PE + atm_pe_plus20)){
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
                let pe_volume_change = row.PE_Volume - initialVolume[row.strike_price]?.PE;
                
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

    setInterval(fetchChain, 2000);
    setInterval(fetchPositions, 3000); // Update positions every 3 seconds
    setInterval(checkBotStatus, 3000);
    window.onload = function(){
        fetchChain();
        fetchPositions();
        checkBotStatus();
    };

    async function resetOrders(){
        let res = await fetch("/reset", {method: "POST"});
        let data = await res.json();
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
  <h2>Sajid Shaikh Algo Software : +91 9834370368</h2>

  <div class="bot-control">
    <div id="botStatus">
      <span class="bot-status status-stopped">⏸️ Bot Stopped</span>
    </div>
    <p style="margin: 10px 0; color: #666;">
      ℹ️ Start background bot to run continuously even when browser is minimized/closed
    </p>
    <button id="startBtn" class="btn-start" onclick="startBackgroundBot()">▶️ Start Background Bot</button>
    <button id="stopBtn" class="btn-stop" onclick="stopBackgroundBot()" disabled>⏸️ Stop Bot</button>
    <button class="btn-exit" onclick="exitAllPositions()">🚪 Exit All Positions</button>
    <a href="/login" target="_blank">🔑 Login</a>
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
    <label>CE Threshold (+ over initial):</label>
    <input type="number" id="atm_ce_plus20" name="atm_ce_plus20" step="0.1" value="{{ atm_ce_plus20 }}" required>
    <label>PE Threshold (+ over initial):</label>
    <input type="number" id="atm_pe_plus20" name="atm_pe_plus20" step="0.1" value="{{ atm_pe_plus20 }}" required>
    <br><br>
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
    print("🚀 Sajid Shaikh Algo Trading Bot")
    print("="*60)
    print(f"📍 Server: http://127.0.0.1:{port}")
    print("✅ Background bot available - runs even when browser closed!")
    print("✅ Positions display with individual exit buttons added!")
    print("✅ OI and Volume values now displayed in crores!")
    print("="*60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
