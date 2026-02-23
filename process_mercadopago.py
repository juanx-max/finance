import os
import re
import sys
import pandas as pd
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TABLE_NAME = "mercadopago_transactions"
BATCH_SIZE = 500
CHUNK_SIZE = 10000

CSV_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILES = [
    "Jun- Jul.csv",
    "Ago- Sep.csv",
    "Oct - Nov.csv",
    "Dic - Ene.csv",
]

# --- Filtros de filas que NO son eventos ---

NON_EVENT_EXACT = {
    "Bank Transfer",
    "Devolucion Swap",
    "Devolucion de swap",
    "Saldo en deuda por controversia",
    "Pedido Piccadely",
    "Link Bombo",
    "Link Dev Swap",
    "Regularizar Pago SWAP",
    "Prueba",
    "Test",
    "VAR",
    "Varios",
    "Pago de servicios",
    "Personal Flow",
    "",
}

NON_EVENT_PREFIXES = [
    "Pago de factura",
    "Pago:",
    "TELECOM",
]

PRODUCT_KEYWORDS = [
    "mouse", "logitech", "disco portatil", "escurridor", "espejo",
    "cortinas", "barral", "lampara", "mesa ratona", "perchero",
    "toallas", "microfono", "luz led", "cafetera", "canasto",
    "tripode", "tacho", "vaso copon", "zapatilla", "mueble",
    "folios", "fragancias", "pagare", "termo termolar",
    "archivero", "braun", "seagate",
]


def clean_sale_detail(raw) -> str | None:
    if pd.isna(raw):
        return None

    s = str(raw).strip()
    if not s:
        return None

    # Remover sufijo: " + N Item adicional" o similar
    s = re.sub(r'"\s*\+\s*\d+\s*(Item\s+adicional|productos?)$', '', s)

    # Quitar comillas envolventes
    while s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1]
    s = s.strip('"').strip()

    if not s:
        return None

    # Chequear contra listas de exclusion
    if s in NON_EVENT_EXACT:
        return None

    for prefix in NON_EVENT_PREFIXES:
        if s.startswith(prefix):
            return None

    s_lower = s.lower()
    for keyword in PRODUCT_KEYWORDS:
        if keyword in s_lower:
            return None

    # Quitar prefijo "Link de pago - "
    if s.lower().startswith("link de pago - "):
        s = s[len("Link de pago - "):]

    # Quitar prefijo "N x " (ej: "1 x ", "2 x ")
    s = re.sub(r'^\d+\s*[xX]\s+', '', s)

    # Quitar prefijo numerico seguido de tipo de ticket (ej: "1 BACKSTAGE", "4 LOTE GENERAL 2")
    s = re.sub(
        r'^\d+\s+(?:BACKSTAGE|GENERAL\s*\d*|LOTE\s*(?:GENERAL\s*)?\d*|VIP\s*(?:STANDING\s*)?(?:LOTE\s*)?\d*|PREVENTA\s*\d*)\s*',
        '', s, flags=re.IGNORECASE
    )

    # Limpiar guion suelto al inicio (de patrones como "1 x - General 2 - EVENT")
    s = re.sub(r'^-\s*', '', s).strip()

    # Cortar en el primer " - " (tomar solo la parte izquierda)
    if " - " in s:
        s = s.split(" - ")[0].strip()

    # Limpiar sufijo de cantidad tipo " X 2", " X 3"
    s = re.sub(r'\s+[xX]\s*\d+$', '', s)

    # Quitar si quedo solo un tipo de ticket sin nombre de evento
    ticket_only = re.fullmatch(
        r'(?:Tier|Lote|General|VIP|GENERAL|Early\s*Bird|BACKSTAGE|Last\s*Call|PREVENTA|TANDA|PARKING|COMBO|Promo)\s*\d*(?:\s*(?:VIP|STANDING|CAMPO|Combo|Pax)\s*\d*)*',
        s, flags=re.IGNORECASE
    )
    if ticket_only:
        return None

    s = s.strip()
    if not s or len(s) < 2:
        return None

    return s


def read_csv_chunks(filepath):
    return pd.read_csv(
        filepath,
        sep=";",
        quotechar='"',
        usecols=[6, 24, 25],
        dtype=str,
        chunksize=CHUNK_SIZE,
        encoding="utf-8",
        on_bad_lines="warn",
    )


def process_chunk(df, source_file):
    df = df.copy()
    df["event_name"] = df["SALE_DETAIL"].apply(clean_sale_detail)
    df = df.dropna(subset=["event_name"])
    df = df.dropna(subset=["TRANSACTION_AMOUNT", "MONEY_RELEASE_DATE"])

    df["transaction_amount"] = pd.to_numeric(df["TRANSACTION_AMOUNT"], errors="coerce")
    df = df.dropna(subset=["transaction_amount"])

    records = []
    for _, row in df.iterrows():
        records.append({
            "transaction_amount": float(row["transaction_amount"]),
            "money_release_date": row["MONEY_RELEASE_DATE"],
            "event_name": row["event_name"],
            "source_file": source_file,
        })
    return records


def upload_batch(client, records):
    url = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = client.post(url, json=records, headers=headers)
    resp.raise_for_status()
    return len(records)


def upload_to_supabase(client, records):
    uploaded = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        try:
            uploaded += upload_batch(client, batch)
        except httpx.HTTPStatusError as e:
            print(f"  ERROR batch {i // BATCH_SIZE + 1}: {e.response.status_code} - {e.response.text[:200]}")
        except Exception as e:
            print(f"  ERROR batch {i // BATCH_SIZE + 1}: {e}")
    return uploaded


def main():
    if not SUPABASE_URL or not SUPABASE_KEY or "tu-proyecto" in SUPABASE_URL:
        print("ERROR: Configura SUPABASE_URL y SUPABASE_KEY en el archivo .env")
        sys.exit(1)

    print(f"Conectando a Supabase: {SUPABASE_URL}")

    total_processed = 0
    total_uploaded = 0

    with httpx.Client(timeout=30.0) as client:
        for csv_file in CSV_FILES:
            filepath = os.path.join(CSV_DIR, csv_file)
            if not os.path.exists(filepath):
                print(f"AVISO: {csv_file} no encontrado, saltando.")
                continue

            print(f"\nProcesando {csv_file}...")
            file_processed = 0
            file_uploaded = 0
            chunk_num = 0

            for chunk_df in read_csv_chunks(filepath):
                chunk_num += 1
                file_processed += len(chunk_df)

                records = process_chunk(chunk_df, csv_file)
                if records:
                    uploaded = upload_to_supabase(client, records)
                    file_uploaded += uploaded

                print(f"  Chunk {chunk_num}: {len(chunk_df)} leidas, "
                      f"{len(records)} eventos, {file_uploaded} subidas total")

            total_processed += file_processed
            total_uploaded += file_uploaded
            print(f"  Listo: {file_processed} filas -> {file_uploaded} eventos subidos")

    print(f"\n{'=' * 50}")
    print(f"COMPLETO")
    print(f"  Total filas leidas:  {total_processed:,}")
    print(f"  Total eventos subidos: {total_uploaded:,}")
    print(f"  Filtradas:           {total_processed - total_uploaded:,}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
