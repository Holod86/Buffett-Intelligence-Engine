import yfinance as yf
import pandas as pd
import requests
import numpy as np

# ============================================================
# MACRO MODULE "GLOBAL GUARD"
# ============================================================

def fetch_fear_greed_index():
    """Fetch CNN Fear & Greed Index via Alternative.me API (crypto proxy)."""
    try:
        res = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10).json()
        data = res.get("data", [{}])[0]
        value = int(data.get("value", 50))
        classification = data.get("value_classification", "Neutral")
        return value, classification
    except Exception:
        return 50, "Neutral"

def fetch_macro_data():
    """Fetch comprehensive macro data for Global Guard module."""
    macro = {}
    try:
        # 10-Year Treasury Rate
        tnx = yf.Ticker("^TNX")
        rate_10y = tnx.info.get("previousClose", 4.2)
        macro["10Y Treasury (%)"] = rate_10y

        # 2-Year Treasury Rate for yield curve inversion check
        twy = yf.Ticker("2YY=F")
        rate_2y = twy.info.get("previousClose", None)
        if rate_2y is None:
            # Fallback: use ^IRX (13-week) as short-term proxy
            irx = yf.Ticker("^IRX")
            rate_2y = irx.info.get("previousClose", 4.5)
        macro["2Y Treasury (%)"] = rate_2y

        # Yield Curve Inversion Check
        if rate_2y and rate_10y:
            spread = float(rate_10y) - float(rate_2y)
            macro["Yield Spread (10Y-2Y)"] = round(spread, 2)
            macro["Yield Curve"] = "⚠️ ИНВЕРСИЯ" if spread < 0 else "✅ Нормальная"
        
        # Fed Funds Rate proxy (use DFF or fallback)
        try:
            fed = yf.Ticker("^FVX")  # 5Y as proxy direction
            macro["Fed Rate Proxy (5Y %)"] = fed.info.get("previousClose", "N/A")
        except Exception:
            macro["Fed Rate Proxy (5Y %)"] = "N/A"

    except Exception:
        macro["10Y Treasury (%)"] = 4.2
        macro["2Y Treasury (%)"] = 4.5
        macro["Yield Spread (10Y-2Y)"] = -0.3
        macro["Yield Curve"] = "Unknown"
    
    # Fear & Greed Index
    fg_value, fg_class = fetch_fear_greed_index()
    macro["Fear & Greed"] = f"{fg_value} ({fg_class})"
    
    return macro, fg_value

def get_dynamic_margin_of_safety(macro_data):
    """Adjust Margin of Safety based on macro conditions."""
    base_mos = 30
    try:
        rate = float(macro_data.get("10Y Treasury (%)", 4.0))
        if rate > 5.0:
            return 45  # High rates → require bigger discount
        elif rate > 4.0:
            return 38
    except (ValueError, TypeError):
        pass
    return base_mos

def is_yield_curve_inverted(macro_data):
    """Check if yield curve is inverted."""
    try:
        spread = float(macro_data.get("Yield Spread (10Y-2Y)", 0))
        return spread < 0
    except (ValueError, TypeError):
        return False

# ============================================================
# STOCK EVALUATION (Buffett Criteria)
# ============================================================

DEFENSIVE_SECTORS = ["Consumer Defensive", "Healthcare", "Utilities"]

