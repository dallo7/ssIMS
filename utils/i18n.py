"""UI strings for English, Arabic, Juba Arabic, and Dinka."""
from __future__ import annotations

from typing import Any

# Locale codes: en, ar (MSA UI), juba (Juba Arabic — colloquial Arabic script), din (Dinka bundle)
LANG_CODES = ("en", "ar", "juba", "din")

LANG_SELECT_DATA: list[dict[str, str]] = [
    {"label": "English", "value": "en"},
    {"label": "العربية", "value": "ar"},
    {"label": "عربي جوبا (Juba Arabic)", "value": "juba"},
    {"label": "Thuɔŋjäŋ (Dinka)", "value": "din"},
]


def normalize_lang(data: dict[str, Any] | None) -> str:
    lang = (data or {}).get("lang", "en")
    return lang if lang in LANG_CODES else "en"


def text_direction(lang: str) -> str:
    return "rtl" if lang in ("ar", "juba") else "ltr"


# --- App chrome ---
_CHROME: dict[str, dict[str, str]] = {
    "header_title": {
        "en": "Smart-Shop Stock Inventory",
        "ar": "سمارت-شوب — مخزون المحل",
        "juba": "سمارت-شوب — مخزون المحل",
        "din": "Smart-Shop Stock Inventory",
    },
    "powered_by": {
        "en": "Powered by CapitalPay",
        "ar": "مدعوم من كابيتال‌باي",
        "juba": "مدعوم من كابيتال‌باي",
        "din": "Powered by CapitalPay",
    },
    "logout": {
        "en": "Log out",
        "ar": "تسجيل الخروج",
        "juba": "اطلع من الحساب",
        "din": "Log out",
    },
    "sidebar_brand": {
        "en": "Smart-Shop",
        "ar": "سمارت-شوب",
        "juba": "سمارت-شوب",
        "din": "Smart-Shop",
    },
    "sidebar_tag": {
        "en": "Stock inventory management",
        "ar": "إدارة مخزون المحل",
        "juba": "إدارة مخزون المحل",
        "din": "Stock inventory management",
    },
    "sidebar_alerts": {
        "en": "Alerts",
        "ar": "التنبيهات",
        "juba": "التنبيهات",
        "din": "Alerts",
    },
    "sidebar_no_pages": {
        "en": "No pages assigned.",
        "ar": "لا توجد صفحات مخصصة.",
        "juba": "ما في صفحات محددة ليك.",
        "din": "No pages assigned.",
    },
    "role_prefix": {
        "en": "Role",
        "ar": "الدور",
        "juba": "الدور",
        "din": "Role",
    },
}

_WORKSPACE = {
    "VIEWER": {"en": "Read-only", "ar": "قراءة فقط", "juba": "بس تقرى", "din": "Read-only"},
    "STOCK_CLERK": {"en": "Stock desk", "ar": "مكتب المخزون", "juba": "شغل المخزون", "din": "Stock desk"},
    "MANAGER": {"en": "Management", "ar": "الإدارة", "juba": "الإدارة", "din": "Management"},
    "ADMIN": {"en": "Administrator", "ar": "مسؤول النظام", "juba": "مسؤول النظام", "din": "Administrator"},
}

_ROLE_SHORT = {
    "VIEWER": {"en": "Viewer", "ar": "مشاهد", "juba": "بشوف بس", "din": "Viewer"},
    "STOCK_CLERK": {"en": "Stock clerk", "ar": "أمين مخزون", "juba": "أمين مخزون", "din": "Stock clerk"},
    "MANAGER": {"en": "Manager", "ar": "مدير", "juba": "مدير", "din": "Manager"},
    "ADMIN": {"en": "Administrator", "ar": "مسؤول", "juba": "مسؤول", "din": "Administrator"},
}

