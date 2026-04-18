import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RoleName(str, enum.Enum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    STOCK_CLERK = "STOCK_CLERK"
    VIEWER = "VIEWER"


class TransactionType(str, enum.Enum):
    RECEIVE = "RECEIVE"
    ISSUE = "ISSUE"
    RETURN = "RETURN"
    ADJUSTMENT = "ADJUSTMENT"
    WRITE_OFF = "WRITE-OFF"
    TRANSFER = "TRANSFER"


class POStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    RECEIVED = "RECEIVED"
    CLOSED = "CLOSED"


class SalesOrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    PICKING = "PICKING"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"


class AuditStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AlertSeverity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )
    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    full_name: Mapped[str] = mapped_column(String(256), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # bcrypt hash for manager/admin inventory approval (PIN or short passphrase)
    approval_pin_hash: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )
    role: Mapped["Role"] = relationship(back_populates="users")


class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    abc_class: Mapped[str] = mapped_column(String(1), default="B", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class UnitOfMeasure(Base):
    __tablename__ = "units_of_measure"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class StorageLocation(Base):
    __tablename__ = "storage_locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    zone: Mapped[Optional[str]] = mapped_column(String(64))
    warehouse: Mapped[str] = mapped_column(String(128), default="Main", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    contact_person: Mapped[Optional[str]] = mapped_column(String(256))
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    email: Mapped[Optional[str]] = mapped_column(String(256))
    address: Mapped[Optional[str]] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(128), default="South Sudan", nullable=False)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(128))
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    rating: Mapped[float] = mapped_column(Float, default=3.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    unit_of_measure_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"), nullable=False)
    quantity_in_stock: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    reorder_point: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    reorder_quantity: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    storage_location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("storage_locations.id"))
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id"))
    expiry_date: Mapped[Optional[date]] = mapped_column(Date)
    barcode: Mapped[Optional[str]] = mapped_column(String(128))
    sku: Mapped[Optional[str]] = mapped_column(String(128))
    fifo_batch_id: Mapped[Optional[int]] = mapped_column(Integer)  # points to batch; no FK (avoids item↔batch cycle)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_audit_date: Mapped[Optional[date]] = mapped_column(Date)

    category: Mapped["Category"] = relationship()
    unit: Mapped["UnitOfMeasure"] = relationship()
    location: Mapped[Optional["StorageLocation"]] = relationship()


class InventoryBatch(Base):
    __tablename__ = "inventory_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    quantity_original: Mapped[float] = mapped_column(Float, nullable=False)
    quantity_remaining: Mapped[float] = mapped_column(Float, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    po_line_id: Mapped[Optional[int]] = mapped_column(ForeignKey("po_lines.id"))
    batch_ref: Mapped[str] = mapped_column(String(64), default=lambda: str(uuid.uuid4())[:12], nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class StockTransaction(Base):
    __tablename__ = "stock_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(128))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    performed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("inventory_batches.id"))
    sales_order_line_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sales_order_lines.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=POStatus.DRAFT.value, nullable=False)
    expected_date: Mapped[Optional[date]] = mapped_column(Date)
    received_date: Mapped[Optional[date]] = mapped_column(Date)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )
    lines: Mapped[list["POLine"]] = relationship(back_populates="purchase_order", cascade="all, delete-orphan")


class POLine(Base):
    __tablename__ = "po_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    qty_ordered: Mapped[float] = mapped_column(Float, nullable=False)
    qty_received: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    discrepancy_note: Mapped[Optional[str]] = mapped_column(Text)
    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="lines")


class AuditSession(Base):
    __tablename__ = "audit_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_ref: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    audit_type: Mapped[str] = mapped_column(String(32), default="CYCLE", nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("storage_locations.id"))
    status: Mapped[str] = mapped_column(String(32), default=AuditStatus.SCHEDULED.value, nullable=False)
    scheduled_for: Mapped[Optional[date]] = mapped_column(Date)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )
    lines: Mapped[list["AuditLine"]] = relationship(back_populates="audit_session", cascade="all, delete-orphan")


class AuditLine(Base):
    __tablename__ = "audit_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_session_id: Mapped[int] = mapped_column(ForeignKey("audit_sessions.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    expected_qty: Mapped[float] = mapped_column(Float, nullable=False)
    counted_qty: Mapped[Optional[float]] = mapped_column(Float)
    variance: Mapped[Optional[float]] = mapped_column(Float)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )
    audit_session: Mapped["AuditSession"] = relationship(back_populates="lines")


class AlertRule(Base):
    __tablename__ = "alert_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    threshold_days: Mapped[Optional[int]] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(16), default=AlertSeverity.WARNING.value, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class AlertLog(Base):
    __tablename__ = "alert_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("alert_rules.id"))
    item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("inventory_items.id"))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class AlertAcknowledgment(Base):
    """Append-only acknowledgment; alert_log rows are never updated."""
    __tablename__ = "alert_acknowledgments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_log_id: Mapped[int] = mapped_column(ForeignKey("alert_log.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class ActivityLog(Base):
    __tablename__ = "activity_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64))
    entity_id: Mapped[Optional[str]] = mapped_column(String(128))
    details: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class InventoryChangeRequest(Base):
    """Clerk-submitted inventory mutations awaiting manager/admin approval (PIN)."""

    __tablename__ = "inventory_change_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # CREATE, UPDATE, SOFT_DELETE
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("inventory_items.id"), nullable=True)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="PENDING", nullable=False)
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewer_note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class SystemConfig(Base):
    __tablename__ = "system_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    email: Mapped[Optional[str]] = mapped_column(String(256))
    address: Mapped[Optional[str]] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(128), default="South Sudan", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )
    sales_orders: Mapped[list["SalesOrder"]] = relationship(back_populates="customer")


class SalesOrder(Base):
    __tablename__ = "sales_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    so_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=SalesOrderStatus.DRAFT.value, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    order_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )
    customer: Mapped["Customer"] = relationship(back_populates="sales_orders")
    lines: Mapped[list["SalesOrderLine"]] = relationship(
        back_populates="sales_order", cascade="all, delete-orphan"
    )


class SalesOrderLine(Base):
    __tablename__ = "sales_order_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    quantity_ordered: Mapped[float] = mapped_column(Float, nullable=False)
    quantity_shipped: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    sales_order: Mapped["SalesOrder"] = relationship(back_populates="lines")


class ItemLocationStock(Base):
    """Per-bin quantity; sum per item should match inventory_items.quantity_in_stock."""

    __tablename__ = "item_location_stock"
    __table_args__ = (UniqueConstraint("item_id", "storage_location_id", name="uq_item_location_stock"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    storage_location_id: Mapped[int] = mapped_column(ForeignKey("storage_locations.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )


class BomLine(Base):
    """Quantity of *component* required to build one unit of *parent* kit SKU."""

    __tablename__ = "bom_lines"
    __table_args__ = (UniqueConstraint("parent_item_id", "component_item_id", name="uq_bom_parent_component"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    component_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    quantity_per: Mapped[float] = mapped_column(Float, nullable=False)


class ApiToken(Base):
    __tablename__ = "api_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP"
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# Note: `fifo_batch_id` is an application-level pointer (no FK) to avoid a batch<->item circular dependency.
