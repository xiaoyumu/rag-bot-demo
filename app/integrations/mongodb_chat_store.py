import asyncio
from datetime import UTC, datetime
from typing import Any

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:  # pragma: no cover - runtime guard for missing optional dependency
    AsyncIOMotorClient = None  # type: ignore[assignment]


class MongoChatStore:
    def __init__(
        self,
        mongodb_uri: str,
        db_name: str,
        collection_name: str,
        profile_collection_name: str,
        default_max_turns: int,
    ) -> None:
        if AsyncIOMotorClient is None:
            raise RuntimeError("motor is required for MongoChatStore. Install it via `pip install motor`.")
        self._client = AsyncIOMotorClient(mongodb_uri)
        self._collection = self._client[db_name][collection_name]
        self._profile_collection = self._client[db_name][profile_collection_name]
        self._default_max_turns = default_max_turns
        self._message_index_ready = False
        self._profile_index_ready = False
        self._index_lock = asyncio.Lock()

    async def create_indexes(self) -> None:
        if self._message_index_ready and self._profile_index_ready:
            return
        async with self._index_lock:
            if not self._message_index_ready:
                await self._collection.create_index(
                    [("session_id", 1), ("created_at", 1)],
                    name="session_created_at_idx",
                )
                self._message_index_ready = True

            if not self._profile_index_ready:
                await self._profile_collection.create_index(
                    [("session_id", 1)],
                    unique=True,
                    name="session_profile_unique_idx",
                )
                self._profile_index_ready = True

    async def get_recent_messages(
        self,
        session_id: str,
        limit_turns: int | None = None,
    ) -> list[dict[str, str]]:
        if not session_id:
            return []
        await self.create_indexes()

        turns = self._default_max_turns if limit_turns is None else max(limit_turns, 0)
        if turns == 0:
            return []

        cursor = self._collection.find(
            {"session_id": session_id},
            projection={"_id": False, "role": True, "content": True},
        ).sort("created_at", -1).limit(turns * 2)
        docs = await cursor.to_list(length=turns * 2)
        docs.reverse()
        return [
            {
                "role": str(doc.get("role", "")),
                "content": str(doc.get("content", "")),
            }
            for doc in docs
            if doc.get("role") and doc.get("content")
        ]

    async def append_messages(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not session_id:
            return
        await self.create_indexes()
        now = datetime.now(UTC)
        base_metadata = metadata or {}
        await self._collection.insert_many(
            [
                {
                    "session_id": session_id,
                    "role": "user",
                    "content": user_message,
                    "created_at": now,
                },
                {
                    "session_id": session_id,
                    "role": "assistant",
                    "content": assistant_message,
                    "created_at": now,
                    "metadata": base_metadata,
                },
            ]
        )

    async def get_profile(self, session_id: str) -> dict[str, Any]:
        if not session_id:
            return {}
        await self.create_indexes()
        doc = await self._profile_collection.find_one(
            {"session_id": session_id},
            projection={"_id": False, "profile": True},
        )
        profile = (doc or {}).get("profile")
        return profile if isinstance(profile, dict) else {}

    async def upsert_profile(self, session_id: str, patch: dict[str, Any]) -> None:
        if not session_id or not patch:
            return
        await self.create_indexes()
        now = datetime.now(UTC)
        update_doc: dict[str, Any] = {
            "$set": {"updated_at": now},
            "$setOnInsert": {"session_id": session_id, "created_at": now},
        }

        set_fields: dict[str, Any] = {}
        for key in ("language", "style"):
            value = patch.get(key)
            if isinstance(value, str) and value.strip():
                set_fields[f"profile.{key}"] = value.strip()
        if set_fields:
            update_doc["$set"].update(set_fields)

        constraints = patch.get("constraints")
        normalized_constraints: list[str] = []
        if isinstance(constraints, list):
            normalized_constraints = [
                str(item).strip()
                for item in constraints
                if isinstance(item, str) and item.strip()
            ]
        if normalized_constraints:
            update_doc["$addToSet"] = {
                "profile.constraints": {"$each": sorted(set(normalized_constraints))}
            }

        if len(update_doc["$set"]) == 1 and "$addToSet" not in update_doc:
            return

        await self._profile_collection.update_one(
            {"session_id": session_id},
            update_doc,
            upsert=True,
        )
