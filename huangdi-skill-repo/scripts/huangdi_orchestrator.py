from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import html
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class TaskScale(str, Enum):
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"


class AuditDecision(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class UserEdict:
    goal: str
    constraints: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass
class SkillInfo:
    name: str
    path: str
    description: str


@dataclass
class AgentAssignment:
    agent: str
    role: str
    mission: str
    inputs: list[str] = field(default_factory=list)
    allowed_files_or_domains: list[str] = field(default_factory=list)
    forbidden_files_or_domains: list[str] = field(default_factory=list)
    relevant_skills: list[str] = field(default_factory=list)
    tools_allowed: list[str] = field(default_factory=list)
    expected_output: str = ""
    stop_condition: str = ""
    review_criteria: list[str] = field(default_factory=list)
    spawn: bool = False


@dataclass
class Plan:
    task_scale: str
    required_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    agent_count: int = 0
    assignments: list[AgentAssignment] = field(default_factory=list)
    verification_plan: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class AuditResult:
    decision: str
    issues: list[str] = field(default_factory=list)
    required_revisions: list[str] = field(default_factory=list)
    responsible_role: str = ""


@dataclass
class ExecutionResult:
    assignment_agent: str
    status: str
    output: str
    artifacts: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass
class CourtRecord:
    edict: UserEdict
    available_skills: list[SkillInfo]
    plan: Plan
    plan_audit: AuditResult
    execution_results: list[ExecutionResult]
    result_audit: AuditResult
    final_report: str
    run_id: str = ""
    memory_matches: list[dict[str, Any]] = field(default_factory=list)
    queue_summary: list[dict[str, Any]] = field(default_factory=list)
    log_artifacts: list[str] = field(default_factory=list)


@dataclass
class QueueTask:
    task_id: str
    assignment: AgentAssignment
    status: str = TaskStatus.QUEUED.value
    result: ExecutionResult | None = None
    error: str = ""
    started_at: str = ""
    ended_at: str = ""


def dataclass_from_dict(cls: type[Any], data: dict[str, Any]) -> Any:
    if cls is Plan:
        assignments = [dataclass_from_dict(AgentAssignment, a) for a in data.get("assignments", [])]
        return Plan(
            task_scale=str(data.get("task_scale", "S1")),
            required_skills=list(data.get("required_skills", [])),
            missing_skills=list(data.get("missing_skills", [])),
            agent_count=int(data.get("agent_count", len(assignments))),
            assignments=assignments,
            verification_plan=list(data.get("verification_plan", [])),
            rationale=str(data.get("rationale", "")),
        )
    if cls is AgentAssignment:
        return AgentAssignment(
            agent=str(data.get("agent", "")),
            role=str(data.get("role", "")),
            mission=str(data.get("mission", "")),
            inputs=list(data.get("inputs", [])),
            allowed_files_or_domains=list(data.get("allowed_files_or_domains", [])),
            forbidden_files_or_domains=list(data.get("forbidden_files_or_domains", [])),
            relevant_skills=list(data.get("relevant_skills", [])),
            tools_allowed=list(data.get("tools_allowed", [])),
            expected_output=str(data.get("expected_output", "")),
            stop_condition=str(data.get("stop_condition", "")),
            review_criteria=list(data.get("review_criteria", [])),
            spawn=bool(data.get("spawn", False)),
        )
    if cls is AuditResult:
        return AuditResult(
            decision=str(data.get("decision", "reject")),
            issues=list(data.get("issues", [])),
            required_revisions=list(data.get("required_revisions", [])),
            responsible_role=str(data.get("responsible_role", "")),
        )
    if cls is ExecutionResult:
        return ExecutionResult(
            assignment_agent=str(data.get("assignment_agent", "")),
            status=str(data.get("status", "")),
            output=str(data.get("output", "")),
            artifacts=list(data.get("artifacts", [])),
            verification=list(data.get("verification", [])),
            risks=list(data.get("risks", [])),
        )
    raise TypeError(f"Unsupported dataclass: {cls}")


def read_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in model output: {text[:400]}")
    return json.loads(stripped[start : end + 1])


class SkillRegistry:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills = self._discover()

    def _discover(self) -> list[SkillInfo]:
        result: list[SkillInfo] = []
        if not self.skills_dir.exists():
            return result
        for skill_md in sorted(self.skills_dir.glob("*/SKILL.md")):
            try:
                text = skill_md.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = skill_md.read_text(encoding="utf-8", errors="replace")
            name = self._frontmatter_value(text, "name") or skill_md.parent.name
            description = self._frontmatter_value(text, "description") or ""
            result.append(SkillInfo(name=name, path=str(skill_md), description=description))
        return result

    @staticmethod
    def _frontmatter_value(text: str, key: str) -> str:
        match = re.search(rf"^{re.escape(key)}:\s*(.+)$", text, flags=re.MULTILINE)
        return match.group(1).strip() if match else ""

    def search(self, query: str) -> list[SkillInfo]:
        terms = {t.lower() for t in re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", query)}
        scored: list[tuple[int, SkillInfo]] = []
        for skill in self.skills:
            haystack = f"{skill.name} {skill.description}".lower()
            score = sum(1 for term in terms if term and term in haystack)
            if score:
                scored.append((score, skill))
        return [s for _score, s in sorted(scored, key=lambda item: (-item[0], item[1].name))]

    def by_name(self, names: Iterable[str]) -> list[SkillInfo]:
        wanted = {name.lower() for name in names}
        return [s for s in self.skills if s.name.lower() in wanted]


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def keyword_tokens(text: str) -> set[str]:
    tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9_\-]+", text)
        if len(token) >= 2
    }
    for seq in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(seq) <= 4:
            tokens.add(seq)
            continue
        for size in (2, 3, 4):
            for index in range(0, len(seq) - size + 1):
                tokens.add(seq[index : index + size])
    return tokens


