import os
import httpx
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
headers = {"apikey": key, "Authorization": f"Bearer {key}"}

# Muestra 10 filas de ejemplo
r = httpx.get(
    f"{url}/rest/v1/mercadopago_transactions?select=event_name,transaction_amount,money_release_date,source_file&limit=10",
    headers=headers,
)
data = r.json()
print("=== 10 filas de ejemplo ===")
for row in data:
    name = row["event_name"]
    amount = row["transaction_amount"]
    date = row["money_release_date"][:10]
    src = row["source_file"]
    print(f"  {name:40s} | ${amount:>12} | {date} | {src}")

print()

# Eventos unicos
r2 = httpx.get(
    f"{url}/rest/v1/mercadopago_transactions?select=event_name&limit=5000",
    headers=headers,
)
names = set(row["event_name"] for row in r2.json())
print(f"=== Eventos unicos (de primeras 5000 filas): {len(names)} ===")
for name in sorted(names):
    print(f"  - {name}")
