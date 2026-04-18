"""Manager/admin: review clerk inventory submissions and approve with PIN."""

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate
from dash_ag_grid import AgGrid
from flask import session

from database.dal import (
    bulk_approve_inventory_change_requests,
    bulk_reject_inventory_change_requests,
    list_pending_inventory_change_requests,
)
from database.engine import db_session
from components.page import page_header
from utils import i18n
from utils.navigation import normalize_path

register_page(__name__, path="/approvals", name="Approvals", title="Approvals", order=25)

_apr_t, _apr_h = i18n.page_heading("en", "approvals")


def _ok():
    return session.get("role") in ("MANAGER", "ADMIN")


def _uid():
    return int(session.get("user_id") or 0)


COLS = [
    {
        "colId": "_select",
        "headerName": "",
        "checkboxSelection": True,
        "headerCheckboxSelection": True,
        "headerCheckboxSelectionFilteredOnly": True,
        "width": 52,
        "pinned": "left",
        "suppressMovable": True,
        "lockPosition": "left",
        "sortable": False,
        "filter": False,
    },
    {"field": "id", "headerName": "ID", "width": 70},
    {"field": "created_at", "headerName": "Submitted", "filter": True},
    {"field": "action", "headerName": "Action", "filter": True},
    {"field": "submitter", "headerName": "Clerk", "filter": True},
    {"field": "summary", "headerName": "Item / summary", "filter": True},
]


def _rows():
    with db_session() as s:
        return list_pending_inventory_change_requests(s)


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        dcc.Store(id="appr-version", data=0),
        dcc.Store(id="appr-intent", data=None),
        html.Div(id="approvals-page-header", children=page_header(_apr_t, help=_apr_h)),
        dmc.Paper(
            className="cpi-toolbar-paper",
            p="md",
            radius="md",
            withBorder=True,
            children=dmc.Stack(
                [
                    dmc.Group(
                        [
                            dmc.Button("Refresh", id="appr-refresh", variant="light"),
                            dmc.Button("Approve selected", id="appr-open-approve", color="cpi"),
                            dmc.Button("Reject selected", id="appr-open-reject", color="red", variant="light"),
                        ],
                        gap="sm",
                        wrap="wrap",
                        justify="flex-end",
                    ),
                    dmc.Text(
                        "Bulk: tick several rows (or the top-left header box for all visible rows on this page), enter your PIN once, and submit.",
                        size="sm",
                        c="dimmed",
                    ),
                ],
                gap="sm",
            ),
        ),
        AgGrid(
            id="appr-grid",
            columnDefs=COLS,
            rowData=[],
            defaultColDef={"resizable": True, "sortable": True, "filter": True},
            dashGridOptions={
                "pagination": True,
                "paginationPageSize": 12,
                "rowSelection": "multiple",
                "suppressRowClickSelection": True,
            },
            style={"height": "480px", "width": "100%"},
            className="ag-theme-alpine",
        ),
        html.Div(id="appr-feedback"),
        dmc.Modal(
            id="appr-modal",
            title="Confirm with approval PIN",
            opened=False,
            children=dmc.Stack(
                [
                    dmc.Text(
                        id="appr-modal-scope",
                        size="sm",
                        c="dimmed",
                        children="",
                    ),
                    dmc.PasswordInput(id="appr-pin", label="Approval PIN", required=True),
                    dmc.Textarea(
                        id="appr-reject-note",
                        label="Note (reject only)",
                        minRows=2,
                        placeholder="Optional reason for the clerk",
                    ),
                    dmc.Group(
                        [
                            dmc.Button("Submit", id="appr-confirm", color="cpi"),
                            dmc.Button("Cancel", id="appr-cancel", variant="default"),
                        ],
                        justify="flex-end",
                    ),
                ],
                gap="md",
            ),
        ),
    ],
)