# Standard nav (non-clerk): path -> lang -> label
_NAV: dict[str, dict[str, str]] = {
    "/": {"en": "Dashboard", "ar": "لوحة المعلومات", "juba": "اللوحة", "din": "Dashboard"},
    "/inventory": {"en": "Inventory", "ar": "المخزون", "juba": "المخزون", "din": "Inventory"},
    "/approvals": {"en": "Approvals", "ar": "الموافقات", "juba": "الموافقات", "din": "Approvals"},
    "/movements": {"en": "Movements", "ar": "الحركات", "juba": "الحركات", "din": "Movements"},
    "/purchase-orders": {"en": "Purchase orders", "ar": "أوامر الشراء", "juba": "أوامر الشراء", "din": "Purchase orders"},
    "/suppliers": {"en": "Suppliers", "ar": "الموردون", "juba": "الموردين", "din": "Suppliers"},
    "/auditing": {"en": "Auditing", "ar": "الجرد", "juba": "الجرد", "din": "Auditing"},
    "/reports": {"en": "Reports", "ar": "التقارير", "juba": "التقارير", "din": "Reports"},
    "/monitoring": {"en": "Alerts", "ar": "التنبيهات", "juba": "التنبيهات", "din": "Alerts"},
    "/users": {"en": "Users", "ar": "المستخدمون", "juba": "الناس المستخدمين", "din": "Users"},
    "/config": {"en": "Configuration", "ar": "الإعدادات", "juba": "الضبط", "din": "Configuration"},
    "/customers": {"en": "Customers", "ar": "العملاء", "juba": "العملاء", "din": "Customers"},
    "/sales-orders": {"en": "Sales orders", "ar": "أوامر البيع", "juba": "أوامر البيع", "din": "Sales orders"},
    "/locations": {"en": "Locations", "ar": "مواقع التخزين", "juba": "أماكن المخزون", "din": "Locations"},
    "/kits-bom": {"en": "Kits & BOM", "ar": "المجموعات وقائمة المواد", "juba": "الكِتات والمكوّنات", "din": "Kits & BOM"},
}

_SECTIONS: dict[str, dict[str, str]] = {
    "Overview": {"en": "Overview", "ar": "نظرة عامة", "juba": "نظرة سريعة", "din": "Overview"},
    "Operations": {"en": "Operations", "ar": "العمليات", "juba": "الشغل اليومي", "din": "Operations"},
    "Insights": {"en": "Insights", "ar": "تحليلات", "juba": "تحليل", "din": "Insights"},
    "Administration": {"en": "Administration", "ar": "الإدارة", "juba": "إدارة النظام", "din": "Administration"},
    "Every day": {"en": "Today's work", "ar": "شغل اليوم", "juba": "شغل اليوم", "din": "Today's work"},
    "When needed": {
        "en": "When you have time",
        "ar": "عند التفرّغ",
        "juba": "لما تفضى",
        "din": "When you have time",
    },
}

_CLERK_LABELS: dict[str, dict[str, str]] = {
    "/": {"en": "Home", "ar": "الرئيسية", "juba": "البيت", "din": "Home"},
    "/inventory": {"en": "Stock list", "ar": "قائمة المخزون", "juba": "قايمة المخزون", "din": "Stock list"},
    "/movements": {"en": "Stock in / out", "ar": "وارد / صادر", "juba": "داخل / طالع", "din": "Stock in / out"},
    "/purchase-orders": {"en": "Orders to suppliers", "ar": "طلبات للموردين", "juba": "طلبات للموردين", "din": "Orders to suppliers"},
    "/suppliers": {"en": "Suppliers", "ar": "الموردون", "juba": "الموردين", "din": "Suppliers"},
    "/auditing": {"en": "Shelf counts", "ar": "جرد الرفوف", "juba": "عد الرفوف", "din": "Shelf counts"},
    "/reports": {"en": "Printed summaries", "ar": "ملخصات مطبوعة", "juba": "ملخصات للطباعة", "din": "Printed summaries"},
    "/monitoring": {"en": "Alerts", "ar": "التنبيهات", "juba": "التنبيهات", "din": "Alerts"},
    "/customers": {"en": "Customers", "ar": "العملاء", "juba": "العملاء", "din": "Customers"},
    "/sales-orders": {"en": "Sales orders", "ar": "أوامر البيع", "juba": "أوامر البيع", "din": "Sales orders"},
    "/locations": {"en": "Bin locations", "ar": "مواقع الرفوف", "juba": "أماكن الرفوف", "din": "Bin locations"},
    "/kits-bom": {"en": "Kits / BOM", "ar": "المجموعات / BOM", "juba": "الكِتات / BOM", "din": "Kits / BOM"},
}


