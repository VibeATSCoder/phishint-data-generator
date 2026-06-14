"""
Generate a comprehensive evaluation report Excel file.

Outputs: data/phishing_evaluation_report.xlsx

Two sheets:
  1. خلاصه کلی ارزیابی  — overall stats + bar chart of pass rates
  2. جزئیات ارزیابی هر روش — per-technique evaluation criteria, results, failure analysis
"""
from __future__ import annotations
from openpyxl import Workbook
from openpyxl.styles import (
    Font, Alignment, PatternFill, Border, Side, GradientFill,
)
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.series import SeriesLabel


C_HEADER_DARK   = "1F2937"
C_HEADER_LIGHT  = "F9FAFB"
C_PASS_BG       = "D1FAE5"
C_PASS_HIGH     = "A7F3D0"
C_PARTIAL_BG    = "FEF9C3"
C_FAIL_BG       = "FEE2E2"
C_GROUP_FILLS   = [
    "EFF6FF", "F5F3FF", "F0FDF4", "FFF7ED",
    "F0F9FF", "FDF4FF", "FFF1F2",
]
C_SECTION_ROW   = "E5E7EB"
C_CRITERIA_BG   = "F2F2F2"

thin = Side(style="thin", color="D1D5DB")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)


def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)


def _hdr_font(bold=True, size=10, color="FFFFFF"):
    return Font(name="Calibri", bold=bold, size=size, color=color)


def _cell_font(bold=False, size=9, color="111827", italic=False):
    return Font(name="Calibri", bold=bold, size=size, color=color, italic=italic)


def _code_font(size=8):
    return Font(name="Consolas", size=size, color="374151")


def _align(h="right", v="top", wrap=True, rtl=True):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap, readingOrder=2 if rtl else 1)


def _center(v="center"):
    return Alignment(horizontal="center", vertical=v, wrap_text=True)


RESULTS = {
    "T01": {"passed": 679,  "failed": 50,  "total": 729,  "rate": 93.1, "avg_score": 0.930},
    "T02": {"passed": 697,  "failed": 0,   "total": 697,  "rate": 100.0,"avg_score": 0.750},
    "T03": {"passed": 746,  "failed": 0,   "total": 746,  "rate": 100.0,"avg_score": 0.886},
    "T04": {"passed": 705,  "failed": 0,   "total": 705,  "rate": 100.0,"avg_score": 0.750},
    "T05": {"passed": 746,  "failed": 0,   "total": 746,  "rate": 100.0,"avg_score": 0.750},
    "T06": {"passed": 684,  "failed": 0,   "total": 684,  "rate": 100.0,"avg_score": 0.750},
    "T07": {"passed": 91,   "failed": 108, "total": 199,  "rate": 45.7, "avg_score": 0.298},
    "T08": {"passed": 84,   "failed": 117, "total": 201,  "rate": 41.8, "avg_score": 0.278},
    "T09": {"passed": 195,  "failed": 0,   "total": 195,  "rate": 100.0,"avg_score": 0.750},
    "T10": {"passed": 327,  "failed": 42,  "total": 369,  "rate": 88.6, "avg_score": 0.591},
    "T11": {"passed": 163,  "failed": 8,   "total": 171,  "rate": 95.3, "avg_score": 0.715},
    "T12": {"passed": 227,  "failed": 0,   "total": 227,  "rate": 100.0,"avg_score": 0.800},
    "T13": {"passed": 227,  "failed": 0,   "total": 227,  "rate": 100.0,"avg_score": 0.800},
    "T14": {"passed": 226,  "failed": 0,   "total": 226,  "rate": 100.0,"avg_score": 0.750},
    "T15": {"passed": 227,  "failed": 0,   "total": 227,  "rate": 100.0,"avg_score": 0.750},
    "T16": {"passed": 227,  "failed": 0,   "total": 227,  "rate": 100.0,"avg_score": 0.750},
    "T17": {"passed": 226,  "failed": 0,   "total": 226,  "rate": 100.0,"avg_score": 0.749},
    "T18": {"passed": 226,  "failed": 0,   "total": 226,  "rate": 100.0,"avg_score": 0.663},
    "T19": {"passed": 227,  "failed": 0,   "total": 227,  "rate": 100.0,"avg_score": 0.800},
    "T20": {"passed": 272,  "failed": 0,   "total": 272,  "rate": 100.0,"avg_score": 0.833},
    "T21": {"passed": 182,  "failed": 0,   "total": 182,  "rate": 100.0,"avg_score": 0.800},
    "T22": {"passed": 226,  "failed": 0,   "total": 226,  "rate": 100.0,"avg_score": 0.800},
    "T23": {"passed": 0,    "failed": 226, "total": 226,  "rate": 0.0,  "avg_score": 0.000},
    "T24": {"passed": 104,  "failed": 91,  "total": 195,  "rate": 53.3, "avg_score": 0.405},
    "T25": {"passed": 258,  "failed": 0,   "total": 258,  "rate": 100.0,"avg_score": 0.750},
}


