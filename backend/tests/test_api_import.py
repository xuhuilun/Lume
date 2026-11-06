import subprocess
import sys


def test_importing_api_does_not_construct_implicit_runtime_settings(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import lume.config

def forbidden(*args, **kwargs):
    raise RuntimeError("Implicit settings construction during import")

lume.config.Settings = forbidden
import lume.api
""",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
