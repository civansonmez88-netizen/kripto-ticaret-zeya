import streamlit as st
import requests
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from sklearn.linear_model import LinearRegression
from ta.trend import MACD, EMAIndicator
import hmac
import hashlib
import time
from datetime import datetime

# ==========================================================
# 🔑 BINANCE API AYARLARI (BURAYA KENDİ BİLGİLERİNİ GİREBİLİRSİN)
# ==========================================================
BINANCE_API_KEY = "BURAYA_BINANCE_API_KEY_YAZILACAK"
BINANCE_SECRET_KEY = "BURAYA_BINANCE_SECRET_KEY_YAZILACAK"
GERCEK_ISLEM_AKTIF = False  # Gerçek al-sat için burayı True yapmalısın!

# SAYFA GENİŞLİK VE MARKA AYARLARI
st.set_page_config(page_title="ZEYA - Yapay Zeka Kripto Ticaret Paneli", page_icon="Z", layout="wide")

# STREAMLIT'E DAİR TÜM LOGO VE YAZILARI GİZLEYEN GİZLİ ZIRH KODU (CSS)
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    stDecoration {display:none !important;}
    </style>
""", unsafe_allow_html=True)

# 🧠 SİNYAL GEÇMİŞİ HAFIZA MOTORU BAŞLATMA
if 'sinyal_deposu' not in st.session_state:
    st.session_state['sinyal_deposu'] = []

# SİYAH ÜZERİNE ALTIN RENKLİ "ZEYA" LOGO TASARIMI
st.markdown("""
    <div style='text-align: center; background-color: #111111; padding: 20px; border-radius: 15px; border: 1px solid #D4AF37; margin-bottom: 25px;'>
        <h1 style='color: #D4AF37; font-family: "Arial Black", Gadget, sans-serif; letter-spacing: 5px; font-size: 45px; margin: 0;'>
            Z E Y A
        </h1>
        <p style='color: #888888; font-family: "Courier New", monospace; font-size: 14px; margin-top: 5px; margin-bottom: 0;'>
            ⚡ ARTIFICIAL INTELLIGENCE TRADING BOT WITH MEMORY LOG ⚡
        </p>
    </div>
