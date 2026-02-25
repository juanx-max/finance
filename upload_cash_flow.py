"""
Sube PAYOUTS, REFUND, CHARGEBACK y CHARGEBACK_CANCEL a unified_transactions.
(Los SETTLEMENT ya estan cargados desde upload_unified.py)
"""

import os
import sys
import pandas as pd
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TABLE = "unified_transactions"
BATCH_SIZE = 500

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILES = ["Jun- Jul.csv", "Ago- Sep.csv", "Oct - Nov.csv", "Dic - Ene.csv"]

NON_SETTLEMENT_TYPES = ["PAYOUTS", "REFUND", "CHARGEBACK", "CHARGEBACK_CANCEL"]


def load_non_settlement():
    frames = []
    for f in CSV_FILES:
        path = os.path.join(BASE_DIR, f)
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path, sep=";", on_bad_lines="skip", low_memory=False)
        df["_source"] = f
        frames.append(df)
        print(f"  {f}: {len(df):,} filas")

    mp = pd.concat(frames, ignore_index=True)

    # Solo los tipos que no son SETTLEMENT
    mp = mp[mp["TRANSACTION_TYPE"].isin(NON_SETTLEMENT_TYPES)].copy()

    mp["SETTLEMENT_NET_AMOUNT"] = pd.to_numeric(mp["SETTLEMENT_NET_AMOUNT"], errors="coerce")
    mp["TRANSACTION_DATE"] = pd.to_datetime(mp["TRANSACTION_DATE"], errors="coerce", utc=True)
    mp = mp.dropna(subset=["TRANSACTION_DATE", "SETTLEMENT_NET_AMOUNT"])
    mp["ref_clean"] = mp["EXTERNAL_REFERENCE"].astype(str).str.strip('"').str.strip()

    print(f"\n  Movimientos no-SETTLEMENT: {len(mp):,}")
    for tt, group in mp.groupby("TRANSACTION_TYPE"):
        print(f"    {tt}: {len(group):,} (NET=${group['SETTLEMENT_NET_AMOUNT'].sum():,.0f})")

    return mp


def build_records(mp):
    records = []
    for _, row in mp.iterrows():
        try:
            dt = row["TRANSACTION_DATE"].isoformat()
        except Exception:
            dt = str(row["TRANSACTION_DATE"])

        net_val = row["SETTLEMENT_NET_AMOUNT"]
        net = 0.0 if pd.isna(net_val) else round(float(net_val), 2)
        tt = row["TRANSACTION_TYPE"]
        ref = row["ref_clean"]

        records.append({
            "reference_id": ref if ref != "nan" and not pd.isna(ref) else None,
            "productor": "MercadoPago",
            "evento": tt,
            "transaction_datetime": dt,
            "ticket_count": 0,
            "costo_ticket": 0,
            "costo_sc": 0,
            "total_transaccion": net,
            "payment_method": "mercadopago",
            "has_mp_data": True,
            "transaction_type": tt,
        })
    return records


def upload_batch(client, batch):
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = client.post(url, json=batch, headers=headers)
    resp.raise_for_status()
    return len(batch)


def upload_to_supabase(records):
    uploaded = 0
    errors = 0
    total = len(records)

    with httpx.Client(timeout=30.0) as client:
        for i in range(0, total, BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            try:
                uploaded += upload_batch(client, batch)
                pct = uploaded / total * 100
                print(f"\r  Subidos: {uploaded:,} / {total:,} ({pct:.1f}%)", end="", flush=True)
            except httpx.HTTPStatusError as e:
                errors += 1
                print(f"\n  ERROR batch {i // BATCH_SIZE + 1}: {e.response.status_code} - {e.response.text[:200]}")
            except Exception as e:
                errors += 1
                print(f"\n  ERROR batch {i // BATCH_SIZE + 1}: {e}")

    print(f"\n  Subidos: {uploaded:,} | Errores: {errors}")
    return uploaded


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: Configura SUPABASE_URL y SUPABASE_KEY en .env")
        sys.exit(1)

    print("1. Cargando movimientos no-SETTLEMENT...")
    mp = load_non_settlement()

    print(f"\n2. Preparando registros...")
    records = build_records(mp)
    print(f"  {len(records):,} registros listos")

    print(f"\n3. Subiendo a Supabase ({TABLE})...")
    uploaded = upload_to_supabase(records)

    print(f"\n{'='*50}")
    print(f"COMPLETO: {uploaded:,} movimientos agregados")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
