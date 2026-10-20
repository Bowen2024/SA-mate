# 02 新项目完整流程

[阅读目录](README.md) · [上一篇](01-overview.md) · [下一篇：角色与文件](03-roles-and-artifacts.md)

本篇解释从零创建项目的标准路线。已有项目不必重走全部步骤，见 [05](05-existing-projects.md)。

## 0. 路由：明确这是一次新建

输入是自然语言要求与已有资料。Router 判断预期结果是技术讨论还是项目工作；项目管理再识别新建、继续、纳管或移除。

确定新建后，由产品设计入口统一收集基础信息。它不会先要求你在空注册表中选择项目。用户只要求讨论方案时也不会创建项目。

结束条件：新建意图明确。依据：[项目管理](../Develop_Helper/harness-core/skills/project-management/SKILL.md)。

## 1. 选择规范、确认身份、创建项目

### 用户需要确定什么

| 项目 | 处理方式 |
| --- | --- |
| 名称和用途 | 用户说明；缺失时补问 |
| ID | 沿用用户提供的 ID，或 AI 根据名称建议后确认 |
| 类型 | web、mobile、api、cli；按用途识别，App 明确目标平台 |
| 本地路径 | 由 ID 推导为 Projects_Repo 的直接子目录 |
| 远程仓库 | 给已有地址或明确暂不配置，不自动创建远端仓库 |
| 规范 | default、自定义集名称、或明确不使用规范集 |

default 适用栈是 React + TypeScript + Vite 前端和 Python 3.11+ + FastAPI + PyCore 后端。API 只采用相关部分；CLI 和移动端不自动套 Web 栈。

没有选择与 JSON `null` 不同：前者是缺决定，后者是已决定不加载规范集。null 仍要完成需求、方案、开发和真实验收，只是任务的 `rules_files=[]`。

### AI 做什么

定向检查注册表和目标路径是否被占用，再调用项目脚本。用户已明确要求创建，信息齐全且无冲突，就不再加一次“授权创建”。

以下是框架根目录下执行的假设命令，仅为说明，不会因阅读而自动执行：

```bash
# 已确认采用 default 的 Web 项目
python3 scripts/sdd_project.py new file-helper --name "文件处理助手" --type web --specification default

# 替代选项：不使用规范集，与上一条只选一种
python3 scripts/sdd_project.py new file-helper --name "文件处理助手" --type web --no-specification
```

两个规范参数必须且只能选一个。已提供远程地址时才增加 `--repo-url`；脚本只配置本地 origin，不推送、不创建远端仓库。

### 产物与结束条件

脚本生成项目目录、`.sdd/project.json`、`.sdd/status.json`、工作日志和经验模板、轻量 AGENTS 入口、README，以及 docs、测试报告等目录；登记并设为活动项目。只有新建且选 default 时复制 PyCore。

这一步不生成完整 PRD、tech-spec、tasks.json 或业务功能，也不表示所有开发依赖已经安装。

核对脚本退出结果、实际路径、登记和项目身份；若配置了 origin，还要验证实际 Git 配置。创建已完成但 origin 设置失败时，应修复残留状态，不重复 new。

依据：[产品设计入口](../Develop_Helper/harness-core/skills/sdd-product-design/SKILL.md)、[项目脚本](../Develop_Helper/scripts/sdd_project.py)。

## 2. A：把想法转成可验收需求

**输入：**用户目标、场景、材料和项目身份。

主智能体逐步确认谁使用、当前如何处理、目标流程、角色交接、权限与数据归属、本次做与不做什么、成功和关键失败的表现。用一个具体例子走完整条链，避免把一句需求直接扩成定稿。

每项需求用 REQ 编号；每条验收用全项目唯一 AC 编号。AC 写前置条件、动作、可观察结果和验证方法。它表达用户结果，不提前拆开发包。

例如“支持文件转换”过于抽象；“提交支持格式文件后取得包含可提取正文的结果；不支持格式得到明确提示”才方便验收。具体格式与限制必须来自项目决定，不能照抄示例。

**产物：**`docs/PRD.md`，包含目标、流程、范围、REQ/AC、业务流程图、业务时序图、必要界面约定、待确认项。

**结束条件：**主流程、角色、范围与关键验收明确，同时具备两类图；用户整体确认后标为 Confirmed。已有确认可沿用。此时不生成 Feature/Task，也不提前用页面代替产品决策。

依据：[A 阶段](../Develop_Helper/harness-core/skills/sdd-product-design/phase-A.md)。

## 3. R：按需调研后回到 A

定位、范围或关键交互需要外部参考，或者用户明确要求竞品调研时，A 可以进入 R。先限定要支持的决策，再查候选产品、官方流程、能力边界和交互说明，通常少量可比产品即可。

原规范限定使用已有网页搜索/正文读取能力，不要求安装浏览器或自动化抓取。未核实的部分标未知，官方事实、第三方观点和本项目建议分开。

**产物：**对话中的比较和建议；用户采用的结论及来源回写 PRD，再返回 A。只有用户要求独立报告才生成 `docs/research.md`。R 不是每个项目必经阶段。

依据：[R 阶段](../Develop_Helper/harness-core/skills/sdd-product-design/phase-R.md)。

## 4. 七层技术方案：把产品承诺转成实现契约

PRD 确认后，主智能体实际派发 Solution Designer，传入项目绝对路径、设计范围、PRD、规范选择和允许改动文档。

