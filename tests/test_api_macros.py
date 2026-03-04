import os


def _env_auth():
    # Werkzeug maps HTTP_X_API_KEY -> X-API-KEY
    return {"HTTP_X_API_KEY": os.environ["API_KEY"]}


def test_get_goal_unauthorized(client):
    r = client.get("/api/macros/goal")
    assert r.status_code == 401


def test_get_goal_with_api_key_and_user_id(client):
    r = client.get("/api/macros/goal?user_id=1", environ_overrides=_env_auth())
    assert r.status_code == 200
    assert r.json["user_id"] == 1
    assert "goal" in r.json
    assert "macro_calories_target" in r.json["goal"]


def test_put_goal_updates_and_macro_calories_449(client):
    # Set targets: P=150g, C=300g, F=70g
    # Macro calories = 150*4 + 300*4 + 70*9 = 600 + 1200 + 630 = 2430
    r = client.put(
        "/api/macros/goal?user_id=1",
        json={
            "calories_target": 3000,
            "protein_target_g": 150,
            "carbs_target_g": 300,
            "fat_target_g": 70,
        },
        environ_overrides=_env_auth(),
    )
    assert r.status_code == 200
    goal = r.json["goal"]
    assert goal["calories_target"] == 3000
    assert goal["protein_target_g"] == 150.0
    assert goal["carbs_target_g"] == 300.0
    assert goal["fat_target_g"] == 70.0
    assert goal["macro_calories_target"] == 2430


def test_put_goal_rejects_negative_values(client):
    r = client.put(
        "/api/macros/goal?user_id=1",
        json={"protein_target_g": -10},
        environ_overrides=_env_auth(),
    )
    assert r.status_code == 400
    assert r.json["error"] == "bad_request"