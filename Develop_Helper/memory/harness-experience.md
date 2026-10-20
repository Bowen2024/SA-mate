# SDD — 系统级经验

> 记录跨项目可复用、能反哺 Harness 本体的经验。  
> 不记录具体项目的业务细节；项目细节写入 `Projects_Repo/<project-id>/.sdd/experience.md`。

## 当前使用边界

按 [错误与经验闭环](../harness-core/protocols/experience-loop.md)（路径：`<harness_root>/harness-core/protocols/experience-loop.md`）维护。项目经验经验证、有跨项目价值且获得用户授权后，由编排器去重写入；新增条目注明适用条件、源项目条目与证据、验证范围、授权依据。项目原条目回链此处标题。

以下旧条目保留当时的事实记录与规则原文，均已标注为历史参考；本轮没有重新验证其技术结论。不得按其“必须”字样覆盖当前用户要求、项目契约和规范。现行流程按核心协议执行；历史命令、端口、字段、角色权限、前端框架和数值经验不自动迁移到新项目。仅按当前问题检索相关条目，不要求每次全量阅读。

需要把经验转成现行 Skill 或规范时，先提出具体文件变更并按用户授权执行；更新经验本身不让旧规则恢复生效。

---

## 2026-05-11｜移动端项目不得套用 Web 产品设计与 Web Rules

> 状态：历史参考。流程已被取代：按项目类型选择规范或 null，不沿用旧版强制警告、自备全套文档及空 rules_files 规则。

- **来源**：V5 → V6 架构升级讨论
- **经验**：当前 Harness 的产品设计 Skill 和前端规范（原 `dev-standards/frontend.mdc`，现 `specification/<集名>/frontend/`）都偏 Web。移动端项目可以复用多 Agent 协同机制，但不能默认触发 Web 产品设计 Skill，也不能读取 Vue/Web 前端 rules。
- **规则**：
  - 移动端项目必须先警告用户当前缺少移动端规范
  - 用户确认继续后，要求用户自备 PRD / 原型 / API 契约 / Plan
  - 移动端客户端任务 `rules_files=[]`
  - 只有后端 API 任务才读取 backend rules

## 2026-05-11｜Bugfix 必须回查经验并反哺经验

> 状态：历史参考。沉淀流程已被 experience-loop.md 取代：定向检索、复验后判断，按需报告，编排器去重落盘；不是每次必写报告或新增经验。

- **来源**：V6 Bugfix 流程升级
- **经验**：Bugfix 不是单纯修代码，而是经验系统的入口。
- **规则**：
  - 修复前必须读取项目 `.sdd/experience.md`
  - 如果已有相关经验，必须分析为什么仍然犯错
  - 修复后必须写 bugfix 报告
  - 修复后必须更新项目经验

## 2026-05-12｜后端业务任务必须任务内完成前端真实联调

> 状态：历史参考。任务编排已被 development-loop.md 与 planner.md 取代；不恢复 frontendIntegration 字段或强制每个后端任务同时修改前端，真实业务验收仍按实际任务覆盖。

- **来源**：customer-service 自动化 Coding 复盘。项目所有任务显示 passed，但用户打开前端仍看到 Mock 数据。
- **经验**：前端 Mock 是产品交互和接口契约对齐阶段的工具；一旦进入后端业务任务，任务 Done Definition 必须包含“对应前端在 `VITE_USE_MOCK=false` 下调用真实后端”。否则后端只完成了 API，不代表用户功能完成。
- **规则**：
  - Planner 生成 Web 后端业务任务时，必须写入 `frontendIntegration.required=true`
  - 对应已有前端页面或 service 的后端任务，acceptanceCriteria 必须包含真实前端联调标准
  - Developer 完成后端业务功能时，必须同步修正对应前端 service / store / page，不能让默认验收路径继续走 Mock
  - Tester 不得只用 curl/API 判 PASS；必须验证 `VITE_USE_MOCK=false` 路径、真实后端请求和页面无 `[Mock]` 残留
  - 最终 E2E 只做全系统回归，不能替代单个后端业务任务内的首次真实联调

## 2026-05-12｜自动化开发前必须确认外部服务与 Tester 权限

> 状态：历史参考。门禁流程已被取代：不恢复 /sdd-start；缺 Key 时先推进已授权的独立本地工作，真实未验不能通过。

