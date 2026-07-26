"""The FastMCP surface: four tools, and none of them may block.

The other module permitted outbound networking, and the only one that imports fastmcp.

**Every handler validates, enqueues, and returns.** None of them waits for game progress. Two
peers each awaiting the other inside a handler is an instant deadlock, and it is the
highest-severity failure available in this design — which is why the game loop lives on a worker
thread and the handlers only ever touch a queue.

The tool names and argument names mirror the reference exactly, including the asymmetry:
``negotiate``, ``receive_turn`` and ``receive_control`` take ``message``; ``submit_audit`` takes
``payload``.
"""

from __future__ import annotations

import threading
from pathlib import Path

from sparring import CODE_VERSION
from sparring.config import SparConfig
from sparring.preflight import assert_sparring_ready
from sparring.transport.loopback import Inboxes


def build_server(cfg: SparConfig, inboxes: Inboxes):
    """Construct the FastMCP app. Imported lazily so the zero-dependency tier stays honest."""
    from fastmcp import FastMCP

    mcp = FastMCP(name=f"copthief-sparring-{cfg.group_id}")

    @mcp.tool
    def negotiate(message: dict) -> dict:
        """Receive the opponent's signed game agreement."""
        inboxes.agreements.append(message)
        return {"ok": True}

    @mcp.tool
    def receive_turn(message: dict) -> dict:
        """Receive the opponent's turn message."""
        inboxes.turns.append(message)
        return {"ok": True}

    @mcp.tool
    def submit_audit(payload: dict) -> dict:
        """Receive the opponent's end-of-game audit reveal (records + nonces)."""
        inboxes.audits.append(payload)
        return {"ok": True}

    @mcp.tool
    def receive_control(message: dict) -> dict:
        """Receive an opponent control signal (enable / status / restart / quit)."""
        inboxes.controls.append(message)
        return {"ok": True}

    return mcp


def _port_is_held(host: str, port: int) -> bool:
    """A connect probe, never a trial bind.

    Binding to test would race the real server for the address — and on Windows two binds can
    both succeed, which would make this check quietly useless on the platform most likely to be
    running the peer.
    """
    import socket

    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def serve(cfg: SparConfig, *, host: str, port: int, peer_url: str | None,
          artifacts: Path, await_peer: bool = False) -> int:
    """Stand the peer up. Preflight first — the server never binds a port if it refuses."""
    report = assert_sparring_ready(cfg)

    if _port_is_held(host, port):
        print(f"  something is already listening on {host}:{port} — refusing to start a second "
              f"peer.\n"
              f"  A peer that starves behind another consumes a sub-game of the series and reports "
              f"a\n  timeout it did not cause. Check for an orphan: killing a shell does not kill "
              f"what it\n  spawned.")
        return 5

    inboxes = Inboxes()
    mcp = build_server(cfg, inboxes)

    print(f"SPARRING — UNCOUNTED (App. E rule 52) — NO REPORT OWED — mail surface ABSENT "
          f"(scan {report.mail_scan_sha256[:8]})")
    print(f"{CODE_VERSION}  listening on http://{host}:{port}/mcp")
    print(f"  wire=reference-v3  scent={cfg.scent_model}  policy={cfg.policy}  "
          f"group={cfg.group_id}")
    print(f"  artifacts -> {artifacts.resolve()}")
    print("  Expect NO report from this host: sparring is not a game under App. E rules 32/35.")
    if peer_url:
        print(f"  opponent: {peer_url}")
    elif await_peer:
        print("  awaiting a peer to dial us.\n"
              "  If you are exposing this through a tunnel, rewrite the Host header or fastmcp\n"
              "  will answer 421 to every request: Cloudflare "
              "originRequest.httpHostHeader: "
              f"127.0.0.1:{port} · ngrok --host-header=rewrite  (SPEC Appendix D).")

    stop = threading.Event()
    try:
        mcp.run(transport="http", host=host, port=port, show_banner=False)
    except KeyboardInterrupt:
        stop.set()
    return 0
