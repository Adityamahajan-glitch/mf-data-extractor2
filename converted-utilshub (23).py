# === Streamlit AMFI NAV Dashboard ===
import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from ta.trend import SMAIndicator, MACD
from ta.momentum import RSIIndicator
from pytz import utc
import plotly.graph_objects as go
from stocktrends import Renko
from ta.volatility import AverageTrueRange
# === Helper Functions ===
def convert_date_to_utc_datetime(date_string):
    return datetime.strptime(date_string, "%d-%b-%Y").replace(tzinfo=utc)
def split_date_range(start_date_str, end_date_str, max_duration=90):
    start_date = datetime.strptime(start_date_str, "%d-%b-%Y")
    end_date = datetime.strptime(end_date_str, "%d-%b-%Y")
    ranges = []
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=max_duration - 1), end_date)
        ranges.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return ranges
def fetch_amfi_data(start_date_str, end_date_str):
    nav_list = []
    chunks = split_date_range(start_date_str, end_date_str)
    progress = st.progress(0, text="Fetching AMFI data...")
    total = len(chunks)
    for i, (start, end) in enumerate(chunks):
        url = f"https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?&frmdt={start.strftime('%d-%b-%Y')}&todt={end.strftime('%d-%b-%Y')}"
        response = requests.get(url)
        lines = response.text.split('\r\n')
        Structure = Category = Sub_Category = amc = ""
        j = 1
        for line in lines[1:]:
            split = line.split(";")
            if j == len(lines) - 1:
                break
            if split[0] == "":
                if j + 1 < len(lines):
                    if lines[j] == lines[j + 1]:
                        sch_cat = lines[j - 1].split("(")
                        sch_cat[-1] = sch_cat[-1][:-2].strip()
                        sch_cat = [s.strip() for s in sch_cat]
                        if len(sch_cat) > 1 and "-" in sch_cat[1]:
                            sub = sch_cat[1].split("-")
                            sch_cat.pop(-1)
                            sch_cat += [s.strip() for s in sub]
                        else:
                            if len(sch_cat) == 1:
                                sch_cat += ["", ""]
                            elif len(sch_cat) == 2:
                                sch_cat.append("")
                        Structure, Category, Sub_Category = sch_cat[:3]
                    elif "Mutual Fund" in lines[j + 1]:
                        amc = lines[j + 1]
            elif len(split) > 1:
                try:
                    code = int(split[0].strip())
                    name = split[1].strip()
                    dg = "Growth" if "growth" in name.lower() else "IDCW" if "idcw" in name.lower() or "dividend" in name.lower() else ""
                    inv_src = "Direct" if "direct" in name.lower() else "Regular" if "regular" in name.lower() else ""
                    nav = float(split[4].strip()) if split[4].strip() else None
                    date = convert_date_to_utc_datetime(split[7].strip())
                    nav_list.append({
                        "Structure": Structure,
                        "Category": Category,
                        "Sub_Category": Sub_Category,
                        "AMC": amc,
                        "Code": code,
                        "Name": name,
                        "Source": inv_src,
                        "Option": dg,
                        "Date": date,
                        "NAV": nav
                    })
                except:
                    pass
            j += 1
        progress.progress((i + 1) / total, text=f"Fetched {i + 1}/{total} chunks...")
    return pd.DataFrame(nav_list)
# === UI ===
st.set_page_config(page_title="AMFI NAV Dashboard", layout="wide")
st.title("\ud83d\udcca AMFI Mutual Fund NAV Dashboard")
st.markdown("Created using **Streamlit** | Data Source: [AMFI India](https://www.amfiindia.com/net-asset-value/nav-history)")
with st.sidebar:
    start_date = st.date_input("Fetch From Date", datetime(2025, 4, 1))
    end_date = st.date_input("Fetch To Date", datetime(2025, 6, 30))
    chart_type = st.radio("Chart Type", ["Line Chart", "Renko Chart"])
    renko_method = st.selectbox("Renko Brick Type", ["ATR(14)*1.5", "0.5%", "1%", "2%"])
    if st.button("\ud83d\udcc5 Fetch Data"):
        with st.spinner("Fetching data from AMFI..."):
            df_nav = fetch_amfi_data(start_date.strftime('%d-%b-%Y'), end_date.strftime('%d-%b-%Y'))
            if df_nav.empty:
                st.error("\u274c No data returned from AMFI.")
            else:
                st.session_state["df_nav"] = df_nav
                st.success(f"\u2705 Loaded {len(df_nav)} records.")
