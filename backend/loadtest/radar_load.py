"""Closed-loop load generator that behaves like the real frontend.

Each virtual user (VU) does what `frontend/src/store/bootstrap.ts` does on a
page load: the three static fetches, the ten-request `hydrate()` burst, then a
WebSocket it holds open and keeps reading. Three scenarios:

  boot   VUs arrive uniformly over --ramp seconds, each boots once and holds the
         socket for --hold seconds. "How many readers can open the map at once."
  storm  Every VU is already connected; then all sockets drop at the same
         moment and every VU reconnects ~1 s later — what a backend
         restart/deploy does to a full house. --storm-mode picks what the
         client does on reconnect: `hydrate` (the ten requests of the pre-0.55
         client), `delta` (GET /sync with the position it saw — the server is
         still the same process, so it answers current/delta) or `full`
         (GET /sync with a foreign epoch — what every client gets after a real
         deploy: one snapshot response instead of ten).
  hold   VUs connect (ramp) and only hold the socket. Measures broadcast fan-out:
         for every frame the server sends, how far apart the first and the last
         client receive it, and (for 'ping') server_time -> client latency.

Usage (against the isolated server `run_local.sh` starts):

    .venv/bin/python -m loadtest.radar_load --users 200 --ramp 20 --hold 60
    .venv/bin/python -m loadtest.radar_load --scenario storm --users 500
    .venv/bin/python -m loadtest.radar_load --base https://<staging>.up.railway.app \
        --ws wss://<staging>.up.railway.app/ws/threats --users 300

Never point it at production: it is indistinguishable from a real crowd.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
import websockets

STATIC_PATHS = ["/districts", "/districts/boundaries", "/regions"]


def hydrate_paths(feed_limit: int) -> list[str]:
    return [
        "/threats/active",
        "/incidents/active",
        "/incidents/recent?limit=20",
        "/axes/active",
        "/alerts/recent?limit=60",
        "/alert-zones",
        f"/events/recent?limit={feed_limit}&region=kyiv",
        "/notices/recent?limit=30",
        "/sources",
        "/health",
    ]


@dataclass
class Stats:
    latency_ms: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    status: dict[str, dict[int, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    ws_connect_ms: list[float] = field(default_factory=list)
    ws_failed: int = 0
    ws_dropped: int = 0
    boot_ms: list[float] = field(default_factory=list)
    stream: dict[int, tuple[int, int]] = field(default_factory=dict)
    sync_status: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    frame_arrivals: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    ping_latency_ms: list[float] = field(default_factory=list)
    frames_received: int = 0
    server_samples: list[tuple[float, float, float]] = field(default_factory=list)

    def endpoint_key(self, path: str) -> str:
        return path.split("?")[0]


def pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((p / 100) * (len(ordered) - 1))))
    return ordered[idx]


async def get(client: httpx.AsyncClient, path: str, stats: Stats) -> None:
    key = stats.endpoint_key(path)
    t0 = time.perf_counter()
    try:
        res = await client.get(path)
        stats.status[key][res.status_code] += 1
    except Exception as ex:
        stats.errors[f"{key}: {type(ex).__name__}"] += 1
        return
    stats.latency_ms[key].append((time.perf_counter() - t0) * 1000)


async def boot(client: httpx.AsyncClient, stats: Stats, feed_limit: int) -> None:
    t0 = time.perf_counter()
    await asyncio.gather(*(get(client, p, stats) for p in STATIC_PATHS))
    await asyncio.gather(*(get(client, p, stats) for p in hydrate_paths(feed_limit)))
    stats.boot_ms.append((time.perf_counter() - t0) * 1000)


def frame_key(raw: str) -> str | None:
    try:
        msg = json.loads(raw)
    except ValueError:
        return None
    if msg.get("type") == "online":
        return None
    return raw


async def hold_socket(
    ws_url: str, stats: Stats, until: float, vu: int = 0
) -> None:
    t0 = time.perf_counter()
    try:
        ws = await websockets.connect(ws_url, open_timeout=30, max_queue=None)
    except Exception:
        stats.ws_failed += 1
        return
    stats.ws_connect_ms.append((time.perf_counter() - t0) * 1000)
    try:
        while True:
            remaining = until - time.monotonic()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except TimeoutError:
                break
            now = time.time()
            stats.frames_received += 1
            _track_position(raw, stats, vu)
            key = frame_key(raw)
            if key is None:
                continue
            stats.frame_arrivals[key].append(now)
            if '"type":"ping"' in raw or '"type": "ping"' in raw:
                sent = datetime.fromisoformat(json.loads(raw)["server_time"])
                stats.ping_latency_ms.append((now - sent.timestamp()) * 1000)
    except websockets.ConnectionClosed:
        stats.ws_dropped += 1
    finally:
        await ws.close()


def _track_position(raw: str, stats: Stats, vu: int) -> None:
    if '"epoch":' not in raw:
        return
    try:
        msg = json.loads(raw)
    except ValueError:
        return
    if msg.get("epoch") is not None and msg.get("seq") is not None:
        stats.stream[vu] = (msg["epoch"], msg["seq"])


async def resume(client: httpx.AsyncClient, stats: Stats, vu: int, mode: str, feed_limit: int) -> None:
    """What the 0.55+ client does on reconnect (ws.ts resumeStream)."""
    epoch, seq = stats.stream.get(vu, (None, None))
    if mode == "full" or epoch is None:
        epoch, seq = 0, 0
    path = f"/sync?limit={feed_limit}&region=kyiv&epoch={epoch}&seq={seq}"
    key = "/sync"
    t0 = time.perf_counter()
    try:
        res = await client.get(path)
        stats.status[key][res.status_code] += 1
        if res.status_code == 200:
            stats.sync_status[res.json()["status"]] += 1
    except Exception as ex:
        stats.errors[f"{key}: {type(ex).__name__}"] += 1
        return
    stats.latency_ms[key].append((time.perf_counter() - t0) * 1000)
    stats.boot_ms.append((time.perf_counter() - t0) * 1000)


def new_client(base: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base, timeout=httpx.Timeout(30.0), limits=httpx.Limits(max_connections=6)
    )


async def vu_boot(args, stats: Stats, delay: float, until: float) -> None:
    await asyncio.sleep(delay)
    async with new_client(args.base) as client:
        await boot(client, stats, args.feed_limit)
    await hold_socket(args.ws, stats, until)


async def vu_hold(args, stats: Stats, delay: float, until: float) -> None:
    await asyncio.sleep(delay)
    await hold_socket(args.ws, stats, until)


async def vu_storm(args, stats: Stats, delay: float, drop_at: float, until: float, vu: int) -> None:
    await asyncio.sleep(delay)
    await hold_socket(args.ws, stats, drop_at, vu)
    await asyncio.sleep(1.0 + random.uniform(0, 0.05))
    async with new_client(args.base) as client:
        if args.storm_mode == "hydrate":
            await boot(client, stats, args.feed_limit)
        else:
            await resume(client, stats, vu, args.storm_mode, args.feed_limit)
    await hold_socket(args.ws, stats, until, vu)


async def sample_server(pid: int, stats: Stats, stop: asyncio.Event) -> None:
    t0 = time.monotonic()
    while not stop.is_set():
        try:
            out = subprocess.run(
                ["ps", "-o", "rss=,%cpu=", "-p", str(pid)], capture_output=True, text=True
            ).stdout.split()
            stats.server_samples.append((time.monotonic() - t0, int(out[0]) / 1024, float(out[1])))
        except (IndexError, ValueError):
            pass
        await asyncio.sleep(1.0)


async def run(args) -> dict:
    stats = Stats()
    random.seed(1)
    delays = [random.uniform(0, args.ramp) for _ in range(args.users)]
    start = time.monotonic()
    stop = asyncio.Event()
    sampler = asyncio.create_task(sample_server(args.server_pid, stats, stop)) if args.server_pid else None

    if args.scenario == "boot":
        until = start + args.ramp + args.hold
        tasks = [vu_boot(args, stats, d, until) for d in delays]
    elif args.scenario == "hold":
        until = start + args.ramp + args.hold
        tasks = [vu_hold(args, stats, d, until) for d in delays]
    else:
        drop_at = start + args.ramp + 5
        until = drop_at + 1 + args.hold
        tasks = [vu_storm(args, stats, d, drop_at, until, i) for i, d in enumerate(delays)]

    await asyncio.gather(*tasks)
    wall = time.monotonic() - start
    stop.set()
    if sampler:
        await sampler
    return report(args, stats, wall)


def report(args, stats: Stats, wall: float) -> dict:
    total_requests = sum(len(v) for v in stats.latency_ms.values())
    rows = []
    for key in sorted(stats.latency_ms):
        lat = stats.latency_ms[key]
        codes = dict(stats.status[key])
        non_ok = sum(n for c, n in codes.items() if c != 200)
        rows.append(
            {
                "endpoint": key,
                "n": len(lat),
                "p50": round(pct(lat, 50), 1),
                "p95": round(pct(lat, 95), 1),
                "p99": round(pct(lat, 99), 1),
                "max": round(max(lat), 1),
                "non200": non_ok,
            }
        )
    spreads = [
        (max(t) - min(t)) * 1000 for t in stats.frame_arrivals.values() if len(t) >= 2
    ]
    result = {
        "scenario": args.scenario,
        "users": args.users,
        "ramp_s": args.ramp,
        "hold_s": args.hold,
        "wall_s": round(wall, 1),
        "requests": total_requests,
        "rps_during_ramp": round(total_requests / max(args.ramp, 1), 1),
        "errors": dict(stats.errors),
        "sync_status": dict(stats.sync_status),
        "boot_ms": {
            "p50": round(pct(stats.boot_ms, 50), 1),
            "p95": round(pct(stats.boot_ms, 95), 1),
            "max": round(max(stats.boot_ms), 1) if stats.boot_ms else None,
        },
        "ws": {
            "connected": len(stats.ws_connect_ms),
            "failed": stats.ws_failed,
            "dropped": stats.ws_dropped,
            "connect_p95_ms": round(pct(stats.ws_connect_ms, 95), 1),
            "frames_received": stats.frames_received,
            "distinct_frames": len(stats.frame_arrivals),
            "fanout_spread_p50_ms": round(pct(spreads, 50), 1) if spreads else None,
            "fanout_spread_p95_ms": round(pct(spreads, 95), 1) if spreads else None,
            "fanout_spread_max_ms": round(max(spreads), 1) if spreads else None,
            "ping_latency_p95_ms": round(pct(stats.ping_latency_ms, 95), 1)
            if stats.ping_latency_ms
            else None,
        },
        "endpoints": rows,
    }
    if stats.server_samples:
        result["server"] = {
            "rss_mb_start": round(stats.server_samples[0][1], 1),
            "rss_mb_peak": round(max(s[1] for s in stats.server_samples), 1),
            "cpu_pct_peak": max(s[2] for s in stats.server_samples),
            "cpu_pct_mean": round(statistics.fmean(s[2] for s in stats.server_samples), 1),
        }
    return result


def print_report(r: dict) -> None:
    print(
        f"\n{r['scenario']}  users={r['users']}  ramp={r['ramp_s']}s  hold={r['hold_s']}s  "
        f"wall={r['wall_s']}s  requests={r['requests']}  (~{r['rps_during_ramp']} rps during ramp)"
    )
    print(f"{'endpoint':32} {'n':>6} {'p50':>8} {'p95':>8} {'p99':>8} {'max':>8} {'!200':>5}")
    for row in r["endpoints"]:
        print(
            f"{row['endpoint']:32} {row['n']:>6} {row['p50']:>8} {row['p95']:>8} "
            f"{row['p99']:>8} {row['max']:>8} {row['non200']:>5}"
        )
    print(f"boot p50={r['boot_ms']['p50']}ms p95={r['boot_ms']['p95']}ms max={r['boot_ms']['max']}ms")
    if r.get("sync_status"):
        print("sync answers:", r["sync_status"])
    ws = r["ws"]
    print(
        f"ws connected={ws['connected']} failed={ws['failed']} dropped={ws['dropped']} "
        f"connect_p95={ws['connect_p95_ms']}ms frames={ws['frames_received']} "
        f"distinct={ws['distinct_frames']}"
    )
    print(
        f"fan-out spread p50={ws['fanout_spread_p50_ms']}ms p95={ws['fanout_spread_p95_ms']}ms "
        f"max={ws['fanout_spread_max_ms']}ms  ping latency p95={ws['ping_latency_p95_ms']}ms"
    )
    if r.get("errors"):
        print("errors:", r["errors"])
    if "server" in r:
        s = r["server"]
        print(
            f"server rss {s['rss_mb_start']}MB -> peak {s['rss_mb_peak']}MB, "
            f"cpu peak {s['cpu_pct_peak']}% mean {s['cpu_pct_mean']}%"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8199")
    ap.add_argument("--ws", default="ws://127.0.0.1:8199/ws/threats")
    ap.add_argument("--scenario", choices=["boot", "storm", "hold"], default="boot")
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--ramp", type=float, default=10.0, help="seconds over which VUs arrive")
    ap.add_argument("--hold", type=float, default=30.0, help="seconds each VU keeps its socket")
    ap.add_argument("--feed-limit", type=int, default=60, choices=[30, 60, 120, 250])
    ap.add_argument("--storm-mode", choices=["hydrate", "delta", "full"], default="delta")
    ap.add_argument("--server-pid", type=int, default=None, help="sample RSS/CPU of this local pid")
    ap.add_argument("--out", default=None, help="write the JSON report here")
    args = ap.parse_args()

    result = asyncio.run(run(args))
    result["at"] = datetime.now(UTC).isoformat(timespec="seconds")
    print_report(result)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print(f"written {args.out}")
    if result["ws"]["failed"] or any(row["non200"] for row in result["endpoints"]) or result["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
