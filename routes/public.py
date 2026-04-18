"""Public, Dash-free routes for /welcome and /login.

These two pages used to be Dash pages, which meant every visit forced
the browser to download the full Dash SPA bundle (Mantine, AgGrid,
dash-renderer, React 18, plotly's component runtime). For unauthenticated
visitors that's roughly a megabyte of JS and a noticeable cold-start —
all to render a marketing page and a login form that need none of it.

Serving them as plain Flask + Jinja makes the first paint near-instant:
~12 KB of HTML, one cached stylesheet, no JS bundle. The Dash SPA still
serves every authenticated page (dashboard, movements, …) — only the
public surface is short-circuited here.
"""
from __future__ import annotations

from typing import Any

from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import select

from database import models
from database.dal import insert_activity_log
from database.engine import db_session
from utils import i18n
from utils.app_text import primary_app_name
from utils.auth import login_user, verify_password


bp = Blueprint("public", __name__)


# Languages exposed in the picker on these pages. Mirrors i18n.LANG_SELECT_DATA
# but kept as a tuple of (code, label) for cheap iteration in Jinja.
_LANG_CHOICES: tuple[tuple[str, str], ...] = tuple(
    (entry["value"], entry["label"]) for entry in i18n.LANG_SELECT_DATA
)


def _resolve_lang() -> str:
    """Pick the active language for this public page.

    Order of precedence:
      1. ``?lang=`` query string (set by the language switcher).
      2. The current Flask session value (rare, but stays sticky).
      3. ``en`` fallback.
    """
    candidate = (
        request.args.get("lang")
        or request.form.get("lang")
        or session.get("lang")
        or "en"
    )
    return i18n.normalize_lang({"lang": candidate})


# i18n bundle for the welcome page. Kept inline rather than added to
# utils/i18n.py so the public surface owns its own copy that stays
# tweakable without dragging the whole translation table along.
_WELCOME_I18N: dict[str, dict[str, str]] = {
    "eyebrow": {
        "en": "Inventory OS for growing businesses",
        "ar": "نظام إدارة مخزون للشركات النامية",
        "juba": "نظام مخزون لشركتك",
        "din": "Inventory OS for growing businesses",
    },
    "title_part1": {
        "en": "Run your stockroom ",
        "ar": "أدِر مخزنك ",
        "juba": "ادير المخزن بتاعك ",
        "din": "Run your stockroom ",
    },
    "title_accent": {
        "en": "with confidence",
        "ar": "بكل ثقة",
        "juba": "بدون قلق",
        "din": "with confidence",
    },
    "lead": {
        "en": (
            "Real-time inventory, multi-warehouse visibility, and intelligent "
            "alerts in one elegant workspace. Built for the shop floor, scaled "
            "for the boardroom."
        ),
        "ar": (
            "مخزون في الوقت الحقيقي، رؤية موحّدة للمستودعات، وتنبيهات ذكية "
            "في مساحة عمل واحدة أنيقة."
        ),
        "juba": (
            "مخزون لايف، شوف كل المخازن في مكان واحد، مع تنبيهات ذكية."
        ),
        "din": (
            "Real-time inventory, multi-warehouse visibility, and smart alerts."
        ),
    },
    "cta_primary": {"en": "Get started", "ar": "ابدأ الآن", "juba": "ابدأ", "din": "Get started"},
    "signin": {"en": "Sign in", "ar": "تسجيل الدخول", "juba": "ادخل", "din": "Sign in"},
    "snapshot": {"en": "Today's snapshot", "ar": "لقطة اليوم", "juba": "ملخص اليوم", "din": "Today's snapshot"},
    "live": {"en": "Live", "ar": "مباشر", "juba": "لايف", "din": "Live"},
    "chip_low": {"en": "Low stock", "ar": "مخزون منخفض", "juba": "مخزون قليل", "din": "Low stock"},
    "how_eyebrow": {"en": "How it works", "ar": "كيف يعمل", "juba": "كيف يشتغل", "din": "How it works"},
    "how_title": {
        "en": "From first click to first insight in under a minute.",
        "ar": "من النقرة الأولى إلى أول رؤية في أقل من دقيقة.",
        "juba": "من أول كلك لحدي أول معلومة في دقيقة.",
        "din": "From first click to first insight in under a minute.",
    },
    "cta_title": {
        "en": "Ready to take control of your inventory?",
        "ar": "هل أنت جاهز للسيطرة على مخزونك؟",
        "juba": "جاهز تتحكم في مخزونك؟",
        "din": "Ready to take control of your inventory?",
    },
    "cta_subtitle": {
        "en": "Sign in to your workspace and see today's numbers in seconds.",
        "ar": "سجّل الدخول إلى مساحة عملك واطّلع على أرقام اليوم في ثوانٍ.",
        "juba": "ادخل لمساحتك وشوف أرقام اليوم في ثواني.",
        "din": "Sign in to your workspace and see today's numbers in seconds.",
    },
    "cta_button": {"en": "Sign in to continue", "ar": "تسجيل الدخول للمتابعة", "juba": "ادخل للمواصلة", "din": "Sign in to continue"},
    "rights": {"en": "All rights reserved.", "ar": "جميع الحقوق محفوظة.", "juba": "كل الحقوق محفوظة.", "din": "All rights reserved."},
}


