import os, httpx
from dotenv import load_dotenv
load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
h = {"apikey": key, "Authorization": f"Bearer {key}"}

# "Tickets" por source_file
print('=== Registros con event_name="Tickets" por archivo ===')
for sf in ["Jun- Jul.csv", "Ago- Sep.csv", "Oct - Nov.csv", "Dic - Ene.csv"]:
    encoded = sf.replace(" ", "%20")
    r = httpx.get(
        f'{url}/rest/v1/mercadopago_transactions?event_name=eq.Tickets&source_file=eq.{encoded}&select=id',
        headers={**h, "Prefer": "count=exact", "Range": "0-0"}
    )
    count = r.headers.get("content-range", "unknown")
    print(f"  {sf}: {count}")

# Total "Tickets"
r2 = httpx.get(
    f'{url}/rest/v1/mercadopago_transactions?event_name=eq.Tickets&select=id',
    headers={**h, "Prefer": "count=exact", "Range": "0-0"}
)
print(f"  TOTAL 'Tickets': {r2.headers.get('content-range', 'unknown')}")

# % del total
print(f"\n  Total registros: 243,216")
print(f"  'Tickets' generico: 162,512 = {162512/243216*100:.1f}% del total")

# Otros genericos
print("\n=== Otros event_names sospechosos y su count ===")
for name in ["TICKETS VIP", "Ticket", "ticket", "TICKET"]:
    r3 = httpx.get(
        f'{url}/rest/v1/mercadopago_transactions?event_name=eq.{name}&select=id',
        headers={**h, "Prefer": "count=exact", "Range": "0-0"}
    )
    ct = r3.headers.get("content-range", "unknown")
    print(f"  '{name}': {ct}")

# Veamos los SALE_DETAIL originales que producen "Tickets" - miremos el CSV directo
print("\n=== Muestra de montos de 'Tickets' para entender el patron ===")
r4 = httpx.get(
    f'{url}/rest/v1/mercadopago_transactions?event_name=eq.Tickets&select=transaction_amount&order=transaction_amount.desc&limit=10',
    headers=h
)
for row in r4.json():
    print(f"  ${float(row['transaction_amount']):>12,.0f}")

r5 = httpx.get(
    f'{url}/rest/v1/mercadopago_transactions?event_name=eq.Tickets&select=transaction_amount&order=transaction_amount.asc&limit=10',
    headers=h
)
print("  ...")
for row in r5.json():
    print(f"  ${float(row['transaction_amount']):>12,.0f}")
