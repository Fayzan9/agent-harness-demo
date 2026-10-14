import asyncio


class Approvals:
    """Holds tool calls that are waiting for a human to click Allow or Deny."""

    def __init__(self, timeout: float = 900):
        self.timeout = timeout
        self._pending: dict[str, asyncio.Future] = {}

    async def wait(self, call_id: str) -> bool:
        fut = self._pending[call_id] = asyncio.get_running_loop().create_future()
        try:
            return await asyncio.wait_for(fut, self.timeout)
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending.pop(call_id, None)

    def resolve(self, call_id: str, allow: bool) -> bool:
        fut = self._pending.get(call_id)
        if fut and not fut.done():
            fut.set_result(allow)
            return True
        return False
