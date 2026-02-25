"""
Sube los datos de Rendicion de Transferencias a unified_transactions.

Hojas procesadas:
  - CARRASCO: 2059 filas, columnas fijas conocidas
  - CROBAR: 897 filas, columnas ligeramente distintas
  - 195 hojas de eventos: estructura variable, deteccion automatica de columnas

transaction_type = 'RENDICION'
Montos guardados como NEGATIVOS (egresos de Bombo hacia productoras).
reference_id determinístico: "REN-{sheet}-{row_index}" para deduplicacion segura.
"""

import os
import sys
import re
import pandas as pd
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TABLE = "unified_transactions"
BATCH_SIZE = 500
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE = "RENDICIÓN DE TRANSFERENCIAS CARRASCO - CROBAR FINAL.xlsx"

FIXED_SHEETS = {"CARRASCO", "CROBAR"}

# Palabras que indican filas de totales/resumen a saltar
SUMMARY_KEYWORDS = ["total", "falta", "subtotal", "resumen", "suma", "saldo"]

# Timezone de Argentina (UTC-3, sin DST)
TZ_ARG = "America/Argentina/Buenos_Aires"


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Mayúsculas, sin acentos, sin caracteres especiales."""
    s = s.upper().strip()
    for src, dst in [("Á","A"),("É","E"),("Í","I"),("Ó","O"),("Ú","U"),("Ñ","N"),
                     ("À","A"),("È","E"),("Ì","I"),("Ò","O"),("Ù","U")]:
        s = s.replace(src, dst)
    return s


def parse_date(value) -> str | None:
    """Parsea un valor de celda a ISO 8601 con timezone Argentina."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        if ts.tzinfo is None:
            ts = ts.tz_localize(TZ_ARG)
        return ts.isoformat()
    except Exception:
        try:
            ts = pd.to_datetime(str(value), dayfirst=True, errors="raise")
            ts = ts.tz_localize(TZ_ARG)
            return ts.isoformat()
        except Exception:
            return None


def parse_amount(value) -> float | None:
    """
    Parsea un valor de celda a float.
    Maneja: formato argentino (1.234.567,89), prefijo USD/u$s, paréntesis negativos, $.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return None
        return float(value)

    s = str(value).strip()
    if not s or s.lower() in ("nan", "-", "n/a", ""):
        return None

    # Prefijo de moneda extranjera: tratar como misma unidad
    s = re.sub(r"(?i)(u\$s|usd|eur|us\$)\s*", "", s)

    # Paréntesis = negativo
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]

    # Quitar símbolos de moneda y espacios
    s = s.replace("$", "").replace(" ", "").replace("\xa0", "")

    if not s:
        return None

    # Formato argentino: punto = miles, coma = decimal  → "1.234,56" → 1234.56
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        # Sin coma: punto puede ser decimal (si hay exactamente uno y ≤2 decimales)
        parts = s.split(".")
        if len(parts) == 2 and len(parts[1]) <= 2:
            pass  # ya es formato decimal correcto
        else:
            s = s.replace(".", "")  # son separadores de miles

    try:
        result = float(s)
        return -result if negative else result
    except ValueError:
        return None


def is_summary_row(row) -> bool:
    """Devuelve True si la fila parece ser una fila de totales/resumen."""
    row_str = " ".join(str(v).lower() for v in row.values if pd.notna(v))
    return any(kw in row_str for kw in SUMMARY_KEYWORDS)


# ─────────────────────────────────────────────
# Parsers de hojas fijas
# ─────────────────────────────────────────────

def _str(val) -> str | None:
    """Convierte un valor de celda a string limpio, o None si está vacío."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s if s and s.lower() != "nan" else None


