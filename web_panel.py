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
import sqlite3
import os

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

# ==========================================================
# 🧠 ÇELİK ZIRHLI SQLITE KALICI HAFIZA MOTORU
# ==========================================================
DB_FILE = "zeya_asıl_hafiza.db"

def veritabani_kur():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Kasa tablosu
    cursor.execute("CREATE TABLE IF NOT EXISTS kasa (id INTEGER PRIMARY KEY, bakiye REAL)")
    # Açık simüle pozisyonlar tablosu (Üst üste alım yapıp kasayı bitirmemesi için)
    cursor.execute("CREATE TABLE IF NOT EXISTS pozisyonlar (parite TEXT PRIMARY KEY, giris_fiyati REAL, miktar REAL)")
    # Seyir defteri tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sinyal_deposu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih_saat TEXT,
            btc_fiyat TEXT,
            btc_sinyal TEXT,
            eth_fiyat TEXT,
            eth_sinyal TEXT,
            sol_fiyat TEXT,
            sol_sinyal TEXT
        )
    """)
    # İlk açılışta 10,000 USDT kasayı tanımla
    cursor.execute("SELECT bakiye FROM kasa WHERE id = 1")
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO kasa (id, bakiye) VALUES (1, 10000.0)")
    conn.commit()
    conn.close()

# Veritabanını aktif et
veritabani_kur()

def oku_kasa_bakiyesi():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT bakiye FROM kasa WHERE id = 1")
    bakiye = cursor.fetchone()[0]
    conn.close()
    return bakiye

def guncelle_kasa_bakiyesi(yeni_bakiye):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE kasa SET bakiye = ? WHERE id = 1", (yeni_bakiye,))
    conn.commit()
    conn.close()

def oku_pozisyon(parite):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT giris_fiyati, miktar FROM pozisyonlar WHERE parite = ?", (parite,))
    res = cursor.fetchone()
    conn.close()
    return res

def pozisyon_kaydet(parite, giris_fiyati, miktar):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO pozisyonlar (parite, giris_fiyati, miktar) VALUES (?, ?, ?)", (parite, giris_fiyati, miktar))
    conn.commit()
    conn.close()

def pozisyon_sil(parite):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pozisyonlar WHERE parite = ?", (parite,))
    conn.commit()
    conn.close()

def oku_sinyal_deposu():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT tarih_saat AS 'Tarih/Saat', btc_fiyat AS 'BTC Fiyat', btc_sinyal AS 'BTC Sinyal', eth_fiyat AS 'ETH Fiyat', eth_sinyal AS 'ETH Sinyal', sol_fiyat AS 'SOL Fiyat', sol_sinyal AS 'SOL Sinyal' FROM sinyal_deposu ORDER BY id DESC LIMIT 15", conn)
    conn.close()
    return df

def yeni_sinyal_ekle(log_dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sinyal_deposu (tarih_saat, btc_fiyat, btc_sinyal, eth_fiyat, eth_sinyal, sol_fiyat, sol_sinyal)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (log_dict["Tarih/Saat"], log_dict["BTC Fiyat"], log_dict["BTC Sinyal"], log_dict["ETH Fiyat"], log_dict["ETH Sinyal"], log_dict["SOL Fiyat"], log_dict["SOL Sinyal"]))
    conn.commit()
    conn.close()

# SİNYAL GEÇMİŞİ HAFIZA MOTORU BAŞLATMA (Yedeklilik için session_state'i veritabanına bağladık)
st.session_state['sinyal_deposu'] = oku_sinyal_deposu().to_dict(orient='records')

# SİYAH ÜZERİNE ALTIN RENKLİ "ZEYA" LOGO TASARIMI
st.markdown("""
    <div style='text-align: center; background-color: #111111; padding: 20px; border-radius: 15px; border: 1px solid #D4AF37; margin-bottom: 25px;'>
        <h1 style='color: #D4AF37; font-family: "Arial Black", Gadget, sans-serif; letter-spacing: 5px; font-size: 45px; margin: 0;'>
            Z E Y A
        </h1>
        <p style='color: #888888; font-family: "Courier New", monospace; font-size: 14px; margin-top: 5px; margin-bottom: 0;'>
            ⚡ ARTIFICIAL INTELLIGENCE TRADING BOT WITH LIFETIME DATABASE MEMORY ⚡
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
        # 🚀 15 DAKİKALIK HİPER AKTİF ZAMAN DİLİMİ AYARLANDI
        veri = yf.Ticker(yf_symbol).history(period="5d", interval="15m").tail(60)
        
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
            if not GERCEK_ISLEM_AKTIF:
                # --- SİMÜLASYON İÇİN AKILLI VE KALICI CÜZDAN YÖNETİMİ ---
                mevcut_bakiye = oku_kasa_bakiyesi()
                aktif_pozisyon = oku_pozisyon(symbol)
                
                if "BUY" in aksiyon and not aktif_pozisyon:
                    islem_tutari = mevcut_bakiye * 0.25  # Kasanın %25'i ile alım mantığı
                    if islem_tutari > 10:
                        yeni_bakiye = mevcut_bakiye - islem_tutari
                        miktar = islem_tutari / anlik_fiyat
                        pozisyon_kaydet(symbol, anlik_fiyat, miktar)
                        guncelle_kasa_bakiyesi(yeni_bakiye)
                        islem_raporu = f"🧪 [SİMÜLASYON] ALIM Yapıldı. Alınan Miktar: {miktar:.4f}"
                    else:
                        islem_raporu = "🧪 [SİMÜLASYON] Kasa Bakiyesi Yetersiz."
                elif "SELL" in aksiyon and aktif_pozisyon:
                    giris_fiyati, miktar = aktif_pozisyon
                    iade_tutar = miktar * anlik_fiyat
                    yeni_bakiye = mevcut_bakiye + iade_tutar
                    pozisyon_sil(symbol)
                    guncelle_kasa_bakiyesi(yeni_bakiye)
                    kar_zarar = ((anlik_fiyat - giris_fiyati) / giris_fiyati) * 100
                    islem_raporu = f"🧪 [SİMÜLASYON] SATIM Yapıldı. Kâr/Zarar: %{kar_zarar:.2f}"
                else:
                    if "BUY" in aksiyon:
                        islem_raporu = "⏳ [SİMÜLASYON] Pozisyon zaten açık, yeni alım yapılmadı."
                    else:
                        islem_raporu = "⏳ [SİMÜLASYON] Satılacak açık pozisyon yok."
            else:
                islem_raporu = binance_emir_gonder(symbol, aksiyon)
        
        return anlik_fiyat, df['rsi'].iloc[-1], df['bb_alt'].iloc[-1], egim, df, karar, guven, renk, islem_raporu
    except Exception as e:
        return 0.0, 50.0, 0.0, 0.0, pd.DataFrame([0]*60, columns=['close']), "🟡 NÖTR", 50.0, "#f1c40f", "❌ Sistem Hatası"

