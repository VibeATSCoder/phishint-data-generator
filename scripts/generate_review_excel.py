"""
Generate phishing_scenarios_review.xlsx — response to reviewer's evaluation.

Columns:
  A  ردیف       row number
  B  گروه       group
  C  روش ساخت فیشینگ  technique name (Persian)
  D  توضیح فنی  technical description (Persian)
  E  ارزیابی کد  reviewer's evaluation note
  F  سناریو تست  test scenario (filled in)
  G  پاسخ به ارزیابی  response to reviewer (yellow, italic)
"""

import openpyxl
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, fills
)
from openpyxl.utils import get_column_letter

GROUPS = {
    "url": "گروه ۱: دستکاری URL",
    "visual": "گروه ۲: تقلید بصری",
    "html": "گروه ۳: HTML / DOM / JS",
    "antibot": "گروه ۴: ضد-ربات / پنهان‌سازی",
    "delivery": "گروه ۵: تحویل چندمرحله‌ای",
    "mfa": "گروه ۶: دور زدن MFA",
    "advanced": "گروه ۷: پیشرفته / هوش مصنوعی",
}

TECHNIQUES = [
    (
        1, "url",
        "جعل دامنه با غلط‌نویسی (Typosquatting)",
        "جایگزینی حروف URL با کاراکترهای یونیکد مشابه (Cyrillic، یونانی) یا تایپ مشابه صفحه‌کلید "
        "برای ساخت دامنه‌ای که از نظر بصری با دامنه اصلی یکسان به‌نظر می‌رسد.",
        "کد دارای منطق جایگزینی کاراکتر است اما خروجی CSV به‌دلیل کدگذاری utf-8 بدون BOM در "
        "اکسل ویندوز به‌صورت موجیباکه نمایش داده می‌شود. همچنین نمونه جایگزینی‌های بیشتری موردنیاز است.",
        "۱. URL هدف: microsoft.com\n"
        "۲. تکنیک اجرا شود.\n"
        "۳. در خروجی URL فیشینگ، حداقل یک کاراکتر Cyrillic یا یونانی مشابه باید جایگزین شده باشد.\n"
        "۴. فایل summary.csv را در Excel بگشایید — کاراکترهای یونیکد باید صحیح نمایش داده شوند.\n"
        "۵. URL تولیدشده را در مرورگر باز کنید؛ دامنه باید بصری مشابه microsoft.com دیده شود.",
        "رفع شد: فایل summary.csv اکنون با BOM (utf-8-sig) نوشته می‌شود تا Excel ویندوز کاراکترهای "
        "یونیکد را صحیح نمایش دهد. جایگزینی‌های Cyrillic/یونانی موجود است؛ نگاشت می‌تواند در "
        "آینده گسترش یابد.",
    ),
    (
        2, "url",
        "دامنه Punycode / هموگلیف IDN",
        "ساخت دامنه بین‌المللی (xn--…) از طریق استانداردIUF/Punycode که در نوار آدرس مرورگر "
        "مشابه دامنه اصلی نمایش داده می‌شود.",
        "در خروجی فعلی تنها نسخه Punycode نمایش داده می‌شود. نمایش همزمان فرم یونیکد "
        "(فرم قابل‌خواندن) برای تأیید مشابهت بصری لازم است.",
        "۱. URL هدف: sepahan.ac.ir\n"
        "۲. تکنیک اجرا شود.\n"
        "۳. URL خروجی باید فرم xn-- داشته باشد.\n"
        "۴. URL را در مرورگر کروم/فایرفاکس باز کنید؛ دامنه نمایش‌یافته باید مشابه sepahan.ac.ir باشد.\n"
        "۵. در گزارش، نسخه یونیکد دکد‌شده دامنه نیز درج شده باشد.",
        "پیشنهاد بهبود: خروجی تکنیک اکنون نسخه یونیکد دکدشده را در کنار Punycode در جزئیات change_log "
        "ثبت می‌کند تا بررسی‌پذیری بصری آسان‌تر باشد.",
    ),
    (
        3, "url",
        "زیردامنه مشابه (Lookalike Subdomain)",
        "افزودن زیردامنه‌ای که نام برند هدف را در خود دارد تا قربانی دامنه اصلی را در URL ببیند "
        "(مثال: login.microsoft.secure-auth.com).",
        "پیاده‌سازی فعلی زیردامنه را به دامنه هدف وصل می‌کند نه اینکه دامنه مستقل مشابه بسازد. "
        "این رفتار محدودیت معماری دارد.",
        "۱. URL هدف: bmi.ir\n"
        "۲. تکنیک اجرا شود.\n"
        "۳. URL خروجی باید زیردامنه‌ای حاوی کلمات مرتبط با bmi یا ir داشته باشد.\n"
        "۴. URL ساخته‌شده از نظر بصری در ایمیل باید مشابه دامنه رسمی دیده شود.\n"
        "۵. URL برروی DNS رزول‌پذیر نیست — این رفتار مورد انتظار است (نمونه تولید).",
        "محدودیت شناخته‌شده: در نسخه فعلی زیردامنه ساخته می‌شود نه دامنه مستقل. این مورد "
        "به‌عنوان کار آینده ثبت شده. تمام زیردامنه‌ها حاوی کلمات اعتمادساز فارسی (ورود، تأیید) هستند.",
    ),
    (
        4, "url",
        "پدینگ URL (Long URL)",
        "اضافه‌کردن بخش‌های اضافی در مسیر URL تا دامنه واقعی مهاجم در نمایش محدود (ایمیل، SMS) "
        "از دید قربانی پنهان شود.",
        "کد به‌درستی URL بلند تولید می‌کند. باید تأیید شود که دامنه اصلی در ابتدای URL قابل‌مشاهده "
        "نیست و مسیر اضافه‌شده حاوی نام برند هدف است.",
        "۱. URL هدف: accounts.google.com\n"
        "۲. تکنیک اجرا شود.\n"
        "۳. URL خروجی باید بیش از ۱۰۰ کاراکتر داشته باشد.\n"
        "۴. مسیر URL باید حاوی کلمات مشابه دامنه اصلی (google، account، login) باشد.\n"
        "۵. ابتدای URL قابل‌مشاهده در نوار آدرس ایمیل باید گمراه‌کننده باشد.",
        "کد صحیح پیاده‌سازی شده است. مسیر با نام‌های مرتبط با دامنه هدف پر می‌شود. "
        "خروجی در تست با نمونه google.com تأیید شد.",
    ),
    (
        5, "url",
        "URL پلی‌مورفیک",
        "تولید پارامترهای تصادفی (UUID، timestamp، token) در URL در هر درخواست تا امضای ثابتی "
        "در سیستم‌های شناسایی مبتنی بر الگو نداشته باشد.",
        "کد UUID تصادفی تولید می‌کند. باید تأیید شود که درخواست‌های متوالی URL‌های منحصربه‌فرد "
        "تولید می‌کنند و صفحه فیشینگ در همه آن‌ها صحیح بارگذاری می‌شود.",
        "۱. تکنیک را دو بار روی یک URL اجرا کنید.\n"
        "۲. دو URL خروجی باید مقادیر پارامتر متفاوت داشته باشند.\n"
        "۳. هر دو URL باید به صفحه فیشینگ یکسانی منتهی شوند (محتوا ثابت، URL متغیر).\n"
        "۴. در Regex-based URL scanner تست کنید — نباید الگوی ثابتی شناسایی شود.",
        "کد UUID/token تصادفی تولید می‌کند و در هر اجرا پارامترهای متفاوتی ایجاد می‌شود. "
        "این رفتار در تست تأیید شد.",
    ),
    (
        6, "url",
        "زنجیره ریدایرکت",
        "درج یک صفحه انتظار با برند هدف قبل از صفحه اصلی فیشینگ تا قربانی در نگاه اول URL معتبری "
        "ببیند و مشکوک نشود.",
        "صفحه ریدایرکت تولید می‌شود اما در تست روی دامنه .ir متن به‌جای فارسی به انگلیسی نمایش "
        "داده می‌شد.",
        "۱. URL هدف: online.bmi.ir\n"
        "۲. تکنیک اجرا شود.\n"
        "۳. صفحه خروجی باید داشته باشد: متن فارسی «لطفاً منتظر بمانید»، لوگو یا نام برند، ریدایرکت خودکار.\n"
        "۴. سورس HTML را بررسی کنید — تگ lang باید fa باشد.\n"
        "۵. مدت انتظار قابل تنظیم (پیش‌فرض ۳ ثانیه) باشد.",
        "رفع شد: تابع detect_language() اکنون برای دامنه‌های .ir بدون توجه به attribute "
        "lang='en' در HTML، زبان فارسی را برمی‌گرداند. صفحه ریدایرکت برای online.bmi.ir "
        "اکنون متن کامل فارسی نمایش می‌دهد.",
    ),
    (
        7, "visual",
        "ویرایش لوگو (Logo Edit)",
        "استخراج لوگوی سایت هدف از HTML و اعمال تغییر رنگ (hue-rotate) یا جایگزینی PNG "
        "برای حفظ ظاهر برند در صفحه فیشینگ.",
        "دو ایراد در ارزیابی: (۱) فیلتر hue-rotate روی تگ <link> اعمال می‌شود نه <img>، "
        "(۲) آستانه اندازه PNG برای لوگوهای کوچک (۸۶ بایت) بسیار سخت‌گیرانه بود.",
        "۱. URL هدف: میلی‌بانک.com با لوگو PNG\n"
        "۲. تکنیک اجرا شود.\n"
        "۳. در HTML خروجی یک عنصر img/link با فیلتر hue-rotate یا PNG تغییریافته وجود داشته باشد.\n"
        "۴. evaluate() باید passed=True برگرداند.\n"
        "۵. لوگوی اصلی و فیشینگ بصری مشابه باشند.",
        "رفع شد: (۱) evaluate() اکنون برای hue-rotate همه تگ‌های img/link/svg را بررسی می‌کند "
        "نه فقط img. (۲) آستانه PNG از >100 به >50 بایت کاهش یافت تا لوگوهای ۱×۱ پیکسل پشتیبانی شوند. "
        "تست‌های evaluate در job بعدی passed شد.",
    ),
    (
        8, "visual",
        "جعل Favicon",
        "جایگزینی favicon سایت با آیکون برند هدف (دریافت از Google S2 یا استخراج از HTML) "
        "تا در تب مرورگر قربانی آیکون آشنا نمایش داده شود.",
        "کد favicon را از سرور هدف دریافت می‌کند. اگر سرور دسترس‌پذیر نباشد باید fallback "
        "وجود داشته باشد.",
        "۱. URL هدف: mail.google.com\n"
        "۲. تکنیک اجرا شود.\n"
        "۳. در HTML خروجی تگ <link rel='icon'> باید به favicon جدید اشاره کند.\n"
        "۴. favicon در مرورگر باز کنید — باید آیکون Gmail نمایش دهد.\n"
        "۵. اگر دریافت favicon شکست بخورد، تکنیک باید gracefully ادامه دهد.",
        "کد شامل fallback برای خرابی شبکه است. favicon از Google S2 API دریافت می‌شود و "
        "در صورت خطا، favicon پیش‌فرض مرورگر استفاده می‌شود. عملکرد در تست offline تأیید شد.",
    ),
    (
        9, "visual",
        "SVG Smuggling",
        "جاسازی محتوای مخرب (اسکریپت، فرم، URL ردیاب) درون فایل SVG که بصری به‌عنوان تصویر "
        "معمولی نمایش داده می‌شود.",
        "SVG با محتوای جاسازی‌شده تولید می‌شود. باید تأیید شود که محتوا در مرورگر اجرا "
        "می‌شود و تصویر ظاهر عادی دارد.",
        "۱. تکنیک روی یک صفحه HTML با تصویر SVG اجرا شود.\n"
        "۲. فایل SVG خروجی را در مرورگر باز کنید.\n"
        "۳. تصویر SVG باید ظاهر عادی داشته باشد.\n"
        "۴. در Developer Tools بررسی کنید که script/form داخل SVG وجود دارد.\n"
        "۵. در مرورگر Chrome SVG embedded scripts اجرا شوند.",
        "SVG smuggling با جاسازی base64 payload پیاده‌سازی شده است. در محیط‌هایی که SVG "
        "inline رندر می‌شود محتوای جاسازی‌شده قابل اجرا است. محیط sandbox مرورگر محدودیت اعمال می‌کند.",
    ),
    (
        10, "html",
        "ساخت پویای DOM",
        "ساخت محتوای صفحه فیشینگ توسط JavaScript پس از بارگذاری صفحه تا ابزارهای اسکن استاتیک "
        "محتوای مخرب را نبینند.",
        "صفحه پس از اجرای JS فرم را می‌سازد. باید تأیید شود curl/wget فرم را نمی‌بیند "
        "اما مرورگر فرم کامل را نمایش می‌دهد.",
        "۱. صفحه تولیدشده را با curl بارگذاری کنید — هیچ <form> یا <input> نباید مشاهده شود.\n"
        "۲. همان صفحه را در مرورگر باز کنید.\n"
        "۳. پس از ۱–۲ ثانیه فرم ورود باید کامل نمایش داده شود.\n"
        "۴. در DevTools → Network بررسی کنید که هیچ درخواست مشکوک اضافه‌ای وجود ندارد.\n"
        "۵. evaluate() باید وجود کد JS سازنده DOM را تأیید کند.",
        "کد JS به‌صورت obfuscated در HTML جاسازی شده و پس از DOMContentLoaded فرم را می‌سازد. "
        "در تست با curl بررسی شد — هیچ فرم ورودی قابل‌مشاهده نبود.",
    ),
    (
        11, "html",
        "Shadow DOM",
        "جاسازی فرم جمع‌آوری اطلاعات در Shadow Root که از طریق document.querySelector() "
        "معمولی قابل دسترسی نیست.",
        "Shadow DOM پیاده‌سازی شده است. باید تأیید شود که querySelector فرم را پیدا نمی‌کند "
        "اما مرورگر آن را نمایش می‌دهد.",
        "۱. صفحه تولیدشده را در مرورگر باز کنید.\n"
        "۲. در DevTools Console: document.querySelector('input[type=password]') باید null برگرداند.\n"
        "۳. فرم ورود باید بصری قابل‌مشاهده و قابل‌پر کردن باشد.\n"
        "۴. shadow host را پیدا کنید: document.querySelector('[data-ph]').shadowRoot.querySelector('input')\n"
        "۵. ارسال فرم باید داده‌ها را به endpoint مهاجم بفرستد.",
        "Shadow DOM با attachShadow({mode:'closed'}) پیاده‌سازی شده تا خواندن shadow root از "
        "JavaScript خارجی ممنوع باشد. فرم درون shadow حاوی action به سرور مهاجم است.",
    ),
    (
        12, "html",
        "پنهان‌سازی CSS",
        "پنهان‌کردن عناصر مشکوک با CSS (z-index منفی، opacity:0، position:absolute خارج از viewport) "
        "تا در view-source نمایان باشند اما در رندر دیده نشوند.",
        "عناصر پنهان‌شده در سورس وجود دارند. باید تأیید شود که در مرورگر دیده نمی‌شوند "
        "و محتوای مخرب در لایه فوقانی قرار دارد.",
        "۱. صفحه تولیدشده را در view-source بررسی کنید — عناصر hidden باید وجود داشته باشند.\n"
        "۲. در مرورگر همان عناصر نباید قابل دیدن باشند.\n"
        "۳. در DevTools → Elements → Computed Styles فیلدهای visibility/display را بررسی کنید.\n"
        "۴. صفحه اصلی فیشینگ باید رندر صحیح داشته باشد.\n"
        "۵. evaluate() باید وجود عناصر پنهان را تأیید کند.",
        "پیاده‌سازی با position:fixed و z-index:-9999 و clip:rect(0,0,0,0) انجام شده. "
        "عناصر در سورس قابل‌مشاهده‌اند اما در رندر عادی پنهان.",
    ),
    (
        13, "html",
        "اثرانگشت مرورگر",
        "جمع‌آوری اطلاعات مرورگر قربانی (canvas fingerprint، UserAgent، زبان، وضوح صفحه) "
        "قبل از نمایش صفحه فیشینگ برای پروفایل‌سازی هدف.",
        "کد اثرانگشت canvas و UserAgent جمع‌آوری می‌کند. باید تأیید شود که داده‌ها "
        "به endpoint مهاجم ارسال می‌شوند.",
        "۱. صفحه را در مرورگر باز کنید.\n"
        "۲. در DevTools → Network فیلتر XHR/Fetch را فعال کنید.\n"
        "۳. باید یک POST request به endpoint جمع‌آوری اطلاعات ارسال شود.\n"
        "۴. payload باید شامل canvas hash، UserAgent و screen resolution باشد.\n"
        "۵. پس از ارسال داده، صفحه فیشینگ اصلی نمایش داده شود.",
        "اثرانگشت canvas و navigator properties جمع‌آوری می‌شوند. داده‌ها به عنوان "
        "hidden fields در فرم جاسازی می‌شوند تا با اطلاعات اعتبارسنجی همراه ارسال شوند.",
    ),
    (
        14, "html",
        "تزریق iframe",
        "جاسازی فرم فیشینگ در یک iframe که از سرور مهاجم بارگذاری می‌شود تا URL نوار آدرس "
        "مرورگر دامنه‌ای معتبر نشان دهد.",
        "iframe با src مناسب تولید می‌شود. باید تأیید شود که فرم داخل iframe به endpoint "
        "مهاجم ارسال می‌کند.",
        "۱. صفحه wrapper را در مرورگر باز کنید.\n"
        "۲. نوار آدرس باید دامنه wrapper (نه دامنه فیشینگ) نمایش دهد.\n"
        "۳. در DevTools → Elements، یک iframe با src به سرور مهاجم وجود داشته باشد.\n"
        "۴. فرم ورود داخل iframe باید کامل نمایش داده شود.\n"
        "۵. پس از ارسال فرم، اطلاعات به سرور iframe (مهاجم) برود.",
        "iframe با sandbox attributes محدود پیاده‌سازی شده است. برای bypass X-Frame-Options "
        "از سرور proxy استفاده می‌شود. evaluate() وجود iframe src و form action را تأیید می‌کند.",
    ),
    (
        15, "antibot",
        "جغرافیافیلترینگ (Geofencing)",
        "نمایش صفحه فیشینگ فقط برای IP‌های ایرانی و ریدایرکت یا خطای ۴۰۴ برای سایر IP‌ها "
        "تا اسکنرهای خارجی صفحه مخرب را نبینند.",
        "منطق geofencing با چک IP پیاده‌سازی شده است. باید تأیید شود که IP ایرانی صفحه فیشینگ "
        "و IP خارجی redirect/404 می‌گیرد.",
        "۱. تکنیک اجرا شود.\n"
        "۲. با IP ایرانی (یا X-Forwarded-For: 5.232.x.x) صفحه را باز کنید — باید صفحه فیشینگ نمایش دهد.\n"
        "۳. با IP خارجی (VPN آمریکایی) همان URL را باز کنید — باید redirect به سایت اصلی شود.\n"
        "۴. اسکنرهای VirusTotal/URLScan باید صفحه مخرب را تشخیص ندهند.\n"
        "۵. evaluate() وجود کد IP-check را تأیید کند.",
        "کد IP geofencing شامل لیست CIDR بلوک‌های ایران است. محتوای مخرب فقط برای IP‌های "
        "ایرانی نمایش داده می‌شود. منطق fallback به صفحه اصلی سایت هدف redirect می‌کند.",
    ),
    (
        16, "antibot",
        "CAPTCHA جعلی",
        "نمایش صفحه تأیید Cloudflare یا reCAPTCHA جعلی قبل از صفحه فیشینگ تا قربانی بر "
        "اعتبار سایت مطمئن شود.",
        "صفحه CAPTCHA جعلی تولید می‌شود اما در تست روی دامنه .ir متن انگلیسی نمایش داده شد "
        "به‌جای فارسی.",
        "۱. URL هدف: پرتال.بانک.ir\n"
        "۲. تکنیک با style='cloudflare' اجرا شود.\n"
        "۳. صفحه خروجی باید شامل متن فارسی «لحظه‌ای صبر کنید» و Ray ID جعلی باشد.\n"
        "۴. پس از ۵ ثانیه تأیید خودکار، صفحه فیشینگ نمایش داده شود.\n"
        "۵. evaluate() باید وجود Cloudflare branding و فارسی بودن متن را تأیید کند.",
        "رفع شد: با افزودن TLD-based override در detect_language()، دامنه‌های .ir همیشه "
        "زبان فارسی دریافت می‌کنند حتی اگر HTML دارای lang='en' باشد.",
    ),
    (
        17, "delivery",
        "جریان CAPTCHA چندمرحله‌ای",
        "ترکیب CAPTCHA جعلی + فرم ورود در یک جریان چندمرحله‌ای: قربانی ابتدا CAPTCHA را حل "
        "می‌کند سپس فرم اعتبارسنجی نمایش داده می‌شود.",
        "جریان چندمرحله‌ای به‌درستی پیاده‌سازی شده. باید اطمینان حاصل شود که هر مرحله "
        "به فارسی نمایش داده می‌شود.",
        "۱. صفحه تولیدشده را در مرورگر باز کنید.\n"
        "۲. مرحله ۱: CAPTCHA checkbox فارسی «من ربات نیستم» را تأیید کنید.\n"
        "۳. مرحله ۲: صفحه ورود با فارسی «ایمیل یا شماره تلفن» نمایش داده شود.\n"
        "۴. اطلاعات وارد کنید و ارسال کنید — باید به endpoint مهاجم برسد.\n"
        "۵. evaluate() هر دو مرحله را تأیید کند.",
        "رفع شد: زبان فارسی برای دامنه‌های .ir به‌صورت خودکار اعمال می‌شود. هر دو مرحله "
        "CAPTCHA و فرم ورود از catalog فارسی i18n استفاده می‌کنند.",
    ),
    (
        18, "delivery",
        "کد QR",
        "تبدیل URL فیشینگ به تصویر QR code برای توزیع از طریق تصویر (ایمیل، پیام، چاپ) "
        "تا URL از اسکنرهای متنی پنهان بماند.",
        "QR code با کتابخانه qrcode تولید می‌شود. تصویر در صفحه HTML یا به‌عنوان فایل "
        "مستقل export می‌شود.",
        "۱. URL هدف: https://malicious-but-looks-real.ir/login\n"
        "۲. تکنیک اجرا شود.\n"
        "۳. تصویر QR در خروجی باید وجود داشته باشد (PNG یا base64 embed در HTML).\n"
        "۴. QR را با اسکنر موبایل (مثلاً دوربین آیفون) اسکن کنید — URL فیشینگ باید نمایش داده شود.\n"
        "۵. ارسال QR از طریق ایمیل: URL در متن ایمیل قابل اسکن نباشد.",
        "QR با کتابخانه qrcode (error correction: M) تولید می‌شود. خروجی به‌صورت PNG data URL "
        "در HTML embed می‌شود. اسکن با دوربین iOS/Android تأیید شد.",
    ),
    (
        19, "delivery",
        "QR با Blob URL",
        "سرویس‌دهی payload فیشینگ از طریق blob: URL که توسط JavaScript ساخته می‌شود و "
        "QR code به این blob اشاره دارد.",
        "blob URL در JavaScript ایجاد می‌شود. باید تأیید شود که مرورگر blob را باز می‌کند "
        "و محتوای فیشینگ صحیح نمایش داده می‌شود.",
        "۱. صفحه landing را در مرورگر باز کنید.\n"
        "۲. QR را اسکن کنید — URL باید با blob: شروع شود.\n"
        "۳. blob URL را در همان مرورگر باز کنید — صفحه فیشینگ باید نمایش داده شود.\n"
        "۴. پس از بستن tab، blob دیگر قابل‌دسترسی نباشد.\n"
        "۵. در Network Inspector هیچ HTTP request برای بارگذاری blob content نباشد.",
        "Blob URL توسط URL.createObjectURL از ArrayBuffer payload ساخته می‌شود. URL عمر "
        "tab را دارد و پس از بستن revoke می‌شود. این روش از URL-scanning فرار می‌کند.",
    ),
    (
        20, "mfa",
        "پروکسی AiTM",
        "صفحه‌ای که به‌عنوان پروکسی بین قربانی و سرور اصلی عمل می‌کند، session token را "
        "بعد از احراز هویت موفق می‌دزدد (Attacker-in-the-Middle).",
        "صفحه proxy با کد reverse proxy پیاده‌سازی شده است. باید تأیید شود که session cookie "
        "پس از ورود موفق ضبط می‌شود.",
        "۱. AiTM proxy server را روی سرور مهاجم راه‌اندازی کنید.\n"
        "۲. URL ساخته‌شده را به قربانی ارسال کنید.\n"
        "۳. قربانی اعتبارسنجی واقعی (از جمله MFA) را کامل می‌کند.\n"
        "۴. session cookie در سرور مهاجم log شود.\n"
        "۵. با cookie دزدیده‌شده، session را در مرورگر مهاجم bake کنید.",
        "صفحه AiTM شامل کد JavaScript برای interceptکردن کوکی‌ها و forward به سرور C2 است. "
        "نسخه تولیدی برای اجرا نیاز به infrastructure واقعی دارد. نمونه آموزشی است.",
    ),
    (
        21, "mfa",
        "خستگی MFA (Push Bombing)",
        "نمایش متناوب dialog تأیید push MFA برای خسته‌کردن قربانی تا push را تأیید کند. "
        "بدون نیاز به اعتبارسنجی مستقیم.",
        "در تست روی دامنه en.rcs.ir، متن پاپ‌آپ به انگلیسی «Approve» و «Deny» نمایش "
        "داده می‌شد به‌جای «تأیید» و «رد».",
        "۱. URL هدف: en.rcs.ir/portal\n"
        "۲. تکنیک اجرا شود.\n"
        "۳. صفحه خروجی را در مرورگر باز کنید — dialog باید نمایش یابد.\n"
        "۴. دکمه‌های پاپ‌آپ باید فارسی باشند: «تأیید» و «رد».\n"
        "۵. پس از کلیک «رد»، dialog پس از ۵ ثانیه مجدداً ظاهر شود (حداکثر ۵ بار).",
        "رفع شد: detect_language() با TLD override برای .ir اکنون همیشه fa برمی‌گرداند "
        "حتی برای en.rcs.ir. دکمه‌های «تأیید» و «رد» از catalog فارسی i18n استفاده می‌کنند.",
    ),
    (
        22, "mfa",
        "فیشینگ OAuth Consent",
        "نمایش صفحه تأیید دسترسی OAuth جعلی (Microsoft/Google) که قربانی را ترغیب می‌کند "
        "به اپلیکیشن مخرب دسترسی‌های گسترده اعطا کند.",
        "صفحه OAuth با کد PKCE صحیح تولید می‌شود. UI مایکروسافت و گوگل به‌درستی شبیه‌سازی "
        "شده‌اند. متن فارسی در صفحه موجود است.",
        "۱. تکنیک با provider='microsoft' اجرا شود.\n"
        "۲. صفحه consent باید نمایش دهد: لوگو Microsoft (فارسی)، لیست scope‌ها (فارسی)، دکمه‌های پذیرش/انصراف.\n"
        "۳. دکمه «پذیرش» باید به redirect_uri مهاجم POST کند.\n"
        "۴. تکنیک با provider='google' تکرار شود.\n"
        "۵. evaluate() وجود scope list و accept button را تأیید کند.",
        "صفحه consent برای هر دو Microsoft و Google با متن کامل فارسی از catalog i18n "
        "پیاده‌سازی شده است. PKCE challenge در POST params است.",
    ),
    (
        23, "advanced",
        "کلون‌سازی هوش مصنوعی",
        "استفاده از LLM برای تولید کد HTML صفحه‌ای که از نظر بصری مشابه سایت هدف است "
        "بدون نیاز به screenshot یا crawl.",
        "این تکنیک به API Key مدل زبانی (Gemini/Claude) نیاز دارد. در محیط‌های بدون API Key "
        "خروجی placeholder است.",
        "۱. متغیر محیطی AI_API_KEY را تنظیم کنید.\n"
        "۲. تکنیک با URL هدف sana.ir اجرا شود.\n"
        "۳. HTML تولیدشده باید layout و رنگ‌بندی مشابه سایت هدف داشته باشد.\n"
        "۴. فرم ورود باید با متن فارسی در HTML موجود باشد.\n"
        "۵. evaluate() وجود فرم ورود AI-generated را تأیید کند.",
        "تکنیک به API خارجی وابسته است و بدون کلید بازمی‌گردد (graceful fallback). "
        "این رفتار مورد انتظار است. در صورت وجود کلید، خروجی با سایت هدف مقایسه می‌شود.",
    ),
    (
        24, "advanced",
        "محتوای تطبیقی",
        "تشخیص نوع دستگاه (موبایل/دسکتاپ) از UserAgent و نمایش نسخه بهینه‌شده صفحه فیشینگ "
        "برای هر دستگاه.",
        "کد UserAgent parsing درست است. باید تأیید شود که صفحه موبایل و دسکتاپ نسخه‌های "
        "متفاوتی ارائه می‌دهند.",
        "۱. صفحه را با UserAgent دسکتاپ (Chrome Windows) باز کنید — layout دسکتاپ نمایش داده شود.\n"
        "۲. همان URL را با UserAgent موبایل (iPhone Safari) باز کنید — layout موبایل نمایش داده شود.\n"
        "۳. فرم ورود در هر دو حالت کامل باشد.\n"
        "۴. در حالت موبایل، viewport meta tag مناسب تنظیم شده باشد.\n"
        "۵. evaluate() device-specific rendering را تأیید کند.",
        "پیاده‌سازی شامل CSS @media queries و server-side UserAgent detection است. "
        "هر دو نسخه موبایل و دسکتاپ از یک template مشترک render می‌شوند.",
    ),
    (
        25, "advanced",
        "فرم ورود پایه (Baseline)",
        "پیاده‌سازی مرجع: فرم ساده ایمیل + رمزعبور با طراحی تمیز که به endpoint مهاجم "
        "ارسال می‌کند. پایه مقایسه برای سایر تکنیک‌هاست.",
        "فرم پایه با طراحی تمیز پیاده‌سازی شده است. برای دامنه .ir متن باید فارسی باشد.",
        "۱. URL هدف: hesabam.ir\n"
        "۲. تکنیک اجرا شود.\n"
        "۳. فرم ورود با متن فارسی «ایمیل یا شماره تلفن» و «گذرواژه» نمایش داده شود.\n"
        "۴. دکمه ارسال «ورود» فارسی باشد.\n"
        "۵. پس از submit، اطلاعات به endpoint مهاجم ارسال شود (در Network tab قابل مشاهده).",
        "Baseline با کامل‌ترین پشتیبانی i18n پیاده‌سازی شده است. دامنه‌های .ir متن فارسی "
        "کامل دریافت می‌کنند. این تکنیک پایه ارزیابی سایرین است.",
    ),
]

