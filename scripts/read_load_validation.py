"""Bounded local Web API GET concurrency measurement, never a model/system QPS claim."""

import argparse
import asyncio
import hashlib
import json
import math
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from urllib.parse import urlparse

import httpx


def save(path, report):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def nearest_rank(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


async def _measure_level(client, paths, concurrency, request_count, minimum_seconds, max_requests):
    results, next_index = [], 0
    wall_start, monotonic_start = time.time(), monotonic()

    async def worker():
        nonlocal next_index
        while next_index < max_requests:
            if next_index >= request_count and monotonic() - monotonic_start >= minimum_seconds:
                return
            index = next_index
            next_index += 1
            path = paths[index % len(paths)]
            start, wall = monotonic(), time.time()
            row = {"sequence": index + 1, "path": path}
            try:
                response = await client.get(path, timeout=10)
                row["status"] = response.status_code
            except httpx.HTTPError as error:
                row["error_type"] = type(error).__name__
            elapsed = monotonic() - start
            row.update(
                elapsed_seconds=elapsed,
                monotonic_elapsed_seconds=elapsed,
                wall_elapsed_seconds=time.time() - wall,
            )
            results.append(row)

    await asyncio.gather(*(worker() for _ in range(concurrency)))
    elapsed = monotonic() - monotonic_start
    results.sort(key=lambda row: row["sequence"])
    latencies = [row["elapsed_seconds"] for row in results]
    satisfied = len(results) >= request_count and elapsed >= minimum_seconds
    return {
        "concurrency": concurrency,
        "request_count": len(results),
        "minimum_request_count": request_count,
        "minimum_seconds": minimum_seconds,
        "maximum_request_count": max_requests,
        "window_satisfied": satisfied,
        "maximum_requests_reached": len(results) >= max_requests,
        "safety_cap_triggered": len(results) >= max_requests and not satisfied,
        "http_status_counts": dict(Counter(str(r["status"]) for r in results if "status" in r)),
        "transport_error_counts": dict(
            Counter(r["error_type"] for r in results if "error_type" in r)
        ),
        "path_request_counts": dict(Counter(r["path"] for r in results)),
        "wall_elapsed_seconds": round(time.time() - wall_start, 6),
        "monotonic_elapsed_seconds": round(elapsed, 6),
        "p50_seconds": nearest_rank(latencies, 0.50),
        "p95_seconds": nearest_rank(latencies, 0.95),
        "completed_requests_per_second": len(results) / elapsed if elapsed else None,
        "successful_2xx_requests": sum(200 <= r.get("status", 0) < 300 for r in results),
        "requests": results,
    }


async def measure_reads(
    client, paths, levels=(1, 4, 8), request_count=96, minimum_seconds=0, max_requests=20_000
):
    """Measure bounded GETs only; the caller owns auth and model-idleness verification."""
    if (
        not paths
        or not levels
        or request_count <= 0
        or any(level <= 0 for level in levels)
        or not math.isfinite(minimum_seconds)
        or minimum_seconds < 0
        or max_requests < request_count
        or max_requests > 20_000
    ):
        raise ValueError(
            "Nonempty paths, finite nonnegative duration and bounded positive counts required"
        )
    if any(not path.startswith("/api/") or "?" in path for path in paths):
        raise ValueError("Only explicit local business API paths are accepted")
    report = {
        "scope": "local read-only Web API window; no model/system capacity conclusion",
        "started_at": datetime.now(UTC).isoformat(),
        "request_timeout_seconds": 10,
        "percentile_method": "nearest rank: sorted[ceil(p*n)-1], p=0.50/0.95",
        "latency_population": "all completed attempts, including HTTP/transport errors",
        "latency_timing": "worker admission to response/error; unissued client work excluded",
        "load_pattern": "fixed workers issue GETs until both minimum targets or the safety cap",
        "minimum_seconds": minimum_seconds,
        "maximum_requests_per_level": max_requests,
        "paths": paths,
        "warmup": [],
        "runs": [],
    }
    for path in paths:
        try:
            response = await client.get(path, timeout=10)
            report["warmup"].append({"path": path, "status": response.status_code})
        except httpx.HTTPError as error:
            report["warmup"].append({"path": path, "error_type": type(error).__name__})
    for concurrency in levels:
        report["runs"].append(
            await _measure_level(
                client, paths, concurrency, request_count, minimum_seconds, max_requests
            )
        )
    report["all_windows_satisfied"] = all(run["window_satisfied"] for run in report["runs"])
    report["finished_at"] = datetime.now(UTC).isoformat()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--space-id", required=True)
    parser.add_argument("--answer-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-seconds", type=float, default=0)
    args = parser.parse_args()
    if not math.isfinite(args.minimum_seconds) or args.minimum_seconds < 0:
        raise SystemExit("minimum-seconds must be finite and nonnegative")
    endpoint = urlparse(args.base_url)
    if (
        endpoint.scheme != "http"
        or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
        or endpoint.path not in {"", "/"}
    ):
        raise SystemExit("A credential-free local HTTP origin is required")
    if any(not re.fullmatch(r"[a-f0-9]{32}", value) for value in [args.space_id, args.answer_id]):
        raise SystemExit("Use the isolated synthetic space and answer identities")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x"):
        pass
    token = args.token_file.read_text().strip()

    async def execute():
        async with httpx.AsyncClient(
            base_url=args.base_url,
            trust_env=False,
            timeout=10,
            headers={"Authorization": "Bearer " + token},
        ) as client:
            return await measure_reads(
                client,
                [
                    "/api/health",
                    "/api/spaces",
                    f"/api/spaces/{args.space_id}/messages",
                    f"/api/answers/{args.answer_id}",
                ],
                minimum_seconds=args.minimum_seconds,
            )

    report = asyncio.run(execute())
    report["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report["caller_asserted_model_idle"] = False
    save(args.output, report)
    print(
        json.dumps(
            {
                "runs": len(report["runs"]),
                "measured_requests": sum(r["request_count"] for r in report["runs"]),
            }
        )
    )


if __name__ == "__main__":
    main()
