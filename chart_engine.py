import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import mplfinance as mpf
import numpy as np

# ============================================================
# PATTERN RECOGNITION
# ============================================================

def identify_patterns(df):
    """Detect chart patterns and return list of unique names + 2 Pandas Series (bullish/bearish markers)."""
    patterns = set()
    
    # Create empty Series mapped to df index with NaNs
    bull_markers = pd.Series(np.nan, index=df.index)
    bear_markers = pd.Series(np.nan, index=df.index)
    
    if len(df) < 10:
        return list(patterns), bull_markers, bear_markers
        
    for i in range(1, len(df)):
        last = df.iloc[i]
        prev = df.iloc[i-1]
        
        # Bullish Engulfing
        if prev['Close'] < prev['Open'] and last['Close'] > last['Open']:
            if last['Open'] <= prev['Close'] and last['Close'] >= prev['Open']:
                patterns.add("Bullish Engulfing 🟢")
                bull_markers.iloc[i] = last['Low'] * 0.99
                
        # Bearish Engulfing
        if prev['Close'] > prev['Open'] and last['Close'] < last['Open']:
            if last['Open'] >= prev['Close'] and last['Close'] <= prev['Open']:
                patterns.add("Bearish Engulfing 🔴")
                bear_markers.iloc[i] = last['High'] * 1.01
                
        # Hammer
        body = abs(last['Close'] - last['Open'])
        lower_shadow = min(last['Close'], last['Open']) - last['Low']
        upper_shadow = last['High'] - max(last['Close'], last['Open'])
        if body > 0 and lower_shadow > 2 * body and upper_shadow < body * 0.5:
            patterns.add("Hammer 🔨")
            bull_markers.iloc[i] = last['Low'] * 0.99

    # Double Bottom (basic) over recent rolling 20
    if len(df) > 20:
        recent_lows = df['Low'].rolling(window=20).min()
        for i in range(20, len(df)):
            current_low = df['Low'].iloc[i]
            hist_low = recent_lows.iloc[i-2] if not pd.isna(recent_lows.iloc[i-2]) else 0
            if hist_low > 0 and abs(current_low - hist_low) / hist_low < 0.02:
                if (i+1 < len(df) and df['Low'].iloc[i] <= df['Low'].iloc[i-1] and df['Low'].iloc[i] <= df['Low'].iloc[i+1]) or i == len(df)-1:
                    patterns.add("Double Bottom 🟢")
                    bull_markers.iloc[i] = df['Low'].iloc[i] * 0.99

    # Head and Shoulders
    if len(df) >= 30:
        segment = df.tail(30)
        highs = segment['High'].values
        third = len(highs) // 3
        left_peak = np.max(highs[:third])
        head_peak = np.max(highs[third:2*third])
        right_peak = np.max(highs[2*third:])
        if head_peak > left_peak and head_peak > right_peak:
            if abs(left_peak - right_peak) / head_peak < 0.05:
                patterns.add("Head & Shoulders ⚠️")
                head_idx = segment['High'].iloc[third:2*third].idxmax()
                bear_markers.loc[head_idx] = df.loc[head_idx, 'High'] * 1.01

    return list(patterns), bull_markers, bear_markers

# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def calculate_support_resistance(df):
    recent = df.tail(20)
    support = recent['Low'].min()
    resistance = recent['High'].max()
    return support, resistance

# ============================================================
# RSI CALCULATION
# ============================================================

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# ============================================================
# MACD CALCULATION
# ============================================================

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

# ============================================================
# MAIN CHART GENERATOR
# ============================================================

def get_internal_ticker(ticker_symbol):
    internal_ticker = ticker_symbol
    crypto_map = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD", 
                  "ADA": "ADA-USD", "DOT": "DOT-USD", "AVAX": "AVAX-USD",
                  "LINK": "LINK-USD", "POL": "POL-USD", "UNI": "UNI-USD", "AAVE": "AAVE-USD"}
    commodity_map = {"Gold": "GC=F", "Silver": "SI=F", "Crude Oil": "CL=F", "Natural Gas": "NG=F", 
                     "Copper": "HG=F", "Wheat": "ZW=F", "Corn": "ZC=F", "Soybeans": "ZS=F", 
                     "Coffee": "KC=F", "Sugar": "SB=F", "Cotton": "CT=F", "Cocoa": "CC=F", 
                     "Platinum": "PL=F", "Palladium": "PA=F", "Heating Oil": "HO=F"}
    if ticker_symbol in crypto_map:
        internal_ticker = crypto_map[ticker_symbol]
    elif ticker_symbol in commodity_map:
        internal_ticker = commodity_map[ticker_symbol]
    return internal_ticker

