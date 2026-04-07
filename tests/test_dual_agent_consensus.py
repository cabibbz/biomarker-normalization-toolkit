from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "operating_system" / "tools" / "dual_agent_consensus.py"


class DualAgentConsensusTests(unittest.TestCase):
    def test_reaches_consensus_and_runs_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            agent_script = temp / "fake_agent.py"
            hook_script = temp / "write_hook.py"
            task_file = temp / "task.md"
            context_file = temp / "context.md"
            config_file = temp / "config.json"
            run_dir = temp / "run"

            agent_script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys
                    from pathlib import Path

                    prompt_file = Path(sys.argv[1])
                    response_file = Path(sys.argv[2])
                    proposal_file = Path(sys.argv[3])
                    agent_name = sys.argv[4]

                    if agent_name == "codex" and not proposal_file.exists():
                        payload = {
                            "action": "propose",
                            "summary": "Initial proposal",
                            "concerns": [],
                            "proposal_markdown": "# Plan\\n\\nUse the shared strategy."
                        }
                    elif agent_name == "claude" and proposal_file.exists():
                        payload = {
                            "action": "accept",
                            "summary": "Proposal is good enough",
                            "concerns": []
                        }
                    else:
                        payload = {
                            "action": "block",
                            "summary": "Unexpected state",
                            "concerns": ["test setup failure"]
                        }

                    response_file.write_text(json.dumps(payload), encoding="utf-8")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            hook_script.write_text(
                textwrap.dedent(
                    """
                    import sys
                    from pathlib import Path

                    target = Path(sys.argv[1])
                    target.write_text("ran\\n", encoding="utf-8")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            task_file.write_text("Reach agreement before execution.\n", encoding="utf-8")
            context_file.write_text("Shared file context.\n", encoding="utf-8")

            config = {
                "workspace": str(temp),
                "run_dir": str(run_dir),
                "task_file": str(task_file),
                "context_files": [str(context_file)],
                "max_rounds": 4,
                "agents": [
                    {
                        "name": "codex",
                        "command": [
                            sys.executable,
                            str(agent_script),
                            "{prompt_file}",
                            "{response_file}",
                            "{proposal_file}",
                            "codex",
                        ],
                    },
                    {
                        "name": "claude",
                        "command": [
                            sys.executable,
                            str(agent_script),
                            "{prompt_file}",
                            "{response_file}",
                            "{proposal_file}",
                            "claude",
                        ],
                    },
                ],
                "execution": {
                    "implementation_command": [sys.executable, str(hook_script), str(temp / "implemented.txt")],
                    "verification_command": [sys.executable, str(hook_script), str(temp / "verified.txt")],
                    "deploy_command": [sys.executable, str(hook_script), str(temp / "deployed.txt")],
                },
            }
            config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(config_file)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("Consensus reached in 2 rounds", result.stdout)
            self.assertTrue((temp / "implemented.txt").exists())
            self.assertTrue((temp / "verified.txt").exists())
            self.assertTrue((temp / "deployed.txt").exists())

            payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "consensus_reached")
            self.assertEqual(payload["accepted_by"], "claude")
            self.assertEqual(payload["proposed_by"], "codex")

    def test_stops_without_consensus(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            agent_script = temp / "no_consensus_agent.py"
            task_file = temp / "task.md"
            config_file = temp / "config.json"
            run_dir = temp / "run"

            agent_script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys
                    from pathlib import Path

                    response_file = Path(sys.argv[2])
                    proposal_file = Path(sys.argv[3])
                    agent_name = sys.argv[4]

                    proposal = f"# Proposal from {agent_name}\\n"
                    if proposal_file.exists():
                        proposal += proposal_file.read_text(encoding="utf-8")

                    payload = {
                        "action": "revise" if proposal_file.exists() else "propose",
                        "summary": f"{agent_name} wants another revision",
                        "concerns": ["not done yet"],
                        "proposal_markdown": proposal,
                    }
                    response_file.write_text(json.dumps(payload), encoding="utf-8")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            task_file.write_text("Keep revising forever.\n", encoding="utf-8")
            config = {
                "workspace": str(temp),
                "run_dir": str(run_dir),
                "task_file": str(task_file),
                "max_rounds": 3,
                "agents": [
                    {
                        "name": "codex",
                        "command": [
                            sys.executable,
                            str(agent_script),
                            "{prompt_file}",
                            "{response_file}",
                            "{proposal_file}",
                            "codex",
                        ],
                    },
                    {
                        "name": "claude",
                        "command": [
                            sys.executable,
                            str(agent_script),
                            "{prompt_file}",
                            "{response_file}",
                            "{proposal_file}",
                            "claude",
                        ],
                    },
                ],
            }
            config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(config_file)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No consensus after 3 rounds", result.stdout)
            payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "no_consensus")

    def test_normalizes_accept_with_proposal_into_first_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            agent_script = temp / "normalize_agent.py"
            task_file = temp / "task.md"
            config_file = temp / "config.json"
            run_dir = temp / "run"

            agent_script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys
                    from pathlib import Path

                    response_file = Path(sys.argv[2])
                    agent_name = sys.argv[4]

                    if agent_name == "codex":
                        payload = {
                            "action": "accept",
                            "summary": "Premature accept with proposal text",
                            "concerns": [],
                            "proposal_markdown": "# Smoke\\n\\n- First actual proposal."
                        }
                    else:
                        payload = {
                            "action": "accept",
                            "summary": "Second agent accepts the proposal",
                            "concerns": [],
                            "proposal_markdown": ""
                        }

                    response_file.write_text(json.dumps(payload), encoding="utf-8")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            task_file.write_text("Normalize sloppy first-agent behavior.\n", encoding="utf-8")
            config = {
                "workspace": str(temp),
                "run_dir": str(run_dir),
                "task_file": str(task_file),
                "max_rounds": 3,
                "agents": [
                    {
                        "name": "codex",
                        "command": [
                            sys.executable,
                            str(agent_script),
                            "{prompt_file}",
                            "{response_file}",
                            "{proposal_file}",
                            "codex",
                        ],
                    },
                    {
                        "name": "claude",
                        "command": [
                            sys.executable,
                            str(agent_script),
                            "{prompt_file}",
                            "{response_file}",
                            "{proposal_file}",
                            "claude",
                        ],
                    },
                ],
            }
            config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(config_file)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "consensus_reached")
            self.assertEqual(payload["proposed_by"], "codex")
            transcript = (run_dir / "transcript.md").read_text(encoding="utf-8")
            self.assertIn("normalized `accept` to `propose`", transcript)


    def test_semantic_validation_blocks_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            agent_script = temp / "fake_agent.py"
            failing_validator = temp / "fail_validate.py"
            hook_script = temp / "write_hook.py"
            task_file = temp / "task.md"
            config_file = temp / "config.json"
            run_dir = temp / "run"

            agent_script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys
                    from pathlib import Path

                    prompt_file = Path(sys.argv[1])
                    response_file = Path(sys.argv[2])
                    proposal_file = Path(sys.argv[3])
                    agent_name = sys.argv[4]

                    if agent_name == "codex":
                        proposal_file.write_text("# Smoke\\n", encoding="utf-8")
                        resp = {"action": "propose", "summary": "initial", "concerns": [], "proposal_markdown": "# Smoke"}
                    else:
                        resp = {"action": "accept", "summary": "ok", "concerns": [], "proposal_markdown": ""}
                    response_file.write_text(json.dumps(resp), encoding="utf-8")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            failing_validator.write_text("import sys; sys.exit(1)\n", encoding="utf-8")
            hook_script.write_text(
                "import sys; from pathlib import Path; Path(sys.argv[1]).write_text('ran\\n')\n",
                encoding="utf-8",
            )

            task_file.write_text("Test semantic validation.\n", encoding="utf-8")

            config = {
                "workspace": str(temp),
                "run_dir": str(run_dir),
                "task_file": str(task_file),
                "context_files": [],
                "max_rounds": 4,
                "agents": [
                    {"name": "codex", "command": [sys.executable, str(agent_script), "{prompt_file}", "{response_file}", "{proposal_file}", "codex"]},
                    {"name": "claude", "command": [sys.executable, str(agent_script), "{prompt_file}", "{response_file}", "{proposal_file}", "claude"]},
                ],
                "execution": {
                    "semantic_validation_command": [sys.executable, str(failing_validator)],
                    "implementation_command": [sys.executable, str(hook_script), str(temp / "implemented.txt")],
                },
            }
            config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(config_file)],
                capture_output=True, text=True, check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("semantic validation failed", result.stdout)
            # Implementation hook must NOT have run
            self.assertFalse((temp / "implemented.txt").exists())

            payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "semantic_validation_failed")


if __name__ == "__main__":
    unittest.main()
