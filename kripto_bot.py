import requests
import time
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from textblob import TextBlob
from sklearn.linear_model import LinearRegression

# --- TELEGRAM AYARLARI ---
TELEGRAM_TOKEN = "8439824799:AAFibuXa3_lLk_yKw39kyhACwElNRCv3wdc"
TELEGRAM_CHAT_ID = "6960254955"

def telegram_mesaj_gonder(mesaj):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mesaj}
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram mesajı gönderilemedi: {e}")

# --- YAPAY ZEKA HABER ANALİZİ ---
def haber_duygusu_analiz_et():
    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        cevap = requests.get(url).json()
        en_son_haber = cevap['Data'][0]['title']
        analiz = TextBlob(en_son_haber)
        return en_son_haber, analiz.sentiment.polarity
    except:
        return "Haber alınamadı", 0.0

# --- MAKİNE ÖĞRENMESİ TREND YÖNÜ TAHMİNİ ---
def makine_ogrenmesi_trend_oku(fiyatlar):
    try:
        # Son fiyat hareketlerini yapay zekaya öğretmek için matrise çeviriyoruz
        X = np.array(range(len(fiyatlar))).reshape(-1, 1)
        y = np.array(fiyatlar)
        
        model = LinearRegression()
        model.fit(X, y) # Yapay zeka şu an trendi öğrendi
        
        eğim = model.coef_[0] # Trend çizgisinin yönü (eğimi)
        return eğim
    except:
        return 0.0

# --- BOTUN AYARLARI ---
coin_listesi = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
bakiye_nakit = 10000.0  
bakiye_coin = 0.0        
alinan_fiyat = 0.0      
en_yuksek_fiyat = 0.0  
pozisyonda_miyiz = False 
aktif_coin = None       

RSI_ALIM_SEVIYESI = 30  
IZ_SUREN_TAKIP_ORANI = 0.01  
ILK_STOP_LOSS_ORANI = 0.99   

fiyat_hafizalari = {coin: [] for coin in coin_listesi}

print("=== NİHAİ YAPAY ZEKA VE MAKİNE ÖĞRENMELİ BOT BAŞLATILDI ===")
telegram_mesaj_gonder("👑 PROJE TAMAMLANDI! Botunuz Çoklu Tarama, Çift İndikatör, Haber Analizi ve Makine Öğrenmesi (Regresyon) beyniyle yayında!")

# --- CANLI TİCARET DÖNGÜSÜ ---
while True:
    try:
        son_haber, duygu_skoru = haber_duygusu_analiz_et()
        piyasa_havasi = "🟢 OLUMLU/NÖTR" if duygu_skoru >= -0.2 else "🔴 KORKU"

        # KOŞUL 1: NAKTTEYSEK TARA
        if not pozisyonda_miyiz:
            for coin in coin_listesi:
                binance_url = f"https://api.binance.com/api/v3/ticker/price?symbol={coin}"
                anlik_fiyat = float(requests.get(binance_url).json()['price'])
                
                fiyat_hafizalari[coin].append(anlik_fiyat)
                if len(fiyat_hafizalari[coin]) > 30: 
                    fiyat_hafizalari[coin].pop(0)
                
                if len(fiyat_hafizalari[coin]) >= 20:
                    df = pd.DataFrame(fiyat_hafizalari[coin], columns=['close'])
                    
                    # İndikatörler
                    guncel_rsi = RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
                    alt_band = BollingerBands(close=df['close'], window=20, window_dev=2).bollinger_lband().iloc[-1]
                    
                    # Makine Öğrenmesi Trend Eğimi Hesaplama
                    trend_egimi = makine_ogrenmesi_trend_oku(fiyat_hafizalari[coin])
                    trend_durumu = "📈 YUKARI" if trend_egimi > 0 else "📉 AŞAĞI"
                    
                    print(f"[{coin}] RSI: {guncel_rsi:.1f} | ML Trend: {trend_durumu} | Haber: {piyasa_havasi}      ", end="\r")
                    
                    # 4 KATMANLI DEV ONAY MEKANİZMASI
                    # 1. RSI Dipte olacak + 2. Fiyat Bollinger Alt Bantta olacak + 3. Haberler felaket olmayacak + 4. YAPAY ZEKA TRENDİ YUKARI GÖSTERECEK!
                    if guncel_rsi <= RSI_ALIM_SEVIYESI and anlik_fiyat <= alt_band and duygu_skoru >= -0.2 and trend_egimi > 0:
                        aktif_coin = coin
                        bakiye_coin = bakiye_nakit / anlik_fiyat
                        bakiye_nakit = 0.0
                        alinan_fiyat = anlik_fiyat
                        en_yuksek_fiyat = anlik_fiyat
                        pozisyonda_miyiz = True
                        
                        telegram_mesaj_gonder(f"👑 [NİHAİ YAPAY ZEKA ALIM SİNYALİ]\nCoin: {aktif_coin}\n🤖 ML Trendi: YUKARI İVME ONAYLANDI!\n📈 RSI: {guncel_rsi:.2f}\n💵 Alış Fiyatı: {alinan_fiyat:.2f} USDT")
                        break 
                else:
                    print(f"[YAPAY ZEKA ÖĞRENİYOR] {coin} ({len(fiyat_hafizalari[coin])}/20)...      ", end="\r")
                
                time.sleep(0.4)

        # KOŞUL 2: POZİSYONDAYSAK İZ SÜREN STOP
        elif pozisyonda_miyiz:
            binance_url = f"https://api.binance.com/api/v3/ticker/price?symbol={aktif_coin}"
            anlik_fiyat = float(requests.get(binance_url).json()['price'])
            
            if anlik_fiyat > en_yuksek_fiyat:
                en_yuksek_fiyat = anlik_fiyat
                
            iz_suren_stop_seviyesi = en_yuksek_fiyat * (1 - IZ_SUREN_TAKIP_ORANI)
            ilk_acil_stop = alinan_fiyat * ILK_STOP_LOSS_ORANI
            guncel_aktif_stop = max(iz_suren_stop_seviyesi, ilk_acil_stop)
            
            print(f"[{aktif_coin}] Fiyat: {anlik_fiyat:.2f} | İz Süren Stop: {guncel_aktif_stop:.2f}      ", end="\r")
            
            if anlik_fiyat <= guncel_aktif_stop:
                bakiye_nakit = bakiye_coin * anlik_fiyat
                fark = bakiye_nakit - 10000.0
                
                if fark >= 0:
                    telegram_mesaj_gonder(f"💰 [MÜKEMMEL YAPAY ZEKA SATIŞI]\nCoin: {aktif_coin}\nNet Kâr: {fark:.2f} USDT\n🔍 Yeni avlar için piyasaya dönüyorum.")
                else:
                    telegram_mesaj_gonder(f"🚨 [KORUMA STOPU ÇALIŞTI]\nCoin: {aktif_coin} için risk yönetimi yapıldı.\nNet Zarar: {fark:.2f} USDT")
                
                bakiye_coin = 0.0
                pozisyonda_miyiz = False
                aktif_coin = None
                
            time.sleep(1)
            
    except Exception as hata:
        print(f"\nBağlantı hatası: {hata}")
        time.sleep(2)