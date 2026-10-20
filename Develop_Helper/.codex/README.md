# SDD Codex Adapter

本目录只维护 Codex 配置和子智能体适配器。核心执行规则在 `harness-core/`。

## 入口与技能发现

- 根入口：`AGENTS.md`，按 `harness-core/router.md` 路由。
- Codex 配置：`.codex/config.toml`。
- 项目技能发现入口：`.agents/skills/`（复数 `agents`），提供全部七个核心 Skill 的薄入口。
- 兼容入口：`.codex/skills/`、`.cursor/skills/`、`.claude/skills/`；同名入口的元信息和正文保持一致，仅指向 `harness-core/skills/`。
- 入口中的核心链接相对于入口文件解析，不依赖当前项目的工作目录。

Cursor 同时支持 `.agents/skills/` 及以上兼容目录；不能假定同名 Skill 会按某个固定顺序去重。保留兼容入口可能使客户端展示多个同名项，因此不在各副本维护不同规则。新增或调整入口时同步同名副本，核心 Skill 的 description 是描述来源。课堂发布前在实际客户端核对技能列表；文件存在不等于运行时已发现。

## 子智能体

平台定义位于 `.codex/agents/`，按编排器传入的项目绝对路径与授权范围工作：

- `solution-designer` → `harness-core/agents/solution-designer.md`：PRD 确认后实际派发，产出七层方案与待决事项。
- `planner` → `harness-core/agents/planner.md`：技术方案及必要界面确认后实际派发，产出任务计划。
- `developer` → `harness-core/agents/developer.md`：实现当前任务、自验并返回证据；经验只提交建议。
- `tester` → `harness-core/agents/tester.md`：独立验收并返回 PASS / FAIL / BLOCKED 及证据。

调度与降级按 `harness-core/protocols/codex-subagents.md`；任务执行按 `harness-core/protocols/development-loop.md`。不能以读取角色文件替代实际派发。平台不能按 TOML 名称启动时，仍可使用可用的通用子智能体并传入角色文件；只有当前工具确无调度能力或调用明确返回不可用时，才按协议说明限制并降级。
