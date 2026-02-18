#!/usr/bin/env python3
"""
PoC for unresolved item #8:
Realtime scanning timing: "scan immediately on FS event" vs "enqueue + resource governor".

We can't reproduce Windows ReadDirectoryChangesW here, so we model the scheduling problem:
- Events arrive over time (bursty).
- Each scan costs fixed CPU time per file (scan_cost_ms).

Two policies (single worker for clarity):
1) immediate: scan as soon as the event arrives (can drive CPU to 100% and build backlog on bursts)
2) queued_with_budget: scan with a target CPU duty cycle f (e.g., 0.1 means ~10% CPU of one core)

Output: latency distribution (time from event arrival to scan completion) and realized CPU fraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    k = int(round((len(xs) - 1) * p))
    return xs[max(0, min(k, len(xs) - 1))]


@dataclass(frozen=True)
class SimResult:
    total_wall_s: float
    cpu_fraction: float
    p50_latency_s: float
    p95_latency_s: float
    max_latency_s: float


def simulate_immediate(events_s: Iterable[float], scan_cost_ms: float) -> SimResult:
    events = list(events_s)
    if not events:
        return SimResult(0.0, 0.0, 0.0, 0.0, 0.0)

    t = 0.0
    latencies: list[float] = []
    scan_cost_s = scan_cost_ms / 1000.0

    for a in events:
        start = max(a, t)
        end = start + scan_cost_s
        latencies.append(end - a)
        t = end

    total_wall = t - events[0]
    total_cpu = len(events) * scan_cost_s
    cpu_frac = (total_cpu / total_wall) if total_wall > 0 else 0.0

    return SimResult(
        total_wall_s=total_wall,
        cpu_fraction=cpu_frac,
        p50_latency_s=pct(latencies, 0.50),
        p95_latency_s=pct(latencies, 0.95),
        max_latency_s=max(latencies) if latencies else 0.0,
    )


def simulate_queued_with_budget(events_s: Iterable[float], scan_cost_ms: float, cpu_fraction_target: float) -> SimResult:
    if cpu_fraction_target <= 0 or cpu_fraction_target > 1:
        raise ValueError("cpu_fraction_target must be in (0, 1]")

    events = list(events_s)
    if not events:
        return SimResult(0.0, 0.0, 0.0, 0.0, 0.0)

    t = 0.0
    latencies: list[float] = []
    scan_cost_s = scan_cost_ms / 1000.0

    # Duty-cycle model: to spend scan_cost_s CPU, wall time becomes scan_cost_s / f.
    wall_per_scan = scan_cost_s / cpu_fraction_target

    for a in events:
        start = max(a, t)
        end = start + wall_per_scan
        latencies.append(end - a)
        t = end

    total_wall = t - events[0]
    total_cpu = len(events) * scan_cost_s
    cpu_frac = (total_cpu / total_wall) if total_wall > 0 else 0.0

    return SimResult(
        total_wall_s=total_wall,
        cpu_fraction=cpu_frac,
        p50_latency_s=pct(latencies, 0.50),
        p95_latency_s=pct(latencies, 0.95),
        max_latency_s=max(latencies) if latencies else 0.0,
    )


def simulate_active_then_idle(
    events_s: Iterable[float],
    scan_cost_ms: float,
    active_cpu_fraction: float,
    idle_cpu_fraction: float,
    idle_after_s: float,
) -> SimResult:
    """
    Simple dynamic governor model:
    - before idle_after_s: throttle at active_cpu_fraction (user active)
    - after  idle_after_s: allow idle_cpu_fraction (user idle / off-hours)
    """
    if not (0 < active_cpu_fraction <= 1 and 0 < idle_cpu_fraction <= 1):
        raise ValueError("cpu fractions must be in (0, 1]")

    events = list(events_s)
    if not events:
        return SimResult(0.0, 0.0, 0.0, 0.0, 0.0)

    t = 0.0
    latencies: list[float] = []
    scan_cost_s = scan_cost_ms / 1000.0

    for a in events:
        start = max(a, t)
        f = active_cpu_fraction if start < idle_after_s else idle_cpu_fraction
        end = start + (scan_cost_s / f)
        latencies.append(end - a)
        t = end

    total_wall = t - events[0]
    total_cpu = len(events) * scan_cost_s
    cpu_frac = (total_cpu / total_wall) if total_wall > 0 else 0.0

    return SimResult(
        total_wall_s=total_wall,
        cpu_fraction=cpu_frac,
        p50_latency_s=pct(latencies, 0.50),
        p95_latency_s=pct(latencies, 0.95),
        max_latency_s=max(latencies) if latencies else 0.0,
    )


def gen_burst(rate_per_s: float, duration_s: float, start_s: float = 0.0) -> list[float]:
    if rate_per_s <= 0 or duration_s <= 0:
        return []
    step = 1.0 / rate_per_s
    n = int(duration_s * rate_per_s)
    return [start_s + i * step for i in range(n)]


def show(title: str, r: SimResult) -> None:
    print(title)
    print(f"  total_wall_s={r.total_wall_s:.3f}")
    print(f"  cpu_fraction={r.cpu_fraction:.3f}")
    print(f"  p50_latency_s={r.p50_latency_s:.3f}")
    print(f"  p95_latency_s={r.p95_latency_s:.3f}")
    print(f"  max_latency_s={r.max_latency_s:.3f}")


def main() -> None:
    # Scenario: bursty FS events (e.g., unzip/build/git checkout).
    # - 200 events/s for 2 seconds (400 events)
    # - then 10 events/s for 8 seconds (80 events)
    events = []
    events += gen_burst(rate_per_s=200.0, duration_s=2.0, start_s=0.0)
    events += gen_burst(rate_per_s=10.0, duration_s=8.0, start_s=2.0)

    scan_cost_ms = 15.0  # CPU per file for "light" scanning stage (regex/validators only)
    print(f"events={len(events)} scan_cost_ms={scan_cost_ms}")
    print()

    r_immediate = simulate_immediate(events, scan_cost_ms=scan_cost_ms)
    show("immediate (scan right away)", r_immediate)
    print()

    for f in (0.10, 0.20, 0.30):
        r = simulate_queued_with_budget(events, scan_cost_ms=scan_cost_ms, cpu_fraction_target=f)
        show(f"queued_with_budget(f={f:.2f})", r)
        print()

    # More realistic: throttle during "active" window, then drain backlog faster when idle.
    idle_after_s = max(events)  # switch after last event arrival
    r_dyn = simulate_active_then_idle(
        events,
        scan_cost_ms=scan_cost_ms,
        active_cpu_fraction=0.10,
        idle_cpu_fraction=0.50,
        idle_after_s=idle_after_s,
    )
    show(f"active_then_idle(active=0.10 idle=0.50 after_t={idle_after_s:.3f})", r_dyn)


if __name__ == "__main__":
    main()
