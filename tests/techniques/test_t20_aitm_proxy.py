"""T20 — AiTM / Evilginx-style phishlet config. Verifies the YAML and
nginx files are generated, the WebSocket block is included in nginx, and
multi-domain alias support widens server_name."""
from app.techniques.group6_mfa.t20_aitm_proxy import AiTMProxyTechnique


def test_t20_emits_yaml_and_nginx(english_login_html, sample_url):
    tech = AiTMProxyTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert "evilginx_phishlet.yaml" in res.extra_files
    assert "nginx_proxy_snippet.conf" in res.extra_files
    nginx = res.extra_files["nginx_proxy_snippet.conf"].decode()
    assert "proxy_set_header Upgrade" in nginx


def test_t20_multi_domain_aliases(english_login_html, sample_url):
    tech = AiTMProxyTechnique()
    opts = tech.get_default_options()
    opts["domain_aliases"] = ["alias1.example.org", "alias2.example.org"]
    res = tech.apply(english_login_html, sample_url, opts)
    nginx = res.extra_files["nginx_proxy_snippet.conf"].decode()
    assert "alias1.example.org" in nginx
    assert "alias2.example.org" in nginx
    assert res.change_log[0].details["alias_count"] == 2


def test_t20_records_base_and_subdomains(english_login_html):
    tech = AiTMProxyTechnique()
    res = tech.apply(english_login_html, "https://login.microsoft.com/", tech.get_default_options())
    change = res.change_log[0]
    assert change.details["base_domain"] == "microsoft.com"
    assert "login" in change.details["subdomains"]
