# 07 原文地图、脚本能力与差异说明

[阅读目录](README.md) · [上一篇：完整实例](06-walkthrough.md)

核对日期：2026-09-12。本篇帮助定位原文，并区分规范描述、脚本实现与历史参考。本次未修改这些核心规则或运行脚本；下面的“建议”不自动成为框架新要求。

## 1. 文件夹阅读地图

```text
Develop_Helper/
├── README.md                 首页和中文指南入口
├── AGENTS.md                 引导到核心 Router
├── Develop_Helper_reading-guide/ 本次新增的人类阅读层
├── .agents/skills/           Codex 技能发现薄入口
├── .codex/                  Codex 配置、角色、兼容技能入口
├── .claude/                 Claude 入口、角色、兼容技能入口
├── .cursor/                 Cursor 入口、角色、兼容技能入口
├── harness-core/
│   ├── router.md            请求分流
│   ├── skills/              七个核心 Skill 与阶段/参考文档
│   ├── agents/              四种角色定义
│   ├── protocols/           八份跨阶段协议
│   └── specification/       规范集说明和 default 的 14 份规范
├── scripts/                 项目管理、派发检查、一致性检查与测试
├── templates/               项目初始化与任务模板
├── project-registry.json    项目登记和默认活动项目
├── Projects_Repo/           业务项目位置
├── pycore/                  后端基础库和人类参考文档
├── pyproject.toml           本地 PyCore 包和依赖声明
├── learning/                技术名词学习记录
├── memory/                  全局经验及标注历史的旧条目
└── PACKAGING_NOTES.md        打包背景，部分示例与当前版本有差异
```

整理前登记为空、Projects_Repo 只有占位文件；本次指南中的示例项目没有实际创建。

## 2. 按阶段定位核心原文

| 原文 | 回答什么 |
| --- | --- |
| [Router](../Develop_Helper/harness-core/router.md) | 如何区分技术讨论与项目工作 |
| [项目管理](../Develop_Helper/harness-core/skills/project-management/SKILL.md) | 新建、修改、纳管、移除如何定位 |
| [新建入口](../Develop_Helper/harness-core/skills/sdd-product-design/SKILL.md) | 信息、规范选择、创建脚本和设计主链 |
| [阶段 A](../Develop_Helper/harness-core/skills/sdd-product-design/phase-A.md) | PRD、REQ/AC、流程图与业务时序 |
| [阶段 R](../Develop_Helper/harness-core/skills/sdd-product-design/phase-R.md) | 按需调研、工具边界与回写 |
| [调研模板](../Develop_Helper/harness-core/skills/sdd-product-design/references/research-template.md) | 事实、来源、推断、项目建议怎样分开 |
| [方案设计](../Develop_Helper/harness-core/skills/solution-design/SKILL.md) | 七层方案、体验讨论、图的技术细化 |
| [七层模板](../Develop_Helper/harness-core/skills/solution-design/references/tech-spec-template.md) | tech-spec 的章节和每层字段 |
| [接口体验分析](../Develop_Helper/harness-core/skills/solution-design/references/interface-experience-review.md) | 技术选择怎样改变等待、质量、恢复等体验 |
| [决策模板](../Develop_Helper/harness-core/skills/solution-design/references/decision-record-template.md) | 保存选项、选择与确认依据 |
| [阶段 B](../Develop_Helper/harness-core/skills/sdd-product-design/phase-B.md) | 风格、原型、浏览器验证与设计确认 |
| [UI Skill](../Develop_Helper/harness-core/skills/ui-design-standard/SKILL.md)及[模板](../Develop_Helper/harness-core/skills/ui-design-standard/references/ui-style-template.md) | 全局视觉和逐页设计 |
| [Solution Designer](../Develop_Helper/harness-core/agents/solution-designer.md) | 方案子智能体的输入输出 |
| [Planner](../Develop_Helper/harness-core/agents/planner.md) | Feature/Task、依赖、AC 覆盖、缺 Key 推演 |
| [Developer](../Develop_Helper/harness-core/agents/developer.md) | 当前任务实现、自验与写入边界 |
| [Tester](../Develop_Helper/harness-core/agents/tester.md) | 独立验收、证据与 PASS/FAIL/BLOCKED |

## 3. 八份协议分别负责什么