def t(lang: str, key: str) -> str:
    lang = normalize_lang({"lang": lang})
    row = _CHROME.get(key)
    if not row:
        return key
    return row.get(lang, row["en"])


def workspace_label(role: str | None, lang: str) -> str:
    lang = normalize_lang({"lang": lang})
    r = role or "VIEWER"
    return _WORKSPACE.get(r, _WORKSPACE["VIEWER"]).get(lang, _WORKSPACE["VIEWER"]["en"])


def role_short_ui(role: str | None, lang: str) -> str:
    lang = normalize_lang({"lang": lang})
    r = role or "VIEWER"
    return _ROLE_SHORT.get(r, _ROLE_SHORT["VIEWER"]).get(lang, _ROLE_SHORT["VIEWER"]["en"])


def nav_link_label(path: str, default: str, lang: str) -> str:
    lang = normalize_lang({"lang": lang})
    if path in _NAV:
        return _NAV[path].get(lang, _NAV[path]["en"])
    return default


def nav_section_label(section: str, lang: str) -> str:
    lang = normalize_lang({"lang": lang})
    if section in _SECTIONS:
        return _SECTIONS[section].get(lang, _SECTIONS[section]["en"])
    return section


def clerk_link_label(path: str, lang: str) -> str:
    lang = normalize_lang({"lang": lang})
    if path in _CLERK_LABELS:
        return _CLERK_LABELS[path].get(lang, _CLERK_LABELS[path]["en"])
    return nav_link_label(path, path, lang)


# --- Login ---
_LOGIN: dict[str, dict[str, str]] = {
    "title": {
        "en": "Inventory management",
        "ar": "إدارة المخزون",
        "juba": "إدارة المخزون",
        "din": "Inventory management",
    },
    "about_pre": {
        "en": "Multi-user inventory with role-based access —",
        "ar": "مخزون متعدد المستخدمين مع صلاحيات حسب الدور —",
        "juba": "مخزون بعدة مستخدمين وصلاحيات حسب الدور —",
        "din": "Multi-user inventory with role-based access —",
    },
    "about_post": {
        "en": "Stock clerks submit changes; managers approve with a PIN. Administrators manage users under Administration → Users.",
        "ar": "يسجل أمين المخزون التغييرات؛ يوافق المدير باستخدام رمز. يدير المسؤول المستخدمين من الإدارة ← المستخدمون.",
        "juba": "أمين المخزون يقدم التغييرات؛ المدير يوافق بالرمز. المسؤول يدير المستخدمين من الإدارة ← المستخدمين.",
        "din": "Stock clerks submit changes; managers approve with a PIN. Administrators manage users under Administration → Users.",
    },
    "tagline": {
        "en": "Secure stock tracking, approvals, and reporting.",
        "ar": "تتبع مخزون آمن مع موافقات وتقارير.",
        "juba": "تتبع مخزون آمن مع موافقات وتقارير.",
        "din": "Secure stock tracking, approvals, and reporting.",
    },
    "user_label": {"en": "Username", "ar": "اسم المستخدم", "juba": "اسم المستخدم", "din": "Username"},
    "user_ph": {"en": "", "ar": "", "juba": "", "din": ""},
    "pass_label": {"en": "Password", "ar": "كلمة المرور", "juba": "الباسورد", "din": "Password"},
    "pass_ph": {"en": "Enter your password", "ar": "أدخل كلمة المرور", "juba": "اكتب باسوردك", "din": "Enter your password"},
    "signin": {"en": "Sign In", "ar": "دخول", "juba": "ادخل", "din": "Sign In"},
    "err_required": {
        "en": "Please enter username and password.",
        "ar": "يرجى إدخال اسم المستخدم وكلمة المرور.",
        "juba": "لازم تكتب اسم المستخدم والباسورد.",
        "din": "Please enter username and password.",
    },
    "err_invalid": {
        "en": "Invalid username or password.",
        "ar": "اسم المستخدم أو كلمة المرور غير صحيحة.",
        "juba": "اسم المستخدم أو الباسورد غلط.",
        "din": "Invalid username or password.",
    },
    "ok_redirect": {
        "en": "Success — redirecting…",
        "ar": "تم — جاري التحويل…",
        "juba": "تمام — بنحولك…",
        "din": "Success — redirecting…",
    },
}