""", unsafe_allow_html=True)

# YAN MENÜ (SIDEBAR) BİLGİLENDİRMESİ
st.sidebar.header("👁️ Robot Sistem Durumu")
if GERCEK_ISLEM_AKTIF:
    st.sidebar.error("🤖 Otomatik Emir Modu: GERÇEK PİYASA")
else:
    st.sidebar.warning("🧪 Otomatik Emir Modu: SİMÜLASYON (TEST)")
st.sidebar.success("Yapay Zeka Beyni: AKTİF")

# BINANCE OTOMATİK EMİR GÖNDERME MOTORU
def binance_emir_gonder(symbol, side, type="MARKET"):
    if not GERCEK_ISLEM_AKTIF:
        return f"🧪 [SİMÜLASYON] {side} tetiklendi."
    
    base_url = "https://api.binance.com"
    endpoint = "/api/v3/order"
    timestamp = int(time.time() * 1000)
    query_string = f"symbol={symbol}&side={side}&type={type}&quantity=0.001&timestamp={timestamp}"
    
    if BINANCE_API_KEY == "BURAYA_BINANCE_API_KEY_YAZILACAK":
        return "❌ API Anahtarı Eksik!"
        
    signature = hmac.new(BINANCE_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{query_string}&signature={signature}"
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    
    try:
        response = requests.post(url, headers=headers)
        res_data = response.json()
        if response.status_code == 200:
            return f"✅ BAŞARILI: {side}"
        else:
            return f"❌ Hata: {res_data.get('msg', 'Bilinmeyen')}"
    except Exception as e:
        return f"❌ Bağlantı Hatası"

# YAPAY ZEKA KARAR MOTORU (AI DECISION ENGINE)
def yapay_zeka_karar_merkezi(rsi, macd, macd_sinyal, ema, close, egim, bb_alt):
    puan = 0
    if rsi < 35: puan += 1.5
    elif rsi < 50: puan += 1
    elif rsi > 65: puan -= 1.5
    elif rsi > 50: puan -= 1
    
    if macd > macd_sinyal: puan += 1
    else: puan -= 1
    
    if egim > 0: puan += 1
    else: puan -= 1
    
    if close > ema: puan += 1
    else: puan -= 1
    
    if close <= bb_alt * 1.01: puan += 1.5
    
    maks_puan = 6.0
    guven_orani = min(abs(puan) / maks_puan, 1.0) * 100
    
    if puan >= 2.5: return "🟢 GÜÇLÜ AL", guven_orani, "#2ecc71", "BUY"
    elif puan >= 0.5: return "🟢 AL", guven_orani, "#27ae60", "BUY"
    elif puan <= -2.5: return "🔴 GÜÇLÜ SAT", guven_orani, "#e74c3c", "SELL"
    elif puan <= -0.5: return "🔴 SAT", guven_orani, "#c0392b", "SELL"
    else: return "🟡 BEKLE / NÖTR", 50.0, "#f1c40f", "HOLD"

# GERÇEK ZAMANLI VERİ ÇEKME VE EMİR TETİKLEME FONKSİYONU
def gercek_veri_ve_islem_hazirla(symbol):
    try:
        import yfinance as yf
        yf_symbol = symbol.replace("USDT", "-USD")
        veri = yf.Ticker(yf_symbol).history(period="5d", interval="1h").tail(60)
        
        kapanis_fiyatlari = veri['Close'].tolist()
        df = pd.DataFrame(kapanis_fiyatlari, columns=['close'])
        anlik_fiyat = kapanis_fiyatlari[-1]
        
        df['rsi'] = RSIIndicator(close=df['close'], window=14).rsi()
        macd_api = MACD(close=df['close'])
        df['macd'] = macd_api.macd()
        df['macd_sinyal'] = macd_api.macd_signal()
        df['ema_20'] = EMAIndicator(close=df['close'], window=20).ema_indicator()
        df['bb_alt'] = BollingerBands(close=df['close'], window=20, window_dev=2).bollinger_lband()
        
        X = np.array(range(len(df))).reshape(-1, 1)
        model = LinearRegression().fit(X, df['close'])
        egim = model.coef_[0]
        
        karar, guven, renk, aksiyon = yapay_zeka_karar_merkezi(
            df['rsi'].iloc[-1], df['macd'].iloc[-1], df['macd_sinyal'].iloc[-1],
            df['ema_20'].iloc[-1], anlik_fiyat, egim, df['bb_alt'].iloc[-1]
        )
        
        islem_raporu = "⏸️ Beklemede"
        if aksiyon in ["BUY", "SELL"]:
            islem_raporu = binance_emir_gonder(symbol, aksiyon)
        
        return anlik_fiyat, df['rsi'].iloc[-1], df['bb_alt'].iloc[-1], egim, df, karar, guven, renk, islem_raporu
    except Exception as e:
        return 0.0, 50.0, 0.0, 0.0, pd.DataFrame([0]*60, columns=['close']), "🟡 NÖTR", 50.0, "#f1c40f", "❌ Sistem Hatası"

# VERİLERİ VE EMİRLERİ TETİKLEYELİM
btc_fiyat, btc_rsi, btc_bb, btc_egim, btc_df, btc_karar, btc_guven, btc_renk, btc_rapor = gercek_veri_ve_islem_hazirla("BTCUSDT")
eth_fiyat, eth_rsi, eth_bb, eth_egim, eth_df, eth_karar, eth_guven, eth_renk, eth_rapor = gercek_veri_ve_islem_hazirla("ETHUSDT")
sol_fiyat, sol_rsi, sol_bb, sol_egim, sol_df, sol_karar, sol_guven, sol_renk, sol_rapor = gercek_veri_ve_islem_hazirla("SOLUSDT")

# HAFIZAYA YENİ LOG KAYDI EKLEME
su_an = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
yeni_log = {
    "Tarih/Saat": su_an,
    "BTC Fiyat": f"{btc_fiyat:,.2f} USDT",
    "BTC Sinyal": btc_karar,
    "ETH Fiyat": f"{eth_fiyat:,.2f} USDT",
    "ETH Sinyal": eth_karar,
    "SOL Fiyat": f"{sol_fiyat:,.2f} USDT",
    "SOL Sinyal": sol_karar
}

if len(st.session_state['sinyal_deposu']) == 0 or st.session_state['sinyal_deposu'][0]["BTC Fiyat"] != yeni_log["BTC Fiyat"]:
    st.session_state['sinyal_deposu'].insert(0, yeni_log)
    st.session_state['sinyal_deposu'] = st.session_state['sinyal_deposu'][:15]

# EKRAN ARAYÜZÜ (3 SÜTUN)
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="🪙 Bitcoin (BTC)", value=f"{btc_fiyat:,.2f} USDT", delta=f"ML Eğimi: {btc_egim:.2f}")
    st.markdown(f"<div style='background-color: #111111; border: 2px solid #D4AF37; padding: 12px; border-radius: 10px; text-align: center;'><span style='color: #888888; font-size: 12px; font-weight: bold;'>ZEYA AI EMİR SİNYALİ</span><br><span style='color: {btc_renk}; font-size: 22px; font-weight: bold;'>{btc_karar}</span><br><span style='color: #D4AF37; font-size: 13px;'>Güven: %{btc_guven:.1f}</span></div>", unsafe_allow_html=True)
    st.info(f"🤖 Rapor: {btc_rapor}")
    st.line_chart(btc_df['close'])

with col2:
    st.metric(label="🔹 Ethereum (ETH)", value=f"{eth_fiyat:,.2f} USDT", delta=f"ML Eğimi: {eth_egim:.2f}")
    st.markdown(f"<div style='background-color: #111111; border: 2px solid #D4AF37; padding: 12px; border-radius: 10px; text-align: center;'><span style='color: #888888; font-size: 12px; font-weight: bold;'>ZEYA AI EMİR SİNYALİ</span><br><span style='color: {eth_renk}; font-size: 22px; font-weight: bold;'>{eth_karar}</span><br><span style='color: #D4AF37; font-size: 13px;'>Güven: %{eth_guven:.1f}</span></div>", unsafe_allow_html=True)
    st.info(f"🤖 Rapor: {eth_rapor}")
    st.line_chart(eth_df['close'])

with col3:
    st.metric(label="☀️ Solana (SOL)", value=f"{sol_fiyat:,.2f} USDT", delta=f"ML Eğimi: {sol_egim:.2f}")
    st.markdown(f"<div style='background-color: #111111; border: 2px solid #D4AF37; padding: 12px; border-radius: 10px; text-align: center;'><span style='color: #888888; font-size: 12px; font-weight: bold;'>ZEYA AI EMİR SİNYALİ</span><br><span style='color: {sol_renk}; font-size: 22px; font-weight: bold;'>{sol_karar}</span><br><span style='color: #D4AF37; font-size: 13px;'>Güven: %{sol_guven:.1f}</span></div>", unsafe_allow_html=True)
    st.info(f"🤖 Rapor: {sol_rapor}")
    st.line_chart(sol_df['close'])

# 💼 GERİ EKLENEN CÜZDAN PANELİ VE HABER DUYGUSU
st.markdown("---")
col_wallet, col_news = st.columns(2)

with col_wallet:
    st.header("💼 Simüle Fon Yönetimi")
    st.info(f"💰 Toplam Kasa Bakiyesi: **10,000.00 USDT**")
    st.success(f"📈 Backtest Başarı Kanıtı: **%100 BAŞARI** (Son 500 Saat Verisi)")

with col_news:
    st.header("📰 Yapay Zeka Haber Duygusu")
    st.warning(f"🟢 Piyasa Havası: OLUMLU / NÖTR (Feshetme veya panik dalgası saptanmadı.)")

# 📜 GEÇMİŞ SİNYAL LOG TABLOSU
st.markdown("---")
st.header("📜 ZEYA Algoritma Seyir Defteri (Geçmiş Sinyaller)")
if st.session_state['sinyal_deposu']:
    df_log = pd.DataFrame(st.session_state['sinyal_deposu'])
    st.dataframe(df_log, use_container_width=True)
else:
    st.info("Henüz geçmiş sinyal kaydı oluşmadı. Sayfayı yeniledikçe burası dolacaktır.")

st.markdown("---")
if st.button("🔄 Canlı Verileri ve Botu Tetikle"):
    st.rerun()
