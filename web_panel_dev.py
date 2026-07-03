import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
import ta

# --- 1. ASIL UYGULAMANIN GÜVENLİ SAYFA AYARLARI ---
st.set_page_config(page_title="ZEYA - Kripto Ticaret Paneli", layout="wide")

# --- 2. YENİ LABORATUVAR KASA VE RISK HAFIZASI ---
STOP_LOSS_ORAN = 0.02
TAKE_PROFIT_ORAN = 0.04

if "simule_bakiye" not in st.session_state:
    st.session_state.simule_bakiye = 10000.0
if "aktif_pozisyonlar" not in st.session_state:
    st.session_state.aktif_pozisyonlar = {}
if "seyir_defteri" not in st.session_state:
    st.session_state.seyir_defteri = pd.DataFrame(columns=[
        "Zaman Damgası", "Parite", "İşlem Tipi", "Fiyat (USDT)", "Miktar", "Toplam Tutar", "Kasa Bakiyesi", "Açıklama"
    ])

# --- 3. VERİ MOTORU ---
@st.cache_data(ttl=15)
def get_binance_data(symbol="BTCUSDT", interval="15m", limit=100):
    urls = [
        f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}",
        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    ]
    for url in urls:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'
                ])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms') + timedelta(hours=3)
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                return df
        except:
            continue
            
    # Bağlantı koptuğunda asıl uygulamanın fiyatlarını taban alan yedek mod
    fiyatlar = {"BTCUSDT": 61849.0, "ETHUSDT": 1732.0, "SOLUSDT": 81.0}
    taban_fiyat = fiyatlar.get(symbol, 100.0)
    saat_serisi = [datetime.now() - timedelta(minutes=15*i) for i in range(limit)][::-1]
    df_fake = pd.DataFrame({
        'timestamp': saat_serisi,
        'open': np.linspace(taban_fiyat - 50, taban_fiyat + 50, limit),
        'high': np.linspace(taban_fiyat, taban_fiyat + 100, limit),
        'low': np.linspace(taban_fiyat - 100, taban_fiyat, limit),
        'close': np.linspace(taban_fiyat - 50, taban_fiyat + 50, limit) + np.random.normal(0, 5, limit),
        'volume': np.random.uniform(10, 100, limit)
    })
    return df_fake

# --- 4. ASIL UYGULAMANIN TEKNİK ANALİZ VE LIN. REGRESYON BEYNİ ---
def analiz_et_ve_karar_ver(df):
    if df.empty or len(df) < 30:
        return "BEKLE / NÖTR", 50.0, df, 0.0

    df['rsi'] = ta.momentum.rsi(df['close'], window=14)
    macd = ta.trend.MACD(df['close'])
    df['macd_diff'] = macd.macd_diff()
    df['ma50'] = ta.trend.sma_indicator(df['close'], window=50)

    X = np.array(range(10)).reshape(-1, 1)
    y = df['close'].iloc[-10:].values
    model = LinearRegression().fit(X, y)
    eğim = round(model.coef_[0], 2)

    son_close = df['close'].iloc[-1]
    son_rsi = df['rsi'].iloc[-1]
    son_macd = df['macd_diff'].iloc[-1]
    son_ma50 = df['ma50'].iloc[-1]

    skor = 0
    if son_rsi < 42: skor += 1
    if son_macd > 0: skor += 1
    if son_close > son_ma50: skor += 1
    if eğim > 0: skor += 1

    guven_orani = (skor / 4.0) * 100

    if skor >= 3:
        karar = "GÜÇLÜ AL"
    elif skor <= 1:
        karar = "GÜÇLÜ SAT"
    else:
        karar = "BEKLE / NÖTR"

    return karar, guven_orani, df, eğim

# --- 5. RISK VE CÜZDAN YÖNETİM MOTORU ---
def simule_cuzdan_motoru(symbol, son_fiyat, karar, guven_orani):
    zaman_simdi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if symbol in st.session_state.aktif_pozisyonlar:
        pozisyon = st.session_state.aktif_pozisyonlar[symbol]
        giris_fiyati = pozisyon['giris_fiyati']
        miktar = pozisyon['miktar']
        degisim = (son_fiyat - giris_fiyati) / giris_fiyati
        
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
        if karar == "GÜÇLÜ AL" and st.session_state.simule_bakiye > 100:
            islem_tutari = st.session_state.simule_bakiye * 0.25
            st.session_state.simule_bakiye -= islem_tutari
            miktar = islem_tutari / son_fiyat
            
            st.session_state.aktif_pozisyonlar[symbol] = {
                'giris_fiyati': son_fiyat, 'miktar': miktar, 'zaman': zaman_simdi
            }
            
            yeni_log = pd.DataFrame([{
                "Zaman Damgası": zaman_simdi, "Parite": symbol, "İşlem Tipi": "ALIM (BUY)",
                "Fiyat (USDT)": son_fiyat, "Miktar": round(miktar, 4), "Toplam Tutar": round(islem_tutari, 2),
                "Kasa Bakiyesi": round(st.session_state.simule_bakiye, 2),
                "Açıklama": f"Yapay Zeka AL Sinyali (Güven: %{round(guven_orani,1)}). Pozisyon açıldı."
            }])
            st.session_state.seyir_defteri = pd.concat([yeni_log, st.session_state.seyir_defteri], ignore_index=True)

