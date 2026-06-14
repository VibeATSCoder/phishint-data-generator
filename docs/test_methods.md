# Per-Technique Test Methods

This document specifies how each of the 25 phishing-generation techniques
is verified. For every technique it gives:

- **Goal** - what the technique does in one sentence.
- **Sample input** - the minimal HTML/URL that exercises the happy path.
- **Expected behavior** - observable side-effects (HTML changes, URL
  mutations, extra files, `ChangeEntry.details` keys).
- **Manual verification steps** - what an operator does in the UI to
  confirm.
- **Automated test** - the path to the pytest module that asserts the
  same behavior programmatically.

All automated tests live under `tests/techniques/` and share the fixtures
in `tests/techniques/conftest.py` (`persian_login_html`, `english_login_html`,
`multi_form_html`, `spa_html`, `inline_svg_html`, `sample_url`, etc.).
Run the full suite with `pytest tests/techniques -v`.

---

## T01 - Homoglyph / Confusable Characters

**Goal:** Replace Latin chars in the base domain label with visually
similar Cyrillic/Greek code points.

**Sample input:** any `https://...` URL; HTML is ignored.

**Expected behavior:**
- `modified_url` differs from input.
- `details = {char_set, chars_replaced, label, mutate_subdomains, skipped_punycode}`.
- IPv6 hosts produce `url_domain_homoglyph_skipped` with `reason="ipv6_literal"`.
- Already-punycode labels are not double-encoded.

**Manual verification:**
1. Generate with T1 against `https://login.microsoft.com/`.
2. Inspect `report.md` → URL change line. Visually compare original and modified.
3. Confirm at least one character looks identical but isn't ASCII (Cyrillic `а` vs Latin `a`).

**Automated test:** `tests/techniques/test_t01_homoglyph.py`

---

## T02 - Punycode / IDN Homograph

**Goal:** Encode a Unicode-look-alike domain as `xn--…` so browsers render
the decoded glyphs while DNS sees ASCII.

**Sample input:** any URL.