if "df_nav" in st.session_state:
    df_nav = st.session_state["df_nav"]
    selected_amc = st.selectbox("Select AMC", sorted(df_nav["AMC"].dropna().unique()))
    schemes = df_nav[df_nav["AMC"] == selected_amc]["Name"].unique()
    selected_scheme = st.selectbox("Select Scheme", schemes)
    filtered_df = df_nav[df_nav["Name"] == selected_scheme].copy()
    filtered_df = filtered_df.sort_values("Date")
    min_date, max_date = filtered_df["Date"].min().date(), filtered_df["Date"].max().date()
    col1, col2 = st.columns(2)
    with col1:
        f_date = st.date_input("From Date", min_date)
    with col2:
        t_date = st.date_input("To Date", max_date)
    filtered_df = filtered_df[
        (filtered_df["Date"].dt.date >= f_date) & (filtered_df["Date"].dt.date <= t_date)
    ].copy()
    df_plot = filtered_df.copy()
    df_plot = df_plot.sort_values("Date")
    df_plot["RSI_14"] = RSIIndicator(close=df_plot["NAV"], window=14).rsi()
    df_plot["RSI_Premier"] = df_plot["RSI_14"].ewm(span=5, adjust=False).mean()
    macd = MACD(close=df_plot["NAV"], window_slow=26, window_fast=12, window_sign=9)
    df_plot["MACD"] = macd.macd()
    df_plot["Signal"] = macd.macd_signal()
    sma1 = st.number_input("SMA 1", min_value=1, value=50, step=5)
    sma2 = st.number_input("SMA 2", min_value=1, value=100, step=5)
    sma3 = st.number_input("SMA 3", min_value=1, value=200, step=5)
    df_plot[f"SMA_{sma1}"] = SMAIndicator(df_plot["NAV"], sma1).sma_indicator()
    df_plot[f"SMA_{sma2}"] = SMAIndicator(df_plot["NAV"], sma2).sma_indicator()
    df_plot[f"SMA_{sma3}"] = SMAIndicator(df_plot["NAV"], sma3).sma_indicator()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["NAV"], name="NAV", line=dict(color="cyan")))
    fig.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot[f"SMA_{sma1}"], name=f"SMA {sma1}", line=dict(dash="dot", color="orange")))
    fig.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot[f"SMA_{sma2}"], name=f"SMA {sma2}", line=dict(dash="dot", color="lime")))
    fig.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot[f"SMA_{sma3}"], name=f"SMA {sma3}", line=dict(dash="dot", color="magenta")))
    # Premier RSI as Area
    fig.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["RSI_Premier"], fill='tozeroy', name="Premier RSI",
                             line=dict(color="green"), opacity=0.3,
                             hoverinfo="x+y",
                             fillcolor="rgba(0,255,0,0.2)",
                             showlegend=True))
    # MACD
    fig.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["MACD"], name="MACD", line=dict(color="aqua")))
    fig.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["Signal"], name="MACD Signal", line=dict(dash="dot", color="white")))
    fig.update_layout(
        height=800,
        title=f"{selected_scheme} - Combined Chart (NAV + Indicators)",
        template="plotly_dark",
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)
    if chart_type == "Renko Chart":
        df_renko = df_plot[["Date", "NAV"]].copy()
        df_renko.columns = ["date", "close"]
        df_renko["date"] = pd.to_datetime(df_renko["date"])
        df_renko["open"] = df_renko["close"]
        df_renko["high"] = df_renko["close"]
        df_renko["low"] = df_renko["close"]
        df_renko.set_index("date", inplace=True)
        renko = Renko(df_renko.reset_index())
        if renko_method == "ATR(14)*1.5":
            atr = AverageTrueRange(df_renko["high"], df_renko["low"], df_renko["close"], window=14).average_true_range()
            box_size = round(atr.iloc[-1] * 1.5, 2)
        else:
            pct = float(renko_method.strip("%")) / 100
            box_size = round(df_renko["close"].iloc[-1] * pct, 2)
        renko.brick_size = box_size
        renko_df = renko.get_ohlc_data()
        st.subheader(f"Renko Chart: {selected_scheme} | Brick Size: {box_size}")
        st.dataframe(renko_df.tail(10))