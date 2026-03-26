import streamlit as st
import pandas as pd
from data_engine import get_market_scan
from chart_engine import generate_chart
from portfolio_engine import (
    init_portfolio, get_portfolio, execute_buy, execute_sell,
    calculate_portfolio_metrics, get_trade_log_df, get_holdings_df
)
from alerts_engine import check_alerts, send_all_alerts_telegram

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Buffett Intelligence Engine", 
    layout="wide", 
    page_icon="📈",
    initial_sidebar_state="expanded"
)

st.title("BUFFETT INTELLIGENCE ENGINE 📈")
st.markdown("##### Анализ недооцененных активов по методу Уоррена Баффета | Anti-Gravity")

# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data(ttl=14400, show_spinner=False)
def load_market_data():
    return get_market_scan()

with st.spinner("🔄 Загрузка и анализ рынка... (это может занять 1-2 минуты)"):
    df_scan, macro_data, fg_value, required_mos = load_market_data()
    
    # Auto-fix cache for missing data with retry limit to avoid infinite reloads
    if "data_retries" not in st.session_state:
        st.session_state.data_retries = 0

    if not df_scan.empty and st.session_state.data_retries < 2:
        types_present = df_scan["Type"].values
        if "Commodity" not in types_present or "Stock" not in types_present or "Crypto" not in types_present:
            st.session_state.data_retries += 1
            load_market_data.clear()
            st.rerun()
            
    # Reset retries if data is healthy
    if not df_scan.empty and "Commodity" in df_scan["Type"].values and "Stock" in df_scan["Type"].values and "Crypto" in df_scan["Type"].values:
        st.session_state.data_retries = 0
# ============================================================
# SIDEBAR: Global Guard Macro Module
# ============================================================

st.sidebar.header("🌍 Global Guard — Макро")
for k, v in macro_data.items():
    st.sidebar.metric(label=k, value=v)

# Fear & Greed visual indicator
if fg_value > 75:
    st.sidebar.error("🔥 РЫНОК ПЕРЕГРЕТ — Фиксируйте прибыль!")
elif fg_value < 25:
    st.sidebar.success("😱 ЭКСТРЕМАЛЬНЫЙ СТРАХ — Активный поиск недооценённых активов!")
else:
    st.sidebar.info(f"📊 Настроение рынка: {fg_value}/100")

st.sidebar.caption(f"Требуемый Margin of Safety: {required_mos}%")

st.sidebar.markdown("---")

# Telegram Settings
st.sidebar.header("📱 Telegram Alerts")
tg_token = st.sidebar.text_input("Bot Token", type="password", key="tg_token")
tg_chat_id = st.sidebar.text_input("Chat ID", key="tg_chat_id")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 ОБНОВИТЬ ДАННЫЕ ВРУЧНУЮ", use_container_width=True):
    load_market_data.clear()
    st.rerun()

# ============================================================
# TABS
# ============================================================

tab_scanner, tab_charts, tab_alerts, tab_portfolio = st.tabs([
    "📊 Сканер", "📈 Графики", "🔔 Smart Alerts", "💰 Демо-Портфель"
])

# ============================================================
# TAB 1: SCANNER + TABLE
# ============================================================