# --- 6. ARAYÜZ YERLEŞİMİ (SUREKLI KORUMALI DÜZEN) ---
main_col, side_col = st.columns([3, 1])

with side_col:
    st.subheader("👁️ Robot Sistem Durumu")
    
    # Yerleşik Streamlit kutuları ile çökme korumalı tasarım
    st.warning("**Otomatik Emir Modu:**\n\n🧪 SİMÜLASYON (TEST)")
    st.success("**Yapay Zeka Beyni:**\n\n🧠 AKTİF")
    
    st.subheader("### 💼 Simülasyon Kasası")
    st.info(f"💰 **Kasa Bakiyesi:**\n\n{st.session_state.simule_bakiye:,.2f} USDT")
    st.info(f"📈 **Açık Pozisyon:**\n\n{int(len(st.session_state.aktif_pozisyonlar))} Adet")

with main_col:
    # Orijinal ZEYA Başlık Alanı
    st.title("⚡ Z E Y A ⚡")
    st.caption("ARTIFICIAL INTELLIGENCE TRADING BOT WITH MEMORY LOG")
    st.markdown("---")
    
    pariteler = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    isimler = {"BTCUSDT": "Bitcoin (BTC)", "ETHUSDT": "Ethereum (ETH)", "SOLUSDT": "Solana (SOL)"}
    
    p_cols = st.columns(3)
    
    for idx, parite in enumerate(pariteler):
        df = get_binance_data(symbol=parite, interval="15m", limit=100)
        if not df.empty:
            karar, guven_orani, df_analiz, egim = analiz_et_ve_karar_ver(df)
            son_fiyat = float(df_analiz['close'].iloc[-1])
            
            simule_cuzdan_motoru(parite, son_fiyat, karar, guven_orani)
            
            with p_cols[idx]:
                st.markdown(f"### 🪙 {isimler[parite]}")
                st.markdown(f"## **{son_fiyat:,.2f} USDT**")
                st.text(f"↑ ML Eğimi: {egim}")
                
                # Sinyal kartı yerine Streamlit'in kendi renkli uyarı kutularını kullanıyoruz (Sıfır Çökme)
                if "AL" in karar:
                    st.success(f"**🟢 ZEYA AI EMİR SİNYALİ**\n\n**{karar}**\n\nGüven: %{int(guven_orani)}")
                elif "SAT" in karar:
                    st.error(f"**🔴 ZEYA AI EMİR SİNYALİ**\n\n**{karar}**\n\nGüven: %{int(guven_orani)}")
                else:
                    st.warning(f"**🟡 ZEYA AI EMİR SİNYALİ**\n\n**{karar}**\n\nGüven: %{int(guven_orani)}")
                
                # Raporlama Alanı
                if parite in st.session_state.aktif_pozisyonlar:
                    st.info("🧪 Rapor: 🚀 [SİMÜLASYON] BUY tetiklendi.")
                else:
                    st.text_input("Rapor", value="⏳ Rapor: Beklemede", key=f"rep_{parite}", label_visibility="collapsed")
                
                # Çizgi Grafik
                chart_data = df_analiz.set_index('timestamp')['close']
                st.line_chart(chart_data, use_container_width=True)

# --- 7. ALT KISMA EKLENEN LABORATUVAR TABLOLARI ---
st.markdown("---")
st.subheader("💼 Gelişmiş Özellik: Mevcut Açık Pozisyonlar")
if st.session_state.aktif_pozisyonlar:
    poz_df = pd.DataFrame.from_dict(st.session_state.aktif_pozisyonlar, orient='index').reset_index()
    poz_df.columns = ["Parite", "Giriş Fiyatı", "Miktar", "Giriş Zamanı"]
    st.dataframe(poz_df, use_container_width=True)
else:
    st.info("Açık simüle pozisyon bulunmuyor.")

st.subheader("📜 Gelişmiş Özellik: ZEYA İşlem Defteri (Stop-Loss Kayıtları)")
if not st.session_state.seyir_defteri.empty:
    st.dataframe(st.session_state.seyir_defteri, use_container_width=True)
else:
    st.text("Henüz stop-loss veya kâr al işlemi tetiklenmedi.")
