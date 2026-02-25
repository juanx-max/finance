import pandas as pd

csv_files = ['Jun- Jul.csv', 'Ago- Sep.csv', 'Oct - Nov.csv', 'Dic - Ene.csv']
frames = []
for f in csv_files:
    df = pd.read_csv(f, sep=';', on_bad_lines='skip', low_memory=False)
    frames.append(df)
mp = pd.concat(frames, ignore_index=True)

mp['TRANSACTION_AMOUNT'] = pd.to_numeric(mp['TRANSACTION_AMOUNT'], errors='coerce')
mp['SETTLEMENT_NET_AMOUNT'] = pd.to_numeric(mp['SETTLEMENT_NET_AMOUNT'], errors='coerce')
mp['FEE_AMOUNT'] = pd.to_numeric(mp['FEE_AMOUNT'], errors='coerce')
mp['TAXES_AMOUNT'] = pd.to_numeric(mp['TAXES_AMOUNT'], errors='coerce')
mp['TRANSACTION_DATE'] = pd.to_datetime(mp['TRANSACTION_DATE'], errors='coerce', utc=True)

print('=== TODOS LOS TRANSACTION_TYPE ===')
summary = mp.groupby('TRANSACTION_TYPE').agg(
    count=('TRANSACTION_AMOUNT', 'size'),
    sum_tx_amount=('TRANSACTION_AMOUNT', 'sum'),
    sum_net=('SETTLEMENT_NET_AMOUNT', 'sum'),
).reset_index()
for _, row in summary.iterrows():
    tt = row['TRANSACTION_TYPE']
    cnt = int(row['count'])
    tx = row['sum_tx_amount']
    net = row['sum_net']
    print(f'  {tt:20s}  count={cnt:>7,}  TX_AMOUNT=${tx:>20,.0f}  NET=${net:>20,.0f}')

total_net = mp['SETTLEMENT_NET_AMOUNT'].sum()
total_tx = mp['TRANSACTION_AMOUNT'].sum()
print(f'\nSuma SETTLEMENT_NET_AMOUNT (todos los tipos): ${total_net:,.0f}')
print(f'Suma TRANSACTION_AMOUNT (todos los tipos):    ${total_tx:,.0f}')

# Balance al 1 de Julio = todo hasta 30/Jun
jun = mp[mp['TRANSACTION_DATE'] < '2025-07-01']
print(f'\n=== BALANCE AL 1 DE JULIO 2025 ===')
print(f'Movimientos hasta 30/Jun: {len(jun):,}')

jun_by_type = jun.groupby('TRANSACTION_TYPE').agg(
    count=('TRANSACTION_AMOUNT', 'size'),
    sum_tx=('TRANSACTION_AMOUNT', 'sum'),
    sum_net=('SETTLEMENT_NET_AMOUNT', 'sum'),
).reset_index()
for _, row in jun_by_type.iterrows():
    tt = row['TRANSACTION_TYPE']
    cnt = int(row['count'])
    tx = row['sum_tx']
    net = row['sum_net']
    print(f'  {tt:20s}  count={cnt:>7,}  TX=${tx:>18,.0f}  NET=${net:>18,.0f}')

print(f'\n  BALANCE NETO al 1/Jul (sum NET): ${jun["SETTLEMENT_NET_AMOUNT"].sum():,.0f}')
print(f'  BALANCE TX al 1/Jul (sum TX):    ${jun["TRANSACTION_AMOUNT"].sum():,.0f}')

# Mes a mes
print('\n=== BALANCE NETO ACUMULADO MES A MES ===')
mp['month'] = mp['TRANSACTION_DATE'].dt.strftime('%Y-%m')
monthly = mp.groupby('month').agg(
    net=('SETTLEMENT_NET_AMOUNT', 'sum'),
    tx=('TRANSACTION_AMOUNT', 'sum'),
    count=('TRANSACTION_AMOUNT', 'size'),
).reset_index().sort_values('month')

acum = 0
for _, row in monthly.iterrows():
    acum += row['net']
    print(f'  {row["month"]}  movimientos={int(row["count"]):>7,}  neto_mes=${row["net"]:>18,.0f}  acumulado=${acum:>18,.0f}')