_STEPS_I18N: dict[str, list[dict[str, str]]] = {
    "en": [
        {"n": "01", "title": "Sign in securely", "body": "Use your issued credentials. Sessions are server-side with full audit trail."},
        {"n": "02", "title": "Move stock in and out", "body": "Receive from suppliers, pick for sales orders, transfer between warehouses — all with two clicks."},
        {"n": "03", "title": "Act on insights", "body": "Dashboards, reports and alerts bring the right number in front of the right person at the right time."},
    ],
    "ar": [
        {"n": "01", "title": "تسجيل دخول آمن", "body": "استخدم بيانات الاعتماد الممنوحة لك. الجلسات تُدار من الخادم مع سجل تدقيق كامل."},
        {"n": "02", "title": "إدخال وإخراج المخزون", "body": "استلام من الموردين، تجهيز أوامر البيع، والتحويل بين المستودعات بنقرتين."},
        {"n": "03", "title": "اتخاذ قرارات مدروسة", "body": "لوحات وتقارير وتنبيهات توصل المعلومة الصحيحة للشخص المناسب في الوقت المناسب."},
    ],
    "juba": [
        {"n": "01", "title": "ادخل بأمان", "body": "استعمل بياناتك. الجلسة في السيرفر مع تسجيل كامل."},
        {"n": "02", "title": "ادخل وطلع المخزون", "body": "استلم من المورد، حضر أمر البيع، وحول بين المخازن بكليكين."},
        {"n": "03", "title": "اشتغل على المعلومة", "body": "لوحات وتقارير وتنبيهات تجيب الرقم الصح للشخص الصح في الوقت الصح."},
    ],
    "din": [
        {"n": "01", "title": "Sign in securely", "body": "Use your issued credentials. Sessions are server-side with full audit trail."},
        {"n": "02", "title": "Move stock in and out", "body": "Receive from suppliers, pick for sales orders, transfer between warehouses."},
        {"n": "03", "title": "Act on insights", "body": "Dashboards, reports and alerts deliver the right number to the right person."},
    ],
}


_SNAPSHOT_LABELS: dict[str, dict[str, str]] = {
    "stock_value": {"en": "Stock value", "ar": "قيمة المخزون", "juba": "قيمة المخزون", "din": "Stock value"},
    "skus": {"en": "SKUs tracked", "ar": "أصناف متتبعة", "juba": "الأصناف", "din": "SKUs tracked"},
    "alerts": {"en": "Open alerts", "ar": "تنبيهات مفتوحة", "juba": "تنبيهات مفتوحة", "din": "Open alerts"},
    "warehouses": {"en": "Warehouses", "ar": "المستودعات", "juba": "المخازن", "din": "Warehouses"},
}


def _bundle(table: dict[str, dict[str, str]], lang: str) -> dict[str, str]:
    return {key: row.get(lang, row.get("en", key)) for key, row in table.items()}


