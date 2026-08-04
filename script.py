import pandas as pd
import requests

# ==========================================
# 1. BEÁLLÍTÁSOK (Itt add meg a nagyker adatait)
# ==========================================
# Cseréld ki a nagyker igazi CSV/ZIP linkjére:
NAGYKER_URL = "https://store.dreamlove.es/dyndata/exportaciones/csvzip/catalog_1_51_125_2_8964ad7838ce7787975ab7a21a3787ff_csv_plain.csv"

# Megadandó oszlopnevek (pontosan úgy, ahogy a nagyker CSV fejlécében vannak!):
COL_SKU = "cikkszam"
COL_STOCK = "keszlet"
COL_PRICE = "ar"

# ==========================================
# 2. FELDOLGOZÁS
# ==========================================
try:
    print("Nagyker feed letöltése és szűrése folyamatban...")
    
    # Csak a 3 szükséges oszlopot töltjük be, így memóriakímélő és villámgyors:
    df = pd.read_csv(NAGYKER_URL, usecols=[COL_SKU, COL_STOCK, COL_PRICE])
    
    # Átnevezzük az oszlopokat egységes, tiszta elnevezésekre:
    df.columns = ['sku', 'stock', 'price']

    # Kimentjük az új karcsúsított CSV-be:
    df.to_csv('karcsusitott_feed.csv', index=False)
    print(f"Sikeres frissítés! Total termék: {len(df)}")

except Exception as e:
    print(f"Hiba történt a feldolgozás során: {str(e)}")
    exit(1)
