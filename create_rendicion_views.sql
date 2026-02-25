-- =====================================================
-- Rendicion de Transferencias: schema + vistas
-- Ejecutar en: Supabase Dashboard > SQL Editor
-- =====================================================

-- ── 1. Nuevas columnas en unified_transactions ──────
-- Todas nullable: los registros existentes (SETTLEMENT, PAYOUTS, etc.)
-- no tienen estos datos y quedan en NULL sin problema.

ALTER TABLE unified_transactions
  ADD COLUMN IF NOT EXISTS cuenta_destino  text,
  ADD COLUMN IF NOT EXISTS cbu             text,
  ADD COLUMN IF NOT EXISTS cuit            text,
  ADD COLUMN IF NOT EXISTS fecha_evento    date,
  ADD COLUMN IF NOT EXISTS devoluciones    numeric,
  ADD COLUMN IF NOT EXISTS impuesto_dc     numeric,
  ADD COLUMN IF NOT EXISTS ingresos_loud   numeric,
  ADD COLUMN IF NOT EXISTS deuda_loud      numeric;

-- ── 2. Vistas de Rendicion ──────────────────────────

-- Vista 1: Resumen mensual
CREATE OR REPLACE VIEW v_rendicion_monthly AS
SELECT
  date_trunc('month', transaction_datetime)::date AS mes,
  count(*)                                         AS transferencias,
  sum(abs(total_transaccion))                      AS total_transferido,
  sum(abs(costo_ticket))                           AS total_abonado,
  sum(abs(costo_sc))                               AS total_liquidado,
  sum(abs(devoluciones))                           AS total_devoluciones,
  sum(abs(impuesto_dc))                            AS total_impuesto_dc
FROM unified_transactions
WHERE transaction_type = 'RENDICION'
GROUP BY 1
ORDER BY 1;

-- Vista 2: Resumen por beneficiario
CREATE OR REPLACE VIEW v_rendicion_by_beneficiario AS
SELECT
  productor                                        AS beneficiario,
  max(cbu)                                         AS cbu,
  max(cuit)                                        AS cuit,
  count(*)                                         AS num_transferencias,
  sum(abs(total_transaccion))                      AS total_transferido,
  round(avg(abs(total_transaccion)), 2)            AS avg_transferencia,
  count(DISTINCT evento)                           AS num_eventos,
  sum(abs(devoluciones))                           AS total_devoluciones
FROM unified_transactions
WHERE transaction_type = 'RENDICION'
GROUP BY productor
ORDER BY total_transferido DESC;

-- Vista 3: Detalle por evento
CREATE OR REPLACE VIEW v_rendicion_by_evento AS
SELECT
  evento,
  productor                                        AS beneficiario,
  max(cuenta_destino)                              AS cuenta_destino,
  max(fecha_evento)                                AS fecha_evento,
  count(*)                                         AS num_transferencias,
  sum(abs(total_transaccion))                      AS total_transferido,
  sum(abs(costo_ticket))                           AS total_abonado,
  sum(abs(costo_sc))                               AS total_liquidado,
  sum(abs(devoluciones))                           AS total_devoluciones,
  sum(abs(impuesto_dc))                            AS total_impuesto_dc,
  sum(abs(ingresos_loud))                          AS total_ingresos_loud,
  min(transaction_datetime)                        AS primera_transferencia,
  max(transaction_datetime)                        AS ultima_transferencia
FROM unified_transactions
WHERE transaction_type = 'RENDICION'
GROUP BY evento, productor
ORDER BY total_transferido DESC;

-- ── 3. Actualizar vistas de balance ─────────────────
-- Agrega columna "rendiciones" (los montos RENDICION son negativos,
-- por lo que el balance ya se reduce automaticamente).
-- DROP necesario porque CREATE OR REPLACE no puede insertar columnas en el medio.

DROP VIEW IF EXISTS v_balance_monthly CASCADE;
CREATE VIEW v_balance_monthly AS
SELECT
  date_trunc('month', transaction_datetime)::date AS mes,
  count(*) AS movimientos,
  sum(total_transaccion) FILTER (WHERE transaction_type = 'SETTLEMENT')                       AS ingresos,
  sum(total_transaccion) FILTER (WHERE transaction_type = 'PAYOUTS')                          AS payouts,
  sum(total_transaccion) FILTER (WHERE transaction_type = 'REFUND')                           AS refunds,
  sum(total_transaccion) FILTER (WHERE transaction_type IN ('CHARGEBACK','CHARGEBACK_CANCEL')) AS chargebacks,
  sum(total_transaccion) FILTER (WHERE transaction_type = 'RENDICION')                        AS rendiciones,
  sum(total_transaccion) AS neto_mes,
  sum(sum(total_transaccion))
    OVER (ORDER BY date_trunc('month', transaction_datetime)::date) AS balance
FROM unified_transactions
GROUP BY 1
ORDER BY 1;

DROP VIEW IF EXISTS v_balance_daily CASCADE;
CREATE VIEW v_balance_daily AS
SELECT
  transaction_datetime::date AS fecha,
  count(*) AS movimientos,
  sum(total_transaccion) FILTER (WHERE transaction_type = 'SETTLEMENT')                       AS ingresos,
  sum(total_transaccion) FILTER (WHERE transaction_type = 'PAYOUTS')                          AS payouts,
  sum(total_transaccion) FILTER (WHERE transaction_type = 'REFUND')                           AS refunds,
  sum(total_transaccion) FILTER (WHERE transaction_type IN ('CHARGEBACK','CHARGEBACK_CANCEL')) AS chargebacks,
  sum(total_transaccion) FILTER (WHERE transaction_type = 'RENDICION')                        AS rendiciones,
  sum(total_transaccion) AS neto_dia,
  sum(sum(total_transaccion))
    OVER (ORDER BY transaction_datetime::date) AS balance
FROM unified_transactions
GROUP BY 1
ORDER BY 1;
