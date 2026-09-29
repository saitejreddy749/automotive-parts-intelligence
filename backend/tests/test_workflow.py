from io import BytesIO


HEADER = "supplier,sku,brand,part_number,description,category,make,model,year_start,year_end,engine\n"


def test_demo_is_seeded_and_evaluation_is_real(client):
    summary = client.get("/api/overview").json()
    assert summary["catalogues"] == 2
    assert summary["supplier_rows"] == 17
    assert summary["gold_pairs"] == 16
    assert summary["evaluations"] == 1
    first = client.get("/api/evaluations").json()[0]
    assert first["label_count"] == 16
    assert 0 <= first["precision"] <= 1
    assert 0 <= first["recall_at_3"] <= 1
    assert first["data_version"]


def test_review_merges_only_confirmed_sources(client):
    proposal = next(item for item in client.get("/api/proposals").json()
                    if {item["left"]["sku"], item["right"]["sku"]} == {"N-101", "S-1"})
    before = client.get("/api/overview").json()["canonical_parts"]
    reviewed = client.post(f"/api/proposals/{proposal['id']}/decision", json={"decision": "accepted"})
    assert reviewed.status_code == 200
    assert client.get("/api/overview").json()["canonical_parts"] == before - 1
    assert client.post(f"/api/proposals/{proposal['id']}/decision", json={"decision": "accepted"}).status_code == 409
    groups = client.get("/api/parts?q=F100").json()
    assert any({p["sku"] for p in group["sources"]} == {"N-101", "S-1"} for group in groups)


def test_fitment_requires_source_declaration_and_respects_engine(client):
    result = client.get("/api/fitment", params={"make": "Aster", "model": "A1", "year": 2020, "engine": "1.6L"}).json()
    assert result and all(row["status"] == "declared" for row in result)
    assert client.get("/api/fitment", params={"make": "Aster", "model": "A1", "year": 2020, "engine": "2.0L"}).json() == []
    assert client.get("/api/fitment", params={"make": "Aster", "model": "A1", "year": 2025}).json() == []


def test_evaluation_changes_with_threshold_and_reports_errors(client):
    low = client.post("/api/evaluations", json={"threshold": 0.6}).json()
    high = client.post("/api/evaluations", json={"threshold": 0.99}).json()
    assert low["threshold"] == 0.6
    assert high["threshold"] == 0.99
    assert low["false_positives"] >= high["false_positives"]
    assert high["false_negatives"] >= low["false_negatives"]
    assert client.get(f"/api/evaluations/{high['id']}").json()["errors"]
    assert client.post("/api/evaluations", json={"threshold": 0}).status_code == 422


def test_upload_accepts_good_rows_and_reports_bad_rows(client):
    content = (HEADER
        + "Third Supplier,T-1,Arcadia,F100,Cabin filter,cabin_filter,Aster,A1,2019,2021,1.6L\n"
        + "Third Supplier,T-2,Arcadia,F200,Oil filter,oil_filter,Aster,A1,2025,2020,1.6L\n")
    response = client.post("/api/catalogues", files={"file": ("third.csv", BytesIO(content.encode()), "text/csv")})
    assert response.status_code == 201, response.text
    assert response.json()["accepted"] == 1
    assert response.json()["invalid"][0]["line"] == 3
    assert client.get("/api/overview").json()["supplier_rows"] == 18
    assert client.post("/api/catalogues", files={"file": ("third.csv", content.encode(), "text/csv")}).status_code == 422


def test_similar_parts_and_ai_availability(client):
    proposal = client.get("/api/proposals").json()[0]
    part_id = proposal["left"]["id"]
    similar = client.get(f"/api/parts/{part_id}/similar")
    assert similar.status_code == 200
    assert similar.json()
    assert client.post(f"/api/proposals/{proposal['id']}/ai-review").status_code == 503
