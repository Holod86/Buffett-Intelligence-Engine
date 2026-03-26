import time
import json
import os
import traceback
import sys
from datetime import datetime, timedelta

# Fix for Windows console encoding
sys.stdout.reconfigure(encoding='utf-8')

# Подключаем ядро вашего приложения
from data_engine import get_market_scan
from alerts_engine import check_alerts, send_telegram_alert

CONFIG_FILE = "bot_config.json"
STATE_FILE = "bot_state.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding='utf-8') as f:
            json.dump({
                "telegram_bot_token": "ВАШ_BOT_TOKEN_СЮДА",
                "telegram_chat_id": "ВАШ_CHAT_ID_СЮДА",
                "check_interval_minutes": 60
            }, f, indent=4)
        print(f"Файл {CONFIG_FILE} создан! Пожалуйста, впишите туда ваши Token и Chat ID и перезапустите скрипт.")
        return None
    with open(CONFIG_FILE, "r", encoding='utf-8') as f:
        return json.load(f)

def load_state():
    """Загружаем историю отправленных сигналов, чтобы не спамить одним и тем же"""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding='utf-8') as f:
        json.dump(state, f, indent=4)

def run_daemon():
    config = load_config()
    if not config:
        return
        
    token = config.get("telegram_bot_token")
    chat_id = config.get("telegram_chat_id")
    interval = config.get("check_interval_minutes", 60)
    
    if not token or token == "ВАШ_BOT_TOKEN_СЮДА":
        print("ОШИБКА: Впишите токен и chat_id в появившийся файл bot_config.json!")
        return

    print(f"🤖 Telegram Робот запущен! Сканирование рынка каждые {interval} минут...")
    
    # Чтобы робот не спамил старыми алертами, которые уже висят на D1 графике неделями, 
    # мы будем блокировать повторную отправку одного и того же алерта на 24 часа.
    BLOCK_REPEAT_HOURS = 24
    
    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск сканирования рынка...")
            # Получаем все данные (долго)
            df_scan, macro_data, fg_value, required_mos = get_market_scan()
            
            # Проверяем алерты
            alerts = check_alerts(df_scan, macro_data, fg_value)
            
            if not alerts:
                print("Текущих сигналов нет.")
            else:
                sent_history = load_state()
                now = datetime.now()
                new_alerts_sent = 0
                
                for alert in alerts:
                    # Уникальный ключ: тикер + тип сигнала (например, AAPL_STRONG BUY)
                    key = f"{alert['ticker']}_{alert['type']}"
                    
                    # Проверяем, не отправляли ли мы этот сигнал сегодня?
                    last_sent_str = sent_history.get(key)
                    if last_sent_str:
                        last_sent = datetime.fromisoformat(last_sent_str)
                        if now - last_sent < timedelta(hours=BLOCK_REPEAT_HOURS):
                            continue # Пропускаем, чтобы не спамить
                    
                    # Отправляем в Telegram
                    success, msg = send_telegram_alert(token, chat_id, alert)
                    if success:
                        print(f"✅ Отправлено: {alert['ticker']} - {alert['type']}")
                        sent_history[key] = now.isoformat()
                        new_alerts_sent += 1
                        time.sleep(1) # Делаем паузу 1 сек, чтобы Telegram не забанил за спам
                    else:
                        print(f"❌ Ошибка отправки для {alert['ticker']}: {msg}")
                        
                if new_alerts_sent > 0:
                    save_state(sent_history)
                else:
                    print("Новых уникальных сигналов за последние сутки не появилось.")
                
        except Exception as e:
            print(f"⚠️ Произошла ошибка во время сканирования: {e}")
            traceback.print_exc()

        print(f"Сон на {interval} минут... Следующая проверка через час.")
        time.sleep(interval * 60)

if __name__ == "__main__":
    run_daemon()
