# app.py
# TrendGuardAI - نسخة محسّنة مع اقتراحات رموز

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
    layout="wide"
)


# ────────────────────────────────────────────────
#  مفتاح Polygon
# ────────────────────────────────────────────────

POLYGON_KEY = os.environ.get("POLYGON_API_KEY", "").strip()

if not POLYGON_KEY:
    st.sidebar.warning("مفتاح Polygon.io غير موجود في Secrets\n→ بعض الأسهم لن تعمل")


# ────────────────────────────────────────────────
#  قائمة الرموز الشائعة (للاقتراحات)
# ────────────────────────────────────────────────

POPULAR_SYMBOLS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "BNB-USD",
    "AVAX-USD", "LINK-USD", "DOT-USD", "LTC-USD", "MATIC-USD",
    "AAPL", "TSLA", "NVDA", "MSFT", "GOOGL", "AMZN", "META", "AMD", "INTC"
]


# ────────────────────────────────────────────────
#  دوال جلب البيانات
# ────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def fetch_polygon(ticker: str, days: int) -> pd.DataFrame | None:
    if not RESTClient or not POLYGON_KEY:
        return None

    client = RESTClient(api_key=POLYGON_KEY)

    t = ticker.strip().upper()
    if t.endswith("-USD"):
        base = t[:-4]
        poly_ticker = f"X:{base}USD"
    else:
        poly_ticker = t

    try:
        from_ = (datetime.now() - timedelta(days=days+2)).strftime("%Y-%m-%d")
        to_   = datetime.now().strftime("%Y-%m-%d")

        aggs = client.get_aggs(poly_ticker, 1, "day", from_, to_)
        if not aggs:
            return None

        df = pd.DataFrame(aggs)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("timestamp")[["open","high","low","close","volume"]]
        return df
    except:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def fetch_coingecko(ticker: str, days: int) -> pd.DataFrame | None:
    if not CoinGeckoAPI:
        return None

    cg = CoinGeckoAPI()

    clean = ticker.strip().upper().replace("-USD", "").replace("-","")
    mapping = {
        "BTC":"bitcoin", "ETH":"ethereum", "SOL":"solana", "XRP":"ripple",
        "ADA":"cardano", "DOGE":"dogecoin", "BNB":"binancecoin",
        "AVAX":"avalanche-2", "DOT":"polkadot", "LINK":"chainlink",
        "MATIC":"polygon", "LTC":"litecoin"
    }
    coin_id = mapping.get(clean, clean.lower())

    try:
        data = cg.get_coin_market_chart_by_id(coin_id, "usd", days, interval="daily")
        if "prices" not in data or len(data["prices"]) < 2:
            return None

        p = pd.DataFrame(data["prices"],  columns=["ts","close"])
        v = pd.DataFrame(data["total_volumes"], columns=["ts","volume"])

        p["ts"] = pd.to_datetime(p["ts"], unit="ms")
        v["ts"] = pd.to_datetime(v["ts"], unit="ms")

        df = pd.merge(p, v, on="ts").set_index("ts")
        df[["close","volume"]] = df[["close","volume"]].astype(float)

        df["open"]  = df["close"].shift(1).fillna(df["close"])
        df["high"]  = df[["open","close"]].max(axis=1)
        df["low"]   = df[["open","close"]].min(axis=1)

        return df[["open","high","low","close","volume"]]
    except:
        return None


def find_pump_dump_signals(df: pd.DataFrame) -> list[dict]:
    if len(df) < 3:
        return []

    df = df.copy()
    df["price_pct"] = df["close"].pct_change() * 100
    df["vol_pct"]   = df["volume"].pct_change() * 100

    signals = (df["price_pct"] > 5.0) & (df["vol_pct"] > 250.0)

    alerts = []
    for dt, row in df[signals].iterrows():
        risk = min(99, int(row["price_pct"] * 7 + row["vol_pct"] * 0.08))
        alerts.append({
            "date": dt.strftime("%Y-%m-%d"),
            "price_change": round(row["price_pct"], 1),
            "vol_change":   round(row["vol_pct"], 0),
            "risk":         risk
        })

    return alerts