def load_sheet_carrasco(xl: pd.ExcelFile) -> list[dict]:
    """
    Parsea la hoja CARRASCO con su esquema fijo.
    Columnas: Fecha, MONTO transf, CUENTA destino, BENEFICIARIO, CBU, CUIT,
              EVENTO LIQUIDADO, FECHA EVENTO, MONTO ABONADO, DEVOLUCIONES,
              MONTO LIQUIDACIÓN, IMPUESTO D&C, INGRESOS EN LOUD, DEUDA LOUD
    """
    df = xl.parse("CARRASCO", header=0)
    records = []

    for idx, row in df.iterrows():
        if row.isna().all():
            continue
        if is_summary_row(row):
            continue

        fecha = parse_date(row.get("Fecha"))
        if fecha is None:
            continue

        monto = parse_amount(row.get("MONTO transf"))
        if monto is None:
            continue

        beneficiario = _str(row.get("BENEFICIARIO")) or "CARRASCO"
        evento = _str(row.get("EVENTO LIQUIDADO")) or "Sin evento"

        records.append({
            "reference_id": f"REN-CARRASCO-{idx}",
            "productor": beneficiario,
            "evento": evento,
            "transaction_datetime": fecha,
            "ticket_count": 0,
            "costo_ticket": round(abs(parse_amount(row.get("MONTO ABONADO")) or 0.0), 2),
            "costo_sc": round(abs(parse_amount(row.get("MONTO LIQUIDACIÓN")) or 0.0), 2),
            "total_transaccion": round(-abs(monto), 2),  # negativo = egreso
            "payment_method": "transferencia",
            "has_mp_data": False,
            "transaction_type": "RENDICION",
            # Campos específicos de rendicion
            "cuenta_destino": _str(row.get("CUENTA destino")),
            "cbu": _str(row.get("CBU")),
            "cuit": _str(row.get("CUIT")),
            "fecha_evento": parse_date(row.get("FECHA EVENTO")),
            "devoluciones": round(abs(parse_amount(row.get("DEVOLUCIONES")) or 0.0), 2) or None,
            "impuesto_dc": round(abs(parse_amount(row.get("IMPUESTO D&C")) or 0.0), 2) or None,
            "ingresos_loud": round(abs(parse_amount(row.get("INGRESOS EN LOUD")) or 0.0), 2) or None,
            "deuda_loud": round(abs(parse_amount(row.get("DEUDA LOUD")) or 0.0), 2) or None,
        })

    print(f"  CARRASCO: {len(records):,} registros válidos")
    return records


def load_sheet_crobar(xl: pd.ExcelFile) -> list[dict]:
    """
    Parsea la hoja CROBAR.
    Diferencias vs CARRASCO:
      - Fecha → "FECHA" (mayúsculas)
      - MONTO transf → "MONTO tranferido" (typo intencional en el origen)
      - Sin columna BENEFICIARIO → productor = "CROBAR"
      - Sin CBU, CUIT, DEUDA LOUD
    """
    df = xl.parse("CROBAR", header=1)  # encabezados en fila 1
    records = []

    for idx, row in df.iterrows():
        if row.isna().all():
            continue
        if is_summary_row(row):
            continue

        fecha = parse_date(row.get("FECHA"))
        if fecha is None:
            continue

        # El typo "tranferido" (sin s) existe literalmente en el archivo fuente
        monto = parse_amount(row.get("MONTO tranferido"))
        if monto is None:
            continue

        evento = _str(row.get("EVENTO LIQUIDADO")) or "Sin evento"

        records.append({
            "reference_id": f"REN-CROBAR-{idx}",
            "productor": "CROBAR",
            "evento": evento,
            "transaction_datetime": fecha,
            "ticket_count": 0,
            "costo_ticket": round(abs(parse_amount(row.get("MONTO ABONADO")) or 0.0), 2),
            "costo_sc": round(abs(parse_amount(row.get("MONTO LIQUIDACIÓN")) or 0.0), 2),
            "total_transaccion": round(-abs(monto), 2),
            "payment_method": "transferencia",
            "has_mp_data": False,
            "transaction_type": "RENDICION",
            # Campos específicos de rendicion
            "cuenta_destino": _str(row.get("CUENTA")),
            "cbu": None,
            "cuit": None,
            "fecha_evento": parse_date(row.get("FECHA EVENTO")),
            "devoluciones": round(abs(parse_amount(row.get("DEVOLUCIONES")) or 0.0), 2) or None,
            "impuesto_dc": round(abs(parse_amount(row.get("IMPUESTO D&C")) or 0.0), 2) or None,
            "ingresos_loud": round(abs(parse_amount(row.get("INGRESOS EN LOUD")) or 0.0), 2) or None,
            "deuda_loud": None,
        })

    print(f"  CROBAR: {len(records):,} registros válidos")
    return records


