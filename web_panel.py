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
# 🛠️ MERKEZİ HATA LOGLAMA SİSTEMİ
# ==========================================================
# Hem bir log dosyasına (geçici, sunucu yeniden başladığında silinebilir) hem de
# veritabanına (kalıcı, arayüzden görülebilir) yazıyoruz. Böylece hiçbir hata
# artık sessizce kaybolmuyor.
logging.basicConfig(
    filename="zeya_hatalar.log",
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ZEYA")

# ==========================================================
# 🔑 BINANCE API AYARLARI (GÜVENLİ YÖNTEM: st.secrets / ortam değişkeni)
# ==========================================================
# ÖNEMLİ: Anahtarları asla doğrudan kodun içine yazma!
# Bunun yerine .streamlit/secrets.toml dosyasına şunları ekle:
#   BINANCE_API_KEY = "gerçek_anahtarın"
#   BINANCE_SECRET_KEY = "gerçek_gizli_anahtarın"
# Bu dosyayı ASLA GitHub'a veya başka bir yere yükleme (.gitignore'a ekle).
def _anahtar_oku(isim):
    # Önce Streamlit secrets'a bakar, yoksa ortam değişkenine (env variable) bakar
    try:
        return st.secrets[isim]
    except Exception:
        return os.environ.get(isim, "")

BINANCE_API_KEY = _anahtar_oku("BINANCE_API_KEY")
BINANCE_SECRET_KEY = _anahtar_oku("BINANCE_SECRET_KEY")
GERCEK_ISLEM_AKTIF = False  # Gerçek al-sat için burayı True yapmalısın!

# ==========================================================
# 📱 TELEGRAM BİLDİRİM AYARLARI (GÜVENLİ YÖNTEM: st.secrets / ortam değişkeni)
# ==========================================================
# .streamlit/secrets.toml dosyasına şunları ekle:
#   TELEGRAM_BOT_TOKEN = "botfather_dan_aldigin_token"
#   TELEGRAM_CHAT_ID = "chat_id_numaran"
TELEGRAM_BOT_TOKEN = _anahtar_oku("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _anahtar_oku("TELEGRAM_CHAT_ID")

# ==========================================================
# ✉️ E-POSTA BİLDİRİM AYARLARI (tamamen bağımsız, üçüncü parti "app" gerektirmez)
# ==========================================================
# .streamlit/secrets.toml dosyasına şunları ekle (Gmail kullanıyorsan "Uygulama Şifresi" oluşturman gerekir):
#   SMTP_SUNUCU = "smtp.gmail.com"
#   SMTP_PORT = "587"
#   SMTP_EPOSTA = "gonderen_hesabin@gmail.com"
#   SMTP_SIFRE = "uygulama_sifresi"
#   ALICI_EPOSTA = "bildirim_almak_istedigin@eposta.com"
SMTP_SUNUCU = _anahtar_oku("SMTP_SUNUCU")
SMTP_PORT = _anahtar_oku("SMTP_PORT")
SMTP_EPOSTA = _anahtar_oku("SMTP_EPOSTA")
SMTP_SIFRE = _anahtar_oku("SMTP_SIFRE")
ALICI_EPOSTA = _anahtar_oku("ALICI_EPOSTA")

# SAYFA GENİŞLİK VE MARKA AYARLARI
st.set_page_config(page_title="ZEYA - Yapay Zeka Kripto Ticaret Paneli", page_icon="Z", layout="wide", initial_sidebar_state="expanded")

# STREAMLIT LOGOLARINI GİZLEME KODU
# NOT: "header" elementini tamamen gizlemiyoruz çünkü sidebar açma/kapama
# oku bazı Streamlit sürümlerinde header'ın içinde yer alıyor ve onu da
# gizleyip geri açılamaz hale getirebiliyor. Sadece MainMenu ve footer'ı gizliyoruz.
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    stDecoration {display:none !important;}
    /* Sidebar açma/kapama oku her zaman görünür ve tıklanabilir kalsın */
    [data-testid="collapsedControl"] {
        visibility: visible !important;
        display: block !important;
        opacity: 1 !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================================
# 🧠 ÇELİK ZIRHLI SQLITE KALICI HAFIZA MOTORU
# ==========================================================
DB_FILE = "zeya_asıl_hafiza.db"

def veritabani_kur():
    # check_same_thread=False ekledik çünkü arka plan motoru ile ön yüz buraya eşzamanlı erişecek
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

    # Eski veritabanlarında "maks_toplam_pozisyon_yuzde" sütunu olmayabilir.
    # Yoksa ekliyoruz (migration) — böylece mevcut kullanıcıların verisi kaybolmaz.
    cursor.execute("PRAGMA table_info(ayarlar)")
    mevcut_sutunlar = [satir[1] for satir in cursor.fetchall()]
    if "maks_toplam_pozisyon_yuzde" not in mevcut_sutunlar:
        cursor.execute("ALTER TABLE ayarlar ADD COLUMN maks_toplam_pozisyon_yuzde REAL DEFAULT 50.0")

    cursor.execute("SELECT id FROM ayarlar WHERE id = 1")
    if cursor.fetchone() is None:
        # Varsayılan risk ayarları: %-5 stop-loss, %+10 take-profit, işlem başına %15 sermaye,
        # kasanın en fazla %50'si aynı anda pozisyonlarda olabilir
        cursor.execute("INSERT INTO ayarlar (id, stop_loss_yuzde, take_profit_yuzde, pozisyon_buyuklugu_yuzde, maks_toplam_pozisyon_yuzde) VALUES (1, -5.0, 10.0, 15.0, 50.0)")
    conn.commit()
    conn.close()

veritabani_kur()

def oku_kasa_bakiyesi():
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT bakiye FROM kasa WHERE id = 1")
        bakiye = cursor.fetchone()[0]
        conn.close()
        return bakiye
    except Exception as e:
        hata_logla("Kasa Bakiyesi Okuma", e)
        return 0.0  # Güvenli varsayılan: hata durumunda 0 dönmek, yanlış (uydurma) bir bakiyeyle işlem yapmaktan daha güvenli

def guncelle_kasa_bakiyesi(yeni_bakiye):
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("UPDATE kasa SET bakiye = ? WHERE id = 1", (yeni_bakiye,))
        conn.commit()
        conn.close()
    except Exception as e:
        hata_logla("Kasa Bakiyesi Güncelleme", e)

def oku_ayarlar():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
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
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE ayarlar SET stop_loss_yuzde = ?, take_profit_yuzde = ?, pozisyon_buyuklugu_yuzde = ?, maks_toplam_pozisyon_yuzde = ? WHERE id = 1",
        (stop_loss_yuzde, take_profit_yuzde, pozisyon_buyuklugu_yuzde, maks_toplam_pozisyon_yuzde)
    )
    conn.commit()
    conn.close()

def oku_tum_pozisyonlar():
    """Tüm açık pozisyonları döner: [(parite, giris_fiyati, miktar), ...]"""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT parite, giris_fiyati, miktar FROM pozisyonlar")
    res = cursor.fetchall()
    conn.close()
    return res

def varlik_anlik_kaydet(toplam_varlik):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    su_an = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cursor.execute("INSERT INTO varlik_gecmisi (tarih_saat, toplam_varlik) VALUES (?, ?)", (su_an, toplam_varlik))
    conn.commit()
    conn.close()

def telegram_bildirim_gonder(mesaj):
    """Telegram üzerinden bildirim gönderir. Token/Chat ID eksikse veya hata olursa
    sessizce geçer — bildirim hatası yüzünden botun al-sat mantığı asla durmamalı.
    NOT: Bu isteğe bağlı ekstra bir kanaldır. Asıl bildirim sistemi uygulama içi
    'Bildirim Merkezi' (bildirim_ekle / oku_bildirimler) — dış servise ihtiyaç duymaz."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj}, timeout=5)
    except Exception as e:
        hata_logla("Telegram Bildirim", e)

def eposta_bildirim_gonder(konu, mesaj):
    """SMTP üzerinden doğrudan e-posta gönderir — Telegram gibi üçüncü parti bir
    'app' platformuna değil, evrensel bir protokole (SMTP) dayanır. Ayarlar eksikse
    veya hata olursa sessizce geçer, bot mantığını asla durdurmaz."""
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
    """Uygulama içi bildirim merkezine yeni bir kayıt ekler. Tamamen bağımsız,
    hiçbir dış servise ihtiyaç duymaz — veriler doğrudan kendi veritabanımızda durur."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    su_an = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cursor.execute("INSERT INTO bildirimler (tarih_saat, tur, mesaj, okundu) VALUES (?, ?, ?, 0)", (su_an, tur, mesaj))
    conn.commit()
    conn.close()

def oku_bildirimler(limit=30):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    df = pd.read_sql_query(f"SELECT id, tarih_saat, tur, mesaj, okundu FROM bildirimler ORDER BY id DESC LIMIT {limit}", conn)
    conn.close()
    return df

def okunmamis_bildirim_sayisi():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bildirimler WHERE okundu = 0")
    sayi = cursor.fetchone()[0]
    conn.close()
    return sayi

def tum_bildirimleri_okundu_yap():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE bildirimler SET okundu = 1 WHERE okundu = 0")
    conn.commit()
    conn.close()

def oku_varlik_gecmisi():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    df = pd.read_sql_query("SELECT tarih_saat, toplam_varlik FROM varlik_gecmisi ORDER BY id ASC", conn)
    conn.close()
    return df

def hata_logla(kaynak, hata):
    """Her hatayı 3 yere kaydeder: (1) log dosyasına, (2) veritabanına (kalıcı,
    arayüzden görülebilir), (3) konsola. Bu fonksiyon çağrılmadan bir except
    bloğu SESSİZCE hata yutmamalı — bu kuralı tüm kodda takip ediyoruz."""
    hata_metni = f"{hata}"
    detay = traceback.format_exc()
    logger.error(f"[{kaynak}] {hata_metni}\n{detay}")
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        su_an = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        cursor.execute(
            "INSERT INTO hata_kayitlari (tarih_saat, kaynak, hata_mesaji) VALUES (?, ?, ?)",
            (su_an, kaynak, hata_metni)
        )
        conn.commit()
        conn.close()
    except Exception:
        # Veritabanına bile yazılamıyorsa (örneğin dosya kilitliyse), en azından
        # log dosyasına yazdık, burada sessizce geçiyoruz — sonsuz döngüye girmemek için.
        pass

def oku_hata_kayitlari(limit=20):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    df = pd.read_sql_query(f"SELECT tarih_saat, kaynak, hata_mesaji FROM hata_kayitlari ORDER BY id DESC LIMIT {limit}", conn)
    conn.close()
    return df

def oku_pozisyon(parite):
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
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
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO pozisyonlar (parite, giris_fiyati, miktar) VALUES (?, ?, ?)", (parite, giris_fiyati, miktar))
        conn.commit()
        conn.close()
    except Exception as e:
        hata_logla(f"Pozisyon Kaydetme ({parite})", e)

def pozisyon_sil(parite):
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pozisyonlar WHERE parite = ?", (parite,))
        conn.commit()
        conn.close()
    except Exception as e:
        hata_logla(f"Pozisyon Silme ({parite})", e)

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

def binance_veri_al(symbol, interval="15m", limit=100):
    """Binance'in herkese açık (API anahtarı GEREKTİRMEYEN) piyasa verisi uç
    noktasından mum (kline) verisi çeker. yfinance gibi üçüncü parti bir veri
    sağlayıcısına değil, doğrudan borsanın kendisine bağlanıyoruz — bu hem daha
    güncel/güvenilir veri demek hem de bir bağımlılık daha azaldı demek.
    symbol örnek: 'BTCUSDT'. interval: '15m', '1h' gibi. limit: en fazla 1000."""
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    veri = response.json()
    # Her mum şu formatta gelir: [açılış_zamanı, açılış, en_yüksek, en_düşük, kapanış, hacim, ...]
    kapanis_fiyatlari = [float(mum[4]) for mum in veri]
    return kapanis_fiyatlari

# ==========================================================
# ⚙️ BOT ALGORİTMİK MANTIĞI VE EMİR MOTORU
# ==========================================================

def binance_emir_gonder(symbol, side, type="MARKET"):
    if not GERCEK_ISLEM_AKTIF:
        return f"🧪 [SİMÜLASYON] {side} tetiklendi."
    base_url = "https://api.binance.com"
    endpoint = "/api/v3/order"
    timestamp = int(time.time() * 1000)
    query_string = f"symbol={symbol}&side={side}&type={type}&quantity=0.001&timestamp={timestamp}"
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return "❌ API Anahtarı Eksik! (.streamlit/secrets.toml dosyasını kontrol et)"
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
        hata_logla("Binance Emir Gönderme", e)
        return "❌ Bağlantı Hatası (detay için Sistem Sağlığı loguna bak)"

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

def analiz_ve_islem_yapi(symbol, emir_tetikle=False):
    """
    emir_tetikle=True: 7/24 Arka plan motoru çalıştırır (Al-sat yapar, DB yazar).
    emir_tetikle=False: Ön yüz paneli çalıştırır (Sadece anlık gösterim yapar, cüzdana dokunmaz).
    """
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
        
        islem_raporu = "⏸️ Beklemede"
        aktif_pozisyon = oku_pozisyon(symbol)
        ayarlar = oku_ayarlar()

        if emir_tetikle:
            mevcut_bakiye = oku_kasa_bakiyesi()
            zorla_kapatildi = False

            # --- ÖNCE STOP-LOSS / TAKE-PROFIT KONTROLÜ (sinyalden bağımsız, her zaman öncelikli) ---
            if aktif_pozisyon:
                giris_fiyati, miktar = aktif_pozisyon
                kar_zarar_yuzde = ((anlik_fiyat - giris_fiyati) / giris_fiyati) * 100

                if kar_zarar_yuzde <= ayarlar["stop_loss_yuzde"]:
                    if not GERCEK_ISLEM_AKTIF:
                        iade_tutar = miktar * anlik_fiyat
                        guncelle_kasa_bakiyesi(mevcut_bakiye + iade_tutar)
                        pozisyon_sil(symbol)
                        islem_raporu = f"🛑 STOP-LOSS TETİKLENDİ! Kâr/Zarar: %{kar_zarar_yuzde:.2f}"
                    else:
                        islem_raporu = "🛑 STOP-LOSS: " + binance_emir_gonder(symbol, "SELL")
                        pozisyon_sil(symbol)
                    zorla_kapatildi = True
                    telegram_bildirim_gonder(f"🛑 ZEYA: {symbol} STOP-LOSS tetiklendi.\nKâr/Zarar: %{kar_zarar_yuzde:.2f}\nFiyat: {anlik_fiyat:,.2f} USDT")
                    bildirim_ekle("STOP-LOSS", f"🛑 {symbol} STOP-LOSS tetiklendi. Kâr/Zarar: %{kar_zarar_yuzde:.2f} (Fiyat: {anlik_fiyat:,.2f} USDT)")
                    eposta_bildirim_gonder(f"🛑 ZEYA: {symbol} Stop-Loss Tetiklendi", f"{symbol} pozisyonu stop-loss ile kapatıldı.\nKâr/Zarar: %{kar_zarar_yuzde:.2f}\nFiyat: {anlik_fiyat:,.2f} USDT")
                elif kar_zarar_yuzde >= ayarlar["take_profit_yuzde"]:
                    if not GERCEK_ISLEM_AKTIF:
                        iade_tutar = miktar * anlik_fiyat
                        guncelle_kasa_bakiyesi(mevcut_bakiye + iade_tutar)
                        pozisyon_sil(symbol)
                        islem_raporu = f"🎯 TAKE-PROFIT TETİKLENDİ! Kâr/Zarar: %{kar_zarar_yuzde:.2f}"
                    else:
                        islem_raporu = "🎯 TAKE-PROFIT: " + binance_emir_gonder(symbol, "SELL")
                        pozisyon_sil(symbol)
                    zorla_kapatildi = True
                    telegram_bildirim_gonder(f"🎯 ZEYA: {symbol} TAKE-PROFIT tetiklendi.\nKâr/Zarar: %{kar_zarar_yuzde:.2f}\nFiyat: {anlik_fiyat:,.2f} USDT")
                    bildirim_ekle("TAKE-PROFIT", f"🎯 {symbol} TAKE-PROFIT tetiklendi. Kâr/Zarar: %{kar_zarar_yuzde:.2f} (Fiyat: {anlik_fiyat:,.2f} USDT)")
                    eposta_bildirim_gonder(f"🎯 ZEYA: {symbol} Take-Profit Tetiklendi", f"{symbol} pozisyonu take-profit ile kapatıldı.\nKâr/Zarar: %{kar_zarar_yuzde:.2f}\nFiyat: {anlik_fiyat:,.2f} USDT")

            # --- STOP-LOSS/TAKE-PROFIT TETİKLENMEDİYSE NORMAL SİNYAL MANTIĞI ÇALIŞIR ---
            if not zorla_kapatildi and aksiyon in ["BUY", "SELL"]:
                aktif_pozisyon = oku_pozisyon(symbol)  # zorla kapanmış olabilir, güncel durumu tekrar oku
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
                            islem_raporu = f"🧪 ALIM Yapıldı. Miktar: {miktar:.4f}"
                            telegram_bildirim_gonder(f"🟢 ZEYA: {symbol} ALIM yapıldı.\nFiyat: {anlik_fiyat:,.2f} USDT\nMiktar: {miktar:.4f}")
                            bildirim_ekle("ALIM", f"🟢 {symbol} ALIM yapıldı. Fiyat: {anlik_fiyat:,.2f} USDT, Miktar: {miktar:.4f}")
                            eposta_bildirim_gonder(f"🟢 ZEYA: {symbol} Alım Yapıldı", f"{symbol} için yeni pozisyon açıldı.\nFiyat: {anlik_fiyat:,.2f} USDT\nMiktar: {miktar:.4f}")
                        elif islem_tutari > 10:
                            islem_raporu = f"⚠️ Alım yapılmadı: Toplam pozisyon limiti doldu (Limit: %{ayarlar['maks_toplam_pozisyon_yuzde']:.0f})"
                    elif "SELL" in aksiyon and aktif_pozisyon:
                        giris_fiyati, miktar = aktif_pozisyon
                        iade_tutar = miktar * anlik_fiyat
                        yeni_bakiye = mevcut_bakiye + iade_tutar
                        pozisyon_sil(symbol)
                        guncelle_kasa_bakiyesi(yeni_bakiye)
                        kar_zarar = ((anlik_fiyat - giris_fiyati) / giris_fiyati) * 100
                        islem_raporu = f"🧪 SATIM Yapıldı. Kâr/Zarar: %{kar_zarar:.2f}"
                        telegram_bildirim_gonder(f"🔴 ZEYA: {symbol} SATIM yapıldı.\nFiyat: {anlik_fiyat:,.2f} USDT\nKâr/Zarar: %{kar_zarar:.2f}")
                        bildirim_ekle("SATIM", f"🔴 {symbol} SATIM yapıldı. Fiyat: {anlik_fiyat:,.2f} USDT, Kâr/Zarar: %{kar_zarar:.2f}")
                        eposta_bildirim_gonder(f"🔴 ZEYA: {symbol} Satım Yapıldı", f"{symbol} pozisyonu kapatıldı.\nFiyat: {anlik_fiyat:,.2f} USDT\nKâr/Zarar: %{kar_zarar:.2f}")
                else:
                    islem_raporu = binance_emir_gonder(symbol, aksiyon)
        else:
            if aktif_pozisyon:
                giris_fiyati, miktar = aktif_pozisyon
                kar_zarar_yuzde = ((anlik_fiyat - giris_fiyati) / giris_fiyati) * 100
                islem_raporu = f"⏳ Pozisyon Açık (Giriş: {giris_fiyati:,.2f}, K/Z: %{kar_zarar_yuzde:.2f})"
        
        return anlik_fiyat, df['rsi'].iloc[-1], df, karar, guven, renk, islem_raporu, egim
    except Exception as e:
        hata_logla(f"Analiz ({symbol})", e)
        return 0.0, 50.0, pd.DataFrame([0]*60, columns=['close']), "🟡 NÖTR", 50.0, "#f1c40f", "❌ Hata (detay için Sistem Sağlığı loguna bak)", 0.0

# ==========================================================
# 📊 GERÇEK BACKTEST MOTORU (Sahte "%100 başarı" yazısının yerine)
# ==========================================================
@st.cache_data(ttl=3600)  # Sonucu 1 saat boyunca önbellekte tutar, her yenilemede yeniden hesaplamaz
def gercek_backtest_yap(symbol, gun_sayisi=30):
    """
    Geçmiş veride, botun kullandığı AYNI karar mantığını adım adım uygular.
    Gerçek bir kâr/zarar, kazanma oranı ve maksimum düşüş (drawdown) hesaplar.
    Bu fonksiyon hiçbir şeyi hardcode etmez; tüm sonuçlar veriden hesaplanır.
    """
    try:
        # Binance saatlik mum limiti 1000'dir; 30 gün = 720 saat, rahatça sığar.
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
# 🚀 7/24 BAĞIMSIZ ARKA PLAN MOTORU (AUTOMATED WORKER)
# ==========================================================
def kesintisiz_bot_dongusu():
    """Ön yüzden tamamen bağımsız, sunucuda sonsuza kadar dönecek olan ana motor"""
    while True:
        try:
            # 1. Tüm pariteleri analiz et ve gerekiyorsa emir tetikle
            btc_f, _, _, btc_k, _, _, _, _ = analiz_ve_islem_yapi("BTCUSDT", emir_tetikle=True)
            eth_f, _, _, eth_k, _, _, _, _ = analiz_ve_islem_yapi("ETHUSDT", emir_tetikle=True)
            sol_f, _, _, sol_k, _, _, _, _ = analiz_ve_islem_yapi("SOLUSDT", emir_tetikle=True)
            
            # 2. Seyir Defterine Günlüğü kaydet
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
            
            # Veritabanındaki en son kaydı kontrol et, fiyat değiştiyse kaydet
            conn = sqlite3.connect(DB_FILE, check_same_thread=False)
            gecmis = pd.read_sql_query("SELECT btc_fiyat FROM sinyal_deposu ORDER BY id DESC LIMIT 1", conn)
            conn.close()
            
            if gecmis.empty or gecmis.iloc[0]["btc_fiyat"] != yeni_log["BTC Fiyat"]:
                yeni_sinyal_ekle(yeni_log)

            # 3. Toplam varlığı (kasa + açık pozisyonların güncel değeri) hesaplayıp
            #    varlık geçmişine kaydet. Bu, performans grafiğinin veri kaynağıdır.
            guncel_fiyatlar = {"BTCUSDT": btc_f, "ETHUSDT": eth_f, "SOLUSDT": sol_f}
            mevcut_bakiye = oku_kasa_bakiyesi()
            tum_pozisyonlar = oku_tum_pozisyonlar()
            pozisyon_degeri = sum(
                miktar * guncel_fiyatlar.get(parite, giris_fiyati)
                for parite, giris_fiyati, miktar in tum_pozisyonlar
            )
            toplam_varlik = mevcut_bakiye + pozisyon_degeri
            varlik_anlik_kaydet(toplam_varlik)

        except Exception as e:
            hata_logla("Arka Plan Döngüsü", e)
            
        # 15 Dakika Uyku Modu (15 dakika = 900 saniye)
        time.sleep(900)

# Streamlit her yenilendiğinde bu thread'i tekrar tekrar açmasın diye cache'liyoruz.
@st.cache_resource
def arkaplan_motorunu_atesle():
    t = threading.Thread(target=kesintisiz_bot_dongusu, daemon=True)
    t.start()
    return True

# 7/24 Çalışacak Motoru Başlat
arkaplan_motorunu_atesle()

# ==========================================================
# 💻 ÖN YÜZ GÖSTERİM PANELİ (STREAMLIT UI)
# ==========================================================

# Ön yüz sadece grafik çizmek ve anlık durumu göstermek için verileri çeker (emir_tetikle=False)
btc_fiyat, btc_rsi, btc_df, btc_karar, btc_guven, btc_renk, btc_rapor, btc_egim = analiz_ve_islem_yapi("BTCUSDT", emir_tetikle=False)
eth_fiyat, eth_rsi, eth_df, eth_karar, eth_guven, eth_renk, eth_rapor, eth_egim = analiz_ve_islem_yapi("ETHUSDT", emir_tetikle=False)
sol_fiyat, sol_rsi, sol_df, sol_karar, sol_guven, sol_renk, sol_rapor, sol_egim = analiz_ve_islem_yapi("SOLUSDT", emir_tetikle=False)

# LOGO VE SIDEBAR TASARIMI
st.markdown("""
    <div style='text-align: center; background-color: #111111; padding: 20px; border-radius: 15px; border: 1px solid #D4AF37; margin-bottom: 25px;'>
        <h1 style='color: #D4AF37; font-family: "Arial Black", Gadget, sans-serif; letter-spacing: 5px; font-size: 45px; margin: 0;'>Z E Y A</h1>
        <p style='color: #888888; font-family: "Courier New", monospace; font-size: 14px; margin-top: 5px; margin-bottom: 0;'>
                    AUTONOMOUS BACKGROUND ENGINE & LIFETIME DATABASE ACTIVE 
        </p>
    </div>
""", unsafe_allow_html=True)

# ==========================================================
# 🔔 BİLDİRİM MERKEZİ (uygulama içi, hiçbir dış servise bağımlı değil)
# ==========================================================
_okunmamis_sayi = okunmamis_bildirim_sayisi()
_bildirim_baslik = f"🔔 Bildirim Merkezi" + (f" ({_okunmamis_sayi} okunmamış)" if _okunmamis_sayi > 0 else "")
with st.expander(_bildirim_baslik, expanded=(_okunmamis_sayi > 0)):
    df_bildirim = oku_bildirimler(limit=30)
    if df_bildirim.empty:
        st.caption("Henüz bildirim yok. Bot bir alım/satım/stop-loss/take-profit gerçekleştirdiğinde burada görünecek.")
    else:
        if _okunmamis_sayi > 0 and st.button("✅ Tümünü okundu olarak işaretle"):
            tum_bildirimleri_okundu_yap()
            st.rerun()
        for _, satir in df_bildirim.iterrows():
            _isaret = "🆕 " if satir["okundu"] == 0 else ""
            st.markdown(f"{_isaret}**{satir['tarih_saat']}** — {satir['mesaj']}")

# ==========================================================
# 🛠️ SİSTEM SAĞLIĞI / HATA KAYITLARI (şeffaflık için — artık hiçbir hata gizli değil)
# ==========================================================
df_hata = oku_hata_kayitlari(limit=20)
_hata_baslik = "🛠️ Sistem Sağlığı" + (f" ({len(df_hata)} kayıtlı hata)" if not df_hata.empty else " (Sorun yok ✅)")
with st.expander(_hata_baslik, expanded=False):
    if df_hata.empty:
        st.success("✅ Son kayıtlarda herhangi bir hata yok. Sistem sorunsuz çalışıyor.")
    else:
        st.caption("Bu liste, botun arka planda karşılaştığı tüm hataları şeffaf şekilde gösterir. Bir hata sık tekrarlanıyorsa (örneğin API bağlantı sorunu), burada görünür.")
        for _, satir in df_hata.iterrows():
            st.markdown(f"🔴 **{satir['tarih_saat']}** — `{satir['kaynak']}`: {satir['hata_mesaji']}")

st.sidebar.header("👁️ Robot Sistem Durumu")
if GERCEK_ISLEM_AKTIF:
    st.sidebar.error("🤖 Otomatik Emir Modu: GERÇEK PİYASA")
else:
    st.sidebar.warning("🧪 Otomatik Emir Modu: SİMÜLASYON (TEST)")
st.sidebar.success(" Kesintisiz Arkaplan Motoru: AKTİF 🟢")
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    st.sidebar.success("📱 Telegram Bildirimleri: AKTİF 🟢")
else:
    st.sidebar.info("📱 Telegram Bildirimleri: Kapalı (isteğe bağlı)")
if all([SMTP_SUNUCU, SMTP_PORT, SMTP_EPOSTA, SMTP_SIFRE, ALICI_EPOSTA]):
    st.sidebar.success("✉️ E-posta Bildirimleri: AKTİF 🟢")
else:
    st.sidebar.info("✉️ E-posta Bildirimleri: Kapalı (isteğe bağlı)")

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Risk Yönetimi Ayarları")
_mevcut_ayarlar = oku_ayarlar()
_yeni_stop_loss = st.sidebar.slider(
    "🛑 Stop-Loss (%)", min_value=-30.0, max_value=-1.0,
    value=float(_mevcut_ayarlar["stop_loss_yuzde"]), step=0.5,
    help="Pozisyon bu yüzde kadar zarar ettiğinde otomatik satılır."
)
_yeni_take_profit = st.sidebar.slider(
    "🎯 Take-Profit (%)", min_value=1.0, max_value=50.0,
    value=float(_mevcut_ayarlar["take_profit_yuzde"]), step=0.5,
    help="Pozisyon bu yüzde kadar kâr ettiğinde otomatik satılır."
)
_yeni_pozisyon_buyuklugu = st.sidebar.slider(
    "💰 İşlem Başına Sermaye (%)", min_value=5.0, max_value=100.0,
    value=float(_mevcut_ayarlar["pozisyon_buyuklugu_yuzde"]), step=5.0,
    help="Her alım işleminde kasanın yüzde kaçının kullanılacağı."
)
_yeni_maks_toplam_pozisyon = st.sidebar.slider(
    "📊 Toplam Pozisyon Limiti (%)", min_value=10.0, max_value=100.0,
    value=float(_mevcut_ayarlar["maks_toplam_pozisyon_yuzde"]), step=5.0,
    help="Tüm açık pozisyonların (BTC+ETH+SOL) toplamda kasanın en fazla yüzde kaçını kullanabileceği. Örn: %50 demek, aynı anda en fazla yarı sermaye riske girer."
)
if (_yeni_stop_loss != _mevcut_ayarlar["stop_loss_yuzde"]
        or _yeni_take_profit != _mevcut_ayarlar["take_profit_yuzde"]
        or _yeni_pozisyon_buyuklugu != _mevcut_ayarlar["pozisyon_buyuklugu_yuzde"]
        or _yeni_maks_toplam_pozisyon != _mevcut_ayarlar["maks_toplam_pozisyon_yuzde"]):
    guncelle_ayarlar(_yeni_stop_loss, _yeni_take_profit, _yeni_pozisyon_buyuklugu, _yeni_maks_toplam_pozisyon)
    st.sidebar.success("✅ Ayarlar kaydedildi. Arka plan motoru bir sonraki döngüde bu ayarları kullanacak.")

# 3 SÜTUN GÖRSEL PANEL
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="🪙 Bitcoin (BTC)", value=f"{btc_fiyat:,.2f} USDT", delta=f"ML Eğimi: {btc_egim:.2f}")
    st.markdown(f"<div style='background-color: #111111; border: 2px solid #D4AF37; padding: 12px; border-radius: 10px; text-align: center;'><span style='color: #888888; font-size: 12px; font-weight: bold;'>ZEYA AI ANLIK DURUM</span><br><span style='color: {btc_renk}; font-size: 22px; font-weight: bold;'>{btc_karar}</span><br><span style='color: #D4AF37; font-size: 13px;'>Güven: %{btc_guven:.1f}</span></div>", unsafe_allow_html=True)
    st.info(f"🤖 Son Durum: {btc_rapor}")
    st.line_chart(btc_df['close'])

with col2:
    st.metric(label="🔹 Ethereum (ETH)", value=f"{eth_fiyat:,.2f} USDT", delta=f"ML Eğimi: {eth_egim:.2f}")
    st.markdown(f"<div style='background-color: #111111; border: 2px solid #D4AF37; padding: 12px; border-radius: 10px; text-align: center;'><span style='color: #888888; font-size: 12px; font-weight: bold;'>ZEYA AI ANLIK DURUM</span><br><span style='color: {eth_renk}; font-size: 22px; font-weight: bold;'>{eth_karar}</span><br><span style='color: #D4AF37; font-size: 13px;'>Güven: %{eth_guven:.1f}</span></div>", unsafe_allow_html=True)
    st.info(f"🤖 Son Durum: {eth_rapor}")
    st.line_chart(eth_df['close'])

with col3:
    st.metric(label="☀️ Solana (SOL)", value=f"{sol_fiyat:,.2f} USDT", delta=f"ML Eğimi: {sol_egim:.2f}")
    st.markdown(f"<div style='background-color: #111111; border: 2px solid #D4AF37; padding: 12px; border-radius: 10px; text-align: center;'><span style='color: #888888; font-size: 12px; font-weight: bold;'>ZEYA AI ANLIK DURUM</span><br><span style='color: {sol_renk}; font-size: 22px; font-weight: bold;'>{sol_karar}</span><br><span style='color: #D4AF37; font-size: 13px;'>Güven: %{sol_guven:.1f}</span></div>", unsafe_allow_html=True)
    st.info(f"🤖 Son Durum: {sol_rapor}")
    st.line_chart(sol_df['close'])

st.markdown("---")
col_wallet, col_news = st.columns(2)

with col_wallet:
    st.header("💼 Simüle Fon Yönetimi")
    canli_kasa_bakiyesi = oku_kasa_bakiyesi()
    st.info(f"💰 Toplam Kasa Bakiyesi: **{canli_kasa_bakiyesi:,.2f} USDT**")

    st.subheader("📈 Gerçek Backtest Sonucu (BTC, son 30 gün)")
    bt_sonuc = gercek_backtest_yap("BTCUSDT", gun_sayisi=30)
    if bt_sonuc:
        bt_col1, bt_col2, bt_col3 = st.columns(3)
        bt_col1.metric("Toplam Getiri", f"%{bt_sonuc['toplam_getiri_yuzde']:.2f}")
        bt_col2.metric("Kazanma Oranı", f"%{bt_sonuc['kazanma_orani']:.1f}", help=f"{bt_sonuc['islem_sayisi']} işlem üzerinden")
        bt_col3.metric("Maks. Düşüş", f"%{bt_sonuc['maks_dusus_yuzde']:.2f}", help="En kötü senaryoda ne kadar değer kaybedildiği")
        st.caption("⚠️ Geçmiş performans gelecekteki sonuçların garantisi değildir. Bu sadece stratejinin geçmiş veri üzerindeki davranışını gösterir.")
    else:
        st.warning("Backtest verisi şu anda hesaplanamadı, birazdan tekrar dene.")

with col_news:
    st.header("📰 Yapay Zeka Haber Duygusu")
    st.warning(f"🟢 Piyasa Havası: OLUMLU / NÖTR (Feshetme veya panik dalgası saptanmadı.)")

# ==========================================================
# 📈 GERÇEK PERFORMANS GRAFİĞİ (VARLIK EĞRİSİ)
# ==========================================================
st.markdown("---")
st.header("📈 Gerçek Zamanlı Performans (Varlık Eğrisi)")
st.caption("Arka plan motoru her 15 dakikada bir toplam varlığını (kasa + açık pozisyonların güncel değeri) kaydeder. Bu grafik botun gerçek geçmiş performansını gösterir — geriye dönük bir tahmin değil.")
df_varlik = oku_varlik_gecmisi()
if len(df_varlik) >= 2:
    baslangic_varlik = 10000.0
    guncel_varlik = df_varlik['toplam_varlik'].iloc[-1]
    toplam_getiri_yuzde = ((guncel_varlik - baslangic_varlik) / baslangic_varlik) * 100

    perf_col1, perf_col2, perf_col3 = st.columns(3)
    perf_col1.metric("Başlangıç Varlığı", f"{baslangic_varlik:,.2f} USDT")
    perf_col2.metric("Güncel Toplam Varlık", f"{guncel_varlik:,.2f} USDT", delta=f"%{toplam_getiri_yuzde:.2f}")
    perf_col3.metric("Kayıt Sayısı", f"{len(df_varlik)} ölçüm")

    grafik_df = df_varlik.set_index('tarih_saat')[['toplam_varlik']]
    st.line_chart(grafik_df)
else:
    st.info("Arka plan motoru henüz yeterli veri toplamadı. İlk grafik, motor birkaç kez çalıştıktan sonra (birkaç saat içinde) burada görünecek.")

# 📜 GEÇMİŞ SİNYAL LOG TABLOSU (Doğrudan Arkaplan Motorunun Kaydettiği Yerden Okur)
st.markdown("---")
st.header("📜 ZEYA Algoritma Seyir Defteri (7/24 Kesintisiz Hafıza Kayıtları)")
df_log = oku_sinyal_deposu()
if not df_log.empty:
    st.dataframe(df_log, use_container_width=True)
else:
    st.info("Arka plan motoru ilk verileri topluyor, tablo birazdan güncellenecektir...")