| 原文 | 职责 |
| --- | --- |
| [development-loop](../Develop_Helper/harness-core/protocols/development-loop.md) | 开发循环、状态、并行、返工、恢复、完成条件 |
| [development-rules](../Develop_Helper/harness-core/protocols/development-rules.md) | 跨角色共同约定，不重定义状态机 |
| [execution-mode](../Develop_Helper/harness-core/protocols/execution-mode.md) | automatic/step_by_step、当前检查点、切换 |
| [frontend-gate](../Develop_Helper/harness-core/protocols/frontend-gate.md) | 全部前端 Mock 后暂停、用户与配置双确认 |
| [codex-subagents](../Develop_Helper/harness-core/protocols/codex-subagents.md) | 真实派发、实例回收、停止处理、能力降级 |
| [platform-adapters](../Develop_Helper/harness-core/protocols/platform-adapters.md) | 多平台薄适配与核心规则引用 |
| [project-delivery](../Develop_Helper/harness-core/protocols/project-delivery.md) | 功能导航 HTML 的字段和 DEL-001～005 |
| [experience-loop](../Develop_Helper/harness-core/protocols/experience-loop.md) | 错误事实、复验、去重、项目与全局经验 |

## 4. 修改与学习分支

| 原文 | 用途 |
| --- | --- |
| [纳管](../Develop_Helper/harness-core/skills/project-management/references/onboard-project.md) | 外部复制、register、旧元信息处理 |
| [修改与继续](../Develop_Helper/harness-core/skills/project-management/references/modify-project.md) | 根据当前事实选择回到哪个阶段 |
| [移除/重置](../Develop_Helper/harness-core/skills/project-management/references/remove-reset-project.md) | 清理范围、服务停止、备份和登记 |
| [Bugfix](../Develop_Helper/harness-core/skills/sdd-bugfix/SKILL.md) | 修复已有承诺与实际行为不一致 |
| [Git](../Develop_Helper/harness-core/skills/git-workflow/SKILL.md) | 仓库边界、提交、推送、集成 |
| [技术讨论](../Develop_Helper/harness-core/skills/technical-discussion/SKILL.md)与[复述规则](../Develop_Helper/harness-core/skills/technical-discussion/references/term-learning.md) | 学习闭环；与项目开发分开 |
| [词汇索引](../Develop_Helper/learning/technical-terms/index.md)与[完成记录](../Develop_Helper/learning/technical-terms/glossary.md) | 当前学习、排队和已复述条目 |
| [全局经验](../Develop_Helper/memory/harness-experience.md) | 当前使用边界与历史经验，不把旧规则当新契约 |

## 5. 三个 Python 脚本的实际边界

| 脚本 | 能做 | 不能据此认定 |
| --- | --- | --- |
| [sdd_project.py](../Develop_Helper/scripts/sdd_project.py) | new、onboard、remove、use、current、list；项目元信息与登记 | 业务代码已开发、依赖已安装、服务已启动、远程已推送 |
| [sdd_dispatch.py](../Develop_Helper/scripts/sdd_dispatch.py) | 检查任务依赖、状态、模式和门禁，返回候选 | 子智能体已启动、用户确认真实、AC 语义完整、文件无冲突 |
| [check_harness_consistency.py](../Develop_Helper/scripts/check_harness_consistency.py) | 检查部分框架入口/引用、模板 JSON、Feature 引用和依赖契约 | 所有文档或代码都正确、实际项目计划合理、业务已验收 |

派发脚本是只读资格检查器。调度、等待、记录真实实例、回收结果和写状态都由编排器完成，不存在运行该脚本就自动完成全部项目的后台任务引擎。

测试位于 [scripts/tests](../Develop_Helper/scripts/tests/)：test_sdd_project 测项目生命周期，test_sdd_dispatch 测门禁/模式，test_harness_consistency 测引用/模板，test_pycore_config 测部分配置行为。它们不构成业务项目的验收套件。

## 6. 当前阅读中确认的差异和边界