with tab_scanner:
    # Filter buttons
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🛢 СЫРЬЁ", use_container_width=True):
            st.session_state.filter = "Commodity"
    with col2:
        if st.button("🚀 АКЦИИ", use_container_width=True):
            st.session_state.filter = "Stock"
    with col3:
        if st.button("💎 КРИПТО", use_container_width=True):
            st.session_state.filter = "Crypto"
    with col4:
        if st.button("🛡️ ЗАЩИТНЫЕ", use_container_width=True):
            st.session_state.filter = "Defensive"

    if "filter" not in st.session_state:
        st.session_state.filter = "Stock"

    df_display = df_scan.copy()
    
    # Safety: if DataFrame is empty or missing expected columns, clear cache and retry
    if df_display.empty or "Undervaluation %" not in df_display.columns:
        st.warning("⏳ Данные ещё загружаются или произошла ошибка. Попробуйте обновить.")
        if st.button("🔄 Перезагрузить данные"):
            load_market_data.clear()
            st.rerun()
        st.stop()
    
    if st.session_state.filter == "Stock":
        df_display = df_display[df_display["Type"] == "Stock"]
    elif st.session_state.filter == "Crypto":
        df_display = df_display[df_display["Type"] == "Crypto"]
    elif st.session_state.filter == "Commodity":
        df_display = df_display[df_display["Type"] == "Commodity"]
    elif st.session_state.filter == "Defensive":
        defensive = ["Consumer Defensive", "Healthcare", "Utilities"]
        if "Sector" in df_display.columns:
            df_display = df_display[df_display["Sector"].isin(defensive)]

    df_display = df_display.sort_values(by="Undervaluation %", ascending=False).head(20)

    # Signal coloring
    def color_signal(val):
        if pd.isna(val) or val == "N/A":
            return ""
        
        val_str = str(val).upper()
        if "BUY" in val_str:
            if "STRONG" in val_str:
                return "color: #00ff00; font-weight: bold; background-color: rgba(0, 255, 0, 0.1);"
            return "color: #4caf50; font-weight: bold"
        elif "WATCH" in val_str:
            return "color: #ff9800; font-weight: bold"
        elif "SELL" in val_str:
            if "STRONG" in val_str:
                return "color: #ff0000; font-weight: bold; background-color: rgba(255, 0, 0, 0.1);"
            return "color: #f44336; font-weight: bold"
        return ""

    st.markdown(f"### 📋 Рыночный Сканер — {st.session_state.filter} (Топ 20)")
    st.caption(f"Найдены активы с высоким уровнем соответствия критериям Баффета | MoS ≥ {required_mos}%")

    if not df_display.empty:
        # Hide internal analytical columns from the visual table, keeping them in the background data
        cols_to_hide = [
            "Type", "Sector", "Entry (Support)", "Exit (Resistance)", 
            "P/E", "P/B", "ROE %", "FCF Yield %", "FDV/MCap", "Intrinsic Value", 
            "52W Low", "52W High", "Детали Сигнала"
        ]
        df_display_table = df_display.drop(columns=cols_to_hide, errors="ignore")
        
        signal_cols = [c for c in ['Signal 1H', 'Signal 4H', 'Signal 1D', 'Общий Сигнал'] if c in df_display_table.columns]
        
        if signal_cols:
            styled = df_display_table.style.map(color_signal, subset=signal_cols)
        else:
            styled = df_display_table.style
        
        try:
            event = st.dataframe(
                styled, 
                use_container_width=True, 
                hide_index=True, 
                on_select="rerun", 
                selection_mode="single-row"
            )
            
            if len(event.selection.rows) > 0:
                selected_idx = event.selection.rows[0]
                clicked_asset = df_display_table.iloc[selected_idx]["Asset"]
                st.markdown("---")
                col_title, col_tf, col_zin, col_zout = st.columns([3, 2, 0.5, 0.5])
                with col_title:
                    st.subheader(f"🔍 График: {clicked_asset}")
                with col_tf:
                    scan_tf = st.radio("Таймфрейм", ["15m", "1h", "4h", "1d"], index=3, horizontal=True, label_visibility="collapsed", key=f"scan_tf_{clicked_asset}")
                with col_zin:
                    if st.button("🔍+", help="Увеличить", use_container_width=True, key=f"sz_in_{clicked_asset}"):
                        st.session_state.zoom_level = max(20, st.session_state.zoom_level - 30)
                        st.rerun()
                with col_zout:
                    if st.button("🔍−", help="Уменьшить", use_container_width=True, key=f"sz_out_{clicked_asset}"):
                        st.session_state.zoom_level = min(500, st.session_state.zoom_level + 30)
                        st.rerun()
                        
                with st.spinner("Загрузка графика..."):
                    fig, patterns = generate_chart(clicked_asset, timeframe=scan_tf, zoom_bars=st.session_state.get("zoom_level", 100))
                    if patterns:
                        st.info(f"🔍 **Обнаружены паттерны:** {', '.join(patterns)}")
                    if fig:
                        st.pyplot(fig)
        except TypeError:
            # Fallback for older streamlit versions that don't support on_select
            st.dataframe(styled, use_container_width=True, hide_index=True)
            clicked_asset = st.selectbox("Посмотреть график актива из таблицы:", [""] + df_display_table["Asset"].tolist())
            if clicked_asset:
                st.markdown("---")
                col_title, col_tf = st.columns([3, 2])
                with col_title:
                    st.subheader(f"🔍 График: {clicked_asset}")
                with col_tf:
                    scan_tf_2 = st.radio("Таймфрейм", ["15m", "1h", "4h", "1d"], index=3, horizontal=True, label_visibility="collapsed", key=f"scan_tf_2_{clicked_asset}")
                with st.spinner("Загрузка графика..."):
                    fig, patterns = generate_chart(clicked_asset, timeframe=scan_tf_2)
                    if patterns:
                        st.info(f"🔍 **Обнаружены паттерны:** {', '.join(patterns)}")
                    if fig:
                        st.pyplot(fig)
            
    else:
        st.warning("Нет данных по заданному фильтру.")

