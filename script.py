import pandas as pd
import requests
import sys
import os
import json
from io import StringIO
from datetime import datetime, timezone

# ==========================================
# 1. BEÁLLÍTÁSOK
# ==========================================
NAGYKER_URL = "https://store.dreamlove.es/dyndata/exportaciones/csvzip/catalog_1_51_125_2_8964ad7838ce7787975ab7a21a3787ff_csv_plain.csv"
COL_SKU = "sku"
COL_STOCK = "available_stock"

# WP All Export "File URL" - a sajat_termekek export kész CSV-jének letöltési linkje
OWN_PRODUCTS_FILE_URL = "https://sexstore.ie/wp-load.php?security_token=aa5206cc02fc4c62&export_id=26&action=get_data"
OWN_SKU_COL = "sku"   # ha az export más oszlopnevet ad, itt igazítsd
OWN_ID_COL = "id"     # ha az export más oszlopnevet ad, itt igazítsd

OWN_PRODUCTS_FILE = "sajat_termekek.csv"      # cache: ha a live letöltés hibázik, ebből dolgozunk
PREV_STATE_FILE = "previous_state.csv"        # a legutóbbi teljes állapot (id, sku, stock) - a diffhez kell
OUTPUT_FILE = "karcsusitott_feed.csv"         # ezt olvassa be a WP All Import
STATUS_FILE = "status.json"
STATUS_MD_FILE = "STATUS.md"

MIN_EXPECTED_NAGYKER_ROWS = 5000       # ha ennél kevesebb sort ad a nagyker, gyanús/csonka letöltés
MIN_EXPECTED_OWN_PRODUCTS = 1000       # ha a saját export ennél kevesebbet ad, gyanús -> cache-re esünk vissza
MISSING_SKU_WARN_PCT = 5.0             # ennyi % feletti eltűnésnél email-figyelmeztetés
MISSING_SKU_CRITICAL_PCT = 10.0        # ennyi % feletti eltűnésnél LEÁLLÁS (nem csak figyelmeztetés!)

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
    "severity": "ok",   # ok | warn | critical | error
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


# ==========================================
# 2. SAJÁT TERMÉKEK (ID + SKU) - WP ALL EXPORT FILE URL-BŐL
#    Ha a letöltés nem elérhető / hibázik / gyanúsan kevés terméket ad
#    vissza -> visszaesünk a legutóbbi jó cache fájlra.
# ==========================================
def fetch_own_products():
    try:
        resp = requests.get(OWN_PRODUCTS_FILE_URL, timeout=60)
        if resp.status_code != 200:
            return None
        text = resp.text.strip()
        if not text or "<html" in text[:200].lower():
            return None
        try:
            df = pd.read_csv(StringIO(text), dtype=str)
        except Exception:
            df = pd.read_csv(StringIO(text), sep=';', dtype=str)
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
            "a legutóbbi cache-elt sajat_termekek.csv-t használtuk helyette. Ha ez több futáson át ismétlődik, "
            "ellenőrizd a WP All Export 'File URL' linket és a napi export ütemezését."
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

# ==========================================
# 3. NAGYKER FEED LETÖLTÉSE ÉS VALIDÁLÁSA
# ==========================================
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

# ==========================================
# 4. MERGE: SAJÁT LISTA + NAGYKER KÉSZLET
#    Left join: minden saját termék megmarad. Ha egy SKU nincs a
#    nagyker feedben (mert törölték nála), stock = 0.
# ==========================================
merged = df_own.merge(df_new[["sku", "stock"]], on="sku", how="left")
missing_mask = merged["stock"].isna()
missing_count = int(missing_mask.sum())
missing_pct = round(100 * missing_count / len(merged), 2) if len(merged) else 0.0

status["missing_skus_count"] = missing_count
status["missing_skus_pct"] = missing_pct

if missing_count > 0:
    missing_list = merged.loc[missing_mask, "sku"].tolist()
    status["missing_skus_sample"] = missing_list[:20]

# ==========================================
# 4b. VÉSZFÉK: ha gyanúsan sok SKU hiányzik, ÁLLJUNK MEG.
#     Nem írjuk ki a feedet, nem írjuk felül a previous_state-et.
#     Ez a leállás MEGELŐZI az 5. szekciót (kiírás) - itt még
#     semmilyen fájl nem módosul.
# ==========================================
if missing_pct >= MISSING_SKU_CRITICAL_PCT:
    status["alerts"].append(
        f"KRITIKUS RIASZTÁS: {missing_count} SKU ({missing_pct}%) hiányzik a nagyker feedből. "
        f"Ez gyanúsan magas arány - valószínűleg nagyker-oldali hiba, NEM valódi tömeges törlés. "
        f"A FUTÁS LEÁLLT, a karcsusitott_feed.csv és previous_state.csv VÁLTOZATLAN maradt, "
        f"hogy ne írjunk felül jó készletadatokat téves 0-kal. MANUÁLIS ELLENŐRZÉS SZÜKSÉGES, "
        f"mielőtt a script újra futna és feldolgozná ezt az adatot."
    )
    status["severity"] = "critical"
    status["changed_rows"] = 0
    save_status_and_exit(1)

# Csak akkor jutunk el ide, ha a hiányzó SKU-k aránya biztonságos (< 10%).
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
            f"{missing_count} SKU ({missing_pct}%) hiányzik a nagyker feedből (valószínűleg törölt cikkek), 0-ra állítva."
        )

# ==========================================
# 5. DIFF - CSAK A TÉNYLEGESEN VÁLTOZOTT SOROK KIÍRÁSA
#    (Ide már csak biztonságos, < 10% hiányzó SKU-t tartalmazó
#    adattal jutunk el.)
# ==========================================
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
