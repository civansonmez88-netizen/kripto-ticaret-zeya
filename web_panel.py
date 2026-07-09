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
import threading
import os

# ==========================================================
# BINANCE API AYARLARI (GÜVENLİ YÖNTEM: st.secrets / ortam değişkeni)
# ==========================================================
def _anahtar_oku(isim):
    try:
        return st.secrets[isim]
    except Exception:
        return os.environ.get(isim, "")

BINANCE_API_KEY = _anahtar_oku("BINANCE_API_KEY")
BINANCE_SECRET_KEY = _anahtar_oku("BINANCE_SECRET_KEY")
GERCEK_ISLEM_AKTIF = False  # Gerçek al-sat için burayı True yapmalısın!

# SAYFA GENİŞLİK VE MARKA AYARLARI
st.set_page_config(page_title="ZEYA - Yapay Zeka Kripto Ticaret Paneli", page_icon="Z", layout="wide")

# STREAMLIT LOGOLARINI GİZLEME KODU
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    stDecoration {display:none !important;}
    </style>
""", unsafe_allow_html=True)

# ==========================================================
# ÇELİK ZIRHLI SQLITE KALICI HAFIZA MOTORU
# ==========================================================
DB_FILE = "zeya_asıl_hafiza.db"

def veritabani_kur():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS kasa (id INTEGER PRIMARY KEY, bakiye REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS pozisyonlar (parite TEXT PRIMARY KEY, giris_fiyati REAL, miktar REAL)")
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
    cursor.execute("SELECT bakiye FROM kasa WHERE id = 1")
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO kasa (id, bakiye) VALUES (1, 10000.0)")
    conn.commit()
    conn.close()

veritabani_kur()

def oku_kasa_bakiyesi():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT bakiye FROM kasa WHERE id = 1")
    res = cursor.fetchone()
    bakiye = res[0] if res else 10000.0
    conn.close()
    return bakiye

def guncelle_kasa_bakiyesi(yeni_bakiye):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE kasa SET bakiye = ? WHERE id = 1", (yeni_bakiye,))
    conn.commit()
    conn.close()

def oku_pozisyon(parite):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT giris_fiyati, miktar FROM pozisyonlar WHERE parite = ?", (parite,))
    res = cursor.fetchone()
    conn.close()
    return res

def pozisyon_kaydet(parite, giris_fiyati, miktar):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO pozisyonlar (parite, giris_fiyati, miktar) VALUES (?, ?, ?)", (parite, giris_fiyati, miktar))
    conn.commit()
    conn.close()

def pozisyon_sil(parite):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pozisyonlar WHERE parite = ?", (parite,))
    conn.commit()
    conn.close()

def oku_sinyal_deposu():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    df = pd.read_sql_query("SELECT tarih_saat AS 'Tarih/Saat', btc_fiyat AS 'BTC Fiyat', btc_sinyal AS 'BTC Sinyal', eth_fiyat AS 'ETH Fiyat', eth_sinyal AS 'ETH Sinyal', sol_fiyat AS 'SOL Fiyat', sol_sinyal AS 'SOL Sinyal' FROM sinyal_deposu ORDER BY id DESC LIMIT 15", conn)
    conn.close()
    return df

def yeni_sinyal_ekle(log_dict):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sinyal_deposu (tarih_saat, btc_fiyat, btc_sinyal, eth_fiyat, eth_sinyal, sol_fiyat, sol_sinyal)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (log_dict["Tarih/Saat"], log_dict["BTC Fiyat"], log_dict["BTC Sinyal"], log_dict["ETH Fiyat"], log_dict["ETH Sinyal"], log_dict["SOL Fiyat"], log_dict["SOL Sinyal"]))
    conn.commit()
    conn.close()

# ==========================================================
# BOT ALGORİTMİK MANTIĞI VE EMİR MOTORU
# ==========================================================

def binance_emir_gonder(symbol, side, type="MARKET"):
    if not GERCEK_ISLEM_AKTIF:
        return f"[SIMULASYON] {side} tetiklendi."
    base_url = "https://api.binance.com"
    endpoint = "/api/v3/order"
    timestamp = int(time.time() * 1000)
    query_string = f"symbol={symbol}&side={side}&type={type}&quantity=0.001&timestamp={timestamp}"
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return "Hata: API Anahtarı Eksik! (.streamlit/secrets.toml dosyasını kontrol et)"
    signature = hmac.new(BINANCE_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{query_string}&signature={signature}"
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    try:
        response = requests.post(url, headers=headers)
        res_data = response.json()
        if response.status_code == 200:
            return f"BASARILI: {side}"
        else:
            return f"Hata: {res_data.get('msg', 'Bilinmeyen')}"
    except Exception as e:
        return f"Hata: Baglanti Hatasi"

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
    if puan >= 2.5: return "GUCLU AL", guven_orani, "#2ecc71", "BUY"
    elif puan >= 0.5: return "AL", guven_orani, "#27ae60", "BUY"
    elif puan <= -2.5: return "GUCLU SAT", guven_orani, "#e74c3c", "SELL"
    elif puan <= -0.5: return "SAT", guven_orani, "#c0392b", "SELL"
    else: return "BEKLE / NOTR", 50.0, "#f1c40f", "HOLD"

def analiz_ve_islem_yapi(symbol, emir_tetikle=False):
    try:
        import yfinance as yf
        yf_symbol = symbol.replace("USDT", "-USD")
        veri = yf.Ticker(yf_symbol).history(period="5d", interval="15m").tail(60)
        if veri.empty or len(veri) < 20:
            return 0.0, 50.0, pd.DataFrame([0]*60, columns=['close']), "NOTR", 50.0, "#f1c40f", "Veri Eksik", 0.0
            
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
        
        islem_raporu = "Beklemede"
        aktif_pozisyon = oku_pozisyon(symbol)
        
        if emir_tetikle:
            mevcut_bakiye = oku_kasa_bakiyesi()
            
            # 1. POZISYON VARSA RISK KONTROLU (TP / SL)
            if aktif_pozisyon:
                giris_fiyati, miktar = aktif_pozisyon
                anlik_kar_zarar_yuzde = ((anlik_fiyat - giris_fiyati) / giris_fiyati) * 100
                
                # TAKE PROFIT (%3 Kar Hedefi)
                if anlik_kar_zarar_yuzde >= 3.0:
                    iade_tutar = miktar * anlik_fiyat
                    pozisyon_sil(symbol)
                    guncelle_kasa_bakiyesi(mevcut_bakiye + iade_tutar)
                    islem_raporu = f"HEDEF GORULDU (TP): %{anlik_kar_zarar_yuzde:.2f} Karla Nakde Gecildi."
                    
                # STOP LOSS (%2 Zarar Siniri)
                elif anlik_kar_zarar_yuzde <= -2.0:
                    iade_tutar = miktar * anlik_fiyat
                    pozisyon_sil(symbol)
                    guncelle_kasa_bakiyesi(mevcut_bakiye + iade_tutar)
                    islem_raporu = f"ZARAR KESILDI (SL): %{anlik_kar_zarar_yuzde:.2f} Zararla Pozisyon Kapatildi."
                    
                # YAPAY ZEKA SAT SINYALI
                elif "SELL" in aksiyon:
                    iade_tutar = miktar * anlik_fiyat
                    pozisyon_sil(symbol)
                    guncelle_kasa_bakiyesi(mevcut_bakiye + iade_tutar)
                    islem_raporu = f"AI SATISI: Yapay Zeka Sinyaliyle %{anlik_kar_zarar_yuzde:.2f} Kar/Zararla Kapatildi."
                    
                else:
                    islem_raporu = f"Pozisyondasin. Guncel: %{anlik_kar_zarar_yuzde:.2f} (Giris: {giris_fiyati:,.2f})"

            # 2. POZISYON YOKSA YENI ALIM SINYALI
            elif "BUY" in aksiyon and not aktif_pozisyon:
                islem_tutari = mevcut_bakiye * 0.25
                if islem_tutari > 10:
                    yeni_bakiye = mevcut_bakiye - islem_tutari
                    miktar = islem_tutari / anlik_fiyat
                    pozisyon_kaydet(symbol, anlik_fiyat, miktar)
                    guncelle_kasa_bakiyesi(yeni_bakiye)
                    islem_raporu = f"AI ALIMI: Miktar: {miktar:.4f} (TP: %3, SL: %2 Set Edildi)"
        else:
            if aktif_pozisyon:
                islem_raporu = f"Pozisyon Acik (Giris: {aktif_pozisyon[0]:,.2f})"
        
        return anlik_fiyat, df['rsi'].iloc[-1], df, karar, guven, renk, islem_raporu, egim
    except Exception as e:
        return 0.0, 50.0, pd.DataFrame([0]*60, columns=['close']), "NOTR", 50.0, "#f1c40f", "Hata", 0.0

# ==========================================================
# GERÇEK BACKTEST MOTORU
# ==========================================================
@st.cache_data(ttl=3600)
def gercek_backtest_yap(symbol, gun_sayisi=30):
    try:
        import yfinance as yf
        yf_symbol = symbol.replace("USDT", "-USD")
        veri = yf.Ticker(yf_symbol).history(period=f"{gun_sayisi}d", interval="1h")
        if veri.empty or len(veri) < 60:
            return None

        df = pd.DataFrame(veri['Close'].tolist(), columns=['close'])
        df['rsi'] = RSIIndicator(close=df['close'], window=14).rsi()
        macd_api = MACD(close=df['close'])
        df['macd'] = macd_api.macd()
        df['macd_sinyal'] = macd_api.macd_signal()
        df['ema_20'] = EMAIndicator(close=df['close'], window=20).ema_indicator()
        df['bb_alt'] = BollingerBands(close=df['close'], window=20, window_dev=2).bollinger_lband()
        df = df.dropna().reset_index(drop=True)

        sanal_bakiye = 10000.0
        pozisyon_miktar = 0.0
        pozisyon_giris = 0.0
        islem_sayisi = 0
        kazanan_islem = 0
        toplam_deger_gecmisi = []

        for i in range(20, len(df)):
            pencere = df.iloc[max(0, i - 20):i + 1]
            X = np.array(range(len(pencere))).reshape(-1, 1)
            egim = LinearRegression().fit(X, pencere['close']).coef_[0]
            satir = df.iloc[i]

            karar, guven, renk, aksiyon = yapay_zeka_karar_merkezi(
                satir['rsi'], satir['macd'], satir['macd_sinyal'],
                satir['ema_20'], satir['close'], egim, satir['bb_alt']
            )

            if aksiyon == "BUY" and pozisyon_miktar == 0:
                islem_tutari = sanal_bakiye * 0.25
                if islem_tutari > 10:
                    pozisyon_miktar = islem_tutari / satir['close']
                    pozisyon_giris = satir['close']
                    sanal_bakiye -= islem_tutari
                    islem_sayisi += 1
            elif aksiyon == "SELL" and pozisyon_miktar > 0:
                satis_tutari = pozisyon_miktar * satir['close']
                sanal_bakiye += satis_tutari
                if satir['close'] > pozisyon_giris:
                    kazanan_islem += 1
                pozisyon_miktar = 0.0
                pozisyon_giris = 0.0

            guncelleme_degeri = sanal_bakiye + (pozisyon_miktar * satir['close'])
            toplam_deger_gecmisi.append(guncelleme_degeri)

        if pozisyon_miktar > 0:
            sanal_bakiye += pozisyon_miktar * df.iloc[-1]['close']

        if not toplam_deger_gecmisi:
            return None

        deger_serisi = pd.Series(toplam_deger_gecmisi)
        zirve = deger_serisi.cummax()
        dususler = (deger_serisi - zirve) / zirve
        maks_dusus = dususler.min() * 100

        toplam_getiri = ((sanal_bakiye - 10000.0) / 10000.0) * 100
        kazanma_orani = (kazanan_islem / islem_sayisi * 100) if islem_sayisi > 0 else 0.0

        return {
            "toplam_getiri_yuzde": toplam_getiri,
            "islem_sayisi": islem_sayisi,
            "kazanma_orani": kazanma_orani,
            "maks_dusus_yuzde": maks_dusus,
            "gun_sayisi": gun_sayisi,
        }
    except Exception as e:
        return None

# ==========================================================
# 7/24 BAĞIMSIZ ARKA PLAN MOTORU (AUTOMATED WORKER)
# ==========================================================
def kesintisiz_bot_dongusu():
    while True:
        try:
            btc_f, _, _, btc_k, _, _, _, _ = analiz_ve_islem_yapi("BTCUSDT", emir_tetikle=True)
            eth_f, _, _, eth_k, _, _, _, _ = analiz_ve_islem_yapi("ETHUSDT", emir_tetikle=True)
            sol_f, _, _, sol_k, _, _, _, _ = analiz_ve_islem_yapi("SOLUSDT", emir_tetikle=True)
            
            su_an = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            yeni_log = {
                "Tarih/Saat": su_an,
                "BTC Fiyat": f"{btc_f:,.2f} USDT",
                "BTC Sinyal": btc_k,
                "ETH Fiyat": f"{eth_f:,.2f} USDT",
                "ETH Sinyal": eth_k,
                "SOL Fiyat": f"{sol_f:,.2f} USDT",
                "SOL Sinyal": sol_k
            }
            
            conn = sqlite3.connect(DB_FILE, check_same_thread=False)
            gecmis = pd.read_sql_query("SELECT btc_fiyat FROM sinyal_deposu ORDER BY id DESC LIMIT 1", conn)
            conn.close()
            
            if btc_f > 0.0 and (gecmis.empty or gecmis.iloc[0]["btc_fiyat"] != yeni_log["BTC Fiyat"]):
                yeni_sinyal_ekle(yeni_log)
                
        except Exception as e:
            print(f"Arkaplan Bot Hatasi: {e}")
            
        time.sleep(900)

@st.cache_resource
def arkaplan_motorunu_atesle():
    t = threading.Thread(target=kesintisiz_bot_dongusu, daemon=True)
    t.start()
    return True

arkaplan_motorunu_atesle()

# ==========================================================
# ÖN YÜZ GÖSTERİM PANELİ (STREAMLIT UI)
# ==========================================================

btc_fiyat, btc_rsi, btc_df, btc_karar, btc_guven, btc_renk, btc_rapor, btc_egim = analiz_ve_islem_yapi("BTCUSDT", emir_tetikle=False)
eth_fiyat, eth_rsi, eth_df, eth_karar, eth_guven, eth_renk, eth_rapor, eth_egim = analiz_ve_islem_yapi("ETHUSDT", emir_tetikle=False)
sol_fiyat, sol_rsi, sol_df, sol_karar, sol_guven, sol_renk, sol_rapor, sol_egim = analiz_ve_islem_yapi("SOLUSDT", emir_tetikle=False)

st.markdown("""
    <div style='text-align: center; background-color: #111111; padding: 20px; border-radius: 15px; border: 1px solid #D4AF37; margin-bottom: 25px;'>
        <h1 style='color: #D4AF37; font-family: "Arial Black", Gadget, sans-serif; letter-spacing: 5px; font-size: 45px; margin: 0;'>Z E Y A</h1>
        <p style='color: #888888; font-family: "Courier New", monospace; font-size: 14px; margin-top: 5px; margin-bottom: 0;'>
            7/24 AUTONOMOUS BACKGROUND ENGINE & LIFETIME DATABASE ACTIVE
        </p>
    </div>
