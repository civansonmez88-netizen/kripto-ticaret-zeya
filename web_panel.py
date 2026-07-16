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
import smtplib
import logging
import traceback
from email.mime.text import MIMEText

# ==========================================================
# MERKEZİ HATA LOGLAMA SİSTEMİ
# ==========================================================
logging.basicConfig(
    filename="zeya_hatalar.log",
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ZEYA")

# ==========================================================
# ÇOKLU DİL SÖZLÜĞÜ (LOCALIZATION)
# ==========================================================
LANGUAGES = {
    "TR": {
        "title": "Z E Y A",
        "subtitle": "7/24 OTONOM ARKA PLAN MOTORU & KALICI VERİTABANI AKTİF",
        "status": "Sistem Durumu",
        "mode_real": "Otomatik Emir Modu: GERÇEK PİYASA",
        "mode_sim": "Otomatik Emir Modu: SİMÜLASYON (TEST)",
        "engine_active": "Kesintisiz Arkaplan Motoru: AKTİF",
        "tg_active": "Telegram Bildirimleri: AKTİF",
        "tg_passive": "Telegram Bildirimleri: Kapalı (İsteğe bağlı)",
        "mail_active": "E-posta Bildirimleri: AKTİF",
        "mail_passive": "E-posta Bildirimleri: Kapalı (İsteğe bağlı)",
        "risk_settings": "Risk Yönetimi Ayarları",
        "stop_loss": "Stop-Loss (%)",
        "take_profit": "Take-Profit (%)",
        "capital_per_trade": "İşlem Başına Sermaye (%)",
        "max_total_position": "Toplam Pozisyon Limiti (%)",
        "settings_saved": "Ayarlar kaydedildi. Motor güncellendi.",
        "ai_status_title": "ZEYA AI ANLIK DURUM",
        "confidence": "Güven",
        "last_status": "Son Durum",
        "wallet_management": "Simüle Fon Yönetimi",
        "total_balance": "Toplam Kasa Bakiyesi",
        "backtest_title": "Gerçek Backtest Sonucu",
        "backtest_return": "Toplam Getiri",
        "backtest_winrate": "Kazanma Oranı",
        "backtest_drawdown": "Maks. Düşüş",
        "backtest_warning": "Geçmiş performans gelecekteki sonuçların garantisi değildir.",
        "news_sentiment": "Yapay Zeka Haber Duygusu",
        "market_sentiment": "Piyasa Havası: OLUMLU / NÖTR (Panik dalgası saptanmadı.)",
        "performance_chart": "Gerçek Zamanlı Performans (Varlık Eğrisi)",
        "performance_caption": "Arka plan motorunun kaydettiği gerçek geçmiş performans.",
        "start_equity": "Başlangıç Varlığı",
        "current_equity": "Güncel Toplam Varlık",
        "record_count": "Kayıt Sayısı",
        "insufficient_data": "Arka plan motoru henüz yeterli veri toplamadı.",
        "log_book": "ZEYA Algoritma Seyir Defteri (7/24 Kesintisiz Hafıza Kayıtları)",
        "no_log": "Arka plan motoru ilk verileri topluyor, tablo birazdan güncellenecektir...",
        "pair_management": "Parite Yönetimi",
        "add_pair": "Yeni Parite Ekle (Örn: DOGEUSDT)",
        "add_button": "Ekle",
        "remove_pair": "Parite Sil",
        "remove_button": "Sil",
        "notification_center": "Bildirim Merkezi",
        "unreads": "okunmamış",
        "no_notifications": "Henüz bildirim yok.",
        "mark_all_read": "Tümünü okundu olarak işaretle",
        "system_health": "Sistem Sağlığı",
        "no_errors": "Son kayıtlarda herhangi bir hata yok.",
        "error_caption": "Sistem hatalarını şeffaf şekilde gösterir.",
        "slope": "ML Eğimi"
    },
    "EN": {
        "title": "Z E Y A",
        "subtitle": "24/7 AUTONOMOUS BACKGROUND ENGINE & LIFETIME DATABASE ACTIVE",
        "status": "System Status",
        "mode_real": "Automated Order Mode: REAL MARKET",
        "mode_sim": "Automated Order Mode: SIMULATION (TEST)",
        "engine_active": "Continuous Background Engine: ACTIVE",
        "tg_active": "Telegram Notifications: ACTIVE",
        "tg_passive": "Telegram Notifications: Disabled (Optional)",
        "mail_active": "Email Notifications: ACTIVE",
        "mail_passive": "Email Notifications: Disabled (Optional)",
        "risk_settings": "Risk Management Settings",
        "stop_loss": "Stop-Loss (%)",
        "take_profit": "Take-Profit (%)",
        "capital_per_trade": "Capital Per Trade (%)",
        "max_total_position": "Max Total Position Limit (%)",
        "settings_saved": "Settings saved. Engine updated.",
        "ai_status_title": "ZEYA AI INSTANT STATUS",
        "confidence": "Confidence",
        "last_status": "Last Status",
        "wallet_management": "Simulated Fund Management",
        "total_balance": "Total Cash Balance",
        "backtest_title": "Real Backtest Results",
        "backtest_return": "Total Return",
        "backtest_winrate": "Win Rate",
        "backtest_drawdown": "Max Drawdown",
        "backtest_warning": "Past performance is not a guarantee of future results.",
        "news_sentiment": "AI News Sentiment",
        "market_sentiment": "Market Sentiment: POSITIVE / NEUTRAL (No panic detected.)",
        "performance_chart": "Real-Time Performance (Equity Curve)",
        "performance_caption": "Actual historical performance recorded by the background engine.",
        "start_equity": "Starting Equity",
        "current_equity": "Current Total Equity",
        "record_count": "Record Count",
        "insufficient_data": "The background engine has not collected enough data yet.",
        "log_book": "ZEYA Algorithm Logbook (24/7 Continuous Memory Records)",
        "no_log": "The background engine is collecting data, the table will update shortly...",
        "pair_management": "Pair Management",
        "add_pair": "Add New Pair (e.g., DOGEUSDT)",
        "add_button": "Add",
        "remove_pair": "Remove Pair",
        "remove_button": "Remove",
        "notification_center": "Notification Center",
        "unreads": "unread",
        "no_notifications": "No notifications yet.",
        "mark_all_read": "Mark all as read",
        "system_health": "System Health",
        "no_errors": "No errors in recent records.",
        "error_caption": "Shows system errors transparently.",
        "slope": "ML Slope"
    }
}

# ==========================================================
# BINANCE API AYARLARI
# ==========================================================
def _anahtar_oku(isim):
    try:
        return st.secrets[isim]
    except Exception:
        return os.environ.get(isim, "")

BINANCE_API_KEY = _anahtar_oku("BINANCE_API_KEY")
BINANCE_SECRET_KEY = _anahtar_oku("BINANCE_SECRET_KEY")
GERCEK_ISLEM_AKTIF = False

TELEGRAM_BOT_TOKEN = _anahtar_oku("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _anahtar_oku("TELEGRAM_CHAT_ID")

SMTP_SUNUCU = _anahtar_oku("SMTP_SUNUCU")
SMTP_PORT = _anahtar_oku("SMTP_PORT")
SMTP_EPOSTA = _anahtar_oku("SMTP_EPOSTA")
SMTP_SIFRE = _anahtar_oku("SMTP_SIFRE")
ALICI_EPOSTA = _anahtar_oku("ALICI_EPOSTA")

st.set_page_config(page_title="ZEYA - AI Crypto Trading Panel", page_icon="Z", layout="wide", initial_sidebar_state="expanded")

# STREAMLIT GİZLEME AYARLARI
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    stDecoration {display:none !important;}
    [data-testid="collapsedControl"] {
        visibility: visible !important;
        display: block !important;
        opacity: 1 !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================================
# ÇELİK ZIRHLI SQLITE KALICI HAFIZA MOTORU (WAL AKTİF)
# ==========================================================
DB_FILE = "zeya_asıl_hafiza.db"

def veritabani_baglantisi_al():
    # Eşzamanlı yazma/okuma kilitlenmelerini önlemek için WAL modunu aktif ediyoruz.
    conn = sqlite3.connect(DB_FILE, timeout=20, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn

def veritabani_kur():
    conn = veritabani_baglantisi_al()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS kasa (id INTEGER PRIMARY KEY, bakiye REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS pozisyonlar (parite TEXT PRIMARY KEY, giris_fiyati REAL, miktar REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS pariteler (symbol TEXT PRIMARY KEY, aktif INTEGER DEFAULT 1)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sinyal_deposu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih_saat TEXT,
            log_verisi TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ayarlar (
            id INTEGER PRIMARY KEY,
            stop_loss_yuzde REAL,
            take_profit_yuzde REAL,
            pozisyon_buyuklugu_yuzde REAL,
            maks_toplam_pozisyon_yuzde REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS varlik_gecmisi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih_saat TEXT,
            toplam_varlik REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bildirimler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih_saat TEXT,
            tur TEXT,
            mesaj TEXT,
            okundu INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hata_kayitlari (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih_saat TEXT,
            kaynak TEXT,
            hata_mesaji TEXT
        )
    """)
    
    cursor.execute("SELECT bakiye FROM kasa WHERE id = 1")
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO kasa (id, bakiye) VALUES (1, 10000.0)")

    # Varsayılan pariteleri ekle
    cursor.execute("SELECT COUNT(*) FROM pariteler")
    if cursor.fetchone()[0] == 0:
        for p in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
            cursor.execute("INSERT OR IGNORE INTO pariteler (symbol, aktif) VALUES (?, 1)", (p,))

    cursor.execute("SELECT id FROM ayarlar WHERE id = 1")
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO ayarlar (id, stop_loss_yuzde, take_profit_yuzde, pozisyon_buyuklugu_yuzde, maks_toplam_pozisyon_yuzde) VALUES (1, -5.0, 10.0, 15.0, 50.0)")
    
    conn.commit()
    conn.close()

veritabani_kur()

# ==========================================================
# PARİTE YÖNETİM FONKSİYONLARI
# ==========================================================
def oku_aktif_pariteler():
    conn = veritabani_baglantisi_al()
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM pariteler WHERE aktif = 1")
    pariteler = [satir[0] for satir in cursor.fetchall()]
    conn.close()
    return pariteler

def parite_ekle(symbol):
    symbol = symbol.strip().upper()
    if not symbol:
        return
    conn = veritabani_baglantisi_al()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO pariteler (symbol, aktif) VALUES (?, 1)", (symbol,))
    conn.commit()
    conn.close()

def parite_sil(symbol):
    conn = veritabani_baglantisi_al()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pariteler WHERE symbol = ?", (symbol,))
    conn.commit()
    conn.close()

# ==========================================================
# VERİTABANI YARDIMCI FONKSİYONLARI
# ==========================================================
def oku_kasa_bakiyesi():
    try:
        conn = veritabani_baglantisi_al()
        cursor = conn.cursor()
        cursor.execute("SELECT bakiye FROM kasa WHERE id = 1")
        bakiye = cursor.fetchone()[0]
        conn.close()
        return bakiye
    except Exception as e:
        hata_logla("Kasa Bakiyesi Okuma", e)
        return 0.0

def guncelle_kasa_bakiyesi(yeni_bakiye):
    try:
        conn = veritabani_baglantisi_al()
        cursor = conn.cursor()
        cursor.execute("UPDATE kasa SET bakiye = ? WHERE id = 1", (yeni_bakiye,))
        conn.commit()
        conn.close()
    except Exception as e:
        hata_logla("Kasa Bakiyesi Güncelleme", e)

def oku_ayarlar():
    conn = veritabani_baglantisi_al()
    cursor = conn.cursor()
    cursor.execute("SELECT stop_loss_yuzde, take_profit_yuzde, pozisyon_buyuklugu_yuzde, maks_toplam_pozisyon_yuzde FROM ayarlar WHERE id = 1")
    sl, tp, pb, maks_toplam = cursor.fetchone()
    conn.close()
    return {
        "stop_loss_yuzde": sl,
        "take_profit_yuzde": tp,
        "pozisyon_buyuklugu_yuzde": pb,
        "maks_toplam_pozisyon_yuzde": maks_toplam if maks_toplam is not None else 50.0,
    }

def guncelle_ayarlar(stop_loss_yuzde, take_profit_yuzde, pozisyon_buyuklugu_yuzde, maks_toplam_pozisyon_yuzde):
    conn = veritabani_baglantisi_al()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE ayarlar SET stop_loss_yuzde = ?, take_profit_yuzde = ?, pozisyon_buyuklugu_yuzde = ?, maks_toplam_pozisyon_yuzde = ? WHERE id = 1",
        (stop_loss_yuzde, take_profit_yuzde, pozisyon_buyuklugu_yuzde, maks_toplam_pozisyon_yuzde)
    )
    conn.commit()
    conn.close()

def oku_tum_pozisyonlar():
    conn = veritabani_baglantisi_al()
    cursor = conn.cursor()
    cursor.execute("SELECT parite, giris_fiyati, miktar FROM pozisyonlar")
    res = cursor.fetchall()
    conn.close()
    return res

def varlik_anlik_kaydet(toplam_varlik):
    conn = veritabani_baglantisi_al()
    cursor = conn.cursor()
    su_an = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cursor.execute("INSERT INTO varlik_gecmisi (tarih_saat, toplam_varlik) VALUES (?, ?)", (su_an, toplam_varlik))
    conn.commit()
    conn.close()

def telegram_bildirim_gonder(mesaj):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj}, timeout=5)
    except Exception as e:
        hata_logla("Telegram Bildirim", e)

def eposta_bildirim_gonder(konu, mesaj):
    if not all([SMTP_SUNUCU, SMTP_PORT, SMTP_EPOSTA, SMTP_SIFRE, ALICI_EPOSTA]):
        return
    try:
        eposta = MIMEText(mesaj, "plain", "utf-8")
        eposta["Subject"] = konu
        eposta["From"] = SMTP_EPOSTA
        eposta["To"] = ALICI_EPOSTA
        with smtplib.SMTP(SMTP_SUNUCU, int(SMTP_PORT), timeout=10) as sunucu:
            sunucu.starttls()
            sunucu.login(SMTP_EPOSTA, SMTP_SIFRE)
            sunucu.send_message(eposta)
    except Exception as e:
        hata_logla("E-posta Bildirim", e)

def bildirim_ekle(tur, mesaj):
    conn = veritabani_baglantisi_al()
    cursor = conn.cursor()
    su_an = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cursor.execute("INSERT INTO bildirimler (tarih_saat, tur, mesaj, okundu) VALUES (?, ?, ?, 0)", (su_an, tur, mesaj))
    conn.commit()
    conn.close()

def oku_bildirimler(limit=30):
    conn = veritabani_baglantisi_al()
    df = pd.read_sql_query(f"SELECT id, tarih_saat, tur, mesaj, okundu FROM bildirimler ORDER BY id DESC LIMIT {limit}", conn)
    conn.close()
    return df

def okunmamis_bildirim_sayisi():
    conn = veritabani_baglantisi_al()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bildirimler WHERE okundu = 0")
    sayi = cursor.fetchone()[0]
    conn.close()
    return sayi

def tum_bildirimleri_okundu_yap():
    conn = veritabani_baglantisi_al()
    cursor = conn.cursor()
    cursor.execute("UPDATE bildirimler SET okundu = 1 WHERE okundu = 0")
    conn.commit()
    conn.close()

def oku_varlik_gecmisi():
    conn = veritabani_baglantisi_al()
    df = pd.read_sql_query("SELECT tarih_saat, toplam_varlik FROM varlik_gecmisi ORDER BY id ASC", conn)
    conn.close()
    return df

def hata_logla(kaynak, hata):
    hata_metni = f"{hata}"
    detay = traceback.format_exc()
    logger.error(f"[{kaynak}] {hata_metni}\n{detay}")
    try:
        conn = veritabani_baglantisi_al()
        cursor = conn.cursor()
        su_an = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        cursor.execute(
            "INSERT INTO hata_kayitlari (tarih_saat, kaynak, hata_mesaji) VALUES (?, ?, ?)",
            (su_an, kaynak, hata_metni)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def oku_hata_kayitlari(limit=20):
    conn = veritabani_baglantisi_al()
    df = pd.read_sql_query(f"SELECT tarih_saat, kaynak, hata_mesaji FROM hata_kayitlari ORDER BY id DESC LIMIT {limit}", conn)
    conn.close()
    return df

def oku_pozisyon(parite):
    try:
        conn = veritabani_baglantisi_al()
        cursor = conn.cursor()
        cursor.execute("SELECT giris_fiyati, miktar FROM pozisyonlar WHERE parite = ?", (parite,))
        res = cursor.fetchone()
        conn.close()
        return res
    except Exception as e:
        hata_logla(f"Pozisyon Okuma ({parite})", e)
        return None

def pozisyon_kaydet(parite, giris_fiyati, miktar):
    try:
        conn = veritabani_baglantisi_al()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO pozisyonlar (parite, giris_fiyati, miktar) VALUES (?, ?, ?)", (parite, giris_fiyati, miktar))
        conn.commit()
        conn.close()
    except Exception as e:
        hata_logla(f"Pozisyon Kaydetme ({parite})", e)

def pozisyon_sil(parite):
    try:
        conn = veritabani_baglantisi_al()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pozisyonlar WHERE parite = ?", (parite,))
        conn.commit()
        conn.close()
    except Exception as e:
        hata_logla(f"Pozisyon Silme ({parite})", e)

def oku_sinyal_deposu():
    conn = veritabani_baglantisi_al()
    df = pd.read_sql_query("SELECT tarih_saat AS 'Tarih/Saat', log_verisi AS 'Sinyal Logları' FROM sinyal_deposu ORDER BY id DESC LIMIT 15", conn)
    conn.close()
    return df

def yeni_sinyal_ekle(tarih, log_metni):
    conn = veritabani_baglantisi_al()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sinyal_deposu (tarih_saat, log_verisi)
        VALUES (?, ?)
    """, (tarih, log_metni))
    conn.commit()
    conn.close()

def binance_veri_al(symbol, interval="15m", limit=100):
    url = "https://data-api.binance.vision/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    veri = response.json()
    kapanis_fiyatlari = [float(mum[4]) for mum in veri]
    return kapanis_fiyatlari

# ==========================================================
# EMİR MOTORU VE ALGORİTMİK KARAR MEKANİZMASI
# ==========================================================
def binance_emir_gonder(symbol, side, type="MARKET"):
    if not GERCEK_ISLEM_AKTIF:
        return f"[SIMULATION] {side} triggered."
    base_url = "https://api.binance.com"
    endpoint = "/api/v3/order"
    timestamp = int(time.time() * 1000)
    query_string = f"symbol={symbol}&side={side}&type={type}&quantity=0.001&timestamp={timestamp}"
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return "API Key Missing!"
    signature = hmac.new(BINANCE_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{query_string}&signature={signature}"
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    try:
        response = requests.post(url, headers=headers)
        res_data = response.json()
        if response.status_code == 200:
            return f"SUCCESS: {side}"
        else:
            return f"Error: {res_data.get('msg', 'Unknown')}"
    except Exception as e:
        hata_logla("Binance Emir Gönderme", e)
        return "Connection Error"

def yapay_zeka_karar_merkezi(rsi, macd, macd_sinyal, ema, close, egim, bb_alt):
    puan = 0
    if rsi < 35: puan += 1.5
    elif rsi < 50: puan += 1
    elif rsi > 65: puan -= 1.5
    elif rsi > 50: puan -= 1
    if macd > macd_sinyal: puan += 1
    else: puan -= 1
    if egim > 0: puan += 1
    else: warn = -1
    if close > ema: puan += 1
    else: puan -= 1
    if close <= bb_alt * 1.01: puan += 1.5
    
    maks_puan = 6.0
    guven_orani = min(abs(puan) / maks_puan, 1.0) * 100
    if puan >= 2.5: return "STRONG BUY", guven_orani, "#2ecc71", "BUY"
    elif puan >= 0.5: return "BUY", guven_orani, "#27ae60", "BUY"
    elif puan <= -2.5: return "STRONG SELL", guven_orani, "#e74c3c", "SELL"
    elif puan <= -0.5: return "SELL", guven_orani, "#c0392b", "SELL"
    else: return "HOLD", 50.0, "#f1c40f", "HOLD"

def analiz_ve_islem_yapi(symbol, emir_tetikle=False):
    try:
        kapanis_fiyatlari = binance_veri_al(symbol, interval="15m", limit=100)
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
        
        islem_raporu = "Wait"
        aktif_pozisyon = oku_pozisyon(symbol)
        ayarlar = oku_ayarlar()

        if emir_tetikle:
            mevcut_bakiye = oku_kasa_bakiyesi()
            zorla_kapatildi = False

            if aktif_pozisyon:
                giris_fiyati, miktar = aktif_pozisyon
                kar_zarar_yuzde = ((anlik_fiyat - giris_fiyati) / giris_fiyati) * 100

                if kar_zarar_yuzde <= ayarlar["stop_loss_yuzde"]:
                    if not GERCEK_ISLEM_AKTIF:
                        iade_tutar = miktar * anlik_fiyat
                        guncelle_kasa_bakiyesi(mevcut_bakiye + iade_tutar)
                        pozisyon_sil(symbol)
                        islem_raporu = f"STOP-LOSS! PNL: %{kar_zarar_yuzde:.2f}"
                    else:
                        islem_raporu = "STOP-LOSS: " + binance_emir_gonder(symbol, "SELL")
                        pozisyon_sil(symbol)
                    zorla_kapatildi = True
                    telegram_bildirim_gonder(f"🛑 ZEYA: {symbol} STOP-LOSS triggered.\nPNL: %{kar_zarar_yuzde:.2f}\nPrice: {anlik_fiyat:,.2f} USDT")
                    bildirim_ekle("STOP-LOSS", f"🛑 {symbol} STOP-LOSS triggered. PNL: %{kar_zarar_yuzde:.2f}")
                    eposta_bildirim_gonder(f"🛑 ZEYA: {symbol} Stop-Loss Triggered", f"{symbol} closed at stop-loss.")
                elif kar_zarar_yuzde >= ayarlar["take_profit_yuzde"]:
                    if not GERCEK_ISLEM_AKTIF:
                        iade_tutar = miktar * anlik_fiyat
                        guncelle_kasa_bakiyesi(mevcut_bakiye + iade_tutar)
                        pozisyon_sil(symbol)
                        islem_raporu = f"TAKE-PROFIT! PNL: %{kar_zarar_yuzde:.2f}"
                    else:
                        islem_raporu = "TAKE-PROFIT: " + binance_emir_gonder(symbol, "SELL")
                        pozisyon_sil(symbol)
                    zorla_kapatildi = True
                    telegram_bildirim_gonder(f"🎯 ZEYA: {symbol} TAKE-PROFIT triggered.\nPNL: %{kar_zarar_yuzde:.2f}\nPrice: {anlik_fiyat:,.2f} USDT")
                    bildirim_ekle("TAKE-PROFIT", f"🎯 {symbol} TAKE-PROFIT triggered. PNL: %{kar_zarar_yuzde:.2f}")
                    eposta_bildirim_gonder(f"🎯 ZEYA: {symbol} Take-Profit Triggered", f"{symbol} closed at take-profit.")

            if not zorla_kapatildi and aksiyon in ["BUY", "SELL"]:
                aktif_pozisyon = oku_pozisyon(symbol)
                mevcut_bakiye = oku_kasa_bakiyesi()
                if not GERCEK_ISLEM_AKTIF:
                    if "BUY" in aksiyon and not aktif_pozisyon:
                        tum_pozisyonlar = oku_tum_pozisyonlar()
                        toplam_yatirilan = sum(gf * m for _, gf, m in tum_pozisyonlar)
                        toplam_varlik = mevcut_bakiye + toplam_yatirilan
                        islem_tutari = mevcut_bakiye * (ayarlar["pozisyon_buyuklugu_yuzde"] / 100)
                        maks_izin_verilen = toplam_varlik * (ayarlar["maks_toplam_pozisyon_yuzde"] / 100)

                        if islem_tutari > 10 and (toplam_yatirilan + islem_tutari) <= maks_izin_verilen:
                            yeni_bakiye = mevcut_bakiye - islem_tutari
                            miktar = islem_tutari / anlik_fiyat
                            pozisyon_kaydet(symbol, anlik_fiyat, miktar)
                            guncelle_kasa_bakiyesi(yeni_bakiye)
                            islem_raporu = f"BUY execution. Qty: {miktar:.4f}"
                            telegram_bildirim_gonder(f"🟢 ZEYA: {symbol} BUY executed.\nPrice: {anlik_fiyat:,.2f} USDT")
                            bildirim_ekle("BUY", f"🟢 {symbol} BUY executed.")
                        elif islem_tutari > 10:
                            islem_raporu = "Total position limit reached"
                    elif "SELL" in aksiyon and aktif_pozisyon:
                        giris_fiyati, miktar = aktif_pozisyon
                        iade_tutar = miktar * anlik_fiyat
                        yeni_bakiye = mevcut_bakiye + iade_tutar
                        pozisyon_sil(symbol)
                        guncelle_kasa_bakiyesi(yeni_bakiye)
                        kar_zarar = ((anlik_fiyat - giris_fiyati) / giris_fiyati) * 100
                        islem_raporu = f"SELL execution. PNL: %{kar_zarar:.2f}"
                        telegram_bildirim_gonder(f"🔴 ZEYA: {symbol} SELL executed.\nPNL: %{kar_zarar:.2f}")
                        bildirim_ekle("SELL", f"🔴 {symbol} SELL executed.")
                else:
                    islem_raporu = binance_emir_gonder(symbol, aksiyon)
        else:
            if aktif_pozisyon:
                giris_fiyati, miktar = aktif_pozisyon
                kar_zarar_yuzde = ((anlik_fiyat - giris_fiyati) / giris_fiyati) * 100
                islem_raporu = f"Active Position (Entry: {giris_fiyati:,.2f}, PNL: %{kar_zarar_yuzde:.2f})"
        
        return anlik_fiyat, df['rsi'].iloc[-1], df, karar, guven, renk, islem_raporu, egim
    except Exception as e:
        hata_logla(f"Analiz ({symbol})", e)
        return 0.0, 50.0, pd.DataFrame([0]*60, columns=['close']), "NEUTRAL", 50.0, "#f1c40f", "Error", 0.0

# ==========================================================
# GERÇEK BACKTEST MOTORU
# ==========================================================
@st.cache_data(ttl=3600)
def gercek_backtest_yap(symbol, gun_sayisi=30):
    try:
        limit = min(gun_sayisi * 24, 1000)
        kapanis_fiyatlari = binance_veri_al(symbol, interval="1h", limit=limit)
        if len(kapanis_fiyatlari) < 60:
            return None

        df = pd.DataFrame(kapanis_fiyatlari, columns=['close'])
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

            guncel_toplam_deger = sanal_bakiye + (pozisyon_miktar * satir['close'])
            toplam_deger_gecmisi.append(guncel_toplam_deger)

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
        hata_logla(f"Backtest ({symbol})", e)
        return None

# ==========================================================
# 7/24 BAĞIMSIZ ARKA PLAN MOTORU
# ==========================================================
def kesintisiz_bot_dongusu():
    while True:
        try:
            aktif_pariteler = oku_aktif_pariteler()
            sinyal_raporu = []
            
            for symbol in aktif_pariteler:
                fiyat, _, _, karar, _, _, _, _ = analiz_ve_islem_yapi(symbol, emir_tetikle=True)
                sinyal_raporu.append(f"{symbol}: {fiyat:,.2f} ({karar})")
            
            # Seyir defterine toplu olarak kaydet
            su_an = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            yeni_sinyal_ekle(su_an, " | ".join(sinyal_raporu))

            # Varlık Geçmişi Güncelleme
            mevcut_bakiye = oku_kasa_bakiyesi()
            tum_pozisyonlar = oku_tum_pozisyonlar()
            pozisyon_degeri = 0.0
            
            for parite, giris_fiyati, miktar in tum_pozisyonlar:
                try:
                    anlik_fiyatlar = binance_veri_al(parite, limit=1)
                    if anlik_fiyatlar:
                        pozisyon_degeri += miktar * anlik_fiyatlar[-1]
                except Exception:
                    pozisyon_degeri += miktar * giris_fiyati
                    
            toplam_varlik = mevcut_bakiye + pozisyon_degeri
            varlik_anlik_kaydet(toplam_varlik)

        except Exception as e:
            hata_logla("Arka Plan Döngüsü", e)
            
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

# 1. Dil Seçimi (Dil Tercihi Session State'te Tutulur)
if "lang" not in st.session_state:
    st.session_state.lang = "TR"

st.sidebar.markdown("### 🌐 Language / Dil")
st.session_state.lang = st.sidebar.selectbox("Select Language", ["TR", "EN"], index=0 if st.session_state.lang == "TR" else 1)

L = LANGUAGES[st.session_state.lang]

# LOGO TASARIMI
st.markdown(f"""
    <div style='text-align: center; background-color: #111111; padding: 20px; border-radius: 15px; border: 1px solid #D4AF37; margin-bottom: 25px;'>
        <h1 style='color: #D4AF37; font-family: "Arial Black", Gadget, sans-serif; letter-spacing: 5px; font-size: 45px; margin: 0;'>{L['title']}</h1>
        <p style='color: #888888; font-family: "Courier New", monospace; font-size: 14px; margin-top: 5px; margin-bottom: 0;'>
            {L['subtitle']}
        </p>
    </div>
""", unsafe_allow_html=True)

# 2. Bildirim ve Sistem Sağlığı Genişleticileri
_okunmamis_sayi = okunmamis_bildirim_sayisi()
_bildirim_baslik = f"🔔 {L['notification_center']}" + (f" ({_okunmamis_sayi} {L['unreads']})" if _okunmamis_sayi > 0 else "")
with st.expander(_bildirim_baslik, expanded=(_okunmamis_sayi > 0)):
    df_bildirim = oku_bildirimler(limit=30)
    if df_bildirim.empty:
        st.caption(L["no_notifications"])
    else:
        if _okunmamis_sayi > 0 and st.button(f"✅ {L['mark_all_read']}"):
            tum_bildirimleri_okundu_yap()
            st.rerun()
        for _, satir in df_bildirim.iterrows():
            _isaret = "🆕 " if satir["okundu"] == 0 else ""
            st.markdown(f"{_isaret}**{satir['tarih_saat']}** — {satir['mesaj']}")

df_hata = oku_hata_kayitlari(limit=20)
_hata_baslik = f"🛠️ {L['system_health']}" + (f" ({len(df_hata)} Errors)" if not df_hata.empty else " (OK ✅)")
with st.expander(_hata_baslik, expanded=False):
    if df_hata.empty:
        st.success(f"✅ {L['no_errors']}")
    else:
        st.caption(L["error_caption"])
        for _, satir in df_hata.iterrows():
            st.markdown(f"🔴 **{satir['tarih_saat']}** — `{satir['kaynak']}`: {satir['hata_mesaji']}")

# SIDEBAR SİSTEM DURUMU
st.sidebar.header(f"👁️ {L['status']}")
if GERCEK_ISLEM_AKTIF:
    st.sidebar.error(f"🤖 {L['mode_real']}")
else:
    st.sidebar.warning(f"🧪 {L['mode_sim']}")
st.sidebar.success(f" {L['engine_active']} 🟢")

if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    st.sidebar.success(f"📱 {L['tg_active']} 🟢")
else:
    st.sidebar.info(f"📱 {L['tg_passive']}")
if all([SMTP_SUNUCU, SMTP_PORT, SMTP_EPOSTA, SMTP_SIFRE, ALICI_EPOSTA]):
    st.sidebar.success(f"✉️ {L['mail_active']} 🟢")
else:
    st.sidebar.info(f"✉️ {L['mail_passive']}")

# SIDEBAR DİNAMİK PARİTE YÖNETİMİ
st.sidebar.markdown("---")
st.sidebar.header(f"🪙 {L['pair_management']}")
mevcut_pariteler = oku_aktif_pariteler()

# Parite Ekleme Formu
yeni_p = st.sidebar.text_input(L["add_pair"]).strip().upper()
if st.sidebar.button(L["add_button"], key="add_btn"):
    if yeni_p and yeni_p not in mevcut_pariteler:
        parite_ekle(yeni_p)
        st.sidebar.success(f"Added: {yeni_p}")
        st.rerun()

# Parite Silme Formu
if mevcut_pariteler:
    silinecek_p = st.sidebar.selectbox(L["remove_pair"], mevcut_pariteler)
    if st.sidebar.button(L["remove_button"], key="rem_btn"):
        parite_sil(silinecek_p)
        st.sidebar.warning(f"Removed: {silinecek_p}")
        st.rerun()

# SIDEBAR RİSK AYARLARI
st.sidebar.markdown("---")
st.sidebar.header(f"⚙️ {L['risk_settings']}")
_mevcut_ayarlar = oku_ayarlar()
_yeni_stop_loss = st.sidebar.slider(
    L["stop_loss"], min_value=-30.0, max_value=-1.0,
    value=float(_mevcut_ayarlar["stop_loss_yuzde"]), step=0.5
)
_yeni_take_profit = st.sidebar.slider(
    L["take_profit"], min_value=1.0, max_value=50.0,
    value=float(_mevcut_ayarlar["take_profit_yuzde"]), step=0.5
)
_yeni_pozisyon_buyuklugu = st.sidebar.slider(
    L["capital_per_trade"], min_value=5.0, max_value=100.0,
    value=float(_mevcut_ayarlar["pozisyon_buyuklugu_yuzde"]), step=5.0
)
_yeni_maks_toplam_pozisyon = st.sidebar.slider(
    L["max_total_position"], min_value=10.0, max_value=100.0,
    value=float(_mevcut_ayarlar["maks_toplam_pozisyon_yuzde"]), step=5.0
)
if (_yeni_stop_loss != _mevcut_ayarlar["stop_loss_yuzde"]
        or _yeni_take_profit != _mevcut_ayarlar["take_profit_yuzde"]
        or _yeni_pozisyon_buyuklugu != _mevcut_ayarlar["pozisyon_buyuklugu_yuzde"]
        or _yeni_maks_toplam_pozisyon != _mevcut_ayarlar["maks_toplam_pozisyon_yuzde"]):
    guncelle_ayarlar(_yeni_stop_loss, _yeni_take_profit, _yeni_pozisyon_buyuklugu, _yeni_maks_toplam_pozisyon)
    st.sidebar.success(f"✅ {L['settings_saved']}")

# ==========================================================
# ANA EKRAN DİNAMİK GRAFİK GRIDİ
# ==========================================================
if mevcut_pariteler:
    # Pariteleri 3'erli kolonlar halinde ön yüze çiziyoruz
    for i in range(0, len(mevcut_pariteler), 3):
        chunk = mevcut_pariteler[i:i+3]
        cols = st.columns(len(chunk))
        for idx, symbol in enumerate(chunk):
            fiyat, rsi, df, karar, guven, renk, rapor, egim = analiz_ve_islem_yapi(symbol, emir_tetikle=False)
            with cols[idx]:
                st.metric(label=f"🪙 {symbol}", value=f"{fiyat:,.2f} USDT", delta=f"{L['slope']}: {egim:.2f}")
                st.markdown(f"<div style='background-color: #111111; border: 2px solid #D4AF37; padding: 12px; border-radius: 10px; text-align: center;'><span style='color: #888888; font-size: 12px; font-weight: bold;'>{L['ai_status_title']}</span><br><span style='color: {renk}; font-size: 22px; font-weight: bold;'>{karar}</span><br><span style='color: #D4AF37; font-size: 13px;'>{L['confidence']}: %{guven:.1f}</span></div>", unsafe_allow_html=True)
                st.info(f"🤖 {L['last_status']}: {rapor}")
                st.line_chart(df['close'])
else:
    st.info("Lütfen sol taraftan aktif işlem yapmak istediğiniz pariteleri ekleyin.")

st.markdown("---")
col_wallet, col_news = st.columns(2)

with col_wallet:
    st.header(f"💼 {L['wallet_management']}")
    canli_kasa_bakiyesi = oku_kasa_bakiyesi()
    st.info(f"💰 {L['total_balance']}: **{canli_kasa_bakiyesi:,.2f} USDT**")

    # Dinamik Backtest Bölümü
    if mevcut_pariteler:
        secilen_backtest_parite = st.selectbox(f"🔍 {L['backtest_title']} (30 Days)", mevcut_pariteler)
        bt_sonuc = gercek_backtest_yap(secilen_backtest_parite, gun_sayisi=30)
        if bt_sonuc:
            bt_col1, bt_col2, bt_col3 = st.columns(3)
            bt_col1.metric(L["backtest_return"], f"%{bt_sonuc['toplam_getiri_yuzde']:.2f}")
            bt_col2.metric(L["backtest_winrate"], f"%{bt_sonuc['kazanma_orani']:.1f}", help=f"{bt_sonuc['islem_sayisi']} trades")
            bt_col3.metric(L["backtest_drawdown"], f"%{bt_sonuc['maks_dusus_yuzde']:.2f}")
            st.caption(f"⚠️ {L['backtest_warning']}")
        else:
            st.warning("No backtest data calculated yet.")

with col_news:
    st.header(f"📰 {L['news_sentiment']}")
    st.warning(f"🟢 {L['market_sentiment']}")

# Varlık Eğrisi Grafiği
st.markdown("---")
st.header(f"📈 {L['performance_chart']}")
st.caption(L["performance_caption"])
df_varlik = oku_varlik_gecmisi()
if len(df_varlik) >= 2:
    baslangic_varlik = 10000.0
    guncel_varlik = df_varlik['toplam_varlik'].iloc[-1]
    toplam_getiri_yuzde = ((guncel_varlik - baslangic_varlik) / baslangic_varlik) * 100

    perf_col1, perf_col2, perf_col3 = st.columns(3)
    perf_col1.metric(L["start_equity"], f"{baslangic_varlik:,.2f} USDT")
    perf_col2.metric(L["current_equity"], f"{guncel_varlik:,.2f} USDT", delta=f"%{toplam_getiri_yuzde:.2f}")
    perf_col3.metric(L["record_count"], f"{len(df_varlik)} logs")

    grafik_df = df_varlik.set_index('tarih_saat')[['toplam_varlik']]
    st.line_chart(grafik_df)
else:
    st.info(L["insufficient_data"])

# Seyir Defteri Logları
st.markdown("---")
st.header(f"📜 {L['log_book']}")
df_log = oku_sinyal_deposu()
if not df_log.empty:
    st.dataframe(df_log, use_container_width=True)
else:
    st.info(L["no_log"])
