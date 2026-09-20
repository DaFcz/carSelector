from fastapi.testclient import TestClient

from tests.conftest import SeededData


def test_list_brands(client: TestClient):
    response = client.get("/api/brands")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [
        {"id": 1, "name": "Mazda", "slug": "mazda"},
        {"id": 2, "name": "Volkswagen", "slug": "volkswagen"},
    ]


def test_list_vehicles_returns_seeded_configurations(client: TestClient):
    response = client.get("/api/vehicles")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    trims = {item["trim"] for item in body["items"]}
    assert trims == {"Prime-Line", "Centre-Line", "People", "R-Line People"}
    prime = next(item for item in body["items"] if item["trim"] == "Prime-Line")
    assert prime["price"] == {"amount": 824900.0, "currency": "CZK"}
    assert prime["match_score"] is None
    assert prime["flag"] is None


def test_list_vehicles_filters_by_drivetrain(client: TestClient):
    response = client.get("/api/vehicles", params={"drivetrain": "awd"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    trims = {item["trim"] for item in body["items"]}
    assert trims == {"Centre-Line", "R-Line People"}


def test_list_vehicles_filters_by_brand(client: TestClient):
    response = client.get("/api/vehicles", params={"brand_id": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2


def test_list_vehicles_filters_by_unknown_brand_returns_empty(client: TestClient):
    response = client.get("/api/vehicles", params={"brand_id": 999999})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_vehicles_filters_by_fuel_type(client: TestClient):
    response = client.get("/api/vehicles", params={"fuel_type": "petrol"})
    assert response.status_code == 200
    body = response.json()
    # Both Mazda configs plus the VW R-Line (2.0 TSI 4MOTION, petrol) - the
    # VW People config is diesel, so it's excluded.
    assert body["total"] == 3


def test_list_vehicles_filters_by_budget_and_currency(client: TestClient):
    response = client.get("/api/vehicles", params={"budget_max": 900_000, "currency": "CZK"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["trim"] == "Prime-Line"


def test_list_vehicles_sorts_by_price_ascending(client: TestClient):
    response = client.get("/api/vehicles", params={"sort": "price_asc"})
    assert response.status_code == 200
    prices = [item["price"]["amount"] for item in response.json()["items"]]
    assert prices == sorted(prices)


def test_list_vehicles_sorts_by_price_descending(client: TestClient):
    response = client.get("/api/vehicles", params={"sort": "price_desc"})
    assert response.status_code == 200
    prices = [item["price"]["amount"] for item in response.json()["items"]]
    assert prices == sorted(prices, reverse=True)


def test_list_vehicles_sorts_alphabetically(client: TestClient):
    response = client.get("/api/vehicles", params={"sort": "alpha"})
    assert response.status_code == 200
    trims = [item["trim"] for item in response.json()["items"]]
    # Ordered by (brand, model, trim): Mazda before Volkswagen, then
    # alphabetically by trim name within each.
    assert trims == ["Centre-Line", "Prime-Line", "People", "R-Line People"]


def test_list_vehicles_rejects_unknown_sort(client: TestClient):
    response = client.get("/api/vehicles", params={"sort": "bogus"})
    assert response.status_code == 422


def test_get_vehicle_detail(client: TestClient, seeded_session: SeededData):
    response = client.get(f"/api/vehicles/{seeded_session.config_prime_2wd_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["brand"] == "Mazda"
    assert body["model"] == "CX-5"
    assert body["powertrain"]["drivetrain"] == "fwd"
    assert body["powertrain"]["consumption_min"] == 7.0
    # 7 real colors from the brochure's "NABÍDKA BAREV KAROSERIE" table -
    # a flat list with no solid/metallic/pearlescent labeling given.
    assert len(body["colors"]) == 7
    colors_by_name = {c["name"]: c for c in body["colors"]}
    assert colors_by_name["Arctic White"] == {
        "name": "Arctic White", "finish_type": None, "surcharge": {"amount": 0.0, "currency": "CZK"}
    }
    assert colors_by_name["Jet Black"]["surcharge"] == {"amount": 14900.0, "currency": "CZK"}
    # Real per-trim VÝBAVA data (Prime-Line column) - standard only, since
    # the source gives no per-item price for its "optional within a
    # package" (m) rows.
    assert len(body["standard_equipment"]) == 73
    assert "Elektrická parkovací brzda (EPB) + Auto Hold" in body["standard_equipment"]
    assert "17-inch alloy wheels" not in body["standard_equipment"]  # old placeholder, gone
    assert body["optional_equipment"] == []
    assert len(body["price_history"]) == 1
    assert body["price_history"][0]["lowest_price_30d"] == {"amount": 875900.0, "currency": "CZK"}


def test_get_vehicle_detail_vw_has_priced_optional_equipment(client: TestClient, seeded_session: SeededData):
    response = client.get(f"/api/vehicles/{seeded_session.config_rline_awd_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["brand"] == "Volkswagen"
    assert body["model"] == "Tiguan"
    assert body["powertrain"]["drivetrain"] == "awd"
    assert len(body["colors"]) == 8
    colors_by_name = {c["name"]: c for c in body["colors"]}
    assert colors_by_name["Bílá Oryx perleťový efekt"] == {
        "name": "Bílá Oryx perleťový efekt",
        "finish_type": "pearlescent",
        "surcharge": {"amount": 11100.0, "currency": "CZK"},
    }
    # R-Line People = People's standard equipment plus its own extras.
    assert "Tříbodové bezpečnostní pásy s předepínači" in body["standard_equipment"]
    assert "IQ.LIGHT HD LED Matrix světlomety s Dynamic Light Assist" in body["standard_equipment"]
    optional_by_name = {o["name"]: o for o in body["optional_equipment"]}
    assert optional_by_name["Paket Black Style"] == {
        "name": "Paket Black Style", "category": "package", "surcharge": {"amount": 7100.0, "currency": "CZK"}
    }


def test_get_vehicle_detail_404(client: TestClient):
    response = client.get("/api/vehicles/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vehicle_not_found"


def test_compare_vehicles(client: TestClient, seeded_session: SeededData):
    ids = f"{seeded_session.config_prime_2wd_id},{seeded_session.config_centre_awd_id}"
    response = client.get("/api/vehicles/compare", params={"ids": ids})
    assert response.status_code == 200
    body = response.json()
    assert len(body["vehicles"]) == 2


def test_compare_vehicles_rejects_too_few_ids(client: TestClient, seeded_session: SeededData):
    response = client.get("/api/vehicles/compare", params={"ids": str(seeded_session.config_prime_2wd_id)})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_id_count"


def test_compare_vehicles_reports_missing_ids(client: TestClient, seeded_session: SeededData):
    ids = f"{seeded_session.config_prime_2wd_id},999999"
    response = client.get("/api/vehicles/compare", params={"ids": ids})
    assert response.status_code == 404
    assert response.json()["error"]["details"]["missing_ids"] == [999999]


def test_model_overview(client: TestClient, seeded_session: SeededData):
    response = client.get(f"/api/models/{seeded_session.model_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["brand"] == "Mazda"
    assert body["model"] == "CX-5"
    assert body["category"] == "SUV"
    trim_names = {trim["name"] for trim in body["trims"]}
    assert trim_names == {"Prime-Line", "Centre-Line"}


def test_model_overview_404(client: TestClient):
    response = client.get("/api/models/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"


def test_start_conversation(client: TestClient):
    response = client.post("/api/conversations")
    assert response.status_code == 201
    body = response.json()
    assert "conversation_id" in body
    assert "intro_message" in body


def test_send_message_unknown_conversation(client: TestClient):
    response = client.post("/api/conversations/does-not-exist/messages", json={"text": "hi"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"


def test_send_message_without_api_key_returns_503(client: TestClient):
    # No ANTHROPIC_API_KEY is configured in this environment - confirms
    # the AI layer fails loudly (503), not silently or with a 500.
    start = client.post("/api/conversations")
    conversation_id = start.json()["conversation_id"]
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"text": "We're a family of 4 heading to the mountains most weekends."},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_not_configured"


def test_send_message_maps_ai_provider_failure_to_502(client, monkeypatch) -> None:
    from app.ai.errors import AiProviderError
    from app.api import conversations as conversations_api

    def _reject(*_args, **_kwargs):
        raise AiProviderError("ai_invalid_key", "Invalid API Key")

    monkeypatch.setattr(conversations_api.orchestrator, "handle_message", _reject)
    conversation_id = client.post("/api/conversations").json()["conversation_id"]
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"text": "Hello"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_invalid_key"
