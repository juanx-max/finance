-- =====================================================
-- Agregar cash flow completo a unified_transactions
-- Ejecutar en Supabase Dashboard > SQL Editor
-- =====================================================

-- 1. Nueva columna (los registros existentes quedan como SETTLEMENT)
ALTER TABLE unified_transactions
  ADD COLUMN IF NOT EXISTS transaction_type text NOT NULL DEFAULT 'SETTLEMENT';

CREATE INDEX IF NOT EXISTS idx_unified_txtype ON unified_transactions(transaction_type);

-- 2. Actualizar vistas existentes para filtrar solo SETTLEMENT
CREATE OR REPLACE VIEW v_unified_by_productor AS
SELECT
  productor,
  count(*) as total_transacciones,
  sum(ticket_count) as total_tickets,
  sum(costo_ticket) as total_costo_ticket,
  sum(costo_sc) as total_costo_sc,
  sum(total_transaccion) as total_neto,
  round(avg(total_transaccion), 2) as avg_transaccion
FROM unified_transactions
WHERE transaction_type = 'SETTLEMENT'
GROUP BY productor
ORDER BY total_neto DESC;

CREATE OR REPLACE VIEW v_unified_by_evento AS
SELECT
  productor,
  evento,
  count(*) as total_transacciones,
  sum(ticket_count) as total_tickets,
  sum(costo_ticket) as total_costo_ticket,
  sum(costo_sc) as total_costo_sc,
  sum(total_transaccion) as total_neto,
  round(avg(total_transaccion), 2) as avg_transaccion,
  min(transaction_datetime) as primera_venta,
  max(transaction_datetime) as ultima_venta
FROM unified_transactions
WHERE transaction_type = 'SETTLEMENT'
GROUP BY productor, evento
ORDER BY total_neto DESC;

CREATE OR REPLACE VIEW v_unified_monthly AS
SELECT
  date_trunc('month', transaction_datetime)::date as mes,
  count(*) filter (where transaction_type = 'SETTLEMENT') as transacciones,
  sum(ticket_count) filter (where transaction_type = 'SETTLEMENT') as tickets,
  sum(costo_ticket) filter (where transaction_type = 'SETTLEMENT') as revenue_tickets,
  sum(costo_sc) filter (where transaction_type = 'SETTLEMENT') as revenue_sc,
  sum(total_transaccion) filter (where transaction_type = 'SETTLEMENT') as revenue_total
FROM unified_transactions
GROUP BY 1
ORDER BY 1;

CREATE OR REPLACE VIEW v_unified_daily AS
SELECT
  transaction_datetime::date as fecha,
  count(*) filter (where transaction_type = 'SETTLEMENT') as transacciones,
  sum(ticket_count) filter (where transaction_type = 'SETTLEMENT') as tickets,
  sum(total_transaccion) filter (where transaction_type = 'SETTLEMENT') as monto_dia,
  sum(sum(total_transaccion) filter (where transaction_type = 'SETTLEMENT'))
    OVER (ORDER BY transaction_datetime::date) as acumulado
FROM unified_transactions
GROUP BY 1
ORDER BY 1;

-- 3. Nuevas vistas de BALANCE (todos los tipos)
CREATE OR REPLACE VIEW v_balance_daily AS
SELECT
  transaction_datetime::date as fecha,
  count(*) as movimientos,
  sum(total_transaccion) filter (where transaction_type = 'SETTLEMENT') as ingresos,
  sum(total_transaccion) filter (where transaction_type = 'PAYOUTS') as payouts,
  sum(total_transaccion) filter (where transaction_type = 'REFUND') as refunds,
  sum(total_transaccion) filter (where transaction_type in ('CHARGEBACK','CHARGEBACK_CANCEL')) as chargebacks,
  sum(total_transaccion) as neto_dia,
  sum(sum(total_transaccion)) over (order by transaction_datetime::date) as balance
FROM unified_transactions
GROUP BY 1
ORDER BY 1;

CREATE OR REPLACE VIEW v_balance_monthly AS
SELECT
  date_trunc('month', transaction_datetime)::date as mes,
  count(*) as movimientos,
  sum(total_transaccion) filter (where transaction_type = 'SETTLEMENT') as ingresos,
  sum(total_transaccion) filter (where transaction_type = 'PAYOUTS') as payouts,
  sum(total_transaccion) filter (where transaction_type = 'REFUND') as refunds,
  sum(total_transaccion) filter (where transaction_type in ('CHARGEBACK','CHARGEBACK_CANCEL')) as chargebacks,
  sum(total_transaccion) as neto_mes,
  sum(sum(total_transaccion)) over (order by date_trunc('month', transaction_datetime)::date) as balance
FROM unified_transactions
GROUP BY 1
ORDER BY 1;