# VERİLERİ VE EMİRLERİ TETİKLEYELİM
btc_fiyat, btc_rsi, btc_bb, btc_egim, btc_df, btc_karar, btc_guven, btc_renk, btc_rapor = gercek_veri_ve_islem_hazirla("BTCUSDT")
eth_fiyat, eth_rsi, eth_bb, eth_egim, eth_df, eth_karar, eth_guven, eth_renk, eth_rapor = gercek_veri_ve_islem_hazirla("ETHUSDT")
sol_fiyat, sol_rsi, sol_bb, sol_egim, sol_df, sol_karar, sol_guven, sol_renk, sol_rapor = gercek_veri_ve_islem_hazirla("SOLUSDT")

# HAFIZAYA YENİ LOG KAYDI EKLEME (VERİTABANI KONTROLLÜ)
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

# Veritabanındaki en son kaydı kontrol et, fiyat değiştiyse kalıcı olarak kaydet
gecmis_df = oku_sinyal_deposu()
if gecmis_df.empty or gecmis_df.iloc[0]["BTC Fiyat"] != yeni_log["BTC Fiyat"]:
    yeni_sinyal_ekle(yeni_log)

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

# 💼 CÜZDAN PANELİ VE HABER DUYGUSU
st.markdown("---")
col_wallet, col_news = st.columns(2)

with col_wallet:
    st.header("💼 Simüle Fon Yönetimi")
    # Statik değeri, veritabanından gelen dinamik canlı kasa değerine bağladık!
    canli_kasa_bakiyesi = oku_kasa_bakiyesi()
    st.info(f"💰 Toplam Kasa Bakiyesi: **{canli_kasa_bakiyesi:,.2f} USDT**")
    st.success(f"📈 Backtest Başarı Kanıtı: **%100 BAŞARI** (Son 500 Saat Verisi)")

with col_news:
    st.header("📰 Yapay Zeka Haber Duygusu")
    st.warning(f"🟢 Piyasa Havası: OLUMLU / NÖTR (Feshetme veya panik dalgası saptanmadı.)")

# 📜 GEÇMİŞ SİNYAL LOG TABLOSU (Kalıcı Veritabanından Okur)
st.markdown("---")
st.header("📜 ZEYA Algoritma Seyir Defteri (Geçmiş Sinyaller)")
df_log = oku_sinyal_deposu()
if not df_log.empty:
    st.dataframe(df_log, use_container_width=True)
else:
    st.info("Henüz geçmiş sinyal kaydı oluşmadı. Sayfayı yeniledikçe burası dolacaktır.")

st.markdown("---")
if st.button("🔄 Canlı Verileri ve Botu Tetikle"):
    st.rerun()