| 问题 | 原文/实现证据 | 本指南如何解释 |
| --- | --- | --- |
| 旧创建命令缺规范参数 | PACKAGING_NOTES 的 new 示例；sdd_project.main 的 required 互斥参数组 | 使用 02 的完整命令；未选规范不能执行创建 |
| 打包说明提到不存在的 commands 目录 | PACKAGING_NOTES 声称补齐 .codex/commands；当前目录无此项 | 不以旧命令入口作为使用前提，按当前 Router/Skill 入口理解 |
| 模板逐步模式容易被当成默认用户选择 | templates/tasks.json 与 execution-mode | 新计划需选择；仅旧计划缺字段时兼容 automatic |
| 空 write_scope 的表述不完全一致 | Planner 字段表允许空并串行；development-loop 要求派发前补齐，串行不代替范围 | 区分规划草案可未定与实际派发必须明确，不修改原规则 |
| 阶段摘要易被误当自动状态机 | 脚本创建 status.json 和 registry initialized；current 显示登记 status | 开发进度以 tasks 和证据为准，未发现自动同步全部设计阶段的脚本 |
| PyCore 通用入门与本框架接入不同 | getting-started 有 pip 及 api/llm/all extras；当前 pyproject 仅声明 dev extras；default 后端规范要求复制并以 PYTHONPATH 引入 | 通用文档作为人类参考；采用 default 时看当前所选规范和源码 |
| Router 对“帮我”的措辞可能有歧义 | Router 同时要求按预期结果分流，又把“帮我”视为执行请求 | “帮我解释”可能仍是理解请求；此为分析风险，不在本次改路由逻辑 |
| 检查器覆盖范围有限 | reading_files 未纳入 PACKAGING_NOTES、.agents、pycore/docs、memory/learning 全部材料 | 检查 PASS 不能排除上列差异，新指南另行核对链接 |

依据：[打包说明](../Develop_Helper/PACKAGING_NOTES.md)、[模式协议](../Develop_Helper/harness-core/protocols/execution-mode.md)、[Planner](../Develop_Helper/harness-core/agents/planner.md)、[开发循环](../Develop_Helper/harness-core/protocols/development-loop.md)、[PyCore 入门](../Develop_Helper/pycore/docs/getting-started.md)、[包声明](../Develop_Helper/pyproject.toml)、[默认后端规范](../Develop_Helper/harness-core/specification/default/backend/tech-stack.md)。

上述差异中，Router 的误分流是根据文字的分析推断；其他条目由文件和脚本定义直接对照。没有实际运行业务服务，不对 PyCore 整体可用性作结论。

## 7. 默认规范集的 14 份文件

仅当项目选择 default 时使用相应规则；自定义集不隐式继承 default，null 不加载规范集。以下是这套规范的具体约定，不是对所有技术栈的普遍要求。选择机制见 [规范集说明](../Develop_Helper/harness-core/specification/README.md)。

| 组别 | 文件与用途 |
| --- | --- |
| 前端技术 | [tech-stack](../Develop_Helper/harness-core/specification/default/frontend/tech-stack.md)：React/TS/Vite、路由、状态与目录 |
| 前端通信 | [api-client](../Develop_Helper/harness-core/specification/default/frontend/api-client.md)：请求封装、路由保护、代理 |
| 前端模拟 | [mock](../Develop_Helper/harness-core/specification/default/frontend/mock.md)：集中管理，匹配 tech-spec DTO |
| 前端视觉 | [style](../Develop_Helper/harness-core/specification/default/frontend/style.md)：设计底线、状态和布局检查 |
| 前端验收 | [acceptance](../Develop_Helper/harness-core/specification/default/frontend/acceptance.md)：任务范围和验证检查 |
| 后端技术 | [tech-stack](../Develop_Helper/harness-core/specification/default/backend/tech-stack.md)：PyCore、Python 环境、配置、目录和质量工具 |
| 后端工作流 | [workflow](../Develop_Helper/harness-core/specification/default/backend/workflow.md)：分层实施、自验、隔离测试与真实联调 |
| 后端分层 | [layers](../Develop_Helper/harness-core/specification/default/backend/layers.md)：模型、Repository、Service |
| 后端接口 | [api-design](../Develop_Helper/harness-core/specification/default/backend/api-design.md)：路由、响应、错误码、认证 |
| 后端异常 | [error-handling](../Develop_Helper/harness-core/specification/default/backend/error-handling.md)：异常传播与分类处理 |
| 后端插件 | [plugin](../Develop_Helper/harness-core/specification/default/backend/plugin.md)：AI Agent 的工具/插件实现 |
| 共享环境 | [env-policy](../Develop_Helper/harness-core/specification/default/shared/env-policy.md)：前后端配置、端口和存储落点 |
| 共享命名 | [naming](../Develop_Helper/harness-core/specification/default/shared/naming.md)：文件、类、函数、字段等命名 |
| 共享安全 | [security](../Develop_Helper/harness-core/specification/default/shared/security.md)：凭据记录和外部服务调用约定 |

例如 default 规定 Agent 验证端口为前端 5199/后端 8099，用户门禁端口为 5175/8003；后端业务放 backend/src，PyCore 与 backend 并列；业务配置从明确文件加载。这些都是所选规范层的约定，不是 SDD 调度脚本负责实现的能力。