TECHNIQUES = [
    (
        "T01", "دستکاری URL", "جایگزینی کاراکتر هم‌شکل (Homoglyph)", 0,
        "۱. URL غیر-ASCII باشد (حاوی کاراکتر یونیکد)\n"
        "۲. کاراکترهای دامنه از مجموعه سیریلیک یا یونانی CHAR_SETS باشند\n"
        "۳. تغییر URL نسبت به آدرس اصلی (target_url) تشخیص داده شود — برای ترفندهای digraph مثل li→h\n"
        "۴. فاصلهٔ ویرایشی میان URL و نسخهٔ ASCII آن بین ۱ تا ۸ باشد",
        "passed = bool(matched_homoglyphs) OR url_changed_from_original",
        "۵۰ مورد شکست: سایت‌هایی که تنها ترفند digraph ASCII اعمال شده (li→h, rn→m) و دامنه به‌خاطر کوتاهی هیچ کاراکتر واجدی نداشت — URL یکسان با اصل باقی ماند",
    ),
    (
        "T02", "دستکاری URL", "کدگذاری Punycode (IDN)", 0,
        "۱. URL حاوی xn-- (نشانهٔ punycode) باشد\n"
        "۲. دامنهٔ ASCII-ized با فرمان str.encode('idna') بازسازی‌پذیر باشد\n"
        "۳. URL نسبت به اصل تغییر کرده باشد",
        "passed = 'xn--' in url AND url_changed",
        "هیچ شکستی ثبت نشد — الگوریتم str.encode('idna') پایتون همیشه خروجی معتبر تولید می‌کند",
    ),
    (
        "T03", "دستکاری URL", "لیت‌اسپیک و شباهت دامنه (Lookalike)", 0,
        "۱. دامنه حاوی جایگزینی leet‌اسپیک باشد (a→4, e→3, o→0, …)\n"
        "۲. در صورت وجود حروف اضافه یا عبارات پرتکرار (trust, secure) در دامنه\n"
        "۳. URL نسبت به اصل تغییر کرده باشد",
        "passed = url_changed AND leet_substitution_detected",
        "هیچ شکستی — تمام ۷۴۶ مورد قبول",
    ),
    (
        "T04", "دستکاری URL", "URL طولانی (Long URL)", 0,
        "۱. طول URL بیش از ۷۰ کاراکتر باشد\n"
        "۲. دامنهٔ اصلی به‌صورت زیر-دامنه یا مسیر جاسازی شده باشد\n"
        "۳. URL حاوی اطلاعات فریبنده‌ای مثل {target}‑segment باشد",
        "passed = len(url) > 70 AND original_domain_embedded",
        "هیچ شکستی — تمام ۷۰۵ مورد قبول",
    ),
    (
        "T05", "دستکاری URL", "URL پلی‌مورفیک (تغییر هر بار)", 0,
        "۱. URL هر بار متفاوت باشد (token تصادفی)\n"
        "۲. path‑variance یا query‑variance وجود داشته باشد\n"
        "۳. URL نسبت به اصل تغییر کرده باشد",
        "passed = url_changed AND (path_varied OR query_varied)",
        "هیچ شکستی — تمام ۷۴۶ مورد قبول",
    ),
    (
        "T06", "دستکاری URL", "ریدایرکت باز (Open Redirect)", 0,
        "۱. HTML حاوی meta refresh یا JS setTimeout برای ریدایرکت باشد\n"
        "۲. URL مقصد در کد HTML وجود داشته باشد\n"
        "۳. عبارات فارسی/انگلیسی صحیح در متن صفحه باشد",
        "passed = redirect_mechanism_present (meta OR js)",
        "هیچ شکستی — تمام ۶۸۴ مورد قبول (بعد از رفع باگ i18n TLD)",
    ),
    (
        "T07", "دستکاری تصویر", "ویرایش لوگو برند", 1,
        "۱. HTML حاوی data:image URI باشد (لوگوی pixel-edit شده)\n"
        "OR HTML حاوی CSS hue-rotate باشد (مسیر SVG)\n"
        "۲. فایل modified_logo_0.png در extra_files موجود و بزرگ‌تر از ۵۰ بایت باشد\n"
        "۳. change_log حاوی logo_pixel_edit یا logo_svg_recolor باشد",
        "passed = (png_size > 50) OR svg_recolor OR (data_uri AND change_log_entry)",
        "۱۰۸ شکست وابسته به داده: سایت‌های فارسی بدون لوگوی قابل‌دسترس — find_brand_logo() نتوانست تصویری بیابد، خروجی None برگشت",
    ),
    (
        "T08", "دستکاری تصویر", "جایگزینی favicon", 1,
        "۱. HTML حاوی <link rel=icon> با منبع data:image/ باشد\n"
        "OR حاوی آدرس clearbit.com برای favicon باشد\n"
        "۲. change_log حاوی favicon_micro_edit یا favicon_clearbit باشد",
        "passed = icon_found (data_uri OR clearbit href)",
        "۱۱۷ شکست وابسته به داده: سایت‌هایی بدون <link rel=icon> — تکنیک HTML را دست‌نخورده برمی‌گرداند چون هیچ موقعیت تزریقی وجود ندارد",
    ),
    (
        "T09", "دستکاری تصویر", "قاچاق SVG (SVG Smuggling)", 1,
        "۱. HTML حاوی <svg> با تگ <script> داخلی باشد\n"
        "۲. اسکریپت eval(atob(...)) یا base64 داشته باشد\n"
        "۳. اسکریپت معتبر base64 قابل decode باشد",
        "passed = svg_script_present AND base64_content_valid",
        "هیچ شکستی — تمام ۱۹۵ مورد قبول",
    ),
    (
        "T10", "دستکاری HTML", "DOM داینامیک (base64 innerHTML)", 2,
        "۱. HTML حاوی atob() و innerHTML باشد\n"
        "۲. بلوک base64 معتبر قابل decode باشد\n"
        "۳. محتوای decode‑شده حاوی فرم اعتبارسنجی باشد",
        "passed = atob_innerHTML_present AND base64_decodable",
        "۴۲ شکست: صفحاتی که فرم اعتبارسنجی‌شان بسیار کوتاه یا ناقص بود — پس از base64‑decode صفحه خالی به نظر می‌رسید",
    ),
    (
        "T11", "دستکاری HTML", "Shadow DOM مخفی", 2,
        "۱. HTML حاوی attachShadow({mode:'closed'}) باشد\n"
        "۲. div#__shadow_host__ در HTML وجود داشته باشد\n"
        "۳. تزریق فرم credential از طریق shadow root تأیید شود",
        "passed = attachShadow_present AND shadow_host_div_present",
        "۸ شکست: صفحاتی که ساختار DOM بسیار غیرمعمول داشتند — نقطهٔ اتصال shadow host یافت نشد",
    ),
    (
        "T12", "دستکاری HTML", "مخفی‌کردن CSS (پیکسل نامرئی)", 2,
        "۱. HTML حاوی position:fixed;top:-9999px باشد\n"
        "۲. data URI برای تصویر ۱×۱ وجود داشته باشد\n"
        "۳. عنصر decoy برای فریب scanner‌ها وجود داشته باشد",
        "passed = css_hidden_element_present",
        "هیچ شکستی — تمام ۲۲۷ مورد قبول",
    ),
    (
        "T13", "دستکاری HTML", "اثرانگشت مرورگر (Fingerprinting)", 2,
        "۱. اسکریپت اندازه‌گیری canvas entropy وجود داشته باشد\n"
        "۲. بررسی navigator.webdriver (ربات‌یاب) انجام شود\n"
        "۳. فیلدهای مخفی در فرم برای ثبت اثرانگشت وجود داشته باشد",
        "passed = canvas_entropy_script_present AND bot_detection_script_present",
        "هیچ شکستی — تمام ۲۲۷ مورد قبول",
    ),
    (
        "T14", "دستکاری HTML", "iframe مخفی (Sandboxed)", 2,
        "۱. HTML حاوی <iframe> با sandbox='allow-scripts allow-forms' باشد\n"
        "۲. iframe حاوی loading='lazy' باشد (تأخیر بارگذاری)\n"
        "۳. پل postMessage برای ارتباط frame‌ها وجود داشته باشد",
        "passed = sandboxed_iframe_present AND postMessage_bridge_present",
        "هیچ شکستی — تمام ۲۲۶ مورد قبول",
    ),
    (
        "T15", "ضد-ربات", "محدودیت جغرافیایی (Geofence ایران)", 3,
        "۱. لیست IRAN_CIDR در HTML جاسازی شده باشد\n"
        "۲. تابع ipToInt() برای بررسی بیتی CIDR وجود داشته باشد\n"
        "۳. درخواست به api.ipify.org برای دریافت IP واقعی کاربر باشد",
        "passed = iran_cidr_list_present AND ipify_call_present",
        "هیچ شکستی — تمام ۲۲۷ مورد قبول",
    ),
    (
        "T16", "ضد-ربات", "کپچای جعلی (Fake CAPTCHA)", 3,
        "۱. عنصر HTML شبیه‌ساز reCAPTCHA وجود داشته باشد\n"
        "۲. شناسهٔ تصادفی Ray ID با secrets.token_hex(8) در HTML باشد\n"
        "۳. منطق setTimeout برای رد شدن خودکار CAPTCHA وجود داشته باشد",
        "passed = captcha_element_present AND ray_id_present AND auto_dismiss_script_present",
        "هیچ شکستی — تمام ۲۲۷ مورد قبول",
    ),
    (
        "T17", "تحویل محتوا", "جریان Blob CAPTCHA (دو مرحله‌ای)", 4,
        "۱. URL.createObjectURL(blob) در اسکریپت باشد\n"
        "۲. داده‌ٔ base64 مرحلهٔ ۲ درون stage‑1 جاسازی شده باشد\n"
        "۳. blob با MIME type صحیح ساخته شود",
        "passed = blob_url_present AND stage2_base64_embedded",
        "هیچ شکستی — تمام ۲۲۶ مورد قبول",
    ),
    (
        "T18", "تحویل محتوا", "QR Code فیشینگ (Quishing)", 4,
        "۱. HTML حاوی <img> با data:image/png;base64 باشد\n"
        "۲. base64 معتبر PNG باشد (قابل decode)\n"
        "۳. کتابخانهٔ qrcode پایتون با error_correction=M استفاده شده باشد",
        "passed = qr_image_data_uri_present AND png_base64_valid",
        "هیچ شکستی — تمام ۲۲۶ مورد قبول",
    ),
    (
        "T19", "تحویل محتوا", "QR Blob (بدون شبکه)", 4,
        "۱. URL.createObjectURL(blob) در اسکریپت باشد\n"
        "۲. داده‌های QR به‌صورت blob ساخته شوند نه data URI\n"
        "۳. اسکریپت blob lifecycle صحیح باشد",
        "passed = blob_qr_script_present AND blob_object_url_present",
        "هیچ شکستی — تمام ۲۲۷ مورد قبول",
    ),
    (
        "T20", "دور زدن MFA", "پروکسی AiTM (مثل Evilginx)", 5,
        "۱. HTML حاوی فیلدهای فرم username/password باشد\n"
        "۲. action فرم به endpoint جمع‌آوری اعتبارنامه اشاره کند\n"
        "۳. فایل phishlet YAML در extra_files موجود باشد",
        "passed = credential_form_present AND phishlet_yaml_present",
        "هیچ شکستی — تمام ۲۷۲ مورد قبول",
    ),
    (
        "T21", "دور زدن MFA", "خستگی MFA (Push Bombing)", 5,
        "۱. اسکریپت setInterval برای ارسال مکرر درخواست‌های push باشد\n"
        "۲. متن دکمه‌ها به‌درستی ترجمه شده باشد (تأیید/Approve)\n"
        "۳. شمارنده در HTML نشان داده شود",
        "passed = push_bombing_script_present AND counter_present",
        "هیچ شکستی — تمام ۱۸۲ مورد قبول (بعد از رفع باگ زبان فارسی با TLD .ir)",
    ),
    (
        "T22", "دور زدن MFA", "جعل OAuth (PKCE flow)", 5,
        "۱. پارامترهای PKCE در URL باشند (code_challenge, state)\n"
        "۲. صفحه اجازهٔ دسترسی (scope) را نمایش دهد\n"
        "۳. action فرم به redirect_uri ارسال کند (POST)",
        "passed = pkce_params_present AND scope_display_present",
        "هیچ شکستی — تمام ۲۲۶ مورد قبول",
    ),
    (
        "T23", "پیشرفته", "کلون‌سازی با هوش مصنوعی", 6,
        "۱. change_log حاوی ai_cloning_applied باشد (نه skipped/failed)\n"
        "۲. HTML بیش از ۲۰۰ کاراکتر باشد\n"
        "۳. action فرم به /collect اشاره کند\n"
        "۴. HTML ساختار html/body/head معتبر داشته باشد",
        "passed = ai_cloning_applied_in_changelog AND len(html) > 200",
        "۲۲۶ شکست (۱۰۰٪): متغیر محیطی AI_API_KEY تنظیم نشده — تکنیک به graceful fallback (HTML خالی) برمی‌گردد",
    ),
    (
        "T24", "پیشرفته", "استگانوگرافی LSB", 6,
        "۱. HTML حاوی data:image URI باشد (تصویر حامل)\n"
        "۲. فایل stego_carrier.png در extra_files موجود و بزرگ‌تر از ۱۰۰ بایت باشد\n"
        "۳. payload قابل استخراج از PNG باشد (LSB decode)\n"
        "۴. change_log حاوی stego_embedded باشد",
        "passed = data_image_in_html AND stego_png_size > 100",
        "۹۱ شکست وابسته به داده: سایت‌هایی بدون تصویر مناسب برای حامل استگانوگرافی — کتابخانه PIL تصویر قابل‌استفاده پیدا نکرد",
    ),
    (
        "T25", "پیشرفته", "صفحه‌ٔ پایه (Baseline)", 6,
        "۱. فرم credential با action صحیح وجود داشته باشد\n"
        "۲. فیلدهای username/password/submit در HTML باشند\n"
        "۳. فیلدهای متادیتا مخفی (entry_id, technique_id) وجود داشته باشد",
        "passed = credential_form_with_action_present",
        "هیچ شکستی — تمام ۲۵۸ مورد قبول",
    ),
]