**Expected behavior:**
- `modified_url` is ASCII-safe (`.encode('ascii')` doesn't raise).
- Per-label results in `details.labels_encoded` / `labels_skipped`.
- `mixed_script_only=true` keeps labels that received no substitution.
- IPv6 hosts skipped.

**Manual verification:**
1. Generate T2 against `https://shapourkhast.ir`.
2. Open the saved URL info file and confirm the `xn--` form.
3. Paste the URL into Chrome's address bar - Chrome should warn about IDN
   if mixed-script.

**Automated test:** `tests/techniques/test_t02_punycode.py`

---

## T03 - Look-alike Domains + Leetspeak + Trust Words

**Goal:** Inject a trust word (`login`, `secure`, …) as subdomain or path
and optionally leetify it.

**Expected behavior:**
- Persian-detected HTML → Persian transliterated trust words
  (`vorood`, `tayid`, etc.).
- `details = {trust_words, leet_words, leet_chars, strategy, label_modified}`.
- Strategy=`path` skips if path already contains a trust word.

**Manual verification:**
1. Generate T3 with strategy=`prepend` against an `.ir` site.
2. Confirm the modified URL starts with a Persian-transliterated word.

**Automated test:** `tests/techniques/test_t03_lookalike.py`

---

## T04 - Long URL + Random Hash Parameters

**Goal:** Append N random query parameters to inflate URL length / entropy.

**Expected behavior:**
- `details.params_added` ≥ 1, `final_url_len > len(input)`.
- URL fragment (`#…`) survives.
- Total length clamped to `_MAX_TOTAL_URL_LEN` (8192).

**Manual verification:**
1. Generate T4 with `param_count=8, param_length=32`.
2. Confirm the URL has 8+ random-looking query params.

**Automated test:** `tests/techniques/test_t04_long_url.py`

---

## T05 - Polymorphic URL Variations

**Goal:** Produce N distinct variants via n-gram/typo/path mutations.

**Expected behavior:**
- `details.variants` lists all of them and is duplicate-free.
- `extra_files["url_polymorphic_variants.txt"]` mirrors that list.

**Manual verification:**
1. Generate T5 with `variation_count=5`.
2. Download `url_polymorphic_variants.txt` and confirm 5 distinct URLs.

**Automated test:** `tests/techniques/test_t05_polymorphic.py`

---

## T06 - Multi-stage Redirect Chain

**Goal:** Build an HTML waiting page that bounces through N intermediate
hops before landing on the final URL.

**Expected behavior:**
- Persian-detected HTML → Persian "در حال انتقال…" waiting page (RTL,
  `lang="fa"`, `dir="rtl"`).
- `details.chain` lists every hop URL.
- Non-HTTP schemes (`javascript:`, `data:`) produce `url_redirect_skipped`.

**Manual verification:**
1. Generate T6 with `hop_count=3` against a Persian login page.
2. Open the produced HTML - the spinner + waiting text must be Persian.

**Automated test:** `tests/techniques/test_t06_redirect.py`

---

## T07 - Logo Pixel-Level Editing

**Goal:** Detect the brand logo and apply imperceptible pixel-level edits
that defeat perceptual-hash matching.

**Expected behavior:**
- Picker uses `find_brand_logo`: prefers `<link rel=apple-touch-icon>`,
  then `rel=icon`, then `<img class~="logo">`, then header/nav images.
- `details.picker` reports which heuristic matched.
- SVG assets get a CSS-filter hue-rotate fallback rather than silent skip.

**Manual verification:**
1. Generate T7 against a site with a `<link rel="apple-touch-icon">`.
2. Open `report.md`; `Details:` should show `picker: rel=apple-touch-icon`.

**Automated test:** `tests/techniques/test_t07_logo_edit.py`

---

## T08 - Favicon Mimicry

**Goal:** Clone or replace every `<link rel=*icon*>` variant on the page.

**Expected behavior:**
- All icon link variants updated (not just the first).
- Clearbit mode strips port/path/`www.` from the domain.
- `details = {links_found, links_updated, format_chain, …}`.

**Manual verification:**
1. Generate T8 with `use_clearbit=true` against a site that has both
   `apple-touch-icon` and `icon` links.
2. Confirm all icon hrefs point at the Clearbit URL in the output HTML.

**Automated test:** `tests/techniques/test_t08_favicon.py`

---

## T09 - SVG Smuggling

**Goal:** Embed JS inside an inline `<svg>` so static HTML scanners miss
the payload while browsers execute it.

**Expected behavior:**
- Payload landed inside `<script>` child of an `<svg>`.
- Unbalanced payloads rejected with `reason="payload_unbalanced"`.
- When no inline SVG exists, a hidden 1×1 SVG is created.

**Manual verification:**
1. Generate T9 against an HTML with `<svg>`.
2. Open output, grep for `<script>` inside `<svg>` - it must contain the
   `atob('…')` encoded payload.

**Automated test:** `tests/techniques/test_t09_svg_smuggling.py`

---

## T10 - Dynamic DOM Generation via JS

**Goal:** Base64-encode the body and rebuild it at runtime via JS.

**Expected behavior:**
- Output `<body>` is empty; `<head>` gets a loader script.
- Persian content survives the base64 round-trip (no mojibake).
- `details = {body_bytes_orig, body_bytes_encoded, stylesheets, scripts_external}`.

**Manual verification:**
1. Generate T10 against a Persian page.
2. Save the output, open in a browser - page must render identical
   Persian content after JS executes.

**Automated test:** `tests/techniques/test_t10_dynamic_dom.py`

---

## T11 - Shadow DOM Encapsulation

**Goal:** Move the login form into a closed shadow root, hiding it from
DOM queries.

**Expected behavior:**
- Picker selects the form with `<input type=password>` even when it isn't
  first on the page.
- `details = {forms_moved, picker, synthetic_form_built}`.
- Orphan password inputs (no parent form) get wrapped in a synthetic form.

**Manual verification:**
1. Generate T11 against the `multi_form_html` fixture.
2. In DevTools, run `document.querySelectorAll('form')` - search bar shows,
   login form is gone.

**Automated test:** `tests/techniques/test_t11_shadow_dom.py`

---

## T12 - CSS Hiding + Honeypot Fields

**Goal:** Inject N variants of honeypot forms with off-viewport CSS and
`aria-hidden`/`tabindex=-1`.

**Expected behavior:**
- `details.honeypots_injected == honeypot_variants` (configurable).
- Each honeypot carries `aria-hidden="true"` and `tabindex="-1"`.
- Real forms get a `.__pf__` class.

**Manual verification:**
1. Generate T12 with `honeypot_variants=3`.
2. View source - 3 hidden `<form>` blocks with off-viewport CSS should be
   appended before `</body>`.

**Automated test:** `tests/techniques/test_t12_css_hiding.py`

---

## T13 - Anti-bot Fingerprint

**Goal:** Inject JS that checks for headless-browser markers and either
redirects or blanks the page when detected.

**Expected behavior:**
- Injected JS calls `navigator.webdriver`, `navigator.plugins`,
  `navigator.languages`, canvas + WebGL probes, mouse/keyboard/touch.
- `details.checks_emitted` lists every check.
- `bot_redirect_url` flows through to the script.

**Manual verification:**
1. Generate T13.
2. Open output in Playwright headless (via the project's screenshot
   service) - page should redirect/blank.
3. Open in a normal browser - page renders normally.

**Automated test:** `tests/techniques/test_t13_fingerprint.py`

---

## T14 - Hidden iframes

**Goal:** Inject 1-pixel hidden iframes with a postMessage listener.

**Expected behavior:**
- Blank `iframe_src` is derived as `urljoin(url, '/login')`.
- Default hide strategy is `clip-path: inset(100%)`.
- `details = {src, count, hide_strategy, listener_wired}`.

**Manual verification:**
1. Generate T14 with empty `iframe_src`.
2. View source - `<iframe id="__ghost_frame_0__">` present with a
   meaningful src.

**Automated test:** `tests/techniques/test_t14_iframe.py`

---

## T15 - Geo / UA / Timezone Fencing

**Goal:** Block crawlers + non-target visitors via UA, language, timezone.

**Expected behavior:**
- Injected JS includes the expanded bot list (`googlebot`, `bingbot`,
  `mj12bot`, `scrapy`, `okhttp`, etc.).
- `mode=redirect` injects `decoy_url`; `mode=show_decoy` swaps body HTML.
- `details.checks` lists `ua`, `lang`, `tz`, `webrtc` as applicable.

**Manual verification:**
1. Generate T15 with mode=`redirect` and a decoy URL.
2. Set Chrome UA to `Googlebot/2.1` (DevTools → Network conditions).
3. Reload - page must redirect to the decoy.

**Automated test:** `tests/techniques/test_t15_geofence.py`

---

## T16 - Fake CAPTCHA Overlay

**Goal:** Overlay a fake Cloudflare/reCAPTCHA screen that scanners can't
scroll past.

**Expected behavior:**
- Persian source HTML → Persian overlay text ("لحظه‌ای صبر کنید…",
  "بررسی مرورگر شما", …).
- `position:fixed; inset:0` forced; `overflow:hidden` on `html,body` when
  `scroll_lock=true`.
- Unknown vendor names fall back to `cloudflare` with a warning log.

**Manual verification:**
1. Generate T16 against a Persian page.
2. Open output - verify the Cloudflare clone displays Persian text and
   covers the entire viewport.

**Automated test:** `tests/techniques/test_t16_fake_captcha.py`

---

## T17 - Multi-stage CAPTCHA Flow

**Goal:** Produce a stage-1 CAPTCHA page + stage-2 credential page in
matching language.

**Expected behavior:**
- Stage-2 filename derived from URL path (no hardcoded names).
- Both files in `extra_files`.
- Persian source → Persian stage 1 ("یک مرحله دیگر") + stage 2 form labels.

**Manual verification:**
1. Generate T17 against a Persian site.
2. Open both `*_step1.html` and `*_step2.html` - verify Persian content
   on both, and that stage 1 redirects to stage 2 by name.

**Automated test:** `tests/techniques/test_t17_captcha_flow.py`

---

## T18 - QR Code (Quishing)

**Goal:** Generate a scannable QR + ASCII QR pointing at the phishing URL.

**Expected behavior:**
- `error_correction="auto"` tunes by URL length (H ≤100, Q ≤250, M >250).
- Unknown EC values produce `qr_skipped` change_log entry.
- `extra_files["qr_url_for_email.txt"]` carries the plain URL (email
  clients strip `data:` URIs).

**Manual verification:**
1. Generate T18 with `error_correction=auto`.
2. Scan the PNG with a phone - it should open the phishing URL.

**Automated test:** `tests/techniques/test_t18_qr_code.py`

---

## T19 - Blob URI Dynamic QR

**Goal:** Same as T18 but the QR is created at runtime as a Blob URI.

**Expected behavior:**
- Script branches on Safari UA (uses `data:` URI fallback).
- `<noscript>` block embeds a static fallback `<img src="data:...">`.
- Persian source → "برای ادامه اسکن کنید" label.

**Manual verification:**
1. Generate T19, open in Chrome - QR renders normally.
2. Disable JS, reload - `<noscript>` fallback img must show.

**Automated test:** `tests/techniques/test_t19_blob_qr.py`

---

## T20 - AiTM / Evilginx Proxy Config

**Goal:** Emit `evilginx_phishlet.yaml` + `nginx_proxy_snippet.conf`
covering the target's auth flow.

**Expected behavior:**
- nginx snippet contains the WebSocket upgrade block
  (`proxy_set_header Upgrade $http_upgrade`).
- Multi-domain aliases land in `server_name`.
- `details = {base_domain, subdomains, alias_count, ws_enabled, port}`.

**Manual verification:**
1. Generate T20 against `https://login.microsoft.com/`.
2. Open the nginx snippet - confirm WebSocket upgrade block present.

**Automated test:** `tests/techniques/test_t20_aitm_proxy.py`

---

## T21 - MFA Fatigue / Push Bombing

**Goal:** Inject a repeating MFA-approval popup with spoofed device
context.

**Expected behavior:**
- JS calls `clearInterval` once `__mfaCount >= __mfaMax` (no runaway).
- Persian source → Persian modal ("تأیید درخواست ورود").
- `details` carries `device_name`, `device_location`, `spoofed_ip`.

**Manual verification:**
1. Generate T21 with `max_prompts=3`.
2. Open output in a browser - popup appears at most 3 times, then stops.

**Automated test:** `tests/techniques/test_t21_mfa_fatigue.py`

---

## T22 - OAuth Consent Phishing

**Goal:** Build a Microsoft/Google-style consent page requesting broad
permissions.

**Expected behavior:**
- Real MS Graph scope IDs (`Mail.ReadWrite`, `offline_access`, …) kept
  verbatim in hidden form fields; human descriptions localised.
- Form is POST with PKCE hidden fields (`code_challenge`,
  `code_challenge_method`).
- Persian source → Persian heading/instructions/buttons; English source
  → English.

**Manual verification:**
1. Generate T22 against `https://login.microsoftonline.com/` with a
   Persian source page.
2. Open output - every visible string is Persian; scope IDs in form
   POST stay Latin.

**Automated test:** `tests/techniques/test_t22_oauth.py`

---

## T23 - AI Full-Page Cloning

**Goal:** Refine the HTML clone via an LLM (Claude / OpenAI-compatible).

**Expected behavior:**
- No API key supplied → `ai_cloning_skipped` change_log entry, no crash.
- `max_html_chars` budget picked per model (claude-haiku 12k, opus 60k,
  gpt-4o 80k, …) via `_budget_for_model`.
- System prompt carries language hint matching detected source language.
- Output is validated as HTML before being returned; invalid responses
  → `ai_cloning_skipped`.

**Manual verification:**
1. Configure `_llm_api_key` via the UI's LLM credentials panel.
2. Generate T23 against a Persian page with `model=claude-haiku-4-5`.
3. Open output - Persian content preserved verbatim.

**Automated test:** `tests/techniques/test_t23_ai_cloning.py`

---

## T24 - LSB Steganography

**Goal:** Hide a text payload inside the LSBs of an image on the page.

**Expected behavior:**
- Capacity pre-check: skips/truncates if payload exceeds carrier capacity.
- RGBA images preserve the alpha channel.
- `details = {carrier_idx, carrier_dims, capacity_bytes, payload_bytes,
  channel, bpp, truncated}`.
- `extract_payload(bytes, channel, bpp)` recovers the embedded payload.

**Manual verification:**
1. Generate T24 with a small payload against a page with one image.
2. Open the resulting `images/stego_carrier.png` - visually identical.
3. In a Python REPL: `SteganographyTechnique().extract_payload(open('stego_carrier.png','rb').read())`
   should return the payload string.

**Automated test:** `tests/techniques/test_t24_stego.py`

---

## T25 - Baseline Phishing Form

**Goal:** Inject a credential-stealing form (the no-evasion control case).

**Expected behavior:**
- Existing forms have their `action` rewritten to `/collect`.
- When no form exists and the page is an SPA, the form is injected
  inside the SPA root (`#root` / `#app` / `[data-reactroot]`).
- Button background uses sniffed `<meta name="theme-color">` value.
- Persian source → Persian form labels ("نام کاربری", "گذرواژه", …).
- Client-side honeypot guard script aborts submit when the hidden field
  is filled.

**Manual verification:**
1. Generate T25 against a Persian SPA template.
2. Verify the form is inside `#root` and uses Persian labels.

**Automated test:** `tests/techniques/test_t25_baseline.py`

---

## Verifying everything at once

Run the smoke-test CLI bundled with this project:

```bash
python -m app.smoketest tests/data/smoketest_urls.csv
```

It crawls a curated set of URLs, applies all 25 techniques to each, and
prints a per-URL breakdown of which techniques succeeded. See
`README.md` → "Verifying a healthy install" for details.
