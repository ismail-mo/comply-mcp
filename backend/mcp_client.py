"""MCP stdio subprocess client.

The subprocess lifecycle (stdio transport + ClientSession) is owned by a single
background task so the anyio cancel scopes are entered and exited in the same
task — calling stop() from a request handler no longer violates cancel-scope
ownership (which previously leaked orphan server processes on reconnect).

Public surface:
    await start() / stop() / restart()
    await call_tool(name, args, timeout=...)   # with one auto-reconnect retry
    get_tools() -> list[dict]                  # Anthropic-ready tool schemas
    connected: bool
"""

import asyncio
import logging
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("comply.mcp")

_SERVER_PATH = Path(__file__).parent / "mcp" / "server.py"

DEFAULT_TOOL_TIMEOUT = 120  # extract_design_values runs its own LLM call


class MCPClient:
    def __init__(self) -> None:
        self.tools: list[dict] = []
        self.connected: bool = False
        self._session: ClientSession | None = None
        self._task: asyncio.Task | None = None
        self._ready: asyncio.Event = asyncio.Event()
        self._shutdown: asyncio.Event = asyncio.Event()
        self._restart_lock = asyncio.Lock()

    async def _runner(self) -> None:
        """Owns the full subprocess + session lifecycle in one task."""
        try:
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(_SERVER_PATH)],
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    self.tools = [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "input_schema": tool.inputSchema,
                        }
                        for tool in result.tools
                    ]
                    self._session = session
                    self.connected = True
                    self._ready.set()
                    logger.info(
                        "MCP connected — tools: %s", [t["name"] for t in self.tools]
                    )
                    await self._shutdown.wait()
        except Exception as exc:
            logger.error("MCP runner failed: %s", exc)
        finally:
            self.connected = False
            self._session = None
            self._ready.set()  # unblock start() even on failure

    async def start(self) -> None:
        self._shutdown = asyncio.Event()
        self._ready = asyncio.Event()
        self._task = asyncio.create_task(self._runner(), name="mcp-runner")
        await self._ready.wait()

    async def stop(self) -> None:
        self._shutdown.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            except Exception as exc:
                logger.warning("MCP stop error: %s", exc)
        self._task = None
        self.connected = False

    async def restart(self) -> bool:
        async with self._restart_lock:
            if self.connected:  # another caller already reconnected
                return True
            logger.info("Restarting MCP subprocess")
            await self.stop()
            await self.start()
            return self.connected

    async def ensure_connected(self) -> bool:
        if self.connected and self._session is not None:
            return True
        return await self.restart()

    async def call_tool(
        self, name: str, args: dict, timeout: float = DEFAULT_TOOL_TIMEOUT
    ):
        """Call an MCP tool with a hard timeout and one reconnect+retry."""
        for attempt in (0, 1):
            if not self.connected or self._session is None:
                if not await self.restart():
                    raise RuntimeError("MCP subprocess unavailable")
            try:
                return await asyncio.wait_for(
                    self._session.call_tool(name, args), timeout=timeout
                )
            except asyncio.TimeoutError:
                # A hung subprocess is unrecoverable in-place — force restart.
                logger.error("MCP tool %s timed out after %ss", name, timeout)
                self.connected = False
                if attempt == 1:
                    raise RuntimeError(f"MCP tool '{name}' timed out")
            except Exception as exc:
                logger.error("MCP tool %s failed: %s", name, exc)
                self.connected = False
                if attempt == 1:
                    raise
        raise RuntimeError(f"MCP tool '{name}' failed after retry")

    def get_tools(self) -> list[dict]:
        if not self.connected:
            logger.warning("MCP not connected — tools unavailable")
        return self.tools
