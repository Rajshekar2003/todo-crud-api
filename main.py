import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from supabase import create_client, Client
from src.llm.schema import BookInput, EnrichmentOutput
from src.llm.client import call_model, call_model_repair, ModelTimeoutError
from src.llm.parse import parse_and_validate
from openai import APIStatusError
import json as _json
from datetime import datetime, timezone

load_dotenv()  # reads variables from .env into the environment

DATABASE_URL = os.environ["DATABASE_URL"]

# --- Supabase setup ---
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# --- end Supabase setup ---

def get_db_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            done BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    conn.commit()

    count = conn.execute("SELECT COUNT(*) AS count FROM tasks").fetchone()["count"]
    if count == 0:
        conn.execute(
            "INSERT INTO tasks (title, done) VALUES (%s, %s), (%s, %s), (%s, %s)",
            ("Buy milk", False, "Walk the dog", True, "Finish assignment", False)
        )
        conn.commit()

    conn.close()

init_db()

app = FastAPI()

print("Server running and connected to Supabase")

class TaskCreate(BaseModel):
    title: str | None = None

class TaskUpdate(BaseModel):
    title: str | None = None
    done: bool | None = None

class AuthCredentials(BaseModel):
    email: str | None = None
    password: str | None = None

@app.get("/")
def root():
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/auth/signup", status_code=201)
def signup(credentials: AuthCredentials):
    if not credentials.email or not credentials.password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    try:
        result = supabase.auth.sign_up({
            "email": credentials.email,
            "password": credentials.password
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result.user

@app.post("/auth/login")
def login(credentials: AuthCredentials):
    if not credentials.email or not credentials.password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    try:
        result = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid login credentials")

    return {
        "access_token": result.session.access_token,
        "refresh_token": result.session.refresh_token
    }

# --- Public & protected gates ---
@app.get("/public/info")
def public_info():
    return {"message": "Welcome stranger! This info is public."}

# --- Auth middleware (Stage 4, updated Stage 5 for Swagger bearer auth) ---
bearer_scheme = HTTPBearer(description="Paste your access token here (no need to type 'Bearer', Swagger adds it).")

def require_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Reusable guard: verifies the bearer token and returns the Supabase user.
    Apply this as a dependency to any route that should require login.
    Using HTTPBearer makes Swagger UI show a lock icon + Authorize button."""
    token = credentials.credentials if credentials else None
    if not token:
        raise HTTPException(status_code=401, detail="Access token required")

    try:
        result = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if result is None or result.user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return result.user
# --- end auth middleware ---

@app.get("/protected/profile")
def get_profile(user=Depends(require_user)):
    return {
        "id": user.id,
        "email": user.email,
        "created_at": user.created_at
    }

@app.get("/protected/dashboard")
def get_dashboard(user=Depends(require_user)):
    return {
        "message": f"Welcome to your dashboard, {user.email}!"
    }

@app.post("/auth/logout", status_code=204)
def logout(user=Depends(require_user)):
    supabase.auth.sign_out()
# --- end public & protected gates ---

# --- Stage 4: /enrich endpoint - real model call with timeout, retries, kill switch ---

LLM_STUB = os.environ.get("LLM_STUB") == "1"
LLM_ENABLED = os.environ.get("LLM_ENABLED", "true").lower() != "false"

QUARANTINE_LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "quarantine.jsonl")


def _write_quarantine_log(input_payload: dict, raw_output: str, error: str) -> None:
    os.makedirs(os.path.dirname(QUARANTINE_LOG_PATH), exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input": input_payload,
        "raw_output": raw_output,
        "error": error,
        "prompt_version": "enrich-v1",
    }
    with open(QUARANTINE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(_json.dumps(entry) + "\n")


@app.post("/enrich", response_model=EnrichmentOutput)
def enrich_book(payload: dict):
    # Manual validation so we can return 400 naming the offending field,
    # instead of FastAPI's default 422 for automatic body parsing.
    title = payload.get("title")
    if not title or not isinstance(title, str) or not (1 <= len(title) <= 300):
        raise HTTPException(status_code=400, detail="Field 'title' must be a string of 1-300 characters")

    description = payload.get("description")
    if description is not None and not isinstance(description, str):
        raise HTTPException(status_code=400, detail="Field 'description' must be a string or null")

    price_gbp = payload.get("price_gbp")
    if price_gbp is None or not isinstance(price_gbp, (int, float)):
        raise HTTPException(status_code=400, detail="Field 'price_gbp' must be a number")

    rating_text = payload.get("rating_text")
    valid_ratings = {"One", "Two", "Three", "Four", "Five"}
    if not rating_text or rating_text not in valid_ratings:
        raise HTTPException(status_code=400, detail="Field 'rating_text' must be one of One, Two, Three, Four, Five")

    availability_text = payload.get("availability_text")
    if not availability_text or not isinstance(availability_text, str):
        raise HTTPException(status_code=400, detail="Field 'availability_text' must be a string")

    book = BookInput(
        title=title,
        description=description,
        price_gbp=price_gbp,
        rating_text=rating_text,
        availability_text=availability_text,
    )

    if LLM_STUB:
        return EnrichmentOutput(
            category="fiction",
            summary="A stubbed summary standing in for a real model answer.",
            quality_flags=["missing_description"] if not book.description else [],
            confidence=0.42,
        )

    if not LLM_ENABLED:
        # Kill switch: skip the model entirely, return a safe deterministic
        # fallback instead. Zero model calls made.
        return EnrichmentOutput(
            category="other",
            summary="Enrichment is temporarily unavailable.",
            quality_flags=[],
            confidence=0.0,
        )

    try:
        raw_answer = call_model(book.model_dump())
    except ModelTimeoutError:
        raise HTTPException(status_code=504, detail="Model call timed out")
    except APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"LLM provider rejected the request: {e.status_code} {e.message}")

    result, error = parse_and_validate(raw_answer)

    if result is None:
        # First attempt failed - try one repair
        try:
            repaired_answer = call_model_repair(book.model_dump(), raw_answer, error)
        except ModelTimeoutError:
            raise HTTPException(status_code=504, detail="Model call timed out during repair")
        except APIStatusError as e:
            raise HTTPException(status_code=502, detail=f"LLM provider rejected the request: {e.status_code} {e.message}")

        result, error = parse_and_validate(repaired_answer)

        if result is None:
            # Repair also failed - quarantine and give up cleanly
            _write_quarantine_log(book.model_dump(), repaired_answer, error)
            raise HTTPException(status_code=422, detail=f"Model output could not be validated: {error}")

    return result
# --- end /enrich endpoint ---

@app.get("/tasks")
def get_tasks():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM tasks").fetchall()
    conn.close()
    return rows

@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return row

@app.post("/tasks", status_code=201)
def create_task(task: TaskCreate):
    if not task.title or not task.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")

    conn = get_db_connection()
    new_row = conn.execute(
        "INSERT INTO tasks (title, done) VALUES (%s, %s) RETURNING *",
        (task.title, False)
    ).fetchone()
    conn.commit()
    conn.close()
    return new_row

@app.put("/tasks/{task_id}")
def update_task(task_id: int, update: TaskUpdate):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()

    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    new_title = row["title"]
    if update.title is not None:
        if not update.title.strip():
            conn.close()
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        new_title = update.title

    new_done = row["done"]
    if update.done is not None:
        new_done = update.done

    updated_row = conn.execute(
        "UPDATE tasks SET title = %s, done = %s WHERE id = %s RETURNING *",
        (new_title, new_done, task_id)
    ).fetchone()
    conn.commit()
    conn.close()
    return updated_row

@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()

    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    conn.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
    conn.commit()
    conn.close()