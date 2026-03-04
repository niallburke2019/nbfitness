def api_headers():
    return {
        "Content-Type": "application/json",
        "X-API-KEY": "supersecret123",
    }


def test_post_get_put_delete_meal(client):
    # POST create
    create_resp = client.post(
        "/api/meals",
        headers=api_headers(),
        json={
            "user_id": 1,
            "entry_date": "2026-03-01",
            "meal_type": "lunch",
            "food_name": "Chicken rice",
            "calories": 650,
            "protein_g": 45,
            "carbs_g": 80,
            "fat_g": 12,
        },
    )
    assert create_resp.status_code == 201
    data = create_resp.get_json()
    assert data["message"] == "created"
    entry_id = data["entry"]["id"]

    # GET one
    get_resp = client.get(
        f"/api/meals/{entry_id}?user_id=1",
        headers={"X-API-KEY": "supersecret123"},
    )
    assert get_resp.status_code == 200
    got = get_resp.get_json()["entry"]
    assert got["food_name"] == "Chicken rice"

    # PUT update (partial)
    put_resp = client.put(
        f"/api/meals/{entry_id}",
        headers=api_headers(),
        json={"user_id": 1, "calories": 700},
    )
    assert put_resp.status_code == 200
    updated = put_resp.get_json()["entry"]
    assert updated["calories"] == 700

    # DELETE
    del_resp = client.delete(
        f"/api/meals/{entry_id}",
        headers=api_headers(),
        json={"user_id": 1},
    )
    assert del_resp.status_code == 200
    assert del_resp.get_json()["message"] == "deleted"

    # GET should now 404
    get_after = client.get(
        f"/api/meals/{entry_id}?user_id=1",
        headers={"X-API-KEY": "supersecret123"},
    )
    assert get_after.status_code == 404