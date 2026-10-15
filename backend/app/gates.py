import asyncio


class Approvals:
    """Holds tool calls that are waiting for a human to click Allow or Deny."""

    def __init__(self, timeout: float = 900):
        self.timeout = timeout
        self._pending: dict[str, asyncio.Future] = {}
        self._owner: dict[str, str] = {}  # who the waiting run belongs to

    async def wait(self, call_id: str, owner: str = "") -> bool:
        self._owner[call_id] = owner
        fut = self._pending[call_id] = asyncio.get_running_loop().create_future()
        try:
            return await asyncio.wait_for(fut, self.timeout)
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending.pop(call_id, None)
            self._owner.pop(call_id, None)

    def resolve(self, call_id: str, allow: bool, owner: str | None = None) -> bool:
        """Answer a waiting call. When an owner is given, only that owner may answer it."""
        if owner is not None and self._owner.get(call_id) != owner:
            return False
        fut = self._pending.get(call_id)
        if fut and not fut.done():
            fut.set_result(allow)
            return True
        return False
