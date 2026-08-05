import pandas as pd
import requests
import sys
import traceback
from io import BytesIO

NAGYKER_URL = "https://store.dreamlove.es/dyndata/exportaciones/csvzip/catalog_1_51_125_2_8964ad7838ce7787975ab7a21a3787ff_csv_plain.csv"
OWN_PRODUCTS_FILE_URL = "https://sexstore.ie/wp-load.php?security_token=aa5206cc02fc4c62&export_id=26&action=get_data"

try:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    resp = requests.get(OWN_PRODUCTS_FILE_URL, headers=headers, timeout=60)
    df_own = pd.read_csv(BytesIO(resp.content), encoding='utf-8-sig', dtype=str)
    df_own.columns = [c.strip().lower() for c in df_own.columns]
    df_own["sku"] = df_own["sku"].astype(str).str.strip()
    df_own = df_own.dropna(subset=["sku"])
    df_own = df_own[df_own["sku"] != ""]
    df_own["id"] = df_own["id"].astype(str)
    df_own = df_own.drop_duplicates(subset=["sku"], keep="last")
    print(f"Saját termékek száma (tisztítás után): {len(df_own)}")

    print("Nagyker feed letöltése (teljes, ez eltarthat egy ideig)...")
    df_new = pd.read_csv(NAGYKER_URL, sep=';', usecols=["sku", "available_stock"], dtype=str)
    df_new = df_new.rename(columns={"available_stock": "stock"})
    df_new["sku"] = df_new["sku"].astype(str).str.strip()
    df_new = df_new.dropna(subset=["sku"])
    df_new = df_new[df_new["sku"] != ""]
    df_new = df_new.drop_duplicates(subset=["sku"], keep="last")
    print(f"Nagyker sorok száma (tisztítás után): {len(df_new)}")

    merged = df_own.merge(df_new[["sku", "stock"]], on="sku", how="left")
    missing_mask = merged["stock"].isna()
    missing_count = int(missing_mask.sum())
    missing_pct = round(100 * missing_count / len(merged), 2) if len(merged) else 0.0

    print(f"Összesen saját termék: {len(merged)}")
    print(f"Nem található a nagykernél (hiányzó): {missing_count} ({missing_pct}%)")
    print("Néhány példa hiányzó SKU-ra:")
    print(merged.loc[missing_mask, "sku"].head(20).tolist())

except Exception:
    print("KIVÉTEL történt:")
    traceback.print_exc()

print()
print("=== DIAGNOSZTIKA VÉGE (mindig 0-s exit code) ===")
sys.exit(0)
