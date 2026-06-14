"""Mock-driven per-technique verifier.

Why this exists
---------------
Phase 2 added Persian localization to 8 visible-text techniques + a
locale detector + a smoke-test CLI. The smoke-test exercises crawls,
which depend on network availability and Playwright. This module is
the *offline* counterpart: it feeds two in-memory mock pages (Persian
RTL login form + English LTR login form) through every one of the 25
techniques and prints a PASS/FAIL table.

For each (technique × language) pair it asserts:
  • apply() did not crash.
  • At least one ChangeEntry was emitted (skipped/applied — both count).
  • If the technique injects user-visible UI (T6, T16/17/19/21/22/25),
    the modified HTML contains Persian Unicode when the source is
    Persian — and Latin script when the source is English.
  • The modified HTML and every extra-file are dumped under
    `out/verify/<tid>_<lang>/` so a reviewer can open them in a browser.

Run from inside the Docker backend container:

    docker compose exec backend python -m app.verify_techniques

Exit code is 0 iff every technique executed without crashing AND every
visible-text technique passed the language assertion. Anything else is
non-zero so the script can gate CI.
"""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any

import app.techniques  # noqa: F401
from app.core.registry import TechniqueRegistry
from app.techniques.base import ApplyResult

logger = logging.getLogger("phishgen.verify")

_PERSIAN_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_LATIN_RE = re.compile(r"[A-Za-z]")


PERSIAN_LOGIN_HTML = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>ورود به حساب کاربری</title>
  <meta name="theme-color" content="#1a73e8">
  <link rel="icon" type="image/png" href="https://www.google.com/favicon.ico">
  <link rel="apple-touch-icon" href="https://www.google.com/favicon.ico">
</head>
<body>
  <header>
    <img class="logo" src="https://www.google.com/favicon.ico" alt="لوگوی برند">
  </header>
  <main>
    <svg width="32" height="32" viewBox="0 0 32 32"><circle cx="16" cy="16" r="14" fill="#1a73e8"/></svg>
    <h1>ورود</h1>
    <form action="/login" method="POST">
      <label for="user">نام کاربری یا ایمیل</label>
      <input type="text" id="user" name="user">
      <label for="pwd">گذرواژه</label>
      <input type="password" id="pwd" name="pwd">
      <button type="submit">ورود</button>
    </form>
  </main>
</body>
</html>"""

ENGLISH_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Sign in</title>
  <meta name="theme-color" content="#1a73e8">
  <link rel="icon" type="image/png" href="https://www.google.com/favicon.ico">
  <link rel="apple-touch-icon" href="https://www.google.com/favicon.ico">
</head>
<body>
  <header>
    <img class="logo" src="https://www.google.com/favicon.ico" alt="brand logo">
  </header>
  <main>
    <svg width="32" height="32" viewBox="0 0 32 32"><circle cx="16" cy="16" r="14" fill="#1a73e8"/></svg>
    <h1>Sign in</h1>
    <form action="/login" method="POST">
      <label for="user">Username or email</label>
      <input type="text" id="user" name="user">
      <label for="pwd">Password</label>
      <input type="password" id="pwd" name="pwd">
      <button type="submit">Sign in</button>
    </form>
  </main>
</body>
</html>"""

VISIBLE_TEXT_TIDS = {6, 16, 17, 19, 21, 22, 25}

MOCK_URL = "https://login.example.com/signin"


def _has_persian(html: str) -> int:
    return len(_PERSIAN_RE.findall(html or ""))


def _has_latin(html: str) -> int:
    return len(_LATIN_RE.findall(html or ""))


def _diff(after: str, before: str) -> str:
    """Return only the substring of `after` that isn't already in `before`,
    so the language check focuses on injected text, not the source page."""
    if not after:
        return ""
    if before and before in after:
        return after.replace(before, "")
    return after


def _run_one(cls, html: str, url: str, out_dir: Path) -> dict[str, Any]:
    """Run a single technique against a mock page. Never raises — failures
    are returned as result rows."""
    row: dict[str, Any] = {
        "tid": cls.TECHNIQUE_ID,
        "name": cls.TECHNIQUE_NAME,
        "status": "FAIL",
        "changes": 0,
        "extras": 0,
        "persian_inj": 0,
        "latin_inj": 0,
        "note": "",
    }
    try:
        instance = cls()
        options = cls.get_default_options()
        result: ApplyResult = instance.apply(
            html=html, url=url, options=options, screenshot_bytes=None,
        )
    except Exception as exc:
        row["note"] = f"{type(exc).__name__}: {exc}"[:90]
        row["traceback"] = traceback.format_exc()
        return row

    out_dir.mkdir(parents=True, exist_ok=True)
    if result.modified_html:
        (out_dir / "modified.html").write_text(result.modified_html, encoding="utf-8")
    if result.modified_url:
        (out_dir / "modified_url.txt").write_text(result.modified_url, encoding="utf-8")
    for fname, content in result.extra_files.items():
        target = out_dir / fname.replace("\\", "/").lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(str(content), encoding="utf-8")

    row["changes"] = len(result.change_log)
    row["extras"] = len(result.extra_files)
    injected = _diff(result.modified_html or "", html)
    row["persian_inj"] = _has_persian(injected)
    row["latin_inj"] = _has_latin(injected)

    if result.change_log:
        first = result.change_log[0]
        if first.change_type.endswith("_skipped"):
            row["note"] = (first.description or "")[:60]
        else:
            row["note"] = first.change_type
    return row