class EventLogger:
    """Structured JSONL logger with a small HTML timeline for visual inspection."""

    def __init__(self, log_dir: Path | None = None, run_id: str | None = None):
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.log_dir = log_dir
        self.events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self.jsonl_path: Path | None = None
        self.html_path: Path | None = None
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self.jsonl_path = self.log_dir / f"{self.run_id}.events.jsonl"
            self.html_path = self.log_dir / f"{self.run_id}.timeline.html"

    def emit(self, stage: str, message: str, **data: Any) -> None:
        event = {
            "run_id": self.run_id,
            "time": utc_now(),
            "stage": stage,
            "message": message,
            "data": data,
        }
        with self._lock:
            self.events.append(event)
            if self.jsonl_path:
                with self.jsonl_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def artifacts(self) -> list[str]:
        return [str(p) for p in (self.jsonl_path, self.html_path) if p]

    def write_html(self, court: CourtRecord | None = None) -> None:
        if not self.html_path:
            return
        cards = []
        for event in self.events:
            data = html.escape(json.dumps(event["data"], ensure_ascii=False, indent=2))
            cards.append(
                f"""
                <article class="event">
                  <div class="meta">{html.escape(event['time'])} · {html.escape(event['stage'])}</div>
                  <h2>{html.escape(event['message'])}</h2>
                  <pre>{data}</pre>
                </article>
                """
            )
        summary = ""
        if court:
            summary = f"""
            <section class="summary">
              <h2>Court Summary</h2>
              <p><b>Task scale:</b> {html.escape(court.plan.task_scale)}</p>
              <p><b>Assignments:</b> {len(court.plan.assignments)}</p>
              <p><b>Result audit:</b> {html.escape(court.result_audit.decision)}</p>
            </section>
            """
        document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Huangdi Run {html.escape(self.run_id)}</title>
  <style>
    body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: #f7f5f0; color: #1f2933; }}
    header {{ padding: 28px 36px; background: #7f1d1d; color: white; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
    .summary, .event {{ background: white; border: 1px solid #e4ded4; border-radius: 8px; padding: 18px; margin-bottom: 14px; }}
    .meta {{ color: #735f46; font-size: 13px; margin-bottom: 6px; }}
    h1, h2 {{ margin: 0 0 10px; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #faf8f3; padding: 12px; border-radius: 6px; }}
  </style>
</head>
<body>
  <header><h1>皇帝skill 可视化日志</h1><p>Run ID: {html.escape(self.run_id)}</p></header>
  <main>{summary}{''.join(cards)}</main>
</body>
</html>
"""
        self.html_path.write_text(document, encoding="utf-8")


class LongTermMemory:
    """Small SQLite memory store for prior court runs and reusable lessons."""

    def __init__(self, db_path: Path | None):
        self.db_path = db_path
        self._lock = threading.Lock()
        if self.db_path:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

    def enabled(self) -> bool:
        return self.db_path is not None

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path:
            raise RuntimeError("Long-term memory is disabled.")
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    task_scale TEXT NOT NULL,
                    required_skills TEXT NOT NULL,
                    final_report TEXT NOT NULL,
                    result_audit TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source_run_id TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    note TEXT NOT NULL
                )
                """
            )

    def recall(self, goal: str, limit: int = 5) -> list[dict[str, Any]]:
        if not self.enabled():
            return []
        terms = sorted(keyword_tokens(goal), key=len, reverse=True)[:8]
        if not terms:
            return []
        clauses = " OR ".join(["goal LIKE ? OR required_skills LIKE ? OR final_report LIKE ?" for _ in terms])
        params: list[str] = []
        for term in terms:
            like = f"%{term}%"
            params.extend([like, like, like])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT run_id, created_at, goal, task_scale, required_skills, result_audit
                FROM runs
                WHERE {clauses}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()
        return [
            {
                "run_id": row[0],
                "created_at": row[1],
                "goal": row[2],
                "task_scale": row[3],
                "required_skills": json.loads(row[4]),
                "result_audit": row[5],
            }
            for row in rows
        ]

    def remember(self, court: CourtRecord) -> None:
        if not self.enabled():
            return
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runs
                    (run_id, created_at, goal, task_scale, required_skills, final_report, result_audit)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        court.run_id,
                        utc_now(),
                        court.edict.goal,
                        court.plan.task_scale,
                        json.dumps(court.plan.required_skills, ensure_ascii=False),
                        court.final_report,
                        court.result_audit.decision,
                    ),
                )
                for skill in court.plan.required_skills:
                    conn.execute(
                        """
                        INSERT INTO lessons (created_at, source_run_id, keyword, note)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            utc_now(),
                            court.run_id,
                            skill,
                            f"Task scale {court.plan.task_scale}; result audit {court.result_audit.decision}.",
                        ),
                    )


class TaskQueue:
    """In-memory task queue for assignment scheduling and status reporting."""

    def __init__(self, assignments: list[AgentAssignment]):
        self.tasks = [
            QueueTask(task_id=f"T{i + 1:03d}", assignment=assignment)
            for i, assignment in enumerate(assignments)
        ]
        self._lock = threading.Lock()

    def mark_running(self, task_id: str) -> None:
        self._update(task_id, status=TaskStatus.RUNNING.value, started_at=utc_now())

    def mark_completed(self, task_id: str, result: ExecutionResult) -> None:
        self._update(task_id, status=TaskStatus.COMPLETED.value, result=result, ended_at=utc_now())

    def mark_failed(self, task_id: str, error: str) -> None:
        self._update(task_id, status=TaskStatus.FAILED.value, error=error, ended_at=utc_now())

    def _update(self, task_id: str, **changes: Any) -> None:
        with self._lock:
            for task in self.tasks:
                if task.task_id == task_id:
                    for key, value in changes.items():
                        setattr(task, key, value)
                    return
            raise KeyError(task_id)

    def summary(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "task_id": task.task_id,
                    "agent": task.assignment.agent,
                    "role": task.assignment.role,
                    "status": task.status,
                    "started_at": task.started_at,
                    "ended_at": task.ended_at,
                    "error": task.error,
                    "artifacts": task.result.artifacts if task.result else [],
                }
                for task in self.tasks
            ]


class LLMBackend:
    def plan(self, edict: UserEdict, skills: list[SkillInfo]) -> Plan:
        raise NotImplementedError

    def audit_plan(self, edict: UserEdict, plan: Plan) -> AuditResult:
        raise NotImplementedError

    def execute(self, assignment: AgentAssignment, skill_context: str) -> ExecutionResult:
        raise NotImplementedError

    def audit_result(
        self, edict: UserEdict, plan: Plan, results: list[ExecutionResult]
    ) -> AuditResult:
        raise NotImplementedError


class RuleBackend(LLMBackend):
    """Deterministic offline backend for smoke tests and dry runs."""

    def __init__(self, explicit_multi_agent: bool = False):
        self.explicit_multi_agent = explicit_multi_agent

    def plan(self, edict: UserEdict, skills: list[SkillInfo]) -> Plan:
        text = " ".join([edict.goal, *edict.constraints, *edict.deliverables]).lower()
        scale = self._classify(text)
        relevant = self._select_skills(text, skills)
        allow_agents = self.explicit_multi_agent and scale in {TaskScale.S2, TaskScale.S3, TaskScale.S4}
        agent_count = 0
        assignments: list[AgentAssignment] = []

        if allow_agents:
            agent_count = 2 if scale == TaskScale.S2 else 3
            assignments = [
                AgentAssignment(
                    agent="zhongshu-local",
                    role="中书省",
                    mission="Refine the approved plan into bounded execution tasks.",
                    relevant_skills=[s.name for s in relevant],
                    expected_output="Execution-ready task list.",
                    stop_condition="Plan is actionable and non-overlapping.",
                    review_criteria=["No overlap", "Skills identified", "Verification included"],
                    spawn=False,
                ),
                AgentAssignment(
                    agent="shangshu-executor",
                    role="尚书省",
                    mission=f"Execute the task: {edict.goal}",
                    relevant_skills=[s.name for s in relevant],
                    expected_output="Concrete work result and verification notes.",
                    stop_condition="All deliverables are produced or blockers are reported.",
                    review_criteria=edict.acceptance_criteria or ["Matches user request"],
                    spawn=True,
                ),
                AgentAssignment(
                    agent="menxia-reviewer",
                    role="门下省",
                    mission="Audit the execution result against the original edict.",
                    relevant_skills=[s.name for s in relevant],
                    expected_output="Approve/reject decision with issues.",
                    stop_condition="Blocking issues are identified or result is approved.",
                    review_criteria=["No drift", "No unsupported claims", "Verification adequate"],
                    spawn=True,
                ),
            ][:agent_count]
        else:
            assignments = [
                AgentAssignment(
                    agent="local-shangshu",
                    role="尚书省",
                    mission=f"Execute locally without spawning: {edict.goal}",
                    relevant_skills=[s.name for s in relevant],
                    expected_output="Concise result, files changed, and verification.",
                    stop_condition="Deliverable is complete or blocker is reported.",
                    review_criteria=edict.acceptance_criteria or ["Matches user request"],
                    spawn=False,
                )
            ]

        return Plan(
            task_scale=scale.value,
            required_skills=[s.name for s in relevant],
            missing_skills=[],
            agent_count=sum(1 for a in assignments if a.spawn),
            assignments=assignments,
            verification_plan=["Check deliverables", "Run relevant validation", "Disclose skipped checks"],
            rationale="Rule backend selected the smallest proportional execution pattern.",
        )

    @staticmethod
    def _classify(text: str) -> TaskScale:
        large_terms = ["architecture", "架构", "project", "项目", "multi", "多agent", "多 agent", "复杂"]
        medium_terms = ["docx", "论文", "code", "代码", "implement", "实现", "skill", "spreadsheet", "deck"]
        if any(t in text for t in large_terms):
            return TaskScale.S3
        if any(t in text for t in medium_terms):
            return TaskScale.S2
        if len(text) < 120:
            return TaskScale.S1
        return TaskScale.S2

    @staticmethod
    def _select_skills(text: str, skills: list[SkillInfo]) -> list[SkillInfo]:
        selected: list[SkillInfo] = []
        for skill in skills:
            haystack = f"{skill.name} {skill.description}".lower()
            if skill.name.lower() in text or any(token in haystack and token in text for token in ["docx", "latex", "英文", "skill", "browser"]):
                selected.append(skill)
        return selected[:5]

    def audit_plan(self, edict: UserEdict, plan: Plan) -> AuditResult:
        issues: list[str] = []
        if plan.task_scale in {"S0", "S1"} and plan.agent_count:
            issues.append("S0/S1 task should not spawn agents.")
        if not plan.assignments:
            issues.append("Plan has no execution assignment.")
        for assignment in plan.assignments:
            if not assignment.mission or not assignment.expected_output or not assignment.stop_condition:
                issues.append(f"Assignment {assignment.agent} lacks required boundary fields.")
        return AuditResult(
            decision=AuditDecision.REJECT.value if issues else AuditDecision.APPROVE.value,
            issues=issues,
            required_revisions=issues,
            responsible_role="中书省" if issues else "",
        )

    def execute(self, assignment: AgentAssignment, skill_context: str) -> ExecutionResult:
        output = (
            "Rule backend does not perform external model execution. "
            "It produced an execution packet for the assignment."
        )
        if skill_context:
            output += f" Loaded skill context characters: {len(skill_context)}."
        return ExecutionResult(
            assignment_agent=assignment.agent,
            status="prepared",
            output=output,
            artifacts=[],
            verification=["Assignment boundary checked"],
            risks=["Use command backend or integrate a model adapter for real execution."],
        )

    def audit_result(
        self, edict: UserEdict, plan: Plan, results: list[ExecutionResult]
    ) -> AuditResult:
        issues = []
        if not results:
            issues.append("No execution results.")
        if any(r.status not in {"prepared", "completed"} for r in results):
            issues.append("At least one execution result is incomplete.")
        return AuditResult(
            decision=AuditDecision.REJECT.value if issues else AuditDecision.APPROVE.value,
            issues=issues,
            required_revisions=issues,
            responsible_role="尚书省" if issues else "",
        )


class CommandBackend(LLMBackend):
    """Send role packets to an external command that returns JSON on stdout."""

    def __init__(self, command: str):
        self.command = command

    def _call(self, role: str, payload: dict[str, Any]) -> dict[str, Any]:
        packet = {"role": role, "payload": payload}
        proc = subprocess.run(
            shlex.split(self.command),
            input=json.dumps(packet, ensure_ascii=False),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"LLM command failed for {role}: {proc.stderr.strip()}")
        return read_json_object(proc.stdout)

    def plan(self, edict: UserEdict, skills: list[SkillInfo]) -> Plan:
        prompt = build_zhongshu_prompt(edict, skills)
        data = self._call(
            "zhongshu",
            {"display_role": "中书省", "prompt": prompt, "edict": asdict(edict), "skills": [asdict(s) for s in skills]},
        )
        return dataclass_from_dict(Plan, data)

    def audit_plan(self, edict: UserEdict, plan: Plan) -> AuditResult:
        prompt = build_menxia_plan_audit_prompt(edict, plan)
        data = self._call(
            "menxia_plan",
            {"display_role": "门下省-方案审核", "prompt": prompt, "edict": asdict(edict), "plan": asdict(plan)},
        )
        return dataclass_from_dict(AuditResult, data)

    def execute(self, assignment: AgentAssignment, skill_context: str) -> ExecutionResult:
        prompt = build_executor_prompt(assignment, skill_context)
        data = self._call(
            "executor",
            {
                "display_role": "尚书省/执行Agent",
                "prompt": prompt,
                "assignment": asdict(assignment),
                "skill_context": skill_context,
            },
        )
        return dataclass_from_dict(ExecutionResult, data)

    def audit_result(
        self, edict: UserEdict, plan: Plan, results: list[ExecutionResult]
    ) -> AuditResult:
        prompt = build_menxia_result_audit_prompt(edict, plan, results)
        data = self._call(
            "menxia_result",
            {
                "display_role": "门下省-结果复核",
                "prompt": prompt,
                "edict": asdict(edict),
                "plan": asdict(plan),
                "results": [asdict(r) for r in results],
            },
        )
        return dataclass_from_dict(AuditResult, data)


def build_zhongshu_prompt(edict: UserEdict, skills: list[SkillInfo]) -> str:
    return f"""你是中书省，只负责规划，不执行。

皇帝任务:
{json.dumps(asdict(edict), ensure_ascii=False, indent=2)}

可用 skills:
{json.dumps([asdict(s) for s in skills], ensure_ascii=False, indent=2)}

返回 JSON，字段必须符合:
{{
  "task_scale": "S0|S1|S2|S3|S4",
  "required_skills": [],
  "missing_skills": [],
  "agent_count": 0,
  "assignments": [
    {{
      "agent": "...",
      "role": "中书省|门下省|尚书省|执行Agent",
      "mission": "...",
      "inputs": [],
      "allowed_files_or_domains": [],
      "forbidden_files_or_domains": [],
      "relevant_skills": [],
      "tools_allowed": [],
      "expected_output": "...",
      "stop_condition": "...",
      "review_criteria": [],
      "spawn": false
    }}
  ],
  "verification_plan": [],
  "rationale": "..."
}}
"""


def build_menxia_plan_audit_prompt(edict: UserEdict, plan: Plan) -> str:
    return f"""你是门下省，只审核中书方案。

皇帝任务:
{json.dumps(asdict(edict), ensure_ascii=False, indent=2)}

中书方案:
{json.dumps(asdict(plan), ensure_ascii=False, indent=2)}

检查是否过度开 Agent、遗漏 skill、违反用户约束、缺少验证、分工重叠。
返回 JSON:
{{
  "decision": "approve|revise|reject",
  "issues": [],
  "required_revisions": [],
  "responsible_role": "中书省"
}}
"""


def build_executor_prompt(assignment: AgentAssignment, skill_context: str) -> str:
    return f"""你是执行角色，不是决策者。严格按边界执行。

任务分配:
{json.dumps(asdict(assignment), ensure_ascii=False, indent=2)}

必须遵守的 skill 内容:
{skill_context}

返回 JSON:
{{
  "assignment_agent": "{assignment.agent}",
  "status": "completed|blocked|failed",
  "output": "...",
  "artifacts": [],
  "verification": [],
  "risks": []
}}
"""


def build_menxia_result_audit_prompt(
    edict: UserEdict, plan: Plan, results: list[ExecutionResult]
) -> str:
    return f"""你是门下省，负责结果复核。

皇帝任务:
{json.dumps(asdict(edict), ensure_ascii=False, indent=2)}

批准方案:
{json.dumps(asdict(plan), ensure_ascii=False, indent=2)}

执行结果:
{json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2)}

返回 JSON:
{{
  "decision": "approve|revise|reject",
  "issues": [],
  "required_revisions": [],
  "responsible_role": "尚书省或具体执行Agent"
}}
"""


class HuangdiOrchestrator:
    def __init__(
        self,
        registry: SkillRegistry,
        backend: LLMBackend,
        max_revisions: int = 2,
        max_workers: int = 1,
        event_logger: EventLogger | None = None,
        memory: LongTermMemory | None = None,
    ):
        self.registry = registry
        self.backend = backend
        self.max_revisions = max_revisions
        self.max_workers = max(1, max_workers)
        self.event_logger = event_logger or EventLogger()
        self.memory = memory or LongTermMemory(None)

    def run(self, edict: UserEdict) -> CourtRecord:
        self.event_logger.emit("receive_task", "皇帝下诏", goal=edict.goal)
        skills = self.registry.skills
        self.event_logger.emit("discover_skills", "扫描可用 skills", count=len(skills))

        memory_matches = self.memory.recall(edict.goal)
        if memory_matches:
            edict = self._with_memory_context(edict, memory_matches)
            self.event_logger.emit("memory_recall", "载入长期记忆", matches=len(memory_matches))

        plan, plan_audit = self._approved_plan(edict, skills)
        self.event_logger.emit(
            "plan_approved",
            "门下省批准中书方案",
            task_scale=plan.task_scale,
            assignments=len(plan.assignments),
            agent_count=plan.agent_count,
        )

        queue = TaskQueue(plan.assignments)
        execution_results = self._execute_plan(plan, queue)
        result_audit = self._audit_results(edict, plan, execution_results)
        final = self._final_report(edict, plan, execution_results, result_audit, queue.summary())

        court = CourtRecord(
            edict=edict,
            available_skills=skills,
            plan=plan,
            plan_audit=plan_audit,
            execution_results=execution_results,
            result_audit=result_audit,
            final_report=final,
            run_id=self.event_logger.run_id,
            memory_matches=memory_matches,
            queue_summary=queue.summary(),
            log_artifacts=self.event_logger.artifacts(),
        )
        self.memory.remember(court)
        self.event_logger.emit("memory_store", "写入长期记忆", enabled=self.memory.enabled())
        self.event_logger.write_html(court)
        return court

    @staticmethod
    def _with_memory_context(edict: UserEdict, memories: list[dict[str, Any]]) -> UserEdict:
        summaries = [
            f"{m['created_at']} | {m['task_scale']} | {m['goal']} | skills={','.join(m['required_skills'])}"
            for m in memories
        ]
        return UserEdict(
            goal=edict.goal,
            constraints=[*edict.constraints, "Relevant long-term memory:\n" + "\n".join(summaries)],
            deliverables=edict.deliverables,
            acceptance_criteria=edict.acceptance_criteria,
        )

    def _approved_plan(self, edict: UserEdict, skills: list[SkillInfo]) -> tuple[Plan, AuditResult]:
        revisions: list[str] = []
        for _attempt in range(self.max_revisions + 1):
            planning_edict = UserEdict(
                goal=edict.goal,
                constraints=[*edict.constraints, *revisions],
                deliverables=edict.deliverables,
                acceptance_criteria=edict.acceptance_criteria,
            )
            plan = self.backend.plan(planning_edict, skills)
            audit = self.backend.audit_plan(planning_edict, plan)
            if audit.decision == AuditDecision.APPROVE.value:
                return plan, audit
            revisions.extend(audit.required_revisions or audit.issues)
        raise RuntimeError("Plan was not approved after revision limit.")

    def _execute_plan(self, plan: Plan, queue: TaskQueue) -> list[ExecutionResult]:
        if not queue.tasks:
            return []
        if self.max_workers <= 1 or len(queue.tasks) == 1:
            return [self._run_queue_task(task, queue) for task in queue.tasks]

        ordered: dict[str, ExecutionResult] = {}
        workers = min(self.max_workers, len(queue.tasks))
        self.event_logger.emit("queue_parallel_start", "尚书省启动并行执行队列", workers=workers)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._run_queue_task, task, queue): task.task_id for task in queue.tasks}
            for future in concurrent.futures.as_completed(futures):
                task_id = futures[future]
                ordered[task_id] = future.result()
        return [ordered[task.task_id] for task in queue.tasks]

    def _run_queue_task(self, task: QueueTask, queue: TaskQueue) -> ExecutionResult:
        queue.mark_running(task.task_id)
        self.event_logger.emit(
            "task_started",
            "执行 Agent 开始任务",
            task_id=task.task_id,
            agent=task.assignment.agent,
            role=task.assignment.role,
        )
        started = time.perf_counter()
        try:
            skill_context = self._load_skill_context(task.assignment.relevant_skills)
            result = self.backend.execute(task.assignment, skill_context)
            queue.mark_completed(task.task_id, result)
            self.event_logger.emit(
                "task_completed",
                "执行 Agent 完成任务",
                task_id=task.task_id,
                agent=task.assignment.agent,
                elapsed_seconds=round(time.perf_counter() - started, 3),
                status=result.status,
            )
            return result
        except Exception as exc:
            message = str(exc)
            queue.mark_failed(task.task_id, message)
            self.event_logger.emit(
                "task_failed",
                "执行 Agent 失败",
                task_id=task.task_id,
                agent=task.assignment.agent,
                error=message,
            )
            return ExecutionResult(
                assignment_agent=task.assignment.agent,
                status="failed",
                output=message,
                risks=["Task failed during queued execution."],
            )

    def _audit_results(
        self, edict: UserEdict, plan: Plan, results: list[ExecutionResult]
    ) -> AuditResult:
        audit = self.backend.audit_result(edict, plan, results)
        return audit

    def _load_skill_context(self, skill_names: list[str]) -> str:
        pieces = []
        for skill in self.registry.by_name(skill_names):
            try:
                text = Path(skill.path).read_text(encoding="utf-8")
            except OSError:
                continue
            pieces.append(f"# Skill: {skill.name}\nPath: {skill.path}\n{text}")
        return "\n\n".join(pieces)

    @staticmethod
    def _final_report(
        edict: UserEdict,
        plan: Plan,
        results: list[ExecutionResult],
        audit: AuditResult,
        queue_summary: list[dict[str, Any]],
    ) -> str:
        return "\n".join(
            [
                "【圣旨】",
                edict.goal,
                "",
                "【中书省】",
                f"任务体量：{plan.task_scale}",
                f"用到的 skill：{', '.join(plan.required_skills) if plan.required_skills else 'none'}",
                f"执行分配：{len(plan.assignments)} assignments, {plan.agent_count} spawned agents requested",
                "",
                "【尚书省】",
                *[f"- {r.assignment_agent}: {r.status}; {r.output}" for r in results],
                "",
                "【任务队列】",
                *[f"- {q['task_id']} {q['agent']}: {q['status']}" for q in queue_summary],
                "",
                "【门下省复核】",
                f"审核：{audit.decision}",
                f"问题：{'; '.join(audit.issues) if audit.issues else 'none'}",
                "",
                "【回奏】",
                "程序级皇帝流程已完成。若使用 rule 后端，本次为流程准备/模拟；若使用 command 后端，结果来自外部模型命令。",
            ]
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="皇帝skill program-level orchestrator")
    parser.add_argument("goal", nargs="?", help="User task / 皇帝圣旨. If omitted, stdin is used.")
    parser.add_argument("--skills-dir", default=str(Path.home() / ".codex" / "skills"))
    parser.add_argument("--constraint", action="append", default=[])
    parser.add_argument("--deliverable", action="append", default=[])
    parser.add_argument("--acceptance", action="append", default=[])
    parser.add_argument("--backend", choices=["rule", "command"], default="rule")
    parser.add_argument("--llm-command", default=os.environ.get("HUANGDI_LLM_COMMAND", ""))
    parser.add_argument("--explicit-multi-agent", action="store_true")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--prompts-out", default="", help="Write role prompts generated from the approved plan.")
    parser.add_argument("--max-workers", type=int, default=4, help="Maximum parallel execution agents.")
    parser.add_argument(
        "--log-dir",
        default=str(Path.cwd() / "huangdi_runs"),
        help="Directory for JSONL event logs and HTML visual timeline. Use empty string to disable.",
    )
    parser.add_argument(
        "--memory-db",
        default=str(Path.home() / ".codex" / "skills" / "huangdi-skill" / "memory" / "huangdi_memory.sqlite3"),
        help="SQLite long-term memory path.",
    )
    parser.add_argument("--no-memory", action="store_true", help="Disable long-term memory for this run.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    goal = args.goal or sys.stdin.read().strip()
    if not goal:
        print("No goal provided.", file=sys.stderr)
        return 2

    registry = SkillRegistry(Path(args.skills_dir))
    if args.backend == "command":
        if not args.llm_command:
            print("--llm-command is required for command backend.", file=sys.stderr)
            return 2
        backend: LLMBackend = CommandBackend(args.llm_command)
    else:
        backend = RuleBackend(explicit_multi_agent=args.explicit_multi_agent)

    edict = UserEdict(
        goal=goal,
        constraints=args.constraint,
        deliverables=args.deliverable,
        acceptance_criteria=args.acceptance,
    )
    event_logger = EventLogger(Path(args.log_dir) if args.log_dir else None)
    memory = LongTermMemory(None if args.no_memory else Path(args.memory_db))
    court = HuangdiOrchestrator(
        registry,
        backend,
        max_workers=args.max_workers,
        event_logger=event_logger,
        memory=memory,
    ).run(edict)

    if args.prompts_out:
        prompts = {
            "zhongshu": build_zhongshu_prompt(court.edict, court.available_skills),
            "menxia_plan": build_menxia_plan_audit_prompt(court.edict, court.plan),
            "executors": [
                build_executor_prompt(a, "") for a in court.plan.assignments
            ],
            "menxia_result": build_menxia_result_audit_prompt(
                court.edict, court.plan, court.execution_results
            ),
        }
        Path(args.prompts_out).write_text(json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(asdict(court), ensure_ascii=False, indent=2), encoding="utf-8")

    print(court.final_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
