import os, httpx
from dotenv import load_dotenv
load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
h = {"apikey": key, "Authorization": f"Bearer {key}"}

# Top events by ticket count
print("=== Top 30 eventos por CANTIDAD de tickets ===")
r = httpx.get(f"{url}/rest/v1/v_top_events?select=event_name,cantidad_tickets,total_facturado&order=cantidad_tickets.desc&limit=30", headers=h)
for row in r.json():
    name = row["event_name"]
    tickets = int(row["cantidad_tickets"])
    total = float(row["total_facturado"])
    print(f"  {name:50s} | Tickets: {tickets:>7,} | Total: ${total:>15,.0f}")

# Buscar event_names sospechosos (cortos, genericos)
print("\n=== Eventos con nombres cortos o sospechosos ===")
r2 = httpx.get(f"{url}/rest/v1/v_top_events?select=event_name,cantidad_tickets,total_facturado&order=cantidad_tickets.desc&limit=500", headers=h)
suspect_keywords = ["general", "link", "pago", "entrada", "ticket", "tier", "lote", "vip", "combo", "promo", "early"]
for row in r2.json():
    name = row["event_name"]
    name_lower = name.lower()
    is_short = len(name) <= 4
    is_suspect = any(kw in name_lower for kw in suspect_keywords)
    if is_short or is_suspect:
        tickets = int(row["cantidad_tickets"])
        total = float(row["total_facturado"])
        reason = "SHORT" if is_short else "KEYWORD"
        print(f"  [{reason}] {name:50s} | Tickets: {tickets:>7,} | Total: ${total:>15,.0f}")

# Registros por source_file con Ago-Sep detalle
print("\n=== Ago-Sep: sample event_names (50 random) ===")
r3 = httpx.get(f"{url}/rest/v1/mercadopago_transactions?source_file=eq.Ago- Sep.csv&select=event_name,transaction_amount&limit=50&offset=1000", headers=h)
for row in r3.json():
    name = row["event_name"]
    amt = float(row["transaction_amount"])
    print(f"  {name:50s} | ${amt:>12,.0f}")

# Count total and by Ago-Sep
print("\n=== Totales ===")
for sf in ["Ago- Sep.csv"]:
    r4 = httpx.get(f"{url}/rest/v1/mercadopago_transactions?source_file=eq.{sf}&select=id", headers={**h, "Prefer": "count=exact", "Range": "0-0"})
    count = r4.headers.get("content-range", "unknown")
    print(f"  {sf}: {count}")

# Total global
r5 = httpx.get(f"{url}/rest/v1/mercadopago_transactions?select=id", headers={**h, "Prefer": "count=exact", "Range": "0-0"})
print(f"  TOTAL: {r5.headers.get('content-range', 'unknown')}")