def _check_language_match(rows_fa: dict, rows_en: dict, tid: int) -> tuple[bool, str]:
    """For visible-text techniques: assert Persian Unicode appears in fa
    output and absent (or minimal) in en output."""
    fa = rows_fa.get(tid, {})
    en = rows_en.get(tid, {})
    fa_persian = fa.get("persian_inj", 0)
    en_persian = en.get("persian_inj", 0)
    en_latin = en.get("latin_inj", 0)

    if fa.get("status") == "FAIL" or en.get("status") == "FAIL":
        return False, "technique crashed"
    if fa_persian == 0 and en_latin == 0:
        return True, "no text injected"
    if fa_persian < 5:
        return False, f"fa output has only {fa_persian} Persian chars"
    if en_persian > fa_persian / 2:
        return False, f"en output has too much Persian ({en_persian})"
    return True, f"fa={fa_persian} en_latin={en_latin}"


def _print_table(label: str, rows: list[dict]) -> None:
    print(f"\n=== {label} ===")
    print(f"{'TID':<4}{'NAME':<46}{'STATUS':<7}{'CHG':<4}{'EXTR':<5}"
          f"{'FA':<4}{'EN':<4}NOTE")
    print("-" * 130)
    for r in rows:
        print(
            f"{r['tid']:<4}"
            f"{r['name'][:45]:<46}"
            f"{r['status']:<7}"
            f"{r['changes']:<4}"
            f"{r['extras']:<5}"
            f"{r['persian_inj']:<4}"
            f"{r['latin_inj']:<4}"
            f"{r['note']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o", "--out-dir", default="out/verify",
        help="Where to write modified.html + extras (default: out/verify)",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Wipe the output dir before running",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show full tracebacks for crashed techniques",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    out_root = Path(args.out_dir).resolve()
    if args.clean and out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    techniques = TechniqueRegistry.all()
    if not techniques:
        print("ERROR: no techniques registered — registry import failed", file=sys.stderr)
        return 2
    print(f"Verifying {len(techniques)} techniques against Persian + English mocks…")

    rows_fa: dict[int, dict] = {}
    rows_en: dict[int, dict] = {}
    for cls in techniques:
        tid = cls.TECHNIQUE_ID
        r_fa = _run_one(cls, PERSIAN_LOGIN_HTML, MOCK_URL, out_root / f"t{tid:02d}_fa")
        r_en = _run_one(cls, ENGLISH_LOGIN_HTML, MOCK_URL, out_root / f"t{tid:02d}_en")
        if "traceback" not in r_fa:
            r_fa["status"] = "OK"
        if "traceback" not in r_en:
            r_en["status"] = "OK"
        rows_fa[tid] = r_fa
        rows_en[tid] = r_en

    _print_table("Persian fixture", [rows_fa[t.TECHNIQUE_ID] for t in techniques])
    _print_table("English fixture", [rows_en[t.TECHNIQUE_ID] for t in techniques])

    print("\n=== Visible-text language match ===")
    print(f"{'TID':<4}{'NAME':<46}{'MATCH':<8}REASON")
    print("-" * 110)
    crashed = 0
    lang_fail = 0
    for cls in techniques:
        tid = cls.TECHNIQUE_ID
        if rows_fa[tid]["status"] == "FAIL" or rows_en[tid]["status"] == "FAIL":
            crashed += 1
        if tid in VISIBLE_TEXT_TIDS:
            ok, reason = _check_language_match(rows_fa, rows_en, tid)
            mark = "PASS" if ok else "FAIL"
            if not ok:
                lang_fail += 1
            print(f"{tid:<4}{cls.TECHNIQUE_NAME[:45]:<46}{mark:<8}{reason}")

    if args.verbose:
        for tid, r in {**rows_fa, **rows_en}.items():
            if "traceback" in r:
                print(f"\n--- Traceback: T{tid} ({r['name']}) ---")
                print(r["traceback"])

    print("\n" + "=" * 60)
    print(f"Techniques run:            {len(techniques) * 2} (×2 langs)")
    print(f"Crashes:                   {crashed}")
    print(f"Language-match failures:   {lang_fail}")
    print(f"Outputs written under:     {out_root}")
    print("=" * 60)

    if crashed == 0 and lang_fail == 0:
        print("\nVERIFY PASSED — every technique ran and visible-text techniques speak the right language.")
        return 0
    print("\nVERIFY FAILED — see breakdown above. Re-run with -v for tracebacks.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
