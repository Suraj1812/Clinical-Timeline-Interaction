from fastapi.testclient import TestClient

from backend.app import main


def client_with_store(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.setattr(main, "DATA_FILE", tmp_path / "store.json")
    return TestClient(main.app)


def event_titles(response):
    return [event["title"] for event in response.json()["events"]]


def test_medication_not_taken_creates_alert(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    created = client.post("/api/tasks", json={"type": "medication"})
    assert created.status_code == 200
    task_id = created.json()["tasks"][0]["id"]

    response = client.post(
        f"/api/tasks/{task_id}/medication",
        json={"outcome": "not_taken"},
    )

    assert response.status_code == 200
    assert event_titles(response) == [
        "Instruction created",
        "Marked as not taken",
        "Alert triggered: Medication not taken",
    ]


def test_temperature_above_threshold_creates_alert(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    created = client.post("/api/tasks", json={"type": "temperature"})
    task_id = created.json()["tasks"][0]["id"]

    response = client.post(f"/api/tasks/{task_id}/temperature", json={"value": 102})

    assert response.status_code == 200
    assert event_titles(response) == [
        "Instruction created",
        "Temperature recorded: 102°F",
        "Alert triggered: High temperature",
    ]


def test_temperature_at_threshold_does_not_alert(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    created = client.post("/api/tasks", json={"type": "temperature"})
    task_id = created.json()["tasks"][0]["id"]

    response = client.post(f"/api/tasks/{task_id}/temperature", json={"value": 101})

    assert response.status_code == 200
    assert event_titles(response) == [
        "Instruction created",
        "Temperature recorded: 101°F",
    ]


def test_temperature_input_is_validated(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    created = client.post("/api/tasks", json={"type": "temperature"})
    task_id = created.json()["tasks"][0]["id"]

    response = client.post(f"/api/tasks/{task_id}/temperature", json={"value": 120})

    assert response.status_code == 422


def test_unknown_task_type_is_rejected(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    response = client.post("/api/tasks", json={"type": "blood_pressure"})

    assert response.status_code == 422


def test_extra_payload_fields_are_rejected(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    response = client.post(
        "/api/tasks",
        json={"type": "medication", "note": "not part of prototype scope"},
    )

    assert response.status_code == 422


def test_wrong_response_route_is_rejected(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    created = client.post("/api/tasks", json={"type": "medication"})
    task_id = created.json()["tasks"][0]["id"]

    response = client.post(f"/api/tasks/{task_id}/temperature", json={"value": 99})

    assert response.status_code == 400
    assert response.json()["detail"] == "Task is not a temperature task"


def test_flat_response_routes_work(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    medication = client.post("/api/tasks", json={"type": "medication"})
    medication_id = medication.json()["tasks"][0]["id"]
    medication_response = client.post(
        "/api/medication-response",
        json={"task_id": medication_id, "outcome": "not_taken"},
    )
    assert medication_response.status_code == 200
    assert "Alert triggered: Medication not taken" in event_titles(medication_response)

    client.post("/api/reset")
    temperature = client.post("/api/tasks", json={"type": "temperature"})
    temperature_id = temperature.json()["tasks"][0]["id"]
    temperature_response = client.post(
        "/api/temperature-response",
        json={"task_id": temperature_id, "value": 102},
    )

    assert temperature_response.status_code == 200
    assert "Alert triggered: High temperature" in event_titles(temperature_response)


def test_missing_task_returns_not_found(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    response = client.post(
        "/api/tasks/missing/medication",
        json={"outcome": "taken"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_completed_task_cannot_be_answered_twice(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    created = client.post("/api/tasks", json={"type": "medication"})
    task_id = created.json()["tasks"][0]["id"]
    assert client.post(
        f"/api/tasks/{task_id}/medication",
        json={"outcome": "taken"},
    ).status_code == 200

    response = client.post(
        f"/api/tasks/{task_id}/medication",
        json={"outcome": "not_taken"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Task has already been completed"


def test_only_one_task_can_be_pending(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    assert client.post("/api/tasks", json={"type": "medication"}).status_code == 200
    response = client.post("/api/tasks", json={"type": "temperature"})

    assert response.status_code == 409
    assert response.json()["detail"] == "Complete the current task before creating another"


def test_new_task_can_be_created_after_completion(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    created = client.post("/api/tasks", json={"type": "medication"})
    task_id = created.json()["tasks"][0]["id"]
    client.post(f"/api/tasks/{task_id}/medication", json={"outcome": "taken"})

    response = client.post("/api/tasks", json={"type": "temperature"})

    assert response.status_code == 200
    assert len(response.json()["tasks"]) == 2


def test_reset_clears_state(monkeypatch, tmp_path):
    client = client_with_store(monkeypatch, tmp_path)

    client.post("/api/tasks", json={"type": "medication"})
    response = client.post("/api/reset")

    assert response.status_code == 200
    assert response.json() == {"tasks": [], "events": []}


def test_database_url_prefers_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@example.test:5432/db")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://other:pass@example.test:5432/db")

    assert main.database_url() == "postgresql://user:pass@example.test:5432/db"


def test_database_url_falls_back_to_postgres_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_URL", "postgresql://user:pass@example.test:5432/db")

    assert main.database_url() == "postgresql://user:pass@example.test:5432/db"