- **来源**：SDD V6 自动化 Coding 复盘。缺少真实服务 Key 时，系统容易用 Mock/fallback 跑完任务并误判为完整联调。
- **经验**：外部服务配置不是后端任务中途才讨论的问题，而是进入多智能体自动化开发前的门禁。否则 Tester 没有完整权限，只能测 Mock/fallback，无法验证真实业务链路。
- **规则**：
  - `/sdd-start` 进入 Planner 前必须先确认外部服务清单
  - 清单必须包含服务名称、用途、配置字段、MVP 必需性、Tester 联调权限、缺失时策略
  - 必要 Key / 测试账号 / Base URL / 回调配置缺失时必须暂停索取
  - 用户明确选择不提供时，相关能力只能标记 Mock/fallback 降级验收
  - 真实 Key 不写入 PRD、Plan、tasks.json、测试报告或经验文件，只写入 `.env`

## 2026-05-21｜后端业务任务必须验证 Vite 开发代理配置

> 状态：历史参考。仅适用于来源项目当时的实现与契约；具体工具、字段、数值和业务规则使用前需按当前项目核对，不作为全局强制要求。

- **来源**：smart-customer-service T-010 用户登录闭环。后端登录接口开发完成，但前端请求始终失败，排查后发现 `vite.config.ts` 未配置 `/api` 开发代理，导致浏览器把请求识别为跨域，OPTIONS 预检异常。
- **经验**：Vite 代理是前后端本地联调的基础设施，不是"有报错才配"的补救措施。Developer 完成后端业务任务时，如果只改了前端 service 但没检查代理配置，Tester 的真实联调会莫名其妙失败，浪费大量时间排查 CORS/端口/中间件等错误方向。
- **规则**：
  - `frontend/vite.config.ts` 必须配置 `server.proxy['/api']` 指向后端端口（默认 `http://localhost:8000`）
  - `frontend/.env` 中 `VITE_API_BASE_URL` 必须使用相对路径 `/api`，禁止写完整 URL（如 `http://localhost:8000/api`）触发 CORS
  - WebSocket 路径 `/ws` 必须单独配置 `ws: true` 代理，前端代码禁止硬编码 `ws://localhost:8000`
  - Developer 输出前必查清单中增加 Vite 代理检查项；Tester 真实联调验证中增加代理配置检查
  - 修改 `vite.config.ts` 或 `.env` 后必须重启 Vite 开发服务器

## 2026-05-22｜固定高度容器的设计必须预留 20% 缓冲空间

> 状态：历史参考。仅适用于来源项目当时的实现与契约；具体工具、字段、数值和业务规则使用前需按当前项目核对，不作为全局强制要求。

- **来源**：customer-service T-003 员工端 Mock 实现。TicketCard 组件使用 `h-20`（80px）固定高度容纳三行文本，经过 5 次 Bugfix（空格、truncate 宽度、leading-tight、仍不够）才发现根本问题是**容器尺寸本身不合理**，最终增加到 `h-24`（96px）解决。
- **经验**：前端固定高度容器（`h-[固定值]`）容纳多行文本时，不能"刚好够用"，必须预留缓冲空间。浏览器实际渲染高度受字体、字重、抗锯齿、line-height 影响，原型工具中的尺寸往往比实际偏小。如果容器高度 = 内容理论高度，实际渲染时极易溢出截断。
- **规则**：
  - **固定高度容器设计公式**：`容器高度 ≥ 内容理论高度 × 1.2`（预留 20% 缓冲）
  - **内容理论高度计算**：`Σ(font-size × line-height × 行数) + Σ(gap) + padding（上下）`
  - **卡片高度经验值**（基于 `text-sm` 14px + `leading-tight` 1.25）：
    - 单行内容：最小 `h-12`（48px）
    - 两行内容：最小 `h-20`（80px）
    - 三行内容：最小 `h-24`（96px）
    - 四行内容：最小 `h-28`（112px）
  - **原型 vs 实际渲染**：Figma/Sketch 原型中的文字高度 ≠ 浏览器渲染高度，必须在真实浏览器中验证
  - **优先使用 `justify-between`**：固定行数（如 3 行）时，用 `justify-between` 替代固定 `gap`，让内容自动均匀分布更可靠
  - **Developer 输出前必查**：固定高度容器必须在浏览器中实际验证文字是否完整显示（上下不被截断）
  - **Tester 验证标准**：使用浏览器开发工具检查元素计算后的 `height`，确认内容高度 < 容器高度 × 0.85
  - **Bugfix 诊断清单**：文字被垂直截断（只显示上半部分）→ 不只是调整 `line-height`，还要评估**容器高度是否合理**

