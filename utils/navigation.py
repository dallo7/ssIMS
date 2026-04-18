"""Role-based navigation: each user sees only pages relevant to their role."""
from __future__ import annotations

from typing import Any

from utils import i18n

# Paths must match register_page(..., path=...) values
NAV_ENTRIES: list[dict[str, Any]] = [
    {
        "path": "/",
        "label": "Dashboard",
        "icon": "tabler:layout-dashboard",
        "section": "Overview",
        "roles": frozenset({"ADMIN", "MANAGER", "STOCK_CLERK", "VIEWER"}),
    },
    {
        "path": "/inventory",
        "label": "Inventory",
        "icon": "tabler:packages",
        "section": "Operations",
        "roles": frozenset({"ADMIN", "MANAGER", "STOCK_CLERK"}),
    },
    {
        "path": "/approvals",
        "label": "Approvals",
        "icon": "tabler:circle-check",
        "section": "Operations",
        "roles": frozenset({"ADMIN", "MANAGER"}),
    },
    {
        "path": "/movements",
        "label": "Movements",
        "icon": "tabler:arrows-exchange",
        "section": "Operations",
        "roles": frozenset({"ADMIN", "MANAGER", "STOCK_CLERK"}),
    },
    {
        "path": "/purchase-orders",
        "label": "Purchase orders",
        "icon": "tabler:shopping-cart",
        "section": "Operations",
        "roles": frozenset({"ADMIN", "MANAGER", "STOCK_CLERK"}),
    },
    {
        "path": "/suppliers",
        "label": "Suppliers",
        "icon": "tabler:truck-delivery",
        "section": "Operations",
        "roles": frozenset({"ADMIN", "MANAGER", "STOCK_CLERK"}),
    },
    {
        "path": "/customers",
        "label": "Customers",
        "icon": "tabler:users-group",
        "section": "Operations",
        "roles": frozenset({"ADMIN", "MANAGER", "STOCK_CLERK", "VIEWER"}),
    },
    {
        "path": "/sales-orders",
        "label": "Sales orders",
        "icon": "tabler:shopping-cart",
        "section": "Operations",
        "roles": frozenset({"ADMIN", "MANAGER", "STOCK_CLERK", "VIEWER"}),
    },
    {
        "path": "/locations",
        "label": "Locations",
        "icon": "tabler:building-warehouse",
        "section": "Operations",
        "roles": frozenset({"ADMIN", "MANAGER", "STOCK_CLERK", "VIEWER"}),
    },
    {
        "path": "/kits-bom",
        "label": "Kits & BOM",
        "icon": "tabler:packages",
        "section": "Operations",
        "roles": frozenset({"ADMIN", "MANAGER", "STOCK_CLERK", "VIEWER"}),
    },
    {
        "path": "/auditing",
        "label": "Auditing",
        "icon": "tabler:clipboard-check",
        "section": "Operations",
        "roles": frozenset({"ADMIN", "MANAGER", "STOCK_CLERK"}),
    },
    {
        "path": "/reports",
        "label": "Reports",
        "icon": "tabler:report-analytics",
        "section": "Insights",
        "roles": frozenset({"ADMIN", "MANAGER", "STOCK_CLERK", "VIEWER"}),
    },
    {
        "path": "/monitoring",
        "label": "Alerts",
        "icon": "tabler:bell-ringing",
        "section": "Insights",
        "roles": frozenset({"ADMIN", "MANAGER", "STOCK_CLERK", "VIEWER"}),
    },
    {
        "path": "/users",
        "label": "Users",
        "icon": "tabler:users",
        "section": "Administration",
        "roles": frozenset({"ADMIN"}),
    },
    {
        "path": "/config",
        "label": "Configuration",
        "icon": "tabler:settings",
        "section": "Administration",
        "roles": frozenset({"ADMIN", "MANAGER"}),
    },
]


def normalize_path(pathname: str | None) -> str:
    p = (pathname or "/").strip()
    if not p:
        return "/"
    p = p.rstrip("/") or "/"
    return p


def allowed_paths_for_role(role: str | None) -> frozenset[str]:
    r = role or "VIEWER"
    return frozenset(e["path"] for e in NAV_ENTRIES if r in e["roles"])


def can_access_path(role: str | None, pathname: str | None) -> bool:
    p = normalize_path(pathname)
    if p == "/login":
        return True
    allowed = allowed_paths_for_role(role)
    return p in allowed


# Stock clerks: plain-language labels, task-first ordering, fewer abstract section names.
_CLERK_NAV_LABELS: dict[str, str] = {
    "/": "Home",
    "/inventory": "Stock list",
    "/movements": "Stock in / out",
    "/purchase-orders": "Orders to suppliers",
    "/suppliers": "Suppliers",
    "/customers": "Customers",
    "/sales-orders": "Sales orders",
    "/locations": "Bin locations",
    "/kits-bom": "Kits / BOM",
    "/auditing": "Shelf counts",
    "/reports": "Printed summaries",
    "/monitoring": "Alerts",
}
_CLERK_NAV_SECTIONS: dict[str, str] = {
    "/": "Every day",
    "/inventory": "Every day",
    "/movements": "Every day",
    "/purchase-orders": "When needed",
    "/suppliers": "When needed",
    "/customers": "When needed",
    "/sales-orders": "When needed",
    "/locations": "When needed",
    "/kits-bom": "When needed",
    "/auditing": "When needed",
    "/reports": "When needed",
    "/monitoring": "When needed",
}
_CLERK_NAV_ORDER: list[str] = [
    "/",
    "/inventory",
    "/movements",
    "/purchase-orders",
    "/suppliers",
    "/customers",
    "/sales-orders",
    "/locations",
    "/kits-bom",
    "/auditing",
    "/reports",
    "/monitoring",
]


def _with_clerk_friendly_nav(entries: list[dict[str, Any]], lang: str) -> list[dict[str, Any]]:
    order = {p: i for i, p in enumerate(_CLERK_NAV_ORDER)}
    out: list[dict[str, Any]] = []
    for e in entries:
        e2 = dict(e)
        p = e2["path"]
        if p in _CLERK_NAV_LABELS:
            e2["label"] = i18n.clerk_link_label(p, lang)
        if p in _CLERK_NAV_SECTIONS:
            sec = _CLERK_NAV_SECTIONS[p]
            e2["section"] = i18n.nav_section_label(sec, lang)
        out.append(e2)
    out.sort(key=lambda x: order.get(x["path"], 999))
    return out


def nav_entries_for_role(role: str | None, lang: str = "en") -> list[dict[str, Any]]:
    r = role or "VIEWER"
    raw = [dict(e) for e in NAV_ENTRIES if r in e["roles"]]
    if r == "STOCK_CLERK":
        return _with_clerk_friendly_nav(raw, lang)
    out = []
    for e in raw:
        e2 = dict(e)
        e2["label"] = i18n.nav_link_label(e2["path"], e2["label"], lang)
        e2["section"] = i18n.nav_section_label(e2["section"], lang)
        out.append(e2)
    return out


def role_workspace_label(role: str | None) -> str:
    return {
        "VIEWER": "Read-only",
        "STOCK_CLERK": "Stock desk",
        "MANAGER": "Management",
        "ADMIN": "Administrator",
    }.get(role or "VIEWER", "Workspace")


def role_short_label(role: str | None) -> str:
    """Human-readable role for the sidebar (avoids codes like STOCK_CLERK)."""
    return {
        "VIEWER": "Viewer",
        "STOCK_CLERK": "Stock clerk",
        "MANAGER": "Manager",
        "ADMIN": "Administrator",
    }.get(role or "VIEWER", role or "User")
