from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from psycopg import connect
from psycopg.types.json import Json


if os.getenv("VERCEL") == "1":
    DATA_FILE = Path("/tmp/clinical-timeline-store.json")
else:
    DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "store.json"
InstructionType = Literal["medication", "temperature"]
MedicationOutcome = Literal["taken", "not_taken"]
DB_STORE_ID = "clinical-timeline"
STORE_LOCK = Lock()


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: InstructionType


class MedicationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: MedicationOutcome


class MedicationTaskResponse(MedicationResponse):
    task_id: str


class TemperatureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float = Field(ge=90, le=110)


class TemperatureTaskResponse(TemperatureResponse):
    task_id: str


app = FastAPI(title="Clinical Timeline Prototype")

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,https://clinical-timeline-interaction.vercel.app",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def blank_store() -> Dict[str, List[Dict[str, Any]]]:
    return {"tasks": [], "events": []}


def database_url() -> Optional[str]:
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not url:
        return None
    if url.startswith("postgres://"):
        return f"postgresql://{url.removeprefix('postgres://')}"
    return url


def ensure_store_shape(store: Any) -> Dict[str, List[Dict[str, Any]]]:
    if not isinstance(store, dict) or "tasks" not in store or "events" not in store:
        raise HTTPException(status_code=500, detail="Timeline store is invalid")
    if not isinstance(store["tasks"], list) or not isinstance(store["events"], list):
        raise HTTPException(status_code=500, detail="Timeline store is invalid")
    return store


def ensure_database_schema(url: str) -> None:
    with connect(url, autocommit=True) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS clinical_timeline_store (
                id text PRIMARY KEY,
                state jsonb NOT NULL,
                updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )


def load_database_store(url: str) -> Dict[str, List[Dict[str, Any]]]:
    ensure_database_schema(url)
    with connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT state FROM clinical_timeline_store WHERE id = %s",
                (DB_STORE_ID,),
            )
            row = cursor.fetchone()
    if row is None:
        return blank_store()
    return ensure_store_shape(row[0])


