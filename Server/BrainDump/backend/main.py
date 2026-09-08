"""
BrainDump — FastAPI main application
Ultra-lightweight: single worker, async SQLite, no ORM overhead.
Memory target: < 50 MB RAM
"""
import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import get_db, init_db
from llm import extract_tasks
from auth import require_auth, verify_password, create_token, verify_token
from models import (
    LoginRequest,
    AuthResponse,
    ProcessRequest,
    ProcessResponse,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    WidgetResponse,
    WidgetTask,
    ExtractedTask,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("braindump")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("BrainDump starting — initialising DB…")
    await init_db()
    logger.info("DB ready.")
    yield
    logger.info("BrainDump shutting down.")


app = FastAPI(
    title="BrainDump API",
    version="1.1.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# CORS — allow same-origin + local dev
_ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://garcarzp.online,http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ─────────────────── AUTH ROUTES ────────────────────

@app.post("/api/auth/login", response_model=AuthResponse)
async def login(body: LoginRequest, response: Response):
    if not verify_password(body.password):
        raise HTTPException(status_code=401, detail="Nesprávne heslo")
    token = create_token()
    response.set_cookie(
        key="braindump_session",
        value=token,
        max_age=60 * 60 * 24 * 180,  # 180 days
        httponly=True,
        samesite="lax",
        secure=True,
        path="/",
    )
    return AuthResponse(status="ok", token=token, message="Prihlásenie úspešné")


@app.get("/api/auth/check")
async def check_auth(request: Request):
    try:
        await require_auth(request)
        return {"authenticated": True}
    except HTTPException:
        return {"authenticated": False}


@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie(key="braindump_session", path="/")
    return {"status": "ok", "message": "Odhlásený"}


# ─────────────────── HELPERS ────────────────────

async def _get_task_or_404(task_id: int) -> dict:
    async with get_db() as db:
        row = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = await row.fetchone()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return dict(task)


# ─────────────────── ROUTES ────────────────────

@app.post("/api/tasks/process", response_model=ProcessResponse, status_code=201, dependencies=[Depends(require_auth)])
async def process_voice_text(body: ProcessRequest):
    """
    Accept raw transcript text, send to LLM, extract tasks (with due_date),
    save to DB, and return the created task objects.
    """
    try:
        extracted = await extract_tasks(body.text)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not extracted:
        return ProcessResponse(tasks=[], raw_extracted=[])

    created: list[TaskOut] = []
    async with get_db() as db:
        for item in extracted:
            cur = await db.execute(
                "INSERT INTO tasks (text, category, due_date) VALUES (?, ?, ?) RETURNING *",
                (item["text"], item["category"], item.get("due_date")),
            )
            row = await cur.fetchone()
            created.append(TaskOut.from_row(row))
        await db.commit()

    return ProcessResponse(
        tasks=created,
        raw_extracted=[ExtractedTask(**item) for item in extracted],
    )


@app.get("/api/tasks", response_model=list[TaskOut], dependencies=[Depends(require_auth)])
async def list_tasks(
    category: Optional[str] = Query(None),
    done: Optional[bool] = Query(None),
    due_date: Optional[str] = Query(None, description="YYYY-MM-DD or 'inbox' for NULL due_date"),
    limit: int = Query(200, le=500),
):
    """List all tasks with optional filtering including due_date."""
    conditions = []
    params: list = []

    if category is not None:
        conditions.append("category = ?")
        params.append(category)
    if done is not None:
        conditions.append("done = ?")
        params.append(1 if done else 0)
    if due_date == "inbox":
        conditions.append("due_date IS NULL")
    elif due_date is not None:
        conditions.append("due_date = ?")
        params.append(due_date)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"SELECT * FROM tasks {where} ORDER BY done ASC, created_at DESC LIMIT ?"
    params.append(limit)

    async with get_db() as db:
        cur = await db.execute(sql, params)
        rows = await cur.fetchall()

    return [TaskOut.from_row(r) for r in rows]


@app.post("/api/tasks", response_model=TaskOut, status_code=201, dependencies=[Depends(require_auth)])
async def create_task(body: TaskCreate):
    """Manually create a single task, optionally with a due_date."""
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO tasks (text, category, due_date) VALUES (?, ?, ?) RETURNING *",
            (body.text, body.category, body.due_date),
        )
        row = await cur.fetchone()
        await db.commit()
    return TaskOut.from_row(row)


@app.patch("/api/tasks/{task_id}", response_model=TaskOut, dependencies=[Depends(require_auth)])
async def update_task(task_id: int, body: TaskUpdate):
    """Update task fields (done, text, category, due_date). Send due_date='' to clear it."""
    updates: list[str] = []
    params: list = []

    if body.text is not None:
        updates.append("text = ?")
        params.append(body.text)
    if body.category is not None:
        updates.append("category = ?")
        params.append(body.category)
    if body.done is not None:
        updates.append("done = ?")
        params.append(1 if body.done else 0)
    if body.due_date is not None:
        updates.append("due_date = ?")
        # empty string → clear to NULL
        params.append(body.due_date if body.due_date.strip() else None)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(task_id)

    async with get_db() as db:
        await db.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut.from_row(row)


@app.delete("/api/tasks/{task_id}", status_code=204, dependencies=[Depends(require_auth)])
async def delete_task(task_id: int):
    """Delete a task by ID."""
    async with get_db() as db:
        cur = await db.execute("DELETE FROM tasks WHERE id = ? RETURNING id", (task_id,))
        deleted = await cur.fetchone()
        await db.commit()
    if deleted is None:
        raise HTTPException(status_code=404, detail="Task not found")


@app.get("/api/tasks/widget", response_model=WidgetResponse, dependencies=[Depends(require_auth)])
async def widget_tasks(limit: int = Query(10, le=20)):
    """
    Lightweight endpoint for Android widgets.
    Returns:
      - Today's open tasks (due_date == today)
      - Overdue open tasks (due_date < today)
      - today_count: number of tasks due today
      - total_open: all open tasks count
    """
    today_iso = date.today().isoformat()

    async with get_db() as db:
        # Total open count
        count_cur = await db.execute("SELECT COUNT(*) FROM tasks WHERE done = 0")
        total_open = (await count_cur.fetchone())[0]

        # Today's task count
        today_count_cur = await db.execute(
            "SELECT COUNT(*) FROM tasks WHERE done = 0 AND due_date = ?",
            (today_iso,),
        )
        today_count = (await today_count_cur.fetchone())[0]

        # Today's tasks + overdue tasks, ordered by priority
        cur = await db.execute(
            """
            SELECT id, text, category, due_date FROM tasks
            WHERE done = 0
              AND (due_date = ? OR (due_date IS NOT NULL AND due_date < ?))
            ORDER BY
                due_date ASC,
                CASE category
                    WHEN 'Work'      THEN 1
                    WHEN 'Groceries' THEN 2
                    WHEN 'Personal'  THEN 3
                    ELSE 4
                END,
                created_at DESC
            LIMIT ?
            """,
            (today_iso, today_iso, limit),
        )
        rows = await cur.fetchall()

    return WidgetResponse(
        total_open=total_open,
        today_count=today_count,
        tasks=[
            WidgetTask(
                id=r["id"],
                text=r["text"],
                category=r["category"],
                due_date=r["due_date"],
                overdue=(r["due_date"] is not None and r["due_date"] < today_iso),
            )
            for r in rows
        ],
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "braindump", "version": "1.1.0"}
