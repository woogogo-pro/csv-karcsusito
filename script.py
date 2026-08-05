import pandas as pd
import requests
import sys
import os
import json
from io import BytesIO
from datetime import datetime, timezone

# ==========================================
# 1. BEÁLLÍTÁSOK
# ==========================================
NAGYKER_URL = "https://store.dreamlove.es/dyndata/exportaciones/csvzip/catalog_1_51_125_2_8964ad7838ce7787975ab7a21a3787ff_csv_plain.csv"
COL_SKU = "sku"
COL_STOCK = "available_stock"

OWN_PRODUCTS_FILE_URL = "https://sexstore.ie/wp-load.php?security_token=aa5206cc02fc4c62&export_id=26&action=get_data"
OWN_SKU_COL = "sku"
OWN_ID_COL = "id"

OWN_PRODUCTS_FILE = "sajat_termekek.csv"
PREV_STATE_FILE = "previous_state.csv"
OUTPUT_FILE = "karcsusitott_feed.csv"
STATUS_FILE = "status.json"
STATUS_MD_FILE = "STATUS.md"

MIN_EXPECTED_NAGYKER_ROWS = 5000
MIN_EXPECTED_OWN_PRODUCTS = 1000
MISSING_SKU_WARN_PCT = 5.0
MISSING_SKU_CRITICAL_PCT = 10.0

status = {
    "run_time_utc": datetime.now(timezone.utc).isoformat(),
    "own_products_source": None,
    "own_products_count": None,
    "nagyker_download_ok": False,
    "nagyker_rows": None,
    "missing_skus_count": 0,
    "missing_skus_pct": 0.0,
    "missing_skus_sample": [],
    "changed_rows": None,
    "alerts": [],
    "severity": "ok",
    "success": False,
}


def write_status_md():
    lines = []
    lines.append(f"# CSV Karcsúsító - Állapot\n")
    lines.append(f"**Utolsó futás (UTC):** {status['run_time_utc']}\n")
    lines.append(f"**Eredmény:** {'✅ Sikeres' if status['success'] else '❌ Sikertelen / leállítva'}\n")
    lines.append(f"**Súlyosság:** {status['severity'].upper()}\n")
    lines.append("## Számok")
    lines.append(f"- Saját termékek forrása: {status['own_products_source']}")
    lines.append(f"- Saját termékek száma: {status['own_products_count']}")
    lines.append(f"- Nagyker letöltés: {'✅ OK' if status['nagyker_download_ok'] else '❌ HIBA'}")
    lines.append(f"- Nagyker feed sorok száma: {status['nagyker_rows']}")
    lines.append(f"- Hiányzó SKU-k (0-ra állítva): {status['missing_skus_count']} ({status['missing_skus_pct']}%)")
    lines.append(f"- Ebben a futásban módosított sorok: {status['changed_rows']}")
    if status["missing_skus_sample"]:
        lines.append(f"- Példa hiányzó SKU-kra: {', '.join(status['missing_skus_sample'])}")
    if status["alerts"]:
        lines.append("\n## Figyelmeztetések")
        for a in status["alerts"]:
            lines.append(f"- {a}")
    with open(STATUS_MD_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def save_status_and_exit(code):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)
    write_status_md()
    sys.exit(code)


def fetch_own_products():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        resp = requests.get(OWN_PRODUCTS_FILE_URL, headers=headers, timeout=60)
        if resp.status_code != 200:
            return None
        if not resp.content:
            return None
        # encoding='utf-8-sig' automatikusan levágja a BOM jelzést (ï»¿),
        # amit a WP All Export tesz a fájl elejére.
        df = pd.read_csv(BytesIO(resp.content), encoding='utf-8-sig', dtype=str)
        df.columns = [c.strip().lower() for c in df.columns]
        if OWN_SKU_COL not in df.columns or OWN_ID_COL not in df.columns:
            return None
        df = df.rename(columns={OWN_ID_COL: "id", OWN_SKU_COL: "sku"})
        return df[["id", "sku"]]
    except Exception:
        return None


df_own = fetch_own_products()
if df_own is not None and len(df_own) >= MIN_EXPECTED_OWN_PRODUCTS:
    df_own.to_csv(OWN_PRODUCTS_FILE, index=False)
    status["own_products_source"] = "wp_all_export_live"
