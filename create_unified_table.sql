-- =====================================================
-- Tabla unificada: MP CSVs + Order Tickets
-- Ejecutar en Supabase Dashboard > SQL Editor
-- =====================================================

-- 1. Crear la tabla
CREATE TABLE IF NOT EXISTS unified_transactions (
  id bigint generated always as identity primary key,
  reference_id text,
  productor text not null,
  evento text not null,
  transaction_datetime timestamptz not null,
  ticket_count int not null default 1,
  costo_ticket numeric not null,
  costo_sc numeric not null,
  total_transaccion numeric not null,
  payment_method text,
  has_mp_data boolean not null default false,
  created_at timestamptz default now()
);

-- 2. Indices para performance
CREATE INDEX IF NOT EXISTS idx_unified_productor ON unified_transactions(productor);
CREATE INDEX IF NOT EXISTS idx_unified_evento ON unified_transactions(evento);
CREATE INDEX IF NOT EXISTS idx_unified_datetime ON unified_transactions(transaction_datetime);
CREATE INDEX IF NOT EXISTS idx_unified_reference ON unified_transactions(reference_id);

-- 3. Habilitar RLS y permitir lectura publica (anon)
ALTER TABLE unified_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read" ON unified_transactions
  FOR SELECT USING (true);

CREATE POLICY "Allow public insert" ON unified_transactions
  FOR INSERT WITH CHECK (true);

-- 4. Vistas para el dashboard

-- Vista: resumen por productor
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
GROUP BY productor
ORDER BY total_neto DESC;

-- Vista: resumen por evento
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
GROUP BY productor, evento
ORDER BY total_neto DESC;

-- Vista: tendencia mensual unificada
CREATE OR REPLACE VIEW v_unified_monthly AS
SELECT
  date_trunc('month', transaction_datetime)::date as mes,
  count(*) as transacciones,
  sum(ticket_count) as tickets,
  sum(costo_ticket) as revenue_tickets,
  sum(costo_sc) as revenue_sc,
  sum(total_transaccion) as revenue_total
FROM unified_transactions
GROUP BY 1
ORDER BY 1;

-- Vista: flujo de caja diario unificado
CREATE OR REPLACE VIEW v_unified_daily AS
SELECT
  transaction_datetime::date as fecha,
  count(*) as transacciones,
  sum(ticket_count) as tickets,
  sum(total_transaccion) as monto_dia,
  sum(sum(total_transaccion)) OVER (ORDER BY transaction_datetime::date) as acumulado
FROM unified_transactions
GROUP BY 1
ORDER BY 1;
