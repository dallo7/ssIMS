-- Smart-Shop Stock Inventory (CapitalPay) — PostgreSQL schema
-- Generated from SQLAlchemy models in `database/models.py`
--
-- Apply:
--   psql "$CPI_DATABASE_URL" -f database/schema_postgres.sql
--
-- Notes:
-- - The app currently stores enums as strings; we keep VARCHAR + CHECK constraints for compatibility.
-- - This is PostgreSQL-only.

BEGIN;

-- =========================
-- Core auth / sessions
-- =========================

CREATE TABLE IF NOT EXISTS roles (
  id            SERIAL PRIMARY KEY,
  name          VARCHAR(64)  NOT NULL UNIQUE,
  description   TEXT,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
  id                 SERIAL PRIMARY KEY,
  username           VARCHAR(128) NOT NULL UNIQUE,
  password_hash      VARCHAR(256) NOT NULL,
  full_name          VARCHAR(256) NOT NULL,
  role_id            INTEGER      NOT NULL REFERENCES roles(id),
  is_active          BOOLEAN      NOT NULL DEFAULT TRUE,
  approval_pin_hash  VARCHAR(256),
  created_at         TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_users_role_id ON users(role_id);

CREATE TABLE IF NOT EXISTS sessions (
  id             SERIAL PRIMARY KEY,
  session_token  VARCHAR(128) NOT NULL UNIQUE,
  user_id        INTEGER      NOT NULL REFERENCES users(id),
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions(user_id);

-- =========================
-- Reference data
-- =========================

CREATE TABLE IF NOT EXISTS categories (
  id          SERIAL PRIMARY KEY,
  name        VARCHAR(128) NOT NULL UNIQUE,
  abc_class   VARCHAR(1)   NOT NULL DEFAULT 'B' CHECK (abc_class IN ('A','B','C')),
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS units_of_measure (
  id          SERIAL PRIMARY KEY,
  code        VARCHAR(32)  NOT NULL UNIQUE,
  label       VARCHAR(128) NOT NULL,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS storage_locations (
  id          SERIAL PRIMARY KEY,
  name        VARCHAR(128) NOT NULL,
  zone        VARCHAR(64),
  warehouse   VARCHAR(128) NOT NULL DEFAULT 'Main',
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_storage_locations_wh ON storage_locations(warehouse);

CREATE TABLE IF NOT EXISTS suppliers (
  id             SERIAL PRIMARY KEY,
  name           VARCHAR(256) NOT NULL,
  contact_person VARCHAR(256),
  phone          VARCHAR(64),
  email          VARCHAR(256),
  address        TEXT,
  country        VARCHAR(128) NOT NULL DEFAULT 'South Sudan',
  payment_terms  VARCHAR(128),
  lead_time_days INTEGER      NOT NULL DEFAULT 7,
  rating         DOUBLE PRECISION NOT NULL DEFAULT 3.0,
  is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_suppliers_active ON suppliers(is_active);

-- =========================
-- Inventory
-- =========================

CREATE TABLE IF NOT EXISTS inventory_items (
  id                  SERIAL PRIMARY KEY,
  item_id              VARCHAR(64)  NOT NULL UNIQUE,
  name                 VARCHAR(256) NOT NULL,
  description          TEXT,
  category_id          INTEGER      NOT NULL REFERENCES categories(id),
  unit_of_measure_id   INTEGER      NOT NULL REFERENCES units_of_measure(id),
  quantity_in_stock    DOUBLE PRECISION NOT NULL DEFAULT 0,
  reorder_point        DOUBLE PRECISION NOT NULL DEFAULT 0,
  reorder_quantity     DOUBLE PRECISION NOT NULL DEFAULT 0,
  unit_cost            DOUBLE PRECISION NOT NULL DEFAULT 0,
  unit_price           DOUBLE PRECISION NOT NULL DEFAULT 0,
  storage_location_id  INTEGER      REFERENCES storage_locations(id),
  supplier_id          INTEGER      REFERENCES suppliers(id),
  expiry_date          DATE,
  barcode              VARCHAR(128),
  sku                  VARCHAR(128),
  fifo_batch_id         INTEGER, -- pointer only; intentionally no FK to avoid batch<->item cycle
  last_updated         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_by           INTEGER     REFERENCES users(id),
  is_active            BOOLEAN     NOT NULL DEFAULT TRUE,
  last_audit_date      DATE
);

CREATE INDEX IF NOT EXISTS ix_inventory_items_category_id ON inventory_items(category_id);
CREATE INDEX IF NOT EXISTS ix_inventory_items_uom_id ON inventory_items(unit_of_measure_id);
CREATE INDEX IF NOT EXISTS ix_inventory_items_location_id ON inventory_items(storage_location_id);
CREATE INDEX IF NOT EXISTS ix_inventory_items_supplier_id ON inventory_items(supplier_id);
CREATE INDEX IF NOT EXISTS ix_inventory_items_active ON inventory_items(is_active);

CREATE TABLE IF NOT EXISTS purchase_orders (
  id            SERIAL PRIMARY KEY,
  po_id         VARCHAR(64) NOT NULL UNIQUE,
  supplier_id   INTEGER     NOT NULL REFERENCES suppliers(id),
  status        VARCHAR(32) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','SUBMITTED','APPROVED','RECEIVED','CLOSED')),
  expected_date DATE,
  received_date DATE,
  created_by    INTEGER     NOT NULL REFERENCES users(id),
  approved_by   INTEGER     REFERENCES users(id),
  notes         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_purchase_orders_supplier_id ON purchase_orders(supplier_id);
CREATE INDEX IF NOT EXISTS ix_purchase_orders_status ON purchase_orders(status);

CREATE TABLE IF NOT EXISTS po_lines (
  id              SERIAL PRIMARY KEY,
  po_id           INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
  item_id         INTEGER NOT NULL REFERENCES inventory_items(id),
  qty_ordered     DOUBLE PRECISION NOT NULL,
  qty_received    DOUBLE PRECISION NOT NULL DEFAULT 0,
  unit_cost       DOUBLE PRECISION NOT NULL,
  discrepancy_note TEXT
);

CREATE INDEX IF NOT EXISTS ix_po_lines_po_id ON po_lines(po_id);
CREATE INDEX IF NOT EXISTS ix_po_lines_item_id ON po_lines(item_id);

CREATE TABLE IF NOT EXISTS inventory_batches (
  id                 SERIAL PRIMARY KEY,
  item_id            INTEGER NOT NULL REFERENCES inventory_items(id),
  quantity_original  DOUBLE PRECISION NOT NULL,
  quantity_remaining DOUBLE PRECISION NOT NULL,
  unit_cost          DOUBLE PRECISION NOT NULL,
  received_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  po_line_id         INTEGER REFERENCES po_lines(id),
  batch_ref          VARCHAR(64) NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_inventory_batches_item_id ON inventory_batches(item_id);
CREATE INDEX IF NOT EXISTS ix_inventory_batches_po_line_id ON inventory_batches(po_line_id);
CREATE INDEX IF NOT EXISTS ix_inventory_batches_received_at ON inventory_batches(received_at);

CREATE TABLE IF NOT EXISTS customers (
  id            SERIAL PRIMARY KEY,
  customer_code VARCHAR(64)  NOT NULL UNIQUE,
  name          VARCHAR(256) NOT NULL,
  phone         VARCHAR(64),
  email         VARCHAR(256),
  address       TEXT,
  country       VARCHAR(128) NOT NULL DEFAULT 'South Sudan',
  is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_customers_active ON customers(is_active);

CREATE TABLE IF NOT EXISTS sales_orders (
  id          SERIAL PRIMARY KEY,
  so_number   VARCHAR(64) NOT NULL UNIQUE,
  customer_id INTEGER     NOT NULL REFERENCES customers(id),
  status      VARCHAR(32) NOT NULL DEFAULT 'DRAFT'
              CHECK (status IN ('DRAFT','CONFIRMED','PICKING','SHIPPED','CANCELLED')),
  notes       TEXT,
  order_date  DATE        NOT NULL DEFAULT CURRENT_DATE,
  created_by  INTEGER     NOT NULL REFERENCES users(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_sales_orders_customer_id ON sales_orders(customer_id);
CREATE INDEX IF NOT EXISTS ix_sales_orders_status ON sales_orders(status);

CREATE TABLE IF NOT EXISTS sales_order_lines (
  id               SERIAL PRIMARY KEY,
  sales_order_id   INTEGER NOT NULL REFERENCES sales_orders(id) ON DELETE CASCADE,
  item_id          INTEGER NOT NULL REFERENCES inventory_items(id),
  quantity_ordered DOUBLE PRECISION NOT NULL,
  quantity_shipped DOUBLE PRECISION NOT NULL DEFAULT 0,
  unit_price       DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_sales_order_lines_so_id ON sales_order_lines(sales_order_id);
CREATE INDEX IF NOT EXISTS ix_sales_order_lines_item_id ON sales_order_lines(item_id);

CREATE TABLE IF NOT EXISTS stock_transactions (
  id                  SERIAL PRIMARY KEY,
  transaction_id      VARCHAR(64) NOT NULL UNIQUE,
  item_id             INTEGER NOT NULL REFERENCES inventory_items(id),
  type                VARCHAR(32) NOT NULL
                      CHECK (type IN ('RECEIVE','ISSUE','RETURN','ADJUSTMENT','WRITE-OFF','TRANSFER')),
  quantity            DOUBLE PRECISION NOT NULL,
  reference_number    VARCHAR(128),
  notes               TEXT,
  performed_by        INTEGER NOT NULL REFERENCES users(id),
  approved_by         INTEGER REFERENCES users(id),
  timestamp           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  batch_id            INTEGER REFERENCES inventory_batches(id),
  sales_order_line_id INTEGER REFERENCES sales_order_lines(id),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_stock_txn_item_id ON stock_transactions(item_id);
CREATE INDEX IF NOT EXISTS ix_stock_txn_timestamp ON stock_transactions(timestamp);
CREATE INDEX IF NOT EXISTS ix_stock_txn_performed_by ON stock_transactions(performed_by);
CREATE INDEX IF NOT EXISTS ix_stock_txn_approved_by ON stock_transactions(approved_by);
CREATE INDEX IF NOT EXISTS ix_stock_txn_batch_id ON stock_transactions(batch_id);
CREATE INDEX IF NOT EXISTS ix_stock_txn_so_line_id ON stock_transactions(sales_order_line_id);

CREATE TABLE IF NOT EXISTS item_location_stock (
  id                  SERIAL PRIMARY KEY,
  item_id             INTEGER NOT NULL REFERENCES inventory_items(id),
  storage_location_id INTEGER NOT NULL REFERENCES storage_locations(id),
  quantity            DOUBLE PRECISION NOT NULL DEFAULT 0,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_item_location_stock UNIQUE (item_id, storage_location_id)
);

CREATE INDEX IF NOT EXISTS ix_item_location_stock_item_id ON item_location_stock(item_id);
CREATE INDEX IF NOT EXISTS ix_item_location_stock_location_id ON item_location_stock(storage_location_id);

CREATE TABLE IF NOT EXISTS bom_lines (
  id                SERIAL PRIMARY KEY,
  parent_item_id    INTEGER NOT NULL REFERENCES inventory_items(id),
  component_item_id INTEGER NOT NULL REFERENCES inventory_items(id),
  quantity_per      DOUBLE PRECISION NOT NULL,
  CONSTRAINT uq_bom_parent_component UNIQUE (parent_item_id, component_item_id)
);

CREATE INDEX IF NOT EXISTS ix_bom_parent ON bom_lines(parent_item_id);
CREATE INDEX IF NOT EXISTS ix_bom_component ON bom_lines(component_item_id);

-- =========================
-- Auditing
-- =========================

CREATE TABLE IF NOT EXISTS audit_sessions (
  id            SERIAL PRIMARY KEY,
  audit_ref     VARCHAR(64)  NOT NULL UNIQUE,
  title         VARCHAR(256) NOT NULL,
  audit_type    VARCHAR(32)  NOT NULL DEFAULT 'CYCLE',
  category_id   INTEGER      REFERENCES categories(id),
  location_id   INTEGER      REFERENCES storage_locations(id),
  status        VARCHAR(32)  NOT NULL DEFAULT 'SCHEDULED'
                CHECK (status IN ('SCHEDULED','IN_PROGRESS','PENDING_REVIEW','APPROVED','REJECTED')),
  scheduled_for DATE,
  created_by    INTEGER      NOT NULL REFERENCES users(id),
  reviewed_by   INTEGER      REFERENCES users(id),
  reviewed_at   TIMESTAMPTZ,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_audit_sessions_status ON audit_sessions(status);
CREATE INDEX IF NOT EXISTS ix_audit_sessions_category_id ON audit_sessions(category_id);
CREATE INDEX IF NOT EXISTS ix_audit_sessions_location_id ON audit_sessions(location_id);

CREATE TABLE IF NOT EXISTS audit_lines (
  id               SERIAL PRIMARY KEY,
  audit_session_id INTEGER NOT NULL REFERENCES audit_sessions(id) ON DELETE CASCADE,
  item_id          INTEGER NOT NULL REFERENCES inventory_items(id),
  expected_qty     DOUBLE PRECISION NOT NULL,
  counted_qty      DOUBLE PRECISION,
  variance         DOUBLE PRECISION,
  notes            TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_audit_lines_session ON audit_lines(audit_session_id);
CREATE INDEX IF NOT EXISTS ix_audit_lines_item ON audit_lines(item_id);

-- =========================
-- Alerts / activity / approvals queue
-- =========================

CREATE TABLE IF NOT EXISTS alert_rules (
  id             SERIAL PRIMARY KEY,
  rule_key       VARCHAR(64)  NOT NULL UNIQUE,
  name           VARCHAR(128) NOT NULL,
  enabled        BOOLEAN      NOT NULL DEFAULT TRUE,
  threshold_days INTEGER,
  severity       VARCHAR(16)  NOT NULL DEFAULT 'WARNING'
                CHECK (severity IN ('CRITICAL','WARNING','INFO')),
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_alert_rules_enabled ON alert_rules(enabled);

CREATE TABLE IF NOT EXISTS alert_log (
  id         SERIAL PRIMARY KEY,
  rule_id    INTEGER REFERENCES alert_rules(id),
  item_id    INTEGER REFERENCES inventory_items(id),
  message    TEXT NOT NULL,
  severity   VARCHAR(16) NOT NULL CHECK (severity IN ('CRITICAL','WARNING','INFO')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_alert_log_created_at ON alert_log(created_at);
CREATE INDEX IF NOT EXISTS ix_alert_log_rule_id ON alert_log(rule_id);
CREATE INDEX IF NOT EXISTS ix_alert_log_item_id ON alert_log(item_id);

CREATE TABLE IF NOT EXISTS alert_acknowledgments (
  id           SERIAL PRIMARY KEY,
  alert_log_id INTEGER NOT NULL REFERENCES alert_log(id) ON DELETE CASCADE,
  user_id      INTEGER NOT NULL REFERENCES users(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_alert_ack_alert_log_id ON alert_acknowledgments(alert_log_id);
CREATE INDEX IF NOT EXISTS ix_alert_ack_user_id ON alert_acknowledgments(user_id);

CREATE TABLE IF NOT EXISTS activity_log (
  id          SERIAL PRIMARY KEY,
  user_id     INTEGER REFERENCES users(id),
  action      VARCHAR(64) NOT NULL,
  entity_type VARCHAR(64),
  entity_id   VARCHAR(128),
  details     TEXT,
  ip_address  VARCHAR(64),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_activity_log_created_at ON activity_log(created_at);
CREATE INDEX IF NOT EXISTS ix_activity_log_user_id ON activity_log(user_id);
CREATE INDEX IF NOT EXISTS ix_activity_log_action ON activity_log(action);

CREATE TABLE IF NOT EXISTS inventory_change_requests (
  id           SERIAL PRIMARY KEY,
  action       VARCHAR(32) NOT NULL CHECK (action IN ('CREATE','UPDATE','SOFT_DELETE')),
  payload_json TEXT NOT NULL,
  item_id      INTEGER REFERENCES inventory_items(id),
  submitted_by INTEGER NOT NULL REFERENCES users(id),
  status       VARCHAR(24) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED')),
  reviewed_by  INTEGER REFERENCES users(id),
  reviewed_at  TIMESTAMPTZ,
  reviewer_note TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_change_req_status ON inventory_change_requests(status);
CREATE INDEX IF NOT EXISTS ix_change_req_item_id ON inventory_change_requests(item_id);
CREATE INDEX IF NOT EXISTS ix_change_req_submitted_by ON inventory_change_requests(submitted_by);

CREATE TABLE IF NOT EXISTS system_config (
  id         SERIAL PRIMARY KEY,
  key        VARCHAR(128) NOT NULL UNIQUE,
  value      TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS api_tokens (
  id          SERIAL PRIMARY KEY,
  label       VARCHAR(128) NOT NULL,
  token_hash  VARCHAR(256) NOT NULL,
  created_by  INTEGER NOT NULL REFERENCES users(id),
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_api_tokens_created_by ON api_tokens(created_by);
CREATE INDEX IF NOT EXISTS ix_api_tokens_active ON api_tokens(is_active);

COMMIT;

