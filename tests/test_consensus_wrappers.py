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
CODEX_WRAPPER = ROOT / "operating_system" / "tools" / "codex_consensus_wrapper.py"
CLAUDE_WRAPPER = ROOT / "operating_system" / "tools" / "claude_consensus_wrapper.py"


class ConsensusWrapperTests(unittest.TestCase):
    def _make_run(self, temp: Path) -> tuple[Path, Path, Path, Path]:
        run_dir = temp / "run"
        context_dir = run_dir / "context"
        context_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "task.md").write_text("Decide the change.\n", encoding="utf-8")
        (run_dir / "context_index.md").write_text("Shared context index.\n", encoding="utf-8")
        (context_dir / "project_memory" / "current_context.md").parent.mkdir(parents=True, exist_ok=True)
        (context_dir / "project_memory" / "current_context.md").write_text("Frozen context.\n", encoding="utf-8")
        prompt_file = run_dir / "prompt.md"
        prompt_file.write_text("Review the shared task and context.\n", encoding="utf-8")
        proposal_file = run_dir / "proposal.md"
        proposal_file.write_text("# Existing Proposal\n\nKeep provenance intact.\n", encoding="utf-8")
        response_file = run_dir / "response.json"
        return run_dir, prompt_file, proposal_file, response_file

    def test_codex_wrapper_writes_validated_response(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            run_dir, prompt_file, proposal_file, response_file = self._make_run(temp)
            fake_codex = temp / "fake_codex.py"
            capture_path = temp / "codex_prompt.txt"

            fake_codex.write_text(
                textwrap.dedent(
                    """
                    import json
                    import os
                    import sys
                    from pathlib import Path

                    args = sys.argv[1:]
                    output_path = Path(args[args.index("-o") + 1])
                    prompt = args[-1]
                    capture = os.environ.get("CAPTURE_PROMPT_FILE")
                    if capture:
                        Path(capture).write_text(prompt, encoding="utf-8")
                    payload = {
                        "action": "propose",
                        "summary": "Codex proposal",
                        "concerns": [],
                        "proposal_markdown": "# Proposal\\n\\nShip the safer change."
                    }
                    output_path.write_text(json.dumps(payload), encoding="utf-8")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            env = dict(os.environ, CAPTURE_PROMPT_FILE=str(capture_path))
            result = subprocess.run(
                [
                    sys.executable,
                    str(CODEX_WRAPPER),
                    "--workspace",
                    str(temp),
                    "--run-dir",
                    str(run_dir),
                    "--prompt-file",
                    str(prompt_file),
                    "--proposal-file",
                    str(proposal_file),
                    "--response-file",
                    str(response_file),
                    "--binary",
                    sys.executable,
                    "--binary-arg",
                    str(fake_codex),
                ],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(response_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["action"], "propose")
            prompt = capture_path.read_text(encoding="utf-8")
            self.assertIn("Frozen context.", prompt)
            self.assertIn("Keep provenance intact.", prompt)

    def test_claude_wrapper_writes_validated_response(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            run_dir, prompt_file, proposal_file, response_file = self._make_run(temp)
            fake_claude = temp / "fake_claude.py"
            capture_path = temp / "claude_prompt.txt"

            fake_claude.write_text(
                textwrap.dedent(
                    """
                    import json
                    import os
                    import sys
                    from pathlib import Path

                    prompt = sys.argv[-1]
                    capture = os.environ.get("CAPTURE_PROMPT_FILE")
                    if capture:
                        Path(capture).write_text(prompt, encoding="utf-8")
                    payload = {
                        "action": "accept",
                        "summary": "Claude accepts",
                        "concerns": []
                    }
                    print(json.dumps({"result": json.dumps(payload)}))
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            env = dict(os.environ, CAPTURE_PROMPT_FILE=str(capture_path))
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLAUDE_WRAPPER),
                    "--workspace",
                    str(temp),
                    "--run-dir",
                    str(run_dir),
                    "--prompt-file",
                    str(prompt_file),
                    "--proposal-file",
                    str(proposal_file),
                    "--response-file",
                    str(response_file),
                    "--binary",
                    sys.executable,
                    "--binary-arg",
                    str(fake_claude),
                ],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(response_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["action"], "accept")
            prompt = capture_path.read_text(encoding="utf-8")
            self.assertIn("Shared context index.", prompt)
            self.assertIn("Existing Proposal", prompt)


if __name__ == "__main__":
    unittest.main()
