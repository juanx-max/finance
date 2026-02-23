import os
import httpx
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
h = {"apikey": key, "Authorization": f"Bearer {key}"}

print("=== v_cash_flow_calendar (ultimos 5 dias) ===")
r = httpx.get(f"{url}/rest/v1/v_cash_flow_calendar?select=*&order=fecha_acreditacion.desc&limit=5", headers=h)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    for row in r.json():
        dia = float(row["monto_del_dia"])
        acum = float(row["acumulado"])
        print(f"  {row['fecha_acreditacion']} | Txns: {row['cantidad_transacciones']} | Dia: ${dia:,.0f} | Acum: ${acum:,.0f}")
else:
    print(r.text[:300])

print()
print("=== v_monthly_trends ===")
r2 = httpx.get(f"{url}/rest/v1/v_monthly_trends?select=*&order=mes.asc", headers=h)
print(f"Status: {r2.status_code}")
if r2.status_code == 200:
    for row in r2.json():
        rev = float(row["revenue_bruto"])
        crec = row["crecimiento_pct"] if row["crecimiento_pct"] is not None else "-"
        print(f"  {row['mes']} | Txns: {row['cantidad_transacciones']:>6} | Eventos: {row['eventos_unicos']:>3} | Rev: ${rev:>15,.0f} | Crec: {crec}%")
else:
    print(r2.text[:300])

print()
print("=== v_top_events (top 10) ===")
r3 = httpx.get(f"{url}/rest/v1/v_top_events?select=*&order=total_facturado.desc&limit=10", headers=h)
print(f"Status: {r3.status_code}")
if r3.status_code == 200:
    for row in r3.json():
        total = float(row["total_facturado"])
        print(f"  {row['event_name']:40s} | Tickets: {row['cantidad_tickets']:>6} | Total: ${total:>15,.0f}")
else:
    print(r3.text[:300])
