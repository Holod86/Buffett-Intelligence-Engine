import pandas as pd
import numpy as np

def get_cross_time(df, fast_col, slow_col):
    """Find the timestamp of the last crossover where fast crossed slow."""
    if df.empty or len(df) < 2:
        return None, None
    
    # +1 if fast > slow, -1 if fast < slow
    signals = np.where(df[fast_col] > df[slow_col], 1, -1)
    diffs = np.diff(signals)
    crossovers = np.where(diffs != 0)[0]
    
    if len(crossovers) == 0:
        # It never crossed in the available history, meaning it's been in this state since the beginning.
        # We return the first timestamp as the "cross time" (happened very long ago).
        current_state = "BUY" if signals[-1] == 1 else "SELL"
        return df.index[0], current_state
    
    last_cross_idx = crossovers[-1] + 1
    current_state = "BUY" if signals[-1] == 1 else "SELL"
    return df.index[last_cross_idx], current_state

def detect_patterns(df):
    """Detect technical patterns on the last closed candle."""
    if len(df) < 3:
        return False, False, False, False # Bullish, Bearish, RSI_Buy, RSI_Sell
        
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 1. Engulfing
    bullish_engulfing = (prev['Close'] < prev['Open']) and (last['Close'] > last['Open']) and \
                        (last['Close'] > prev['Open']) and (last['Open'] < prev['Close'])
                        
    bearish_engulfing = (prev['Close'] > prev['Open']) and (last['Close'] < last['Open']) and \
                        (last['Close'] < prev['Open']) and (last['Open'] > prev['Close'])
                        
    # 2. Pin Bar / Hammer (lower tail is at least 2x body, upper tail is very small)
    body = abs(last['Close'] - last['Open'])
    lower_tail = min(last['Close'], last['Open']) - last['Low']
    upper_tail = last['High'] - max(last['Close'], last['Open'])
    
    bullish_hammer = (lower_tail >= 2 * body) and (upper_tail <= 0.5 * body) and body > 0
    bearish_pinbar = (upper_tail >= 2 * body) and (lower_tail <= 0.5 * body) and body > 0
    
    bullish_pattern = bullish_engulfing or bullish_hammer
    bearish_pattern = bearish_engulfing or bearish_pinbar
    
    # 3. Indicators (RSI 14)
    df['delta'] = df['Close'].diff()
    df['gain'] = df['delta'].clip(lower=0)
    df['loss'] = -1 * df['delta'].clip(upper=0)
    avg_gain = df['gain'].rolling(window=14, min_periods=1).mean()
    avg_loss = df['loss'].rolling(window=14, min_periods=1).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    rsi_val = df['RSI'].iloc[-1]
    
    # MACD standard
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    
    macd_bullish = (macd.iloc[-1] > macd_signal.iloc[-1]) and (macd.iloc[-2] <= macd_signal.iloc[-2])
    macd_bearish = (macd.iloc[-1] < macd_signal.iloc[-1]) and (macd.iloc[-2] >= macd_signal.iloc[-2])
    
    rsi_buy_signal = rsi_val < 35 or macd_bullish
    rsi_sell_signal = rsi_val > 65 or macd_bearish
    
    return bullish_pattern, bearish_pattern, rsi_buy_signal, rsi_sell_signal

def evaluate_master_signal(ticker_obj):
    """
    Evaluates chronology: D1 -> H4 -> H1.
    If all match and chronologically ordered and pattern confirms -> STRONG signal.
    """
    try:
        # Request history
        df_1h = ticker_obj.history(period="60d", interval="1h")
        if df_1h.empty:
            return "WAIT", "No Data"
            
        # Drop the live (unfinished) candle to avoid repainting
        df_1h = df_1h.iloc[:-1].copy()
        
        if len(df_1h) < 100:
            return "WAIT", "Insufficient Data"
            
        # Ensure timezone consistency before resampling
        if df_1h.index.tz is not None:
            df_1h.index = df_1h.index.tz_convert('UTC')
        else:
            df_1h.index = df_1h.index.tz_localize('UTC')

        # Resample to 4H
        df_4h = df_1h.resample('4h').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}
        ).dropna()
        
        # Resample to 1D
        df_1d = df_1h.resample('1d').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}
        ).dropna()
        
        df_1h['SMA20'] = df_1h['Close'].rolling(20).mean()
        df_4h['SMA20'] = df_4h['Close'].rolling(20).mean()
        df_1d['SMA20'] = df_1d['Close'].rolling(20).mean()
        
        t_1d, state_1d = get_cross_time(df_1d.dropna(), 'Close', 'SMA20')
        t_4h, state_4h = get_cross_time(df_4h.dropna(), 'Close', 'SMA20')
        t_1h, state_1h = get_cross_time(df_1h.dropna(), 'Close', 'SMA20')
        
        if t_1d is None or t_4h is None or t_1h is None:
            return "WAIT", "No crossover data"
            
        bull_pat, bear_pat, ind_buy, ind_sell = detect_patterns(df_1h)
        
        master_signal = "WAIT"
        details = ""
        
        # Chronology condition: D1 reversed before or same time as H4, which reversed before or same time as H1
        chronology_ok = (t_1d <= t_4h) and (t_4h <= t_1h)
        
        if state_1d == "BUY" and state_4h == "BUY" and state_1h == "BUY":
            if chronology_ok and bull_pat:
                master_signal = "STRONG BUY" if ind_buy else "BUY"
                details = "Chronology BUY + Pattern" + (" + MACD/RSI" if ind_buy else "")
        elif state_1d == "SELL" and state_4h == "SELL" and state_1h == "SELL":
            if chronology_ok and bear_pat:
                master_signal = "STRONG SELL" if ind_sell else "SELL"
                details = "Chronology SELL + Pattern" + (" + MACD/RSI" if ind_sell else "")
                
        return master_signal, details
    except Exception as e:
        print("TA Engine Error:", e)
        return "WAIT", f"Error: {e}"
