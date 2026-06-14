from __future__ import annotations

import io


def _post_analyze(client, html: str, url: str):
    return client.post(
        "/analyze",
        data={"url": url},
        files={"html_file": ("page.html", io.BytesIO(html.encode()), "text/html")},
    )


def test_analyze_with_form(client, simple_html, sample_url):
    resp = _post_analyze(client, simple_html, sample_url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["applicable_count"] > 0
    assert data["inapplicable_count"] >= 0
    assert data["html_features"]["has_input_fields"] is True


def test_analyze_no_form(client, no_form_html, sample_url):
    resp = _post_analyze(client, no_form_html, sample_url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["html_features"]["has_input_fields"] is False
    inapplicable_ids = {t["technique_id"] for t in data["inapplicable"]}
    assert 11 in inapplicable_ids
    assert 25 not in inapplicable_ids


def test_analyze_total_is_25(client, simple_html, sample_url):
    resp = _post_analyze(client, simple_html, sample_url)
    data = resp.json()
    total = data["applicable_count"] + data["inapplicable_count"]
    assert total == 25


def test_analyze_empty_html_returns_400(client, sample_url):
    resp = client.post(
        "/analyze",
        data={"url": sample_url},
        files={"html_file": ("page.html", io.BytesIO(b""), "text/html")},
    )
    assert resp.status_code == 400
