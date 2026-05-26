# Governance Checklists

## Task Scale Rubric

S0 Trivial:
- Direct factual or conceptual answer.
- Tiny wording change.
- One short file inspection.
- One simple command.
- No meaningful uncertainty.

S1 Small:
- Single-file change.
- Narrow bug fix with obvious tests.
- Short text revision.
- One skill is clearly sufficient.

S2 Medium:
- Multi-file change with moderate uncertainty.
- Requires one or two specialized skills.
- Needs implementation plus review.
- Has moderate design or testing risk.

S3 Large:
- Architecture change.
- Complex document, deck, app, or research deliverable.
- Multiple skills are relevant.
- Requires independent critique, validation, synthesis, or staged execution.

S4 Imperial Campaign:
- Long-running project plan.
- Multi-domain research and implementation.
- High-stakes deliverable with multiple review loops.
- Requires staged milestones and explicit acceptance gates.

## 中书 Plan Checklist

- Goal and deliverables are explicit.
- Latest user constraints are included.
- Task size is graded S0-S4.
- Required skills are identified.
- Missing skills trigger a question to the user.
- Agent count is proportional to task size.
- Every execution agent has a non-overlapping scope.
- The immediate blocking task remains local unless delegation is clearly better.
- Verification is planned before final delivery.

## 门下 Plan Rejection Conditions

Reject or revise the plan if:
- It opens agents without explicit user authorization.
- It creates ceremony for S0/S1 tasks.
- It lacks a final verification step.
- It assigns overlapping file edits.
- It delegates a blocking task that the lead should do locally.
- It ignores a user constraint.
- It assumes unavailable skills or tools without checking.
- It allows subagents to make destructive changes, purchases, live sends, production changes, or broad refactors without explicit permission.
- It asks several agents for duplicated generic summaries.

## 尚书 Execution Checklist

- Use the approved plan as the boundary.
- Continue local work while side agents run.
- Do not wait for agents unless their result blocks integration.
- Do not let execution agents change strategy.
- Inspect all changed files before final delivery.
- Resolve contradictions using evidence and user constraints.
- Keep final artifacts clean; do not include raw transcripts unless requested.

## 门下 Result Audit Checklist

- Final answer matches the latest user request.
- Output format matches the requested format.
- Files are created in the intended location.
- Forbidden files are not modified.
- Claims are supported by observed files, test output, citations, or tool results.
- Skipped verification is disclosed.
- Residual risks are concise and actionable.

## 门下驳回 Format

```text
门下驳回:
Reason:
Required revision:
Responsible role:
Evidence needed for approval:
```

After rejection:

1. Send the issue back only to the responsible role.
2. Keep the revision scope narrow.
3. Re-run review on the revised portion.
4. Do not proceed to final synthesis until all blocking rejections are resolved or explicitly waived by the user.

## Final Court Record Template

```text
【圣旨】
[goal]

【中书省】
任务体量：[scale]
用到的 skill：[skills]
执行分配：[agents_or_local]

【门下省】
审核：[approved/revised/rejected]
理由：[reason]

【尚书省】
执行：[summary]

【门下省复核】
验证：[checks]
风险：[remaining_risks]

【回奏】
[final_answer]
```
