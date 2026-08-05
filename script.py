import pandas as pd
import requests
import sys
import os
from io import StringIO

NAGYKER_URL = "https://store.dreamlove.es/dyndata/exportaciones/csvzip/catalog_1_51_125_2_8964ad7838ce7787975ab7a21a3787ff_csv_plain.csv"
OWN_PRODUCTS_FILE_URL = "https://sexstore.ie/wp-load.php?security_token=aa5206cc02fc4c62&export_id=26&action=get_data"

print("=== 1. SAJÁT EXPORT LETÖLTÉSE ===")
try:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    resp = requests.get(OWN_PRODUCTS_FILE_URL, headers=headers, timeout=60)
    print(f"Status code: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('Content-Type')}")
    print(f"Content length: {len(resp.text)}")
    print("Első 500 karakter a válaszból:")
    print(resp.text[:500])
    print("--- vége az első 500 karakternek ---")
except Exception as e:
    print(f"KIVÉTEL a saját export letöltésekor: {repr(e)}")

print()
print("=== 2. NAGYKER FEED LETÖLTÉSE ===")
try:
    df_new = pd.read_csv(NAGYKER_URL, sep=';', nrows=5)
    print("Nagyker feed oszlopai:", list(df_new.columns))
    print("Első pár sor:")
    print(df_new.head())
except Exception as e:
    print(f"KIVÉTEL a nagyker feed letöltésekor: {repr(e)}")

print()
print("=== DIAGNOSZTIKA VÉGE ===")
sys.exit(0)