def generate_chart(ticker_symbol, timeframe="1d", zoom_bars=100):
    try:
        internal_ticker = get_internal_ticker(ticker_symbol)
        ticker = yf.Ticker(internal_ticker)
        
        # Fetch larger dataset for full indicator calculation before slicing
        if timeframe == "15m":
            df = ticker.history(period="60d", interval="15m")
            title_suffix = "15M"
        elif timeframe == "1h":
            df = ticker.history(period="3mo", interval="1h")
            title_suffix = "1H"
        elif timeframe == "4h":
            df = ticker.history(period="6mo", interval="1h")
            if not df.empty:
                df = df.resample('4h').agg({
                    'Open': 'first', 'High': 'max', 'Low': 'min', 
                    'Close': 'last', 'Volume': 'sum'
                })
                df.dropna(inplace=True)
            title_suffix = "4H"
        else:  # 1d
            df = ticker.history(period="2y", interval="1d")
            title_suffix = "1D"
        
        if df.empty:
            return None, []
            
        # === EMA 50 / 200 ===
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # === RSI ===
        df['RSI'] = calculate_rsi(df['Close'])
        
        # === MACD ===
        df['MACD'], df['MACD_Signal'], df['MACD_Hist'] = calculate_macd(df['Close'])
        
        # === BUY/SELL Signals (EMA50 crossover with EMA200 trend filter) ===
        buy_signals = []
        sell_signals = []
        for i in range(len(df)):
            cross_up = (i > 0 and pd.notna(df['EMA50'].iloc[i]) and 
                       df['Close'].iloc[i] > df['EMA50'].iloc[i] and 
                       df['Close'].iloc[i-1] <= df['EMA50'].iloc[i-1])
            cross_down = (i > 0 and pd.notna(df['EMA50'].iloc[i]) and 
                         df['Close'].iloc[i] < df['EMA50'].iloc[i] and 
                         df['Close'].iloc[i-1] >= df['EMA50'].iloc[i-1])
            
            uptrend = pd.notna(df['EMA200'].iloc[i]) and df['Close'].iloc[i] > df['EMA200'].iloc[i]
            downtrend = pd.notna(df['EMA200'].iloc[i]) and df['Close'].iloc[i] < df['EMA200'].iloc[i]

            if cross_up and uptrend:
                buy_signals.append(df['Low'].iloc[i] * 0.97)
                sell_signals.append(np.nan)
            elif cross_down and downtrend:
                buy_signals.append(np.nan)
                sell_signals.append(df['High'].iloc[i] * 1.03)
            else:
                buy_signals.append(np.nan)
                sell_signals.append(np.nan)
                
        df['Buy_Signal'] = buy_signals
        df['Sell_Signal'] = sell_signals
        
        # === Zoom Slice ===
        df = df.tail(int(zoom_bars))
        
        if len(df) < 5:
            return None, []
            
        patterns, bull_markers, bear_markers = identify_patterns(df)
        support, resistance = calculate_support_resistance(df)

        # ============================================================
        # BUILD MULTI-PANEL CHART (Candles + RSI + MACD)
        # ============================================================
        
        fig = plt.figure(figsize=(14, 10), facecolor='#121212')
        gs = gridspec.GridSpec(4, 1, height_ratios=[3, 0.8, 1, 1], hspace=0.05)
        
        # --- Panel 1: Candlestick + EMAs + Signals ---
        ax_candle = fig.add_subplot(gs[0])
        ax_volume = fig.add_subplot(gs[1], sharex=ax_candle)
        ax_rsi = fig.add_subplot(gs[2], sharex=ax_candle)
        ax_macd = fig.add_subplot(gs[3], sharex=ax_candle)
        
        for ax in [ax_candle, ax_volume, ax_rsi, ax_macd]:
            ax.set_facecolor('#1E1E1E')
            ax.tick_params(colors='white')
            ax.yaxis.label.set_color('white')
            ax.spines['top'].set_color('#333')
            ax.spines['bottom'].set_color('#333')
            ax.spines['left'].set_color('#333')
            ax.spines['right'].set_color('#333')
            ax.grid(True, alpha=0.2, linestyle='--')
        
        # Candlesticks via mplfinance on the axis
        mc = mpf.make_marketcolors(up='#26a69a', down='#ef5350', edge='inherit', 
                                    wick='inherit', volume='in', ohlc='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, facecolor='#1E1E1E', edgecolor='#333',
                               figcolor='#121212', gridstyle='--', gridcolor='#333',
                               rc={'text.color': '#FFFFFF', 'axes.labelcolor': '#FFFFFF',
                                   'xtick.color':'#FFFFFF', 'ytick.color':'#FFFFFF'})
        
        apds = []
        if not df['EMA50'].isnull().all():
            apds.append(mpf.make_addplot(df['EMA50'], ax=ax_candle, color='#00bcd4', width=1.5))
        if not df['EMA200'].isnull().all():
            apds.append(mpf.make_addplot(df['EMA200'], ax=ax_candle, color='#ff9800', width=1.5))
        if df['Buy_Signal'].notna().any():
            apds.append(mpf.make_addplot(df['Buy_Signal'], ax=ax_candle, type='scatter', 
                                          markersize=120, marker='^', color='#4caf50'))
        if df['Sell_Signal'].notna().any():
            apds.append(mpf.make_addplot(df['Sell_Signal'], ax=ax_candle, type='scatter', 
                                          markersize=120, marker='v', color='#f44336'))
        
        # New Markers for Patterns
        if bull_markers.notna().any():
            apds.append(mpf.make_addplot(bull_markers, ax=ax_candle, type='scatter', 
                                          markersize=60, marker='^', color='#00e676'))
        if bear_markers.notna().any():
            apds.append(mpf.make_addplot(bear_markers, ax=ax_candle, type='scatter', 
                                          markersize=60, marker='v', color='#ff1744'))
        
        current_price = df['Close'].iloc[-1]

        mpf.plot(df, type='candle', style=s, ax=ax_candle, volume=ax_volume,
                 hlines=dict(hlines=[support, resistance, current_price], 
                            colors=['#4caf50','#f44336', '#ffffff'], 
                            linestyle='-.', linewidths=[0.8, 0.8, 1.2]),
                 addplot=apds if apds else None, warn_too_much_data=2000)
        
        ax_candle.set_title(f"{ticker_symbol} — {title_suffix}  |  EMA50 (cyan) · EMA200 (orange)", 
                           color='white', fontsize=13, fontweight='bold', pad=10)
        ax_candle.legend(['EMA50', 'EMA200'], loc='upper left', fontsize=8, 
                        facecolor='#1E1E1E', edgecolor='#555', labelcolor='white')
        
        # --- Panel 3: RSI ---
        rsi_data = df['RSI'].values
        x_range = range(len(rsi_data))
        ax_rsi.plot(x_range, rsi_data, color='#ab47bc', linewidth=1.2)
        ax_rsi.axhline(70, color='#f44336', linestyle='--', alpha=0.6, linewidth=0.8)
        ax_rsi.axhline(30, color='#4caf50', linestyle='--', alpha=0.6, linewidth=0.8)
        ax_rsi.fill_between(x_range, 30, 70, alpha=0.05, color='white')
        ax_rsi.set_ylabel('RSI', fontsize=9, color='white')
        ax_rsi.set_ylim(0, 100)
        ax_rsi.set_title('RSI (14)', color='white', fontsize=9, loc='left')
        
        # --- Panel 4: MACD ---
        macd_data = df['MACD'].values
        signal_data = df['MACD_Signal'].values
        hist_data = df['MACD_Hist'].values
        
        ax_macd.plot(x_range, macd_data, color='#29b6f6', linewidth=1.0, label='MACD')
        ax_macd.plot(x_range, signal_data, color='#ff7043', linewidth=1.0, label='Signal')
        colors_hist = ['#4caf50' if v >= 0 else '#f44336' for v in hist_data]
        ax_macd.bar(x_range, hist_data, color=colors_hist, alpha=0.5, width=0.8)
        ax_macd.axhline(0, color='white', linewidth=0.5, alpha=0.3)
        ax_macd.set_ylabel('MACD', fontsize=9, color='white')
        ax_macd.set_title('MACD (12, 26, 9)', color='white', fontsize=9, loc='left')
        ax_macd.legend(loc='upper left', fontsize=7, facecolor='#1E1E1E', 
                      edgecolor='#555', labelcolor='white')

        # Hide x-axis labels for upper panels
        ax_candle.tick_params(labelbottom=False)
        ax_volume.tick_params(labelbottom=False)
        ax_rsi.tick_params(labelbottom=False)
        
        plt.tight_layout()
        
        return fig, patterns
    except Exception as e:
        print(f"Generate chart error: {e}")
        import traceback
        traceback.print_exc()
        return None, []
