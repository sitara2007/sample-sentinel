import pytest

from app.embeddings import embeddings_available

LONG_A = "The city should repair the large pothole on Oak Avenue before winter weather arrives."
LONG_B = "The city should repair the large pothole on Oak Avenue before winter weather arrives!"


pytestmark = pytest.mark.skipif(
    not embeddings_available(),
    reason="sentence-transformers model unavailable",
)


def test_near_duplicate_flags_similar_text(client) -> None:
    created = client.post("/datasets", json={"name": "near"})
    dataset_id = created.json()["id"]
    response = client.post(
        f"/datasets/{dataset_id}/samples",
        json=[
            {"text": LONG_A, "label": "roads", "source": "311"},
            {"text": LONG_B, "label": "roads", "source": "email"},
        ],
        headers={"Idempotency-Key": "near-1"},
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 2
    report = client.get(f"/datasets/{dataset_id}/report").json()
    assert report["duplicate_counts"]["near_duplicate"] >= 1
    rules = {item["rule"] for item in report["flagged_samples"]}
    assert "near_duplicate" in rules
