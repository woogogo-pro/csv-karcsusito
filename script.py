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
OUTPUT_FILE = "karcsusitott_feed.csv"   # ez marad a bevalt nev, a git workflow erre van beallitva
MISSING_FILE = "hianyoznak.csv"

MAX_DROP_PCT = 35.0  # ha ennel tobbet esik a sorszam az elozo futashoz kepest -> leallas

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
    """Visszaadja: (ok: bool, uzenet: str). Ha nincs korabbi ertek, mindig ok=True (baseline)."""
    if previous is None or previous == 0:
        return True, f"{label}: nincs korabbi adat, ez lesz a kiindulo ertek ({current} sor)."

    drop_pct = round(100 * (previous - current) / previous, 2)

    if drop_pct > max_drop_pct:
        msg = (
            f"HIBA -- {label}: a sorok szama drasztikusan csokkent!\n"
            f"  Elozo futasnal: {previous} sor\n"
            f"  Mostani futasnal: {current} sor\n"
            f"  Csokkenes: {drop_pct}% (megengedett maximum: {max_drop_pct}%)\n"
            f"  --> Ez valoszinuleg hibas/csonka letoltest jelent, ezert a script LEALL, "
            f"nem frissit semmit, hogy ne allitson be teves 0 keszletet."
        )
        return False, msg

    return True, f"{label}: OK ({previous} -> {current} sor, {drop_pct}% valtozas, hatar: {max_drop_pct}%)"


def main():
    state = load_state()

    # === 1. SAJAT EXPORT LETOLTESE ===
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
    
    # Biztosítjuk, hogy kizárólag az id és sku oszlopok maradjanak a saját fájlból
    df_own = df_own[["id", "sku"]].copy()

    own_count = len(df_own)
    print(f"Sajat termekek szama (tisztitas utan): {own_count}")

    # === 2. NAGYKER FEED LETOLTESE (CACHE-BUSTERREL) ===
    print("\n=== 2. NAGYKER FEED LETOLTESE ===")
    
    # Időbélyeg hozzáfűzése a linkhez, hogy a szerver garantáltan a friss fájlt adja át
    fresh_nagyker_url = f"{NAGYKER_URL}?v={int(time.time())}"
    
    df_new = pd.read_csv(fresh_nagyker_url, sep=";", usecols=["sku", "dealer_price", "available_stock"], dtype=str)
    df_new["sku"] = df_new["sku"].astype(str).str.strip()
    df_new = df_new[df_new["sku"] != ""]
    df_new = df_new.drop_duplicates(subset=["sku"], keep="last")
    nagyker_count = len(df_new)
    print(f"Nagyker sorok szama (tisztitas utan): {nagyker_count}")

    # === 3. VESZFEKEK: elozo futashoz kepest tul nagy visszaeses? ===
    print("\n=== 3. VESZFEK ELLENORZES (35%-os szabaly) ===")
    ok_own, msg_own = check_drop("Sajat lista", state.get("own_count"), own_count, MAX_DROP_PCT)
    ok_new, msg_new = check_drop("Nagyker feed", state.get("nagyker_count"), nagyker_count, MAX_DROP_PCT)

    print(msg_own)
    print(msg_new)

    if not ok_own or not ok_new:
        print("\n>>> A FUTAS LEALL, SEMMI SEM LETT FRISSITVE / FELULIRVA. <<<")
        sys.exit(1)

    # === 4. OSSZEFESULES ===
    print("\n=== 4. OSSZEFESULES ===")
    merged = df_own.merge(df_new[["sku", "dealer_price", "available_stock"]], on="sku", how="left")

    missing_mask = merged["available_stock"].isna()
    missing_count = int(missing_mask.sum())
    missing_pct = round(100 * missing_count / len(merged), 2) if len(merged) else 0.0
    print(f"Nem talalhato a nagykernel (informacios celra, NEM allitja meg a futast): "
          f"{missing_count} db ({missing_pct}%)")

    merged["available_stock"] = merged["available_stock"].fillna("0")

    # === 5. VEGLEGES CSV -- a bevalt fajlnevvel, pontosvesszos elvalasztoval ===
    final_df = merged[["id", "sku", "dealer_price", "available_stock"]].copy()
    final_df.to_csv(OUTPUT_FILE, sep=";", index=False, encoding="utf-8-sig")
    print(f"\nVegleges frissitesi fajl elmentve: {OUTPUT_FILE} ({len(final_df)} sor)")

    # === 6. HIANYZO SKU-K KULON FAJLBA ===
    missing_df = merged.loc[missing_mask, ["id", "sku"]].copy()
    missing_df.to_csv(MISSING_FILE, sep=";", index=False, encoding="utf-8-sig")
    print(f"Hianyzo SKU-k fajlja frissitve: {MISSING_FILE} ({len(missing_df)} sor)")

    # === 7. ALLAPOT MENTESE (csak sikeres futas utan) ===
    state["own_count"] = own_count
    state["nagyker_count"] = nagyker_count
    save_state(state)
    print("\nAllapot elmentve a kovetkezo futashoz.")

    print("\n=== FUTAS SIKERESEN BEFEJEZVE ===")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\nVARATLAN KIVETEL TORTENT, A FUTAS LEALL:")
        traceback.print_exc()
        sys.exit(1)
