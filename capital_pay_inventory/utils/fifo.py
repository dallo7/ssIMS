"""FIFO consumption helpers for issuing stock."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import models


def list_batches_fifo(session: Session, item_id: int) -> list[models.InventoryBatch]:
    q = (
        select(models.InventoryBatch)
        .where(
            models.InventoryBatch.item_id == item_id,
            models.InventoryBatch.quantity_remaining > 0,
        )
        .order_by(models.InventoryBatch.received_at.asc(), models.InventoryBatch.id.asc())
    )
    return list(session.scalars(q).all())


def consume_fifo(
    session: Session, item_id: int, qty: float
) -> list[tuple[models.InventoryBatch, float]]:
    """
    Returns list of (batch, qty_taken) for recording per-batch transactions.
    Raises ValueError if insufficient stock.
    """
    remaining = qty
    out: list[tuple[models.InventoryBatch, float]] = []
    for b in list_batches_fifo(session, item_id):
        if remaining <= 0:
            break
        take = min(b.quantity_remaining, remaining)
        b.quantity_remaining -= take
        remaining -= take
        out.append((b, take))
    if remaining > 1e-9:
        raise ValueError("Insufficient stock for FIFO issue.")
    return out