# ─────────────────────────────────────────────
# Detección de columnas para hojas de eventos
# ─────────────────────────────────────────────

def detect_columns(df: pd.DataFrame, sheet_name: str) -> dict:
    """
    Auto-detecta qué columna cumple cada rol en una hoja de evento.
    Retorna: {date_col, amount_col, costo_ticket_col, costo_sc_col, productor_col}
    Todos pueden ser None si no se detecta.
    """
    # Mapa: nombre_normalizado → nombre_original
    norm_map = {}
    for col in df.columns:
        col_str = str(col)
        if not col_str.startswith("Unnamed"):
            norm_map[_normalize(col_str)] = col

    result = {
        "date_col": None,
        "amount_col": None,
        "costo_ticket_col": None,
        "costo_sc_col": None,
        "productor_col": None,
        "cuenta_col": None,
        "cbu_col": None,
        "cuit_col": None,
    }

    def find_col(keywords: list[str]) -> str | None:
        for kw in keywords:
            for norm, orig in norm_map.items():
                if kw in norm:
                    return orig
        return None

    # Fecha: buscar por keyword, luego por parsing heurístico
    result["date_col"] = find_col(["FECHA", "DATE", "DIA", "FEC"])
    if result["date_col"] is None:
        for col in df.columns:
            series = df[col].dropna()
            if len(series) == 0:
                continue
            parsed = pd.to_datetime(series, errors="coerce", dayfirst=True)
            if parsed.notna().sum() / len(series) > 0.3:
                result["date_col"] = col
                break

    # Monto transferido
    result["amount_col"] = find_col([
        "MONTO TRANSF", "MONTO TRANSFER", "MONTO TRANF", "TRANSFERIDO",
        "IMPORTE", "MONTO",
    ])

    # Monto abonado
    result["costo_ticket_col"] = find_col(["MONTO ABONADO", "ABONADO", "COBRADO", "BRUTO"])

    # Monto liquidación
    result["costo_sc_col"] = find_col(["LIQUIDACION", "LIQUIDACIÓN", "NETO", "ACREDITADO"])

    # Productora/beneficiario
    result["productor_col"] = find_col(["BENEFICIARIO", "PRODUCTOR", "RAZON", "TITULAR", "NOMBRE"])

    # Cuenta destino
    result["cuenta_col"] = find_col(["CUENTA DESTINO", "CUENTA", "BANCO"])

    # CBU
    result["cbu_col"] = find_col(["CBU"])

    # CUIT / CUIL
    result["cuit_col"] = find_col(["CUIT", "CUIL"])

    return result


