# TrendGuardAI - أداة لتحليل ترندات الأسواق وكشف Pump & Dump
# License: MIT License (يمكنك بيع نسخ معدلة أو خدمات، لكن احتفظ بحقوقي الأصلية)
# MIT License: Copyright (c) 2026 Mohannad. Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following
# conditions: The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from polygon import RESTClient  # للأسهم والكريبتو
from pycoingecko import CoinGeckoAPI  # للكريبتو
import streamlit as st  # للواجهة الويب
from datetime import datetime, timedelta
import smtplib  # لإرسال إيميل تنبيهات (اختياري)

# استبدل بـ API Keys الخاصة بك
POLYGON_API_KEY = 'BdLG7nJ0a7DtZPvAvJxYSpuIfjlB4kxt'
COINGECKO = CoinGeckoAPI()

# دالة لجلب بيانات من Polygon (أسهم/كريبتو/سلع)
def get_polygon_data(ticker, days=7):
    client = RESTClient(api_key=POLYGON_API_KEY)
    from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    to_date = datetime.now().strftime('%Y-%m-%d')
    aggs = client.get_aggs(ticker, 1, 'day', from_date, to_date)
    data = pd.DataFrame(aggs)
    data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
    data.set_index('timestamp', inplace=True)
    return data[['open', 'high', 'low', 'close', 'volume']]

# دالة لجلب بيانات كريبتو من CoinGecko (إذا فشل Polygon)
def get_coingecko_data(coin_id, days=7):
    data = COINGECKO.get_coin_market_chart_by_id(id=coin_id, vs_currency='usd', days=days)
    prices = pd.DataFrame(data['prices'], columns=['timestamp', 'price'])
    volumes = pd.DataFrame(data['total_volumes'], columns=['timestamp', 'volume'])
    prices['timestamp'] = pd.to_datetime(prices['timestamp'], unit='ms')
    volumes['timestamp'] = pd.to_datetime(volumes['timestamp'], unit='ms')
    df = pd.merge(prices, volumes, on='timestamp').set_index('timestamp')
    df['close'] = df['price']
    return df[['close', 'volume']]

# دالة تحليل وكشف Pump & Dump
def analyze_trend(data):
    # حساب التغييرات اليومية
    data['price_change'] = data['close'].pct_change() * 100
    data['volume_change'] = data['volume'].pct_change() * 100
    
    # كشف Pump: زيادة سعر > 5% وزيادة حجم > 300% في يوم واحد
    pump_signals = (data['price_change'] > 5) & (data['volume_change'] > 300)
    
    # احتمال انهيار: بناءً على انحراف معياري (إذا كان عالياً، احتمال انهيار أعلى)
    volatility = data['price_change'].std()
    dump_prob = min(100, volatility * 10)  # نموذج بسيط، يمكن تحسينه بـ ML
    
    alerts = []
    for idx, row in data[pump_signals].iterrows():
        alert = f"هذا الترند مشبوه – احتمال انهيار {int(dump_prob)}% خلال 48 ساعة"
        alerts.append((idx, alert))
    
    return alerts, data

# دالة لإرسال إيميل تنبيه (اختياري)
def send_email_alert(alert, email_to='your_email@example.com'):
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login('your_gmail@gmail.com', 'your_password')
    server.sendmail('trendguardai@gmail.com', email_to, alert)
    server.quit()

# واجهة CLI البسيطة (للتشغيل بدون Streamlit)
def cli_mode():
    ticker = input("أدخل رمز الأصل (مثل AAPL أو BTC-USD): ")
    try:
        data = get_polygon_data(ticker)
    except:
        data = get_coingecko_data(ticker.lower().replace('-usd', ''), days=7)  # للكريبتو
    alerts, analyzed_data = analyze_trend(data)
    
    print("التنبيهات:")
    for date, alert in alerts:
        print(f"{date}: {alert}")
    
    # رسم بياني
    analyzed_data['close'].plot(title='سعر الإغلاق')
    plt.show()

# واجهة Streamlit للعرض على الإنترنت
if __name__ == "__main__":
    if 'streamlit' in globals():
        st.title("TrendGuardAI: حارس الترندات المالية")
        ticker = st.text_input("أدخل رمز الأصل (مثل AAPL أو BTC-USD)")
        if ticker:
            try:
                data = get_polygon_data(ticker)
            except:
                data = get_coingecko_data(ticker.lower().replace('-usd', ''), days=7)
            alerts, analyzed_data = analyze_trend(data)
            
            st.write("التنبيهات:")
            for date, alert in alerts:
                st.warning(alert)
                # send_email_alert(alert)  # فعل هذا للإيميل
            
            st.line_chart(analyzed_data['close'], use_container_width=True)
            st.write(analyzed_data.describe())  # إحصاءات
    else:
        cli_mode()
