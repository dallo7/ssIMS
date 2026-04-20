"""
Data access layer. stock_transactions, activity_log, alert_log: INSERT + SELECT only (no UPDATE/DELETE).
Acknowledgments use alert_acknowledgments (append-only).
"""
from __future__ import annotations

import json
import math
import secrets
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from database import models
from utils.auth import hash_password, verify_password
from utils.fifo import consume_fifo


class ImmutableMutationError(RuntimeError):
    pass


def sanitize_float(value: Any, default: float = 0.0) -> float:
    """Coerce to float; NaN/inf/invalid become *default* (Mantine NumberInput often sends NaN for empty)."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(x) or math.isinf(x):
        return default
    return x


# --- Immutable writers ---


def insert_stock_transaction(
    session: Session,
    *,
    item_id: int,
    txn_type: str,
    quantity: float,
    performed_by: int,
    reference_number: str | None = None,
    notes: str | None = None,
    approved_by: int | None = None,
    batch_id: int | None = None,
    sales_order_line_id: int | None = None,
) -> models.StockTransaction:
    row = models.StockTransaction(
        transaction_id=str(uuid.uuid4()),
        item_id=item_id,
        type=txn_type,
        quantity=quantity,
        reference_number=reference_number,
        notes=notes,
        performed_by=performed_by,
        approved_by=approved_by,
        timestamp=datetime.utcnow(),
        batch_id=batch_id,
        sales_order_line_id=sales_order_line_id,
    )
    session.add(row)
    session.flush()
    return row


def insert_activity_log(
    session: Session,
    *,
    user_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: str | None = None,
    ip_address: str | None = None,
) -> models.ActivityLog:
    row = models.ActivityLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
    )
    session.add(row)
    session.flush()
    return row


def insert_alert_log(
    session: Session,
    *,
    rule_id: int | None,
    item_id: int | None,
    message: str,
    severity: str,
) -> models.AlertLog:
    row = models.AlertLog(
        rule_id=rule_id,
        item_id=item_id,
        message=message,
        severity=severity,
    )
    session.add(row)
    session.flush()
    return row


def insert_alert_acknowledgment(session: Session, *, alert_log_id: int, user_id: int) -> models.AlertAcknowledgment:
    row = models.AlertAcknowledgment(alert_log_id=alert_log_id, user_id=user_id)
    session.add(row)
    session.flush()
    return row


def is_alert_acknowledged(session: Session, alert_log_id: int) -> bool:
    q = select(func.count()).select_from(models.AlertAcknowledgment).where(
        models.AlertAcknowledgment.alert_log_id == alert_log_id
    )
    return (session.scalar(q) or 0) > 0


# --- Transactions / activity reads ---


def list_transactions(
    session: Session,
    item_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Sequence[models.StockTransaction]:
    q = select(models.StockTransaction).order_by(models.StockTransaction.timestamp.desc())
    if item_id is not None:
        q = q.where(models.StockTransaction.item_id == item_id)
    if since is not None:
        q = q.where(models.StockTransaction.timestamp >= since)
    if until is not None:
        q = q.where(models.StockTransaction.timestamp <= until)
    return session.scalars(q).all()


def list_activity(session: Session, limit: int = 500) -> Sequence[models.ActivityLog]:
    q = select(models.ActivityLog).order_by(models.ActivityLog.created_at.desc()).limit(limit)
    return session.scalars(q).all()


def list_alerts_with_ack_state(session: Session, limit: int = 200) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(models.AlertLog).order_by(models.AlertLog.created_at.desc()).limit(limit)
    ).all()
    if not rows:
        return []
    ids = [r.id for r in rows]
    acked_ids = set(
        session.scalars(
            select(models.AlertAcknowledgment.alert_log_id).where(
                models.AlertAcknowledgment.alert_log_id.in_(ids)
            )
        ).all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "rule_id": r.rule_id,
                "item_id": r.item_id,
                "message": r.message,
                "severity": r.severity,
                "created_at": r.created_at,
                "acknowledged": r.id in acked_ids,
            }
        )
    return out


# --- Inventory ---


def get_item(session: Session, item_pk: int) -> models.InventoryItem | None:
    return session.get(models.InventoryItem, item_pk)


def list_items(
    session: Session,
    active_only: bool = True,
    search: str | None = None,
) -> Sequence[models.InventoryItem]:
    q = select(models.InventoryItem)
    if active_only:
        q = q.where(models.InventoryItem.is_active == True)  # noqa: E712
    if search:
        like = f"%{search.strip()}%"
        q = q.where(
            or_(
                models.InventoryItem.name.ilike(like),
                models.InventoryItem.item_id.ilike(like),
                models.InventoryItem.sku.ilike(like),
            )
        )
    q = q.order_by(models.InventoryItem.name)
    return session.scalars(q).all()


def soft_delete_item(session: Session, item_pk: int, user_id: int) -> bool:
    item = get_item(session, item_pk)
    if not item:
        return False
    item.is_active = False
    item.last_updated = datetime.utcnow()
    insert_activity_log(
        session,
        user_id=user_id,
        action="SOFT_DELETE",
        entity_type="inventory_item",
        entity_id=item.item_id,
    )
    return True


def create_item(
    session: Session,
    *,
    name: str,
    description: str | None,
    category_id: int,
    unit_of_measure_id: int,
    quantity_in_stock: float,
    reorder_point: float,
    reorder_quantity: float,
    unit_cost: float,
    unit_price: float,
    storage_location_id: int | None,
    supplier_id: int | None,
    expiry_date: date | None,
    barcode: str | None,
    sku: str | None,
    created_by: int,
) -> models.InventoryItem:
    item = models.InventoryItem(
        item_id=str(uuid.uuid4())[:12].upper(),
        name=name,
        description=description,
        category_id=category_id,
        unit_of_measure_id=unit_of_measure_id,
        quantity_in_stock=quantity_in_stock,
        reorder_point=reorder_point,
        reorder_quantity=reorder_quantity,
        unit_cost=unit_cost,
        unit_price=unit_price,
        storage_location_id=storage_location_id,
        supplier_id=supplier_id,
        expiry_date=expiry_date,
        barcode=barcode,
        sku=sku or None,
        created_by=created_by,
        last_updated=datetime.utcnow(),
    )
    session.add(item)
    session.flush()
    insert_activity_log(
        session,
        user_id=created_by,
        action="CREATE",
        entity_type="inventory_item",
        entity_id=item.item_id,
        details=name,
    )
    return item


def update_item(session: Session, item_pk: int, user_id: int, **fields) -> models.InventoryItem | None:
    item = get_item(session, item_pk)
    if not item:
        return None
    allowed = {
        "name",
        "description",
        "category_id",
        "unit_of_measure_id",
        "quantity_in_stock",
        "reorder_point",
        "reorder_quantity",
        "unit_cost",
        "unit_price",
        "storage_location_id",
        "supplier_id",
        "expiry_date",
        "barcode",
        "sku",
    }
    float_keys = {"quantity_in_stock", "reorder_point", "reorder_quantity", "unit_cost", "unit_price"}
    for k, v in fields.items():
        if k in allowed and v is not None:
            if k in float_keys:
                v = sanitize_float(v, 0.0)
            setattr(item, k, v)
    item.last_updated = datetime.utcnow()
    insert_activity_log(
        session,
        user_id=user_id,
        action="UPDATE",
        entity_type="inventory_item",
        entity_id=item.item_id,
    )
    return item


# --- Stock movements (transactions + quantities) ---


def _default_storage_location_id(session: Session, item: models.InventoryItem) -> int:
    if item.storage_location_id:
        return int(item.storage_location_id)
    loc = session.scalar(select(models.StorageLocation).order_by(models.StorageLocation.id).limit(1))
    if not loc:
        raise ValueError("No storage location defined — add one under Locations.")
    return int(loc.id)


def adjust_item_location_quantity(
    session: Session, *, item_id: int, storage_location_id: int, delta: float
) -> models.ItemLocationStock:
    row = session.scalar(
        select(models.ItemLocationStock).where(
            models.ItemLocationStock.item_id == item_id,
            models.ItemLocationStock.storage_location_id == storage_location_id,
        )
    )
    if not row:
        if delta < 0:
            raise ValueError("No bin stock row for this item at the selected location")
        row = models.ItemLocationStock(
            item_id=item_id, storage_location_id=storage_location_id, quantity=0.0
        )
        session.add(row)
        session.flush()
    row.quantity = float(row.quantity) + float(delta)
    if row.quantity < -1e-9:
        raise ValueError("Insufficient quantity at location")
    if abs(row.quantity) < 1e-9:
        row.quantity = 0.0
    return row


def receive_stock(
    session: Session,
    *,
    item_id: int,
    quantity: float,
    unit_cost: float,
    performed_by: int,
    reference_number: str | None = None,
    po_line_id: int | None = None,
    notes: str | None = None,
    approved_by: int | None = None,
    storage_location_id: int | None = None,
) -> tuple[models.InventoryBatch, models.StockTransaction]:
    item = get_item(session, item_id)
    if not item or not item.is_active:
        raise ValueError("Invalid item")
    loc_id = int(storage_location_id) if storage_location_id is not None else _default_storage_location_id(session, item)
    batch = models.InventoryBatch(
        item_id=item_id,
        quantity_original=quantity,
        quantity_remaining=quantity,
        unit_cost=unit_cost,
        received_at=datetime.utcnow(),
        po_line_id=po_line_id,
    )
    session.add(batch)
    session.flush()
    item.quantity_in_stock += quantity
    item.fifo_batch_id = batch.id
    item.last_updated = datetime.utcnow()
    adjust_item_location_quantity(session, item_id=item_id, storage_location_id=loc_id, delta=quantity)
    txn = insert_stock_transaction(
        session,
        item_id=item_id,
        txn_type=models.TransactionType.RECEIVE.value,
        quantity=quantity,
        performed_by=performed_by,
        reference_number=reference_number,
        notes=notes,
        approved_by=approved_by,
        batch_id=batch.id,
    )
    insert_activity_log(
        session,
        user_id=performed_by,
        action="RECEIVE_STOCK",
        entity_type="inventory_item",
        entity_id=item.item_id,
        details=f"qty={quantity}",
    )
    return batch, txn


def issue_stock_fifo(
    session: Session,
    *,
    item_id: int,
    quantity: float,
    performed_by: int,
    reference_number: str | None = None,
    notes: str | None = None,
    approved_by: int | None = None,
    storage_location_id: int | None = None,
    sales_order_line_id: int | None = None,
) -> list[models.StockTransaction]:
    item = get_item(session, item_id)
    if not item or not item.is_active:
        raise ValueError("Invalid item")
    loc_id = int(storage_location_id) if storage_location_id is not None else _default_storage_location_id(session, item)
    ils = session.scalar(
        select(models.ItemLocationStock).where(
            models.ItemLocationStock.item_id == item_id,
            models.ItemLocationStock.storage_location_id == loc_id,
        )
    )
    if not ils or float(ils.quantity) + 1e-9 < float(quantity):
        raise ValueError("Not enough stock at the selected location for this issue")
    allocations = consume_fifo(session, item_id, quantity)
    item.quantity_in_stock -= quantity
    item.last_updated = datetime.utcnow()
    adjust_item_location_quantity(session, item_id=item_id, storage_location_id=loc_id, delta=-quantity)
    txns: list[models.StockTransaction] = []
    for batch, take in allocations:
        txns.append(
            insert_stock_transaction(
                session,
                item_id=item_id,
                txn_type=models.TransactionType.ISSUE.value,
                quantity=take,
                performed_by=performed_by,
                reference_number=reference_number,
                notes=notes,
                approved_by=approved_by,
                batch_id=batch.id,
                sales_order_line_id=sales_order_line_id,
            )
        )
    insert_activity_log(
        session,
        user_id=performed_by,
        action="ISSUE_STOCK",
        entity_type="inventory_item",
        entity_id=item.item_id,
        details=f"qty={quantity}",
    )
    return txns


def adjustment_stock(
    session: Session,
    *,
    item_id: int,
    delta: float,
    performed_by: int,
    reference_number: str | None = None,
    notes: str | None = None,
    approved_by: int | None = None,
    storage_location_id: int | None = None,
) -> models.StockTransaction:
    item = get_item(session, item_id)
    if not item:
        raise ValueError("Invalid item")
    item.quantity_in_stock += delta
    item.last_updated = datetime.utcnow()
    loc_id: int | None = int(storage_location_id) if storage_location_id is not None else None
    if loc_id is not None:
        adjust_item_location_quantity(session, item_id=item_id, storage_location_id=loc_id, delta=delta)
    elif abs(delta) > 1e-9:
        loc_id = _default_storage_location_id(session, item)
        adjust_item_location_quantity(session, item_id=item_id, storage_location_id=loc_id, delta=delta)
    txn = insert_stock_transaction(
        session,
        item_id=item_id,
        txn_type=models.TransactionType.ADJUSTMENT.value,
        quantity=delta,
        performed_by=performed_by,
        reference_number=reference_number,
        notes=notes,
        approved_by=approved_by,
    )
    insert_activity_log(
        session,
        user_id=performed_by,
        action="ADJUSTMENT",
        entity_type="inventory_item",
        entity_id=item.item_id,
        details=f"delta={delta}",
    )
    return txn


# --- Suppliers ---


def list_suppliers(session: Session, active_only: bool = True) -> Sequence[models.Supplier]:
    q = select(models.Supplier).order_by(models.Supplier.name)
    if active_only:
        q = q.where(models.Supplier.is_active == True)  # noqa: E712
    return session.scalars(q).all()


def create_supplier(session: Session, user_id: int, **kwargs) -> models.Supplier:
    s = models.Supplier(**kwargs)
    session.add(s)
    session.flush()
    insert_activity_log(session, user_id=user_id, action="CREATE", entity_type="supplier", entity_id=str(s.id))
    return s


def update_supplier(session: Session, sid: int, user_id: int, **kwargs) -> models.Supplier | None:
    s = session.get(models.Supplier, sid)
    if not s:
        return None
    for k in ("name", "contact_person", "phone", "email", "address", "country", "payment_terms", "lead_time_days", "rating"):
        if k in kwargs and kwargs[k] is not None:
            setattr(s, k, kwargs[k])
    insert_activity_log(session, user_id=user_id, action="UPDATE", entity_type="supplier", entity_id=str(sid))
    return s


def soft_delete_supplier(session: Session, sid: int, user_id: int) -> bool:
    s = session.get(models.Supplier, sid)
    if not s:
        return False
    s.is_active = False
    insert_activity_log(session, user_id=user_id, action="SOFT_DELETE", entity_type="supplier", entity_id=str(sid))
    return True


# --- Purchase orders ---


def create_po(session: Session, supplier_id: int, created_by: int, expected_date: date | None, lines: list[dict]) -> models.PurchaseOrder:
    po = models.PurchaseOrder(
        po_id=f"PO-{uuid.uuid4().hex[:10].upper()}",
        supplier_id=supplier_id,
        status=models.POStatus.DRAFT.value,
        expected_date=expected_date,
        created_by=created_by,
    )
    session.add(po)
    session.flush()
    for ln in lines:
        pl = models.POLine(
            po_id=po.id,
            item_id=int(ln["item_id"]),
            qty_ordered=float(ln["qty_ordered"]),
            unit_cost=float(ln["unit_cost"]),
        )
        session.add(pl)
    session.flush()
    insert_activity_log(session, user_id=created_by, action="CREATE", entity_type="purchase_order", entity_id=po.po_id)
    return po


def list_pos(session: Session) -> Sequence[models.PurchaseOrder]:
    return session.scalars(select(models.PurchaseOrder).order_by(models.PurchaseOrder.created_at.desc())).all()


def submit_po(session: Session, po_pk: int, user_id: int) -> bool:
    po = session.get(models.PurchaseOrder, po_pk)
    if not po or po.status != models.POStatus.DRAFT.value:
        return False
    po.status = models.POStatus.SUBMITTED.value
    insert_activity_log(session, user_id=user_id, action="SUBMIT_PO", entity_type="purchase_order", entity_id=po.po_id)
    return True


def approve_po(session: Session, po_pk: int, user_id: int) -> bool:
    po = session.get(models.PurchaseOrder, po_pk)
    if not po or po.status != models.POStatus.SUBMITTED.value:
        return False
    po.status = models.POStatus.APPROVED.value
    po.approved_by = user_id
    insert_activity_log(session, user_id=user_id, action="APPROVE_PO", entity_type="purchase_order", entity_id=po.po_id)
    return True


def receive_po(
    session: Session,
    po_pk: int,
    user_id: int,
    receipts: list[dict],
) -> bool:
    """
    receipts: [{ "line_id": int, "qty_received": float }, ...]
    """
    po = session.get(models.PurchaseOrder, po_pk)
    if not po or po.status not in (models.POStatus.APPROVED.value, models.POStatus.RECEIVED.value):
        return False
    for r in receipts:
        line = session.get(models.POLine, int(r["line_id"]))
        if not line or line.po_id != po.id:
            continue
        qty = float(r["qty_received"])
        line.qty_received += qty
        if qty < line.qty_ordered - 1e-9:
            line.discrepancy_note = (line.discrepancy_note or "") + f"; recv {qty} vs ord {line.qty_ordered}"
        item = get_item(session, line.item_id)
        if item:
            receive_stock(
                session,
                item_id=line.item_id,
                quantity=qty,
                unit_cost=line.unit_cost,
                performed_by=user_id,
                reference_number=po.po_id,
                po_line_id=line.id,
                notes="PO receive",
                approved_by=po.approved_by,
            )
    po.status = models.POStatus.RECEIVED.value
    po.received_date = date.today()
    insert_activity_log(session, user_id=user_id, action="RECEIVE_PO", entity_type="purchase_order", entity_id=po.po_id)
    return True


def close_po(session: Session, po_pk: int, user_id: int) -> bool:
    po = session.get(models.PurchaseOrder, po_pk)
    if not po:
        return False
    po.status = models.POStatus.CLOSED.value
    insert_activity_log(session, user_id=user_id, action="CLOSE_PO", entity_type="purchase_order", entity_id=po.po_id)
    return True


# --- Audits ---


def create_audit_session(
    session: Session,
    *,
    title: str,
    audit_type: str,
    created_by: int,
    category_id: int | None,
    location_id: int | None,
    scheduled_for: date | None,
) -> models.AuditSession:
    au = models.AuditSession(
        audit_ref=f"AUD-{uuid.uuid4().hex[:10].upper()}",
        title=title,
        audit_type=audit_type,
        category_id=category_id,
        location_id=location_id,
        status=models.AuditStatus.SCHEDULED.value,
        scheduled_for=scheduled_for,
        created_by=created_by,
    )
    session.add(au)
    session.flush()
    insert_activity_log(session, user_id=created_by, action="CREATE", entity_type="audit", entity_id=au.audit_ref)
    return au


def generate_audit_sheet(session: Session, audit_id: int) -> int:
    au = session.get(models.AuditSession, audit_id)
    if not au:
        return 0
    q = select(models.InventoryItem).where(models.InventoryItem.is_active == True)  # noqa: E712
    if au.category_id:
        q = q.where(models.InventoryItem.category_id == au.category_id)
    if au.location_id:
        q = q.where(models.InventoryItem.storage_location_id == au.location_id)
    items = session.scalars(q).all()
    n = 0
    for it in items:
        line = models.AuditLine(
            audit_session_id=au.id,
            item_id=it.id,
            expected_qty=it.quantity_in_stock,
        )
        session.add(line)
        n += 1
    au.status = models.AuditStatus.IN_PROGRESS.value
    session.flush()
    return n


def submit_audit_counts(session: Session, audit_id: int, user_id: int, counts: list[dict]) -> bool:
    """counts: [{line_id, counted_qty}]"""
    au = session.get(models.AuditSession, audit_id)
    if not au:
        return False
    for c in counts:
        line = session.get(models.AuditLine, int(c["line_id"]))
        if not line or line.audit_session_id != au.id:
            continue
        line.counted_qty = float(c["counted_qty"])
        line.variance = line.counted_qty - line.expected_qty
    au.status = models.AuditStatus.PENDING_REVIEW.value
    insert_activity_log(session, user_id=user_id, action="SUBMIT_AUDIT", entity_type="audit", entity_id=au.audit_ref)
    return True


def approve_audit(session: Session, audit_id: int, reviewer_id: int) -> bool:
    au = session.get(models.AuditSession, audit_id)
    if not au or au.status != models.AuditStatus.PENDING_REVIEW.value:
        return False
    for line in au.lines:
        if line.variance is None:
            continue
        if abs(line.variance) > 1e-9:
            adjustment_stock(
                session,
                item_id=line.item_id,
                delta=line.variance,
                performed_by=reviewer_id,
                reference_number=au.audit_ref,
                notes="Audit adjustment",
                approved_by=reviewer_id,
            )
        it = get_item(session, line.item_id)
        if it:
            it.last_audit_date = date.today()
    au.status = models.AuditStatus.APPROVED.value
    au.reviewed_by = reviewer_id
    au.reviewed_at = datetime.utcnow()
    insert_activity_log(session, user_id=reviewer_id, action="APPROVE_AUDIT", entity_type="audit", entity_id=au.audit_ref)
    return True


def list_audits(session: Session) -> Sequence[models.AuditSession]:
    return session.scalars(select(models.AuditSession).order_by(models.AuditSession.created_at.desc())).all()


# --- Reference data ---


def list_categories(session: Session) -> Sequence[models.Category]:
    return session.scalars(select(models.Category).order_by(models.Category.name)).all()


def list_units(session: Session) -> Sequence[models.UnitOfMeasure]:
    return session.scalars(select(models.UnitOfMeasure).order_by(models.UnitOfMeasure.code)).all()


def list_locations(session: Session) -> Sequence[models.StorageLocation]:
    return session.scalars(select(models.StorageLocation).order_by(models.StorageLocation.name)).all()


# --- Config ---


def get_config(session: Session, key: str, default: str | None = None) -> str | None:
    row = session.scalar(select(models.SystemConfig).where(models.SystemConfig.key == key))
    return row.value if row else default


def set_config(session: Session, key: str, value: str, user_id: int | None = None) -> None:
    row = session.scalar(select(models.SystemConfig).where(models.SystemConfig.key == key))
    if row:
        row.value = value
        row.updated_at = datetime.utcnow()
    else:
        session.add(models.SystemConfig(key=key, value=value))
    session.flush()
    if user_id:
        insert_activity_log(session, user_id=user_id, action="CONFIG_SET", entity_type="system_config", entity_id=key)


# --- Users (for admin) ---


def get_user_by_username(session: Session, username: str) -> models.User | None:
    return session.scalar(select(models.User).where(models.User.username == username))


def list_users(session: Session) -> Sequence[models.User]:
    return session.scalars(select(models.User).order_by(models.User.username)).all()


def create_user(
    session: Session,
    username: str,
    password_hash: str,
    full_name: str,
    role_id: int,
    actor_id: int | None = None,
) -> models.User:
    u = models.User(username=username, password_hash=password_hash, full_name=full_name, role_id=role_id)
    session.add(u)
    session.flush()
    if actor_id is not None:
        insert_activity_log(session, user_id=actor_id, action="CREATE_USER", entity_type="user", entity_id=username)
    return u


# --- Alert engine ---


def _recent_alert_rule_item_pairs(session: Session, hours: int = 4) -> set[tuple[int, int]]:
    """(rule_id, item_id) pairs that already have an alert_log row in the last *hours*."""
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = session.execute(
        select(models.AlertLog.rule_id, models.AlertLog.item_id).where(
            models.AlertLog.created_at >= since,
            models.AlertLog.rule_id.is_not(None),
            models.AlertLog.item_id.is_not(None),
        )
    ).all()
    return {(int(rule_id), int(item_id)) for rule_id, item_id in rows}


def _latest_stock_transaction_by_item(session: Session, item_ids: Sequence[int]) -> dict[int, models.StockTransaction]:
    """Most recent stock_transactions row per item_id (one query + one id lookup)."""
    ids_list = list(item_ids)
    if not ids_list:
        return {}
    st = models.StockTransaction
    rn = func.row_number().over(partition_by=st.item_id, order_by=st.timestamp.desc()).label("rn")
    sq = select(st.id, rn).where(st.item_id.in_(ids_list)).subquery()
    latest_ids = list(session.scalars(select(sq.c.id).where(sq.c.rn == 1)).all())
    if not latest_ids:
        return {}
    txs = session.scalars(select(st).where(st.id.in_(latest_ids))).all()
    return {t.item_id: t for t in txs}


def evaluate_alerts(session: Session) -> int:
    """Insert alert_log rows for current conditions; returns new rows count."""
    rules = {r.rule_key: r for r in session.scalars(select(models.AlertRule)).all()}
    n = 0
    expiry_days = int(get_config(session, "expiry_warning_days", "30") or "30")
    audit_days = int(get_config(session, "audit_overdue_days", "90") or "90")
    dead_days = int(get_config(session, "dead_stock_days", "90") or "90")
    today = date.today()

    items = session.scalars(select(models.InventoryItem).where(models.InventoryItem.is_active == True)).all()  # noqa: E712
    recent_pairs = _recent_alert_rule_item_pairs(session, hours=4)
    last_tx_by_item = _latest_stock_transaction_by_item(session, [it.id for it in items])

    def has_recent(rule_id: int, item_id: int) -> bool:
        return (rule_id, item_id) in recent_pairs

    for it in items:
        r = rules.get("OUT_OF_STOCK")
        if r and r.enabled and it.quantity_in_stock <= 0 and not has_recent(r.id, it.id):
            insert_alert_log(
                session,
                rule_id=r.id,
                item_id=it.id,
                message=f"Out of stock: {it.name} ({it.item_id})",
                severity=models.AlertSeverity.CRITICAL.value,
            )
            n += 1
            recent_pairs.add((r.id, it.id))
        r = rules.get("LOW_STOCK")
        if (
            r
            and r.enabled
            and it.quantity_in_stock > 0
            and it.quantity_in_stock < it.reorder_point
            and not has_recent(r.id, it.id)
        ):
            insert_alert_log(
                session,
                rule_id=r.id,
                item_id=it.id,
                message=f"Low stock: {it.name} below reorder point",
                severity=models.AlertSeverity.WARNING.value,
            )
            n += 1
            recent_pairs.add((r.id, it.id))
        r = rules.get("EXPIRY")
        if (
            r
            and r.enabled
            and it.expiry_date
            and it.expiry_date <= today + timedelta(days=expiry_days)
            and not has_recent(r.id, it.id)
        ):
            insert_alert_log(
                session,
                rule_id=r.id,
                item_id=it.id,
                message=f"Expiry soon: {it.name} by {it.expiry_date}",
                severity=models.AlertSeverity.WARNING.value,
            )
            n += 1
            recent_pairs.add((r.id, it.id))
        r = rules.get("AUDIT_OVERDUE")
        if (
            r
            and r.enabled
            and it.last_audit_date
            and (today - it.last_audit_date).days > audit_days
            and not has_recent(r.id, it.id)
        ):
            insert_alert_log(
                session,
                rule_id=r.id,
                item_id=it.id,
                message=f"Audit overdue: {it.name}",
                severity=models.AlertSeverity.INFO.value,
            )
            n += 1
            recent_pairs.add((r.id, it.id))
        last_tx = last_tx_by_item.get(it.id)
        r = rules.get("DEAD_STOCK")
        if (
            r
            and r.enabled
            and last_tx
            and (today - last_tx.timestamp.date()).days >= dead_days
            and not has_recent(r.id, it.id)
        ):
            insert_alert_log(
                session,
                rule_id=r.id,
                item_id=it.id,
                message=f"Dead stock risk: {it.name} — no movement {dead_days}+ days",
                severity=models.AlertSeverity.INFO.value,
            )
            n += 1
            recent_pairs.add((r.id, it.id))
    return n


def dashboard_kpis(session: Session) -> dict[str, float]:
    from sqlalchemy import func

    n_skus = session.scalar(
        select(func.count()).select_from(models.InventoryItem).where(models.InventoryItem.is_active == True)  # noqa: E712
    )
    items = session.scalars(select(models.InventoryItem).where(models.InventoryItem.is_active == True)).all()  # noqa: E712
    stock_value = sum(i.quantity_in_stock * i.unit_cost for i in items)
    low = sum(1 for i in items if 0 < i.quantity_in_stock < i.reorder_point)
    oos = sum(1 for i in items if i.quantity_in_stock <= 0)
    pending_po = session.scalar(
        select(func.count())
        .select_from(models.PurchaseOrder)
        .where(models.PurchaseOrder.status.in_([models.POStatus.SUBMITTED.value, models.POStatus.APPROVED.value]))
    )
    return {
        "skus": float(n_skus or 0),
        "stock_value": float(stock_value),
        "low_stock": float(low),
        "out_of_stock": float(oos),
        "pending_po": float(pending_po or 0),
    }


def stock_by_category(session: Session) -> list[dict]:
    rows = session.execute(
        select(models.Category.name, func.sum(models.InventoryItem.quantity_in_stock))
        .join(models.InventoryItem, models.InventoryItem.category_id == models.Category.id)
        .where(models.InventoryItem.is_active == True)  # noqa: E712
        .group_by(models.Category.name)
    ).all()
    return [{"category": r[0], "qty": float(r[1] or 0)} for r in rows]


def abc_distribution(session: Session) -> list[dict]:
    rows = session.execute(
        select(models.Category.abc_class, func.count())
        .join(models.InventoryItem, models.InventoryItem.category_id == models.Category.id)
        .where(models.InventoryItem.is_active == True)  # noqa: E712
        .group_by(models.Category.abc_class)
    ).all()
    return [{"class": r[0], "count": int(r[1])} for r in rows]


def movement_timeseries(session: Session, days: int) -> list[dict]:
    since = datetime.utcnow() - timedelta(days=days)
    tx = session.scalars(
        select(models.StockTransaction).where(models.StockTransaction.timestamp >= since)
    ).all()
    from collections import defaultdict

    by_day: dict[str, float] = defaultdict(float)
    for t in tx:
        k = t.timestamp.date().isoformat()
        if t.type == models.TransactionType.RECEIVE.value:
            by_day[k] += t.quantity
        elif t.type == models.TransactionType.ISSUE.value:
            by_day[k] -= t.quantity
    return sorted([{"date": k, "net": v} for k, v in by_day.items()], key=lambda x: x["date"])


def top_movers(session: Session, days: int, top_n: int = 10) -> tuple[list[dict], list[dict]]:
    since = datetime.utcnow() - timedelta(days=days)
    from collections import defaultdict

    issue_vol: dict[int, float] = defaultdict(float)
    for t in session.scalars(
        select(models.StockTransaction).where(
            models.StockTransaction.timestamp >= since,
            models.StockTransaction.type == models.TransactionType.ISSUE.value,
        )
    ).all():
        issue_vol[t.item_id] += abs(t.quantity)
    ranked = sorted(issue_vol.items(), key=lambda x: x[1], reverse=True)
    fast_ids = [i for i, _ in ranked[:top_n]]
    ranked_slow = sorted(issue_vol.items(), key=lambda x: x[1])
    slow_ids = [i for i, _ in ranked_slow[:top_n]]
    items = {i.id: i for i in session.scalars(select(models.InventoryItem)).all()}

    def rows(ids):
        out = []
        for pk in ids:
            it = items.get(pk)
            if it:
                out.append({"name": it.name, "qty": issue_vol.get(pk, 0)})
        return out

    return rows(fast_ids), rows(slow_ids)


def unique_items_status_review(
    session: Session,
    days: int = 30,
    limit: int | None = None,
) -> list[dict]:
    """Per-SKU snapshot: current status + in / out / net flow over a window.

    Returns one dict per active inventory item with:
        id, item_id, sku, name, on_hand, reorder_point, reorder_quantity,
        status ('OUT' | 'LOW' | 'OVER' | 'OK'), received, issued, net,
        last_movement_at, activity (received + issued).

    Rows are ranked so the most-relevant items surface first:
        1. severity (OUT, then LOW, then OVER, then OK)
        2. recent activity (descending)
        3. name (alphabetical)
    Pass ``limit=None`` (default) to return every active SKU; pass an int to
    cap the response.
    """
    from collections import defaultdict

    since = datetime.utcnow() - timedelta(days=days)
    items = list(
        session.scalars(
            select(models.InventoryItem).where(models.InventoryItem.is_active == True)  # noqa: E712
        ).all()
    )
    if not items:
        return []
    items_by_pk = {it.id: it for it in items}

    rec: dict[int, float] = defaultdict(float)
    iss: dict[int, float] = defaultdict(float)
    last_at: dict[int, datetime | None] = {}
    for t in session.scalars(
        select(models.StockTransaction).where(models.StockTransaction.timestamp >= since)
    ).all():
        pk = t.item_id
        if pk not in items_by_pk:
            continue
        if t.type == models.TransactionType.RECEIVE.value:
            rec[pk] += abs(float(t.quantity or 0))
        elif t.type == models.TransactionType.ISSUE.value:
            iss[pk] += abs(float(t.quantity or 0))
        prev = last_at.get(pk)
        if prev is None or t.timestamp > prev:
            last_at[pk] = t.timestamp

    rows: list[dict] = []
    for it in items:
        on = float(it.quantity_in_stock or 0)
        rp = float(it.reorder_point or 0)
        rq = float(it.reorder_quantity or 0)
        if on <= 0:
            status = "OUT"
        elif on <= rp:
            status = "LOW"
        elif rq and on >= (rp + rq) * 1.5:
            status = "OVER"
        else:
            status = "OK"
        received = rec.get(it.id, 0.0)
        issued = iss.get(it.id, 0.0)
        rows.append(
            {
                "id": it.id,
                "item_id": it.item_id,
                "sku": it.sku or "",
                "name": it.name,
                "on_hand": on,
                "reorder_point": rp,
                "reorder_quantity": rq,
                "status": status,
                "received": received,
                "issued": issued,
                "net": received - issued,
                "last_movement_at": last_at.get(it.id),
                "activity": received + issued,
            }
        )

    sev_order = {"OUT": 0, "LOW": 1, "OVER": 2, "OK": 3}
    rows.sort(key=lambda r: (sev_order[r["status"]], -r["activity"], r["name"].lower()))
    if limit is None:
        return rows
    try:
        n = max(1, int(limit))
    except (TypeError, ValueError):
        return rows
    return rows[:n]


def movement_summary(session: Session, since: datetime, until: datetime) -> dict[str, float]:
    txns = session.scalars(
        select(models.StockTransaction).where(
            models.StockTransaction.timestamp >= since,
            models.StockTransaction.timestamp <= until,
        )
    ).all()
    rec = sum(t.quantity for t in txns if t.type == models.TransactionType.RECEIVE.value)
    iss = sum(t.quantity for t in txns if t.type == models.TransactionType.ISSUE.value)
    return {"received": rec, "issued": iss, "net": rec - iss}


def daily_issue_sales_proxy(session: Session, days: int) -> list[dict[str, Any]]:
    """
    Daily aggregates of ISSUE (stock-out) transactions.

    *units*: quantity issued. *revenue_proxy*: quantity × current item unit_price.
    Interpretation for analytics: treat stock-out as realised sales (same units / revenue proxy).
    """
    since = datetime.utcnow() - timedelta(days=days)
    # Portable across SQLite + Postgres. CAST(x AS DATE) on SQLite falls back
    # to NUMERIC affinity and returns the leading integer (e.g. 2026) instead
    # of a date, which then breaks SQLAlchemy's Date result processor with
    # "fromisoformat: argument must be str". func.date() is the standard SQL
    # DATE() function: on SQLite it returns ISO text "YYYY-MM-DD", on Postgres
    # it returns a true date. The loop below accepts both.
    day_key = func.date(models.StockTransaction.timestamp)
    rows = session.execute(
        select(
            day_key.label("d"),
            func.sum(models.StockTransaction.quantity).label("units"),
            func.sum(models.StockTransaction.quantity * models.InventoryItem.unit_price).label("revenue"),
        )
        .join(models.InventoryItem, models.InventoryItem.id == models.StockTransaction.item_id)
        .where(
            models.StockTransaction.timestamp >= since,
            models.StockTransaction.type == models.TransactionType.ISSUE.value,
        )
        .group_by(day_key)
        .order_by(day_key)
    ).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        d, units, rev = r[0], float(r[1] or 0), float(r[2] or 0)
        if d is None:
            continue
        ds = d if isinstance(d, str) else (d.isoformat() if hasattr(d, "isoformat") else str(d))
        out.append({"ds": ds, "y_units": units, "y_revenue": rev})
    return out


# --- Inventory change approval (clerk submit → manager PIN approve) ---


def _role_name_for_user(session: Session, user_id: int) -> str | None:
    u = session.get(models.User, user_id)
    if not u:
        return None
    r = session.get(models.Role, u.role_id)
    return r.name if r else None


def user_has_approval_pin(session: Session, user_id: int) -> bool:
    u = session.get(models.User, user_id)
    return bool(u and u.approval_pin_hash)


def set_user_approval_pin(
    session: Session,
    *,
    user_id: int,
    new_pin: str,
    old_pin: str | None,
) -> tuple[bool, str]:
    from utils.auth import hash_password, verify_password

    u = session.get(models.User, user_id)
    if not u:
        return False, "User not found."
    rname = _role_name_for_user(session, user_id)
    if rname not in ("MANAGER", "ADMIN"):
        return False, "Only managers and administrators can set an approval PIN."
    pin = (new_pin or "").strip()
    if len(pin) < 4:
        return False, "PIN must be at least 4 characters."
    if u.approval_pin_hash:
        if not old_pin or not verify_password(old_pin.strip(), u.approval_pin_hash):
            return False, "Current PIN is incorrect."
    u.approval_pin_hash = hash_password(pin)
    insert_activity_log(
        session,
        user_id=user_id,
        action="APPROVAL_PIN_SET",
        entity_type="user",
        entity_id=str(user_id),
    )
    return True, "Approval PIN saved."


def clear_user_approval_pin(session: Session, *, user_id: int, old_pin: str) -> tuple[bool, str]:
    from utils.auth import verify_password

    u = session.get(models.User, user_id)
    if not u or not u.approval_pin_hash:
        return False, "No PIN is set."
    if not old_pin or not verify_password(old_pin.strip(), u.approval_pin_hash):
        return False, "Current PIN is incorrect."
    u.approval_pin_hash = None
    insert_activity_log(
        session,
        user_id=user_id,
        action="APPROVAL_PIN_CLEARED",
        entity_type="user",
        entity_id=str(user_id),
    )
    return True, "Approval PIN removed."


def queue_inventory_change(
    session: Session,
    *,
    action: str,
    submitted_by: int,
    item_pk: int | None = None,
    fields: dict[str, Any] | None = None,
    item_display: str | None = None,
) -> models.InventoryChangeRequest:
    payload = {"fields": fields or {}, "item_pk": item_pk, "item_display": item_display}
    row = models.InventoryChangeRequest(
        action=action,
        payload_json=json.dumps(payload, default=str),
        item_id=item_pk,
        submitted_by=submitted_by,
        status="PENDING",
    )
    session.add(row)
    session.flush()
    insert_activity_log(
        session,
        user_id=submitted_by,
        action="INVENTORY_SUBMITTED_FOR_APPROVAL",
        entity_type="inventory_change_request",
        entity_id=str(row.id),
        details=f"{action} {item_display or ''}".strip(),
    )
    return row


def _deserialize_inventory_fields(d: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime as dt

    ex = d.get("expiry_date")
    if ex:
        exd = dt.strptime(str(ex)[:10], "%Y-%m-%d").date()
    else:
        exd = None
    loc = d.get("storage_location_id")
    sup = d.get("supplier_id")
    return {
        "name": d["name"],
        "description": d.get("description"),
        "category_id": int(d["category_id"]),
        "unit_of_measure_id": int(d["unit_of_measure_id"]),
        "quantity_in_stock": sanitize_float(d.get("quantity_in_stock"), 0.0),
        "reorder_point": sanitize_float(d.get("reorder_point"), 0.0),
        "reorder_quantity": sanitize_float(d.get("reorder_quantity"), 0.0),
        "unit_cost": sanitize_float(d.get("unit_cost"), 0.0),
        "unit_price": sanitize_float(d.get("unit_price"), 0.0),
        "storage_location_id": int(loc) if loc not in (None, "") else None,
        "supplier_id": int(sup) if sup not in (None, "") else None,
        "expiry_date": exd,
        "barcode": d.get("barcode"),
        "sku": d.get("sku"),
    }


def list_pending_inventory_change_requests(session: Session) -> list[dict[str, Any]]:
    q = (
        select(models.InventoryChangeRequest, models.User.full_name)
        .join(models.User, models.InventoryChangeRequest.submitted_by == models.User.id)
        .where(models.InventoryChangeRequest.status == "PENDING")
        .order_by(models.InventoryChangeRequest.created_at.desc())
    )
    out: list[dict[str, Any]] = []
    for req, submitter_name in session.execute(q).all():
        payload = json.loads(req.payload_json)
        fields = payload.get("fields") or {}
        summary = fields.get("name") or payload.get("item_display") or (str(req.item_id) if req.item_id else "")
        out.append(
            {
                "id": req.id,
                "created_at": req.created_at.isoformat()[:19] if req.created_at else "",
                "action": req.action,
                "submitter": submitter_name,
                "summary": summary,
                "item_pk": payload.get("item_pk"),
            }
        )
    return out


def _verify_approver_pin(session: Session, approver_id: int, pin_plain: str) -> tuple[bool, str]:
    from utils.auth import verify_password

    rname = _role_name_for_user(session, approver_id)
    if rname not in ("MANAGER", "ADMIN"):
        return False, "Only a manager or administrator can approve inventory changes."
    u = session.get(models.User, approver_id)
    if not u or not u.approval_pin_hash:
        return False, "Set your approval PIN under Configuration before approving."
    if not pin_plain or not verify_password(pin_plain.strip(), u.approval_pin_hash):
        return False, "Invalid approval PIN."
    return True, ""


def _approve_inventory_change_request_core(
    session: Session,
    *,
    request_id: int,
    approver_id: int,
) -> tuple[bool, str]:
    """Apply one pending request (no PIN check). DB errors propagate for savepoint rollback."""
    req = session.get(models.InventoryChangeRequest, request_id)
    if not req:
        return False, "Request not found."
    if req.status != "PENDING":
        return False, "This request was already processed."
    payload = json.loads(req.payload_json)
    fields = _deserialize_inventory_fields(payload.get("fields") or {})
    item_pk = payload.get("item_pk")
    if req.action == "CREATE":
        create_item(session, created_by=req.submitted_by, **fields)
    elif req.action == "UPDATE":
        if not item_pk:
            return False, "Missing item reference."
        update_item(session, int(item_pk), approver_id, **fields)
    elif req.action == "SOFT_DELETE":
        if not item_pk:
            return False, "Missing item reference."
        soft_delete_item(session, int(item_pk), approver_id)
    else:
        return False, f"Unknown action: {req.action}"
    req.status = "APPROVED"
    req.reviewed_by = approver_id
    req.reviewed_at = datetime.utcnow()
    insert_activity_log(
        session,
        user_id=approver_id,
        action="INVENTORY_CHANGE_APPROVED",
        entity_type="inventory_change_request",
        entity_id=str(req.id),
        details=req.action,
    )
    return True, "Approved and applied."


def approve_inventory_change_request(
    session: Session,
    *,
    request_id: int,
    approver_id: int,
    pin_plain: str,
) -> tuple[bool, str]:
    ok, msg = _verify_approver_pin(session, approver_id, pin_plain)
    if not ok:
        return False, msg
    try:
        return _approve_inventory_change_request_core(session, request_id=request_id, approver_id=approver_id)
    except Exception as e:
        session.rollback()
        return False, str(e)


def bulk_approve_inventory_change_requests(
    session: Session,
    *,
    request_ids: Sequence[int],
    approver_id: int,
    pin_plain: str,
) -> tuple[int, int, list[str]]:
    """Verify PIN once; approve each id in a savepoint so one failure does not undo the rest.

    Returns (approved_count, failed_count, error_lines).
    """
    unique = sorted({int(x) for x in request_ids})
    ok, msg = _verify_approver_pin(session, approver_id, pin_plain)
    if not ok:
        return 0, len(unique), [msg]
    n_ok = 0
    errs: list[str] = []
    for rid in unique:
        try:
            with session.begin_nested():
                inner_ok, inner_msg = _approve_inventory_change_request_core(
                    session, request_id=rid, approver_id=approver_id
                )
                if not inner_ok:
                    raise ValueError(inner_msg)
                n_ok += 1
        except Exception as e:
            errs.append(f"Request #{rid}: {e}")
    return n_ok, len(unique) - n_ok, errs


def _reject_inventory_change_request_core(
    session: Session,
    *,
    request_id: int,
    approver_id: int,
    note: str | None = None,
) -> tuple[bool, str]:
    req = session.get(models.InventoryChangeRequest, request_id)
    if not req:
        return False, "Request not found."
    if req.status != "PENDING":
        return False, "This request was already processed."
    req.status = "REJECTED"
    req.reviewed_by = approver_id
    req.reviewed_at = datetime.utcnow()
    req.reviewer_note = (note or "").strip() or None
    insert_activity_log(
        session,
        user_id=approver_id,
        action="INVENTORY_CHANGE_REJECTED",
        entity_type="inventory_change_request",
        entity_id=str(req.id),
        details=(note or "")[:200],
    )
    return True, "Request rejected."


def reject_inventory_change_request(
    session: Session,
    *,
    request_id: int,
    approver_id: int,
    pin_plain: str,
    note: str | None = None,
) -> tuple[bool, str]:
    ok, msg = _verify_approver_pin(session, approver_id, pin_plain)
    if not ok:
        return False, msg
    try:
        return _reject_inventory_change_request_core(
            session, request_id=request_id, approver_id=approver_id, note=note
        )
    except Exception as e:
        session.rollback()
        return False, str(e)


def bulk_reject_inventory_change_requests(
    session: Session,
    *,
    request_ids: Sequence[int],
    approver_id: int,
    pin_plain: str,
    note: str | None = None,
) -> tuple[int, int, list[str]]:
    unique = sorted({int(x) for x in request_ids})
    ok, msg = _verify_approver_pin(session, approver_id, pin_plain)
    if not ok:
        return 0, len(unique), [msg]
    n_ok = 0
    errs: list[str] = []
    for rid in unique:
        try:
            with session.begin_nested():
                inner_ok, inner_msg = _reject_inventory_change_request_core(
                    session, request_id=rid, approver_id=approver_id, note=note
                )
                if not inner_ok:
                    raise ValueError(inner_msg)
                n_ok += 1
        except Exception as e:
            errs.append(f"Request #{rid}: {e}")
    return n_ok, len(unique) - n_ok, errs


# --- Multi-location (bin-level) ---


def list_storage_locations(session: Session) -> Sequence[models.StorageLocation]:
    return session.scalars(
        select(models.StorageLocation).order_by(models.StorageLocation.warehouse, models.StorageLocation.name)
    ).all()


def create_storage_location(
    session: Session,
    *,
    name: str,
    warehouse: str,
    zone: str | None,
    user_id: int,
) -> models.StorageLocation:
    loc = models.StorageLocation(name=name.strip(), warehouse=warehouse.strip(), zone=(zone or None))
    session.add(loc)
    session.flush()
    insert_activity_log(
        session, user_id=user_id, action="CREATE", entity_type="storage_location", entity_id=str(loc.id)
    )
    return loc


def list_item_location_stock_matrix(session: Session) -> list[dict[str, Any]]:
    q = (
        select(models.ItemLocationStock, models.InventoryItem, models.StorageLocation)
        .join(models.InventoryItem, models.InventoryItem.id == models.ItemLocationStock.item_id)
        .join(
            models.StorageLocation,
            models.StorageLocation.id == models.ItemLocationStock.storage_location_id,
        )
        .where(models.InventoryItem.is_active == True)  # noqa: E712
        .order_by(models.InventoryItem.name, models.StorageLocation.name)
    )
    out: list[dict[str, Any]] = []
    for ils, it, loc in session.execute(q):
        out.append(
            {
                "ils_id": ils.id,
                "item_id": it.id,
                "item_code": it.item_id,
                "item_name": it.name,
                "location_id": loc.id,
                "location": loc.name,
                "warehouse": loc.warehouse,
                "qty": float(ils.quantity),
                "total_on_hand": float(it.quantity_in_stock),
            }
        )
    return out


def transfer_bin_stock(
    session: Session,
    *,
    item_id: int,
    from_location_id: int,
    to_location_id: int,
    quantity: float,
    performed_by: int,
    reference_number: str | None = None,
) -> None:
    if int(from_location_id) == int(to_location_id):
        raise ValueError("Source and destination must differ")
    item = get_item(session, item_id)
    if not item or not item.is_active:
        raise ValueError("Invalid item")
    q = float(quantity)
    if q <= 0:
        raise ValueError("Quantity must be positive")
    adjust_item_location_quantity(
        session, item_id=item_id, storage_location_id=int(from_location_id), delta=-q
    )
    adjust_item_location_quantity(
        session, item_id=item_id, storage_location_id=int(to_location_id), delta=q
    )
    insert_stock_transaction(
        session,
        item_id=item_id,
        txn_type=models.TransactionType.TRANSFER.value,
        quantity=q,
        performed_by=performed_by,
        reference_number=reference_number,
        notes=f"BIN {from_location_id}->{to_location_id}",
    )
    insert_activity_log(
        session,
        user_id=performed_by,
        action="TRANSFER_BIN",
        entity_type="inventory_item",
        entity_id=item.item_id,
        details=f"{from_location_id}->{to_location_id} qty={q}",
    )


# --- Customers & sales orders ---


def list_customers(session: Session, active_only: bool = True) -> Sequence[models.Customer]:
    q = select(models.Customer).order_by(models.Customer.name)
    if active_only:
        q = q.where(models.Customer.is_active == True)  # noqa: E712
    return session.scalars(q).all()


def create_customer(
    session: Session,
    *,
    user_id: int,
    name: str,
    phone: str | None = None,
    email: str | None = None,
    address: str | None = None,
    country: str = "",
) -> models.Customer:
    code = f"CUST-{uuid.uuid4().hex[:8].upper()}"
    c = models.Customer(
        customer_code=code,
        name=name.strip(),
        phone=phone,
        email=email,
        address=address,
        country=(country or "").strip(),
    )
    session.add(c)
    session.flush()
    insert_activity_log(session, user_id=user_id, action="CREATE", entity_type="customer", entity_id=code)
    return c


def create_sales_order_draft(
    session: Session, *, customer_id: int, created_by: int, notes: str | None = None
) -> models.SalesOrder:
    so = models.SalesOrder(
        so_number=f"SO-{uuid.uuid4().hex[:10].upper()}",
        customer_id=int(customer_id),
        status=models.SalesOrderStatus.DRAFT.value,
        notes=notes,
        created_by=created_by,
        order_date=date.today(),
    )
    session.add(so)
    session.flush()
    insert_activity_log(
        session, user_id=created_by, action="CREATE", entity_type="sales_order", entity_id=so.so_number
    )
    return so


def add_sales_order_line(
    session: Session, *, so_pk: int, item_id: int, qty: float, unit_price: float
) -> models.SalesOrderLine | None:
    so = session.get(models.SalesOrder, so_pk)
    if not so or so.status != models.SalesOrderStatus.DRAFT.value:
        return None
    ln = models.SalesOrderLine(
        sales_order_id=so.id,
        item_id=int(item_id),
        quantity_ordered=float(qty),
        unit_price=float(unit_price),
    )
    session.add(ln)
    session.flush()
    return ln


def list_sales_orders(session: Session, limit: int = 200) -> Sequence[models.SalesOrder]:
    return session.scalars(
        select(models.SalesOrder).order_by(models.SalesOrder.created_at.desc()).limit(limit)
    ).all()


def confirm_sales_order(session: Session, so_pk: int, user_id: int) -> tuple[bool, str]:
    so = session.get(models.SalesOrder, so_pk)
    if not so or so.status != models.SalesOrderStatus.DRAFT.value:
        return False, "Order not in draft"
    n_lines = session.scalar(
        select(func.count())
        .select_from(models.SalesOrderLine)
        .where(models.SalesOrderLine.sales_order_id == so_pk)
    )
    if not n_lines:
        return False, "Add order lines first"
    so.status = models.SalesOrderStatus.CONFIRMED.value
    insert_activity_log(
        session, user_id=user_id, action="CONFIRM_SO", entity_type="sales_order", entity_id=so.so_number
    )
    return True, "Confirmed"


def cancel_sales_order(session: Session, so_pk: int, user_id: int) -> tuple[bool, str]:
    so = session.get(models.SalesOrder, so_pk)
    if not so:
        return False, "Not found"
    if so.status == models.SalesOrderStatus.CANCELLED.value:
        return False, "Already cancelled"
    if so.status == models.SalesOrderStatus.SHIPPED.value:
        return False, "Already fully shipped"
    if so.status == models.SalesOrderStatus.DRAFT.value:
        so.status = models.SalesOrderStatus.CANCELLED.value
        insert_activity_log(
            session, user_id=user_id, action="CANCEL_SO", entity_type="sales_order", entity_id=so.so_number
        )
        return True, "Cancelled"
    if so.status in (models.SalesOrderStatus.CONFIRMED.value, models.SalesOrderStatus.PICKING.value):
        for ln in session.scalars(
            select(models.SalesOrderLine).where(models.SalesOrderLine.sales_order_id == so_pk)
        ):
            if float(ln.quantity_shipped) > 1e-9:
                return False, "Partially shipped — cannot cancel"
    so.status = models.SalesOrderStatus.CANCELLED.value
    insert_activity_log(
        session, user_id=user_id, action="CANCEL_SO", entity_type="sales_order", entity_id=so.so_number
    )
    return True, "Cancelled"


def ship_sales_order_line(
    session: Session,
    *,
    so_line_id: int,
    ship_qty: float,
    performed_by: int,
    storage_location_id: int | None = None,
) -> tuple[bool, str]:
    line = session.get(models.SalesOrderLine, int(so_line_id))
    if not line:
        return False, "Line not found"
    so = session.get(models.SalesOrder, line.sales_order_id)
    if not so or so.status not in (
        models.SalesOrderStatus.CONFIRMED.value,
        models.SalesOrderStatus.PICKING.value,
    ):
        return False, "Order not ready to ship"
    remaining = float(line.quantity_ordered) - float(line.quantity_shipped)
    q = min(float(ship_qty), remaining)
    if q < 1e-9:
        return False, "Nothing to ship"
    try:
        issue_stock_fifo(
            session,
            item_id=line.item_id,
            quantity=q,
            performed_by=performed_by,
            reference_number=so.so_number,
            notes=f"SO ship line {line.id}",
            storage_location_id=storage_location_id,
            sales_order_line_id=line.id,
        )
    except ValueError as e:
        return False, str(e)
    line.quantity_shipped = float(line.quantity_shipped) + q
    order_lines = session.scalars(
        select(models.SalesOrderLine).where(models.SalesOrderLine.sales_order_id == so.id)
    ).all()
    all_done = all(
        float(x.quantity_shipped) + 1e-9 >= float(x.quantity_ordered) for x in order_lines
    )
    so.status = models.SalesOrderStatus.SHIPPED.value if all_done else models.SalesOrderStatus.PICKING.value
    insert_activity_log(
        session,
        user_id=performed_by,
        action="SHIP_SO_LINE",
        entity_type="sales_order",
        entity_id=so.so_number,
        details=f"line={line.id} qty={q}",
    )
    return True, f"Shipped {q}"


# --- BOM / kits ---


def list_bom_lines(session: Session, parent_item_id: int) -> Sequence[models.BomLine]:
    return session.scalars(
        select(models.BomLine)
        .where(models.BomLine.parent_item_id == int(parent_item_id))
        .order_by(models.BomLine.id)
    ).all()


def bom_would_cycle(session: Session, parent_item_id: int, component_item_id: int) -> bool:
    if int(parent_item_id) == int(component_item_id):
        return True
    stack = [int(component_item_id)]
    seen: set[int] = set()
    while stack:
        cid = stack.pop()
        if cid in seen:
            continue
        seen.add(cid)
        for bl in session.scalars(select(models.BomLine).where(models.BomLine.parent_item_id == cid)):
            nxt = int(bl.component_item_id)
            if nxt == int(parent_item_id):
                return True
            stack.append(nxt)
    return False


def upsert_bom_line(
    session: Session,
    *,
    parent_item_id: int,
    component_item_id: int,
    quantity_per: float,
    user_id: int,
) -> tuple[bool, str]:
    if float(quantity_per) <= 0:
        return False, "quantity_per must be positive"
    if bom_would_cycle(session, parent_item_id, component_item_id):
        return False, "BOM would create a cycle"
    existing = session.scalar(
        select(models.BomLine).where(
            models.BomLine.parent_item_id == int(parent_item_id),
            models.BomLine.component_item_id == int(component_item_id),
        )
    )
    if existing:
        existing.quantity_per = float(quantity_per)
    else:
        session.add(
            models.BomLine(
                parent_item_id=int(parent_item_id),
                component_item_id=int(component_item_id),
                quantity_per=float(quantity_per),
            )
        )
    session.flush()
    insert_activity_log(
        session, user_id=user_id, action="UPSERT_BOM", entity_type="bom", entity_id=str(parent_item_id)
    )
    return True, "OK"


def delete_bom_line(session: Session, bom_line_id: int, user_id: int) -> bool:
    row = session.get(models.BomLine, int(bom_line_id))
    if not row:
        return False
    pid = row.parent_item_id
    session.delete(row)
    insert_activity_log(session, user_id=user_id, action="DELETE_BOM", entity_type="bom", entity_id=str(pid))
    return True


def assemble_kit(
    session: Session,
    *,
    parent_item_id: int,
    quantity_built: float,
    performed_by: int,
    storage_location_id: int | None = None,
) -> tuple[bool, str]:
    qb = float(quantity_built)
    if qb <= 0:
        return False, "quantity must be positive"
    parent = get_item(session, parent_item_id)
    if not parent or not parent.is_active:
        return False, "Invalid parent SKU"
    lines = list(list_bom_lines(session, parent_item_id))
    if not lines:
        return False, "No BOM lines for this item"
    total_cost = 0.0
    try:
        with session.begin_nested():
            for bl in lines:
                need = qb * float(bl.quantity_per)
                txs = issue_stock_fifo(
                    session,
                    item_id=bl.component_item_id,
                    quantity=need,
                    performed_by=performed_by,
                    reference_number=f"KIT->{parent.item_id}",
                    notes=f"Assemble parent {parent_item_id}",
                    storage_location_id=storage_location_id,
                )
                for t in txs:
                    if t.batch_id:
                        b = session.get(models.InventoryBatch, t.batch_id)
                        if b:
                            total_cost += float(t.quantity) * float(b.unit_cost)
            unit_cost = total_cost / qb if qb else 0.0
            receive_stock(
                session,
                item_id=parent_item_id,
                quantity=qb,
                unit_cost=max(unit_cost, 0.0),
                performed_by=performed_by,
                reference_number=f"ASSEMBLE-{parent.item_id}",
                notes="Kit assembly",
                storage_location_id=storage_location_id,
            )
    except ValueError as e:
        return False, str(e)
    insert_activity_log(
        session,
        user_id=performed_by,
        action="ASSEMBLE_KIT",
        entity_type="inventory_item",
        entity_id=parent.item_id,
        details=f"qty={qb}",
    )
    return True, f"Built {qb} × {parent.name}"


# --- REST API tokens ---


def create_api_token(session: Session, *, user_id: int, label: str) -> tuple[models.ApiToken, str]:
    plain = secrets.token_urlsafe(32)
    row = models.ApiToken(
        label=(label or "").strip() or "API key",
        token_hash=hash_password(plain),
        created_by=user_id,
    )
    session.add(row)
    session.flush()
    insert_activity_log(
        session, user_id=user_id, action="CREATE", entity_type="api_token", entity_id=str(row.id)
    )
    return row, plain


def list_api_tokens(session: Session) -> Sequence[models.ApiToken]:
    return session.scalars(select(models.ApiToken).order_by(models.ApiToken.created_at.desc())).all()


def revoke_api_token(session: Session, token_pk: int, user_id: int) -> bool:
    row = session.get(models.ApiToken, int(token_pk))
    if not row:
        return False
    row.is_active = False
    insert_activity_log(
        session, user_id=user_id, action="REVOKE", entity_type="api_token", entity_id=str(token_pk)
    )
    return True


def verify_api_token_string(session: Session, plain: str) -> models.ApiToken | None:
    p = (plain or "").strip()
    if not p:
        return None
    for row in session.scalars(select(models.ApiToken).where(models.ApiToken.is_active == True)):  # noqa: E712
        if verify_password(p, row.token_hash):
            row.last_used_at = datetime.utcnow()
            return row
    return None
