from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "operating_system" / "tools" / "run_live_consensus_smoke_test.py"


class LiveConsensusSmokeTestScriptTests(unittest.TestCase):
    def test_writes_config_and_invokes_orchestrator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            workspace.mkdir()

            fake_orchestrator = temp / "fake_orchestrator.py"
            capture_path = temp / "captured_config.json"
            fake_orchestrator.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys
                    from pathlib import Path

                    config_path = Path(sys.argv[1])
                    payload = json.loads(config_path.read_text(encoding="utf-8"))
                    capture = Path(sys.argv[2])
                    rows = []
                    if capture.exists():
                        rows = json.loads(capture.read_text(encoding="utf-8"))
                    rows.append(payload)
                    capture.write_text(json.dumps(rows, indent=2), encoding="utf-8")
                    print("Consensus reached in 2 rounds")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--workspace",
                    str(workspace),
                    "--run-dir",
                    str(workspace / ".agent_consensus" / "live_smoke_test"),
                    "--codex-model",
                    "gpt-5.4-mini",
                    "--claude-model",
                    "sonnet",
                    "--claude-effort",
                    "low",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={
                    **os.environ,
                    "LIVE_CONSENSUS_ORCHESTRATOR": f"{sys.executable}|{fake_orchestrator}|{{config_path}}|{capture_path}",
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("Attempt 1/3", result.stdout)
            self.assertIn("Consensus reached in 2 rounds", result.stdout)

            payload = json.loads(capture_path.read_text(encoding="utf-8"))[0]
            self.assertEqual(payload["max_rounds"], 4)
            self.assertEqual(payload["agents"][0]["name"], "codex")
            self.assertIn("--model", payload["agents"][0]["command"])
            self.assertIn("gpt-5.4-mini", payload["agents"][0]["command"])
            self.assertIn("--max-budget-usd", payload["agents"][1]["command"])

    def test_retries_until_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            workspace.mkdir()

            fake_orchestrator = temp / "retry_orchestrator.py"
            capture_path = temp / "attempts.json"
            fake_orchestrator.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys
                    from pathlib import Path

                    config_path = Path(sys.argv[1])
                    capture = Path(sys.argv[2])
                    rows = []
                    if capture.exists():
                        rows = json.loads(capture.read_text(encoding="utf-8"))
                    rows.append(config_path.parent.name)
                    capture.write_text(json.dumps(rows), encoding="utf-8")
                    if len(rows) < 2:
                        print("No consensus after 4 rounds")
                        raise SystemExit(1)
                    print("Consensus reached in 3 rounds")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--workspace",
                    str(workspace),
                    "--run-dir",
                    str(workspace / ".agent_consensus" / "retry_smoke"),
                    "--attempts",
                    "2",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={
                    **os.environ,
                    "LIVE_CONSENSUS_ORCHESTRATOR": f"{sys.executable}|{fake_orchestrator}|{{config_path}}|{capture_path}",
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("Attempt 1/2", result.stdout)
            self.assertIn("Attempt 2/2", result.stdout)
            self.assertIn("Consensus reached in 3 rounds", result.stdout)
            attempts = json.loads(capture_path.read_text(encoding="utf-8"))
            self.assertEqual(attempts, ["attempt_01", "attempt_02"])


if __name__ == "__main__":
    unittest.main()
