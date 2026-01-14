# app.py
# TrendGuardAI - نسخة محسّنة ومستقرة - يناير 2026

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

try:
    from polygon import RESTClient
except ImportError:
    RESTClient = None

try:
    from pycoingecko import CoinGeckoAPI
except ImportError:
    CoinGeckoAPI = None

# ────────────────────────────────────────────────
#  إعدادات الصفحة
# ────────────────────────────────────────────────

st.set_page_config(
    page_title="TrendGuardAI – حارس الترندات",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ────────────────────────────────────────────────
#  قراءة المفتاح
# ────────────────────────────────────────────────

POLYGON_KEY = os.environ.get("POLYGON_API_KEY", "").strip()

if not POLYGON_KEY:
    st.warning("مفتاح Polygon.io غير موجود في Secrets → بعض الرموز (الأسهم خصوصًا) لن تعمل")

# ────────────────────────────────────────────────
#  دوال جلب البيانات
# ────────────────────────────────────────────────

@st.cache_data(ttl=420, show_spinner=False)
def fetch_polygon(ticker: str, days: int) -> pd.DataFrame | None:
    if not RESTClient or not POLYGON_KEY:
        return None

    client = RESTClient(api_key=POLYGON_KEY)

    ticker_clean = ticker.strip().upper()
    if ticker_clean.endswith("-USD"):
        base = ticker_clean[:-4]
        poly_ticker = f"X:{base}USD"
    else:
        poly_ticker = ticker_clean

    try:
        from_ = (datetime.now() - timedelta(days=days+1)).strftime("%Y-%m-%d")
        to_   = datetime.now().strftime("%Y-%m-%d")

        aggs = client.get_aggs(poly_ticker, 1, "day", from_, to_)
        if not aggs:
            return None

        df = pd.DataFrame(aggs)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("timestamp")[["open","high","low","close","volume"]]
        return df
    except Exception:
        return None


@st.cache_data(ttl=420, show_spinner=False)
def fetch_coingecko(ticker: str, days: int) -> pd.DataFrame | None:
    if not CoinGeckoAPI:
        return None

    cg = CoinGeckoAPI()

    clean = ticker.strip().upper().replace("-USD", "").replace("-","")
    mapping = {
        "BTC":"bitcoin",   "ETH":"ethereum",   "SOL":"solana",
        "ADA":"cardano",   "XRP":"ripple",     "DOGE":"dogecoin",
        "BNB":"binancecoin","AVAX":"avalanche-2","DOT":"polkadot",
        "LINK":"chainlink", "MATIC":"polygon",  "LTC":"litecoin",
    }
    coin_id = mapping.get(clean, clean.lower())

    try:
        data = cg.get_coin_market_chart_by_id(coin_id, "usd", days, interval="daily")
        if "prices" not in data or len(data["prices"]) < 2:
            return None

        prices  = pd.DataFrame(data["prices"],  columns=["ts","close"])
        volumes = pd.DataFrame(data["total_volumes"], columns=["ts","volume"])

        prices["ts"]  = pd.to_datetime(prices["ts"],  unit="ms")
        volumes["ts"] = pd.to_datetime(volumes["ts"], unit="ms")

        df = pd.merge(prices, volumes, on="ts").set_index("ts")
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)

        # تقريب بسيط للـ OHLC
        df["open"]  = df["close"].shift(1).fillna(df["close"])
        df["high"]  = df[["open","close"]].max(axis=1)
        df["low"]   = df[["open","close"]].min(axis=1)

        return df[["open","high","low","close","volume"]]
    except Exception:
        return None


def detect_pump_dump_signals(df: pd.DataFrame) -> list:
    if len(df) < 3:
        return []

    df = df.copy()
    df["price_chg"] = df["close"].pct_change() * 100
    df["vol_chg"]   = df["volume"].pct_change() * 100

    signals = (df["price_chg"] > 5.0) & (df["vol_chg"] > 250.0)

    alerts = []
    for dt, row in df[signals].iterrows():
        risk = min(99, int(abs(row["price_chg"]) * 8 + abs(row["vol_chg"]) * 0.1))
        alerts.append({
            "date": dt.strftime("%Y-%m-%d"),
            "price_chg": round(row["price_chg"],1),
            "vol_chg":   round(row["vol_chg"],0),
            "risk_pct":  risk
        })

    return alerts


# ────────────────────────────────────────────────
#  واجهة المستخدم
# ────────────────────────────────────────────────

st.title("🛡️ TrendGuardAI")
st.caption("كشف التحركات المشبوهة (Pump & Dump / FOMO) في الأسهم والعملات الرقمية")

left, right = st.columns([5,3])

with left:
    symbol = st.text_input("رمز الأصل", "BTC-USD", key="symbol").strip().upper()

with right:
    lookback = st.slider("عدد الأيام", 3, 30, 7, step=1)

provider_options = ["تلقائي"]
if POLYGON_KEY:
    provider_options.append("Polygon.io فقط")
provider_options.append("CoinGecko فقط")

source_choice = st.selectbox("المصدر المفضّل", provider_options, index=0)

if st.button("تحليل الآن", type="primary", use_container_width=True):

    if not symbol:
        st.error("أدخل رمزًا صحيحًا")
        st.stop()

    with st.spinner("جاري جلب ومعالجة البيانات..."):

        df = None
        used_source = ""

        # ─── الترتيب حسب اختيار المستخدم ────────────────────────────────
        attempts = []

        if source_choice == "تلقائي":
            if POLYGON_KEY:
                attempts = ["polygon", "coingecko"]
            else:
                attempts = ["coingecko"]
        elif source_choice == "Polygon.io فقط":
            attempts = ["polygon"]
        else:
            attempts = ["coingecko"]

        for attempt in attempts:
            if attempt == "polygon":
                df = fetch_polygon(symbol, lookback)
                if df is not None:
                    used_source = "Polygon.io"
                    break
            else:
                df = fetch_coingecko(symbol, lookback)
                if df is not None:
                    used_source = "CoinGecko"
                    break

        if df is None:
            st.error("تعذّر جلب البيانات من أي مصدر.")
            if "coingecko" in attempts:
                st.info("• تأكد من كتابة الرمز بشكل صحيح\n"
                        "• للعملات الرقمية: BTC-USD, ETH-USD, SOL-USD ...\n"
                        "• للأسهم: AAPL, TSLA, NVDA ... (يتطلب مفتاح Polygon)")
            st.stop()

        # ─── التحليل ─────────────────────────────────────────────────────
        alerts = detect_pump_dump_signals(df)

        st.success(f"تم جلب {len(df)} يوم من {used_source}")

        if alerts:
            st.subheader("⚠️ إشارات مشبوهة محتملة")
            for al in alerts:
                st.warning(
                    f"**{al['date']}**  \n"
                    f"تغيّر السعر: **+{al['price_chg']}%**    \n"
                    f"تغيّر الحجم: **+{al['vol_chg']}%**    \n"
                    f"تقدير مخاطر الانهيار: **{al['risk_pct']}%**"
                )
        else:
            st.success("لا توجد إشارات Pump & Dump واضحة في الفترة المختارة.")

        # ─── عرض الرسم البياني والجدول ──────────────────────────────────
        st.subheader("سعر الإغلاق")
        st.line_chart(df["close"])

        with st.expander("بيانات مفصلة"):
            st.dataframe(df.round(2))

        with st.expander("إحصائيات"):
            st.dataframe(df.describe().round(2))

st.markdown("---")
st.caption("للأغراض التعليمية والبحثية فقط • لا يُعتبر نصيحة استثمارية")
