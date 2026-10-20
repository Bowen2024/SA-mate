# 修改与继续项目

进入前由 project-management 确定目标项目的 `active_project_path`。本文件只分流当前工作，读取命中的阶段即可，不重新创建项目或重复选择规范。

## 继续当前工作

结合本次请求，检查必要的文档状态和现有确认记录：

- 需求尚未形成或 PRD 为 `Draft`：进入 [需求与验收](../../sdd-product-design/phase-A.md)。不因用户提到界面就提前制作原型。
- PRD 已确认，技术方案缺失或为 `Draft`：进入 [七层技术方案](../../solution-design/SKILL.md)。
- PRD、技术方案均已确认，有新建或待调整界面：先进入 [界面设计](../../sdd-product-design/phase-B.md)，复用已有确认，只完成本轮需要的设计。
- PRD、技术方案及本轮必要界面设计均已确认，用户要求开发或继续任务：进入 [开发循环](../../../protocols/development-loop.md)，复用现有任务状态和授权。
- 用户只询问进度时，读取 `.sdd/tasks.json` 的状态及证据摘要回答；未进入开发时说明当前设计阶段，不因此启动任务。

明确的当前请求优先于旧状态。文件存在不代表内容已确认；已有会话确认可以复用，不要求用户重复确认。

## 修改当前项目

- **仅初始化 Git、管理分支、提交、推送或合并**：进入 [Git 工作流](../../git-workflow/SKILL.md)，沿用当前项目和授权，不为 Git 操作重跑需求或开发规划。

- **新增功能、改变流程或验收结果**：进入需求与验收，只更新 PRD（路径：`<active_project_path>/docs/PRD.md`）受影响功能；再更新技术方案（路径：`<active_project_path>/docs/tech-spec.md`）中对应的接口、算法或异常设计。
- **需求不变，只调整技术实现或接口约定**：进入七层技术方案流程，修改 tech-spec（路径：`<active_project_path>/docs/tech-spec.md`）的相关章节；普通实现细节可在已确认约束内直接处理。
- **功能不变，只调整界面风格或布局**：进入按需原型分支，更新 `docs/ui-style.md`（路径：`<active_project_path>/docs/ui-style.md`）及相关原型（路径：`<active_project_path>/docs/prototypes/` 下的实际文件）；PRD（路径：`<active_project_path>/docs/PRD.md`）仅更新必要的页面引用，不重做技术方案。
- **修复与已确认结果不一致的问题**：进入 [Bug 修复](../../sdd-bugfix/SKILL.md)，定位、修复并验证，不重跑整套设计。

范围、验收或契约改变时，将受影响的设计文档标为 `Draft`，更新并确认后交开发循环调整相关任务。保留任务历史；受影响的已通过任务及必要下游任务需要重新验收。

已有旧版设计文档时，优先读取本次相关内容，必要时将已确认结论整理到 PRD（路径：`<active_project_path>/docs/PRD.md`）/ tech-spec（路径：`<active_project_path>/docs/tech-spec.md`）并保留原文档。缺少新版标题不是重建整个项目的理由；不自动删除历史产物，不把旧版本的接口或确认凭空当成新版结论。
