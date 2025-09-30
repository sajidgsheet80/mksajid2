from fyers_apiv3 import fyersModel
from flask import Flask, redirect, request, render_template_string
import webbrowser
import pandas as pd
import os
import math
import traceback
import json

# ---- Credentials ----
client_id = "VMS68P9EK0-100"
secret_key = "ZJ0CFWZEL1"
redirect_uri = "http://127.0.0.1:5000/callback"

# ---- Session ----
appSession = fyersModel.SessionModel(
    client_id=client_id,
    secret_key=secret_key,
    redirect_uri=redirect_uri,
    response_type="code",
    grant_type="authorization_code",
    state="sample"
)

# ---- Flask ----
app = Flask(__name__)
app.secret_key = "sajid_secret"
fyers = None

# ---- Symbol Mapping ----
symbols_map = {
    "NIFTY50": "NSE:NIFTY50-INDEX",
    "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
    "FINNIFTY": "NSE:FINNIFTY-INDEX",
    "MIDCAPNIFTY": "NSE:MIDCPNIFTY-INDEX",
    "SENSEX": "BSE:SENSEX-INDEX"
}

# Updated display columns to match your format
display_cols = ["theta", "delta", "ltp", "ltpch", "oi", "oich", "oichp", "prev_oi", "volume"]

previous_data = {}  # Store previous rows for diff

@app.route("/")
def home():
    return """
    <h2>Sajid Shaikh Algo Software : +91 9834370368</h2>
    <a href="/login" target="_blank">🔑 Login</a> |
    <a href="/chain?index=NIFTY50" target="_blank">📊 View Option Chain</a>
    <hr>
    <h1>Under Testing and Validation.</h1>
    """

@app.route("/login")
def login():
    login_url = appSession.generate_authcode()
    webbrowser.open(login_url, new=1)
    return redirect(login_url)

@app.route("/callback")
def callback():
    global fyers
    auth_code = request.args.get("auth_code")
    if auth_code:
        try:
            appSession.set_token(auth_code)
            token_response = appSession.generate_token()
            access_token = token_response.get("access_token")
            fyers = fyersModel.FyersModel(client_id=client_id, token=access_token, is_async=False)
            return "<h2>✅ Authentication Successful! You can return to the app 🚀</h2>"
        except Exception as e:
            return f"<h3>Callback error: {str(e)}</h3>"
    return "❌ Authentication failed. Please retry."

