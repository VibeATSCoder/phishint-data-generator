from __future__ import annotations

import re

from bs4 import BeautifulSoup


def normalize_charset_utf8(html: str) -> str:
    """Strip any existing charset meta and declare UTF-8.

    Prevents browsers from mis-decoding UTF-8 bytes when the original page
    declared a legacy charset (e.g. windows-1256, windows-1252).
    Must be called on the final HTML *before* encoding to bytes for output.
    """
    html = re.sub(r'<meta[^>]+charset[^>]*>', '', html, flags=re.IGNORECASE)
    if re.search(r'<head(\s[^>]*)?>', html, re.IGNORECASE):
        html = re.sub(
            r'(<head(\s[^>]*)?>)',
            r'\1\n  <meta charset="utf-8">',
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    return html


def inject_base_href(html: str, base_url: str) -> str:
    """Inject `<base href="...">` into <head> so relative URLs in the saved
    HTML resolve against the original site when the file is opened locally
    (file://). Without this, `<img src="/logo.png">` becomes
    `file:///logo.png` and breaks.

    If a <base> tag already exists, it is replaced. Inserts <head> if missing.
    `base_url` should be the final URL of the page (post-redirects); the
    crawler passes `page.url` here.
    """
    if not base_url or not base_url.strip():
        return html
    safe = base_url.strip().replace('"', '%22')
    html = re.sub(r'<base\b[^>]*/?>', '', html, flags=re.IGNORECASE)
    base_tag = f'<base href="{safe}">'
    if re.search(r'<head(\s[^>]*)?>', html, re.IGNORECASE):
        return re.sub(
            r'(<head(\s[^>]*)?>)',
            r'\1\n  ' + base_tag,
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    if re.search(r'<html(\s[^>]*)?>', html, re.IGNORECASE):
        return re.sub(
            r'(<html(\s[^>]*)?>)',
            r'\1\n<head>' + base_tag + '</head>',
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    return f'<head>{base_tag}</head>' + html


def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def serialize_html(soup: BeautifulSoup) -> str:
    return str(soup)


def ensure_head(soup: BeautifulSoup) -> BeautifulSoup:
    """Ensure a <head> element exists; create one if missing."""
    if not soup.find("head"):
        html_tag = soup.find("html")
        if html_tag:
            head = soup.new_tag("head")
            html_tag.insert(0, head)
        else:
            head = soup.new_tag("head")
            soup.insert(0, head)
    return soup


def ensure_body(soup: BeautifulSoup) -> BeautifulSoup:
    """Ensure a <body> element exists; create one if missing."""
    if not soup.find("body"):
        html_tag = soup.find("html")
        if html_tag:
            body = soup.new_tag("body")
            html_tag.append(body)
        else:
            body = soup.new_tag("body")
            soup.append(body)
    return soup


def inject_script_into_head(soup: BeautifulSoup, js_code: str) -> BeautifulSoup:
    """Append a <script> tag to <head> (creates head if missing)."""
    ensure_head(soup)
    script = soup.new_tag("script")
    script.string = js_code
    soup.find("head").append(script)
    return soup


def inject_style_into_head(soup: BeautifulSoup, css: str) -> BeautifulSoup:
    """Append a <style> tag to <head> (creates head if missing)."""
    ensure_head(soup)
    style = soup.new_tag("style")
    style.string = css
    soup.find("head").append(style)
    return soup


def inject_element_into_body(soup: BeautifulSoup, tag_str: str) -> BeautifulSoup:
    """Append raw HTML string into <body>."""
    ensure_body(soup)
    frag = BeautifulSoup(tag_str, "lxml")
    body = soup.find("body")
    src = frag.body or frag
    for child in list(src.children):
        tag = child if hasattr(child, "name") else None
        if tag and tag.name:
            body.append(tag)
    return soup


def find_all_forms(soup: BeautifulSoup) -> list:
    return soup.find_all("form")


def find_all_inputs(soup: BeautifulSoup) -> list:
    return soup.find_all("input")


def find_all_images(soup: BeautifulSoup) -> list:
    return soup.find_all("img", src=True)


def _has_token(value, token: str) -> bool:
    """Match a class/rel value (str OR list) against a CSS-style token."""
    if value is None:
        return False
    items = value if isinstance(value, list) else str(value).split()
    return any(token.lower() == str(x).lower() for x in items)


def _rel_contains_icon(value) -> bool:
    """Truthy when a `<link rel=…>` mentions any icon variant."""
    if value is None:
        return False
    items = value if isinstance(value, list) else str(value).split()
    return any("icon" in str(x).lower() for x in items)


def find_brand_logo(soup: BeautifulSoup) -> tuple[object | None, str]:
    """Find the most likely brand logo in priority order. Returns
    `(tag, picker_name)` where `picker_name` describes which heuristic matched
    so techniques can log it.

    Order:
      1. `<link rel="apple-touch-icon">` — explicit brand asset.
      2. `<link rel="icon|shortcut icon">` — favicon link.
      3. `<img class~=logo>` / `<img id~=logo>` — most sites' brand img.
      4. `<img alt~="logo">` / `<img title~="logo">`.
      5. First `<img>` inside `<header>` / `<nav>`.
      6. Falls back to first `<img>` with a `src`.
    """
    for link in soup.find_all("link", rel=True):
        rels = link.get("rel") or []
        rels_lower = [str(r).lower() for r in (rels if isinstance(rels, list) else [rels])]
        if "apple-touch-icon" in rels_lower:
            return link, "rel=apple-touch-icon"
    for link in soup.find_all("link", rel=True):
        if _rel_contains_icon(link.get("rel")):
            return link, "rel=icon"

    for img in soup.find_all("img", src=True):
        if _has_token(img.get("class"), "logo") or _has_token([img.get("id") or ""], "logo"):
            return img, "img.class=logo"
        if img.get("id") and "logo" in str(img["id"]).lower():
            return img, "img.id=logo"

    for img in soup.find_all("img", src=True):
        alt = (img.get("alt") or "").lower()
        title = (img.get("title") or "").lower()
        if "logo" in alt or "logo" in title:
            return img, "img.alt=logo"

    for section_tag in ("header", "nav"):
        section = soup.find(section_tag)
        if section:
            img = section.find("img", src=True)
            if img:
                return img, f"first img in <{section_tag}>"

    first = soup.find("img", src=True)
    if first:
        return first, "first img"
    return None, "no candidate"


def find_login_form(soup: BeautifulSoup) -> tuple[object | None, str]:
    """Pick the form that most resembles a login form. Returns `(form, picker)`.

    Order: form with `<input type=password>` → form whose inputs include
    `name=email|user|login` → first form. Returns `(None, "no_form")` if no
    `<form>` exists.
    """
    forms = soup.find_all("form")
    if not forms:
        return None, "no_form"
    for f in forms:
        if f.find("input", attrs={"type": "password"}):
            return f, "form_with_password"
    for f in forms:
        for inp in f.find_all("input"):
            name = (inp.get("name") or "").lower()
            iid = (inp.get("id") or "").lower()
            if any(k in name + " " + iid for k in ("email", "user", "login", "username")):
                return f, "form_with_credlike_input"
    return forms[0], "first_form"


def count_real_logins(soup: BeautifulSoup) -> int:
    """Number of `<form>` elements that contain a `type=password` input."""
    return sum(1 for f in soup.find_all("form") if f.find("input", attrs={"type": "password"}))


def safe_append_fragment(
    soup: BeautifulSoup, frag_html: str, target: str = "body",
) -> int:
    """Parse `frag_html` and append every top-level element into `soup.target`.

    Returns the number of elements appended. Centralises the pattern that
    used to live as `body.append(frag.find('div'))` (which silently appended
    `None` on malformed fragments) across T9, T10, T12, T14, T16, T21.
    """
    if not frag_html or not frag_html.strip():
        return 0
    if target == "body":
        ensure_body(soup)
        host = soup.find("body")
    elif target == "head":
        ensure_head(soup)
        host = soup.find("head")
    else:
        host = soup.find(target)
        if host is None:
            return 0
    frag = BeautifulSoup(frag_html, "lxml")
    src = frag.body or frag
    appended = 0
    for child in list(src.children):
        name = getattr(child, "name", None)
        if name:
            host.append(child)
            appended += 1
    return appended