@callback(
    Output("approvals-page-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def approvals_page_header(pathname, loc):
    if normalize_path(pathname) != "/approvals":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    t, h = i18n.page_heading(lang, "approvals")
    return page_header(t, help=h)


@callback(
    Output("appr-grid", "rowData"),
    Input("_pages_location", "pathname"),
    Input("appr-version", "data"),
)
def appr_load(pathname, _v):
    if "/approvals" not in (pathname or ""):
        raise PreventUpdate
    if not _ok():
        raise PreventUpdate
    return _rows()


@callback(
    Output("appr-modal", "opened"),
    Output("appr-intent", "data"),
    Output("appr-pin", "value"),
    Output("appr-reject-note", "value"),
    Output("appr-modal-scope", "children"),
    Input("appr-open-approve", "n_clicks"),
    Input("appr-open-reject", "n_clicks"),
    Input("appr-cancel", "n_clicks"),
    State("appr-grid", "selectedRows"),
    prevent_initial_call=True,
)
def appr_modal_open(na, nr, nc, selected):
    if not _ok():
        raise PreventUpdate
    tid = dash.callback_context.triggered_id
    if tid == "appr-cancel":
        return False, None, "", "", ""
    if not selected:
        raise PreventUpdate
    n = len(selected)
    scope = f"This will apply to {n} selected request{'s' if n != 1 else ''}."
    if tid == "appr-open-approve":
        return True, "approve", "", "", scope
    if tid == "appr-open-reject":
        return True, "reject", "", "", scope
    raise PreventUpdate


@callback(
    Output("appr-version", "data"),
    Output("appr-modal", "opened", allow_duplicate=True),
    Output("appr-feedback", "children"),
    Output("cpi-inventory-refresh", "data"),
    Input("appr-confirm", "n_clicks"),
    Input("appr-refresh", "n_clicks"),
    State("appr-version", "data"),
    State("appr-intent", "data"),
    State("appr-pin", "value"),
    State("appr-reject-note", "value"),
    State("appr-grid", "selectedRows"),
    prevent_initial_call=True,
)
def appr_apply(_conf, _ref, ver, intent, pin, note, selected):
    if not _ok():
        raise PreventUpdate
    tid = dash.callback_context.triggered_id
    v = (ver or 0) + 1
    if tid == "appr-refresh":
        return v, dash.no_update, "", dash.no_update
    if tid != "appr-confirm":
        raise PreventUpdate
    if not selected or not intent:
        return (ver or 0), True, dmc.Alert("Select at least one pending request.", color="yellow"), dash.no_update
    ids = sorted({int(r["id"]) for r in selected})
    uid = _uid()
    with db_session() as s:
        if intent == "approve":
            n_ok, n_fail, errs = bulk_approve_inventory_change_requests(
                s, request_ids=ids, approver_id=uid, pin_plain=pin or ""
            )
        elif intent == "reject":
            n_ok, n_fail, errs = bulk_reject_inventory_change_requests(
                s, request_ids=ids, approver_id=uid, pin_plain=pin or "", note=note
            )
        else:
            return (ver or 0), True, dmc.Alert("Invalid action.", color="red"), dash.no_update

    inv_tick = dash.no_update
    if intent == "approve" and n_ok > 0:
        inv_tick = (ver or 0) + 10000 + max(ids)

    if n_ok == len(ids) and n_fail == 0:
        verb = "Approved" if intent == "approve" else "Rejected"
        return v, False, dmc.Alert(f"{verb} {n_ok} request(s).", color="green", title="Done"), inv_tick
    if n_ok > 0:
        detail = " ".join(errs[:5]) + (" …" if len(errs) > 5 else "")
        return (
            v,
            False,
            dmc.Alert(
                f"Completed {n_ok} of {len(ids)}. {n_fail} failed. {detail}",
                color="yellow",
                title="Partial success",
            ),
            inv_tick,
        )
    err0 = errs[0] if errs else "Nothing was applied."
    return (ver or 0), True, dmc.Alert(err0, color="red", title="Could not complete"), dash.no_update

