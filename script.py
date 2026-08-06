import pandas as pd
import requests
import sys
import json
import os
import time
import traceback
from io import BytesIO

NAGYKER_URL = "https://store.dreamlove.es/dyndata/exportaciones/csvzip/catalog_1_51_125_2_8964ad7838ce7787975ab7a21a3787ff_csv_plain.csv"
OWN_PRODUCTS_FILE_URL = "https://sexstore.ie/wp-load.php?security_token=aa5206cc02fc4c62&export_id=26&action=get_data"

STATE_FILE = "state.json"
OUTPUT_FILE = "karcsusitott_feed.csv"                  # Az eredeti, fő frissítési fájl
SURGOS_OUTPUT_FILE = "surgos_frissites_valtoztak.csv"  # ÚJ: csak a megváltozott termékek
MISSING_FILE = "hianyoznak.csv"

MAX_DROP_PCT = 35.0  # ha ennél többet esik a sorszám -> leállás

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def check_drop(label, previous, current, max_drop_pct):
    if previous is None or previous == 0:
        return True, f"{label}: nincs korabbi adat, ez lesz a kiindulo ertek ({current} sor)."

    drop_pct = round(100 * (previous - current) / previous, 2)

    if drop_pct > max_drop_pct:
        msg = (
            f"HIBA -- {label}: a sorok szama drasztikusan csokkent!\n"
            f"  Elozo futasnal: {previous} sor\n"
            f"  Mostani futasnal: {current} sor\n"
            f"  Csokkenes: {drop_pct}% (megengedett maximum: {max_drop_pct}%)\n"
            f"  --> Ez valoszinuleg hibas/csonka letoltest jelent, ezert a script LEALL."
        )
        return False, msg

    return True, f"{label}: OK ({previous} -> {current} sor, {drop_pct}% valtozas)"


def main():
    state = load_state()

    # === 1. SAJÁT EXPORT LETÖLTÉSE ===
    print("=== 1. SAJAT EXPORT LETOLTESE ===")
    resp = requests.get(OWN_PRODUCTS_FILE_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    df_own = pd.read_csv(BytesIO(resp.content), encoding="utf-8-sig", dtype=str)
    df_own.columns = [c.strip().lower() for c in df_own.columns]

    if "id" not in df_own.columns or "sku" not in df_own.columns:
        print(f"HIBA: a sajat export hianyos oszlopokkal erkezett: {df_own.columns.tolist()}")
        sys.exit(1)

    df_own["sku"] = df_own["sku"].astype(str).str.strip()
    df_own["id"] = df_own["id"].astype(str).str.strip()
    df_own = df_own[df_own["sku"] != ""]
    df_own = df_own.drop_duplicates(subset=["sku"], keep="last")
    df_own = df_own[["id", "sku"]].copy()

    own_count = len(df_own)
    print(f"Sajat termekek szama: {own_count}")

    # === 2. NAGYKER FEED LETÖLTÉSE ===
    print("\n=== 2. NAGYKER FEED LETOLTESE ===")
    fresh_nagyker_url = f"{NAGYKER_URL}?v={int(time.time())}"
    
    df_new = pd.read_csv(fresh_nagyker_url, sep=";", usecols=["sku", "dealer_price", "available_stock"], dtype=str)
    df_new["sku"] = df_new["sku"].astype(str).str.strip()
    df_new = df_new[df_new["sku"] != ""]
    df_new = df_new.drop_duplicates(subset=["sku"], keep="last")
    nagyker_count = len(df_new)
    print(f"Nagyker sorok szama: {nagyker_count}")

    # === 3. VÉSZFÉKEK Ellenőrzése ===
    print("\n=== 3. VESZFEK ELLENORZES ===")
    ok_own, msg_own = check_drop("Sajat lista", state.get("own_count"), own_count, MAX_DROP_PCT)
    ok_new, msg_new = check_drop("Nagyker feed", state.get("nagyker_count"), nagyker_count, MAX_DROP_PCT)

    print(msg_own)
    print(msg_new)

    if not ok_own or not ok_new:
        print("\n>>> A FUTAS LEALL, SEMMI SEM LETT FRISSITVE. <<<")
        sys.exit(1)

    # === 4. ÖSSZEFÉSÜLÉS ===
    print("\n=== 4. OSSZEFESULES ===")
    merged = df_own.merge(df_new[["sku", "dealer_price", "available_stock"]], on="sku", how="left")

    missing_mask = merged["available_stock"].isna()
    merged["available_stock"] = merged["available_stock"].fillna("0")

    final_df = merged[["id", "sku", "dealer_price", "available_stock"]].copy()
    final_df["available_stock"] = final_df["available_stock"].astype(str).str.strip()

    # =========================================================================
    # === 5. SÜRGŐS FRISSÍTÉS GENERÁLÁSA (TELJESEN IZOLÁLT BIZTONSÁGI BLOKK) ===
    # =========================================================================
    try:
        print("\n=== 5. SURGOS FRISSITES DETEKTALASA (MELLEKKULDETES) ===")
        if os.path.exists(OUTPUT_FILE):
            df_old = pd.read_csv(OUTPUT_FILE, sep=";", dtype=str)
            df_old.columns = [c.strip().lower() for c in df_old.columns]
            
            if "sku" in df_old.columns and "available_stock" in df_old.columns:
                df_old["sku"] = df_old["sku"].astype(str).str.strip()
                df_old["available_stock"] = df_old["available_stock"].astype(str).str.strip()
                
                merged_diff = final_df.merge(
                    df_old[["sku", "available_stock"]].rename(columns={"available_stock": "available_stock_old"}),
                    on="sku",
                    how="left"
                )
                changed_mask = (
                    merged_diff["available_stock_old"].isna() |
                    (merged_diff["available_stock"] != merged_diff["available_stock_old"])
                )
                surgos_df = merged_diff.loc[changed_mask, ["id", "sku", "available_stock"]].copy()
            else:
                surgos_df = final_df[["id", "sku", "available_stock"]].copy()
        else:
            surgos_df = final_df[["id", "sku", "available_stock"]].copy()

        surgos_df.to_csv(SURGOS_OUTPUT_FILE, sep=";", index=False, encoding="utf-8-sig")
        print(f"-> Surgos frissitesi fajl sikeresen elmentve: {SURGOS_OUTPUT_FILE} ({len(surgos_df)} valtozott sor)")

    except Exception as e:
        # Ha BÁRMI hiba történik a sürgős frissítés közben, kiírja a hibát, DE A SCRIPT MEGY TOVÁBB!
        print(f"\n[FIGYELMEZTETES] A surgos frissites generalasa nem sikerult ({e}), de a fo feed mentese folytatodik!")

    # =========================================================================
    # === 6. FŐ FAJL ÉS HIÁNYZÓK MENTÉSE (EZ MINDENKÉPP LEFUT) ===
    # =========================================================================
    final_df.to_csv(OUTPUT_FILE, sep=";", index=False, encoding="utf-8-sig")
    print(f"\nVegleges karcsusitott_feed.csv elmentve ({len(final_df)} sor)")

    missing_df = merged.loc[missing_mask, ["id", "sku"]].copy()
    missing_df.to_csv(MISSING_FILE, sep=";", index=False, encoding="utf-8-sig")

    state["own_count"] = own_count
    state["nagyker_count"] = nagyker_count
    save_state(state)

    print("\n=== FUTAS SIKERESEN BEFEJEZVE ===")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\nVARATLAN KIVETEL TORTENT, A FUTAS LEALL:")
        traceback.print_exc()
        sys.exit(1)
