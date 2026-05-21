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
  workflow_id TEXT NOT NULL DEFAULT 'default_coding',
  workflow_task_id TEXT,
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

CREATE TABLE IF NOT EXISTS auto_issue_seen (
  project_id INTEGER NOT NULL,
  issue_iid INTEGER NOT NULL,
  issue_id INTEGER,
  project_path TEXT,
  seen_at TEXT NOT NULL,
  job_id TEXT,
  PRIMARY KEY (project_id, issue_iid)
);

CREATE TABLE IF NOT EXISTS poller_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
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
                      workflow_id TEXT NOT NULL DEFAULT 'default_coding',
                      workflow_task_id TEXT,
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
                      trigger_type, trigger_label, agent, workflow_id, workflow_task_id, status, repo_http_url, default_branch,
                      branch, merge_request_iid, created_at, started_at, finished_at, error, log_path
                    )
                    SELECT
                      id, project_id, project_path, issue_iid, issue_title, issue_description,
                      trigger_type, trigger_label, agent, 'default_coding', NULL, status, repo_http_url, default_branch,
                      branch, merge_request_iid, created_at, started_at, finished_at, error, log_path
                    FROM jobs_old_unique;
                    DROP TABLE jobs_old_unique;
                    """
                )
            self._ensure_column(conn, "jobs", "sandbox_id", "INTEGER")
            self._ensure_column(conn, "jobs", "workspace_path", "TEXT")
            self._ensure_column(conn, "jobs", "workflow_id", "TEXT NOT NULL DEFAULT 'default_coding'")
            self._ensure_column(conn, "jobs", "workflow_task_id", "TEXT")
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
        workflow_id: str = "default_coding",
        workflow_task_id: str | None = None,
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
                  trigger_type, trigger_label, agent, workflow_id, workflow_task_id, status, repo_http_url, default_branch,
                  created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    workflow_id,
                    workflow_task_id,
                    JobStatus.pending,
                    repo_http_url,
                    default_branch,
                    utc_now(),
                ),
            )
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return Job.from_row(row)

    def is_auto_issue_seen(self, project_id: int, issue_iid: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM auto_issue_seen WHERE project_id = ? AND issue_iid = ?",
                (project_id, issue_iid),
            ).fetchone()
        return row is not None

    def mark_auto_issue_seen(
        self,
        *,
        project_id: int,
        issue_iid: int,
        issue_id: int | None = None,
        project_path: str | None = None,
        job_id: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO auto_issue_seen (
                  project_id, issue_iid, issue_id, project_path, seen_at, job_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, issue_iid) DO UPDATE SET
                  issue_id = COALESCE(excluded.issue_id, auto_issue_seen.issue_id),
                  project_path = COALESCE(excluded.project_path, auto_issue_seen.project_path),
                  job_id = COALESCE(excluded.job_id, auto_issue_seen.job_id)
                """,
                (project_id, issue_iid, issue_id, project_path, utc_now(), job_id),
            )

    def get_poller_state(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM poller_state WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def set_poller_state(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO poller_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  value = excluded.value,
                  updated_at = excluded.updated_at
                """,
                (key, value, utc_now()),
            )

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
