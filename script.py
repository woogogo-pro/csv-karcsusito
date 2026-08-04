import pandas as pd

# ==========================================
# 1. BEÁLLÍTÁSOK
# ==========================================
# Másold be a nagyker igazi CSV letöltési linkjét a macskakörmök közé:
NAGYKER_URL = "https://store.dreamlove.es/dyndata/exportaciones/csvzip/catalog_1_51_125_2_8964ad7838ce7787975ab7a21a3787ff_csv_plain.csv"

# Pontos oszlopnevek a képeid alapján:
COL_SKU = "sku"
COL_STOCK = "available_stock"
COL_PRICE = "dealer_price"

# ==========================================
# 2. FELDOLGOZÁS
# ==========================================
try:
    print("Nagyker feed letöltése és karcsúsítása folyamatban...")
    
    # Pontosvessző elválasztó (sep=';') és a 3 oszlop beolvasása:
    df = pd.read_csv(
        NAGYKER_URL, 
        sep=';', 
        usecols=[COL_SKU, COL_STOCK, COL_PRICE],
        dtype=str  # megőrzi a cikkszámok pontos formátumát
    )
    
    # Kimentjük az új karcsúsított CSV-t pontosvessző elválasztóval:
    df.to_csv('karcsusitott_feed.csv', sep=';', index=False)
    print(f"Sikeres frissítés! Feldolgozva: {len(df)} termék.")

except Exception as e:
    print(f"Hiba történt a feldolgozás során: {str(e)}")
    exit(1)
