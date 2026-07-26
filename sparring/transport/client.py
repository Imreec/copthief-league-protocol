"""Reaching the opponent over MCP, and telling a stranger what is wrong when we cannot.

One of two modules permitted to open outbound networking (``guards/no_mail.py`` rule NM-5). The
whole fastmcp surface lives here and in ``server.py`` — about a hundred lines between them — so a
breaking release upstream is a two-file fix and never touches the rules.

``diagnose`` is the pre-match probe worth running before you agree a start time. The status codes
are not degrees of one problem, and confusing them costs windows:

* ``406`` — an MCP peer is listening and correctly refused a browser-shaped GET. **This is ready.**
* ``502`` — the edge answered but found no origin: either their peer has not started, or their
  tunnel has no ingress. Indistinguishable from outside, which is why each side must prove its
  *own* path (``tools/netcheck.py --loopback``).
* ``421`` — a DNS-rebinding guard rejected the Host header, which is every request through a
  tunnel. Fixed at the tunnel, not in code (SPEC Appendix D).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

TOOLS = ("negotiate", "receive_turn", "submit_audit", "receive_control")


class PeerUnreachable(Exception):
    pass


def _post(url: str, body: dict, timeout: float) -> tuple[int, str]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(8192).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(2048).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        raise PeerUnreachable(str(exc)) from exc


class McpClient:
    """The four calls, with the argument-name asymmetry the reference defines.

    ``submit_audit`` takes ``payload``; the other three take ``message``. It looks like an
    inconsistency and it is load-bearing: a peer that sends ``message`` to ``submit_audit`` gets a
    schema error at the one moment both sides are trying to agree on a result.

    MCP over streamable HTTP is **session-oriented**: a bare `tools/call` without an established
    session is answered ``400 Missing session ID``, which reads like an unreachable peer and is
    not one. So the session is held open here rather than re-established per call, on a private
    event loop this class owns — the game loop stays synchronous, which is what keeps the rules,
    the state machine and the tests free of async.
    """

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        self.url = url
        self.timeout = timeout
        self._loop = None
        self._client = None
        self._entered = False

    def _ensure_session(self) -> None:
        import asyncio
        import threading

        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            threading.Thread(target=self._loop.run_forever, daemon=True).start()
        if self._entered:
            return

        from fastmcp import Client

        self._client = Client(self.url)
        try:
            self._await(self._client.__aenter__())
            self._entered = True
        except Exception as exc:                       # noqa: BLE001 — surfaced as one diagnosis
            self._client = None
            raise PeerUnreachable(f"could not open an MCP session at {self.url}: {exc}") from exc

    def _await(self, coro):
        import asyncio

        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(self.timeout)

    def _call(self, tool: str, argument: dict) -> dict:
        self._ensure_session()
        arg_name = "payload" if tool == "submit_audit" else "message"
        try:
            self._await(self._client.call_tool(tool, {arg_name: argument}))
        except Exception as exc:                       # noqa: BLE001
            raise PeerUnreachable(f"{tool} -> {type(exc).__name__}: {exc}") from exc
        return {"ok": True}

    def close(self) -> None:
        if self._entered and self._client is not None:
            try:
                self._await(self._client.__aexit__(None, None, None))
            except Exception:                          # noqa: BLE001 — closing is best-effort
                pass
        self._entered = False

    def negotiate(self, message: dict) -> dict:
        return self._call("negotiate", message)

    def receive_turn(self, message: dict) -> dict:
        return self._call("receive_turn", message)

    def submit_audit(self, payload: dict) -> dict:
        return self._call("submit_audit", payload)

    def receive_control(self, message: dict) -> dict:
        return self._call("receive_control", message)


def diagnose(url: str, timeout: float = 10.0) -> int:
    """Classify a peer URL and say what to do about it. Returns a CLI exit code."""
    print(f"probing {url}")
    try:
        status, text = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                   "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                              "clientInfo": {"name": "sparring-doctor",
                                                             "version": "1"}}}, timeout)
    except PeerUnreachable as exc:
        print(f"  UNREACHABLE — {exc}\n"
              f"  Nothing accepted a connection. Check the URL, the tunnel process, and DNS.")
        return 7

    if status == 421:
        print("  HOST HEADER NOT REWRITTEN (421). Their MCP server's DNS-rebinding guard rejects\n"
              "  any Host that is not its bind address — which is every request through a tunnel.\n"
              "  Fix at the tunnel, no code change:\n"
              "    Cloudflare  originRequest.httpHostHeader: 127.0.0.1:<port>\n"
              "    ngrok       --host-header=rewrite\n"
              "  (SPEC Appendix D, kit issue #4.)")
        return 7
    if status == 502:
        print("  EDGE UP, NOTHING BEHIND IT (502). Their peer has not started, or their connector\n"
              "  is running with no ingress. Those look identical from here — ask them to run\n"
              "  `python tools/netcheck.py --loopback <port> <their hostnames>`.")
        return 7
    if status == 406:
        print("  PEER LISTENING (406) — an MCP streamable-HTTP server refused a browser-shaped\n"
              "  request, which is the healthy answer. This is the state to poll for before a\n"
              "  scheduled start.")
        return 0

    ok = "protocolVersion" in text or "result" in text
    print(f"  {status} — {'answered an MCP initialize' if ok else text[:160]}")
    if not ok:
        return 7
    print(f"  tools this peer must expose: {', '.join(TOOLS)}\n"
          f"  note submit_audit takes `payload`; the other three take `message`.")
    return 0
