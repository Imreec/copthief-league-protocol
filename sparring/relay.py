"""A plain-HTTP message relay, mountable alongside the sparring peer.

Every communication method used in this league — MCP coordination channels, GitHub issue polling,
email forwarding — has failed at least once, and the cost has been measured in days. MCP channels
need both tunnels up. GitHub issues work but are polled at minute-scale latency and require a
token to post. Email needs a human in the loop.

This is the thing that should have existed from the start: a JSON endpoint at the peer's own
address that any ``curl`` can read and any ``curl`` can post to. No MCP session, no auth token
for reading, no tunnel on the caller's side. It runs alongside the game peer on the same port
and the same hostname.

    POST /messages         {"from": "best2934", "text": "thief restarted, drive when ready"}
    GET  /messages         [{"seq": 1, "from": "best2934", "text": "...", "ts": "..."}]
    GET  /messages?since=5 only messages with seq > 5

**Why unauthenticated.** Authentication would mean exchanging credentials before the first
message, which is the coordination problem the relay exists to solve. An opponent must be able to
reach you cold, with nothing but the URL, and leave a message you will see. Abuse is bounded by
the size cap and message limit, not by a gate that stops first contact from happening.

**Why at the peer's address.** The whole point of a stable hostname is that one URL reaches
everything. A relay on a separate host is one more thing that can be down independently, and
this league has already demonstrated that two independent things will be down at the same time.

Integration into a sparring peer::

    from starlette.routing import Route
    from sparring.relay import MessageRelay, build_routes

    relay = MessageRelay(persist=Path("results/relay_messages.json"))
    app_routes = [
        Route("/health", health_endpoint),
        *build_routes(relay),
        # ... your MCP mounts ...
    ]

Or with FastAPI/Starlette's ``include_router`` if you prefer that pattern.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

try:
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route
except ImportError:
    Request = Response = Route = None  # type: ignore[misc, assignment]

#: Hard caps — enough for a full league campaign, small enough that abuse is bounded.
MAX_MESSAGES = 500
MAX_MESSAGE_BYTES = 4096


class MessageRelay:
    """An in-memory message list that persists to disk so a restart does not lose the conversation.

    Thread-safe for the single-writer, multiple-reader pattern that a Starlette/uvicorn server
    provides — ``add`` is the only mutator and it writes atomically to disk.
    """

    def __init__(self, persist: Path | None = None) -> None:
        self.persist = persist or Path("relay_messages.json")
        self.messages: list[dict[str, Any]] = []
        self._seq = 0
        self._load()

    def _load(self) -> None:
        """Restore from disk, tolerating a missing or corrupt file."""
        try:
            data = json.loads(self.persist.read_text(encoding="utf-8"))
            self.messages = list(data)
            self._seq = max((m.get("seq", 0) for m in self.messages), default=0)
        except (OSError, ValueError, TypeError):
            pass

    def _save(self) -> None:
        """Best-effort persist. A failure here loses one message, not the service."""
        try:
            self.persist.parent.mkdir(parents=True, exist_ok=True)
            self.persist.write_text(json.dumps(self.messages, indent=2), encoding="utf-8")
        except OSError:
            pass

    def add(self, sender: str, text: str) -> dict[str, Any]:
        """Append one message and return it with its sequence number."""
        self._seq += 1
        msg: dict[str, Any] = {
            "seq": self._seq,
            "from": str(sender).strip()[:64],
            "text": str(text).strip()[:MAX_MESSAGE_BYTES],
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.messages.append(msg)
        if len(self.messages) > MAX_MESSAGES:
            self.messages = self.messages[-MAX_MESSAGES:]
        self._save()
        return msg

    def since(self, seq: int) -> list[dict[str, Any]]:
        """Messages with sequence number strictly greater than ``seq``."""
        return [m for m in self.messages if m.get("seq", 0) > seq]

    def all(self) -> list[dict[str, Any]]:
        """Every message, oldest first."""
        return list(self.messages)


def build_routes(relay: MessageRelay) -> list:
    """The two routes, ready to mount alongside the game peer.

    Returns ``Route`` objects if starlette is available; raises ``ImportError`` otherwise.

    Usage::

        from starlette.applications import Starlette
        from sparring.relay import MessageRelay, build_routes

        relay = MessageRelay()
        app = Starlette(routes=[*build_routes(relay), ...])
    """
    if Route is None:
        raise ImportError("starlette is required for the HTTP relay — pip install starlette")

    async def get_messages(request: Request) -> JSONResponse:
        """Read the conversation, optionally filtering by sequence."""
        since = int(request.query_params.get("since", 0))
        return JSONResponse(relay.since(since) if since else relay.all())

    async def post_message(request: Request) -> JSONResponse:
        """Leave a message. No auth — the point is that a stranger can reach you cold."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        sender = str(body.get("from", "anonymous"))
        text = str(body.get("text", ""))
        if not text.strip():
            return JSONResponse({"error": "empty message"}, status_code=400)
        msg = relay.add(sender, text)
        return JSONResponse(msg, status_code=201)

    return [
        Route("/messages", get_messages, methods=["GET"]),
        Route("/messages", post_message, methods=["POST"]),
    ]
