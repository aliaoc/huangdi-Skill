---
name: huangdi-skill
description: Multi-agent and multi-skill orchestration using a "皇帝 / 三省六部" governance model. Use when the user explicitly asks for 皇帝skill, 三省六部制协作, multi-agent planning, subagent delegation, agent supervision, dynamic execution agents, or coordinated use of multiple Codex skills for complex tasks.
---

# 皇帝skill

Use this skill to organize complex work through a disciplined "皇帝 / 三省六部" model. The user is the 皇帝: they issue the command and perform final acceptance. Codex operates the court system: 中书省 plans, 门下省 audits, 尚书省 executes, and execution agents perform bounded work.

## Runtime Role Note

The skill does not bundle permanent subagents. 中书省, 门下省, 尚书省, and execution agents are runtime roles created or simulated as needed. When the task justifies real delegation and the user has explicitly requested multi-agent work, spawn a 门下省 subagent for plan/result audit. For S0/S1 tasks, perform 门下省 as a local self-check instead of spawning.

## Non-Negotiable Contract

- Spawn subagents only when the user explicitly requests multi-agent, subagent, parallel-agent, agent collaboration, or 皇帝skill work.
- Do not spawn agents for small tasks. The imperial system must improve correctness or efficiency, not create ceremony.
- Keep one lead Codex responsible for final integration, file edits, synthesis, verification, and final answer.
- Treat subagent outputs as evidence, not authority. The lead resolves conflicts.
- Never let execution agents make policy decisions. 尚书省 executes the 中书-approved plan.
- 门下省 must review both the plan and the execution result before final delivery on non-tiny tasks.
- If a required skill or plugin is missing, ask the 皇帝 before installing, requesting installation, or pretending it exists.
- Preserve user constraints above institutional metaphor. The user's newest instruction outranks all role logic.

## Task Scale Decision

中书省 first classifies the task:

- **S0 Trivial**: direct answer, tiny wording change, one simple command, one obvious file inspection. Do locally. Do not spawn.
- **S1 Small**: single-file change, narrow bug fix, short text revision, one obvious skill. Usually do locally with brief self-review.
- **S2 Medium**: multi-file change, moderate uncertainty, implementation plus review, one or two specialized skills. Use two or three agents only if explicitly requested and independently useful.
- **S3 Large**: architecture work, complex document/deck/app/research deliverable, several skills, meaningful independent critique or validation. Use three to five bounded agents if justified.
- **S4 Imperial Campaign**: long-running or multi-domain project with staged milestones. Ask the 皇帝 to confirm scope and resource level before using more than five agents.
- **Imperial Emergency**: user asks to stop, correct direction, or avoid a risky action. Pause expansion and obey the 皇帝.

Dynamic count rule:

```text
if user did not explicitly request multi-agent / agents / subagents / collaboration:
    agent_count = 0
elif task_size in S0 or S1:
    agent_count = 0 or 1 reviewer only if the user insisted
elif task_size == S2:
    agent_count = 2 or 3
elif task_size == S3:
    agent_count = 3 to 5
elif task_size == S4:
    ask user before using more than 5
```

## Default Workflow

1. **皇帝下诏**
   - Restate the user's goal, constraints, deliverables, and acceptance criteria.
   - Identify required skills, plugins, files, tools, and likely verification.

2. **中书省拟旨**
   - Classify task size and complexity.
   - Decide whether subagents are justified.
   - Inspect available skills before assigning work.
   - If necessary skills are unavailable, ask the 皇帝 whether to install, create, proceed with fallback, or continue without it.
   - Produce an allocation plan: role, scope, allowed skills, forbidden overlap, output format, and stop condition.

3. **门下省封驳**
   - Review whether the plan is proportional, complete, non-overlapping, and consistent with user constraints.
   - Reject plans that overuse agents, lack verification, assign overlapping edits, ignore skill availability, or delegate blocking work unnecessarily.
   - If the plan is wasteful, missing verification, or unsafe, revise before execution.

4. **尚书省执行**
   - Carry out the approved plan.
   - Spawn only the approved number of agents and only for bounded tasks.
   - Give each execution agent a concrete mission, inputs, allowed files/domains, forbidden files/domains, relevant skills, expected output, stop condition, and review criteria.
   - Continue useful local work while agents run.
   - Summarize and integrate agent outputs.