def save_database_store(url: str, store: Dict[str, List[Dict[str, Any]]]) -> None:
    ensure_database_schema(url)
    with connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO clinical_timeline_store (id, state, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (id)
                DO UPDATE SET state = EXCLUDED.state, updated_at = now()
                """,
                (DB_STORE_ID, Json(store)),
            )
        connection.commit()


def load_store() -> Dict[str, List[Dict[str, Any]]]:
    url = database_url()
    if url:
        return load_database_store(url)

    if not DATA_FILE.exists():
        return blank_store()
    try:
        store = json.loads(DATA_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Timeline store is unreadable") from exc
    return ensure_store_shape(store)


def save_store(store: Dict[str, List[Dict[str, Any]]]) -> None:
    url = database_url()
    if url:
        save_database_store(url, store)
        return

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = DATA_FILE.with_suffix(".tmp")
    temporary_file.write_text(json.dumps(store, indent=2))
    temporary_file.replace(DATA_FILE)


def task_text(task_type: InstructionType) -> str:
    if task_type == "medication":
        return "Tab. Dolo 650 1 tablet TDPC"
    return "Record Temperature (°F)"


def make_event(
    event_type: str,
    actor: Literal["doctor", "patient", "system"],
    title: str,
    summary: str,
    task_id: str,
    severity: Literal["neutral", "success", "warning", "critical"] = "neutral",
) -> Dict[str, Any]:
    return {
        "id": str(uuid4()),
        "task_id": task_id,
        "type": event_type,
        "actor": actor,
        "title": title,
        "summary": summary,
        "severity": severity,
        "created_at": timestamp(),
    }


def ordered_store(store: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "tasks": sorted(store["tasks"], key=lambda item: item["created_at"]),
        "events": sorted(store["events"], key=lambda item: item["created_at"]),
    }


def find_task(store: Dict[str, List[Dict[str, Any]]], task_id: str) -> Dict[str, Any]:
    for task in store["tasks"]:
        if task["id"] == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")


def ensure_pending(task: Dict[str, Any]) -> None:
    if task["status"] != "pending":
        raise HTTPException(status_code=409, detail="Task has already been completed")


def has_pending_task(store: Dict[str, List[Dict[str, Any]]]) -> bool:
    return any(task["status"] == "pending" for task in store["tasks"])


@app.get("/")
def root() -> Dict[str, str]:
    return {"name": "Clinical Timeline API", "status": "ok"}


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/state")
def get_state() -> Dict[str, List[Dict[str, Any]]]:
    with STORE_LOCK:
        return ordered_store(load_store())


@app.post("/api/tasks")
def create_task(payload: TaskCreate) -> Dict[str, List[Dict[str, Any]]]:
    with STORE_LOCK:
        store = load_store()
        if has_pending_task(store):
            raise HTTPException(
                status_code=409,
                detail="Complete the current task before creating another",
            )

        now = timestamp()
        task = {
            "id": str(uuid4()),
            "type": payload.type,
            "instruction": task_text(payload.type),
            "status": "pending",
            "response": None,
            "created_at": now,
            "updated_at": now,
        }
        store["tasks"].append(task)
        store["events"].append(
            make_event(
                "instruction_created",
                "doctor",
                "Instruction created",
                task["instruction"],
                task["id"],
            )
        )
        save_store(store)
        return ordered_store(store)


@app.post("/api/tasks/{task_id}/medication")
def respond_to_medication(
    task_id: str, payload: MedicationResponse
) -> Dict[str, List[Dict[str, Any]]]:
    with STORE_LOCK:
        store = load_store()
        task = find_task(store, task_id)
        if task["type"] != "medication":
            raise HTTPException(status_code=400, detail="Task is not a medication instruction")
        ensure_pending(task)

        task["status"] = "completed"
        task["response"] = {"outcome": payload.outcome}
        task["updated_at"] = timestamp()

        if payload.outcome == "taken":
            store["events"].append(
                make_event(
                    "task_completed",
                    "patient",
                    "Marked as taken",
                    "Patient confirmed the medication was taken.",
                    task_id,
                    "success",
                )
            )
        else:
            store["events"].append(
                make_event(
                    "task_not_taken",
                    "patient",
                    "Marked as not taken",
                    "Patient reported the medication was not taken.",
                    task_id,
                    "warning",
                )
            )
            store["events"].append(
                make_event(
                    "alert_triggered",
                    "system",
                    "Alert triggered: Medication not taken",
                    "Rule matched patient response: not taken.",
                    task_id,
                    "critical",
                )
            )

        save_store(store)
        return ordered_store(store)


@app.post("/api/medication-response")
def respond_to_medication_task(
    payload: MedicationTaskResponse,
) -> Dict[str, List[Dict[str, Any]]]:
    return respond_to_medication(payload.task_id, MedicationResponse(outcome=payload.outcome))


@app.post("/api/tasks/{task_id}/temperature")
def record_temperature(
    task_id: str, payload: TemperatureResponse
) -> Dict[str, List[Dict[str, Any]]]:
    with STORE_LOCK:
        store = load_store()
        task = find_task(store, task_id)
        if task["type"] != "temperature":
            raise HTTPException(status_code=400, detail="Task is not a temperature task")
        ensure_pending(task)

        value = round(payload.value, 1)
        task["status"] = "completed"
        task["response"] = {"value": value}
        task["updated_at"] = timestamp()

        store["events"].append(
            make_event(
                "temperature_recorded",
                "patient",
                f"Temperature recorded: {value:g}°F",
                "Patient submitted a temperature reading.",
                task_id,
                "warning" if value > 101 else "success",
            )
        )

        if value > 101:
            store["events"].append(
                make_event(
                    "alert_triggered",
                    "system",
                    "Alert triggered: High temperature",
                    f"Rule matched temperature reading above 101°F: {value:g}°F.",
                    task_id,
                    "critical",
                )
            )

        save_store(store)
        return ordered_store(store)


@app.post("/api/temperature-response")
def record_temperature_task(
    payload: TemperatureTaskResponse,
) -> Dict[str, List[Dict[str, Any]]]:
    return record_temperature(payload.task_id, TemperatureResponse(value=payload.value))


@app.post("/api/reset")
def reset() -> Dict[str, List[Dict[str, Any]]]:
    with STORE_LOCK:
        store = blank_store()
        save_store(store)
        return store
