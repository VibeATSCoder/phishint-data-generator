from __future__ import annotations

import random
import string
import urllib.parse

_INJECTED_SCHEME = "https://"


def _ensure_scheme(url: str) -> tuple[str, bool]:
    """Return (url_with_scheme, scheme_was_added).

    urlparse only populates `netloc` when a scheme is present.
    For bare domains like 'test.com' we prepend https:// so every
    technique can work uniformly, then strip it back before returning.
    """
    if urllib.parse.urlparse(url).scheme:
        return url, False
    return _INJECTED_SCHEME + url, True


def parse_url(url: str) -> tuple[urllib.parse.ParseResult, bool]:
    """Parse a URL, handling schemeless inputs like 'test.com'.

    Returns (ParseResult, scheme_was_injected).
    Pass scheme_was_injected to rebuild_url so it can strip the scheme.
    """
    normed, injected = _ensure_scheme(url)
    return urllib.parse.urlparse(normed), injected


def rebuild_url(parts: urllib.parse.ParseResult, strip_scheme: bool = False) -> str:
    """Reconstruct a URL from ParseResult parts.

    If strip_scheme=True, remove the injected 'https://' prefix that was
    added by parse_url to handle a bare domain input.
    """
    result = urllib.parse.urlunparse(parts)
    if strip_scheme and result.startswith(_INJECTED_SCHEME):
        result = result[len(_INJECTED_SCHEME):]
    return result


def get_domain(url: str) -> str:
    parsed, _ = parse_url(url)
    return parsed.netloc


def add_query_params(url: str, params: dict[str, str]) -> str:
    parsed, injected = parse_url(url)
    existing = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    existing.update({k: [v] for k, v in params.items()})
    new_query = urllib.parse.urlencode(existing, doseq=True)
    return rebuild_url(parsed._replace(query=new_query), strip_scheme=injected)


def random_string(length: int = 32, chars: str | None = None) -> str:
    if chars is None:
        chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


def random_hex_string(length: int = 32) -> str:
    return "".join(random.choices("0123456789abcdef", k=length))


def random_hash_like(style: str = "random", length: int = 32) -> str:
    if style == "md5_like":
        return random_hex_string(32)
    if style == "sha_like":
        return random_hex_string(64)
    return random_string(length)


def inject_trust_word(url: str, word: str, strategy: str = "prepend") -> str:
    """Inject a trust word into the subdomain position."""
    parsed, injected = parse_url(url)
    netloc = parsed.netloc
    if strategy == "prepend":
        new_netloc = f"{word}-{netloc}"
    elif strategy == "replace":
        new_netloc = f"{word}.{netloc}"
    else:
        new_netloc = f"{netloc}-{word}"
    return rebuild_url(parsed._replace(netloc=new_netloc), strip_scheme=injected)



_MULTI_PART_TLDS = {
    "co.uk", "ac.uk", "org.uk", "gov.uk", "net.uk",
    "com.au", "net.au", "org.au", "edu.au", "gov.au",
    "co.jp", "ne.jp", "or.jp", "ac.jp", "go.jp",
    "co.kr", "or.kr", "go.kr", "ac.kr",
    "com.br", "com.mx", "com.ar", "com.cn",
    "co.in", "co.id", "co.za", "co.nz",
    "ac.ir", "gov.ir", "co.ir", "net.ir", "org.ir", "edu.ir", "sch.ir",
    "id.ir", "mil.ir", "nic.ir",
}


def is_ipv6_literal(host: str) -> bool:
    """True when `host` is an IPv6 literal in URL bracket form (`[2001:db8::1]`)
    or a bare colon-delimited IPv6 address. Used by T1/T2/T3 to skip mutation.
    """
    if not host:
        return False
    h = host.strip()
    if h.startswith("[") and "]" in h:
        return True
    return h.count(":") >= 2 and "@" not in h


def is_already_punycode(label: str) -> bool:
    """True when a single domain label is already IDNA-encoded (`xn--`)."""
    return bool(label) and label.lower().startswith("xn--")


def split_domain_labels(host: str) -> tuple[str, list[str]]:
    """Split a hostname into `(base_domain, subdomains)`.

    `login.microsoft.com` → `("microsoft.com", ["login"])`
    `accounts.shop.example.co.uk` → `("example.co.uk", ["accounts", "shop"])`
    Bare `localhost`, IPs, and IPv6 literals are returned as base with no subs.
    """
    if not host:
        return "", []
    raw = host.strip().strip("[]").split(":", 1)[0].lower()
    if is_ipv6_literal(host) or _looks_like_ip(raw) or "." not in raw:
        return raw, []
    labels = raw.split(".")
    if len(labels) >= 3:
        last_two = ".".join(labels[-2:])
        if last_two in _MULTI_PART_TLDS:
            base = ".".join(labels[-3:])
            subs = labels[:-3]
            return base, subs
    base = ".".join(labels[-2:])
    subs = labels[:-2]
    return base, subs


def _looks_like_ip(host: str) -> bool:
    parts = host.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) < 256 for p in parts)


def domain_for_clearbit(url: str) -> str:
    """Normalize a URL to a domain string suitable for the Clearbit logo API.

    Strips port, path, query, fragment; lowercases; drops `www.`. Returns an
    empty string for inputs without a usable hostname.
    """
    if not url:
        return ""
    parsed, _ = parse_url(url)
    host = (parsed.hostname or "").lower().strip()
    if not host or _looks_like_ip(host) or is_ipv6_literal(host):
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host
