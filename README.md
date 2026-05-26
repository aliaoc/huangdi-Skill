[README.md](https://github.com/user-attachments/files/28285571/README.md)
# 皇帝skill

一个面向 Codex 的多 Agent、多 Skill 编排 skill，使用“皇帝 / 三省六部”作为治理隐喻：

- 皇帝：用户，提出总需求并最终验收。
- 中书省：规划任务、评估体量、分配执行 Agent 和所需 skills。
- 门下省：审核方案与结果，负责制衡和驳回异常。
- 尚书省：执行总指挥，调度执行 Agent 落地任务。

## 功能

- 按 S0-S4 自动评估任务体量。
- 动态决定是否启用执行 Agent。
- 扫描本地 Codex skills 并分配给对应任务。
- 对中大型任务支持并行 Agent 执行。
- 内置任务队列，记录 queued / running / completed / failed 状态。
- 输出 JSONL 事件日志和 HTML 可视化时间线。
- 使用 SQLite 保存长期记忆，后续相似任务可自动召回历史经验。
- 支持 rule 后端 dry run，也支持 command 后端接外部 LLM / OpenAI API / Codex CLI 适配器。

## 安装

将本仓库复制到 Codex skills 目录：

```powershell
Copy-Item -Recurse . C:\Users\0\.codex\skills\huangdi-skill
```

或者手动放置为：

```text
~/.codex/skills/huangdi-skill/
```

## 使用

Dry run：

```powershell
python C:\Users\0\.codex\skills\huangdi-skill\scripts\huangdi_orchestrator.py "你的中大型任务" --explicit-multi-agent --max-workers 4 --json-out court_record.json --prompts-out court_prompts.json
```

接外部模型命令：

```powershell
python C:\Users\0\.codex\skills\huangdi-skill\scripts\huangdi_orchestrator.py "任务" --backend command --llm-command "python my_llm_adapter.py" --max-workers 4
```

默认运行输出：

- `huangdi_runs/{run_id}.events.jsonl`
- `huangdi_runs/{run_id}.timeline.html`
- `~/.codex/skills/huangdi-skill/memory/huangdi_memory.sqlite3`

## 目录

```text
SKILL.md
agents/
references/
scripts/
```

核心程序入口：

```text
scripts/huangdi_orchestrator.py
```

架构说明：

```text
references/orchestrator-architecture.md
```

## 许可

MIT License.