## 2026-08-27｜登录/表单页必须逐字对照原型，且演示文案可走通

> 状态：历史参考。仅适用于来源项目当时的实现与契约；具体工具、字段、数值和业务规则使用前需按当前项目核对，不作为全局强制要求。

- **来源**：智能客服机器人 T-001 Tester 验证
- **类型**：规范/对齐
- **经验**：登录页未逐字对照原型（placeholder、底部说明缺失）；补上底部说明后仍未同步 Mock 登录名，用户按页面说明无法登录。
- **规则**：
  - Developer 完成登录/表单页后，必须对照原型 HTML 逐字段核对 placeholder、按钮文案、底部说明与 alert 文案
  - Tester 用 Playwright 抓取可见文本与 placeholder 属性做 diff
  - 添加原型演示说明后，必须用说明中的每个登录名实测登录；`mockLogin` 匹配须与原型 JS 或 api-contracts 示例 `login_name` 一致
  - Developer 完成登录页后，用演示文案中的登录名逐条跑 AC，不只测 `mocks/users.ts` 里的内部字段

## 2026-08-27｜转人工可用性必须绑定当前会话工单

> 状态：历史参考。仅适用于来源项目当时的实现与契约；具体工具、字段、数值和业务规则使用前需按当前项目核对，不作为全局强制要求。

- **来源**：智能客服机器人 T-002 Tester 验证
- **类型**：对齐/业务规则
- **经验**：转人工可用性误用员工级 `hasTicket(employeeId)`，与「同一会话最多一张工单」冲突，导致有历史工单的员工在新会话无法转人工
- **规则**：Mock/前端 `can_escalate` 必须绑定 `conversation.ticket_id`，禁止用员工全局工单数禁用当前会话转人工；Tester 用「有历史工单 + 新进行中会话」用例覆盖转人工可用

## 2026-08-28｜Mock 对话页必须实现本地发送/转人工状态机

> 状态：历史参考。仅适用于来源项目当时的实现与契约；具体工具、字段、数值和业务规则使用前需按当前项目核对，不作为全局强制要求。

- **来源**：service-robot T-002 Tester 验证
- **类型**：重复/对齐
- **经验**：Mock 阶段将发送/转人工留空为 alert，且 query 场景缺 rag，导致多条 AC 无法通过静态+交互验证。第 2 轮仅调整左栏顺序后，Outlook 时间仍因 `formatTime(updated_at)` 显示 09:40，与原型 09:12 不符。
- **规则**：Developer 完成 EmployeePage 一类对话 Mock 时必须实现本地 `handleSend`/`handleTransfer` 状态机，并覆盖 tasks.json 列出的全部 `?state=` 场景（含 rag）；禁止以 alert 代替 Mock 交互。对照原型验收左栏时间时，必须静态计算 `formatTime` 输出并与原型逐字比对；须反推应使用的 UTC 字段（`created_at` / `claimed_at` / `closed_at` / `updated_at`），不得只核对 Mock 字段字面量或只改数组顺序。坐席端处理中分组应用 `claimed_at`（如原型「今天 14:08」），不要误用 `created_at`。

## 2026-08-28｜backend 脚本必须在 `PYTHONPATH=..` 下能导入 `src`

> 状态：历史参考。仅适用于来源项目当时的实现与契约；具体工具、字段、数值和业务规则使用前需按当前项目核对，不作为全局强制要求。

- **来源**：service-robot T-007 Tester 验证
- **类型**：框架/脚手架
- **经验**：`cd backend && PYTHONPATH=.. python3 scripts/init_db.py` 时 `sys.path[0]` 是 `scripts/`，项目根只有 `pycore` 没有 `src`，导致 `ModuleNotFoundError: No module named 'src'`。配置路径若按项目根写 `backend/.env` 也会在 backend cwd 下解析错。
- **规则**：要求 `cd backend && PYTHONPATH=..` 的脚本必须把 `backend/`（脚本的上一级）插入 `sys.path`，数据和 `.env` 相对 `backend/` 解析；禁止注释写一种 CWD、实现假设另一种。

## 2026-08-28｜uvicorn 启动必须调用 init_config，不得只靠 pytest 夹具

> 状态：历史参考。仅适用于来源项目当时的实现与契约；具体工具、字段、数值和业务规则使用前需按当前项目核对，不作为全局强制要求。