def evaluate_stock(ticker_str, required_mos=30, prefer_defensive=False):
    try:
        ticker = yf.Ticker(ticker_str)
        info = ticker.info
        
        price = info.get("currentPrice", info.get("previousClose", 0))
        if price == 0:
            return None
        
        # Fundamentals
        roe = info.get("returnOnEquity", 0)
        if roe is None: roe = 0
        roe_pct = roe * 100
        
        debt_eq = info.get("debtToEquity", 0) or 0
        sector = info.get("sector", "N/A")

        # If preferring defensive and this stock isn't defensive, skip
        if prefer_defensive and sector not in DEFENSIVE_SECTORS:
            return None
        
        # Multiples
        pe_ratio = info.get("trailingPE", None)
        pb_ratio = info.get("priceToBook", None)
        
        # FCF Yield
        fcf = info.get("freeCashflow", 0)
        market_cap = info.get("marketCap", 0)
        fcf_yield = None
        if fcf and market_cap and market_cap > 0:
            fcf_yield = round((fcf / market_cap) * 100, 2)

        # DCF Intrinsic Value
        eps = info.get("trailingEps", 0)
        growth_rate = 0.08
        discount_rate = 0.10
        terminal_rate = 0.02
        
        intrinsic_value = 0
        if eps and eps > 0:
            eps_proj = eps
            for year in range(1, 6):
                eps_proj *= (1 + growth_rate)
                intrinsic_value += eps_proj / ((1 + discount_rate) ** year)
            terminal_value = (eps_proj * (1 + terminal_rate)) / (discount_rate - terminal_rate)
            intrinsic_value += terminal_value / ((1 + discount_rate) ** 5)
        else:
            intrinsic_value = info.get("targetMeanPrice", price * 1.1)
        
        undervaluation = 0
        if intrinsic_value > price:
            undervaluation = ((intrinsic_value - price) / intrinsic_value) * 100
            
        # Signal with dynamic Margin of Safety
        signal_1d = "WAIT"
        margin_of_safety = undervaluation
        if roe_pct > 15 and debt_eq < 100 and margin_of_safety > required_mos:
            signal_1d = "BUY"
        elif margin_of_safety > 15:
            signal_1d = "WATCH"
            
        # Tech Analysis for shorter timeframes (1H, 4H)
        signal_1h = "N/A"
        signal_4h = "N/A"
        try:
            df_1h = ticker.history(period="5d", interval="1h")
            if len(df_1h) >= 20:
                sma20_1h = df_1h['Close'].rolling(window=20).mean().iloc[-1]
                signal_1h = "BUY" if df_1h['Close'].iloc[-1] > sma20_1h else "SELL"
                
            df_4h_raw = ticker.history(period="20d", interval="1h")
            if not df_4h_raw.empty:
                df_4h = df_4h_raw.resample('4h').agg({'Close': 'last'}).dropna()
                if len(df_4h) >= 20:
                    sma20_4h = df_4h['Close'].rolling(window=20).mean().iloc[-1]
                    signal_4h = "BUY" if df_4h['Close'].iloc[-1] > sma20_4h else "SELL"
        except Exception as e_ta:
            print(f"Failed TA for {ticker_str}: {e_ta}")

        # 52-week extremes
        low_52 = info.get("fiftyTwoWeekLow", 0)
        high_52 = info.get("fiftyTwoWeekHigh", 0)
        is_52w_low = price <= (low_52 * 1.05) if low_52 else False
        is_52w_high = price >= (high_52 * 0.95) if high_52 else False
        
        # Support/Resistance on 1D for Entry/Exit
        rec_buy = "N/A"
        rec_sell = "N/A"
        try:
            df_1d = ticker.history(period="6mo", interval="1d")
            if not df_1d.empty and len(df_1d) > 20:
                recent_1d = df_1d.tail(20)
                target_buy = recent_1d['Low'].min()
                target_sell = recent_1d['High'].max()
                rec_buy = f"${target_buy:.2f}"
                rec_sell = f"${target_sell:.2f}"
        except Exception:
            pass
            
        return {
            "Asset": ticker_str,
            "Type": "Stock",
            "Sector": sector,
            "Price": round(price, 2),
            "P/E": round(pe_ratio, 1) if pe_ratio else None,
            "P/B": round(pb_ratio, 2) if pb_ratio else None,
            "ROE %": round(roe_pct, 1),
            "FCF Yield %": fcf_yield,
            "Undervaluation %": round(undervaluation, 1),
            "Signal 1H": signal_1h,
            "Signal 4H": signal_4h,
            "Signal 1D": signal_1d,
            "Entry (Support)": rec_buy,
            "Exit (Resistance)": rec_sell,
            "Intrinsic Value": round(intrinsic_value, 2),
            "52W Low": is_52w_low,
            "52W High": is_52w_high,
        }
    except Exception as e:
        print(f"Error evaluating {ticker_str}: {e}")
        return None

# ============================================================
# CRYPTO EVALUATION ("Digital Buffett" Filter)
# ============================================================

