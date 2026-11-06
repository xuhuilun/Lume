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


async def measure_reads(client, paths, levels=(1, 4, 8), request_count=96):
    """Measure bounded GETs only; the caller owns auth and model-idleness verification."""
    if not paths or request_count <= 0 or any(level <= 0 for level in levels):
        raise ValueError("Nonempty paths and positive bounded counts required")
    if any(not path.startswith("/api/") or "?" in path for path in paths):
        raise ValueError("Only explicit local business API paths are accepted")
    report = {
        "scope": "local read-only Web API window; no model/system capacity conclusion",
        "started_at": datetime.now(UTC).isoformat(),
        "request_timeout_seconds": 10,
        "percentile_method": "nearest rank: sorted[ceil(p*n)-1], p=0.50/0.95",
        "latency_population": "all completed attempts, including HTTP/transport errors",
        "latency_timing": "semaphore admission to response/error; client queue excluded",
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
        semaphore = asyncio.Semaphore(concurrency)

        async def one(index, gate=semaphore):
            async with gate:
                start = time.monotonic()
                path = paths[index % len(paths)]
                row = {"path": path}
                try:
                    response = await client.get(path, timeout=10)
                    row["status"] = response.status_code
                except httpx.HTTPError as error:
                    row["error_type"] = type(error).__name__
                row["elapsed_seconds"] = time.monotonic() - start
                return row

        wall_start, monotonic_start = time.time(), time.monotonic()
        results = await asyncio.gather(*(one(i) for i in range(request_count)))
        elapsed = time.monotonic() - monotonic_start
        latencies = [row["elapsed_seconds"] for row in results]
        report["runs"].append(
            {
                "concurrency": concurrency,
                "request_count": request_count,
                "http_status_counts": dict(
                    Counter(str(r["status"]) for r in results if "status" in r)
                ),
                "transport_error_counts": dict(
                    Counter(r["error_type"] for r in results if "error_type" in r)
                ),
                "path_request_counts": dict(Counter(r["path"] for r in results)),
                "wall_elapsed_seconds": round(time.time() - wall_start, 6),
                "monotonic_elapsed_seconds": round(elapsed, 6),
                "p50_seconds": nearest_rank(latencies, 0.50),
                "p95_seconds": nearest_rank(latencies, 0.95),
                "completed_requests_per_second": request_count / elapsed if elapsed else None,
                "successful_2xx_requests": sum(200 <= r.get("status", 0) < 300 for r in results),
                "requests": results,
            }
        )
    report["finished_at"] = datetime.now(UTC).isoformat()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--space-id", required=True)
    parser.add_argument("--answer-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
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
            )

    report = asyncio.run(execute())
    report["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report["caller_asserted_model_idle"] = False
    save(args.output, report)
    print(json.dumps({"runs": len(report["runs"]), "measured_requests": 288}))


if __name__ == "__main__":
    main()