- **来源**：service-robot T-010 Tester 验证
- **类型**：框架/对齐
- **经验**：`src.main` 未调用 `init_config()` 时，真实 uvicorn 下依赖 `get_db`/`get_settings` 的路由 HTTP 500，而 pytest 夹具注入配置造成假阳性。
- **规则**：后端 integration 合并前必须用文档规定的 uvicorn 命令做一次真实 POST 冒烟；`main.py` 启动路径必须 `init_config()`；Tester 不得仅依赖 ASGITransport + dependency_overrides 判 PASS。相对路径必须统一相对 `backend/` cwd（与 init_db 一致），禁止再写 `Path("backend")/data/...`，否则 uvicorn 从 backend 启动时意图规则文件找不到，RAG 会误报 llm_unavailable。

## 2026-08-28｜错误必须扁平信封；切片循环必须有终止条件

> 状态：历史参考。旧 {code,message,data} 信封仅是源项目契约；当前项目按已确认接口与所选规范处理，切片结论按实际实现核对。

- **来源**：service-robot T-011 Tester 验证
- **类型**：框架/规范
- **经验**：`HTTPException(detail=dict)` 被 FastAPI 包成 `{"detail":{...}}`，与 api-contracts `{code,message,data}` 及前端解析不一致。短文档 `split_into_chunks`  overlap>=step 时死循环，真实百炼抽 QA 成功后入库挂起。
- **规则**：在 `main.py` 注册异常 handler，错误 JSON 必须是 `{code,message,data}`。字符切片必须保证前进（step>0 且 overlap<chunk_size），短文本也要能结束。

## 2026-08-28｜.env 多行模板必须单行，FTS 不得用改写标题

> 状态：历史参考。仅适用于来源项目当时的实现与契约；具体工具、字段、数值和业务规则使用前需按当前项目核对，不作为全局强制要求。

- **来源**：service-robot T-012 Tester 验证
- **类型**：对齐/重复
- **经验**：`.env` 多行 `QUERY_REWRITE_TEMPLATE` 未加引号时 dotenv 只读首行 `## 意图`，FTS5 把 `#` 当语法导致检索失败，整条 RAG 误报 llm_unavailable。
- **规则**：多行模板写入 `.env` 必须单行 `\n` 或引号包裹；真实 RAG 验收须断言 rewrite/query 长度大于标题首行；FTS5 查询使用用户原问题，改写失败回退原文。

## 2026-08-28｜RAG 后置画像不得拖垮已生成答案；FTS 必须转义

> 状态：历史参考。仅适用于来源项目当时的实现与契约；具体工具、字段、数值和业务规则使用前需按当前项目核对，不作为全局强制要求。

- **来源**：service-robot T-012 Tester 验证
- **类型**：重复/对齐
- **经验**：`intent_rules.json` 的 `profile_issue_domain_rules` 是列表，代码却调用 `.items()`，检索+生成成功后崩溃，整段被 catch 成 `llm_unavailable`。用户问题含 `.` 时 FTS5 语法错误同样拖垮 pipeline。profile/FTS 修好后，`no_knowledge` 仍不可达：0.3 向量阈值无法过滤 0.4+ 弱相关切片，库外问题仍走 `rag` 并可能编造答案。
- **规则**：真实联调验收 RAG 必须用一条不命中 QA 直出的问题断言 `reply_kind=rag`。profile/后置步骤异常不得吞掉已生成答案。FTS MATCH 须转义或隔离失败；配置 JSON 结构必须与遍历代码一致。验收 `no_knowledge` 必须用库外具体问题断言 `reply_kind=no_knowledge`（不能只 mock 空检索）；向量阈值须用真实 embedding 分数标定。

## 2026-08-28｜integration 双端页面必须各自退出 Mock

> 状态：历史参考。旧 frontendIntegration.pages/defer 字段不恢复；按当前 tasks 与 PRD 核对需要真实联调的页面。

- **来源**：service-robot T-014 Tester 验证
- **类型**：对齐
- **经验**：`frontendIntegration.pages` 含 `/employee` 与 `/agent` 时，Developer 只把 EmployeePage 转人工接到真实 API，AgentPage 待接列表仍走 Mock，AC 要求坐席端看见新单无法在 `VITE_USE_MOCK=false` 下成立。
- **规则**：Tester 必须逐页检查 `frontendIntegration.pages`；任一页默认仍走 Mock 则 FAIL。Developer 不得把对端页面推迟到后续任务，除非 tasks.json 明确 defer。
