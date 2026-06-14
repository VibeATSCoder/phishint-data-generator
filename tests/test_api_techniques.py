from __future__ import annotations


def test_list_techniques_returns_25(client):
    resp = client.get("/techniques")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 25
    assert len(data["groups"]) > 0


def test_technique_has_required_fields(client):
    resp = client.get("/techniques")
    data = resp.json()
    for group_list in data["groups"].values():
        for technique in group_list:
            assert "id" in technique
            assert "name" in technique
            assert "group" in technique
            assert "description" in technique
            assert "requirements" in technique
            assert "options" in technique


def test_technique_ids_are_unique(client):
    resp = client.get("/techniques")
    data = resp.json()
    ids = [
        t["id"]
        for group_list in data["groups"].values()
        for t in group_list
    ]
    assert len(ids) == len(set(ids))