# ============================================================
# TAB 2: CHARTS
# ============================================================

with tab_charts:
    st.markdown("### 📈 Глубокий Технический Анализ")
    
    cat_charts = st.radio("Категория (Графики)", ["Акции", "Крипто", "Сырьё", "Защитные"], horizontal=True, key="cat_charts")
    cat_match_c = {"Акции": "Stock", "Крипто": "Crypto", "Сырьё": "Commodity", "Защитные": "Defensive"}[cat_charts]
    
    if cat_match_c == "Defensive":
        filtered_df_c = df_scan[df_scan["Sector"].isin(["Consumer Defensive", "Healthcare", "Utilities"])] if not df_scan.empty and "Sector" in df_scan.columns else pd.DataFrame()
    else:
        filtered_df_c = df_scan[df_scan["Type"] == cat_match_c] if not df_scan.empty and "Type" in df_scan.columns else pd.DataFrame()

    if filtered_df_c.empty:
        st.warning(f"Нет данных для категории: {cat_charts}")
    else:
        if "zoom_level" not in st.session_state:
            st.session_state.zoom_level = 100

        col_asset, col_tf, col_zin, col_zout = st.columns([2, 1, 0.5, 0.5])
        with col_asset:
            selected_asset = st.selectbox("Актив", filtered_df_c["Asset"].tolist(), key="chart_asset_sel")
        with col_tf:
            selected_tf = st.radio(
                "Таймфрейм", ["15m", "1h", "4h", "1d"], index=3, horizontal=True,
                label_visibility="collapsed", key="chart_tf_sel"
            )
        with col_zin:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔍+", help="Увеличить", use_container_width=True, key="btn_z_in_1"):
                st.session_state.zoom_level = max(20, st.session_state.zoom_level - 30)
                st.rerun()
        with col_zout:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔍−", help="Уменьшить", use_container_width=True, key="btn_z_out_1"):
                st.session_state.zoom_level = min(500, st.session_state.zoom_level + 30)
                st.rerun()
            
        if selected_asset:
            with st.spinner(f"Построение графика {selected_asset} ({selected_tf})..."):
                fig, patterns = generate_chart(
                    selected_asset, timeframe=selected_tf, 
                    zoom_bars=st.session_state.zoom_level
                )
                if fig:
                    if patterns:
                        st.info(f"🔍 **Обнаружены паттерны:** {', '.join(patterns)}")
                    st.pyplot(fig)
                else:
                    st.warning("Не удалось загрузить данные для графика.")

# ============================================================
# TAB 3: SMART ALERTS
# ============================================================

