"""SQLite storage for AI-generated feature clusters and skills summaries."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class SkillFeature:
    feature_id: int
    name: str
    summary: str
    created_at: str
    updated_at: str
    commits: list[dict]
    skill_title: Optional[str]
    skill_content: Optional[str]
    skill_label: Optional[str]


class SkillsDB:
    """Lightweight SQLite helper for skills/feature clustering data."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS features (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feature_commits (
                    feature_id INTEGER NOT NULL,
                    commit_hash TEXT NOT NULL,
                    commit_short TEXT NOT NULL,
                    PRIMARY KEY (feature_id, commit_hash),
                    FOREIGN KEY(feature_id) REFERENCES features(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS skills (
                    feature_id INTEGER PRIMARY KEY,
                    title TEXT,
                    content TEXT,
                    label TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(feature_id) REFERENCES features(id) ON DELETE CASCADE
                );
                """
            )
            # Backfill schema if label column is missing
            cols = [row["name"] for row in conn.execute("PRAGMA table_info(skills)")]
            if "label" not in cols:
                conn.execute("ALTER TABLE skills ADD COLUMN label TEXT")

    def reset(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                DELETE FROM skills;
                DELETE FROM feature_commits;
                DELETE FROM features;
                """
            )

    def insert_feature(self, name: str, summary: str) -> int:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO features (name, summary, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, summary, now, now),
            )
            return int(cur.lastrowid)

    def set_feature_commits(self, feature_id: int, commits: Iterable[dict]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM feature_commits WHERE feature_id = ?", (feature_id,))
            conn.executemany(
                """
                INSERT INTO feature_commits (feature_id, commit_hash, commit_short)
                VALUES (?, ?, ?)
                """,
                [(feature_id, c["commit_hash"], c["commit_short"]) for c in commits],
            )

    def set_skill_doc(self, feature_id: int, title: str, content: str, label: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO skills (feature_id, title, content, label, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(feature_id) DO UPDATE SET
                    title = excluded.title,
                    content = excluded.content,
                    label = excluded.label,
                    updated_at = excluded.updated_at
                """,
                (feature_id, title, content, label, now, now),
            )

    def get_features(self) -> list[SkillFeature]:
        with self._connect() as conn:
            features_rows = conn.execute(
                """
                SELECT id, name, summary, created_at, updated_at
                FROM features
                ORDER BY id ASC
                """
            ).fetchall()

            commits_rows = conn.execute(
                """
                SELECT feature_id, commit_hash, commit_short
                FROM feature_commits
                ORDER BY commit_short ASC
                """
            ).fetchall()

            skills_rows = conn.execute(
                """
                SELECT feature_id, title, content, label
                FROM skills
                """
            ).fetchall()

        commits_by_feature: dict[int, list[dict]] = {}
        for row in commits_rows:
            commits_by_feature.setdefault(int(row["feature_id"]), []).append(
                {
                    "commit_hash": row["commit_hash"],
                    "commit_short": row["commit_short"],
                }
            )

        skills_by_feature = {
            int(row["feature_id"]): {
                "title": row["title"],
                "content": row["content"],
                "label": row["label"],
            }
            for row in skills_rows
        }

        features: list[SkillFeature] = []
        for row in features_rows:
            feature_id = int(row["id"])
            skill = skills_by_feature.get(feature_id, {})
            features.append(
                SkillFeature(
                    feature_id=feature_id,
                    name=row["name"],
                    summary=row["summary"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    commits=commits_by_feature.get(feature_id, []),
                    skill_title=skill.get("title"),
                    skill_content=skill.get("content"),
                    skill_label=skill.get("label"),
                )
            )
        return features
