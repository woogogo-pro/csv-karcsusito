import pandas as pd
import requests
import sys
import traceback
from io import BytesIO

NAGYKER_URL = "https://store.dreamlove.es/dyndata/exportaciones/csvzip/catalog_1_51_125_2_8964ad7838ce7787975ab7a21a3787ff_csv_plain.csv"
OWN_PRODUCTS_FILE_URL = "https://sexstore.ie/wp-load.php?security_token=aa5206cc02fc4c62&export_id=26&action=get_data"

print("=== 1. SAJÁT EXPORT LETÖLTÉSE ÉS FELDOLGOZÁSA ===")
try:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    resp = requests.get(OWN_PRODUCTS_FILE_URL, headers=headers, timeout=60)
    print(f"Status code: {resp.status_code}")
    print(f"Content length (bytes): {len(resp.content)}")

    df = pd.read_csv(BytesIO(resp.content), encoding='utf-8-sig', dtype=str)
    print("Sikeres beolvasás!")
    print("Eredeti oszlopnevek:", list(df.columns))

    df.columns = [c.strip().lower() for c in df.columns]
    print("Kisbetűsített oszlopnevek:", list(df.columns))
    print("Sorok száma:", len(df))
    print(df.head())

    if "id" not in df.columns or "sku" not in df.columns:
        print("HIBA: 'id' vagy 'sku' oszlop nem található!")
    else:
        print("OK: mindkét oszlop megvan.")

except Exception as e:
    print("KIVÉTEL történt a saját export feldolgozásakor:")
    traceback.print_exc()

print()
print("=== 2. NAGYKER FEED LETÖLTÉSE ===")
try:
    df_new = pd.read_csv(NAGYKER_URL, sep=';', usecols=["sku", "available_stock"], dtype=str, nrows=10)
    print("Sikeres beolvasás, oszlopok:", list(df_new.columns))
    print(df_new.head())
except Exception as e:
    print("KIVÉTEL történt a nagyker feed feldolgozásakor:")
    traceback.print_exc()

print()
print("=== DIAGNOSZTIKA VÉGE (mindig 0-s exit code) ===")
sys.exit(0)
