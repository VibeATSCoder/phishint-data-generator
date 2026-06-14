from __future__ import annotations

import io
import json
import zipfile


def _post_generate(
    client,
    html: str,
    url: str,
    technique_configs: list[dict],
    hybrid_mode: bool = True,
    include_report: bool = True,
):
    return client.post(
        "/generate",
        data={
            "url": url,
            "technique_configs": json.dumps(technique_configs),
            "hybrid_mode": str(hybrid_mode).lower(),
            "include_report": str(include_report).lower(),
        },
        files={"html_file": ("page.html", io.BytesIO(html.encode()), "text/html")},
    )


def test_generate_returns_zip(client, simple_html, sample_url):
    resp = _post_generate(
        client, simple_html, sample_url,
        [{"technique_id": 1, "options": {}}]
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"


def test_generate_zip_contains_modified_html(client, simple_html, sample_url):
    resp = _post_generate(
        client, simple_html, sample_url,
        [{"technique_id": 10}]
    )
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert "modified.html" in names
    html_content = zf.read("modified.html").decode()
    assert "atob(" in html_content or "DOMContentLoaded" in html_content


def test_generate_includes_report(client, simple_html, sample_url):
    resp = _post_generate(
        client, simple_html, sample_url,
        [{"technique_id": 4}],
        include_report=True,
    )
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert "report.md" in zf.namelist()
    report_text = zf.read("report.md").decode()
    assert "# Phishing Generation Report" in report_text


def test_generate_qr_produces_png(client, simple_html, sample_url):
    resp = _post_generate(
        client, simple_html, sample_url,
        [{"technique_id": 18, "options": {"include_ascii": True}}]
    )
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert "qr_code.png" in names
    assert "qr_ascii.txt" in names


def test_generate_redirect_chain_extra_files(client, simple_html, sample_url):
    resp = _post_generate(
        client, simple_html, sample_url,
        [{"technique_id": 6, "options": {"hop_count": 3}}]
    )
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert "redirect_chain.html" in names
    assert "redirect_chain.txt" in names


def test_generate_hybrid_url_then_dom(client, simple_html, sample_url):
    resp = _post_generate(
        client, simple_html, sample_url,
        [{"technique_id": 1}, {"technique_id": 10}],
        hybrid_mode=True,
    )
    assert resp.status_code == 200
    run_id_header = resp.headers.get("x-run-id")
    assert run_id_header
    final_url_header = resp.headers.get("x-final-url")
    assert final_url_header


def test_generate_unknown_technique_id_422(client, simple_html, sample_url):
    resp = _post_generate(
        client, simple_html, sample_url,
        [{"technique_id": 999}]
    )
    assert resp.status_code == 422


def test_generate_aitm_config_yaml(client, simple_html, sample_url):
    resp = _post_generate(
        client, simple_html, sample_url,
        [{"technique_id": 20}]
    )
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert "evilginx_phishlet.yaml" in zf.namelist()
    yaml_content = zf.read("evilginx_phishlet.yaml").decode()
    assert "proxy_hosts" in yaml_content
    assert "credentials" in yaml_content