def login_txt(lang: str, key: str) -> str:
    lang = normalize_lang({"lang": lang})
    row = _LOGIN.get(key, {})
    return row.get(lang, row.get("en", key))


# --- Inventory header (callback-driven) ---
_INV: dict[str, dict[str, str]] = {
    "title_clerk": {
        "en": "Stock list",
        "ar": "قائمة المخزون",
        "juba": "قايمة المخزون",
        "din": "Stock list",
    },
    "help_clerk": {
        "en": "Select a row in the table, then use Edit selected row. A manager approves changes before stock updates apply.",
        "ar": "حدد صفًا في الجدول، ثم اضغط تعديل الصف المحدد. يوافق المدير قبل تطبيق التحديثات.",
        "juba": "اختار سطر في الجدول، وبعدين اضغط تعديل السطر. المدير لازم يوافق قبل ما التحديث يشتغل.",
        "din": "Select a row, then Edit selected row. A manager approves changes first.",
    },
    "title_full": {
        "en": "Stock register",
        "ar": "سجل المخزون",
        "juba": "دفتر المخزون",
        "din": "Stock register",
    },
    "help_full": {
        "en": "Browse items, import or export CSV, and maintain the catalog.",
        "ar": "استعراض الأصناف، استيراد/تصدير CSV، وإدارة البيانات المرجعية.",
        "juba": "شوف الأصناف، جيب أو طلع CSV، وضبط البيانات.",
        "din": "Browse items, CSV import/export, and maintain the catalog.",
    },
}


def inventory_header(lang: str, key: str) -> str:
    lang = normalize_lang({"lang": lang})
    row = _INV.get(key, {})
    return row.get(lang, row.get("en", ""))


# --- Stock clerk home (dashboard) ---
_CLERK_HOME: dict[str, dict[str, str]] = {
    "name_fallback": {
        "en": "friend",
        "ar": "زميلنا",
        "juba": "صديقنا",
        "din": "friend",
    },
    "welcome_title": {
        "en": "Good day, {name}",
        "ar": "يومك طيّب، {name}",
        "juba": "يوم سعيد، {name}",
        "din": "Good day, {name}",
    },
    "welcome_sub": {
        "en": "Check shelf stock first, then record goods in or out. Important edits wait for a manager’s OK.",
        "ar": "راجع الرفوف أولاً، ثم سجّل الوارد أو الصادر. التعديلات المهمة تنتظر موافقة المدير.",
        "juba": "اتأكد من الرفوف الأول، بعدين سجّل الداخل أو الطالع. التعديل المهم لازم المدير يوافق.",
        "din": "Check shelves first, then record stock in or out. Important edits wait for a manager.",
    },
    "card_stock_title": {
        "en": "Shelf & stock list",
        "ar": "الرفوف وقائمة المخزون",
        "juba": "الرفوف وقايمة المخزون",
        "din": "Shelf & stock list",
    },
    "card_stock_body": {
        "en": "Find an item, see quantity, and request updates. Your manager approves before numbers change.",
        "ar": "ابحث عن الصنف وشاهد الكمية واطلب التعديل. يوافق المدير قبل تغيير الأرقام.",
        "juba": "دور على الصنف وشوف الكمية واطلب التعديل. المدير يوافق قبل ما الأرقام تتغيّر.",
        "din": "Find an item and quantity; request updates. A manager approves before numbers change.",
    },
    "card_stock_cta": {
        "en": "Open stock list",
        "ar": "افتح قائمة المخزون",
        "juba": "افتح قايمة المخزون",
        "din": "Open stock list",
    },
    "card_move_title": {
        "en": "Goods in & out",
        "ar": "وارد وصادر البضاعة",
        "juba": "داخل وطالع البضاعة",
        "din": "Goods in & out",
    },
    "card_move_body": {
        "en": "When a delivery arrives or stock leaves the shop, write it here so the book stays honest.",
        "ar": "عند وصول توريد أو خروج بضاعة من المحل، سجّل هنا ليبقى الدفتر دقيقاً.",
        "juba": "لما التوريد يجي أو البضاعة تطلع من المحل، اكتب هنا عشان الدفتر يظل صاحي.",
        "din": "When deliveries arrive or stock leaves, record it here so records stay accurate.",
    },
    "card_move_cta": {
        "en": "Record stock movement",
        "ar": "سجّل حركة المخزون",
        "juba": "سجّل حركة المخزون",
        "din": "Record stock movement",
    },
    "section_more": {
        "en": "More in the menu",
        "ar": "المزيد في القائمة",
        "juba": "كمان في القايمة",
        "din": "More in the menu",
    },
    "warnings_title": {
        "en": "Needs attention",
        "ar": "يحتاج متابعة",
        "juba": "لازم تنتبه",
        "din": "Needs attention",
    },
    "no_warnings": {
        "en": "No open warnings — shelves look calm.",
        "ar": "لا تنبيهات مفتوحة — الوضع هادئ.",
        "juba": "ما في تنبيهات مفتوحة — الوضع هادي.",
        "din": "No open warnings.",
    },
    "sev_critical": {
        "en": "Urgent",
        "ar": "عاجل",
        "juba": "عاجل",
        "din": "Urgent",
    },
    "sev_warning": {
        "en": "Heads up",
        "ar": "تنبيه",
        "juba": "انتباه",
        "din": "Heads up",
    },
    "sev_notice": {
        "en": "Notice",
        "ar": "إشعار",
        "juba": "تنويه",
        "din": "Notice",
    },
}


