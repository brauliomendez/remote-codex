from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChatState:
    chat_id: int
    workdir: Path
    thread_id: str | None


@dataclass(frozen=True)
class ChatSessionRef:
    thread_id: str
    workdir: Path
    last_used_at: str


class ChatStateStore:
    def __init__(self, db_path: Path, default_workdir: Path):
        self.db_path = db_path
        self.default_workdir = default_workdir
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_state (
                    chat_id INTEGER PRIMARY KEY,
                    workdir TEXT NOT NULL,
                    thread_id TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    chat_id INTEGER NOT NULL,
                    thread_id TEXT NOT NULL,
                    workdir TEXT NOT NULL,
                    last_used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, thread_id)
                )
                """
            )

    def get_chat_state(self, chat_id: int) -> ChatState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT workdir, thread_id FROM chat_state WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if row is None:
            return ChatState(chat_id=chat_id, workdir=self.default_workdir, thread_id=None)
        return ChatState(
            chat_id=chat_id,
            workdir=Path(row["workdir"]),
            thread_id=row["thread_id"],
        )

    def set_workdir(self, chat_id: int, workdir: Path) -> ChatState:
        state = ChatState(chat_id=chat_id, workdir=workdir, thread_id=None)
        self._upsert(state)
        return state

    def set_thread_id(self, chat_id: int, thread_id: str | None) -> ChatState:
        current = self.get_chat_state(chat_id)
        state = ChatState(chat_id=chat_id, workdir=current.workdir, thread_id=thread_id)
        self._upsert(state)
        if thread_id is not None:
            self._remember_session(chat_id=chat_id, thread_id=thread_id, workdir=current.workdir)
        return state

    def reset_chat(self, chat_id: int) -> ChatState:
        current = self.get_chat_state(chat_id)
        state = ChatState(chat_id=chat_id, workdir=current.workdir, thread_id=None)
        self._upsert(state)
        return state

    def clear_chat_history(self, chat_id: int) -> ChatState:
        current = self.get_chat_state(chat_id)
        with self._connect() as connection:
            connection.execute("DELETE FROM chat_sessions WHERE chat_id = ?", (chat_id,))
        state = ChatState(chat_id=chat_id, workdir=current.workdir, thread_id=None)
        self._upsert(state)
        return state

    def list_chat_sessions(self, chat_id: int, limit: int = 10) -> list[ChatSessionRef]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT thread_id, workdir, last_used_at
                FROM chat_sessions
                WHERE chat_id = ?
                ORDER BY datetime(last_used_at) DESC, rowid DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        return [
            ChatSessionRef(
                thread_id=row["thread_id"],
                workdir=Path(row["workdir"]),
                last_used_at=row["last_used_at"],
            )
            for row in rows
        ]

    def resume_session(self, chat_id: int, thread_id: str) -> ChatState:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT workdir
                FROM chat_sessions
                WHERE chat_id = ? AND thread_id = ?
                """,
                (chat_id, thread_id),
            ).fetchone()
        if row is None:
            raise KeyError(thread_id)
        workdir = Path(row["workdir"])
        state = ChatState(chat_id=chat_id, workdir=workdir, thread_id=thread_id)
        self._upsert(state)
        self._remember_session(chat_id=chat_id, thread_id=thread_id, workdir=workdir)
        return state

    def _upsert(self, state: ChatState) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_state (chat_id, workdir, thread_id)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    workdir = excluded.workdir,
                    thread_id = excluded.thread_id
                """,
                (state.chat_id, str(state.workdir), state.thread_id),
            )

    def _remember_session(self, chat_id: int, thread_id: str, workdir: Path) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_sessions (chat_id, thread_id, workdir, last_used_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id, thread_id) DO UPDATE SET
                    workdir = excluded.workdir,
                    last_used_at = CURRENT_TIMESTAMP
                """,
                (chat_id, thread_id, str(workdir)),
            )
