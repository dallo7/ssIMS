"""REST API v1 for integrations / mobile clients.

Authentication
--------------
All endpoints except ``/health`` and ``/auth/login`` require:

    Authorization: Bearer <API_TOKEN>

You can get a token two ways:

1. POST ``/api/v1/auth/login`` with JSON ``{"username":"...","password":"..."}``.
   The server verifies the user, creates a new :class:`ApiToken` for that user
   and returns the plaintext token ONCE. Store it on the mobile client
   (keychain / encrypted storage).
2. From the admin UI -> Configuration -> API tokens (shown once on creation).

Tokens are long-lived. Call ``POST /api/v1/auth/logout`` from the client to
revoke the current token when the user signs out.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import select

from database import dal, models
from database.engine import db_session
from utils.app_text import api_service_slug
from utils.auth import verify_password

bp = Blueprint("cpi_api_v1", __name__)

# ---------------------------------------------------------------------------
# CORS (only matters for browser clients — mobile apps don't need it).
# ---------------------------------------------------------------------------


def _allowed_origins() -> set[str]:
    raw = (os.environ.get("CPI_API_CORS_ORIGINS") or "").strip()
    if not raw:
        return set()
    return {o.strip() for o in raw.split(",") if o.strip()}


@bp.after_request
def _add_cors_headers(resp: Response) -> Response:
    origin = (request.headers.get("Origin") or "").strip()
    allowed = _allowed_origins()
    if origin and (origin in allowed or "*" in allowed):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    return resp


@bp.route("/<path:_any>", methods=["OPTIONS"])
def _cors_preflight(_any: str):
    return ("", 204)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_error(message: str, code: int = 400):
    return jsonify({"error": message}), code


def _json_iso(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _auth_user_id() -> int | None:
    """Resolve the calling user from the ``Authorization: Bearer`` header."""
    auth = (request.headers.get("Authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return None
    raw = auth[7:].strip()
    if not raw:
        return None
    with db_session() as s:
        row = dal.verify_api_token_string(s, raw)
        if not row:
            return None
        return int(row.created_by)


def _require_auth():
    """Decorator-less guard: returns a (response, code) tuple or None if OK."""
    uid = _auth_user_id()
    if uid is None:
        return _json_error("Authorization: Bearer <token> required", 401)
    return uid


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


@bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": api_service_slug()})


@bp.post("/auth/login")
def login():
    """Exchange username+password for a long-lived bearer token.

    Request:  {"username": "...", "password": "...", "label": "iPhone 15"}
    Response: {"token": "...", "user": {...}}
    """
    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception:
        return _json_error("Invalid JSON", 400)
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    label = (body.get("label") or f"mobile-{datetime.utcnow():%Y%m%d-%H%M%S}").strip()
    if not username or not password:
        return _json_error("username and password required", 400)
    with db_session() as s:
        u = dal.get_user_by_username(s, username)
        if not u or not u.is_active or not verify_password(password, u.password_hash):
            return _json_error("Invalid credentials", 401)
        tok_row, plain = dal.create_api_token(s, user_id=int(u.id), label=label)
        role = s.get(models.Role, u.role_id)
        return jsonify(
            {
                "token": plain,
                "token_id": tok_row.id,
                "user": {
                    "id": u.id,
                    "username": u.username,
                    "full_name": u.full_name,
                    "role": role.name if role else None,
                },
            }
        )


@bp.post("/auth/logout")
def logout():
    """Revoke the token currently used to authenticate this request."""
    auth = (request.headers.get("Authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return _json_error("Authorization: Bearer <token> required", 401)
    raw = auth[7:].strip()
    with db_session() as s:
        row = dal.verify_api_token_string(s, raw)
        if not row:
            return _json_error("Invalid token", 401)
        dal.revoke_api_token(s, int(row.id), int(row.created_by))
    return jsonify({"ok": True})


@bp.get("/me")
def me():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    uid = guard
    with db_session() as s:
        u = s.get(models.User, uid)
        if not u:
            return _json_error("User not found", 404)
        role = s.get(models.Role, u.role_id)
        return jsonify(
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "role": role.name if role else None,
                "is_active": bool(u.is_active),
            }
        )


# ---------------------------------------------------------------------------
# Items / inventory
# ---------------------------------------------------------------------------


def _item_to_dict(it: models.InventoryItem) -> dict[str, Any]:
    return {
        "id": it.id,
        "item_id": it.item_id,
        "name": it.name,
        "sku": it.sku,
        "barcode": it.barcode,
        "description": it.description,
        "category_id": it.category_id,
        "unit_of_measure_id": it.unit_of_measure_id,
        "quantity_in_stock": float(it.quantity_in_stock or 0),
        "reorder_point": float(it.reorder_point or 0),
        "reorder_quantity": float(it.reorder_quantity or 0),
        "unit_cost": float(it.unit_cost or 0),
        "unit_price": float(it.unit_price or 0),
        "storage_location_id": it.storage_location_id,
        "supplier_id": it.supplier_id,
        "is_active": bool(it.is_active),
    }


@bp.get("/items")
def list_items():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    q = (request.args.get("q") or "").strip() or None
    active_only = (request.args.get("active") or "1").strip() != "0"
    with db_session() as s:
        items = dal.list_items(s, active_only=active_only, search=q)
        return jsonify({"items": [_item_to_dict(it) for it in items]})


@bp.get("/items/<int:pk>")
def one_item(pk: int):
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    with db_session() as s:
        it = dal.get_item(s, pk)
        if not it:
            return _json_error("Not found", 404)
        loc_rows = []
        for ils, loc in s.execute(
            select(models.ItemLocationStock, models.StorageLocation)
            .join(
                models.StorageLocation,
                models.StorageLocation.id == models.ItemLocationStock.storage_location_id,
            )
            .where(models.ItemLocationStock.item_id == pk)
        ):
            loc_rows.append(
                {
                    "location_id": loc.id,
                    "location_name": loc.name,
                    "warehouse": loc.warehouse,
                    "quantity": float(ils.quantity or 0),
                }
            )
        out = _item_to_dict(it)
        out["by_location"] = loc_rows
        return jsonify(out)


@bp.get("/stock-by-location")
def stock_by_location():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    with db_session() as s:
        rows = dal.list_item_location_stock_matrix(s)
    return jsonify({"rows": rows})


# ---------------------------------------------------------------------------
# Reference data (categories, storage locations, suppliers, customers)
# ---------------------------------------------------------------------------


@bp.get("/categories")
def list_categories():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    with db_session() as s:
        rows = dal.list_categories(s)
        return jsonify(
            {
                "categories": [
                    {"id": c.id, "name": c.name, "abc_class": c.abc_class} for c in rows
                ]
            }
        )


@bp.get("/storage-locations")
def list_storage_locations():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    with db_session() as s:
        rows = dal.list_storage_locations(s)
        return jsonify(
            {
                "storage_locations": [
                    {
                        "id": sl.id,
                        "name": sl.name,
                        "zone": sl.zone,
                        "warehouse": sl.warehouse,
                    }
                    for sl in rows
                ]
            }
        )


def _supplier_to_dict(sp: models.Supplier) -> dict[str, Any]:
    return {
        "id": sp.id,
        "name": sp.name,
        "contact_person": sp.contact_person,
        "phone": sp.phone,
        "email": sp.email,
        "address": sp.address,
        "country": sp.country,
        "payment_terms": sp.payment_terms,
        "lead_time_days": sp.lead_time_days,
        "rating": float(sp.rating or 0),
        "is_active": bool(sp.is_active),
    }


@bp.get("/suppliers")
def list_suppliers():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    active_only = (request.args.get("active") or "1").strip() != "0"
    with db_session() as s:
        rows = dal.list_suppliers(s, active_only=active_only)
        return jsonify({"suppliers": [_supplier_to_dict(x) for x in rows]})


@bp.post("/suppliers")
def create_supplier():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    uid = guard
    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception:
        return _json_error("Invalid JSON", 400)
    name = (body.get("name") or "").strip()
    if not name:
        return _json_error("name required", 400)
    with db_session() as s:
        sp = dal.create_supplier(
            s,
            user_id=uid,
            name=name,
            contact_person=body.get("contact_person"),
            phone=body.get("phone"),
            email=body.get("email"),
            address=body.get("address"),
            country=(body.get("country") or "").strip(),
            payment_terms=body.get("payment_terms"),
            lead_time_days=int(body.get("lead_time_days") or 7),
        )
        return jsonify(_supplier_to_dict(sp)), 201


def _customer_to_dict(c: models.Customer) -> dict[str, Any]:
    return {
        "id": c.id,
        "customer_code": c.customer_code,
        "name": c.name,
        "phone": c.phone,
        "email": c.email,
        "address": c.address,
        "country": c.country,
        "is_active": bool(c.is_active),
    }


@bp.get("/customers")
def list_customers():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    active_only = (request.args.get("active") or "1").strip() != "0"
    with db_session() as s:
        rows = dal.list_customers(s, active_only=active_only)
        return jsonify({"customers": [_customer_to_dict(x) for x in rows]})


@bp.post("/customers")
def create_customer():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    uid = guard
    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception:
        return _json_error("Invalid JSON", 400)
    name = (body.get("name") or "").strip()
    if not name:
        return _json_error("name required", 400)
    with db_session() as s:
        c = dal.create_customer(
            s,
            user_id=uid,
            name=name,
            phone=body.get("phone"),
            email=body.get("email"),
            address=body.get("address"),
            country=(body.get("country") or "").strip(),
        )
        return jsonify(_customer_to_dict(c)), 201


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@bp.get("/alerts")
def list_alerts():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    try:
        limit = int(request.args.get("limit") or 100)
    except ValueError:
        limit = 100
    limit = max(1, min(limit, 500))
    with db_session() as s:
        rows = dal.list_alerts_with_ack_state(s, limit=limit)
    out = []
    for r in rows:
        d = dict(r)
        d["created_at"] = _json_iso(d.get("created_at"))
        out.append(d)
    return jsonify({"alerts": out})


# ---------------------------------------------------------------------------
# Sales orders
# ---------------------------------------------------------------------------


@bp.get("/sales-orders")
def list_sales_orders():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    try:
        limit = int(request.args.get("limit") or 100)
    except ValueError:
        limit = 100
    limit = max(1, min(limit, 500))
    with db_session() as s:
        rows = dal.list_sales_orders(s, limit=limit)
        out = []
        for so in rows:
            out.append(
                {
                    "id": so.id,
                    "so_number": so.so_number,
                    "customer_id": so.customer_id,
                    "status": so.status,
                    "order_date": _json_iso(so.order_date),
                    "created_at": _json_iso(so.created_at),
                    "notes": so.notes,
                }
            )
        return jsonify({"sales_orders": out})


@bp.post("/sales-orders")
def post_sales_order():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    uid = guard
    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception:
        return _json_error("Invalid JSON", 400)
    cid = body.get("customer_id")
    lines = body.get("lines") or []
    if not cid or not lines:
        return _json_error("customer_id and lines[] required", 400)
    notes = body.get("notes")
    with db_session() as s:
        try:
            so = dal.create_sales_order_draft(
                s, customer_id=int(cid), created_by=uid, notes=notes
            )
            for ln in lines:
                dal.add_sales_order_line(
                    s,
                    so_pk=so.id,
                    item_id=int(ln["item_id"]),
                    qty=float(ln.get("quantity_ordered", ln.get("qty", 0))),
                    unit_price=float(ln.get("unit_price", 0)),
                )
            ok, msg = dal.confirm_sales_order(s, so.id, uid)
            if not ok:
                raise ValueError(msg)
        except Exception as e:
            return _json_error(str(e), 400)
        return (
            jsonify({"so_number": so.so_number, "id": so.id, "status": so.status}),
            201,
        )


# ---------------------------------------------------------------------------
# Stock movements
# ---------------------------------------------------------------------------


@bp.post("/movements/issue")
def post_issue():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    uid = guard
    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception:
        return _json_error("Invalid JSON", 400)
    item_id = body.get("item_id")
    qty = body.get("quantity")
    if item_id is None or qty is None:
        return _json_error("item_id and quantity required", 400)
    ref = body.get("reference_number")
    loc = body.get("storage_location_id")
    with db_session() as s:
        try:
            dal.issue_stock_fifo(
                s,
                item_id=int(item_id),
                quantity=float(qty),
                performed_by=uid,
                reference_number=ref,
                notes=body.get("notes") or "API issue",
                storage_location_id=int(loc) if loc is not None else None,
            )
        except Exception as e:
            return _json_error(str(e), 400)
    return jsonify({"ok": True})


@bp.post("/movements/receive")
def post_receive():
    guard = _require_auth()
    if isinstance(guard, tuple):
        return guard
    uid = guard
    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception:
        return _json_error("Invalid JSON", 400)
    item_id = body.get("item_id")
    qty = body.get("quantity")
    unit_cost = body.get("unit_cost")
    if item_id is None or qty is None or unit_cost is None:
        return _json_error("item_id, quantity and unit_cost required", 400)
    loc = body.get("storage_location_id")
    with db_session() as s:
        try:
            batch, txn = dal.receive_stock(
                s,
                item_id=int(item_id),
                quantity=float(qty),
                unit_cost=float(unit_cost),
                performed_by=uid,
                reference_number=body.get("reference_number"),
                notes=body.get("notes") or "API receive",
                storage_location_id=int(loc) if loc is not None else None,
            )
        except Exception as e:
            return _json_error(str(e), 400)
        return (
            jsonify(
                {
                    "ok": True,
                    "batch_id": batch.id,
                    "transaction_id": txn.id,
                    "quantity_remaining": float(batch.quantity_remaining or 0),
                }
            ),
            201,
        )
