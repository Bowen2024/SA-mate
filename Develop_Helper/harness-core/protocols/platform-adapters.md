# 平台适配

核心规则统一位于 `harness-core/`。平台入口只引导 Agent 读取核心文件，不复制工作流程。

| 平台 | 自动入口 | 角色适配 |
| --- | --- | --- |
| Codex | `AGENTS.md` | `.codex/agents/*.toml` |
| Claude Code | `.claude/CLAUDE.md` | `.claude/agents/*.md` |
| Cursor | `.cursor/rules/00-harness-router.mdc` | `.cursor/agents/*.md` |

三个入口都读取 `harness-core/router.md`。平台 Skills 只引用 `harness-core/skills/` 的对应文件。核心阶段增加、合并或移除时，同步适配路径，避免旧入口指向不存在的文件。

子智能体适配只声明角色信息并指向 `harness-core/agents/`，执行规则以核心角色文件为准。是否能直接启动子智能体以当前环境可用能力为准；不能调用时按 [角色降级协议](codex-subagents.md) 执行。

业务项目的 `AGENTS.md` 是返回 Harness 的轻量入口。`Projects_Repo/<project-id>/` 保存代码、`docs/` 与 `.sdd/`，不复制 `.codex/`、`.claude/`、`.cursor/` 平台适配目录。