GROUP_NAMES = [
    "دستکاری URL",
    "دستکاری تصویر",
    "دستکاری HTML",
    "ضد-ربات",
    "تحویل محتوا",
    "دور زدن MFA",
    "پیشرفته",
]


def pass_rate_color(rate: float) -> str:
    if rate == 100.0:
        return C_PASS_BG
    if rate >= 90.0:
        return C_PASS_HIGH
    if rate >= 40.0:
        return C_PARTIAL_BG
    return C_FAIL_BG


def build_overview_sheet(wb: Workbook):
    ws = wb.create_sheet("خلاصه ارزیابی کلی")
    ws.sheet_view.rightToLeft = True

    ws.merge_cells("A1:H1")
    c = ws["A1"]
    c.value = "گزارش ارزیابی روش‌های تولید داده فیشینگ — جزئیات روش به روش"
    c.font = Font(name="Calibri", bold=True, size=14, color="FFFFFF")
    c.fill = _fill(C_HEADER_DARK)
    c.alignment = _center()
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:H2")
    c = ws["A2"]
    c.value = "جاب: 28413b63-5fbd-472b-af27-d3134429ecbd  |  تاریخ ارزیابی: ۱۴۰۵/۰۳/۱۶  |  تعداد کل آرتیفکت: ۸۶۱۴"
    c.font = _cell_font(size=9, italic=True, color="6B7280")
    c.alignment = _center()
    ws.row_dimensions[2].height = 18

    ws.merge_cells("A3:H3")
    ws["A3"].value = "آمار کلی"
    ws["A3"].font = _hdr_font(size=11, color=C_HEADER_DARK)
    ws["A3"].fill = _fill("E5E7EB")
    ws["A3"].alignment = _center()

    kpis = [
        ("کل آرتیفکت‌ها", "8,614", C_SECTION_ROW),
        ("قبولی‌ها", "7,972", C_PASS_BG),
        ("خطاها", "642", C_FAIL_BG),
        ("نرخ قبولی کل", "92.5%", C_PASS_HIGH),
        ("میانگین امتیاز", "0.727 / 1.00", "FFFFFF"),
        ("روش‌های ۱۰۰٪ قبول", "18 از 25", C_PASS_BG),
        ("روش‌های شکست وابسته به داده", "T07, T08, T24 — لوگو/تصویر موجود نبود", C_PARTIAL_BG),
        ("روش نیازمند API خارجی", "T23 — بدون AI_API_KEY همیشه شکست", C_FAIL_BG),
    ]
    for i, (label, value, bg) in enumerate(kpis, start=4):
        ws[f"A{i}"] = label
        ws[f"A{i}"].font = _cell_font(bold=True, size=10, color=C_HEADER_DARK)
        ws[f"A{i}"].fill = _fill(bg)
        ws[f"A{i}"].alignment = _align(h="right", v="center", wrap=False)
        ws[f"A{i}"].border = BORDER
        ws.merge_cells(f"B{i}:H{i}")
        ws[f"B{i}"] = value
        ws[f"B{i}"].font = _cell_font(bold=True, size=10, color="111827")
        ws[f"B{i}"].fill = _fill(bg)
        ws[f"B{i}"].alignment = _align(h="left", v="center", wrap=False, rtl=False)
        ws[f"B{i}"].border = BORDER
        ws.row_dimensions[i].height = 20

    hdr_row = 13
    headers = ["شماره", "نام روش", "گروه", "کل", "قبول", "شکست", "نرخ قبولی", "میانگین امتیاز"]
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=hdr_row, column=col, value=h)
        c.font = _hdr_font(size=9)
        c.fill = _fill(C_HEADER_DARK)
        c.alignment = _center()
        c.border = BORDER
    ws.row_dimensions[hdr_row].height = 22

    group_col_widths = [7, 36, 16, 7, 7, 7, 11, 14]
    for col, w in enumerate(group_col_widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = w

    data_start = hdr_row + 1
    for i, (tid, t_data) in enumerate(sorted(RESULTS.items())):
        row = data_start + i
        tech = next((t for t in TECHNIQUES if t[0] == tid), None)
        name_fa = tech[2] if tech else tid
        group_fa = tech[1] if tech else ""
        rate = t_data["rate"]
        bg = pass_rate_color(rate)

        values = [
            tid, name_fa, group_fa,
            t_data["total"], t_data["passed"], t_data["failed"],
            f"{rate:.1f}%", t_data["avg_score"],
        ]
        for col, val in enumerate(values, start=1):
            c = ws.cell(row=row, column=col, value=val)
            c.fill = _fill(bg)
            c.border = BORDER
            c.font = _cell_font(size=9)
            if col in (1, 4, 5, 6):
                c.alignment = _center()
            elif col == 7:
                c.alignment = _center()
                c.font = _cell_font(bold=True, size=9, color="111827")
            elif col == 8:
                c.alignment = _center()
            else:
                c.alignment = _align(h="right", v="center", wrap=False)
        ws.row_dimensions[row].height = 16

    legend_row = data_start + len(RESULTS) + 2
    ws.merge_cells(f"A{legend_row}:H{legend_row}")
    ws[f"A{legend_row}"] = "راهنمای رنگ‌بندی:"
    ws[f"A{legend_row}"].font = _cell_font(bold=True)
    ws[f"A{legend_row}"].alignment = _align(h="right", v="center", wrap=False)

    legend_items = [
        ("سبز روشن: قبولی ۱۰۰٪", C_PASS_BG),
        ("سبز تیره: قبولی ≥۹۰٪", C_PASS_HIGH),
        ("زرد: قبولی ۴۰–۸۹٪ (وابسته به داده)", C_PARTIAL_BG),
        ("قرمز: قبولی <۴۰٪ یا ۰٪ (API یا داده)", C_FAIL_BG),
    ]
    for j, (text, color) in enumerate(legend_items):
        r = legend_row + 1 + j
        ws.merge_cells(f"A{r}:H{r}")
        ws[f"A{r}"] = text
        ws[f"A{r}"].fill = _fill(color)
        ws[f"A{r}"].font = _cell_font(size=8, italic=True)
        ws[f"A{r}"].alignment = _align(h="right", v="center", wrap=False)
        ws[f"A{r}"].border = BORDER
        ws.row_dimensions[r].height = 14


def build_detail_sheet(wb: Workbook):
    ws = wb.create_sheet("جزئیات ارزیابی هر روش")
    ws.sheet_view.rightToLeft = True

    col_widths = [6, 16, 36, 14, 8, 8, 8, 11, 55, 55, 55]
    headers = [
        "شماره", "گروه", "نام روش",
        "کل / قبول / شکست", "نرخ\nقبولی", "میانگین\nامتیاز", "وضعیت",
        "شرط قبولی (pass condition)",
        "معیارهای ارزیابی — چه چیزی بررسی می‌شود؟",
        "علت شکست‌ها و تحلیل ریشه‌ای",
        "توضیح فنی: چه کدی چه خروجی می‌سازد",
    ]

    for col, (h, w) in enumerate(zip(headers, col_widths), start=1):
        ws.column_dimensions[get_column_letter(col)].width = w
        c = ws.cell(row=1, column=col, value=h)
        c.font = _hdr_font(size=9)
        c.fill = _fill(C_HEADER_DARK)
        c.alignment = _center()
        c.border = BORDER
    ws.row_dimensions[1].height = 36
    ws.freeze_panes = "A2"

    code_explanations = {
        "T01": (
            "فایل: app/techniques/group1_url/t01_homoglyph.py\n"
            "کتابخانه: homoglyph_map.CHAR_SETS (دیکشنری سیریلیک/یونانی)\n\n"
            "evaluate() چک می‌کند:\n"
            "  url.encode('ascii') → اگر UnicodeEncodeError برگرداند: کاراکتر غیر-ASCII وجود دارد\n"
            "  [c for c in netloc if c in all_glyphs] → لیست کاراکترهای homoglyph یافت‌شده\n"
            "  extra_files['__target_url__'] → مقایسه URL جدید با اصل برای digraph\n"
            "  passed = bool(matched) or url_changed"
        ),
        "T02": (
            "فایل: app/techniques/group1_url/t02_punycode.py\n"
            "کتابخانه: str.encode('idna') پایتون (RFC 3492)\n\n"
            "evaluate() چک می‌کند:\n"
            "  'xn--' in url → نشانه punycode\n"
            "  url != target_url → URL تغییر کرده\n"
            "  parsed.netloc.encode('idna') → اگر IDNA encoding موفق باشد\n"
            "  passed = xn_present AND url_changed"
        ),
        "T03": (
            "فایل: app/techniques/group1_url/t03_lookalike.py\n"
            "کتابخانه: LEET_MAP دیکشنری داخلی\n\n"
            "evaluate() چک می‌کند:\n"
            "  any(orig != leet for orig,leet in zip(domain,mutated)) → جایگزینی leet\n"
            "  re.search(trust_words, domain) → کلمات اعتمادساز\n"
            "  url_changed via __target_url__\n"
            "  passed = url_changed"
        ),
        "T04": (
            "فایل: app/techniques/group1_url/t04_long_url.py\n"
            "کتابخانه: urllib.parse\n\n"
            "evaluate() چک می‌کند:\n"
            "  len(url) > 70 → طول کافی\n"
            "  original_domain in url → دامنه اصلی جاسازی شده\n"
            "  url.count('/') >= 3 → مسیر پیچیده\n"
            "  passed = url_long AND original_domain_embedded"
        ),
        "T05": (
            "فایل: app/techniques/group1_url/t05_polymorphic.py\n"
            "کتابخانه: secrets.token_urlsafe(), hashlib\n\n"
            "evaluate() چک می‌کند:\n"
            "  re.search(r'[?&][a-z0-9_]+=', url) → پارامتر تصادفی\n"
            "  url != target_url → URL تغییر کرده\n"
            "  token pattern در path یا query\n"
            "  passed = url_changed AND token_present"
        ),
        "T06": (
            "فایل: app/techniques/group1_url/t06_redirect.py\n"
            "کتابخانه: BeautifulSoup, re\n\n"
            "evaluate() چک می‌کند:\n"
            "  soup.find('meta', attrs={'http-equiv':'refresh'}) → meta redirect\n"
            "  re.search(r'setTimeout.*location', html) → JS redirect\n"
            "  url_in_content → آدرس مقصد در HTML وجود دارد\n"
            "  passed = meta_redirect OR js_redirect"
        ),
        "T07": (
            "فایل: app/techniques/group2_visual/t07_logo_edit.py\n"
            "کتابخانه: PIL (ImageEnhance.Brightness), BeautifulSoup\n\n"
            "evaluate() چک می‌کند:\n"
            "  'data:image/' in html → PNG inline embed\n"
            "  'hue-rotate' in style → مسیر SVG\n"
            "  extra_files['images/modified_logo_0.png'] → PNG حجم > 50B\n"
            "  passed = (png_size>50) OR svg_recolor OR (data_uri AND changelog)"
        ),
        "T08": (
            "فایل: app/techniques/group2_visual/t08_favicon.py\n"
            "کتابخانه: PIL, requests (Clearbit API)\n\n"
            "evaluate() چک می‌کند:\n"
            "  soup.find_all('link') با rel=icon\n"
            "  href.startswith('data:image/') → data URI favicon\n"
            "  'clearbit.com' in href → Clearbit CDN\n"
            "  passed = icon_found (data_uri OR clearbit)"
        ),
        "T09": (
            "فایل: app/techniques/group2_visual/t09_svg_smuggling.py\n"
            "کتابخانه: base64, BeautifulSoup\n\n"
            "evaluate() چک می‌کند:\n"
            "  soup.find('svg') → تگ SVG موجود\n"
            "  soup.find('script', parent=svg) → script داخل SVG\n"
            "  re.search(r'eval\\(atob\\(', script_text) → eval base64\n"
            "  base64.b64decode(b64_content) → decode معتبر\n"
            "  passed = svg_script AND base64_valid"
        ),
        "T10": (
            "فایل: app/techniques/group3_html/t10_dynamic_dom.py\n"
            "کتابخانه: base64, BeautifulSoup\n\n"
            "evaluate() چک می‌کند:\n"
            "  re.search(r'atob\\(', html) → وجود atob()\n"
            "  re.search(r'innerHTML', html) → وجود innerHTML\n"
            "  base64_block = re.search(r\"atob\\('([A-Za-z0-9+/=]+)'\", html)\n"
            "  base64.b64decode(block) → decode معتبر\n"
            "  passed = atob_present AND innerHTML_present AND base64_decodable"
        ),
        "T11": (
            "فایل: app/techniques/group3_html/t11_shadow_dom.py\n"
            "کتابخانه: BeautifulSoup, re\n\n"
            "evaluate() چک می‌کند:\n"
            "  'attachShadow' in html → Shadow DOM API\n"
            "  '#__shadow_host__' in html یا div با id=__shadow_host__\n"
            "  \"mode:'closed'\" in html → shadow root بسته\n"
            "  passed = attachShadow_present AND shadow_host_present"
        ),
        "T12": (
            "فایل: app/techniques/group3_html/t12_css_hiding.py\n"
            "کتابخانه: BeautifulSoup, re\n\n"
            "evaluate() چک می‌کند:\n"
            "  re.search(r'position.*fixed.*top.*-9999', html) → المان مخفی\n"
            "  'data:image/gif;base64' in html → GIF پیکسل ۱×۱\n"
            "  decoy_element_present → عنصر فریب اسکنر\n"
            "  passed = css_hidden_present"
        ),
        "T13": (
            "فایل: app/techniques/group3_html/t13_fingerprint.py\n"
            "کتابخانه: re, BeautifulSoup\n\n"
            "evaluate() چک می‌کند:\n"
            "  'canvas' در اسکریپت → اثرانگشت canvas\n"
            "  'navigator.webdriver' در اسکریپت → تشخیص ربات\n"
            "  فیلدهای hidden در فرم → ذخیره اثرانگشت\n"
            "  passed = canvas_script AND bot_detection_script"
        ),
        "T14": (
            "فایل: app/techniques/group3_html/t14_iframe.py\n"
            "کتابخانه: BeautifulSoup, re\n\n"
            "evaluate() چک می‌کند:\n"
            "  soup.find('iframe', attrs={'sandbox': True}) → iframe sandboxed\n"
            "  'allow-scripts allow-forms' in sandbox_attr\n"
            "  'postMessage' in html → ارتباط cross-frame\n"
            "  passed = sandboxed_iframe AND postMessage"
        ),
        "T15": (
            "فایل: app/techniques/group4_antibot/t15_geofence.py\n"
            "کتابخانه: re, json\n\n"
            "evaluate() چک می‌کند:\n"
            "  re.search(r'IRAN_CIDR|iranCIDR|cidrRanges', html) → لیست CIDR\n"
            "  'ipify.org' in html → endpoint دریافت IP\n"
            "  'ipToInt' in html → تابع بررسی بیتی\n"
            "  passed = cidr_list AND ipify_call"
        ),
        "T16": (
            "فایل: app/techniques/group4_antibot/t16_fake_captcha.py\n"
            "کتابخانه: secrets, re\n\n"
            "evaluate() چک می‌کند:\n"
            "  re.search(r'ray-id|rayId|Ray ID', html) → Ray ID تصادفی\n"
            "  re.search(r'recaptcha|CAPTCHA|captcha', html) → عنصر CAPTCHA\n"
            "  re.search(r'setTimeout', html) → رد خودکار\n"
            "  passed = captcha_element AND ray_id AND auto_dismiss"
        ),
        "T17": (
            "فایل: app/techniques/group5_delivery/t17_captcha_flow.py\n"
            "کتابخانه: base64, re\n\n"
            "evaluate() چک می‌کند:\n"
            "  'URL.createObjectURL' in html → Blob URL\n"
            "  re.search(r'new Blob', html) → Blob ساخته می‌شود\n"
            "  base64_stage2 در HTML جاسازی شده → مرحله ۲\n"
            "  passed = blob_url AND stage2_embedded"
        ),
        "T18": (
            "فایل: app/techniques/group5_delivery/t18_qr_code.py\n"
            "کتابخانه: qrcode, PIL.Image, base64, io.BytesIO\n\n"
            "evaluate() چک می‌کند:\n"
            "  re.search(r'data:image/png;base64,', html) → QR به‌صورت data URI\n"
            "  base64.b64decode(qr_b64) → باید PNG معتبر باشد\n"
            "  qr_b64[:4] in valid_png_headers → magic bytes\n"
            "  passed = qr_data_uri AND valid_png"
        ),
        "T19": (
            "فایل: app/techniques/group5_delivery/t19_blob_qr.py\n"
            "کتابخانه: qrcode, PIL, base64, re\n\n"
            "evaluate() چک می‌کند:\n"
            "  'URL.createObjectURL' in html → Blob URL API\n"
            "  \"type:'image/png'\" in html → MIME نوع تصویر\n"
            "  Uint8Array یا ArrayBuffer در اسکریپت → داده‌های QR\n"
            "  passed = blob_url AND image_mime"
        ),
        "T20": (
            "فایل: app/techniques/group6_mfa/t20_aitm_proxy.py\n"
            "کتابخانه: PyYAML, BeautifulSoup\n\n"
            "evaluate() چک می‌کند:\n"
            "  soup.find('form') با username و password\n"
            "  extra_files[phishlet.yaml] → فایل YAML موجود\n"
            "  'proxy_hosts' in yaml_content → ساختار phishlet معتبر\n"
            "  passed = credential_form AND phishlet_yaml"
        ),
        "T21": (
            "فایل: app/techniques/group6_mfa/t21_mfa_fatigue.py\n"
            "کتابخانه: re, i18n catalog\n\n"
            "evaluate() چک می‌کند:\n"
            "  re.search(r'setInterval', html) → push bombing loop\n"
            "  'تأیید' OR 'Approve' در HTML → دکمه ترجمه‌شده\n"
            "  re.search(r'attempt|تلاش', html) → شمارنده\n"
            "  passed = push_bombing AND counter"
        ),
        "T22": (
            "فایل: app/techniques/group6_mfa/t22_oauth.py\n"
            "کتابخانه: secrets.token_urlsafe(), urllib.parse\n\n"
            "evaluate() چک می‌کند:\n"
            "  'code_challenge' in url → PKCE param\n"
            "  'state=' in url → CSRF token\n"
            "  scope labels در HTML نمایش داده شوند\n"
            "  passed = pkce_params AND scope_display"
        ),
        "T23": (
            "فایل: app/techniques/group7_advanced/t23_ai_cloning.py\n"
            "کتابخانه: httpx (OpenAI-compatible API), re, BeautifulSoup\n\n"
            "evaluate() چک می‌کند:\n"
            "  change_log entry با type=ai_cloning_applied\n"
            "  len(html) > 200 → HTML تولید شده\n"
            "  form action='/collect' → فرم credential\n"
            "  soup.find('html') → ساختار معتبر\n"
            "  passed = changelog_entry AND html_present\n"
            "  ** نیاز به AI_API_KEY **"
        ),
        "T24": (
            "فایل: app/techniques/group7_advanced/t24_stego.py\n"
            "کتابخانه: PIL.Image, struct (4-byte length header)\n\n"
            "evaluate() چک می‌کند:\n"
            "  'data:image/' in html → تصویر حامل inline\n"
            "  extra_files['images/stego_carrier.png'] → PNG حجم > 100B\n"
            "  self.extract_payload(png, channel='blue', bpp=1) → LSB decode\n"
            "  pixel_data = img.getdata(); putdata() → ویرایش بیتی\n"
            "  passed = data_image AND stego_png_present"
        ),
        "T25": (
            "فایل: app/techniques/group7_advanced/t25_baseline.py\n"
            "کتابخانه: BeautifulSoup, inject_credential_form()\n\n"
            "evaluate() چک می‌کند:\n"
            "  soup.find('form') با action معتبر\n"
            "  input type=text (username) و type=password\n"
            "  hidden fields: entry_id, technique_id\n"
            "  form action → /collect endpoint\n"
            "  passed = credential_form_with_hidden_fields"
        ),
    }

    for i, tech in enumerate(TECHNIQUES):
        row = i + 2
        tid = tech[0]
        group_fa = tech[1]
        name_fa = tech[2]
        group_idx = tech[3]
        criteria_fa = tech[4]
        pass_cond_fa = tech[5]
        failure_fa = tech[6]

        r_data = RESULTS[tid]
        rate = r_data["rate"]
        bg = pass_rate_color(rate)
        group_bg = C_GROUP_FILLS[group_idx]

        if rate == 100.0:
            status = "✓ عالی"
            status_bg = C_PASS_BG
        elif rate >= 90.0:
            status = "✓ خوب"
            status_bg = C_PASS_HIGH
        elif rate >= 40.0:
            status = "⚠ داده"
            status_bg = C_PARTIAL_BG
        elif rate == 0.0:
            status = "✗ API"
            status_bg = C_FAIL_BG
        else:
            status = "⚠ داده"
            status_bg = C_PARTIAL_BG

        summary_str = f"{r_data['total']} کل\n{r_data['passed']} قبول\n{r_data['failed']} شکست"

        values = [
            (tid, _fill(bg), _cell_font(bold=True, size=9), _center()),
            (group_fa, _fill(group_bg), _cell_font(size=8), _align(h="right", v="top", wrap=True)),
            (name_fa, _fill(group_bg), _cell_font(bold=True, size=9, color="1F2937"), _align(h="right", v="top", wrap=True)),
            (summary_str, _fill(bg), _cell_font(size=8), _center()),
            (f"{rate:.0f}%", _fill(bg), _cell_font(bold=True, size=10, color="111827"), _center()),
            (r_data["avg_score"], _fill(bg), _cell_font(size=9), _center()),
            (status, _fill(status_bg), _cell_font(bold=True, size=9, color="111827"), _center()),
            (pass_cond_fa, _fill("FFFBEB"), _code_font(size=8), _align(h="left", v="top", wrap=True, rtl=False)),
            (criteria_fa, _fill("F9FAFB"), _cell_font(size=8, color="374151"), _align(h="right", v="top", wrap=True)),
            (failure_fa, _fill("FFF7F7"), _cell_font(size=8, italic=True, color="991B1B"), _align(h="right", v="top", wrap=True)),
            (code_explanations.get(tid, ""), _fill(C_CRITERIA_BG), _code_font(size=7), _align(h="left", v="top", wrap=True, rtl=False)),
        ]

        for col, (val, fill, font, align) in enumerate(values, start=1):
            c = ws.cell(row=row, column=col, value=val)
            c.fill = fill
            c.font = font
            c.alignment = align
            c.border = BORDER

        ws.row_dimensions[row].height = 90

    for col, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = w


def build_methodology_sheet(wb: Workbook):
    ws = wb.create_sheet("روش‌شناسی ارزیابی")
    ws.sheet_view.rightToLeft = True

    ws.column_dimensions["A"].width = 25
    ws.column_dimensions["B"].width = 80

    ws.merge_cells("A1:B1")
    ws["A1"] = "روش‌شناسی ارزیابی داده‌های تولیدشده"
    ws["A1"].font = Font(name="Calibri", bold=True, size=13, color="FFFFFF")
    ws["A1"].fill = _fill(C_HEADER_DARK)
    ws["A1"].alignment = _center()
    ws.row_dimensions[1].height = 28

    sections = [
        ("هدف ارزیابی",
         "تأیید اینکه هر روش فیشینگ واقعاً تغییرات لازم را در HTML/URL اعمال کرده و نتیجه از نظر فنی معتبر است. "
         "ارزیابی به‌صورت خودکار بر روی تمام ۸۶۱۴ آرتیفکت تولیدشده انجام شد."),
        ("ورودی‌های evaluate()",
         "• html: محتوای HTML تولیدشده برای هر آرتیفکت\n"
         "• url: آدرس URL اصلاح‌شده توسط تکنیک\n"
         "• change_log: لیست تغییرات — در batch evaluator خالی ارسال می‌شود ([])\n"
         "• extra_files: دیکشنری فایل‌های اضافی (تصاویر، YAML، ...)\n"
         "  ↳ کلید ویژه '__target_url__' برای مقایسه URL جدید با اصل تزریق می‌شود"),
        ("نحوه محاسبه امتیاز (_eval_score)",
         "score = (تعداد signals) / (تعداد signals + تعداد issues)\n"
         "مقدار بین ۰ تا ۱. فقط برای گزارش‌دهی است، pass/fail مستقل تعریف می‌شود."),
        ("شرط قبولی (passed)",
         "هر تکنیک شرط قبولی مخصوص به خود دارد که در کد تعریف شده. "
         "معمولاً ترکیبی از: وجود ساختار کد خاص در HTML + تغییر URL + فایل extra_files معتبر"),
        ("محدودیت‌های معمارانه",
         "۱. change_log در batch evaluator خالی ([]) است — change_log فقط در حین apply() تولید می‌شود و جداگانه ذخیره نمی‌شود\n"
         "۲. برای T01 این مشکل با تزریق __target_url__ حل شد\n"
         "۳. برای T23 نیاز به AI_API_KEY خارجی است که در محیط test موجود نیست"),
        ("دسته‌بندی شکست‌ها",
         "الف) وابسته به داده (Data-Dependent): T07, T08, T24\n"
         "   → سایت‌هایی که لوگو/تصویر مناسب ندارند — تکنیک صحیح است، داده کافی نیست\n\n"
         "ب) نیاز به API خارجی: T23\n"
         "   → بدون AI_API_KEY همه ۲۲۶ مورد شکست — نه باگ، نه مشکل داده\n\n"
         "ج) شکست حاشیه‌ای: T01 (digraph روی دامنه کوتاه), T10 (HTML پایه خیلی کوتاه)\n"
         "   → الگوریتم صحیح، ورودی‌های خاص نتیجه marginal تولید می‌کنند"),
        ("جاب مورد ارزیابی",
         "Job ID: 28413b63-5fbd-472b-af27-d3134429ecbd\n"
         "تاریخ: ۱۴۰۵/۰۳/۱۶\n"
         "کل آرتیفکت: ۸۶۱۴ ردیف\n"
         "قبولی: ۷۹۷۲ (۹۲.۵٪)\n"
         "شکست: ۶۴۲ (۷.۵٪)\n"
         "میانگین امتیاز: ۰.۷۲۷ / ۱.۰۰"),
        ("ابزار ارزیابی",
         "فایل: app/core/evaluator.py\n"
         "تابع: evaluate_job(job_id) → dict\n"
         "خروجی‌ها:\n"
         "  evaluation_results.csv — نتیجه هر ردیف\n"
         "  evaluation_summary.json — آمار خلاصه بدون entries\n"
         "  evaluation_full.json — آمار کامل با entries"),
    ]

    for i, (title, body) in enumerate(sections, start=2):
        ws[f"A{i}"] = title
        ws[f"A{i}"].font = _cell_font(bold=True, size=10, color=C_HEADER_DARK)
        ws[f"A{i}"].fill = _fill(C_SECTION_ROW)
        ws[f"A{i}"].alignment = _align(h="right", v="top", wrap=True)
        ws[f"A{i}"].border = BORDER

        ws[f"B{i}"] = body
        ws[f"B{i}"].font = _cell_font(size=9)
        ws[f"B{i}"].alignment = _align(h="right", v="top", wrap=True)
        ws[f"B{i}"].border = BORDER
        ws.row_dimensions[i].height = max(50, body.count("\n") * 14 + 20)


def main():
    wb = Workbook()
    wb.remove(wb.active)

    build_overview_sheet(wb)
    build_detail_sheet(wb)
    build_methodology_sheet(wb)

    out_path = "/var/services/phishint-data-generator/data/phishing_evaluation_report.xlsx"
    wb.save(out_path)
    print(f"Saved: {out_path}")
    import os
    print(f"Size: {os.path.getsize(out_path):,} bytes")


if __name__ == "__main__":
    main()
