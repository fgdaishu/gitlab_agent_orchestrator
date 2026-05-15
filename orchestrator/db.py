from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from .models import Job, JobStatus, utc_now


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  project_id INTEGER NOT NULL,
  project_path TEXT NOT NULL,
  issue_iid INTEGER NOT NULL,
  issue_title TEXT NOT NULL,
  issue_description TEXT NOT NULL,
  trigger_type TEXT NOT NULL,
  trigger_label TEXT NOT NULL,
  agent TEXT NOT NULL,
  status TEXT NOT NULL,
  repo_http_url TEXT NOT NULL,
  default_branch TEXT NOT NULL,
  branch TEXT,
  merge_request_iid INTEGER,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT,
  log_path TEXT,
  sandbox_id INTEGER,
  workspace_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);

CREATE TABLE IF NOT EXISTS project_sandboxes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL UNIQUE,
  project_path TEXT NOT NULL,
  container_name TEXT NOT NULL UNIQUE,
  image TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_used_at TEXT,
  bootstrap_version TEXT,
  error TEXT
);

CREATE INDEX IF NOT EXISTS idx_project_sandboxes_status ON project_sandboxes(status);
"""


class JobStore:
    def __init__(self, path: Path):
        self.path = path
        if self.path.parent != Path("."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=MEMORY")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'jobs'").fetchone()
            if row and "UNIQUE(project_id, issue_iid, trigger_label, status)" in (row["sql"] or ""):
                conn.executescript(
                    """
                    ALTER TABLE jobs RENAME TO jobs_old_unique;
                    CREATE TABLE jobs (
                      id TEXT PRIMARY KEY,
                      project_id INTEGER NOT NULL,
                      project_path TEXT NOT NULL,
                      issue_iid INTEGER NOT NULL,
                      issue_title TEXT NOT NULL,
                      issue_description TEXT NOT NULL,
                      trigger_type TEXT NOT NULL,
                      trigger_label TEXT NOT NULL,
                      agent TEXT NOT NULL,
                      status TEXT NOT NULL,
                      repo_http_url TEXT NOT NULL,
                      default_branch TEXT NOT NULL,
                      branch TEXT,
                      merge_request_iid INTEGER,
                      created_at TEXT NOT NULL,
                      started_at TEXT,
                      finished_at TEXT,
                      error TEXT,
                      log_path TEXT,
                      sandbox_id INTEGER,
                      workspace_path TEXT
                    );
                    INSERT INTO jobs (
                      id, project_id, project_path, issue_iid, issue_title, issue_description,
                      trigger_type, trigger_label, agent, status, repo_http_url, default_branch,
                      branch, merge_request_iid, created_at, started_at, finished_at, error, log_path
                    )
                    SELECT
                      id, project_id, project_path, issue_iid, issue_title, issue_description,
                      trigger_type, trigger_label, agent, status, repo_http_url, default_branch,
                      branch, merge_request_iid, created_at, started_at, finished_at, error, log_path
                    FROM jobs_old_unique;
                    DROP TABLE jobs_old_unique;
                    """
                )
            self._ensure_column(conn, "jobs", "sandbox_id", "INTEGER")
            self._ensure_column(conn, "jobs", "workspace_path", "TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_project_sandboxes_status ON project_sandboxes(status)")

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_job(
        self,
        *,
        project_id: int,
        project_path: str,
        issue_iid: int,
        issue_title: str,
        issue_description: str,
        trigger_label: str,
        agent: str,
        repo_http_url: str,
        default_branch: str,
    ) -> Job:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM jobs
                WHERE project_id = ? AND issue_iid = ? AND trigger_label = ?
                  AND status IN (?, ?)
                ORDER BY created_at DESC LIMIT 1
                """,
                (project_id, issue_iid, trigger_label, JobStatus.pending, JobStatus.running),
            ).fetchone()
            if existing:
                return Job.from_row(existing)

            conn.execute(
                """
                INSERT INTO jobs (
                  id, project_id, project_path, issue_iid, issue_title, issue_description,
                  trigger_type, trigger_label, agent, status, repo_http_url, default_branch,
                  created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    project_id,
                    project_path,
                    issue_iid,
                    issue_title,
                    issue_description,
                    "label_added",
                    trigger_label,
                    agent,
                    JobStatus.pending,
                    repo_http_url,
                    default_branch,
                    utc_now(),
                ),
            )
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return Job.from_row(row)

    def get_job(self, job_id: str) -> Job | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return Job.from_row(row) if row else None

    def claim_next(self) -> Job | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM jobs AS candidate
                WHERE candidate.status = ?
                  AND NOT EXISTS (
                    SELECT 1 FROM jobs AS running
                    WHERE running.project_id = candidate.project_id
                      AND running.status = ?
                  )
                ORDER BY candidate.created_at LIMIT 1
                """,
                (JobStatus.pending, JobStatus.running),
            ).fetchone()
            if not row:
                conn.commit()
                return None
            conn.execute(
                "UPDATE jobs SET status = ?, started_at = ? WHERE id = ?",
                (JobStatus.running, utc_now(), row["id"]),
            )
            conn.commit()
        return self.get_job(row["id"])

    def mark_succeeded(self, job_id: str, *, branch: str, merge_request_iid: int | None, log_path: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, branch = ?, merge_request_iid = ?, finished_at = ?, log_path = ?, error = NULL
                WHERE id = ?
                """,
                (JobStatus.succeeded, branch, merge_request_iid, utc_now(), log_path, job_id),
            )

    def mark_failed(self, job_id: str, *, error: str, branch: str | None = None, log_path: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, branch = COALESCE(?, branch), finished_at = ?, error = ?, log_path = ?
                WHERE id = ?
                """,
                (JobStatus.failed, branch, utc_now(), error[:4000], log_path, job_id),
            )

    def mark_cancelled(self, job_id: str, *, error: str = "cancelled") -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, finished_at = ?, error = ?
                WHERE id = ? AND status IN (?, ?)
                """,
                (JobStatus.cancelled, utc_now(), error[:4000], job_id, JobStatus.pending, JobStatus.running),
            )

    def retry(self, job_id: str) -> Job | None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, started_at = NULL, finished_at = NULL, error = NULL, log_path = NULL
                WHERE id = ? AND status IN (?, ?)
                """,
                (JobStatus.pending, job_id, JobStatus.failed, JobStatus.cancelled),
            )
        return self.get_job(job_id)

    def latest_for_issue(self, project_id: int, issue_iid: int) -> Job | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE project_id = ? AND issue_iid = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (project_id, issue_iid),
            ).fetchone()
        return Job.from_row(row) if row else None

    def latest_for_issue_before(self, project_id: int, issue_iid: int, job_id: str) -> Job | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE project_id = ? AND issue_iid = ? AND id != ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (project_id, issue_iid, job_id),
            ).fetchone()
        return Job.from_row(row) if row else None

    def attach_workspace(self, job_id: str, *, sandbox_id: int | None, workspace_path: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE jobs SET sandbox_id = ?, workspace_path = ? WHERE id = ?",
                (sandbox_id, workspace_path, job_id),
            )

    def get_or_create_sandbox(
        self,
        *,
        project_id: int,
        project_path: str,
        container_name: str,
        image: str,
    ) -> sqlite3.Row:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO project_sandboxes (
                  project_id, project_path, container_name, image, status,
                  created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                  project_path = excluded.project_path,
                  container_name = excluded.container_name,
                  image = excluded.image,
                  updated_at = excluded.updated_at
                """,
                (project_id, project_path, container_name, image, "missing", now, now),
            )
            row = conn.execute("SELECT * FROM project_sandboxes WHERE project_id = ?", (project_id,)).fetchone()
        return row

    def get_sandbox(self, project_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM project_sandboxes WHERE project_id = ?", (project_id,)).fetchone()

    def update_sandbox(
        self,
        sandbox_id: int,
        *,
        status: str,
        bootstrap_version: str | None = None,
        error: str | None = None,
        touch_used: bool = False,
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE project_sandboxes
                SET status = ?,
                    updated_at = ?,
                    last_used_at = CASE WHEN ? THEN ? ELSE last_used_at END,
                    bootstrap_version = COALESCE(?, bootstrap_version),
                    error = ?
                WHERE id = ?
                """,
                (status, now, 1 if touch_used else 0, now, bootstrap_version, error, sandbox_id),
            )