5. **门下省复核**
   - Check final output against the original edict and the latest user instruction.
   - Verify files, tests, renders, citations, or other quality gates as relevant.
   - If execution drifted, require correction before final response.

6. **回奏皇帝**
   - Deliver the final artifact or answer.
   - State what was created or changed.
   - State verification performed and any skipped checks.
   - Keep subagent details concise unless the 皇帝 asks for the full court record.

## Agent Boundary Contract

Every execution agent assignment must include:

```text
Agent:
Mission:
Inputs:
Allowed files / domains:
Forbidden files / domains:
Relevant skills:
Tools allowed:
Expected output:
Stop condition:
Review criteria:
```

If any field is unclear, do not spawn that agent yet.

## Skill Inspection Rules

Before dispatching execution agents, 中书省 should identify skills by name and purpose:

- Use available skills already listed in context first.
- Read only the needed `SKILL.md` files and reference files.
- Choose the minimal sufficient skill set.
- If a needed skill is absent, ask the 皇帝 whether to install or create it, use a fallback, or proceed without it.
- If installation is not approved or impossible, use a fallback and disclose the limitation.

Suggested missing-skill wording:

```text
这一步需要一个用于 [capability] 的 skill，但当前可用列表里没有。我可以用通用流程替代，或者你可以让我安装/创建对应 skill。你想怎么走？
```

## Output Forms

For substantial tasks, expose a compact court record:

```text
【圣旨】User goal and constraints.
【中书省】Task scale, skill needs, agent allocation.
【门下省】Audit result: approved / revised / rejected, with reason.
【尚书省】Execution summary.
【门下省复核】Verification result.
【回奏】Final answer and artifact links.
```

For simple tasks, do not show the full court record. Execute directly and provide a concise result:

```text
【中书裁定】Result.
【验证】What was checked, or why no check was needed.
```

## Program-Level Orchestrator

For code-level orchestration, use `scripts/huangdi_orchestrator.py`. It implements the 皇帝 / 中书省 / 门下省 / 尚书省 state machine as a local program:

- scans available Codex skills from `~/.codex/skills`;
- classifies task scale and chooses a proportional number of execution assignments;
- performs 门下省 plan audit before execution;
- builds bounded execution-agent packets with allowed skills, scope, output format, and stop conditions;
- schedules approved assignments through a task queue;
- runs medium/large assignments in parallel when `--max-workers` is greater than 1;
- writes structured JSONL logs and an HTML visual timeline;
- recalls and stores long-term run memory in SQLite;
- performs 门下省 result audit after execution;
- can export a full JSON court record and all role prompts.

Use the deterministic rule backend for planning, debugging, and dry runs:

```powershell
python C:\Users\0\.codex\skills\huangdi-skill\scripts\huangdi_orchestrator.py "你的任务" --explicit-multi-agent --max-workers 4 --json-out court_record.json --prompts-out court_prompts.json
```

Use the command backend when wiring the framework to an external LLM runner:

```powershell
python C:\Users\0\.codex\skills\huangdi-skill\scripts\huangdi_orchestrator.py "你的任务" --backend command --llm-command "python my_llm_adapter.py"
```

The command backend sends one JSON object to stdin:

```json
{"role": "zhongshu|menxia_plan|executor|menxia_result", "payload": "..."}
```

and expects one JSON object on stdout matching the requested role schema. See `references/orchestrator-architecture.md` for the program architecture and extension points.

Runtime outputs:

- `huangdi_runs/{run_id}.events.jsonl`: machine-readable event stream.
- `huangdi_runs/{run_id}.timeline.html`: visual log for human inspection.
- `~/.codex/skills/huangdi-skill/memory/huangdi_memory.sqlite3`: default long-term memory database.

## References

- `references/role-templates.md`: Prompt templates for 中书省, 门下省, 尚书省, and execution agents.
- `references/governance-checklists.md`: Task scale rubric, plan audit checklist, execution audit checklist, rejection conditions, and final response checklist.
- `references/orchestrator-architecture.md`: Program-level architecture, backends, state machine, and adapter contract.