with tab_alerts:
    st.markdown("### 🔔 Smart Alerts — Инвестиционные Сигналы")
    
    alerts = check_alerts(df_scan, macro_data, fg_value)
    
    if not alerts:
        st.success("✅ Нет активных триггеров на данный момент.")
    else:
        st.metric("Активных алертов", len(alerts))
        
        for alert in alerts:
            priority_color = "🔴" if alert["priority"] == "HIGH" else "🟡" if alert["priority"] == "MEDIUM" else "🟢"
            
            with st.expander(f"{priority_color} {alert['type']} — {alert['ticker']}", expanded=(alert["priority"] == "HIGH")):
                st.markdown(f"**📌 Тикер:** `{alert['ticker']}`")
                st.markdown(f"**📊 Сигнал:** {alert['message']}")
                st.markdown(f"**⚠️ Риск:** {alert['risk']}")
        
        st.markdown("---")
        if tg_token and tg_chat_id:
            if st.button("📤 Отправить все алерты в Telegram", use_container_width=True):
                with st.spinner("Отправка в Telegram..."):
                    results = send_all_alerts_telegram(tg_token, tg_chat_id, alerts)
                    success_count = sum(1 for r in results if r["success"])
                    st.success(f"Отправлено: {success_count}/{len(results)}")
        else:
            st.caption("💡 Введите Bot Token и Chat ID в боковой панели для отправки алертов в Telegram.")

# ============================================================
# TAB 4: DEMO PORTFOLIO
# ============================================================