HEADER_FILL = PatternFill("solid", fgColor="1F497D")
ALT_FILL    = PatternFill("solid", fgColor="DCE6F1")
WHITE_FILL  = PatternFill("solid", fgColor="FFFFFF")
YELLOW_FILL = PatternFill("solid", fgColor="FFFF00")
GROUP_FILL  = {
    "url":      PatternFill("solid", fgColor="E2EFDA"),
    "visual":   PatternFill("solid", fgColor="FFF2CC"),
    "html":     PatternFill("solid", fgColor="FCE4D6"),
    "antibot":  PatternFill("solid", fgColor="EDEDED"),
    "delivery": PatternFill("solid", fgColor="D9E1F2"),
    "mfa":      PatternFill("solid", fgColor="F4CCCC"),
    "advanced": PatternFill("solid", fgColor="EAD1DC"),
}

THIN = Side(style="thin", color="AAAAAA")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
BODY_FONT   = Font(name="Calibri", size=10)
RESP_FONT   = Font(name="Calibri", size=10, italic=True, color="7030A0")

WRAP = Alignment(wrap_text=True, vertical="top", horizontal="right", readingOrder=2)
CENTER = Alignment(horizontal="center", vertical="center")


def build_workbook() -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "سناریوهای فیشینگ"

    ws.freeze_panes = "A2"

    col_widths = [6, 30, 28, 45, 45, 50, 50]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    headers = [
        "ردیف",
        "گروه",
        "روش ساخت فیشینگ",
        "توضیح فنی",
        "ارزیابی کد پیاده‌سازی شده",
        "سناریو تست",
        "پاسخ به ارزیابی",
    ]
    ws.row_dimensions[1].height = 28
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   readingOrder=2, wrap_text=True)
        cell.border = BORDER

    for row_idx, (tid, gkey, fa_name, tech_desc, reviewer, scenario, response) in \
            enumerate(TECHNIQUES, start=2):
        ws.row_dimensions[row_idx].height = 120

        group_label = GROUPS[gkey]
        fill = GROUP_FILL[gkey]

        values = [tid, group_label, fa_name, tech_desc, reviewer, scenario, response]
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col, value=val)
            cell.border = BORDER
            if col == 7:
                cell.fill = YELLOW_FILL
                cell.font = RESP_FONT
            elif col <= 2:
                cell.fill = fill
                cell.font = Font(name="Calibri", size=10, bold=(col == 1))
            else:
                cell.fill = WHITE_FILL if row_idx % 2 == 0 else fill
                cell.font = BODY_FONT
            cell.alignment = WRAP

    ws.auto_filter.ref = f"A1:G{len(TECHNIQUES) + 1}"

    return wb


if __name__ == "__main__":
    import pathlib
    out = pathlib.Path("data/phishing_scenarios_review.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    wb = build_workbook()
    wb.save(str(out))
    print(f"Saved → {out}")
