# TrendGuardAI - أداة لتحليل ترندات الأسواق وكشف Pump & Dump
# License: MIT License
# Copyright (c) 2026 Mohannad

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from polygon import RESTClient
from pycoingecko import CoinGeckoAPI
import streamlit as st
from datetime import datetime, timedelta
import os

# =============================================
# إعدادات Streamlit
# =============================================
st.set_page_config(
    page_title="TrendGuardAI - حارس الترندات المالية",
    page_icon="🛡️",
    layout="wide"
)

# جلب API Key من Secrets (أفضل ممارسة في Streamlit Cloud)
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")

if not POLYGON_API_KEY:
    st.error("لم يتم العثور على مفتاح POLYGON_API_KEY.\nأضفه في: Manage app → Secrets → POLYGON_API_KEY = pk_...")
    st.stop()

# =============================================
# الدوال المساعدة
# =============================================

@st.cache_data(ttl=300)  # cache لمدة 5 دقائق
def get_polygon_data(ticker, days=7):
    client = RESTClient(api_key=POLYGON_API_KEY)
    from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    to_date = datetime.now().strftime('%Y-%m-%d')
    aggs = client.get_aggs(ticker, 1, "day", from_date, to_date)
    if not aggs:
        raise ValueError("لا توجد بيانات من Polygon لهذا الرمز")
    data = pd.DataFrame(aggs)
    data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
    data.set_index('timestamp', inplace=True)
    return data[['open', 'high', 'low', 'close', 'volume']]


@st.cache_data(ttl=300)
def get_coingecko_data(coin_id, days=7):
    cg = CoinGeckoAPI()
    data = cg.get_coin_market_chart_by_id(id=coin_id, vs_currency='usd', days=days)
    prices = pd.DataFrame(data['prices'], columns=['timestamp', 'price'])
    volumes = pd.DataFrame(data['total_volumes'], columns=['timestamp', 'volume'])
    prices['timestamp'] = pd.to_datetime(prices['timestamp'], unit='ms')
    volumes['timestamp'] = pd.to_datetime(volumes['timestamp'], unit='ms')
    df = pd.merge(prices, volumes, on='timestamp').set_index('timestamp')
    df['close'] = df['price']
    return df[['close', 'volume']]


def analyze_trend(data):
    data = data.copy()
    data['price_change'] = data['close'].pct_change() * 100
    data['volume_change'] = data['volume'].pct_change() * 100

    # كشف Pump مشبوه: سعر +5% وحجم +300% في يوم واحد
    pump_signals = (data['price_change'] > 5) & (data['volume_change'] > 300)

    volatility = data['price_change'].std()
    dump_prob = min(100, volatility * 10)  # نموذج بسيط جدًا

    alerts = []
    for idx, row in data[pump_signals].iterrows():
        alert = f"ترند مشبوه – احتمال انهيار {int(dump_prob)}% خلال 48 ساعة"
        alerts.append((idx, alert, row['price_change'], row['volume_change']))

    return alerts, data


# =============================================
# الواجهة الرئيسية
# =============================================

st.title("🛡️ TrendGuardAI")
st.markdown("**حارس الترندات المالية** – كشف Pump & Dump و FOMO في الأسهم والكريبتو")

st.info("الأداة تستخدم بيانات يومية من Polygon.io و CoinGecko. ليست نصيحة استثمارية – استخدمها للتحليل فقط.")

# ------------------------------
# إدخال المستخدم
# ------------------------------
col1, col2 = st.columns([3, 1])

with col1:
    ticker = st.text_input(
        "أدخل رمز الأصل",
        value="BTC-USD",
        placeholder="مثال: AAPL, TSLA, BTC-USD, ETH-USD, XAUUSD",
        help="للكريبتو استخدم -USD في النهاية مثل BTC-USD"
    )

with col2:
    days = st.slider("عدد الأيام للتحليل", 3, 30, 7)

# زر للتشغيل (اختياري – يمكن جعلها auto-run)
if st.button("تحليل الآن", type="primary", use_container_width=True) or ticker:
    if not ticker.strip():
        st.warning("أدخل رمز الأصل أولاً")
    else:
        with st.spinner("جاري جلب البيانات وتحليلها..."):
            data = None
            source = None

            # محاولة Polygon أولاً
            try:
                data = get_polygon_data(ticker, days)
                source = "Polygon.io"
            except Exception as e:
                st.warning(f"Polygon.io: {str(e)}")

            # إذا فشل → CoinGecko (للكريبتو بشكل أساسي)
            if data is None:
                try:
                    coin_id = ticker.lower().replace('-usd', '')
                    data = get_coingecko_data(coin_id, days)
                    source = "CoinGecko"
                except Exception as e:
                    st.error(f"فشل جلب البيانات من CoinGecko: {str(e)}")
                    st.stop()

            if data is not None:
                st.success(f"تم جلب البيانات بنجاح من {source} ({len(data)} يوم)")

                alerts, analyzed = analyze_trend(data)

                # عرض التنبيهات
                if alerts:
                    st.subheader("⚠️ تنبيهات مشبوهة")
                    for date, alert, p_change, v_change in alerts:
                        st.warning(f"**{date.strftime('%Y-%m-%d')}**  \n{alert}  \n(تغيير السعر: +{p_change:.1f}%, تغيير الحجم: +{v_change:.0f}%)")
                else:
                    st.success("لا توجد إشارات Pump & Dump مشبوهة في الفترة الحالية.")

                # الرسم البياني
                st.subheader("سعر الإغلاق")
                st.line_chart(analyzed['close'])

                # جدول الإحصاءات
                with st.expander("إحصاءات مفصلة"):
                    st.dataframe(analyzed.describe().round(2))

                # عرض البيانات الخام (اختياري)
                with st.expander("البيانات الخام"):
                    st.dataframe(analyzed.round(2))

else:
    st.info("أدخل رمز الأصل لبدء التحليل")