with tab_portfolio:
    st.markdown("### 💰 Демо-Торговля — Виртуальный Портфель")
    
    init_portfolio(st.session_state)
    portfolio = get_portfolio(st.session_state)
    
    # Portfolio Metrics
    metrics = calculate_portfolio_metrics(portfolio)
    
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("💵 Кэш", f"${portfolio['cash']:,.2f}")
    with col_m2:
        st.metric("📈 Доходность", f"{metrics['total_return']:+.2f}%")
    with col_m3:
        st.metric("📊 Sharpe Ratio", f"{metrics['sharpe_ratio']}")
    with col_m4:
        st.metric("📉 Макс. Просадка", f"{metrics['max_drawdown']:.2f}%")
    
    st.markdown("---")
    
    # Trade Execution
    st.markdown("#### 🛒 Совершить сделку")
    
    cat_port = st.radio("Выбор рынка", ["Акции", "Крипто", "Сырьё", "Защитные"], horizontal=True, key="cat_port")
    cat_match_p = {"Акции": "Stock", "Крипто": "Crypto", "Сырьё": "Commodity", "Защитные": "Defensive"}[cat_port]
    
    if cat_match_p == "Defensive":
        filtered_df_p = df_scan[df_scan["Sector"].isin(["Consumer Defensive", "Healthcare", "Utilities"])] if not df_scan.empty and "Sector" in df_scan.columns else pd.DataFrame()
    else:
        filtered_df_p = df_scan[df_scan["Type"] == cat_match_p] if not df_scan.empty and "Type" in df_scan.columns else pd.DataFrame()
        
    all_assets_p = filtered_df_p["Asset"].tolist() if not filtered_df_p.empty else []

    col_t1, col_t2, col_t3, col_t4 = st.columns([2, 1, 1, 1])
    
    with col_t1:
        trade_asset = st.selectbox("Актив", all_assets_p, key="trade_asset")
        
    initial_price = 0.0
    if trade_asset and not df_scan.empty:
        match = df_scan[df_scan["Asset"] == trade_asset]
        if not match.empty:
            initial_price = float(match.iloc[0]["Price"])

    with col_t2:
        trade_price = st.number_input("Цена ($)", value=initial_price if initial_price > 0 else 0.01, min_value=0.01, step=0.01, key=f"trade_price_{trade_asset}" if trade_asset else "trade_price")
    with col_t3:
        trade_qty = st.number_input("Кол-во", value=1, min_value=1, step=1, key="trade_qty")
    with col_t4:
        st.markdown("<br>", unsafe_allow_html=True)
        col_buy, col_sell = st.columns(2)
        with col_buy:
            if st.button("🟢 BUY", use_container_width=True, key="btn_buy"):
                if trade_asset:
                    success, msg = execute_buy(st.session_state, trade_asset, trade_price, trade_qty)
                    if success:
                        st.toast(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.toast(f"❌ {msg}")
        with col_sell:
            if st.button("🔴 SHORT", use_container_width=True, key="btn_sell", help="Продать актив (возвести шорт)"):
                if trade_asset:
                    success, msg = execute_sell(st.session_state, trade_asset, trade_price, trade_qty)
                    if success:
                        st.toast(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.toast(f"❌ {msg}")
                        
    if trade_asset:
        
        @st.fragment(run_every="1s")
        def live_portfolio_chart(asset):
            st.markdown("##### 📈 Live График для Торговли")
            
            # 1. Very fast live price fetch inside the fragment
            live_price = initial_price
            try:
                import yfinance as yf
                from chart_engine import get_internal_ticker
                internal_t = get_internal_ticker(asset)
                fast_data = yf.download(internal_t, period="1d", interval="1m", progress=False)
                if not fast_data.empty:
                    if isinstance(fast_data.columns, pd.MultiIndex):
                        live_price = float(fast_data['Close'][internal_t].dropna().iloc[-1])
                    else:
                        live_price = float(fast_data['Close'].dropna().iloc[-1])
            except Exception:
                pass
            
            st.markdown(f"**⚡ Текущая рыночная цена:** `${live_price:,.2f}` *(обновляется каждую секунду)*")

            if "zoom_level" not in st.session_state:
                st.session_state.zoom_level = 100
                
            col_ptf, col_p_zin, col_p_zout, _ = st.columns([1.5, 0.5, 0.5, 1.5])
            with col_ptf:
                port_tf = st.radio(
                    "Таймфрейм", ["15m", "1h", "4h", "1d"], index=0, horizontal=True,
                    label_visibility="collapsed", key=f"port_tf_sel_{asset}"
                )
            with col_p_zin:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔍+", help="Увеличить", use_container_width=True, key=f"btn_z_in_2_{asset}"):
                    st.session_state.zoom_level = max(20, st.session_state.zoom_level - 30)
                    st.rerun()
            with col_p_zout:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔍−", help="Уменьшить", use_container_width=True, key=f"btn_z_out_2_{asset}"):
                    st.session_state.zoom_level = min(500, st.session_state.zoom_level + 30)
                    st.rerun()
                    
            fig, patterns = generate_chart(asset, timeframe=port_tf, zoom_bars=st.session_state.get("zoom_level", 100))
            if patterns:
                st.info(f"🔍 **Обнаружены паттерны:** {', '.join(patterns)}")
            if fig:
                st.pyplot(fig)
                
        # Mount and start the fragment
        live_portfolio_chart(trade_asset)
    
    st.markdown("---")
    
    # Current Holdings
    st.markdown("#### 📦 Текущие позиции")
    # Build current prices dict from scan
    current_prices = {}
    if not df_scan.empty:
        for _, row in df_scan.iterrows():
            current_prices[row["Asset"]] = row["Price"]
    
    holdings_df = get_holdings_df(portfolio, current_prices)
    if not holdings_df.empty:
        st.dataframe(holdings_df, use_container_width=True, hide_index=True)
    else:
        st.info("Портфель пуст. Совершите первую сделку!")
    
    # Trade Log
    st.markdown("#### 📜 Журнал сделок")
    trade_log = get_trade_log_df(portfolio)
    if not trade_log.empty:
        st.dataframe(trade_log, use_container_width=True, hide_index=True)
    else:
        st.info("История сделок пуста.")

# ============================================================
# FOOTER
# ============================================================

st.markdown("---")
st.caption("Данные обновляются каждые 4 часа. Стратегия: Стоимостное инвестирование с запасом прочности. Anti-Gravity © 2026")
