"""
Alerts Engine — Smart Alert System
Detects trigger conditions and formats alerts for UI and Telegram.
"""
import requests

# ============================================================
# ALERT TRIGGERS
# ============================================================

def check_alerts(df_scan, macro_data, fg_value):
    """
    Check all assets against smart alert triggers.
    Returns a list of alert dicts.
    """
    alerts = []
    
    for _, row in df_scan.iterrows():
        asset = row.get("Asset", "")
        underval = row.get("Undervaluation %", 0)
        signal_1d = row.get("Signal 1D", "")
        is_52w_low = row.get("52W Low", False)
        roe = row.get("ROE %", 0)
        
        master_signal = row.get("Общий Сигнал", "")
        master_details = row.get("Детали Сигнала", "")
        
        # === Trigger 1: "Master Signal BUY" ===
        if "BUY" in master_signal:
            priority = "HIGH" if "STRONG" in master_signal else "MEDIUM"
            title = "⭐ STRONG ОБЩИЙ СИГНАЛ" if "STRONG" in master_signal else "💡 ПОДТВЕРЖДЕННЫЙ СИГНАЛ"
            alerts.append({
                "type": title,
                "ticker": asset,
                "message": f"{master_signal}: {master_details}. Недооценка: {underval:.1f}%",
                "risk": _assess_risk(underval, fg_value),
                "priority": priority
            })
            continue # If it's a confirmed master signal, no need to spam other alerts for this asset
        
        # === Trigger 2: "Master Signal SELL" ===
        if "SELL" in master_signal:
            priority = "HIGH" if "STRONG" in master_signal else "MEDIUM"
            title = "🚨 STRONG SELL СИГНАЛ" if "STRONG" in master_signal else "⚠️ SELL СИГНАЛ"
            alerts.append({
                "type": title,
                "ticker": asset,
                "message": f"{master_signal}: {master_details}.",
                "risk": "HIGH",
                "priority": priority
            })
            continue
            
        # === Trigger 3: "Идеальное совпадение по мультипликаторам (только если нет Master Signal)" ===
        # Deep discount without full technical alignment
        if underval > 40 and signal_1d == "BUY":
            alerts.append({
                "type": "🎯 ГЛУБОКАЯ НЕДООЦЕНКА",
                "ticker": asset,
                "message": f"Недооценён на {underval:.1f}% + Сигнал BUY на 1D (Ожидание тех. подтверждения)",
                "risk": _assess_risk(underval, fg_value),
                "priority": "LOW"
            })
    
    # === Market-wide alert: Extreme Greed ===
    if fg_value > 80:
        alerts.insert(0, {
            "type": "🔥 ПЕРЕГРЕВ РЫНКА",
            "ticker": "РЫНОК",
            "message": f"Fear & Greed = {fg_value}. Рынок перегрет! Новые покупки не рекомендуются. Фиксируйте прибыль.",
            "risk": "HIGH",
            "priority": "HIGH"
        })
    
    # Deduplicate by ticker+type
    seen = set()
    unique_alerts = []
    for alert in alerts:
        key = f"{alert['ticker']}_{alert['type']}"
        if key not in seen:
            seen.add(key)
            unique_alerts.append(alert)
    
    return unique_alerts

def _assess_risk(underval, fg_value):
    """Simple risk assessment based on undervaluation and market sentiment."""
    if fg_value > 70:
        return "HIGH"
    elif fg_value < 30 and underval > 30:
        return "LOW"
    else:
        return "MEDIUM"

# ============================================================
# TELEGRAM INTEGRATION
# ============================================================

def send_telegram_alert(bot_token, chat_id, alert):
    """Send a single alert to Telegram."""
    if not bot_token or not chat_id:
        return False, "Bot token или Chat ID не указаны"
    
    text = (
        f"{'='*30}\n"
        f"{alert['type']}\n"
        f"{'='*30}\n"
        f"📌 Тикер: {alert['ticker']}\n"
        f"📊 {alert['message']}\n"
        f"⚠️ Риск: {alert['risk']}\n"
        f"{'='*30}"
    )
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True, "Отправлено"
        else:
            return False, f"Ошибка Telegram API: {resp.status_code}"
    except Exception as e:
        return False, str(e)

def send_all_alerts_telegram(bot_token, chat_id, alerts):
    """Send all alerts to Telegram."""
    results = []
    for alert in alerts:
        success, msg = send_telegram_alert(bot_token, chat_id, alert)
        results.append({"alert": alert["ticker"], "success": success, "message": msg})
    return results