| 层 | 需要明确的内容 | 下游用途 |
| --- | --- | --- |
| 1 用户结果 | REQ/AC 与输入到输出的链路 | 确保方案覆盖承诺 |
| 2 前后端与接口 | 分工、Method/URL、字段和类型、完整成功/失败示例 | 前端 Mock 和后端共用契约 |
| 3 数据 | 格式、校验、单位、可空性、实体关系与生命周期 | 字段、存储和算法衔接 |
| 4 模型与提示词 | 模型职责、系统提示词、动态输入、输出约束、工具边界 | AI 项目确定真实调用，无模型则不适用 |
| 5 算法 | 校验、处理、状态变化、返回、逐接口体验分析 | 描述内部如何完成，而非只列字段 |
| 6 异常 | 错误、超时、断连、重试、降级、清理、用户反馈 | 关键失败 AC 有实现路径 |
| 7 本地结构 | 目录、环境、配置、外部服务与验证条件 | Planner 明确依赖和阻塞 |

接口用 API 编号关联 REQ/AC，一个需求不一定只对应一个接口。

影响结果质量、等待、费用、恢复、留存或权限的取舍，由主智能体转达给用户。例如“断开连接后后台继续还是终止”，会改变用户重试时的结果，应明确选择。普通命名、内部函数和不改变约定的代码分层可由智能体决定。

有重要取舍时才建立 `docs/decisions.md`，保存选项、影响、建议、选择和确认依据。确认后的实现写回 tech-spec；若用户结果变了，同步受影响 PRD/AC。

完成前还要细化 PRD 的时序图：加入实际前后端、模型、存储或外部服务、API 编号、同步/异步/流式及关键失败反馈；流程图与文字保持一致。

**产物：**`docs/tech-spec.md`，必要时 decisions.md，以及更新后的 PRD 图。

**结束条件：**关键验收有实现路径、重要取舍已定、图文一致，用户整体确认方案。未决定的关键分支不能标为定稿。

依据：[方案 Skill](../Develop_Helper/harness-core/skills/solution-design/SKILL.md)、[七层模板](../Develop_Helper/harness-core/skills/solution-design/references/tech-spec-template.md)。

## 5. B：设计界面风格与按需原型

本轮有新建或待调整界面时进入；API/CLI 跳过，已有界面无需调整也可跳过。

依据 PRD 和方案确定页面、导航、动作和业务状态，再由 UI Skill 形成 `docs/ui-style.md`：目标、配色字阶、组件、每页信息层级、布局、滚动、窄屏表现和示例文案。

需要可视化确认重要交互，或用户明确要求原型时，才生成 `docs/prototypes/` 的实际文件。简单界面可只交风格与页面说明，不强制做原型。

若制作原型，必须实际检查直接访问、刷新、导航、主流程、失败反馈、长内容和适配宽度。源码检查不替代画面与交互验证；原型不表示真实后端已实现。

**结束条件：**本轮风格文档和已有原型共同提交用户确认一次，相关设计标 Confirmed。发现业务或接口变化时，返回对应章节更新，不整套重问。

依据：[B 阶段](../Develop_Helper/harness-core/skills/sdd-product-design/phase-B.md)、[UI Skill](../Develop_Helper/harness-core/skills/ui-design-standard/SKILL.md)。

## 6. Planner：拆出能实现、能验收的完整计划

首次规划前主智能体确认推进模式，实际派发 Planner。模板中的 step_by_step 不是用户选择。

Planner 提取全部业务 AC，按用户能力组织 Feature，再拆前端、后端、联调等任务。每项明确产物、依赖、优先级、写入范围、技术检查、要读的章节和外部条件。

必须做两种推演：

1. 只用本任务与已通过前置任务，能否验收？若需要未来产物，调整拆分或依赖。
2. 缺 Key 时哪些本地能力仍可独立实现和验证？无关能力不应被一起阻塞。

有前端时，最后一个前端任务设置整体 Mock 收口和用户门禁。每轮完整计划末尾安排功能导航交付任务。前后端初始化并入各自首个使用它的任务，不先做一个承担所有基础设施的大任务。

**产物：**`.sdd/tasks.json`，首次一次形成完整任务清单。主智能体复核后，有按确认方案开发的授权则推进；只请求规划时，交清单后等待开发请求。

依据：[Planner](../Develop_Helper/harness-core/agents/planner.md)。

## 7. Developer / Tester：逐任务留下实现与证据

每次派发前，主智能体检查模式、门禁、依赖、在途实例、写入范围和资源冲突。Developer 仅实现当前任务并自验；Tester 独立按 AC 和 technicalChecks 验证。

Tester 返回 PASS/FAIL/BLOCKED；编排器维护状态。FAIL 按额度定点修复，BLOCKED 保留已完成部分和恢复条件。完整状态机见 [04](04-execution-and-gates.md)。

## 8. 用户验收 Mock，补配置，再真实联调

有前端时，全体前端技术验收通过触发项目级暂停：用户实际检查 Mock，并完成必要后端配置和真实调用授权。在途后端可收尾，不再补派新开发、测试或修复。

界面认可和必要配置两项齐备才放行；无外部服务则明确记录“不适用”。放行后通过真实链路验证证明用户操作经过后端、持久化或必要外部服务。

## 9. 最终交付

本轮必要任务、业务 AC 和最终工作区证据齐备后，delivery 任务由 Developer 实现、Tester 验收。产出 `docs/project-console.html`，必要时有 `docs/project-map.json`，README 提供运行和刷新方式。

导航按页面/入口解释功能触发、输入输出、流程、接口、算法、参数、工具及实现来源。API/CLI 项目使用实际入口，不编造业务页面。它是派生说明，不维护第二份任务进度。

逐步模式下最终任务仍需用户确认。必要 AC 未验或任务仍 blocked，只能说明已完成部分。Git 提交、推送、合并、发布按各自授权进行，任务通过不自动执行这些操作。

依据：[交付协议](../Develop_Helper/harness-core/protocols/project-delivery.md)、[开发循环](../Develop_Helper/harness-core/protocols/development-loop.md)。
