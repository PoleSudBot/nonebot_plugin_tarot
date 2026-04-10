import asyncio

_AI_RUNNING_USERS: set[tuple[str, str]] = set()
_AI_RUNNING_LOCK = asyncio.Lock()


async def acquire_ai_lock(platform: str, user_id: str) -> bool:
    key = (platform, user_id)
    async with _AI_RUNNING_LOCK:
        if key in _AI_RUNNING_USERS:
            return False
        _AI_RUNNING_USERS.add(key)
        return True


async def release_ai_lock(platform: str, user_id: str) -> None:
    key = (platform, user_id)
    async with _AI_RUNNING_LOCK:
        _AI_RUNNING_USERS.discard(key)
