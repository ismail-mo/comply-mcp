import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("comply.mcp")

_SERVER_PATH = Path(__file__).parent / "mcp" / "server.py"


class MCPClient:
    def __init__(self) -> None:
        self.tools: list = []
        self.connected: bool = False
        self._stdio_ctx = None
        self._session_ctx = None
        self._session: ClientSession | None = None

    @property
    def pid(self) -> int | None:
        try:
            if self._stdio_ctx is None:
                return None
            for attr in ("_process", "process", "_proc"):
                proc = getattr(self._stdio_ctx, attr, None)
                if proc is not None:
                    return getattr(proc, "pid", None)
            return None
        except Exception:
            return None

    async def start(self) -> None:
        try:
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(_SERVER_PATH)],
            )
            self._stdio_ctx = stdio_client(params)
            read, write = await self._stdio_ctx.__aenter__()

            self._session_ctx = ClientSession(read, write)
            self._session = await self._session_ctx.__aenter__()
            await self._session.initialize()

            result = await self._session.list_tools()
            self.tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                for tool in result.tools
            ]
            self.connected = True
            logger.info("MCP connected — tools: %s", [t["name"] for t in self.tools])
        except Exception as exc:
            logger.error("MCP startup failed: %s", exc)
            self.tools = []
            self.connected = False

    async def stop(self) -> None:
        try:
            if self._session_ctx is not None:
                await self._session_ctx.__aexit__(None, None, None)
        except Exception as exc:
            logger.warning("MCP session close error: %s", exc)
        try:
            if self._stdio_ctx is not None:
                await self._stdio_ctx.__aexit__(None, None, None)
        except Exception as exc:
            logger.warning("MCP stdio close error: %s", exc)
        self._session = None
        self._session_ctx = None
        self._stdio_ctx = None
        self.connected = False

    async def ensure_connected(self) -> bool:
        try:
            if self.connected and self._session is not None:
                pid = self.pid
                if pid is not None:
                    try:
                        os.kill(pid, 0)
                        return True
                    except ProcessLookupError:
                        logger.warning("MCP subprocess (pid=%d) has died — reconnecting", pid)
                    except PermissionError:
                        return True
                else:
                    try:
                        result = await self._session.list_tools()
                        self.tools = [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.inputSchema,
                            }
                            for tool in result.tools
                        ]
                        return True
                    except Exception:
                        logger.warning("MCP session health check failed — reconnecting")
            await self.stop()
            await self.start()
            logger.info("MCP subprocess reconnected")
            return self.connected
        except Exception as exc:
            logger.error("MCP ensure_connected failed: %s", exc)
            return self.connected

    def get_tools(self) -> list:
        if not self.connected:
            logger.warning("MCP not connected — tools unavailable")
        return self.tools
