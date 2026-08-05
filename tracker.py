import pandas as pd
import os
from datetime import datetime

MISSING_FILE = "hianyoznak.csv"
TRACKER_FILE = "hianyoznak-bovitett-info.csv"

def main():
    if not os.path.exists(MISSING_FILE):
        print(f"A(z) {MISSING_FILE} nem talalhato, a tracker leall.")
        return

    # 1. Friss hiányzó SKU-k betöltése az éles scriptből
    df_missing = pd.read_csv(MISSING_FILE, sep=";", dtype=str)
    if "sku" not in df_missing.columns:
        print("Hibas hianyoznak.csv struktura.")
        return
    
    current_missing_skus = set(df_missing["sku"].dropna().unique())
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_date = datetime.now().date()

    # 2. Meglévő bővített fájl betöltése vagy új létrehozása
    if os.path.exists(TRACKER_FILE):
        df_tracker = pd.read_csv(TRACKER_FILE, sep=";", dtype=str)
    else:
        df_tracker = pd.DataFrame(columns=["id", "sku", "elso_datum", "hianyzo_napok", "statusz"])

    tracker_dict = {}
    for _, row in df_tracker.iterrows():
        tracker_dict[row["sku"]] = row.to_dict()

    # 3. Éles hiányzók feldolgozása (Új eltűnők + Folyamatosan hiányzók)
    for _, row in df_missing.iterrows():
        sku = row["sku"]
        item_id = row["id"]

        if sku not in tracker_dict:
            # Újonnan eltűnt termék
            tracker_dict[sku] = {
                "id": item_id,
                "sku": sku,
                "elso_datum": today_str,
                "hianyzo_napok": "0",
                "statusz": "HIANYZIK"
            }
        else:
            # Már korábban is hiányzott
            elso_dt = datetime.strptime(tracker_dict[sku]["elso_datum"], "%Y-%m-%d").date()
            napok = (today_date - elso_dt).days
            tracker_dict[sku]["hianyzo_napok"] = str(napok)
            tracker_dict[sku]["statusz"] = "HIANYZIK"

    # 4. Visszatért termékek észlelése
    for sku, data in tracker_dict.items():
        if sku not in current_missing_skus and data["statusz"] == "HIANYZIK":
            data["statusz"] = "VISSZATERI"

    # 5. Mentés az új bővített fájlba
    df_result = pd.DataFrame(list(tracker_dict.values()))
    df_result.to_csv(TRACKER_FILE, sep=";", index=False, encoding="utf-8-sig")
    print(f"Tracker sikeresen frissitve: {TRACKER_FILE} ({len(df_result)} sor)")

if __name__ == "__main__":
    main()
