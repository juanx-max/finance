"""
Unifica MP CSVs + Order Tickets y sube a Supabase unified_transactions.

Campos:
  - productor, evento, transaction_datetime
  - costo_ticket = Subtotal (precio base del ticket)
  - costo_sc    = SERVICE - |impuestos| - |mp_fee|  (SC neto)
  - total_transaccion = costo_ticket + costo_sc      (= SETTLEMENT_NET_AMOUNT)

Para refs sin match en MP: costo_sc = SERVICE (sin deducciones conocidas),
                           total_transaccion = TOTAL del ticket.
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
TICKETS_FILE = "csv-order-tickets-202602ma010723 (1) (1).xlsx"


def load_mp():
    """Carga y combina los 4 CSVs de MercadoPago (solo SETTLEMENT)."""
    frames = []
    for f in CSV_FILES:
        path = os.path.join(BASE_DIR, f)
        if not os.path.exists(path):
            print(f"  AVISO: {f} no encontrado, saltando.")
            continue
        df = pd.read_csv(path, sep=";", on_bad_lines="skip", low_memory=False)
        frames.append(df)
        print(f"  {f}: {len(df):,} filas")

    mp = pd.concat(frames, ignore_index=True)
    mp = mp[mp["TRANSACTION_TYPE"] == "SETTLEMENT"].copy()
    mp["ref_clean"] = mp["EXTERNAL_REFERENCE"].astype(str).str.strip('"').str.strip()
    mp["TRANSACTION_AMOUNT"] = pd.to_numeric(mp["TRANSACTION_AMOUNT"], errors="coerce")
    mp["FEE_AMOUNT"] = pd.to_numeric(mp["FEE_AMOUNT"], errors="coerce").fillna(0)
    mp["TAXES_AMOUNT"] = pd.to_numeric(mp["TAXES_AMOUNT"], errors="coerce").fillna(0)
    print(f"  MP total SETTLEMENT: {len(mp):,}")
    return mp


def load_tickets():
    """Carga el xlsx de order tickets."""
    path = os.path.join(BASE_DIR, TICKETS_FILE)
    tk = pd.read_excel(path)
    tk["ref_clean"] = tk["Referencia de Pago"].astype(str).str.strip()
    # Filtrar tickets con referencia valida y tipo Estandar (pagados)
    tk = tk[tk["ref_clean"] != "nan"].copy()
    print(f"  Tickets con referencia: {len(tk):,}")
    return tk


def build_unified(mp, tk):
    """
    Unifica por referencia de pago.
    Cada fila = 1 referencia = 1 transaccion de pago.
    """
    # --- Agregar tickets por referencia ---
    metodo_col = tk.columns[3]  # "Método de Pago"
    tk_agg = tk.groupby("ref_clean").agg(
        ticket_count=("ref_clean", "size"),
        subtotal=("Subtotal", "sum"),
        service=("SERVICE", "sum"),
        total_tk=("TOTAL", "sum"),
        productor=("Productor", "first"),
        evento=("Evento", "first"),
        payment_method=pd.NamedAgg(column=metodo_col, aggfunc="first"),
        fecha_pago=("Fecha de pago", "first"),
    ).reset_index()

    # --- Agregar MP por referencia (tomar la primera fila, sumar montos si hay duplicados) ---
    mp_agg = mp.groupby("ref_clean").agg(
        tx_amount=("TRANSACTION_AMOUNT", "sum"),
        fee=("FEE_AMOUNT", "sum"),
        taxes=("TAXES_AMOUNT", "sum"),
        tx_date=("TRANSACTION_DATE", "first"),
    ).reset_index()

    # --- Merge: tickets LEFT JOIN mp ---
    merged = tk_agg.merge(mp_agg, on="ref_clean", how="left")
    merged["has_mp"] = merged["tx_date"].notna()

    records = []
    for _, row in merged.iterrows():
        subtotal = float(row["subtotal"])
        service = float(row["service"])

        if row["has_mp"]:
            # Con datos MP: costo_sc = SERVICE + taxes + fee (taxes y fee son negativos)
            fee = float(row["fee"])
            taxes = float(row["taxes"])
            costo_sc = service + taxes + fee
            total = subtotal + costo_sc
            dt = row["tx_date"]
        else:
            # Sin datos MP: SC completo, total = TOTAL del ticket
            costo_sc = service
            total = float(row["total_tk"])
            dt = str(row["fecha_pago"])

        # Parsear datetime
        try:
            dt_str = pd.Timestamp(dt).isoformat()
        except Exception:
            dt_str = str(dt)

        records.append({
            "reference_id": row["ref_clean"],
            "productor": str(row["productor"]) if pd.notna(row["productor"]) else "Sin productor",
            "evento": str(row["evento"]),
            "transaction_datetime": dt_str,
            "ticket_count": int(row["ticket_count"]),
            "costo_ticket": round(subtotal, 2),
            "costo_sc": round(costo_sc, 2),
            "total_transaccion": round(total, 2),
            "payment_method": str(row["payment_method"]) if pd.notna(row["payment_method"]) else None,
            "has_mp_data": bool(row["has_mp"]),
        })

    df_unified = pd.DataFrame(records)
    print(f"\n=== DATASET UNIFICADO ===")
    print(f"  Total registros: {len(df_unified):,}")
    print(f"  Con datos MP: {df_unified['has_mp_data'].sum():,}")
    print(f"  Sin datos MP: {(~df_unified['has_mp_data']).sum():,}")
    print(f"  Costo ticket total: ${df_unified['costo_ticket'].sum():,.0f}")
    print(f"  Costo SC total:     ${df_unified['costo_sc'].sum():,.0f}")
    print(f"  Total transaccion:  ${df_unified['total_transaccion'].sum():,.0f}")
    print(f"  Productores unicos: {df_unified['productor'].nunique()}")
    print(f"  Eventos unicos:     {df_unified['evento'].nunique()}")

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

    print("1. Cargando MP CSVs...")
    mp = load_mp()

    print("\n2. Cargando Order Tickets...")
    tk = load_tickets()

    print("\n3. Unificando datasets...")
    records = build_unified(mp, tk)

    print(f"\n4. Subiendo a Supabase ({TABLE})...")
    uploaded = upload_to_supabase(records)

    print(f"\n{'='*50}")
    print(f"COMPLETO: {uploaded:,} registros unificados en Supabase")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