其中 security 的开头仍有“换规范集仍适用”的文字，而规范集总说明明确自定义集不隐式继承 default。阅读时应保留这一原文差异：共同执行协议已有的凭据保护继续适用，default 中特定供应商/库的约束不能因此自动扩展到任意自定义技术栈。本次没有改写该条。

## 8. 平台适配文件怎样读

| 平台 | 根入口 | 角色/技能位置 |
| --- | --- | --- |
| Codex | [AGENTS.md](../Develop_Helper/AGENTS.md) | [.codex/README](../Develop_Helper/.codex/README.md)、[配置](../Develop_Helper/.codex/config.toml)、[角色](../Develop_Helper/.codex/agents/)、[.agents 技能](../Develop_Helper/.agents/skills/) |
| Claude Code | [.claude/CLAUDE.md](../Develop_Helper/.claude/CLAUDE.md) | [.claude/agents](../Develop_Helper/.claude/agents/)、[兼容技能](../Develop_Helper/.claude/skills/) |
| Cursor | [路由规则](../Develop_Helper/.cursor/rules/00-harness-router.mdc) | [.cursor/agents](../Develop_Helper/.cursor/agents/)、[兼容技能](../Develop_Helper/.cursor/skills/) |

四个技能发现/兼容目录里的同名 Skill 主要指回同一个核心文件，不是四套独立工作流。.cursor 中的 phase-A/B/R 也只是适配指针。维护时优先看 harness-core 的正文。

当前 config.toml 写了 max_threads=6 和 max_depth=1，但它只是此文件夹的配置内容，不保证每个实际会话都有相同名额，也不替代运行时能力检查。

原文要求有调度能力时真实派发四种角色，不能用创建用户侧独立聊天任务冒充子智能体。通用子智能体可携带角色文件执行；只有明确不可用时才说明降级。

## 9. 模板与 PyCore 配套资料

任务字段看 [tasks 模板](../Develop_Helper/templates/tasks.json)。新建脚本直接生成 project/status JSON，并读取 [项目 README 模板](../Develop_Helper/templates/project/README.md)、[项目经验模板](../Develop_Helper/templates/project/.sdd/experience.md)、[项目日志模板](../Develop_Helper/templates/project/.sdd/work-log.md)。因此模板文件存在不表示脚本原样复制每个 JSON。

templates 根目录还有经验/日志模板，是配套结构参考，不应再建立另一份执行状态库。设计模板位于相应 Skill 的 references，具体项目内容应生成在业务项目 docs。

PyCore 的人类参考资料如下，理解 SDD 流程无需按每个 API 示例运行一遍：

| 资料 | 说明 |
| --- | --- |
| [总入口](../Develop_Helper/pycore/docs/index.md)、[入门](../Develop_Helper/pycore/docs/getting-started.md)、[示例](../Develop_Helper/pycore/docs/examples.md) | 包结构、通用用法、样例；接入方式仍需核对当前规范 |
| [core](../Develop_Helper/pycore/docs/core.md) | 配置、日志、异常、基础结果模型 |
| [api](../Develop_Helper/pycore/docs/api.md) | FastAPI 服务、路由、中间件和响应 |
| [services](../Develop_Helper/pycore/docs/services.md) | 服务层及生命周期 |
| [execution](../Develop_Helper/pycore/docs/execution.md) | 业务执行上下文与顺序/并行 Flow |
| [plugins](../Develop_Helper/pycore/docs/plugins.md) | 可复用插件及注册表 |
| [llm](../Develop_Helper/pycore/docs/llm.md) | 模型抽象、调用、工具与 Token 相关能力 |
| [配套开发说明索引](../Develop_Helper/pycore/docs/specs/index.md) | API/Core/Plugins/Services 的进一步参考及空配置示例 |

这些文档对应 pycore/core、api、services、execution、plugins、integrations 等源码。它们属于应用基础库，不是 SDD 项目状态引擎；旧示例的接口与依赖需对照源码，不能据文字直接声称已验证。

## 10. 本次整理的范围

新增本目录八篇指南并在根 README 增加入口。保留原核心规则、平台适配、脚本、模板、登记和业务目录的位置，不替换既有实现。

检查包括新增导航的本地目标、Markdown 结构、框架引用与模板检查，以及与流程说明直接相关的现有脚本测试。检查结果在本次交付中报告；它们不证明平台已实际加载全部角色、图已视觉渲染，或业务项目已开发完成。
