"""Shared fixtures for the per-technique tests.

These tests instantiate technique classes directly (skipping the API/engine
layers) and assert on ApplyResult.change_log entries — specifically that
each technique populates `details` with the keys promised in its docstring
and the planning doc. Fixtures cover the variety of real-world HTML shapes
the 11k-page bulk crawl produces: Persian RTL pages, English LTR pages,
multi-form pages where the login form isn't first, SPA bodies, etc.
"""
from __future__ import annotations

import pytest


PERSIAN_LOGIN_HTML = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>ورود به حساب کاربری</title>
  <link rel="icon" type="image/png" href="/static/favicon.png">
  <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <img class="logo" src="/static/brand-logo.png" alt="لوگوی برند">
  </header>
  <main>
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
</html>
"""


ENGLISH_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Sign In</title>
  <link rel="icon" type="image/png" href="/static/favicon.png">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <img class="logo" src="/static/brand-logo.png" alt="brand logo">
  </header>
  <main>
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
</html>
"""


MULTI_FORM_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Multi-form Page</title></head>
<body>
  <form action="/search" method="GET" id="searchbar">
    <input type="text" name="q" placeholder="search">
    <button type="submit">Go</button>
  </form>
  <form action="/login" method="POST" id="loginform">
    <input type="email" name="email">
    <input type="password" name="password">
    <button type="submit">Sign in</button>
  </form>
</body>
</html>
"""


SPA_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>SPA</title></head>
<body>
  <div id="root"></div>
  <script src="/static/bundle.js"></script>
</body>
</html>
"""


INLINE_SVG_HTML = """<!DOCTYPE html>
<html><body>
  <svg width="100" height="100" viewBox="0 0 100 100">
    <circle cx="50" cy="50" r="40" fill="blue"/>
  </svg>
</body></html>
"""


@pytest.fixture
def persian_login_html() -> str:
    return PERSIAN_LOGIN_HTML


@pytest.fixture
def english_login_html() -> str:
    return ENGLISH_LOGIN_HTML


@pytest.fixture
def multi_form_html() -> str:
    return MULTI_FORM_HTML


@pytest.fixture
def spa_html() -> str:
    return SPA_HTML


@pytest.fixture
def inline_svg_html() -> str:
    return INLINE_SVG_HTML


@pytest.fixture
def sample_url() -> str:
    return "https://example.com/login"


@pytest.fixture
def idn_url() -> str:
    return "https://accounts.example.co.uk/login"


@pytest.fixture
def ipv6_url() -> str:
    return "https://[2001:db8::1]/login"


def assert_details_has(change, *keys: str) -> None:
    """Helper: assert a ChangeEntry's details dict carries each named key."""
    assert change.details, f"change.details is empty: {change.to_dict()}"
    missing = [k for k in keys if k not in change.details]
    assert not missing, f"missing detail keys {missing} in {change.details}"
