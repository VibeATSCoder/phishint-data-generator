from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.techniques  # noqa: F401
from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def sample_url() -> str:
    return "https://www.example.com/login"


@pytest.fixture
def simple_html() -> str:
    return """<!DOCTYPE html>
<html>
<head><title>Login</title></head>
<body>
  <form action="/login" method="POST">
    <input type="text" name="username" placeholder="Username">
    <input type="password" name="password" placeholder="Password">
    <button type="submit">Login</button>
  </form>
</body>
</html>"""


@pytest.fixture
def no_form_html() -> str:
    return """<!DOCTYPE html>
<html>
<head><title>Welcome</title></head>
<body>
  <h1>Welcome to Example</h1>
  <p>Click <a href="/login">here</a> to log in.</p>
</body>
</html>"""


@pytest.fixture
def html_with_image() -> str:
    return """<!DOCTYPE html>
<html>
<head><title>Image Page</title></head>
<body>
  <img src="https://via.placeholder.com/150" alt="logo">
  <form action="/login" method="POST">
    <input type="text" name="username">
    <input type="password" name="password">
    <button type="submit">Login</button>
  </form>
</body>
</html>"""
