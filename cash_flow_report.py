import os, httpx
from dotenv import load_dotenv
load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
h = {"apikey": key, "Authorization": f"Bearer {key}"}

r = httpx.get(f"{url}/rest/v1/v_balance_monthly?select=*&order=mes.asc", headers=h)
data = r.json()

total_ing = 0
total_pay = 0
total_ref = 0
total_cb = 0

print("MES            |    INGRESOS    |     PAYOUTS    |   REFUNDS+CB   |    NETO MES    |    BALANCE")
print("-" * 110)
for row in data:
    ing = row["ingresos"] or 0
    pay = row["payouts"] or 0
    ref = row["refunds"] or 0
    cb = row["chargebacks"] or 0
    neto = row["neto_mes"]
    bal = row["balance"]
    total_ing += ing
    total_pay += pay
    total_ref += ref
    total_cb += cb

    mes = row["mes"][:7]
    print(f"{mes}        | {ing:>14,.0f} | {pay:>14,.0f} | {ref+cb:>14,.0f} | {neto:>14,.0f} | {bal:>14,.0f}")

salidas = total_pay + total_ref + total_cb
balance = total_ing + salidas

print("-" * 110)
print()
print("=== FLUJO DE CAJA TOTAL ===")
print(f"  Ingresos (SETTLEMENT):     +${total_ing:,.0f}")
print(f"  Payouts:                    ${total_pay:,.0f}")
print(f"  Refunds:                    ${total_ref:,.0f}")
print(f"  Chargebacks:                ${total_cb:,.0f}")
print(f"  Total salidas:              ${salidas:,.0f}")
print(f"  -----------------------------------------")
print(f"  BALANCE FINAL:              ${balance:,.0f}")