def _icon_svg(name: str) -> str:
    """Inline SVGs to avoid pulling tabler-icons over HTTP for 4 glyphs."""
    common = (
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" width="18" height="18" viewBox="0 0 24 24"'
    )
    if name == "wallet":
        return f'<svg {common}><path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/></svg>'
    if name == "packages":
        return f'<svg {common}><path d="M16.5 9.4 7.55 4.24"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>'
    if name == "bell":
        return f'<svg {common}><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>'
    if name == "warehouse":
        return f'<svg {common}><path d="M3 21V8l9-5 9 5v13"/><path d="M9 21v-6h6v6"/><path d="M3 9h18"/></svg>'
    return ""


@bp.route("/welcome", methods=["GET"])
def welcome():
    """Public landing page. No Dash bundle, no JS bundle."""
    # If the visitor is already signed in, skip the marketing page and
    # send them straight to the dashboard.
    if session.get("user_id"):
        return redirect("/")

    lang = _resolve_lang()
    snapshot_labels = _bundle(_SNAPSHOT_LABELS, lang)
    snapshot_rows = [
        {"label": snapshot_labels["stock_value"], "value": "$128,430", "icon": _icon_svg("wallet")},
        {"label": snapshot_labels["skus"], "value": "1,842", "icon": _icon_svg("packages")},
        {"label": snapshot_labels["alerts"], "value": "3", "icon": _icon_svg("bell")},
        {"label": snapshot_labels["warehouses"], "value": "6", "icon": _icon_svg("warehouse")},
    ]
    return render_template(
        "welcome.html",
        title=primary_app_name(),
        app_name=primary_app_name(),
        lang=lang,
        dir=i18n.text_direction(lang),
        languages=_LANG_CHOICES,
        t=_bundle(_WELCOME_I18N, lang),
        steps=_STEPS_I18N.get(lang, _STEPS_I18N["en"]),
        snapshot_rows=snapshot_rows,
    )


def _login_render(lang: str, *, error: str | None = None, status: int = 200) -> Any:
    next_path = request.values.get("next") or ""
    # Only honour relative paths to defend against open-redirect.
    if next_path and (not next_path.startswith("/") or next_path.startswith("//")):
        next_path = ""
    payload = {
        "title": i18n.login_txt(lang, "title"),
        "tagline": i18n.login_txt(lang, "tagline"),
        "user_label": i18n.login_txt(lang, "user_label"),
        "pass_label": i18n.login_txt(lang, "pass_label"),
        "pass_ph": i18n.login_txt(lang, "pass_ph"),
        "signin": i18n.login_txt(lang, "signin"),
    }
    response = render_template(
        "login.html",
        title=i18n.login_txt(lang, "title"),
        lang=lang,
        dir=i18n.text_direction(lang),
        languages=_LANG_CHOICES,
        t=payload,
        error=error,
        next_path=next_path,
    )
    return (response, status) if status != 200 else response


@bp.route("/login", methods=["GET"])
def login_get():
    """Static login form. Already-authenticated users are bounced to /."""
    if session.get("user_id"):
        return redirect("/")
    return _login_render(_resolve_lang())


@bp.route("/login", methods=["POST"])
def login_post():
    """Validate credentials and start a session — no Dash callback round-trip."""
    lang = _resolve_lang()
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    if not username or not password:
        return _login_render(lang, error=i18n.login_txt(lang, "err_required"), status=400)

    with db_session() as s:
        user = s.scalar(select(models.User).where(models.User.username == username))
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            return _login_render(lang, error=i18n.login_txt(lang, "err_invalid"), status=401)
        role = s.get(models.Role, user.role_id)
        insert_activity_log(
            s,
            user_id=user.id,
            action="LOGIN",
            entity_type="session",
            entity_id=str(user.id),
            ip_address=(request.remote_addr or None),
        )
        # Capture before the session closes — no detached-instance traps.
        user_id = int(user.id)
        username_val = user.username
        full_name = user.full_name
        role_name = role.name if role else "VIEWER"

    login_user(user_id, username_val, role_name, full_name)
    # Remember the language so subsequent public pages keep it sticky.
    session["lang"] = lang

    next_path = request.form.get("next") or ""
    if not next_path or not next_path.startswith("/") or next_path.startswith("//"):
        next_path = "/"
    return redirect(next_path)