def fetch_crypto_data():
    results = []
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": "bitcoin,ethereum,solana,cardano,polkadot,avalanche-2,chainlink,polygon-ecosystem-token,uniswap,aave",
            "order": "market_cap_desc",
            "per_page": 20,
            "page": 1,
            "sparkline": False
        }
        res = requests.get(url, params=params, timeout=15).json()
        
        for coin in res:
            price = coin.get("current_price", 0)
            ath = coin.get("ath", price * 2)
            market_cap = coin.get("market_cap", 0)
            fdv = coin.get("fully_diluted_valuation", market_cap)

            # Undervaluation by ATH distance
            undervaluation = 0
            if price < ath:
                undervaluation = ((ath - price) / ath) * 100
            
            # FDV / Market Cap ratio (dilution risk)
            fdv_mcap_ratio = None
            if fdv and market_cap and market_cap > 0:
                fdv_mcap_ratio = round(fdv / market_cap, 2)
                
            signal_1d = "WAIT"
            if undervaluation > 50:
                signal_1d = "BUY"
            elif undervaluation > 30:
                signal_1d = "WATCH"
                
            signal_1h = "BUY" if undervaluation > 40 else "SELL"
            signal_4h = "BUY" if undervaluation > 45 else "SELL"
            
            # Support/Resistance
            rec_buy = "N/A"
            rec_sell = "N/A"
            try:
                internal_ticker = f"{coin.get('symbol', '').upper()}-USD"
                t_cryp = yf.Ticker(internal_ticker)
                df_1d = t_cryp.history(period="6mo", interval="1d")
                if not df_1d.empty and len(df_1d) > 20:
                    recent_1d = df_1d.tail(20)
                    target_buy = recent_1d['Low'].min()
                    target_sell = recent_1d['High'].max()
                    rec_buy = f"${target_buy:.2f}"
                    rec_sell = f"${target_sell:.2f}"
            except Exception:
                pass
                
            results.append({
                "Asset": coin.get("symbol", "").upper(),
                "Type": "Crypto",
                "Sector": "Crypto",
                "Price": round(price, 2),
                "P/E": None,
                "P/B": None,
                "ROE %": None,
                "FCF Yield %": None,
                "FDV/MCap": fdv_mcap_ratio,
                "Undervaluation %": round(undervaluation, 1),
                "Signal 1H": signal_1h,
                "Signal 4H": signal_4h,
                "Signal 1D": signal_1d,
                "Entry (Support)": rec_buy,
                "Exit (Resistance)": rec_sell,
                "Intrinsic Value": None,
                "52W Low": False,
                "52W High": False,
            })
    except Exception as e:
        print(f"Error fetching crypto: {e}")
    return results

# ============================================================
# MARKET SCANNER
# ============================================================

def get_market_scan():
    """Run full market scan with macro-adjusted parameters."""
    # Fetch macro first
    macro_data, fg_value = fetch_macro_data()
    
    # Dynamic Margin of Safety based on rates
    required_mos = get_dynamic_margin_of_safety(macro_data)
    
    # Check if we should prefer defensive sectors
    prefer_defensive = is_yield_curve_inverted(macro_data)
    
    # Watchlist
    watch_stocks = [
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "BRK-B", "JNJ", "JPM", "V", 
        "PG", "UNH", "HD", "MA", "CVX", "MRK", "ABBV", "PEP", "KO", "AVGO", 
        "TSLA", "WMT", "LLY", "MCD", "CSCO", "CRM", "PFE", "TMO", "NKE", "NFLX"
    ]
    
    # When yield curve is inverted, also add defensive stalwarts
    if prefer_defensive:
        defensive_extra = ["CL", "GIS", "K", "SJM", "ABT", "MDT", "NEE", "DUK", "SO", "XEL"]
        watch_stocks = list(set(watch_stocks + defensive_extra))
    
    data = []
    for t in watch_stocks:
        stock_data = evaluate_stock(t, required_mos=required_mos, prefer_defensive=False)
        if stock_data:
            data.append(stock_data)
            
    crypto_data = fetch_crypto_data()
    data.extend(crypto_data)
    
    df = pd.DataFrame(data)
    
    # Ensure FDV/MCap column exists for all rows
    if "FDV/MCap" not in df.columns:
        df["FDV/MCap"] = None
    
    return df, macro_data, fg_value, required_mos
