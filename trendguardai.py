# app.py أو trendguardai.py
# TrendGuardAI - نسخة كاملة جاهزة للنشر على Streamlit Cloud

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from polygon import RESTClient
from pycoingecko import CoinGeckoAPI
import os

# =============================================
# إعدادات الصفحة
# =============================================
st.set_page_config(
    page_title="TrendGuardAI - حارس الترندات",
    page_icon="🛡️",
    layout="wide"
)

# جلب مفتاح Polygon من Secrets
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")

# =============================================
# الدوال المساعدة
# =============================================

@st.cache_data(ttl=300)
def get_polygon_data(ticker_input: str, days: int = 7):
    if not POLYGON_API_KEY:
        raise ValueError("مفتاح Polygon مفقود")
    
    client = RESTClient(api_key=POLYGON_API_KEY)
    
    # تحويل الرمز إلى تنسيق Polygon
    ticker = ticker_input.upper().strip()
    if ticker.endswith('-USD'):
        base = ticker.replace('-USD', '')
        ticker_formatted = f"X:{base}USD"
    else:
        ticker_formatted = ticker
    
    from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    to_date = datetime.now().strftime('%Y-%m-%d')
    
    aggs = client.get_aggs(ticker_formatted, 1, "day", from_date, to_date)
    if not aggs:
        raise ValueError("لا توجد بيانات من Polygon")
    
    df = pd.DataFrame(aggs)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df[['open', 'high', 'low', 'close', 'volume']]

@st.cache_data(ttl=300)
def get_coingecko_data(ticker_input: str, days: int = 7):
    cg = CoinGeckoAPI()
    
    # تحويل الرمز إلى coin_id
    clean = ticker_input.strip().upper().replace('-USD', '').replace('-', '')
    coin_map = {
        'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana', 'ADA': 'cardano',
        'XRP': 'ripple', 'DOGE': 'dogecoin', 'BNB': 'binancecoin', 'USDT': 'tether',
        'USDC': 'usd-coin', 'AVAX': 'avalanche-2', 'DOT': 'polkadot', 'MATIC': 'polygon'
    }
    coin_id = coin_map.get(clean, clean.lower())
    
    data = cg.get_coin_market_chart_by_id(id=coin_id, vs_currency='usd', days=days)
    if 'prices' not in data or not data['prices']:
        raise ValueError(f"العملة '{coin_id}' غير موجودة في CoinGecko")
    
    prices = pd.DataFrame(data['prices'], columns=['timestamp', 'price'])
    volumes = pd.DataFrame(data['total_volumes'], columns=['timestamp', 'volume'])
    prices['timestamp'] = pd.to_datetime(prices['timestamp'], unit='ms')
    volumes['timestamp'] = pd.to_datetime(volumes['timestamp'], unit='ms')
    
    df = pd.merge(prices, volumes, on='timestamp').set_index('timestamp')
    df['close'] = df['price']
    df['open'] = df['close'].shift(1).fillna(df['close'])
    df['high'] = df['close'].cummax()
    df['low'] = df['close'].cummin()
    return df[['open', 'high', 'low', 'close', 'volume']]

def analyze_trend(data):
    df = data.copy()
    df['price_change_%'] = df['close'].pct_change() * 100
    df['volume_change_%'] = df['volume'].pct_change() * 100
    
    # كشف Pump & Dump
    pump_signals = (df['price_change_%'] > 5) & (df['volume_change_%'] > 300)
    volatility = df['price_change_%'].std()
    dump_risk = min(99, int(volatility * 12))
    
    alerts = []
    for idx, row in df[pump_signals].iterrows():
        alerts.append({
            'date': idx.strftime('%Y-%m-%d'),
            'risk': dump_risk,
            'price_change': row['price_change_%'],
            'volume_change': row['volume_change_%']
        })
    return alerts, df

# =============================================
# الواجهة الرئيسية
# =============================================

st.title("🛡️ TrendGuardAI")
st.markdown("### حارس الترندات المالية – يكشف Pump & Dump و FOMO قبل وقوعه")

col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    ticker = st.text_input(
        "رمز الأصل",
        value="BTC-USD",
        placeholder="مثال: BTC-USD, ETH-USD, AAPL, TSLA"
    )

with col2:
    provider = st.selectbox(
        "مصدر البيانات",
        options=["تلقائي", "Polygon.io", "CoinGecko"],
        help="تلقائي = يختار الأفضل تلقائيًا"
    )

with col3:
    days = st.slider("عدد الأيام", 3, 30, 7)

if st.button("🚀 تحليل الآن", type="primary", use_container_width=True):
    if not ticker.strip():
        st.error("أدخل رمز الأصل أولاً")
    else:
        with st.spinner("جاري جلب البيانات..."):
            data = None
            source = "غير معروف"

            # اختيار المزود
            if provider in ["تلقائي", "Polygon.io"] and POLYGON_API_KEY:
                try:
                    data = get_polygon_data(ticker, days)
                    source = "Polygon.io"
                except Exception as e:
                    st.warning(f"Polygon فشل: {str(e)}")
                    if provider == "Polygon.io":
                        st.stop()

            if data is None and provider in ["تلقائي", "CoinGecko"]:
                try:
                    data = get_coingecko_data(ticker, days)
                    source = "CoinGecko"
                except Exception as e:
                    st.error(f"CoinGecko فشل: {str(e)}")
                    st.stop()

            if data is not None:
                st.success(f"تم جلب البيانات من {source} – {len(data)} يوم")

                alerts, analyzed = analyze_trend(data)

                if alerts:
                    st.error(f"⚠️ تم اكتشاف {len(alerts)} إشارة Pump & Dump مشبوهة!")
                    for a in alerts:
                        st.warning(f"**{a['date']}** → احتمال انهيار {a['risk']}% خلال 48 ساعة\n"
                                 f"📈 السعر: +{a['price_change']:.1f}% | 📊 الحجم: +{a['volume_change']:.0f}%")
                else:
                    st.success("✅ لا إشارات مشبوهة – الترند يبدو طبيعيًا")

                st.subheader("📊 رسم بياني للسعر")
                st.line_chart(analyzed['close'], use_container_width=True)

                col_a, col_b = st.columns(2)
                with col_a:
                    st.subheader("📈 التغييرات اليومية")
                    st.dataframe(analyzed[['close', 'price_change_%', 'volume_change_%']].round(2))

                with col_b:
                    st.subheader("📋 الإحصاءات")
                    st.dataframe(analyzed.describe().round(2))

else:
    st.info("أدخل رمز الأصل واختر المزود ثم اضغط تحليل")

st.markdown("---")
st.caption("تحذير: هذه الأداة لأغراض تعليمية فقط – لا تعتبر نصيحة مالية")
