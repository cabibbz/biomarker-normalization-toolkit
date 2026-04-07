# Dual Agent Consensus

Use this workflow when you want Codex and Claude to reason from the same files, bounce one proposal back and forth, and only run implementation or deployment hooks after consensus.

## What It Does

- freezes a shared task and shared context files into one run directory
- alternates two agents in a strict proposal and review loop
- treats consensus as one agent accepting the other agent's current proposal
- can run implementation, verification, and deployment hooks only after consensus
- records prompts, responses, logs, the adopted proposal, and the final result in one place

## Config Contract

Run:

```powershell
python .\operating_system\tools\dual_agent_consensus.py .\operating_system\examples\dual_agent_consensus_config.json
```

Expected config fields:

- `workspace`: working directory for agent and hook commands
- `run_dir`: optional output directory for the run; defaults under `.agent_consensus/`
- `task_text` or `task_file`: required shared task
- `context_files`: optional list of files to snapshot for both agents
- `max_rounds`: maximum alternating rounds before failure
- `agents`: exactly two agents, each with:
  - `name`
  - `command`: a command array with placeholders
- `execution`: optional hook commands for:
  - `implementation_command`
  - `verification_command`
  - `deploy_command`

Supported command placeholders:

- `{workspace}`
- `{run_dir}`
- `{task_file}`
- `{context_index_file}`
- `{proposal_file}`
- `{prompt_file}`
- `{response_file}`
- `{agent_name}`
- `{round}`

Relative path resolution:

- `workspace` resolves from the repo root
- `task_file` and `context_files` resolve from the workspace first, then the config file directory, then the repo root

## Agent Wrapper Contract

The orchestrator is vendor-agnostic. It does not call Claude or Codex APIs directly. Instead, each configured command should point to a local wrapper you control.

Each wrapper should:

1. read the prompt file
2. read any shared files it needs, especially the proposal and context snapshots
3. return valid JSON either by writing `{response_file}` or printing to stdout

Response schema:

```json
{
  "action": "propose",
  "summary": "short summary",
  "concerns": [],
  "proposal_markdown": "# Proposal\n\nFull replacement proposal text."
}
```

Valid `action` values:

- `propose`: create the first proposal
- `revise`: replace the current proposal with a better full proposal
- `accept`: accept the current proposal unchanged
- `block`: stop the run with concrete concerns

## Agreement Rule

Consensus is reached when the reviewing agent returns `accept` for the current proposal. That means:

- one agent authored the current proposal
- the other agent reviewed it and accepted it unchanged

Only after that will the orchestrator run implementation, verification, and deployment hooks.

## Run Artifacts

Each run writes:

- `task.md`
- `context_index.md`
- `context/` snapshots
- `proposal.md`
- `prompts/`
- `responses/`
- `logs/`
- `hooks/`
- `transcript.md`
- `result.json`

## Practical Setup

Use this with thin local wrappers around each model CLI. Keep the wrappers small and deterministic: they should translate the prompt file into one JSON response, not try to manage the whole loop themselves.
