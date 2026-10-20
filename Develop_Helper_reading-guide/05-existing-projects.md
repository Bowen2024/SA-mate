# 05 已有项目、变更与异常恢复

[阅读目录](README.md) · [上一篇](04-execution-and-gates.md) · [下一篇：完整实例](06-walkthrough.md)

## 1. 找到本次目标

定位顺序是：用户明确指定 → 当前会话已确定 → 注册表中的活动项目。用户指定的项目不能被旧 active_project_id 替换。

登记、实际目录和 `.sdd/project.json` 身份一致，才认定为对应已纳管项目。确定 active_project_path 后，不必为本次操作先切换全局活动项目。目录存在本身不表示已经纳管；当前框架仅纳管 Projects_Repo 的直接子目录。

## 2. 接入已有项目

| 情况 | 方式 | 核对内容 |
| --- | --- | --- |
| 原项目在框架外 | 默认建议复制、保留原目录，由用户确定 | 名称、ID、类型、规范、origin、目标路径 |
| 已在目标目录但未登记 | register，只补元信息 | 目标身份、无冲突的 .sdd 信息 |
| 已登记且一致 | 直接继续/修改 | 不重复复制或创建 |
| 有旧 .sdd | 核对并保留，必要时在副本归档后登记 | 记录来源与可沿用证据 |

授权后使用 onboard。复制跳过常见依赖和缓存，保留业务代码、文档和普通独立 Git 仓库等。符号链接仍为链接；Git worktree 的 .git 文件需先处理为明确的独立副本。

纳管不替换技术栈，不复制默认 PyCore，不自动重写原 README/AGENTS，也不把旧 PASS 当当前验收。接入后沿用已有需求、方案和界面，只补当前缺口。

依据：[纳管流程](../Develop_Helper/harness-core/skills/project-management/references/onboard-project.md)。

## 3. 继续从哪里恢复

| 当前事实 | 进入位置 |
| --- | --- |
| 需求未形成或 PRD Draft | A：需求与验收 |
| PRD 确认，方案缺失或 Draft | 七层技术方案 |
| 前两者确认，本轮界面需设计 | B：风格与按需原型 |
| 设计齐备且有开发意图 | 开发循环，沿用 tasks 和授权 |
| 只询问进度 | 读状态与证据回答，不启动开发 |

当前请求优先于旧状态。文件存在不等于确认，真实会话确认可以沿用。

## 4. 按修改影响分流

| 要求 | 修改路径 | 已通过任务 |
| --- | --- | --- |
| 新功能、流程或验收变化 | PRD → 相关方案 → 必要界面 → 相关任务 | 受影响任务及必要下游复验 |
| 需求不变，接口或重要技术约定变化 | tech-spec 相关层，必要决策记录 | 调整依赖/检查，说明证据版本 |
| 功能不变，只改布局/风格 | ui-style、相关原型和页面 | 定向验证实际画面和交互 |
| 行为偏离已确认要求 | Bugfix → 修复 → Tester 复验 | 记录原任务或工作日志 |
| 只做 Git 操作 | Git Skill | 不改变业务验收状态 |

范围、AC 或契约实质变化时，受影响文档回 Draft，更新并确认，再调整任务。普通实现细节在已确认约束内决定，不增加常规审批。

旧文档缺新版标题、旧任务缺 features，不是重做或强制迁移整个项目的理由。原编号、记录与成果优先保留。

依据：[修改与继续](../Develop_Helper/harness-core/skills/project-management/references/modify-project.md)。

## 5. 独立 Bug 的闭环

1. 明确触发动作、实际与预期，优先使用已确认要求和 AC。
2. 定向读取相关需求、接口和代码，检索项目经验，复现并区分已证实原因与推测。
3. 修复当前缺陷；若要改变需求或契约，交主智能体更新方案。
4. 修复者自验，返回改动、根因证据、适用条件、预防办法和经验建议。
5. Tester 复验原问题及直接影响路径，不能改 AC 让错误实现通过。
6. 编排器记录事实：有任务写 notes，无任务写工作日志，长证据才保存报告。
7. 复验后判断复用价值，去重更新项目经验，或记录不新增原因。

未复验修复、未证实根因不沉淀为已验证经验。经验候选证据不足，只暂缓沉淀，不自动否定已满足 AC 的功能。跨项目经验须获授权再写全局；历史记录的“必须”不覆盖当前项目要求。

依据：[Bugfix](../Develop_Helper/harness-core/skills/sdd-bugfix/SKILL.md)、[经验闭环](../Develop_Helper/harness-core/protocols/experience-loop.md)。

## 6. 中断、Stopped 与 BLOCKED

| 情况 | 恢复判断 |
| --- | --- |
| 会话结束，仍 in_progress | 查真实实例和已有成果，避免重复写同任务 |
| 智能体 Stopped | 查结束原因；它不自动表示 PASS/FAIL |
| 编码齐备、只缺测试 | 复用实现，恢复 testing |
| 有局部成果、仍需编码 | 带原任务和成果继续，不从零重做 |
| 缺必要服务或权限 | 可做部分完成后 blocked，写未验 AC 与恢复条件 |
| 返工额度耗尽 | 保留次数与失败证据，等待明确决定 |
| 用户暂停或取消 | 停止新派发，不自动恢复终止实例 |

实例 ID 来自真实调用，无法核实时说明未知，不编造已派发记录。名额满时等待释放，不代表平台没有调度能力。重启实例也不清零返工次数。

依据：[子智能体协议](../Develop_Helper/harness-core/protocols/codex-subagents.md)、[开发循环](../Develop_Helper/harness-core/protocols/development-loop.md)。

## 7. 重置与 Git

重跑测试不等于删除项目。清测试数据只清明确范围；重跑阶段保留上游产物和旧证据；完整移除先停止属于该项目的服务，再可恢复地移到框架外备份并移除登记。

remove 脚本不负责停服务，不操作远端。只有用户同时要求重新创建才再走创建流程。

Git 操作核对实际仓库根、分支、remote 和本轮差异，避免把 Harness 仓库误当业务仓库。继续开发、自动模式不自动授权提交、推送或合并；明确持续授权可以沿用。

依据：[移除与重置](../Develop_Helper/harness-core/skills/project-management/references/remove-reset-project.md)、[Git 工作流](../Develop_Helper/harness-core/skills/git-workflow/SKILL.md)。

## 8. 技术讨论独立进行

原框架的名词学习链为：登记 → 解释与项目对比 → 用户复述 → 核对理解 → 保存 → 下一名词。index 记录待讲解、待复述和已完成；glossary 保存实际复述通过后的记录。

普通报错解释或框架维护不套名词复述门槛，学习也不阻塞无关项目任务。这里是说明原 Skill，不表示读本指南需要参加复述测试。

依据：[技术讨论](../Develop_Helper/harness-core/skills/technical-discussion/SKILL.md)、[学习规则](../Develop_Helper/harness-core/skills/technical-discussion/references/term-learning.md)。
