from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

LONG_TEXT = "A civic complaint about a broken streetlight on Main Street near the library."


def _create_dataset(client, name: str = "complaints") -> str:
    response = client.post("/datasets", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def test_exact_duplicate(client) -> None:
    dataset_id = _create_dataset(client)
    payload = [{"text": LONG_TEXT, "label": "roads", "source": "311"}]
    first = client.post(
        f"/datasets/{dataset_id}/samples",
        json=payload,
        headers={"Idempotency-Key": "batch-1"},
    )
    second = client.post(
        f"/datasets/{dataset_id}/samples",
        json=payload,
        headers={"Idempotency-Key": "batch-2"},
    )
    assert first.status_code == 200
    assert first.json()["accepted"] == 1
    assert second.json()["accepted"] == 0
    assert second.json()["rejected"] == 1

    report = client.get(f"/datasets/{dataset_id}/report")
    assert report.status_code == 200
    body = report.json()
    assert body["duplicate_counts"]["exact_duplicate"] == 1
    flagged_rules = {item["rule"] for item in body["flagged_samples"]}
    assert "exact_duplicate" in flagged_rules
    assert body["flagged_samples"][0]["sample_id"]


def test_malformed_record(client) -> None:
    dataset_id = _create_dataset(client, "malformed")
    response = client.post(
        f"/datasets/{dataset_id}/samples",
        json=[{"label": "roads", "source": "311"}],
        headers={"Idempotency-Key": "bad-row"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["received"] == 1
    assert body["accepted"] == 0
    assert body["rejected"] == 1

    report = client.get(f"/datasets/{dataset_id}/report")
    assert report.json()["counts_by_status"]["rejected"] == 1
    assert report.json()["flagged_samples"] == []


def test_idempotent_retry(client) -> None:
    dataset_id = _create_dataset(client, "idem")
    payload = [{"text": LONG_TEXT, "label": "roads", "source": "web"}]
    headers = {"Idempotency-Key": "same-key"}
    first = client.post(f"/datasets/{dataset_id}/samples", json=payload, headers=headers)
    second = client.post(f"/datasets/{dataset_id}/samples", json=payload, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["accepted"] == 1
    assert second.json()["received"] == 1

    report = client.get(f"/datasets/{dataset_id}/report")
    assert report.json()["counts_by_status"]["accepted"] + report.json()["counts_by_status"]["flagged"] == 1


def test_db_failure(client, monkeypatch) -> None:
    dataset_id = _create_dataset(client, "dbfail")
    calls = {"n": 0}

    def boom(self) -> None:
        calls["n"] += 1
        raise OperationalError("COMMIT", {}, Exception("db down"))

    monkeypatch.setattr(Session, "commit", boom)
    response = client.post(
        f"/datasets/{dataset_id}/samples",
        json=[{"text": LONG_TEXT, "label": "roads", "source": "311"}],
        headers={"Idempotency-Key": "db-fail"},
    )
    assert response.status_code == 503
    assert calls["n"] == 3