""", unsafe_allow_html=True)

st.sidebar.header("Robot Sistem Durumu")
if GERCEK_ISLEM_AKTIF:
    st.sidebar.error("Otomatik Emir Modu: GERCEK PIYASA")
else:
    st.sidebar.warning("Otomatik Emir Modu: SIMULASYON (TEST)")
st.sidebar.success("Kesintisiz Arkaplan Motoru: AKTIF")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="Bitcoin (BTC)", value=f"{btc_fiyat:,.2f} USDT", delta=f"ML Egimi: {btc_egim:.2f}")
    st.markdown(f"<div style='background-color: #111111; border: 2px solid #D4AF37; padding: 12px; border-radius: 10px; text-align: center;'><span style='color: #888888; font-size: 12px; font-weight: bold;'>ZEYA AI ANLIK DURUM</span><br><span style='color: {btc_renk}; font-size: 22px; font-weight: bold;'>{btc_karar}</span><br><span style='color: #D4AF37; font-size: 13px;'>Guven: %{btc_guven:.1f}</span></div>", unsafe_allow_html=True)
    st.info(f"Son Durum: {btc_rapor}")
    st.line_chart(btc_df['close'])

with col2:
    st.metric(label="Ethereum (ETH)", value=f"{eth_fiyat:,.2f} USDT", delta=f"ML Egimi: {eth_egim:.2f}")
    st.markdown(f"<div style='background-color: #111111; border: 2px solid #D4AF37; padding: 12px; border-radius: 10px; text-align: center;'><span style='color: #888888; font-size: 12px; font-weight: bold;'>ZEYA AI ANLIK DURUM</span><br><span style='color: {eth_renk}; font-size: 22px; font-weight: bold;'>{eth_karar}</span><br><span style='color: #D4AF37; font-size: 13px;'>Guven: %{eth_guven:.1f}</span></div>", unsafe_allow_html=True)
    st.info(f"Son Durum: {eth_rapor}")
    st.line_chart(eth_df['close'])

with col3:
    st.metric(label="Solana (SOL)", value=f"{sol_fiyat:,.2f} USDT", delta=f"ML Egimi: {sol_egim:.2f}")
    st.markdown(f"<div style='background-color: #111111; border: 2px solid #D4AF37; padding: 12px; border-radius: 10px; text-align: center;'><span style='color: #888888; font-size: 12px; font-weight: bold;'>ZEYA AI ANLIK DURUM</span><br><span style='color: {sol_renk}; font-size: 22px; font-weight: bold;'>{sol_karar}</span><br><span style='color: #D4AF37; font-size: 13px;'>Guven: %{sol_guven:.1f}</span></div>", unsafe_allow_html=True)
    st.info(f"Son Durum: {sol_rapor}")
    st.line_chart(sol_df['close'])

st.markdown("---")
col_wallet, col_news = st.columns(2)

with col_wallet:
    st.header("Simule Fon Yonetimi")
    canli_kasa_bakiyesi = oku_kasa_bakiyesi()
    st.info(f"Toplam Kasa Bakiyesi: **{canli_kasa_bakiyesi:,.2f} USDT**")

    st.subheader("Gercek Backtest Sonucu (BTC, son 30 gun)")
    bt_sonuc = gercek_backtest_yap("BTCUSDT", gun_sayisi=30)
    if bt_sonuc:
        bt_col1, bt_col2, bt_col3 = st.columns(3)
        bt_col1.metric("Toplam Getiri", f"%{bt_sonuc['toplam_getiri_yuzde']:.2f}")
        bt_col2.metric("Kazanma Orani", f"%{bt_sonuc['kazanma_orani']:.1f}", help=f"{bt_sonuc['islem_sayisi']} islem uzerinden")
        bt_col3.metric("Maks. Dusus", f"%{bt_sonuc['maks_dusus_yuzde']:.2f}", help="En kotu senaryoda ne kadar deger kaybedildigi")
        st.caption("Gecmis performans gelecekteki sonuclarin garantisi degildir. Bu sadece stratejinin gecmis veri uzerindeki davranisini gosterir.")
    else:
        st.warning("Backtest verisi su anda hesaplanamadi, birazdan tekrar dene.")

with col_news:
    st.header("Yapay Zeka Haber Duygusu")
    st.warning(f"Piyasa Havasi: OLUMLU / NOTR (Feshetme veya panik dalgasi saptanmadi.)")

st.markdown("---")
st.header("ZEYA Algoritma Seyir Defteri (7/24 Kesintisiz Hafiza Kayitlari)")
df_log = oku_sinyal_deposu()
if not df_log.empty:
    st.dataframe(df_log, use_container_width=True)
else:
    st.info("Arka plan motoru ilk verileri topluyor, tablo birazdan guncellenecektir...")
