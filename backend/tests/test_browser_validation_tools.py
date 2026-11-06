import asyncio
import base64
import io
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from PIL import Image

from scripts.browser_validation import packets, private_write, sanitize
from scripts.read_load_validation import measure_reads, nearest_rank


def test_new_browser_fixture_is_self_contained_and_has_only_one_original_image():
    messages, digest = packets()
    images = [image for message in messages for image in message.get("images", [])]
    assert len(messages) == 4 and len(images) == 1 and len(digest) == 64
    assert all(message["source_id"].startswith("browser-") for message in messages)
    assert messages[2]["reply_to"] == messages[1]["source_id"]
    with Image.open(io.BytesIO(base64.b64decode(images[0]["base64"]))) as image:
        assert image.size == (760, 340)


def test_temporary_token_is_private_and_never_silently_overwritten(tmp_path):
    path = tmp_path / "access-token"
    private_write(path, "synthetic-only-token")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        private_write(path, "replacement")
    assert path.read_text() == "synthetic-only-token"


def test_browser_report_redaction_recurses_without_mutating_original():
    raw = {"error": ["fill secret-token at /tmp/private-runtime/file"], "count": 2}
    public = sanitize(raw, [("secret-token", "<redacted>"), ("/tmp/private-runtime", "<runtime>")])
    assert "secret-token" not in json.dumps(public)
    assert "/tmp/private-runtime" not in json.dumps(public)
    assert "secret-token" in raw["error"][0]
    assert public["count"] == 2


def test_percentiles_use_documented_nearest_rank_including_error_attempts():
    assert nearest_rank(list(range(1, 97)), 0.50) == 48
    assert nearest_rank(list(range(1, 97)), 0.95) == 92
    assert nearest_rank([], 0.95) is None


async def test_read_measurement_keeps_error_types_and_respects_concurrency_limit():
    active, maximum = 0, 0

    async def transport(request):
        nonlocal active, maximum
        assert request.method == "GET"
        active += 1
        maximum = max(maximum, active)
        try:
            await asyncio.sleep(0.002)
            if request.url.path == "/api/timeout":
                raise httpx.ReadTimeout("synthetic interruption")
            return httpx.Response(503 if request.url.path == "/api/unavailable" else 200)
        finally:
            active -= 1

    async with httpx.AsyncClient(
        base_url="http://local", transport=httpx.MockTransport(transport)
    ) as client:
        report = await measure_reads(
            client,
            ["/api/health", "/api/unavailable", "/api/timeout", "/api/spaces"],
            levels=(2,),
            request_count=8,
        )
    run = report["runs"][0]
    assert maximum == 2
    assert run["http_status_counts"] == {"200": 4, "503": 2}
    assert run["transport_error_counts"] == {"ReadTimeout": 2}
    assert run["request_count"] == len(run["requests"]) == 8
    assert run["successful_2xx_requests"] == 4
    assert run["p50_seconds"] <= run["p95_seconds"]
    assert len(report["warmup"]) == 4


async def test_read_measurement_refuses_paths_outside_explicit_api():
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="explicit local"):
            await measure_reads(client, ["https://example.com/api/tasks"])


def test_browser_entry_does_not_read_an_unrelated_dotenv_file(tmp_path):
    # A malformed synthetic URL makes an accidental default-app import observably fail.
    (tmp_path / ".env").write_text("LUME_DATABASE_URL=not-a-database-url\n")
    project = Path(__file__).resolve().parents[2]
    environment = {key: value for key, value in os.environ.items() if not key.startswith("LUME_")}
    environment["PYTHONPATH"] = str(project)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from scripts.browser_validation import private_write; print('safe-import')",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "safe-import"
