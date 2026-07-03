import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
import ta

# --- 1. SAYFA YAPILANDIRMASI ---
st.set_page_config(page_title="ZEYA - Laboratuvar Geliştirme Paneli", layout="wide")

# --- 2. YENİ GELİŞMİŞ ÖZELLİK AYARLARI ---
GERCEK_ISLEM_AKTIF = False  
STOP_LOSS_ORAN = 0.02      # %2 Zarar Durdurma
TAKE_PROFIT_ORAN = 0.04    # %4 Kâr Alma

# --- 3. YENİ GELİŞMİŞ ÖZELLİK: CÜZDAN VE SEYİR DEFTERİ HAFIZASI ---
if "simule_bakiye" not in st.session_state:
    st.session_state.simule_bakiye = 10000.0  

if "aktif_pozisyonlar" not in st.session_state:
    st.session_state.aktif_pozisyonlar = {}  

if "seyir_defteri" not in st.session_state:
    st.session_state.seyir_defteri = pd.DataFrame(columns=[
        "Zaman Damgası", "Parite", "İşlem Tipi", "Fiyat (USDT)", "Miktar", "Toplam Tutar", "Kasa Bakiyesi", "Açıklama"
    ])

# --- 4. ASIL UYGULAMANIN VERİ MOTORU ---
@st.cache_data(ttl=60)
def get_binance_data(symbol="BTCUSDT", interval="15m", limit=200):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms') + timedelta(hours=3)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        st.error(f"Binance API Bağlantı Hatası: {e}")
        return pd.DataFrame()

# --- 5. ASIL UYGULAMANIN TEKNİK ANALİZ VE YAPAY ZEKA MODELİ ---
def analiz_et_ve_karar_ver(df):
    if df.empty or len(df) < 30:
        return "NÖTR", 0.0, df

    df['rsi'] = ta.momentum.rsi(df['close'], window=14)
    macd = ta.trend.MACD(df['close'])
    df['macd_diff'] = macd.macd_diff()
    df['ma50'] = ta.trend.sma_indicator(df['close'], window=50)

    X = np.array(range(10)).reshape(-1, 1)
    y = df['close'].iloc[-10:].values
    model = LinearRegression().fit(X, y)
    eğim = model.coef_[0]

    son_close = df['close'].iloc[-1]
    son_rsi = df['rsi'].iloc[-1]
    son_macd = df['macd_diff'].iloc[-1]
    son_ma50 = df['ma50'].iloc[-1]

    skor = 0
    if son_rsi < 40: skor += 1
    if son_macd > 0: skor += 1
    if son_close > son_ma50: skor += 1
    if eğim > 0: skor += 1

    guven_orani = (skor / 4.0) * 100

    if skor >= 3:
        karar = "AL"
    elif skor <= 1:
        karar = "SAT"
    else:
        karar = "NÖTR"

    return karar, guven_orani, df

# --- 6. YENİ GELİŞMİŞ ÖZELLİK: RISK VE CÜZDAN YÖNETİM MOTORU ---
def simule_cuzdan_motoru(symbol, son_fiyat, karar, guven_orani):
    zaman_simdi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if symbol in st.session_state.aktif_pozisyonlar:
        pozisyon = st.session_state.aktif_pozisyonlar[symbol]
        giris_fiyati = pozisyon['giris_fiyati']
        miktar = pozisyon['miktar']
        degisim = (son_fiyat - giris_fiyati) / giris_fiyati
        
        # %2 Otomatik Stop-Loss
        if degisim <= -STOP_LOSS_ORAN:
            iade_tutar = miktar * son_fiyat
            st.session_state.simule_bakiye += iade_tutar
            del st.session_state.aktif_pozisyonlar[symbol]
            
            yeni_log = pd.DataFrame([{
                "Zaman Damgası": zaman_simdi, "Parite": symbol, "İşlem Tipi": "STOP-LOSS (SAT)",
                "Fiyat (USDT)": son_fiyat, "Miktar": miktar, "Toplam Tutar": round(iade_tutar, 2),
                "Kasa Bakiyesi": round(st.session_state.simule_bakiye, 2),
                "Açıklama": f"ZEYA Risk Koruması: %{abs(round(degisim*100,2))} zararla pozisyon stoplandı."
            }])
            st.session_state.seyir_defteri = pd.concat([yeni_log, st.session_state.seyir_defteri], ignore_index=True)
            
        # %4 Otomatik Kâr Al (Take-Profit)
        elif degisim >= TAKE_PROFIT_ORAN:
            iade_tutar = miktar * son_fiyat
            st.session_state.simule_bakiye += iade_tutar
            del st.session_state.aktif_pozisyonlar[symbol]
            
            yeni_log = pd.DataFrame([{
                "Zaman Damgası": zaman_simdi, "Parite": symbol, "İşlem Tipi": "TAKE-PROFIT (SAT)",
                "Fiyat (USDT)": son_fiyat, "Miktar": miktar, "Toplam Tutar": round(iade_tutar, 2),
                "Kasa Bakiyesi": round(st.session_state.simule_bakiye, 2),
                "Açıklama": f"Hedef Değer: %{round(degisim*100,2)} kâr realize edildi!"
            }])
            st.session_state.seyir_defteri = pd.concat([yeni_log, st.session_state.seyir_defteri], ignore_index=True)

    else:
        if karar == "AL" and st.session_state.simule_bakiye > 100:
            islem_tutari = st.session_state.simule_bakiye * 0.25
            st.session_state.simule_bakiye -= islem_tutari
            miktar = islem_tutari / son_fiyat
            
            st.session_state.aktif_pozisyonlar[symbol] = {
                'giris_fiyati': son_fiyat,
                'miktar': miktar,
                'zaman': zaman_simdi
            }
            
            yeni_log = pd.DataFrame([{
                "Zaman Damgası": zaman_simdi, "Parite": symbol, "İşlem Tipi": "ALIM (BUY)",
                "Fiyat (USDT)": son_fiyat, "Miktar": round(miktar, 4), "Toplam Tutar": round(islem_tutari, 2),
                "Kasa Bakiyesi": round(st.session_state.simule_bakiye, 2),
                "Açıklama": f"Yapay Zeka AL Sinyali (Güven: %{round(guven_orani,1)}). Pozisyon açıldı."
            }])
            st.session_state.seyir_defteri = pd.concat([yeni_log, st.session_state.seyir_defteri], ignore_index=True)
            
        elif karar == "SAT" and symbol in st.session_state.aktif_pozisyonlar:
            pozisyon = st.session_state.aktif_pozisyonlar[symbol]
            eski_miktar = pozisyon['miktar']
            iade_tutar = eski_miktar * son_fiyat
            st.session_state.simule_bakiye += iade_tutar
            del st.session_state.aktif_pozisyonlar[symbol]
            
            yeni_log = pd.DataFrame([{
                "Zaman Damgası": zaman_simdi, "Parite": symbol, "İşlem Tipi": "SİNYAL ÇIKIŞI (SAT)",
                "Fiyat (USDT)": son_fiyat, "Miktar": eski_miktar, "Toplam Tutar": round(iade_tutar, 2),
                "Kasa Bakiyesi": round(st.session_state.simule_bakiye, 2),
                "Açıklama": f"Yapay zeka trend dönüşü algıladı ve pozisyondan çıktı."
            }])
            st.session_state.seyir_defteri = pd.concat([yeni_log, st.session_state.seyir_defteri], ignore_index=True)

