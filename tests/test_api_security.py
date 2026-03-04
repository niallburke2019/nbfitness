import os


def _env_auth():
    # Werkzeug maps HTTP_X_API_KEY -> X-API-KEY header
    return {"HTTP_X_API_KEY": os.environ["API_KEY"]}


def test_api_requires_auth(client):
    # no key -> 401
    response = client.get("/api/meals/day")
    assert response.status_code == 401
    assert response.json["error"] == "unauthorized"


def test_create_meal_validation_error(client):
    # API key request ALSO requires user_id when not logged in
    response = client.post(
        "/api/meals?user_id=1",
        json={
            "meal_type": "lunch",
            "calories": 500,
            # intentionally missing food_name
        },
        environ_overrides=_env_auth(),
    )

    assert response.status_code == 400
    assert response.json["error"] == "bad_request"
    assert "food_name" in response.json["message"]


def test_update_invalid_date(client):
    # Create a valid meal (needs user_id)
    create_response = client.post(
        "/api/meals?user_id=1",
        json={
            "food_name": "Rice",
            "meal_type": "lunch",
            "calories": 400,
        },
        environ_overrides=_env_auth(),
    )
    assert create_response.status_code == 201
    entry_id = create_response.json["entry"]["id"]

    # Invalid date update (needs user_id)
    update_response = client.put(
        f"/api/meals/{entry_id}?user_id=1",
        json={"entry_date": "invalid-date"},
        environ_overrides=_env_auth(),
    )

    assert update_response.status_code == 400
    assert update_response.json["error"] == "bad_request"