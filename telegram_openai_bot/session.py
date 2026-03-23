from __future__ import annotations

from pathlib import Path

from agents.items import TResponseInputItem
from agents.memory import SQLiteSession
from agents.memory.session import SessionABC


class TurnLimitedSession(SessionABC):
    """Persist session history in SQLite while keeping only the last N user turns."""

    def __init__(self, session_id: str, db_path: str | Path, max_turns: int = 10):
        self.session_id = session_id
        self.max_turns = max_turns
        self._session = SQLiteSession(session_id=session_id, db_path=db_path)

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        items = await self._session.get_items()
        trimmed = self._trim_to_last_turns(items)
        if limit is None:
            return trimmed
        return trimmed[-limit:]

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        await self._session.add_items(items)
        await self._trim_and_persist()

    async def pop_item(self) -> TResponseInputItem | None:
        item = await self._session.pop_item()
        await self._trim_and_persist()
        return item

    async def clear_session(self) -> None:
        await self._session.clear_session()

    async def _trim_and_persist(self) -> None:
        items = await self._session.get_items()
        trimmed = self._trim_to_last_turns(items)
        if len(trimmed) == len(items):
            return
        await self._session.clear_session()
        await self._session.add_items(trimmed)

    def _trim_to_last_turns(self, items: list[TResponseInputItem]) -> list[TResponseInputItem]:
        user_indices = [
            index
            for index, item in enumerate(items)
            if isinstance(item, dict) and item.get("role") == "user"
        ]

        if len(user_indices) <= self.max_turns:
            return items

        start_index = user_indices[-self.max_turns]
        return items[start_index:]
