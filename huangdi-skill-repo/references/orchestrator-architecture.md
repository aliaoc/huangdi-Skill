# Program-Level 皇帝skill Architecture

This file describes the runnable architecture implemented in `scripts/huangdi_orchestrator.py`.

## Components

- `UserEdict`: the 皇帝 command: goal, constraints, deliverables, acceptance criteria.
- `SkillRegistry`: scans local Codex skills and exposes their name, path, and description.
- `Plan`: the 中书省 output: task scale, required skills, assignments, verification plan.
- `AuditResult`: the 门下省 decision: approve, revise, or reject.
- `ExecutionResult`: the 尚书省 / execution agent output.
- `TaskQueue`: converts approved assignments into queued tasks with status, timestamps, errors, and artifacts.
- `EventLogger`: writes JSONL event logs and an HTML timeline for visual inspection.
- `LongTermMemory`: stores and recalls prior court runs in SQLite.
- `HuangdiOrchestrator`: state machine that controls plan, audit, execution, result audit, and final report.

## State Machine

```text
RECEIVE_TASK
→ DISCOVER_SKILLS
→ RECALL_MEMORY
→ ZHONGSHU_PLAN
→ MENXIA_AUDIT_PLAN
→ BUILD_TASK_QUEUE
→ SHANGSHU_EXECUTE_PARALLEL
→ MENXIA_AUDIT_RESULT
→ STORE_MEMORY
→ FINAL_REPORT
```

If `MENXIA_AUDIT_PLAN` rejects the plan, the orchestrator revises through 中书省 until the revision limit is reached.

## Backends

`rule` backend:
- Runs offline with deterministic heuristics.
- Useful for testing the court workflow without an external model.
- Does not perform real task execution; it prepares execution packets.

`command` backend:
- Sends each role packet to an external command via stdin.
- The command must return a JSON object on stdout.
- This is the adapter point for Codex CLI, OpenAI API wrappers, local models, or other LLM runners.

## Parallel Agents and Task Queue

Medium and large tasks are represented as `AgentAssignment` objects. After 门下省 approves the plan, `TaskQueue` assigns each one a stable task id such as `T001`, tracks `queued → running → completed/failed`, and preserves the original 中书省 order when returning results.

The executor uses `ThreadPoolExecutor` when `--max-workers` is greater than `1`. This enables parallel calls to the command backend, so multiple external agent/model invocations can run at the same time. The rule backend remains safe for dry runs because it only prepares execution packets.

## Visual Logs

By default, each run writes:

- `{run_id}.events.jsonl`: structured event stream for machines.
- `{run_id}.timeline.html`: readable visual timeline for humans.

Disable log writing by passing an empty log directory:

```powershell
python C:\Users\0\.codex\skills\huangdi-skill\scripts\huangdi_orchestrator.py "任务" --log-dir ""
```

## Long-Term Memory

`LongTermMemory` uses SQLite to store prior run ids, goals, task scales, selected skills, final reports, and audit outcomes. On later runs it recalls matching prior tasks by keyword and adds a concise memory context to the planning constraints.

The default memory path is:

```text
~\.codex\skills\huangdi-skill\memory\huangdi_memory.sqlite3
```

Disable memory with:

```powershell
python C:\Users\0\.codex\skills\huangdi-skill\scripts\huangdi_orchestrator.py "任务" --no-memory
```

## Basic Usage

```powershell
python C:\Users\0\.codex\skills\huangdi-skill\scripts\huangdi_orchestrator.py "用英文科学写作润色一个 docx" --explicit-multi-agent
```

Run with explicit parallelism, logs, and memory:

```powershell
python C:\Users\0\.codex\skills\huangdi-skill\scripts\huangdi_orchestrator.py "任务" --explicit-multi-agent --max-workers 4 --json-out court_record.json --prompts-out prompts.json
```

Write the full court record to JSON:

```powershell
python C:\Users\0\.codex\skills\huangdi-skill\scripts\huangdi_orchestrator.py "任务" --json-out court_record.json
```

Generate role prompts for manual or external model use:

```powershell
python C:\Users\0\.codex\skills\huangdi-skill\scripts\huangdi_orchestrator.py "任务" --prompts-out prompts.json
```

Use an external model command:

```powershell
python C:\Users\0\.codex\skills\huangdi-skill\scripts\huangdi_orchestrator.py "任务" --backend command --llm-command "python my_llm_adapter.py"
```

The external command receives a stable role id plus a payload. The `role` value is always one of `zhongshu`, `menxia_plan`, `executor`, or `menxia_result`; Chinese role names are carried in `payload.display_role`.

```json
{
  "role": "zhongshu",
  "payload": {
    "display_role": "中书省",
    "prompt": "...",
    "edict": {},
    "skills": []
  }
}
```

It must return the JSON schema requested in the prompt.

## Safety Model

- The state machine, not the LLM, decides whether the plan can proceed.
- 门下省 audit is a program gate.
- Skill loading is explicit: assignment skill names are resolved by `SkillRegistry`.
- Execution agents receive bounded assignments with allowed and forbidden scope.
- The `rule` backend is safe for tests because it does not modify external files.