# --- 7. BİREBİR ASIL UYGULAMA ARAYÜZÜ VE YENİ METRİKLER ---
st.title("🪙 ZEYA QUANT ALGORİTMASI SİMÜLASYONU")
st.subheader("Yapay Zeka ve Matematiksel Risk Yönetim Motoru")

# Şık ve modern metrik alanı
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="💼 Toplam Simüle Nakit", value=f"{round(st.session_state.simule_bakiye, 2)} USDT")
with col2:
    st.metric(label="📊 Açık Pozisyon Sayısı", value=f"{len(st.session_state.aktif_pozisyonlar)} Adet")
with col3:
    st.metric(label="🛡️ Koruma (Stop-Loss)", value=f"% {int(STOP_LOSS_ORAN * 100)}")
with col4:
    st.metric(label="🎯 Hedef (Take-Profit)", value=f"% {int(TAKE_PROFIT_ORAN * 100)}")

st.markdown("---")

pariteler = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# Asıl uygulamadaki grafiklerin ve analizlerin birebir döngüsü
for parite in pariteler:
    df = get_binance_data(symbol=parite, interval="15m", limit=100)
    if not df.empty:
        karar, guven_orani, df_analiz = analiz_et_ve_karar_ver(df)
        son_fiyat = df_analiz['close'].iloc[-1]
        
        # Arka planda gelişmiş cüzdan motorunu çalıştır
        simule_cuzdan_motoru(parite, son_fiyat, karar, guven_orani)
        
        # Birebir asıl uygulama başlık ve sinyal yapısı
        p_col1, p_col2, p_col3 = st.columns([2, 1, 1])
        with p_col1:
            st.markdown(f"### 📈 {parite} 15 Dakikalık Canlı Grafik")
        with p_col2:
            st.metric(label="Anlık Fiyat", value=f"{son_fiyat} USDT")
        with p_col3:
            renk = "🟢" if karar == "AL" else "🔴" if karar == "SAT" else "⚪"
            st.metric(label="ZEYA Kararı", value=f"{renk} {karar}", delta=f"Güven: %{int(guven_orani)}")
        
        # Birebir asıl uygulama çizgi grafiği
        chart_data = df_analiz.set_index('timestamp')['close']
        st.line_chart(chart_data, use_container_width=True)
        st.markdown("---")

# --- YENİ GELİŞMİŞ ÖZELLİKLERİN TABLOLARI ---
st.markdown("### 💼 Mevcut Açık Pozisyonlar")
if st.session_state.aktif_pozisyonlar:
    poz_df = pd.DataFrame.from_dict(st.session_state.aktif_pozisyonlar, orient='index').reset_index()
    poz_df.columns = ["Parite", "Giriş Fiyatı", "Miktar", "Giriş Zamanı"]
    st.dataframe(poz_df, use_container_width=True)
else:
    st.info("Şu an açıkta pozisyon bulunmuyor. ZEYA strateji doğrultusunda 'AL' sinyali bekliyor.")

st.markdown("### 📜 ZEYA Gelişmiş Algoritma Seyir Defteri")
if not st.session_state.seyir_defteri.empty:
    st.dataframe(st.session_state.seyir_defteri, use_container_width=True)
else:
    st.text("Henüz bir işlem veya risk tetiklenmesi gerçekleşmedi. İzleniyor...")