@app.route("/chain")
def fetch_option_chain():
    global fyers
    if fyers is None:
        return "<h3>⚠ Please <a href='/login'>login</a> first!</h3>"

    index_name = request.args.get("index", "NIFTY50")
    symbol = symbols_map.get(index_name, "NSE:NIFTY50-INDEX")

    try:
        table_html, spot_price, analysis_html, ce_headers, pe_headers = generate_full_table(index_name, symbol)
    except Exception as e:
        table_html = f"<p>Error fetching option chain: {str(e)}</p>"
        spot_price = ""
        analysis_html = ""

    html = f"""
    <!doctype html>
    <html>
    <head>
        <title>{index_name} Option Chain (ATM ±3)</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 16px; }}
            h2 {{ text-align:center; color:#1a73e8; }}
            table {{ width:100%; border-collapse: collapse; font-size:12px; }}
            th, td {{ border:1px solid #ddd; padding:4px; text-align:center; }}
            th {{ background:#1a73e8; color:#fff; font-weight: bold; }}
            tr:nth-child(even) {{ background:#f7f7f7; }}
            .dropdown {{ margin:12px 0; text-align:center; }}
            #analysis {{ background:#eef; padding:10px; border-radius:5px; margin-top:15px; }}
            .strike-cell {{ background:#ffeb3b; font-weight: bold; }}
            .total-row {{ background-color: #c8e6c9; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1 align=center >Sajid Shaikh</h1>
        <h2 id="spot-title">{index_name} Option Chain (ATM ±3) — Spot: {spot_price}</h2>

        <div class="dropdown">
            <form method="get" action="/chain">
                <label for="index">Select Index: </label>
                <select name="index" id="index" onchange="this.form.submit()">
                    <option value="NIFTY50" {"selected" if index_name=="NIFTY50" else ""}>NIFTY50</option>
                    <option value="BANKNIFTY" {"selected" if index_name=="BANKNIFTY" else ""}>BANKNIFTY</option>
                    <option value="FINNIFTY" {"selected" if index_name=="FINNIFTY" else ""}>FINNIFTY</option>
                    <option value="MIDCAPNIFTY" {"selected" if index_name=="MIDCAPNIFTY" else ""}>MIDCAPNIFTY</option>
                    <option value="SENSEX" {"selected" if index_name=="SENSEX" else ""}>SENSEX</option>
                </select>
            </form>
        </div>

        <table id="option-chain-table">
            <thead><tr>{ce_headers}<th class="strike-cell">STRIKE</th>{pe_headers}</tr></thead>
            <tbody>{table_html}</tbody>
        </table>

        <div id="analysis">{analysis_html}</div>

        <script>
            const indexName = "{index_name}";
            async function refreshTableRows() {{
                try {{
                    const resp = await fetch(`/chain_rows_diff?index=${{indexName}}`);
                    const result = await resp.json();
                    if (result.rows) {{
                        document.querySelector("#option-chain-table tbody").innerHTML = result.rows;
                        document.querySelector("#spot-title").innerHTML = `${{indexName}} Option Chain (ATM ±3) — Spot: ${{result.spot}}`;
                        document.querySelector("#analysis").innerHTML = result.analysis;
                    }}
                }} catch (err) {{
                    console.error("Error refreshing rows:", err);
                }}
            }}
            setInterval(refreshTableRows, 3000);
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route("/chain_rows_diff")
def chain_rows_diff():
    global previous_data
    index_name = request.args.get("index", "NIFTY50")
    symbol = symbols_map.get(index_name, "NSE:NIFTY50-INDEX")

    rows_html, spot_price, analysis_html, _, _ = generate_rows(index_name, symbol)

    current_data = {"rows": rows_html, "analysis": analysis_html}

    diff_rows = ""
    if previous_data.get(index_name) != current_data["rows"]:
        diff_rows = current_data["rows"]
        previous_data[index_name] = current_data["rows"]

    return json.dumps({"rows": diff_rows, "spot": spot_price, "analysis": analysis_html})

def generate_full_table(index_name, symbol):
    rows_html, spot_price, analysis_html, ce_headers, pe_headers = generate_rows(index_name, symbol)
    return rows_html, spot_price, analysis_html, ce_headers, pe_headers

def calculate_greeks(spot_price, strike_price, option_type, ltp, days_to_expiry=30):
    """
    Simple approximation for THETA and DELTA
    Note: For accurate Greeks, you'd need proper Black-Scholes implementation
    """
    try:
        # Simple delta approximation
        if option_type == "CE":
            if spot_price > strike_price:
                delta = -0.99 if (spot_price - strike_price) > 100 else -1.0
            else:
                delta = -1.0
        else:  # PE
            if spot_price < strike_price:
                delta = -1.0
            else:
                delta = -1.0

        # Simple theta approximation (time decay)
        theta = -ltp * 0.1 if ltp and ltp > 0 else 0

        return round(theta, 2), delta
    except:
        return 0, -1

def generate_rows(index_name, symbol):
    global fyers
    data = {"symbol": symbol, "strikecount": 50}
    response = fyers.optionchain(data=data)
    data_section = response.get("data", {}) if isinstance(response, dict) else {}
    options_data = data_section.get("optionsChain") or data_section.get("options_chain") or []

    if not options_data:
        return "", "", "<p>No option chain data available.</p>", "", ""

    df = pd.json_normalize(options_data)
    if "strike_price" not in df.columns:
        possible_strike_cols = [c for c in df.columns if "strike" in c.lower()]
        if possible_strike_cols:
            df = df.rename(columns={possible_strike_cols[0]: "strike_price"})

    num_cols = ["strike_price", "ltp", "oi", "oich", "oichp", "prev_oi", "volume", "ltpch"]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    spot_price = None
    for key in ("underlying_value", "underlyingValue", "underlying", "underlying_value_instrument"):
        if data_section.get(key) is not None:
            try:
                spot_price = float(data_section.get(key))
                break
            except Exception:
                pass

    strikes_all = sorted(df["strike_price"].dropna().unique())
    if spot_price is None:
        spot_price = float(strikes_all[len(strikes_all)//2]) if strikes_all else 0

    # Calculate Greeks for each option
    theta_list = []
    delta_list = []
    for _, row in df.iterrows():
        theta, delta = calculate_greeks(
            spot_price,
            row.get('strike_price', 0),
            row.get('option_type', 'CE'),
            row.get('ltp', 0)
        )
        theta_list.append(theta)
        delta_list.append(delta)

    df['theta'] = theta_list
    df['delta'] = delta_list

    atm_strike = min(strikes_all, key=lambda s: abs(s - spot_price)) if strikes_all else 0
    atm_index = strikes_all.index(atm_strike) if atm_strike in strikes_all else 0
    low = max(0, atm_index - 3)
    high = min(len(strikes_all), atm_index + 4)
    strikes_to_show = strikes_all[low:high] if strikes_all else []

    df = df[df["strike_price"].isin(strikes_to_show)]
    ce_df = df[df["option_type"] == "CE"].set_index("strike_price", drop=False) if "option_type" in df.columns else pd.DataFrame()
    pe_df = df[df["option_type"] == "PE"].set_index("strike_price", drop=False) if "option_type" in df.columns else pd.DataFrame()

    # Updated column order to match your format
    lr_cols = ["theta", "delta", "ltp", "ltpch", "oi", "oich", "oichp", "prev_oi", "volume"]

    rows_html = ""
    for strike in strikes_to_show:
        ce_cells = ""
        pe_cells = ""
        for c in lr_cols:
            ce_val = ce_df.loc[strike, c] if (not ce_df.empty and strike in ce_df.index and c in ce_df.columns) else ""
            pe_val = pe_df.loc[strike, c] if (not pe_df.empty and strike in pe_df.index and c in pe_df.columns) else ""

            # Format values properly
            if isinstance(ce_val, (int, float)) and not pd.isna(ce_val):
                if c in ['theta', 'ltpch']:
                    ce_val = f"{ce_val:.2f}" if ce_val != 0 else ""
                elif c == 'delta':
                    ce_val = f"{ce_val:.2f}" if ce_val != 0 else ""
                elif c in ['oi', 'oich', 'prev_oi', 'volume']:
                    ce_val = f"{int(ce_val):,}" if ce_val != 0 else ""
                else:
                    ce_val = f"{ce_val:.2f}" if ce_val != 0 else ""

            if isinstance(pe_val, (int, float)) and not pd.isna(pe_val):
                if c in ['theta', 'ltpch']:
                    pe_val = f"{pe_val:.2f}" if pe_val != 0 else ""
                elif c == 'delta':
                    pe_val = f"{pe_val:.2f}" if pe_val != 0 else ""
                elif c in ['oi', 'oich', 'prev_oi', 'volume']:
                    pe_val = f"{int(pe_val):,}" if pe_val != 0 else ""
                else:
                    pe_val = f"{pe_val:.2f}" if pe_val != 0 else ""

            ce_cells += f"<td>{ce_val}</td>"
            pe_cells += f"<td>{pe_val}</td>"

        row_style = "style='background-color: #ffeb3b; font-weight: bold;'" if strike == atm_strike else ""
        rows_html += f"<tr {row_style}>{ce_cells}<td class='strike-cell'><b>{int(strike)}</b></td>{pe_cells}</tr>"

    # Calculate totals
    ce_totals = ce_df[lr_cols].sum(numeric_only=True) if not ce_df.empty else pd.Series(0, index=lr_cols)
    pe_totals = pe_df[lr_cols].sum(numeric_only=True) if not pe_df.empty else pd.Series(0, index=lr_cols)

    ce_headers, pe_headers = generate_headers()

    # CE Total row (displayed in PE side for comparison)
    ce_totals_cells = ""
    for col in lr_cols:
        val = ce_totals.get(col, 0)
        if col in ['oi', 'oich', 'prev_oi', 'volume']:
            formatted_val = f"{int(val):,}" if val != 0 else "0"
        else:
            formatted_val = f"{val:.2f}" if val != 0 else "0"
        ce_totals_cells += f"<td><b>{formatted_val}</b></td>"

    rows_html += f"<tr class='total-row'><td colspan='{len(lr_cols)}'></td><td><b>CE Total</b></td>{ce_totals_cells}</tr>"

    # PE Total row (also displayed in PE side for comparison)
    pe_totals_cells = ""
    for col in lr_cols:
        val = pe_totals.get(col, 0)
        if col in ['oi', 'oich', 'prev_oi', 'volume']:
            formatted_val = f"{int(val):,}" if val != 0 else "0"
        else:
            formatted_val = f"{val:.2f}" if val != 0 else "0"
        pe_totals_cells += f"<td><b>{formatted_val}</b></td>"

    rows_html += f"<tr class='total-row'><td colspan='{len(lr_cols)}'></td><td><b>PE Total</b></td>{pe_totals_cells}</tr>"

    analysis_html = generate_market_insights(ce_df, pe_df, spot_price)

    return rows_html, spot_price, analysis_html, ce_headers, pe_headers

def generate_headers():
    lr_cols = ["theta", "delta", "ltp", "ltpch", "oi", "oich", "oichp", "prev_oi", "volume"]
    ce_headers = "".join([f"<th>{c.upper()}</th>" for c in lr_cols])
    pe_headers = "".join([f"<th>{c.upper()}</th>" for c in lr_cols])
    return ce_headers, pe_headers

def calculate_signal_strength(ce_df, pe_df, pcr):
    try:
        strength = 0

        # PCR based strength
        if pcr:
            if pcr > 1.5 or pcr < 0.5:
                strength += 3  # Strong signal
            elif pcr > 1.2 or pcr < 0.8:
                strength += 2  # Medium signal
            else:
                strength += 1  # Weak signal

        # Volume analysis
        total_ce_vol = ce_df['volume'].sum() if not ce_df.empty else 0
        total_pe_vol = pe_df['volume'].sum() if not pe_df.empty else 0

        if total_ce_vol > 0 and total_pe_vol > 0:
            vol_ratio = max(total_ce_vol, total_pe_vol) / min(total_ce_vol, total_pe_vol)
            if vol_ratio > 2:
                strength += 2
            elif vol_ratio > 1.5:
                strength += 1

        # OI change analysis
        ce_oi_change = ce_df['oich'].sum() if not ce_df.empty else 0
        pe_oi_change = pe_df['oich'].sum() if not pe_df.empty else 0

        if abs(ce_oi_change) > 100000 or abs(pe_oi_change) > 100000:
            strength += 2

        return min(strength, 5)  # Cap at 5

    except Exception as e:
        return 1

def generate_market_insights(ce_df, pe_df, spot_price):
    try:
        total_ce_oi = ce_df["oi"].sum() if not ce_df.empty else 0
        total_pe_oi = pe_df["oi"].sum() if not pe_df.empty else 0
        pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else None

        strongest_support = pe_df.loc[pe_df["oi"].idxmax(), "strike_price"] if not pe_df.empty else None
        strongest_resistance = ce_df.loc[ce_df["oi"].idxmax(), "strike_price"] if not ce_df.empty else None

        ce_vol = ce_df["volume"].sum() if not ce_df.empty else 0
        pe_vol = pe_df["volume"].sum() if not pe_df.empty else 0
        volume_trend = "CE Volume > PE Volume → Bullish" if ce_vol > pe_vol else "PE Volume > CE Volume → Bearish"

        ltp_trend = "LTP falling 📉" if (ce_df["ltpch"].mean() < 0 and pe_df["ltpch"].mean() < 0) else \
                    "LTP rising 📈" if (ce_df["ltpch"].mean() > 0 and pe_df["ltpch"].mean() > 0) else "Sideways ⚖️"

        trend_bias = ""
        if pcr is not None:
            if pcr > 1:
                trend_bias = "Bearish 📉"
            elif pcr < 0.8:
                trend_bias = "Bullish 📈"
            else:
                trend_bias = "Neutral ⚖️"

        # Advanced Trading Recommendations
        trading_recommendations = generate_trading_recommendations(ce_df, pe_df, spot_price, pcr)

        return f"""
        <h3>🔎 Market Insights</h3>
        <ul>
            <li><b>Spot Price:</b> {spot_price}</li>
            <li><b>Total CE OI:</b> {total_ce_oi:,.0f}</li>
            <li><b>Total PE OI:</b> {total_pe_oi:,.0f}</li>
            <li><b>Put-Call Ratio (PCR):</b> {pcr}</li>
            <li><b>Volume Trend:</b> {volume_trend}</li>
            <li><b>Strongest Support (PE OI):</b> {strongest_support}</li>
            <li><b>Strongest Resistance (CE OI):</b> {strongest_resistance}</li>
            <li><b>Trend Bias:</b> {trend_bias}</li>
        </ul>

        {trading_recommendations}

        <h1>It a product of Mohammed Kareemuddin Sajid Shaikh</h1>
        """
    except Exception as e:
        return f"<p>Error in analysis: {e}</p>"

def generate_trading_recommendations(ce_df, pe_df, spot_price, pcr):
    try:
        recommendations = "<h3>🎯 Trading Recommendations</h3>"

        # Determine market direction
        if pcr and pcr > 1.2:
            market_direction = "BEARISH"
            primary_strategy = "PUT"
            secondary_strategy = "CALL"
        elif pcr and pcr < 0.8:
            market_direction = "BULLISH"
            primary_strategy = "CALL"
            secondary_strategy = "PUT"
        else:
            market_direction = "SIDEWAYS"
            primary_strategy = "STRADDLE"
            secondary_strategy = "STRANGLE"

        recommendations += f"<h4>📈 Market Direction: {market_direction}</h4>"

        # Generate LIVE SIGNALS
        live_signals = generate_live_signals(ce_df, pe_df, spot_price, pcr, market_direction)

        # PROFIT MAXIMIZATION FEATURES
        profit_features = generate_profit_maximization_features(ce_df, pe_df, spot_price, pcr)

        # Best strikes for trading
        best_strikes = find_best_trading_strikes(ce_df, pe_df, spot_price, market_direction)

        # Time recommendations
        time_recommendation = get_time_recommendation()

        # LTP analysis and targets
        ltp_analysis = analyze_ltp_targets(ce_df, pe_df, spot_price, market_direction)

        recommendations += f"""
        <div style='background: #ff6b6b; color: white; padding: 15px; border-radius: 5px; margin: 10px 0; border: 2px solid #ff5252;'>
            <h4>🚨 LIVE TRADING SIGNALS 🚨</h4>
            {live_signals}
        </div>

        <div style='background: #4CAF50; color: white; padding: 15px; border-radius: 5px; margin: 10px 0; border: 2px solid #45a049;'>
            <h4>💰 PROFIT MAXIMIZATION TOOLKIT 💰</h4>
            {profit_features}
        </div>

        <div style='background: #f0f8ff; padding: 10px; border-radius: 5px; margin: 10px 0;'>
            <h4>🏆 Best Strikes to Trade:</h4>
            {best_strikes}
        </div>

        <div style='background: #f5f5dc; padding: 10px; border-radius: 5px; margin: 10px 0;'>
            <h4>⏰ Best Time to Trade:</h4>
            {time_recommendation}
        </div>

        <div style='background: #f0fff0; padding: 10px; border-radius: 5px; margin: 10px 0;'>
            <h4>💰 LTP Analysis & Targets:</h4>
            {ltp_analysis}
        </div>
        """

        return recommendations
    except Exception as e:
        return f"<p>Error in trading recommendations: {e}</p>"

def generate_live_signals(ce_df, pe_df, spot_price, pcr, market_direction):
    try:
        import datetime
        current_time = datetime.datetime.now()
        signal_time = current_time.strftime("%H:%M:%S")

        signals = f"<div style='text-align: center; font-size: 14px; margin-bottom: 10px;'>"
        signals += f"<b>🕒 Signal Time: {signal_time}</b><br>"
        signals += f"<b>📍 Spot: ₹{spot_price}</b> | <b>PCR: {pcr}</b></div>"

        # Signal strength calculation
        signal_strength = calculate_signal_strength(ce_df, pe_df, pcr)

        # Generate specific signals based on multiple factors
        if market_direction == "BULLISH":
            if not ce_df.empty:
                # Find best call option
                ce_filtered = ce_df[(ce_df['ltp'] > 0) & (ce_df['volume'] > 100)].copy()
                if not ce_filtered.empty:
                    # Sort by a combination of volume, OI change, and proximity to ATM
                    ce_filtered['signal_score'] = (
                        ce_filtered['volume'] * 0.3 +
                        ce_filtered['oich'] * 0.2 +
                        abs(ce_filtered['delta']) * 100 +
                        (1000 / (abs(ce_filtered['strike_price'] - spot_price) + 1))
                    )

                    best_call = ce_filtered.loc[ce_filtered['signal_score'].idxmax()]

                    # Determine signal type
                    if best_call['ltpch'] > 5 and best_call['oich'] > 10000:
                        signal_type = "🟢 STRONG BUY"
                        confidence = "HIGH"
                    elif best_call['ltpch'] > 0 and best_call['volume'] > ce_filtered['volume'].median():
                        signal_type = "🔵 BUY"
                        confidence = "MEDIUM"
                    else:
                        signal_type = "🟡 WATCH"
                        confidence = "LOW"

                    entry_price = best_call['ltp']
                    target1 = entry_price * 1.15
                    target2 = entry_price * 1.30
                    stop_loss = entry_price * 0.85

                    signals += f"<div style='background: #4caf50; color: white; padding: 8px; border-radius: 3px; margin: 5px 0;'>"
                    signals += f"<b>{signal_type}</b> | Confidence: <b>{confidence}</b><br>"
                    signals += f"<b>📈 {int(best_call['strike_price'])} CE</b><br>"
                    signals += f"Entry: ₹{entry_price:.2f} | T1: ₹{target1:.2f} | T2: ₹{target2:.2f}<br>"
                    signals += f"Stop Loss: ₹{stop_loss:.2f} | Volume: {int(best_call['volume']):,}"
                    signals += f"</div>"

        elif market_direction == "BEARISH":
            if not pe_df.empty:
                # Find best put option
                pe_filtered = pe_df[(pe_df['ltp'] > 0) & (pe_df['volume'] > 100)].copy()
                if not pe_filtered.empty:
                    pe_filtered['signal_score'] = (
                        pe_filtered['volume'] * 0.3 +
                        pe_filtered['oich'] * 0.2 +
                        abs(pe_filtered['delta']) * 100 +
                        (1000 / (abs(pe_filtered['strike_price'] - spot_price) + 1))
                    )

                    best_put = pe_filtered.loc[pe_filtered['signal_score'].idxmax()]

                    if best_put['ltpch'] > 5 and best_put['oich'] > 10000:
                        signal_type = "🔴 STRONG SELL"
                        confidence = "HIGH"
                    elif best_put['ltpch'] > 0 and best_put['volume'] > pe_filtered['volume'].median():
                        signal_type = "🟠 SELL"
                        confidence = "MEDIUM"
                    else:
                        signal_type = "🟡 WATCH"
                        confidence = "LOW"

                    entry_price = best_put['ltp']
                    target1 = entry_price * 1.15
                    target2 = entry_price * 1.30
                    stop_loss = entry_price * 0.85

                    signals += f"<div style='background: #f44336; color: white; padding: 8px; border-radius: 3px; margin: 5px 0;'>"
                    signals += f"<b>{signal_type}</b> | Confidence: <b>{confidence}</b><br>"
                    signals += f"<b>📉 {int(best_put['strike_price'])} PE</b><br>"
                    signals += f"Entry: ₹{entry_price:.2f} | T1: ₹{target1:.2f} | T2: ₹{target2:.2f}<br>"
                    signals += f"Stop Loss: ₹{stop_loss:.2f} | Volume: {int(best_put['volume']):,}"
                    signals += f"</div>"

        else:  # SIDEWAYS
            signals += f"<div style='background: #ff9800; color: white; padding: 8px; border-radius: 3px; margin: 5px 0;'>"
            signals += f"<b>⚖️ SIDEWAYS MARKET</b><br>"
            signals += f"<b>Strategy:</b> Iron Condor or Short Straddle<br>"
            signals += f"<b>ATM Strike:</b> {int(spot_price)}<br>"
            signals += f"<b>Action:</b> Wait for breakout or sell premium"
            signals += f"</div>"

        # Add risk disclaimer
        signals += f"<div style='background: #ffc107; color: black; padding: 5px; border-radius: 3px; margin: 10px 0; font-size: 11px;'>"
        signals += f"⚠️ <b>DISCLAIMER:</b> Signals are based on technical analysis. Trade at your own risk. "
        signals += f"Always use proper risk management and position sizing."
        signals += f"</div>"

        return signals

    except Exception as e:
        return f"<p>Error generating live signals: {e}</p>"

def generate_profit_maximization_features(ce_df, pe_df, spot_price, pcr):
    try:
        profit_features = ""

        # 1. ARBITRAGE OPPORTUNITIES
        arbitrage = detect_arbitrage_opportunities(ce_df, pe_df, spot_price)

        # 2. VOLATILITY CRUSH PREDICTIONS
        vol_crush = predict_volatility_crush(ce_df, pe_df)

        # 3. SPREAD STRATEGIES
        spread_strategies = suggest_spread_strategies(ce_df, pe_df, spot_price, pcr)

        # 4. SCALPING OPPORTUNITIES
        scalping_ops = find_scalping_opportunities(ce_df, pe_df, spot_price)

        # 5. MOMENTUM BREAKOUT ALERTS
        breakout_alerts = detect_breakout_momentum(ce_df, pe_df, spot_price)

        # 6. RISK-REWARD OPTIMIZER
        risk_reward = optimize_risk_reward_ratios(ce_df, pe_df, spot_price)

        profit_features += f"""
        <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 10px;'>
            <div style='background: green; padding: 8px; border-radius: 5px; border-left: 4px solid #4CAF50;'>
                <h5>🔍 ARBITRAGE SCANNER</h5>
                {arbitrage}
            </div>
            <div style='background: green; padding: 8px; border-radius: 5px; border-left: 4px solid #FF9800;'>
                <h5>📉 VOLATILITY CRUSH ALERT</h5>
                {vol_crush}
            </div>
            <div style='background: green; padding: 8px; border-radius: 5px; border-left: 4px solid #2196F3;'>
                <h5>📊 SPREAD STRATEGIES</h5>
                {spread_strategies}
            </div>
            <div style='background: green; padding: 8px; border-radius: 5px; border-left: 4px solid #E91E63;'>
                <h5>⚡ SCALPING ALERTS</h5>
                {scalping_ops}
            </div>
            <div style='background: green; padding: 8px; border-radius: 5px; border-left: 4px solid #9C27B0;'>
                <h5>🚀 BREAKOUT MOMENTUM</h5>
                {breakout_alerts}
            </div>
            <div style='background: green; padding: 8px; border-radius: 5px; border-left: 4px solid #009688;'>
                <h5>⚖️ RISK-REWARD OPTIMIZER</h5>
                {risk_reward}
            </div>
        </div>
        """

        return profit_features

    except Exception as e:
        return f"<p>Error in profit features: {e}</p>"

def detect_arbitrage_opportunities(ce_df, pe_df, spot_price):
    try:
        arbitrage_found = []

        if not ce_df.empty and not pe_df.empty:
            # Put-Call Parity Arbitrage
            for strike in ce_df['strike_price'].unique():
                if strike in pe_df['strike_price'].values:
                    ce_ltp = ce_df[ce_df['strike_price'] == strike]['ltp'].iloc[0]
                    pe_ltp = pe_df[pe_df['strike_price'] == strike]['ltp'].iloc[0]

                    if ce_ltp > 0 and pe_ltp > 0:
                        # Simplified Put-Call Parity check
                        theoretical_diff = abs((ce_ltp - pe_ltp) - (spot_price - strike))

                        if theoretical_diff > 5:  # Significant deviation
                            profit_potential = theoretical_diff * 0.7  # Conservative estimate
                            arbitrage_found.append(f"Strike {int(strike)}: ₹{profit_potential:.2f} potential")

        if arbitrage_found:
            return "<br>".join(arbitrage_found[:2])  # Show top 2
        else:
            return "No arbitrage opportunities detected"

    except Exception as e:
        return "Scanning for opportunities..."

def predict_volatility_crush(ce_df, pe_df):
    try:
        crush_alerts = []

        # Check for high premium options that might crush
        if not ce_df.empty:
            high_premium_ces = ce_df[ce_df['ltp'] > ce_df['ltp'].quantile(0.8)]
            for _, option in high_premium_ces.iterrows():
                if abs(option['theta']) > option['ltp'] * 0.1:  # High theta decay
                    crush_risk = (abs(option['theta']) / option['ltp']) * 100
                    crush_alerts.append(f"{int(option['strike_price'])}CE: {crush_risk:.0f}% decay risk")

        if not pe_df.empty:
            high_premium_pes = pe_df[pe_df['ltp'] > pe_df['ltp'].quantile(0.8)]
            for _, option in high_premium_pes.iterrows():
                if abs(option['theta']) > option['ltp'] * 0.1:
                    crush_risk = (abs(option['theta']) / option['ltp']) * 100
                    crush_alerts.append(f"{int(option['strike_price'])}PE: {crush_risk:.0f}% decay risk")

        if crush_alerts:
            return "<br>".join(crush_alerts[:3])
        else:
            return "Low volatility crush risk"

    except Exception as e:
        return "Analyzing volatility..."

def suggest_spread_strategies(ce_df, pe_df, spot_price, pcr):
    try:
        strategies = []

        if pcr and 0.9 < pcr < 1.1:  # Neutral market
            strategies.append("🦋 Iron Butterfly: High profit potential")
            strategies.append("🔄 Iron Condor: Steady income strategy")
        elif pcr and pcr > 1.2:  # Bearish
            strategies.append("🐻 Bear Put Spread: Limited risk bearish")
            strategies.append("📉 Call Credit Spread: Premium collection")
        elif pcr and pcr < 0.8:  # Bullish
            strategies.append("🐂 Bull Call Spread: Limited risk bullish")
            strategies.append("📈 Put Credit Spread: Premium collection")

        # Add specific strike recommendations
        if not ce_df.empty and not pe_df.empty:
            atm_strike = min(ce_df['strike_price'], key=lambda x: abs(x - spot_price))
            strategies.append(f"ATM Strike: {int(atm_strike)} for spreads")

        return "<br>".join(strategies[:3])

    except Exception as e:
        return "Analyzing spread opportunities..."

def find_scalping_opportunities(ce_df, pe_df, spot_price):
    try:
        scalping_alerts = []

        # High volume, high volatility options for scalping
        combined_df = pd.concat([ce_df, pe_df], ignore_index=True) if not ce_df.empty and not pe_df.empty else pd.DataFrame()

        if not combined_df.empty:
            # Filter for liquid options
            liquid_options = combined_df[
                (combined_df['volume'] > combined_df['volume'].quantile(0.7)) &
                (combined_df['ltp'] > 0) &
                (abs(combined_df['ltpch']) > 2)  # Good price movement
            ]

            for _, option in liquid_options.head(3).iterrows():
                option_type = "CE" if option['option_type'] == "CE" else "PE"
                momentum = "📈" if option['ltpch'] > 0 else "📉"
                scalping_alerts.append(
                    f"{momentum} {int(option['strike_price'])}{option_type}: "
                    f"₹{option['ltpch']:+.2f} move"
                )

        if scalping_alerts:
            return "<br>".join(scalping_alerts)
        else:
            return "Looking for scalping setups..."

    except Exception as e:
        return "Scanning for quick trades..."

def detect_breakout_momentum(ce_df, pe_df, spot_price):
    try:
        momentum_alerts = []

        # Detect unusual activity patterns
        if not ce_df.empty:
            ce_vol_avg = ce_df['volume'].mean()
            ce_unusual = ce_df[ce_df['volume'] > ce_vol_avg * 2]  # 2x average volume

            for _, option in ce_unusual.head(2).iterrows():
                if option['oich'] > 0:  # Positive OI change
                    momentum_alerts.append(f"🔥 {int(option['strike_price'])}CE: Volume spike!")

        if not pe_df.empty:
            pe_vol_avg = pe_df['volume'].mean()
            pe_unusual = pe_df[pe_df['volume'] > pe_vol_avg * 2]

            for _, option in pe_unusual.head(2).iterrows():
                if option['oich'] > 0:
                    momentum_alerts.append(f"🔥 {int(option['strike_price'])}PE: Volume spike!")

        # Support/Resistance breakout alerts
        if not pe_df.empty:
            max_pe_oi_strike = pe_df.loc[pe_df['oi'].idxmax(), 'strike_price']
            if spot_price < max_pe_oi_strike * 1.02:
                momentum_alerts.append(f"⚠️ Near support: {int(max_pe_oi_strike)}")

        if not ce_df.empty:
            max_ce_oi_strike = ce_df.loc[ce_df['oi'].idxmax(), 'strike_price']
            if spot_price > max_ce_oi_strike * 0.98:
                momentum_alerts.append(f"⚠️ Near resistance: {int(max_ce_oi_strike)}")

        return "<br>".join(momentum_alerts[:3]) if momentum_alerts else "No breakout signals yet"

    except Exception as e:
        return "Monitoring breakouts..."

def optimize_risk_reward_ratios(ce_df, pe_df, spot_price):
    try:
        optimization_tips = []

        # Find best risk-reward options
        combined_df = pd.concat([ce_df, pe_df], ignore_index=True) if not ce_df.empty and not pe_df.empty else pd.DataFrame()

        if not combined_df.empty:
            # Calculate risk-reward score
            combined_df['rr_score'] = combined_df.apply(lambda row:
                (row['ltp'] * 1.5) / (row['ltp'] * 0.3) if row['ltp'] > 0 else 0, axis=1)

            # Find options with good risk-reward
            good_rr_options = combined_df[combined_df['rr_score'] > 3].nlargest(2, 'volume')

            for _, option in good_rr_options.iterrows():
                option_type = "CE" if option['option_type'] == "CE" else "PE"
                potential_profit = option['ltp'] * 0.5  # 50% profit target
                max_loss = option['ltp'] * 0.3  # 30% stop loss
                rr_ratio = potential_profit / max_loss if max_loss > 0 else 0

                optimization_tips.append(
                    f"{int(option['strike_price'])}{option_type}: "
                    f"R:R = 1:{rr_ratio:.1f}"
                )

        # Add position sizing advice
        optimization_tips.append("💡 Risk only 1-2% per trade")
        optimization_tips.append("📊 Use 3:1 risk-reward minimum")

        return "<br>".join(optimization_tips[:4])

    except Exception as e:
        return "Calculating optimal ratios..."

def find_best_trading_strikes(ce_df, pe_df, spot_price, market_direction):
    try:
        strikes_info = ""

        if market_direction == "BULLISH":
            # For bullish: ATM/ITM calls with good delta and manageable theta
            if not ce_df.empty:
                ce_df_sorted = ce_df[ce_df['ltp'] > 0].copy()
                ce_df_sorted['score'] = (ce_df_sorted['volume'] * 0.3 +
                                       ce_df_sorted['oi'] * 0.0001 +
                                       abs(ce_df_sorted['delta']) * 100 +
                                       (1 / (abs(ce_df_sorted['theta']) + 1)) * 10)

                if not ce_df_sorted.empty:
                    best_ce = ce_df_sorted.loc[ce_df_sorted['score'].idxmax()]
                    strikes_info += f"<b>🔥 BEST CALL:</b> {int(best_ce['strike_price'])} CE<br>"
                    strikes_info += f"Current LTP: ₹{best_ce['ltp']:.2f} | Delta: {best_ce['delta']:.2f} | Theta: {best_ce['theta']:.2f}<br><br>"

            # Secondary PE for hedging
            if not pe_df.empty:
                otm_puts = pe_df[pe_df['strike_price'] < spot_price * 0.98]
                if not otm_puts.empty:
                    hedge_put = otm_puts.loc[otm_puts['volume'].idxmax()]
                    strikes_info += f"<b>🛡️ HEDGE PUT:</b> {int(hedge_put['strike_price'])} PE<br>"
                    strikes_info += f"LTP: ₹{hedge_put['ltp']:.2f} (for protection)<br>"

        elif market_direction == "BEARISH":
            # For bearish: ATM/ITM puts
            if not pe_df.empty:
                pe_df_sorted = pe_df[pe_df['ltp'] > 0].copy()
                pe_df_sorted['score'] = (pe_df_sorted['volume'] * 0.3 +
                                       pe_df_sorted['oi'] * 0.0001 +
                                       abs(pe_df_sorted['delta']) * 100 +
                                       (1 / (abs(pe_df_sorted['theta']) + 1)) * 10)

                if not pe_df_sorted.empty:
                    best_pe = pe_df_sorted.loc[pe_df_sorted['score'].idxmax()]
                    strikes_info += f"<b>🔥 BEST PUT:</b> {int(best_pe['strike_price'])} PE<br>"
                    strikes_info += f"Current LTP: ₹{best_pe['ltp']:.2f} | Delta: {best_pe['delta']:.2f} | Theta: {best_pe['theta']:.2f}<br><br>"

            # Secondary CE for hedging
            if not ce_df.empty:
                otm_calls = ce_df[ce_df['strike_price'] > spot_price * 1.02]
                if not otm_calls.empty:
                    hedge_call = otm_calls.loc[otm_calls['volume'].idxmax()]
                    strikes_info += f"<b>🛡️ HEDGE CALL:</b> {int(hedge_call['strike_price'])} CE<br>"
                    strikes_info += f"LTP: ₹{hedge_call['ltp']:.2f} (for protection)<br>"

        else:  # SIDEWAYS
            strikes_info += f"<b>📊 SIDEWAYS STRATEGY:</b><br>"
            strikes_info += f"• Consider Iron Condor or Butterfly spreads<br>"
            strikes_info += f"• Sell ATM straddle if high IV<br>"
            strikes_info += f"• ATM Strike: ~{int(spot_price)}<br>"

        return strikes_info
    except Exception as e:
        return f"Error finding best strikes: {e}"

def get_time_recommendation():
    import datetime

    current_time = datetime.datetime.now().time()

    if datetime.time(9, 15) <= current_time <= datetime.time(10, 0):
        return "🌅 <b>OPENING HOUR:</b> High volatility, good for momentum trades. Watch for breakouts!"
    elif datetime.time(10, 0) <= current_time <= datetime.time(11, 30):
        return "📈 <b>MORNING SESSION:</b> Trend establishment phase. Good for directional trades."
    elif datetime.time(11, 30) <= current_time <= datetime.time(14, 0):
        return "😴 <b>LUNCH TIME:</b> Lower volatility. Good for range-bound strategies."
    elif datetime.time(14, 0) <= current_time <= datetime.time(15, 0):
        return "🔥 <b>AFTERNOON POWER:</b> High activity! Best time for intraday trades."
    elif datetime.time(15, 0) <= current_time <= datetime.time(15, 30):
        return "⚡ <b>CLOSING HOUR:</b> Maximum volatility! Quick scalping opportunities but risky."
    else:
        return "🌙 <b>MARKET CLOSED:</b> Use this time for analysis and planning tomorrow's trades."

def analyze_ltp_targets(ce_df, pe_df, spot_price, market_direction):
    try:
        analysis = ""

        if market_direction == "BULLISH" and not ce_df.empty:
            # Find ATM/ITM calls
            atm_calls = ce_df[abs(ce_df['strike_price'] - spot_price) <= 100]
            if not atm_calls.empty:
                best_call = atm_calls.loc[atm_calls['volume'].idxmax()]
                current_ltp = best_call['ltp']
                theta_decay = abs(best_call['theta'])

                # Calculate targets based on delta and theta
                target_1 = current_ltp * 1.25  # 25% profit
                target_2 = current_ltp * 1.50  # 50% profit
                stop_loss = current_ltp * 0.75  # 25% loss

                analysis += f"<b>📊 CALL OPTION ANALYSIS:</b><br>"
                analysis += f"Strike: {int(best_call['strike_price'])} CE<br>"
                analysis += f"Current LTP: ₹{current_ltp:.2f}<br>"
                analysis += f"🎯 Target 1: ₹{target_1:.2f} (25% profit)<br>"
                analysis += f"🎯 Target 2: ₹{target_2:.2f} (50% profit)<br>"
                analysis += f"🛑 Stop Loss: ₹{stop_loss:.2f} (25% loss)<br>"
                analysis += f"⚠️ Theta Decay: -₹{theta_decay:.2f} per day<br><br>"

        elif market_direction == "BEARISH" and not pe_df.empty:
            # Find ATM/ITM puts
            atm_puts = pe_df[abs(pe_df['strike_price'] - spot_price) <= 100]
            if not atm_puts.empty:
                best_put = atm_puts.loc[atm_puts['volume'].idxmax()]
                current_ltp = best_put['ltp']
                theta_decay = abs(best_put['theta'])

                target_1 = current_ltp * 1.25
                target_2 = current_ltp * 1.50
                stop_loss = current_ltp * 0.75

                analysis += f"<b>📊 PUT OPTION ANALYSIS:</b><br>"
                analysis += f"Strike: {int(best_put['strike_price'])} PE<br>"
                analysis += f"Current LTP: ₹{current_ltp:.2f}<br>"
                analysis += f"🎯 Target 1: ₹{target_1:.2f} (25% profit)<br>"
                analysis += f"🎯 Target 2: ₹{target_2:.2f} (50% profit)<br>"
                analysis += f"🛑 Stop Loss: ₹{stop_loss:.2f} (25% loss)<br>"
                analysis += f"⚠️ Theta Decay: -₹{theta_decay:.2f} per day<br><br>"

        # Add general advice
        analysis += f"<b>💡 TRADING TIPS:</b><br>"
        analysis += f"• Book 50% profits at Target 1<br>"
        analysis += f"• Trail stop loss after Target 1<br>"
        analysis += f"• Avoid holding overnight if high theta<br>"
        analysis += f"• Exit 30 minutes before market close<br>"

        return analysis
    except Exception as e:
        return f"Error in LTP analysis: {e}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=True)