def load_event_sheet(xl: pd.ExcelFile, sheet_name: str) -> list[dict]:
    """
    Parsea una hoja de evento con estructura variable.
    - Detecta el header real (puede estar en offset 0, 1, 2, 3)
    - Detecta columnas por keywords y heurísticas
    - Salta filas vacías y de resumen
    """
    # ── Paso 1: Encontrar la fila de encabezado real ──
    try:
        df_try = xl.parse(sheet_name, header=0, nrows=20)
    except Exception as e:
        print(f"    [{sheet_name}] ERROR al leer: {e}")
        return []

    unnamed_count = sum(1 for c in df_try.columns if str(c).startswith("Unnamed"))
    df = None

    if unnamed_count > len(df_try.columns) / 2:
        for offset in [1, 2, 3]:
            try:
                df_candidate = xl.parse(sheet_name, header=offset)
                u = sum(1 for c in df_candidate.columns if str(c).startswith("Unnamed"))
                if u <= len(df_candidate.columns) / 4:
                    df = df_candidate
                    break
            except Exception:
                continue

    if df is None:
        df = xl.parse(sheet_name, header=0)

    if df is None or df.empty:
        return []

    # ── Paso 2: Detectar columnas ──
    cols = detect_columns(df, sheet_name)

    if cols["date_col"] is None and cols["amount_col"] is None:
        return []

    # ── Paso 3: Parsear filas ──
    safe_sheet = re.sub(r"[^A-Za-z0-9_-]", "_", sheet_name)
    records = []

    for idx, row in df.iterrows():
        if row.isna().all():
            continue
        if is_summary_row(row):
            continue

        # Fecha obligatoria para considerar la fila como dato
        fecha = None
        if cols["date_col"] is not None:
            fecha = parse_date(row.get(cols["date_col"]))
        if fecha is None:
            continue

        monto = 0.0
        if cols["amount_col"] is not None:
            monto = abs(parse_amount(row.get(cols["amount_col"])) or 0.0)

        costo_ticket = 0.0
        if cols["costo_ticket_col"] is not None:
            costo_ticket = abs(parse_amount(row.get(cols["costo_ticket_col"])) or 0.0)

        costo_sc = 0.0
        if cols["costo_sc_col"] is not None:
            costo_sc = abs(parse_amount(row.get(cols["costo_sc_col"])) or 0.0)

        # Productor: preferir columna detectada, fallback al nombre de la hoja
        productor = sheet_name
        if cols["productor_col"] is not None:
            val = row.get(cols["productor_col"])
            if pd.notna(val) and str(val).strip():
                productor = str(val).strip()

        # Campos específicos: intentar detectar CBU, CUIT, cuenta en hojas de evento
        cbu_val = None
        cuit_val = None
        cuenta_val = None
        if cols.get("cbu_col"):
            cbu_val = _str(row.get(cols["cbu_col"]))
        if cols.get("cuit_col"):
            cuit_val = _str(row.get(cols["cuit_col"]))
        if cols.get("cuenta_col"):
            cuenta_val = _str(row.get(cols["cuenta_col"]))

        records.append({
            "reference_id": f"REN-{safe_sheet}-{idx}",
            "productor": productor,
            "evento": sheet_name,
            "transaction_datetime": fecha,
            "ticket_count": 0,
            "costo_ticket": round(costo_ticket, 2),
            "costo_sc": round(costo_sc, 2),
            "total_transaccion": round(-monto, 2),  # negativo = egreso
            "payment_method": "transferencia",
            "has_mp_data": False,
            "transaction_type": "RENDICION",
            # Campos específicos de rendicion
            "cuenta_destino": cuenta_val,
            "cbu": cbu_val,
            "cuit": cuit_val,
            "fecha_evento": None,  # hojas de evento no tienen esta columna separada
            "devoluciones": None,
            "impuesto_dc": None,
            "ingresos_loud": None,
            "deuda_loud": None,
        })

    return records


# ─────────────────────────────────────────────
# Carga de todas las hojas
# ─────────────────────────────────────────────