def clerk_home_txt(lang: str, key: str) -> str:
    lang = normalize_lang({"lang": lang})
    row = _CLERK_HOME.get(key, {})
    return row.get(lang, row.get("en", key))


# --- Page hero titles + tooltip help (callback-driven headers) ---
_PAGE_HEADERS: dict[str, dict[str, dict[str, str]]] = {
    "dash_clerk": {
        "title": {"en": "Your shop desk", "ar": "مكتب محلك", "juba": "مكتب المحل", "din": "Your shop desk"},
        "help": {
            "en": (
                "Use the two big buttons for daily work: stock on the shelf, then movements when goods move. "
                "The sidebar lists everything else — same tasks, clearer words."
            ),
            "ar": (
                "استخدم الزرّين الكبيرين للعمل اليومي: المخزون على الرف، ثم الحركات عند تحرك البضاعة. "
                "القائمة الجانبية تعرض الباقي — نفس المهام بعبارات أوضح."
            ),
            "juba": (
                "استعمل الزرّين الكبار للشغل اليومي: المخزون في الرف، بعدين الحركات لما البضاعة تتحرك. "
                "القايمة على الجنب فيها الباقي — نفس الشغل بكلام أوضح."
            ),
            "din": (
                "Use the two big buttons for daily work: shelf stock, then movements when goods move. "
                "The sidebar lists the rest in plain words."
            ),
        },
    },
    "dash_analytics": {
        "title": {"en": "Dashboard", "ar": "لوحة المعلومات", "juba": "اللوحة", "din": "Dashboard"},
        "help": {
            "en": "KPIs, category mix, movement trends, and open alerts for your workspace.",
            "ar": "مؤشرات الأداء، توزيع الفئات، اتجاهات الحركة، والتنبيهات المفتوحة لمساحة عملك.",
            "juba": "أرقام مهمّة، توزيع الأصناف، حركة المخزون، والتنبيهات المفتوحة لشغلك.",
            "din": "KPIs, category mix, movement trends, and open alerts for your workspace.",
        },
    },
    "movements": {
        "title": {"en": "Stock in and out", "ar": "وارد وصادر المخزون", "juba": "داخل وطالع المخزون", "din": "Stock in and out"},
        "help": {
            "en": (
                "When a delivery arrives, record stock in. When you take goods from the shelf, record stock out. "
                "The table below shows past entries."
            ),
            "ar": (
                "عند وصول توريد، سجّل الوارد. عند أخذ بضائع من الرف، سجّل الصادر. الجدول يعرض السجلات السابقة."
            ),
            "juba": (
                "لما التوريد يجي سجّل الداخل. لما تاخد بضاعة من الرف سجّل الطالع. الجدول تحت فيه السجلات القديمة."
            ),
            "din": (
                "When a delivery arrives, record stock in. When you take goods from the shelf, record stock out. "
                "The table below shows past entries."
            ),
        },
    },
    "reports": {
        "title": {"en": "Reports & analytics", "ar": "التقارير والتحليلات", "juba": "التقارير والتحليل", "din": "Reports & analytics"},
        "help": {
            "en": (
                "KPIs at the top, then exports, Prophet forecast and decomposition (stock-out as sales proxy), "
                "what-if scenarios, and daily detail."
            ),
            "ar": "مؤشرات في الأعلى، ثم التصدير، تنبؤ Prophet وتحليله، وسيناريوهات what-if، والتفاصيل اليومية.",
            "juba": (
                "فوق فيه أرقام مهمّة، بعدين تصدير، وتنبؤ Prophet وتحليله (النقص زي مبيعات)، "
                "وسيناريوهات لو حصل كذا، وتفاصيل يوم بيوم."
            ),
            "din": "KPIs, exports, Prophet forecast and decomposition, what-if, and daily detail.",
        },
    },
    "config": {
        "title": {"en": "System configuration", "ar": "إعدادات النظام", "juba": "ضبط النظام", "din": "System configuration"},
        "help": {
            "en": "Thresholds, database backup, approval PIN, and the append-only activity log.",
            "ar": "عتبات التنبيه، نسخ احتياطي لقاعدة البيانات، رمز موافقة المدير، وسجل النشاط.",
            "juba": "حدود التنبيه، نسخة احتياطية للداتابيس، رقم موافقة المدير، وسجل الحركات.",
            "din": "Thresholds, database backup, approval PIN, and the append-only activity log.",
        },
    },
    "approvals": {
        "title": {"en": "Inventory approvals", "ar": "موافقات المخزون", "juba": "موافقة المخزون", "din": "Inventory approvals"},
        "help": {
            "en": (
                "Use the approval PIN from Configuration. Select one or more rows (checkboxes or header checkbox on this page), "
                "then approve or reject in bulk."
            ),
            "ar": (
                "استخدم رمز الموافقة من الإعدادات. حدد صفًا أو أكثر (مربعات الاختيار)، ثم وافق أو ارفض دفعة واحدة."
            ),
            "juba": (
                "استعمل رقم الموافقة من الضبط. اختار سطر أو أكتر (علامات الصح)، بعدين وافق أو ارفض مرة وحدة."
            ),
            "din": (
                "Use the approval PIN from Configuration. Select one or more rows, then approve or reject in bulk."
            ),
        },
    },
    "monitoring": {
        "title": {"en": "Monitoring & alerting", "ar": "المراقبة والتنبيهات", "juba": "المراقبة والتنبيه", "din": "Monitoring & alerting"},
        "help": {
            "en": "Recent system alerts and acknowledgements.",
            "ar": "تنبيهات النظام الأخيرة وتأكيد الاطلاع.",
            "juba": "آخر تنبيهات النظام وتأكيد إنك شفتها.",
            "din": "Recent system alerts and acknowledgements.",
        },
    },
    "users": {
        "title": {"en": "User management", "ar": "إدارة المستخدمين", "juba": "إدارة المستخدمين", "din": "User management"},
        "help": {
            "en": "Create accounts and assign roles. Only administrators can add users.",
            "ar": "إنشاء الحسابات وتعيين الأدوار. يمكن للمسؤول فقط إضافة مستخدمين.",
            "juba": "اعمل حسابات وحدد الأدوار. بس المسؤول يقدر يضيف مستخدمين.",
            "din": "Create accounts and assign roles. Only administrators can add users.",
        },
    },
    "auditing": {
        "title": {"en": "Auditing & cycle counts", "ar": "الجرد والعد الدوري", "juba": "الجرد والعد", "din": "Auditing & cycle counts"},
        "help": {
            "en": "Create sessions, generate count sheets, submit variances, and approve adjustments.",
            "ar": "إنشاء جلسات، إنشاء أوراق العد، إرسال الفروقات، والموافقة على التسويات.",
            "juba": "اعمل جلسات، طلع أوراق العد، ابعت الفروقات، ووافق على التعديل.",
            "din": "Create sessions, generate count sheets, submit variances, and approve adjustments.",
        },
    },
    "suppliers": {
        "title": {"en": "Suppliers", "ar": "الموردون", "juba": "الموردين", "din": "Suppliers"},
        "help": {
            "en": "Vendor master data: contacts, lead times, and ratings.",
            "ar": "بيانات الموردين: جهات الاتصال، أوقات التوريد، والتقييمات.",
            "juba": "بيانات المورد: التلفونات، مدة التوريد، والتقييم.",
            "din": "Vendor master data: contacts, lead times, and ratings.",
        },
    },
    "purchase_orders": {
        "title": {"en": "Purchase orders", "ar": "أوامر الشراء", "juba": "أوامر الشراء", "din": "Purchase orders"},
        "help": {
            "en": "Create drafts, submit for approval, receive lines, and close POs.",
            "ar": "إنشاء مسودات، إرسال للموافقة، استلام البنود، وإغلاق أوامر الشراء.",
            "juba": "اعمل مسودة، ابعتها للموافقة، استلم البنود، وأقفل أمر الشراء.",
            "din": "Create drafts, submit for approval, receive lines, and close POs.",
        },
    },
    "customers": {
        "title": {"en": "Customers", "ar": "العملاء", "juba": "العملاء", "din": "Customers"},
        "help": {
            "en": "Customer master for outbound sales orders and fulfilment.",
            "ar": "بيانات العملاء لأوامر البيع والتسليم.",
            "juba": "بيانات العملاء لأوامر البيع والتسليم.",
            "din": "Customer master for outbound sales orders and fulfilment.",
        },
    },
    "sales_orders": {
        "title": {"en": "Sales orders", "ar": "أوامر البيع", "juba": "أوامر البيع", "din": "Sales orders"},
        "help": {
            "en": "Draft lines, confirm the order, then ship from stock (FIFO) with optional pick location.",
            "ar": "أضف البنود، أكد الطلب، ثم صدّر من المخزون (FIFO) مع اختيار موقع الالتقاط.",
            "juba": "زوّد البنود، أكّد الطلب، بعدين طلع من المخزون مع مكان الاختيار.",
            "din": "Draft lines, confirm the order, then ship from stock (FIFO) with optional pick location.",
        },
    },
    "locations": {
        "title": {"en": "Locations & bin stock", "ar": "المواقع والمخزون حسب الرف", "juba": "الأماكن والكمية في الرف", "din": "Locations & bin stock"},
        "help": {
            "en": "Per-bin quantities, new warehouses or aisles, and bin-to-bin transfers (on-hand total unchanged).",
            "ar": "كميات لكل رف، مستودعات جديدة، ونقل بين الرفوف دون تغيير إجمالي الكمية.",
            "juba": "كمية في كل رف، مستودع جديد، ونقل بين الرفوف من غير ما تغيّر المجموع.",
            "din": "Per-bin quantities, new warehouses or aisles, and bin-to-bin transfers (on-hand total unchanged).",
        },
    },
    "kits_bom": {
        "title": {"en": "Kits & bill of materials", "ar": "المجموعات وقائمة المواد", "juba": "الكِتات وقايمة المكوّنات", "din": "Kits & bill of materials"},
        "help": {
            "en": "Define components per finished SKU, then assemble: consumes components (FIFO) and receives parents at rolled-up cost.",
            "ar": "حدد المكوّنات لكل صنف نهائي، ثم التجميع: يستهلك المكوّنات ويستلم الناتج بالتكلفة المجمعة.",
            "juba": "حدد المكوّنات للصنف الجاهز، بعدين التجميع يستهلك المكوّنات ويدخل الناتج بالتكلفة.",
            "din": "Define components per finished SKU, then assemble: consumes components (FIFO) and receives parents at rolled-up cost.",
        },
    },
}


def page_heading(lang: str, key: str) -> tuple[str, str]:
    """Localized (title, help) for `page_header(title, help=...)`."""
    lang = normalize_lang({"lang": lang})
    blk = _PAGE_HEADERS.get(key) or {"title": {"en": key}, "help": {"en": ""}}
    title = blk["title"].get(lang, blk["title"]["en"])
    help_text = blk["help"].get(lang, blk["help"]["en"])
    return title, help_text
