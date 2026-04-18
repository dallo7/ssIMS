"""Display names for shell, browser title, and exports (production vs development)."""
from __future__ import annotations

import os

from utils.server_config import is_production_env

_DEV_NAME = "Smart-Shop Stock Inventory"
_PROD_NAME = "Inventory"


def primary_app_name() -> str:
    """Browser title, PDF headers, API metadata when CPI_APP_TITLE is unset."""
    custom = (os.environ.get("CPI_APP_TITLE") or "").strip()
    if custom:
        return custom
    return _PROD_NAME if is_production_env() else _DEV_NAME


def api_service_slug() -> str:
    return (os.environ.get("CPI_API_SERVICE_NAME") or "inventory-api").strip() or "inventory-api"
