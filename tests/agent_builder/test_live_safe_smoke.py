import subprocess
import sys


def test_live_safe_smoke_requires_explicit_env_gate(monkeypatch):
    monkeypatch.delenv("AGENT_BUILDER_LIVE_SAFE", raising=False)
    completed = subprocess.run(
        [sys.executable, "-m", "agent_builder.api.live_safe_smoke"],
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 2
    assert "AGENT_BUILDER_LIVE_SAFE=1" in completed.stderr
