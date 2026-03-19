"""
Portfolio Engine — Demo Trading Module
Manages a virtual portfolio with buy/sell operations, trade journal,
Sharpe Ratio and Max Drawdown calculations.
"""
import pandas as pd
import numpy as np
from datetime import datetime

def init_portfolio(session_state):
    """Initialize portfolio in session state if not present."""
    if "portfolio" not in session_state:
        session_state.portfolio = {
            "cash": 100000.0,  # Starting virtual capital $100k
            "holdings": {},     # {ticker: {"qty": N, "avg_price": X}}
            "trade_log": [],    # List of trade dicts
            "equity_history": [{"date": datetime.now().isoformat(), "equity": 100000.0}]
        }

def get_portfolio(session_state):
    init_portfolio(session_state)
    return session_state.portfolio

def execute_buy(session_state, ticker, price, qty):
    """Execute a virtual buy order (Long or Cover Short)."""
    portfolio = get_portfolio(session_state)
    cost = price * qty
    
    if cost > portfolio["cash"]:
        return False, "Недостаточно средств"
    
    portfolio["cash"] -= cost
    
    if ticker in portfolio["holdings"]:
        existing = portfolio["holdings"][ticker]
        current_qty = existing["qty"]
        if current_qty < 0:
            # Covering a short position
            cover_qty = min(abs(current_qty), qty)
            remaining_buy_qty = qty - cover_qty
            
            pnl_realized = (existing["avg_price"] - price) * cover_qty
            new_qty = current_qty + qty
            
            if new_qty == 0:
                del portfolio["holdings"][ticker]
            elif new_qty < 0:
                portfolio["holdings"][ticker]["qty"] = new_qty
            else:
                # Flipped from short to long
                portfolio["holdings"][ticker] = {"qty": new_qty, "avg_price": price}
                
            portfolio["trade_log"].append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "action": "BUY (Cover)" if new_qty <= 0 else "BUY (Cover+Long)",
                "ticker": ticker,
                "price": price,
                "qty": qty,
                "total": round(cost, 2),
                "pnl": round(pnl_realized, 2)
            })
        else:
            # Adding to existing long
            total_qty = current_qty + qty
            avg_price = ((existing["avg_price"] * current_qty) + (price * qty)) / total_qty
            portfolio["holdings"][ticker] = {"qty": total_qty, "avg_price": round(avg_price, 4)}
            portfolio["trade_log"].append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "action": "BUY",
                "ticker": ticker,
                "price": price,
                "qty": qty,
                "total": round(cost, 2)
            })
    else:
        # New long position
        portfolio["holdings"][ticker] = {"qty": qty, "avg_price": price}
        portfolio["trade_log"].append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "action": "BUY",
            "ticker": ticker,
            "price": price,
            "qty": qty,
            "total": round(cost, 2)
        })
    
    _update_equity(portfolio, {})
    return True, f"Куплено {qty} x {ticker} по ${price}"

def execute_sell(session_state, ticker, price, qty):
    """Execute a virtual sell order (Sell Long or Short)."""
    portfolio = get_portfolio(session_state)
    revenue = price * qty
    portfolio["cash"] += revenue
    
    if ticker in portfolio["holdings"]:
        existing = portfolio["holdings"][ticker]
        current_qty = existing["qty"]
        
        if current_qty > 0:
            # Selling a long position
            sell_qty = min(current_qty, qty)
            remaining_short_qty = qty - sell_qty
            
            pnl_realized = (price - existing["avg_price"]) * sell_qty
            new_qty = current_qty - qty
            
            if new_qty == 0:
                del portfolio["holdings"][ticker]
            elif new_qty > 0:
                portfolio["holdings"][ticker]["qty"] = new_qty
            else:
                # Flipped from long to short
                portfolio["holdings"][ticker] = {"qty": new_qty, "avg_price": price}
                
            portfolio["trade_log"].append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "action": "SELL" if new_qty >= 0 else "SELL (Short)",
                "ticker": ticker,
                "price": price,
                "qty": qty,
                "total": round(revenue, 2),
                "pnl": round(pnl_realized, 2)
            })
        else:
            # Adding to existing short
            total_qty = current_qty - qty
            # average short price = weighted average of short entry prices
            avg_price = ((existing["avg_price"] * abs(current_qty)) + (price * qty)) / abs(total_qty)
            portfolio["holdings"][ticker] = {"qty": total_qty, "avg_price": round(avg_price, 4)}
            
            portfolio["trade_log"].append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "action": "SHORT",
                "ticker": ticker,
                "price": price,
                "qty": qty,
                "total": round(revenue, 2)
            })
    else:
        # New short position
        portfolio["holdings"][ticker] = {"qty": -qty, "avg_price": price}
        portfolio["trade_log"].append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "action": "SHORT",
            "ticker": ticker,
            "price": price,
            "qty": qty,
            "total": round(revenue, 2)
        })
    
    _update_equity(portfolio, {})
    return True, f"Продано {qty} x {ticker} по ${price}"