else:
    if os.path.exists(OWN_PRODUCTS_FILE):
        df_own = pd.read_csv(OWN_PRODUCTS_FILE, dtype=str)
        status["own_products_source"] = "cached_fallback"
        status["alerts"].append(
            "A sajat_termekek export élő letöltése sikertelen vagy gyanúsan kevés sort adott ebben a futásban - "
            "a legutóbbi cache-elt sajat_termekek.csv-t használtuk helyette."
        )
        status["severity"] = "warn"
    else:
        status["alerts"].append(
            "KRITIKUS: nincs elérhető sajat_termekek.csv (sem élő export, sem cache). A futás leáll, "
            "a korábbi karcsusitott_feed.csv változatlan marad."
        )
        status["severity"] = "critical"
        save_status_and_exit(1)

df_own["sku"] = df_own["sku"].astype(str).str.strip()
df_own = df_own.dropna(subset=["sku"])
df_own = df_own[df_own["sku"] != ""]
df_own["id"] = df_own["id"].astype(str)
df_own = df_own.drop_duplicates(subset=["sku"], keep="last")
status["own_products_count"] = len(df_own)

try:
    df_new = pd.read_csv(NAGYKER_URL, sep=';', usecols=[COL_SKU, COL_STOCK], dtype=str)
    df_new = df_new.rename(columns={COL_SKU: "sku", COL_STOCK: "stock"})
    df_new["sku"] = df_new["sku"].astype(str).str.strip()
    df_new = df_new.dropna(subset=["sku"])
    df_new = df_new[df_new["sku"] != ""]
    df_new = df_new.drop_duplicates(subset=["sku"], keep="last")
    df_new["stock"] = pd.to_numeric(df_new["stock"], errors="coerce").fillna(0).astype(int)

    if len(df_new) < MIN_EXPECTED_NAGYKER_ROWS:
        raise ValueError(f"Csak {len(df_new)} sor érkezett (minimum elvárt: {MIN_EXPECTED_NAGYKER_ROWS})")

    status["nagyker_download_ok"] = True
    status["nagyker_rows"] = len(df_new)
except Exception as e:
    status["alerts"].append(
        f"KRITIKUS: nagyker feed letöltés/validálás sikertelen ({e}). "
        f"A korábbi karcsusitott_feed.csv NEM módosul, a régi állapot marad érvényben."
    )
    status["severity"] = "critical"
    save_status_and_exit(1)

merged = df_own.merge(df_new[["sku", "stock"]], on="sku", how="left")
missing_mask = merged["stock"].isna()
missing_count = int(missing_mask.sum())
missing_pct = round(100 * missing_count / len(merged), 2) if len(merged) else 0.0

status["missing_skus_count"] = missing_count
status["missing_skus_pct"] = missing_pct

if missing_count > 0:
    missing_list = merged.loc[missing_mask, "sku"].tolist()
    status["missing_skus_sample"] = missing_list[:20]

if missing_pct >= MISSING_SKU_CRITICAL_PCT:
    status["alerts"].append(
        f"KRITIKUS RIASZTÁS: {missing_count} SKU ({missing_pct}%) hiányzik a nagyker feedből. "
        f"A FUTÁS LEÁLLT, a fájlok változatlanok maradtak. MANUÁLIS ELLENŐRZÉS SZÜKSÉGES."
    )
    status["severity"] = "critical"
    status["changed_rows"] = 0
    save_status_and_exit(1)

merged.loc[missing_mask, "stock"] = 0
merged["stock"] = merged["stock"].astype(int)

if missing_count > 0:
    if missing_pct >= MISSING_SKU_WARN_PCT:
        status["alerts"].append(
            f"FIGYELMEZTETÉS: {missing_count} SKU ({missing_pct}%) hiányzik a nagyker feedből, 0 készletre állítva."
        )
        if status["severity"] == "ok":
            status["severity"] = "warn"
    else:
        status["alerts"].append(
            f"{missing_count} SKU ({missing_pct}%) hiányzik a nagyker feedből, 0-ra állítva."
        )

if os.path.exists(PREV_STATE_FILE):
    df_prev = pd.read_csv(PREV_STATE_FILE, dtype=str)
    df_prev["stock"] = pd.to_numeric(df_prev["stock"], errors="coerce").fillna(0).astype(int)
else:
    df_prev = pd.DataFrame(columns=["id", "sku", "stock"])

diff = merged.merge(df_prev[["id", "stock"]], on="id", how="left", suffixes=("", "_prev"))
changed_mask = diff["stock_prev"].isna() | (diff["stock"] != diff["stock_prev"])
df_changed = diff.loc[changed_mask, ["id", "sku", "stock"]]

status["changed_rows"] = len(df_changed)

df_changed.to_csv(OUTPUT_FILE, sep=';', index=False)
merged[["id", "sku", "stock"]].to_csv(PREV_STATE_FILE, index=False)

status["success"] = True
save_status_and_exit(0)