# ────────────────────────────────────────────────
#  الواجهة
# ────────────────────────────────────────────────

st.title("🛡️ TrendGuardAI")
st.caption("كشف التحركات المشبوهة (Pump & Dump / FOMO)")

# ─── اختيار الرمز ──────────────────────────────────────────────────

st.subheader("رمز الأصل")

preset = st.selectbox(
    "اختر رمزًا شائعًا أو اكتب بنفسك",
    options=["اكتب رمزًا مخصصًا..."] + POPULAR_SYMBOLS,
    index=0,
    key="preset"
)

if preset == "اكتب رمزًا مخصصًا...":
    symbol = st.text_input(
        "اكتب الرمز (مثال: BTC-USD أو TSLA)",
        value="",
        placeholder="BTC-USD, ETH-USD, AAPL, TSLA...",
        key="custom"
    ).strip().upper()
else:
    symbol = preset.strip().upper()
    st.success(f"الرمز المختار: **{symbol}**", icon="✅")

# ─── باقي الإعدادات ───────────────────────────────────────────────

col_days, col_source = st.columns([1, 2])

with col_days:
    days = st.slider("عدد الأيام", 3, 30, 7)

with col_source:
    source_pref = st.radio(
        "المصدر المفضّل",
        options=["تلقائي", "Polygon.io فقط", "CoinGecko فقط"],
        horizontal=True,
        index=0
    )

# ─── زر التحليل ───────────────────────────────────────────────────

if st.button("🚀 تحليل الآن", type="primary", use_container_width=True):

    if not symbol:
        st.error("يرجى إدخال رمز أصل صحيح")
        st.stop()

    with st.spinner("جاري جلب البيانات..."):

        df = None
        used = ""

        order = []
        if source_pref == "تلقائي":
            if POLYGON_KEY:
                order = ["polygon", "coingecko"]
            else:
                order = ["coingecko"]
        elif source_pref == "Polygon.io فقط":
            order = ["polygon"]
        else:
            order = ["coingecko"]

        for src in order:
            if src == "polygon":
                df = fetch_polygon(symbol, days)
                if df is not None:
                    used = "Polygon.io"
                    break
            else:
                df = fetch_coingecko(symbol, days)
                if df is not None:
                    used = "CoinGecko"
                    break

        if df is None:
            st.error("تعذّر جلب البيانات من أي مصدر.")
            st.markdown("""
            **نصائح للحل:**
            • للعملات الرقمية: جرب BTC-USD, ETH-USD, SOL-USD...
            • للأسهم: جرب AAPL, TSLA, NVDA... (يتطلب مفتاح Polygon صحيح)
            • تأكد من كتابة الرمز بدون مسافات زائدة
            """)
            st.stop()

        # ─── التحليل والعرض ─────────────────────────────────────────────

        st.success(f"تم جلب {len(df)} يوم من **{used}**")

        alerts = find_pump_dump_signals(df)

        if alerts:
            st.subheader("⚠️ إشارات مشبوهة")
            for a in alerts:
                st.warning(
                    f"**{a['date']}**  \n"
                    f"تغيّر السعر: **+{a['price_change']}%**  \n"
                    f"تغيّر الحجم: **+{a['vol_change']}%**  \n"
                    f"تقدير مخاطر انهيار: **{a['risk']}%**"
                )
        else:
            st.success("لا توجد إشارات Pump & Dump واضحة في الفترة الحالية.")

        st.subheader("سعر الإغلاق")
        st.line_chart(df["close"])

        col1, col2 = st.columns(2)

        with col1:
            with st.expander("بيانات يومية"):
                st.dataframe(df.round(2))

        with col2:
            with st.expander("إحصائيات"):
                st.dataframe(df.describe().round(2))

st.markdown("---")
st.caption("للأغراض التعليمية والبحثية فقط • غير نصيحة استثمارية")
