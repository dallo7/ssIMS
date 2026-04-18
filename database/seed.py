"""Database seeding: demo dataset for development, or minimal reference data for production."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import models
from database.engine import db_session
from utils.auth import hash_password
from utils.fifo import consume_fifo
from utils.server_config import is_production_env


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _seed_mode() -> str:
    raw = (os.environ.get("CPI_SEED_MODE") or "").strip().lower()
    if raw:
        return raw
    if is_production_env():
        return "minimal"
    return "demo"


def _is_minimal_mode(mode: str) -> bool:
    return mode in ("minimal", "production", "prod", "empty", "none")


def ensure_minimal_reference(session: Session) -> None:
    """Idempotent: roles, alert rules, system_config. No inventory, suppliers, or demo users."""
    if not session.scalar(select(models.Role).limit(1)):
        roles = {
            "ADMIN": models.Role(name="ADMIN", description="Full system access"),
            "MANAGER": models.Role(name="MANAGER", description="Approvals & reporting"),
            "STOCK_CLERK": models.Role(name="STOCK_CLERK", description="Stock operations"),
            "VIEWER": models.Role(name="VIEWER", description="Read-only"),
        }
        for r in roles.values():
            session.add(r)
        session.flush()

    if not session.scalar(select(models.AlertRule).limit(1)):
        for key, name, sev, days in (
            ("LOW_STOCK", "Low stock vs reorder point", models.AlertSeverity.WARNING.value, None),
            ("OUT_OF_STOCK", "Out of stock", models.AlertSeverity.CRITICAL.value, None),
            ("EXPIRY", "Expiry warning window", models.AlertSeverity.WARNING.value, 30),
            ("AUDIT_OVERDUE", "Audit overdue", models.AlertSeverity.INFO.value, 90),
            ("DEAD_STOCK", "Dead stock detection", models.AlertSeverity.INFO.value, 90),
        ):
            session.add(
                models.AlertRule(rule_key=key, name=name, enabled=True, threshold_days=days, severity=sev)
            )

    if not session.scalar(select(models.SystemConfig).limit(1)):
        for k, v in (
            ("expiry_warning_days", "30"),
            ("audit_overdue_days", "60"),
            ("dead_stock_days", "60"),
            ("theme_default", "light"),
        ):
            session.add(models.SystemConfig(key=k, value=v))


def bootstrap_admin_from_env(session: Session) -> bool:
    """If there are no users and CPI_BOOTSTRAP_ADMIN_PASSWORD is set, create the first admin. Returns True if created."""
    if session.scalar(select(models.User).limit(1)):
        return False
    pw = (os.environ.get("CPI_BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
    if not pw:
        return False
    username = (os.environ.get("CPI_BOOTSTRAP_ADMIN_USERNAME") or "admin").strip() or "admin"
    full_name = (os.environ.get("CPI_BOOTSTRAP_ADMIN_FULL_NAME") or "Administrator").strip() or "Administrator"
    admin_role = session.scalar(select(models.Role).where(models.Role.name == "ADMIN"))
    if not admin_role:
        return False
    session.add(
        models.User(
            username=username,
            password_hash=hash_password(pw),
            full_name=full_name,
            role_id=admin_role.id,
        )
    )
    return True


def _seed_demo_dataset(session: Session) -> None:
    """First-install demo: roles, admin/admin, reference data, inventory, and history."""
    roles = {
        "ADMIN": models.Role(name="ADMIN", description="Full system access"),
        "MANAGER": models.Role(name="MANAGER", description="Approvals & reporting"),
        "STOCK_CLERK": models.Role(name="STOCK_CLERK", description="Stock operations"),
        "VIEWER": models.Role(name="VIEWER", description="Read-only"),
    }
    for r in roles.values():
        session.add(r)
    session.flush()
    rid = {r.name: r.id for r in session.scalars(select(models.Role)).all()}

    session.add(
        models.User(
            username="admin",
            password_hash=_hash("admin"),
            full_name="Super Administrator",
            role_id=rid["ADMIN"],
        )
    )

    cats = [
        models.Category(name="Beverages", abc_class="A"),
        models.Category(name="Dry Goods", abc_class="B"),
        models.Category(name="Cold Chain", abc_class="A"),
        models.Category(name="Hardware", abc_class="C"),
    ]
    for c in cats:
        session.add(c)
    session.flush()
    cat_by = {c.name: c.id for c in session.scalars(select(models.Category)).all()}

    for code, label in (
        ("kg", "Kilogram"),
        ("L", "Litre"),
        ("pc", "Piece"),
        ("box", "Box"),
    ):
        session.add(models.UnitOfMeasure(code=code, label=label))
    session.flush()
    u_by = {u.code: u.id for u in session.scalars(select(models.UnitOfMeasure)).all()}

    for name, zone in (("WH-A-01", "Zone A"), ("WH-B-02", "Zone B"), ("COLD-01", "Cold")):
        session.add(models.StorageLocation(name=name, zone=zone, warehouse="Juba Main"))

    session.flush()
    locs = list(session.scalars(select(models.StorageLocation)).all())
    loc_ids = [x.id for x in locs]

    sups = [
        models.Supplier(
            name="Nile Trade Supplies",
            contact_person="Akol Deng",
            phone="+211912345678",
            email="sales@niletrade.example",
            country="South Sudan",
            lead_time_days=5,
            rating=4.5,
        ),
        models.Supplier(
            name="East Africa Logistics",
            contact_person="Mary Lado",
            phone="+254700000000",
            email="ops@eal.example",
            country="Kenya",
            lead_time_days=10,
            rating=4.0,
        ),
        models.Supplier(
            name="CapitalPay Procurement",
            contact_person="James Kuol",
            phone="+211900000000",
            email="procurement@capitalpay.example",
            country="South Sudan",
            lead_time_days=3,
            rating=4.8,
        ),
    ]
    for s in sups:
        session.add(s)
    session.flush()
    suppliers = list(session.scalars(select(models.Supplier)).all())

    admin = session.scalar(select(models.User).where(models.User.username == "admin"))

    session.add(
        models.Customer(
            customer_code="CUST-DEMO-01",
            name="Juba Wholesale Partner",
            phone="+211900000001",
            email="orders@jubawholesale.example",
            country="South Sudan",
        )
    )

    demo_items = [
        ("Premium Maize Meal 25kg", "Dry Goods", "kg", 120, 40, 80, 18.5, 24.0, 0),
        ("Sunflower Oil 5L", "Dry Goods", "pc", 200, 60, 100, 6.2, 8.5, 1),
        ("UHT Milk 1L", "Cold Chain", "pc", 300, 100, 150, 0.85, 1.2, 2),
        ("Sugar 1kg", "Dry Goods", "pc", 500, 150, 200, 0.9, 1.4, 0),
        ("Rice 50kg", "Dry Goods", "kg", 80, 25, 50, 32.0, 42.0, 0),
        ("Soap Carton", "Dry Goods", "box", 60, 20, 30, 12.0, 16.0, 0),
        ("Battery AA Pack", "Hardware", "pc", 400, 100, 200, 2.5, 4.0, 0),
        ("Steel Nails 5kg", "Hardware", "pc", 150, 40, 60, 4.0, 6.5, 0),
        ("Bottled Water 500ml", "Beverages", "pc", 800, 200, 400, 0.25, 0.45, 0),
        ("Soda Crate", "Beverages", "box", 90, 30, 45, 8.0, 11.0, 0),
        ("Cooking Gas 13kg", "Hardware", "pc", 45, 10, 15, 28.0, 38.0, 0),
        ("Salt 1kg", "Dry Goods", "pc", 600, 200, 300, 0.35, 0.55, 0),
    ]
    items: list[models.InventoryItem] = []
    for i, row in enumerate(demo_items):
        name, cname, ucode, q, rp, rq, cost, price, sup_i = row
        exp = date.today() + timedelta(days=45 + i * 7) if i % 3 == 0 else None
        it = models.InventoryItem(
            item_id=f"SKU-{1000 + i}",
            name=name,
            description=f"Demo SKU for {name}",
            category_id=cat_by[cname],
            unit_of_measure_id=u_by[ucode],
            quantity_in_stock=q,
            reorder_point=rp,
            reorder_quantity=rq,
            unit_cost=cost,
            unit_price=price,
            storage_location_id=loc_ids[i % len(loc_ids)],
            supplier_id=suppliers[sup_i % len(suppliers)].id,
            expiry_date=exp,
            sku=f"SKU-{1000 + i}",
            created_by=admin.id,
            last_audit_date=date.today() - timedelta(days=30 + i),
        )
        session.add(it)
        items.append(it)
    session.flush()

    for idx, it in enumerate(items):
        batch = models.InventoryBatch(
            item_id=it.id,
            quantity_original=it.quantity_in_stock,
            quantity_remaining=it.quantity_in_stock,
            unit_cost=it.unit_cost,
            received_at=datetime.utcnow() - timedelta(days=60 - idx),
        )
        session.add(batch)
        session.flush()
        it.fifo_batch_id = batch.id
        session.add(
            models.StockTransaction(
                transaction_id=f"seed-recv-{it.id}",
                item_id=it.id,
                type=models.TransactionType.RECEIVE.value,
                quantity=it.quantity_in_stock,
                reference_number="SEED",
                performed_by=admin.id,
                timestamp=datetime.utcnow() - timedelta(days=60 - idx),
                batch_id=batch.id,
            )
        )
        if idx % 2 == 0:
            qty = min(5.0, max(it.quantity_in_stock * 0.02, 1.0))
            try:
                consume_fifo(session, it.id, qty)
                it.quantity_in_stock -= qty
                session.add(
                    models.StockTransaction(
                        transaction_id=f"seed-issue-{it.id}",
                        item_id=it.id,
                        type=models.TransactionType.ISSUE.value,
                        quantity=qty,
                        reference_number="SEED-ISSUE",
                        performed_by=admin.id,
                        timestamp=datetime.utcnow() - timedelta(days=20 + idx),
                        batch_id=batch.id,
                    )
                )
            except ValueError:
                pass

    for key, name, sev, days in (
        ("LOW_STOCK", "Low stock vs reorder point", models.AlertSeverity.WARNING.value, None),
        ("OUT_OF_STOCK", "Out of stock", models.AlertSeverity.CRITICAL.value, None),
        ("EXPIRY", "Expiry warning window", models.AlertSeverity.WARNING.value, 30),
        ("AUDIT_OVERDUE", "Audit overdue", models.AlertSeverity.INFO.value, 90),
        ("DEAD_STOCK", "Dead stock detection", models.AlertSeverity.INFO.value, 90),
    ):
        session.add(
            models.AlertRule(rule_key=key, name=name, enabled=True, threshold_days=days, severity=sev)
        )

    for k, v in (
        ("expiry_warning_days", "30"),
        ("audit_overdue_days", "60"),
        ("dead_stock_days", "60"),
        ("theme_default", "light"),
    ):
        session.add(models.SystemConfig(key=k, value=v))

    soap = session.scalar(select(models.InventoryItem).where(models.InventoryItem.item_id == "SKU-1005"))
    if soap:
        soap.quantity_in_stock = 0
        for b in session.scalars(select(models.InventoryBatch).where(models.InventoryBatch.item_id == soap.id)):
            b.quantity_remaining = 0


def seed_if_empty():
    # Schema initialization is the caller's responsibility — `app.py` invokes
    # `init_database()` on boot immediately before this function, so repeating
    # the reflection + CREATE-IF-NOT-EXISTS pass here is pure waste.
    mode = _seed_mode()
    with db_session() as session:
        if _is_minimal_mode(mode):
            ensure_minimal_reference(session)
            bootstrap_admin_from_env(session)
            session.commit()
            return
        if session.scalar(select(models.User).limit(1)):
            return
        _seed_demo_dataset(session)
        session.commit()