def _update_equity(portfolio, current_prices):
    """Update equity history with current portfolio value."""
    holdings_value = 0
    for ticker, data in portfolio["holdings"].items():
        price = current_prices.get(ticker, data["avg_price"])
        holdings_value += price * data["qty"]
    
    total_equity = portfolio["cash"] + holdings_value
    portfolio["equity_history"].append({
        "date": datetime.now().isoformat(),
        "equity": round(total_equity, 2)
    })

def calculate_portfolio_metrics(portfolio):
    """Calculate Sharpe Ratio and Max Drawdown."""
    equity_history = portfolio.get("equity_history", [])
    
    if len(equity_history) < 2:
        return {"sharpe_ratio": 0, "max_drawdown": 0, "total_return": 0}
    
    equities = [e["equity"] for e in equity_history]
    
    # Total Return
    initial = equities[0]
    current = equities[-1]
    total_return = ((current - initial) / initial) * 100
    
    # Returns
    returns = []
    for i in range(1, len(equities)):
        if equities[i-1] > 0:
            returns.append((equities[i] - equities[i-1]) / equities[i-1])
    
    # Sharpe Ratio (annualized, risk-free rate ~4%)
    sharpe_ratio = 0
    if returns and len(returns) > 1:
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        if std_return > 0:
            sharpe_ratio = (mean_return - 0.04/252) / std_return * np.sqrt(252)
    
    # Max Drawdown
    max_drawdown = 0
    peak = equities[0]
    for eq in equities:
        if eq > peak:
            peak = eq
        drawdown = (peak - eq) / peak * 100 if peak > 0 else 0
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    return {
        "sharpe_ratio": round(sharpe_ratio, 2),
        "max_drawdown": round(max_drawdown, 2),
        "total_return": round(total_return, 2)
    }

def get_trade_log_df(portfolio):
    """Return trade log as a DataFrame."""
    log = portfolio.get("trade_log", [])
    if not log:
        return pd.DataFrame(columns=["Дата", "Действие", "Тикер", "Цена", "Кол-во", "Сумма", "P&L"])
    
    df = pd.DataFrame(log)
    df.columns = ["Дата", "Действие", "Тикер", "Цена", "Кол-во", "Сумма"] + (["P&L"] if "pnl" in log[0] else [])
    return df

def get_holdings_df(portfolio, current_prices=None):
    """Return current holdings as a DataFrame."""
    if not portfolio["holdings"]:
        return pd.DataFrame(columns=["Тикер", "Кол-во", "Ср. цена", "Текущая", "P&L", "P&L %"])
    
    rows = []
    for ticker, data in portfolio["holdings"].items():
        current = current_prices.get(ticker, data["avg_price"]) if current_prices else data["avg_price"]
        
        qty = data["qty"]
        if qty > 0:
            pnl = (current - data["avg_price"]) * qty
            pnl_pct = ((current - data["avg_price"]) / data["avg_price"]) * 100 if data["avg_price"] > 0 else 0
        else:
            # For short positions, lower price = profit
            pnl = (data["avg_price"] - current) * abs(qty)
            pnl_pct = ((data["avg_price"] - current) / data["avg_price"]) * 100 if data["avg_price"] > 0 else 0
            
        rows.append({
            "Тикер": ticker,
            "Кол-во": qty,
            "Ср. цена": f"${data['avg_price']:.2f}",
            "Текущая": f"${current:.2f}",
            "P&L": f"${pnl:+.2f}",
            "P&L %": f"{pnl_pct:+.1f}%"
        })
    
    return pd.DataFrame(rows)
