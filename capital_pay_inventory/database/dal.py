"""
Data access layer. stock_transactions, activity_log, alert_log: INSERT + SELECT only (no UPDATE/DELETE).
Acknowledgments use alert_acknowledgments (append-only).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Optional, Sequence

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from database import models
from utils.fifo import consume_fifo, list_batches_fifo


class ImmutableMutationError(RuntimeError):
    pass


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
    out = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "rule_id": r.rule_id,
                "item_id": r.item_id,
                "message": r.message,
                "severity": r.severity,
                "created_at": r.created_at,
                "acknowledged": is_alert_acknowledged(session, r.id),
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
    for k, v in fields.items():
        if k in allowed and v is not None:
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
) -> tuple[models.InventoryBatch, models.StockTransaction]:
    item = get_item(session, item_id)
    if not item or not item.is_active:
        raise ValueError("Invalid item")
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
) -> list[models.StockTransaction]:
    item = get_item(session, item_id)
    if not item or not item.is_active:
        raise ValueError("Invalid item")
    allocations = consume_fifo(session, item_id, quantity)
    item.quantity_in_stock -= quantity
    item.last_updated = datetime.utcnow()
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
) -> models.StockTransaction:
    item = get_item(session, item_id)
    if not item:
        raise ValueError("Invalid item")
    item.quantity_in_stock += delta
    item.last_updated = datetime.utcnow()
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


def _recent_same_alert(session: Session, rule_id: int | None, item_id: int | None, hours: int = 4) -> bool:
    if rule_id is None or item_id is None:
        return False
    since = datetime.utcnow() - timedelta(hours=hours)
    q = (
        select(func.count())
        .select_from(models.AlertLog)
        .where(
            models.AlertLog.rule_id == rule_id,
            models.AlertLog.item_id == item_id,
            models.AlertLog.created_at >= since,
        )
    )
    return (session.scalar(q) or 0) > 0


def evaluate_alerts(session: Session) -> int:
    """Insert alert_log rows for current conditions; returns new rows count."""
    rules = {r.rule_key: r for r in session.scalars(select(models.AlertRule)).all()}
    n = 0
    expiry_days = int(get_config(session, "expiry_warning_days", "30") or "30")
    audit_days = int(get_config(session, "audit_overdue_days", "90") or "90")
    dead_days = int(get_config(session, "dead_stock_days", "90") or "90")
    today = date.today()

    items = session.scalars(select(models.InventoryItem).where(models.InventoryItem.is_active == True)).all()  # noqa: E712
    for it in items:
        r = rules.get("OUT_OF_STOCK")
        if r and r.enabled and it.quantity_in_stock <= 0 and not _recent_same_alert(session, r.id, it.id):
            insert_alert_log(
                session,
                rule_id=r.id,
                item_id=it.id,
                message=f"Out of stock: {it.name} ({it.item_id})",
                severity=models.AlertSeverity.CRITICAL.value,
            )
            n += 1
        r = rules.get("LOW_STOCK")
        if (
            r
            and r.enabled
            and it.quantity_in_stock > 0
            and it.quantity_in_stock < it.reorder_point
            and not _recent_same_alert(session, r.id, it.id)
        ):
            insert_alert_log(
                session,
                rule_id=r.id,
                item_id=it.id,
                message=f"Low stock: {it.name} below reorder point",
                severity=models.AlertSeverity.WARNING.value,
            )
            n += 1
        r = rules.get("EXPIRY")
        if (
            r
            and r.enabled
            and it.expiry_date
            and it.expiry_date <= today + timedelta(days=expiry_days)
            and not _recent_same_alert(session, r.id, it.id)
        ):
            insert_alert_log(
                session,
                rule_id=r.id,
                item_id=it.id,
                message=f"Expiry soon: {it.name} by {it.expiry_date}",
                severity=models.AlertSeverity.WARNING.value,
            )
            n += 1
        r = rules.get("AUDIT_OVERDUE")
        if (
            r
            and r.enabled
            and it.last_audit_date
            and (today - it.last_audit_date).days > audit_days
            and not _recent_same_alert(session, r.id, it.id)
        ):
            insert_alert_log(
                session,
                rule_id=r.id,
                item_id=it.id,
                message=f"Audit overdue: {it.name}",
                severity=models.AlertSeverity.INFO.value,
            )
            n += 1
        last_tx = session.scalars(
            select(models.StockTransaction)
            .where(models.StockTransaction.item_id == it.id)
            .order_by(models.StockTransaction.timestamp.desc())
            .limit(1)
        ).first()
        r = rules.get("DEAD_STOCK")
        if (
            r
            and r.enabled
            and last_tx
            and (today - last_tx.timestamp.date()).days >= dead_days
            and not _recent_same_alert(session, r.id, it.id)
        ):
            insert_alert_log(
                session,
                rule_id=r.id,
                item_id=it.id,
                message=f"Dead stock risk: {it.name} — no movement {dead_days}+ days",
                severity=models.AlertSeverity.INFO.value,
            )
            n += 1
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