def load_all_sheets() -> list[dict]:
    """Carga las 197 hojas del Excel y retorna todos los registros."""
    path = os.path.join(BASE_DIR, EXCEL_FILE)
    if not os.path.exists(path):
        print(f"ERROR: Archivo no encontrado: {path}")
        sys.exit(1)

    print(f"Abriendo {EXCEL_FILE}...")
    xl = pd.ExcelFile(path, engine="openpyxl")
    all_names = xl.sheet_names
    print(f"  Total de hojas: {len(all_names)}")

    all_records = []
    skipped = []

    print("\nParsing hoja CARRASCO...")
    all_records.extend(load_sheet_carrasco(xl))

    print("Parsing hoja CROBAR...")
    all_records.extend(load_sheet_crobar(xl))

    event_sheets = [s for s in all_names if s not in FIXED_SHEETS]
    print(f"\nParsing {len(event_sheets)} hojas de eventos...")

    for i, sheet_name in enumerate(event_sheets, 1):
        try:
            records = load_event_sheet(xl, sheet_name)
            if records:
                all_records.extend(records)
                if i % 20 == 0 or i == len(event_sheets):
                    print(f"  [{i}/{len(event_sheets)}] ... total acumulado: {len(all_records):,}")
            else:
                skipped.append(sheet_name)
        except Exception as e:
            print(f"  [{i}] ERROR en hoja '{sheet_name}': {e}")
            skipped.append(sheet_name)

    print(f"\n  Hojas con datos: {len(event_sheets) - len(skipped)}")
    print(f"  Hojas vacías/saltadas: {len(skipped)}")
    if skipped:
        sample = ", ".join(skipped[:5])
        print(f"    Ejemplos: {sample}{'...' if len(skipped) > 5 else ''}")

    return all_records


# ─────────────────────────────────────────────
# Deduplicación
# ─────────────────────────────────────────────

def check_existing_rendicion() -> set[str]:
    """
    Consulta Supabase para obtener todos los reference_id con transaction_type=RENDICION.
    Usa paginación de 1000 registros.
    """
    existing = set()
    offset = 0
    limit = 1000

    get_headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    with httpx.Client(timeout=30.0) as client:
        while True:
            url = (
                f"{SUPABASE_URL}/rest/v1/{TABLE}"
                f"?select=reference_id"
                f"&transaction_type=eq.RENDICION"
                f"&limit={limit}&offset={offset}"
            )
            resp = client.get(url, headers=get_headers)
            resp.raise_for_status()
            data = resp.json()

            for row in data:
                if row.get("reference_id"):
                    existing.add(row["reference_id"])

            if len(data) < limit:
                break
            offset += limit

    print(f"  Ya cargados en Supabase: {len(existing):,} registros RENDICION")
    return existing


def filter_new_records(records: list[dict], existing_refs: set[str]) -> list[dict]:
    new = [r for r in records if r["reference_id"] not in existing_refs]
    dupes = len(records) - len(new)
    if dupes:
        print(f"  Duplicados omitidos: {dupes:,}")
    return new


# ─────────────────────────────────────────────
# Upload a Supabase
# ─────────────────────────────────────────────

def upload_batch(client: httpx.Client, batch: list[dict]) -> int:
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    post_headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = client.post(url, json=batch, headers=post_headers)
    resp.raise_for_status()
    return len(batch)


def upload_to_supabase(records: list[dict]) -> int:
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


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: Configura SUPABASE_URL y SUPABASE_KEY en .env")
        sys.exit(1)

    print("=" * 60)
    print("UPLOAD RENDICION DE TRANSFERENCIAS")
    print("=" * 60)

    print("\n1. Cargando hojas del Excel...")
    records = load_all_sheets()
    print(f"\n   Total registros parseados: {len(records):,}")

    # Estadísticas antes de subir
    if records:
        total_monto = sum(r["total_transaccion"] for r in records)
        productores = {r["productor"] for r in records}
        eventos = {r["evento"] for r in records}
        print(f"   Total transferido (negativo=egreso): ${total_monto:,.0f}")
        print(f"   Productores únicos: {len(productores)}")
        print(f"   Eventos únicos: {len(eventos)}")

    print("\n2. Verificando registros ya cargados en Supabase...")
    existing_refs = check_existing_rendicion()

    print("\n3. Filtrando nuevos registros...")
    new_records = filter_new_records(records, existing_refs)
    print(f"   Nuevos a subir: {len(new_records):,}")

    if not new_records:
        print("\n   No hay registros nuevos. Nada que subir.")
        return

    print(f"\n4. Subiendo a Supabase ({TABLE})...")
    uploaded = upload_to_supabase(new_records)

    print(f"\n{'=' * 60}")
    print(f"COMPLETO: {uploaded:,} registros RENDICION agregados")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
