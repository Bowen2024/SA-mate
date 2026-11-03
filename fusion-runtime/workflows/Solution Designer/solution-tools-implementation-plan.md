# 步骤 4：方案工具契约与确认链实施说明

> 发布说明（2026-11-03）：本规格保留原接口与保护要求；角色工具已经实现，本次验证范围见发布记录。正文中原建设状态按原日期理解，建设管理材料未收录。

日期：2026-11-01（Asia/Shanghai）。文档版本：v1.2 实施准备稿。工具契约标识仍为 solution-tools-v1。本稿已补齐步骤 5 的准确修改范围、分段完成条件、测试清单和 Fizz／Honey 执行入口；尚未派发或实施。本文中的接口、参数和保障是建设目标；示例均为说明数据，不代表真实调用或正式确认。

本说明承接建设计划（建设期引用未收录：`solution-designer-construction-plan.md`）第 9—11、14 节。唯一方案角色入口仍为 [solution-design.md](solution-design.md)，文件操作行为仍按 [agent-file-workflow.md](agent-file-workflow.md)。本文维护工具字段、内部依赖和实现验收口径，不另建方案角色，不复制七层方法。

实施与独立验收共同使用[详细测试清单](solution-tools-test-checklist.md)。Fizz 手册（建设期引用未收录：`../../../fusion-design/agent-rule/FIZZ_DEVELOPMENT_RUNBOOK.md`）与 Honey 手册（建设期引用未收录：`../../../fusion-design/agent-rule/HONEY_VERIFICATION_RUNBOOK.md`）仅保留职责和执行入口。建设内容、范围和交付以本文为准，测试操作与判定以清单为准，两份手册不重复维护；冲突时定位对应条件，不由任一角色降低标准取得通过。

## 1. 本步骤要交付什么

本步骤把行为草案收敛为可实施契约，回答六个问题：

1. 三个工具分别收什么、返回什么，何时允许保存？
2. `project_path` 如何绑定持久项目身份，怎样拒绝越界或错项目？
3. `read_id` 保护哪些文件，哪些材料只有读取记录，没有版本保护？
4. 保存前、锁内和写后分别核验什么，失败如何报告？
5. requirements、foundation、两个方法入口和客户端配置怎样连接？
6. 真正有效的 PRD 用途确认从哪里产生，当前缺口如何补验？

本轮文档交付不实施 MCP、保存内核、确认写入、客户端安装或业务项目修改。步骤 4 的文档完成与步骤 5 的代码实现、步骤 7 的独立验收、步骤 8 的真实客户端及确认链通过分别记录。

### 1.1 固定的首版取舍

| 项目 | 契约候选 |
| --- | --- |
| 工具面 | 两个只读工具、一个按启动开关开放的 Draft 保存工具 |
| 服务形态 | 独立 stdio MCP；共享项目入口，每次调用显式选择项目 |
| 服务代码 | 本目录 `mcp_server.py`、`file_tools/solution.py`，必要时拆出本地只读依赖采集模块 |
| 配置辅助 | 本目录 `configure_client.py`；首版实现 Cursor JSON 配置预览／应用算法，其他客户端只输出人工接入说明 |
| foundation | 明确指定兄弟 requirements 目录，复用其本地基础模块及配置 |
| 方法与模板 | 本目录入口；双方法入口必须解析到同一份已锁定上游 |
| 业务写入 | `docs/tech-spec.md` 与其内容寻址历史，及必要的临时文件／锁 |
| 正式确认 | 只读校验既有持久记录；不签发、不登记、不发送、不启动下游 |
| 历史恢复 | 读旧稿，核对当前条件，作为新候选保存；没有直接覆盖式恢复工具 |
| 实施顺序 | 先依赖与读取，再检查，再保存，再配置辅助；真实接入后验 |

首版不提供项目初始化、默认项目、任意文件读写、确认布尔开关、自动修补 PRD、自动选规范、方案正式确认或下游启动工具。保留现有 requirements 服务。

## 2. 事实基线与需要适配的差异

### 2.1 当前实际存在的基础

| 事实 | 对本次实施的影响 |
| --- | --- |
| requirements 的实际 MCP 入口是 `cursor_mcp.py` | 参考其工具目录、读取凭证、共享项目绑定模式；不引用不存在的 requirements/mcp_server.py |
| requirements 当前 `read_id` 保护四份上下文文件，恢复附件不加入凭证 | 方案必须建立自己的集合，不能复用需求进程凭证 |
| `recovery.verify_prd_confirmation` 已返回 valid／missing／outdated／invalid／unavailable | 复用其分类语义和本地校验器，不迁入旧确认写入模块 |
| `artifact_records.validate_registry` 遍历全部登记条目和版本 | 依赖集合要包含其实际可能读取的内容、清单和成员，不能只保护当前 PRD |
| 旧 solution 内核有公共锁、方案锁、历史与原子替换 | 提取适配，补目录绑定、凭证、来源保护、写后核对与结果分类 |
| 旧检查器采用正则与关键词，部分 Lite 章节可省略 | 按当前本地统一模板补齐 0—12 章节与覆盖检查，不照搬旧简化口径 |
| requirements 的 `config/local.json` 当前缺失 | 隔离开发使用临时配置；真实安装不能从 example 空映射直接覆盖 |
| 两个 methods 链接与本地工程模板已经建立 | 校验入口、来源与摘要，不另复制上游方法或生成第二份锁 |

以上是本轮源码只读核对结果，不等于已运行新工具或已复跑历史验收。

### 2.2 不可混用的四个结论

| 结论 | 证明内容 | 不能推出 |
| --- | --- | --- |
| 结构检查完成 | 对指定内容版本完成有限机器检查 | 业务正确、模型效果通过、图表可渲染 |
| PRD 确认 valid | 当前项目、准确 PRD、精确用途与登记／快照满足持久记录契约 | 方案本身已确认、允许开发 |
| Draft 保存成功 | 本次方案写入与指定写后核对完成 | 正式确认、登记、交接或下游启动 |
| 下游采用 | 另行针对准确方案版本、用途和执行范围处理 | 不能由前三项自动触发 |

工具返回禁止笼统的 `approved=true` 或 `ready_for_development=true`。方案文件始终为 Draft、`approval_verified=false`。

## 3. 服务启动、能力和共享模块

### 3.1 拟定启动参数

```text
python -B <方案目录>/mcp_server.py --foundation <requirements绝对目录>
python -B <方案目录>/mcp_server.py --foundation <requirements绝对目录> --allow-save
```

以上是未来 CLI 形态，当前文件不存在，不作为可执行命令交付。

| 参数 | 要求 |
| --- | --- |
| `--foundation` | 必填、绝对路径，真实位置必须是随方案部署的受信 requirements 基础目录；不是模型参数 |
| `--allow-save` | 默认关闭；开启后才列出并接受保存工具 |
| 其他启动参数 | 首版不提供任意模块路径、项目初始化、确认签发和旧目录回退开关 |

服务标识固定为 `solution-designer-file-tools`，初始服务版本拟为 `0.1.0`；业务工具结构另用 `contract_version: "solution-tools-v1"` 标识。客户端条目名固定为 `solution-designer`。

未开放工具即使被直接构造 `tools/call` 也必须拒绝。MCP 注解仅帮助客户端理解，只读／写入权限由实际分派逻辑执行。`clientInfo`、工具参数、文件正文及 Agent 自述不产生身份或确认权限。

MCP 传输可参考 requirements 的已实现协议处理，按隔离互操作测试固定支持版本；不把新协议规范调研混入本步骤，也不因复制了版本字符串就声称兼容。

### 3.2 模块加载契约

采用显式路径的受控包加载，建立专用包名，例如 `_solution_shared_requirements`，从受信 requirements 目录加载 `file_tools` 及其相对导入。方案本地内核使用另一专用包名；目录名含空格不参与普通包名解析。

必须满足：

1. requirements 路径来自启动时确认的安装布局，与配置 foundation 一致；不允许 foundation 指向另一份任意 Python 模块树。
2. 先核对路径和源文件存在，再加载；不使用业务目录、当前工作目录或用户正文修改模块搜索路径。
3. 不导入 requirements 的 MCP 入口来取得默认服务器，不重用其进程内状态。
4. 不全局替换 `sys.modules["requirements"]` 等通用名称，不从旧 scripts 补齐导入失败。
5. `SOURCES.json` 保存采用时的依赖摘要。启动时对所采用源文件逐项比较；缺失或变化返回 `dependency_missing`／`dependency_changed`，不自动刷新。
6. 导入后核对模块 `__file__` 仍在固定基础目录；隔离测试预先放置同名模块，证明不会误导入。
7. 服务记录启动时配置、锁文件和模板摘要。后续调用发现这些运行基线变化，停止相关调用并要求重新连接和核对，不热替换代码或配置。

共享模块清单沿用步骤 1 的八个模块：`check_foundation`、`project_state`、`project_init`、`requirements`、`project_info`、`recovery`、`confirmation_records`、`artifact_records`。步骤 5 如发现相对导入闭包增加，先更新清单和测试，不隐式加载整套旧融合能力。

固定实际加载文件为受信 requirements 根下的 `file_tools/__init__.py` 及上述八个模块。包入口也纳入采用时摘要和来源记录。额外只读依赖如果来自同一固定基础目录，且不扩展权限或记录语义，可在 SOURCES 和报告中明确新增路径、原因和测试后采用；需要修改共享文件或采用另一目录时停止受影响部分，报告最小追加范围。

### 3.3 foundation 与双方法入口检查

启动时运行现有基础检查，并增加方案自身检查：

- `foundation/config/local.json` 存在且 schema 有效；projects_root、upstream_root 和项目映射合法。
- foundation、上游、业务父目录按共享约定不重叠；方案安装目录也不能落入业务项目或被业务目录替换。
- requirements 的 `methods/develop-helper` 与方案的 `methods/develop-helper` 都必须是预期软链，解析到配置中的同一 upstream_root。
- 按 requirements 的 `upstream-lock.json` 校验上游内容；不接受仅旧 `upstream/develop-helper` 布局，不自动改链或刷新锁。
- 本地 `solution-design.md`、`agent-file-workflow.md`、工程模板可读且与来源清单一致；调研模板链可解析到同一上游原文。
- 项目指定规范通过 `project_info.resolve_specification` 解析，不把方法入口检查当作规范检查。

每次业务调用重新检查目录绑定、配置／锁摘要与方法入口。共享项目定位仍会触发基础检查，首版接受其成本；优化必须保留等价失效条件，不能只启动时检查一次后无限信任。

## 4. 公共字段、大小和目录规则

### 4.1 公共输入与返回

三个工具均要求 `project_path`，均拒绝未知字段，不接受工具调用参数扩展权限。

公共成功返回包含：

| 字段 | 类型／含义 |
| --- | --- |
| `contract_version` | 固定 `solution-tools-v1` |
| `operation` | 本次工具名 |
| `project` | `{project_id, project_path, identity_source, identity_persisted:true}` |
| `capabilities` | `{read:true, inspect:true, save:<启动能力>}` |
| `atomic_snapshot` | 固定 false，多个文件读取不承诺原子快照 |
| `warnings` | 对象数组，包含 code、message，可选 path／related_ids |
| `confirmation_written` | 固定 false |
| `artifact_registered` | 固定 false |
| `downstream_started` | 固定 false |

读取／检查的成功表示操作完成，即使检查发现问题也不自动成为调用失败。不可执行的参数、目录或读取错误使用错误结构。

错误结构为 `{contract_version, operation, error:{code,message,details,next_action}, ...}`；保存调用必须附 `write_outcome`、`read_id_consumed`、`side_effects`。调用级失败以 MCP `isError:true` 返回，业务发现的结构问题仍是成功的检查结果。协议格式错误使用 JSON-RPC 错误，不伪造工具已执行。

### 4.2 文件描述对象

```json
{"path":"docs/PRD.md","status":"present","sha256":"<64位小写摘要>","size_bytes":4210,"content":"<完整正文>"}
```

- `status`：present／missing／unreadable／invalid。present 的空文件保留真实空串、真实摘要和 0 字节，不能当 missing。
- missing 使用 `sha256:"missing"`、`size_bytes:0`、`content:null`；unreadable 使用 `sha256:null`，不得签发假基线。
- invalid 指能读取但结构／格式不合法；保留可知摘要，附诊断。正文是否可返回按 UTF-8 解码结果处理。
- 所有摘要均对原始字节计算；正文 UTF-8，不对读取结果静默换行或 Unicode 归一化。

### 4.3 大小与资源边界

| 对象 | 首版上限 |
| --- | --- |
| 主上下文、方案、规范单文件 | 128 KiB，与共享文档读取限制一致 |
| 候选正文与最终文件 | 正文非空，先渲染受管头，再要求最终 UTF-8 文件不超过 128 KiB；不只固定预留 512 字节 |
| MCP 输入消息 | 1 MiB，超限拒绝，不截断后保存 |
| 确认记录／登记内容 | 沿用现有校验器各类限制：记录 1 MiB、清单与 metadata 128 KiB、登记成果 32 MiB |
| 新增依赖集合总预算 | 至多 512 个唯一文件、合计至多 64 MiB；超限报告 `dependency_limit_exceeded`，讨论可继续但不签发保存凭证 |
| 规范集／附加资料正文返回 | 总返回正文上限 1 MiB；超限明确报告，不静默截断、分页后冒充完整读取 |
| 凭证 | 单进程全局最多 64 个，按签发顺序淘汰；有效期 900 秒 |

预算是首版工具限制，不是业务限制或上游能力结论；后续调整需更新契约与边界测试。1 MiB 返回预算指所有返回正文 UTF-8 字节总和，不包含 JSON 转义开销；实现不能静默丢字段以控制预算。记录校验器可按其限制核验 1 MiB decisions，主上下文正文仍受单文件 128 KiB 限制，超限时明确报告、不给保存凭证，不把两种限额混同。

### 4.4 项目绑定

1. 路径必须为用户明确选定的绝对路径，位于配置 projects_root 的直接子目录；拒绝 `..`、根目录自身、嵌套目录及软链跳转。
2. 复用项目映射和持久 `project.json.project_id`，两者冲突即拒绝；已有项目以校验后的持久身份为准。
3. 三个工具只承接已初始化项目；缺少 project.json 时报告 `project_not_initialized`，不生成临时 ID、不初始化。
4. 调用共享函数传 `expected_root` 与 `directory_name`，不能只按 ID 重新推导目录。
5. 文件安全检查拒绝越界、路径中的软链及非独立普通文件；历史摘要只接收 `[0-9a-f]{64}`。
6. foundation、项目路径、项目 ID 与配置／代码基线全部绑定凭证；相同 ID 的其他目录不能借用。
7. 未完成的公共事务日志 `.project-state-transaction.json` 以独立状态检查；只读可报告，保存拒绝。方案不替 Main 恢复或清理事务。

## 5. 工具一：solution_read_context

### 5.1 输入

```json
{"project_path":"/absolute/projects/meeting-helper","history_sha256":"<可选的64位方案历史摘要>"}
```

| 字段 | 必填 | 类型／校验 |
| --- | --- | --- |
| `project_path` | 是 | 按第 4.4 节核对的绝对路径 |
| `history_sha256` | 否 | 仅方案历史摘要；不是路径，不接受需求或 PRD 历史参数 |

首版不提供任意 `additional_paths`。额外资料由 Agent 在获准范围普通读取，并记录来源；不能据此声称进入凭证。若未来必须强制保护某类新输入，应扩展显式工具契约，不能靠聊天声明升级保护。

### 5.2 读取与返回内容

- 六份核心文档：project.json、README.md、docs/requirements.md、docs/PRD.md、docs/tech-spec.md、docs/decisions.md。
- 项目选择报告，区分已记录、未记录和非法；规范选择区分缺失、显式 null 和指定名称，不默认选择 default。
- 规范被选定时返回解析位置、文件清单、各摘要和限制范围内完整正文；规范文件清单及内容进入保护集合。拒绝规范内部绕出目录的链接。
- PRD 的源需求绑定及其与当前源需求的关系。
- 当前 tech-spec 的 PRD 绑定及失效信息。
- PRD 结构报告与用途确认报告；确认相关依赖返回路径、摘要和角色，不默认把全部快照正文拼入上下文。
- 如请求历史，返回 `docs/tech-spec-history/<sha>.md` 的准确旧稿及元数据。摘要不符拒绝该请求，不用坏历史签发凭证。
- `read_receipt` 与 `protection`，说明保存凭证和附加读取边界。

### 5.3 凭证签发条件

只读允许 PRD 缺失、未确认或方案首次缺失并如实返回。只要必需文件的存在／缺失状态可确定、依赖集合可完整构建、前后比较稳定，可以签发版本凭证；这不代表具备保存资格。

项目身份不确定、必需文件不可读、依赖集合不完整、预算超限或读取期间有变化时，返回 `read_receipt:null` 和具体原因。已取得的可读材料可以返回，但不能用其拼造可保存状态。无效的确认结构如无法完整确定依赖闭包，也不签发凭证。

```json
{
  "read_receipt": {
    "read_id":"<服务随机签发的不可预测引用>",
    "valid_seconds":900,
    "save_eligible_at_read":false,
    "ineligible_reasons":["prd_confirmation_missing"]
  },
  "protection": {
    "protected_versions":[
      {"path":"project.json","sha256":"<项目摘要>","role":"project_identity_and_registry"},
      {"path":"docs/PRD.md","sha256":"<PRD摘要>","role":"prd_input"},
      {"path":"docs/tech-spec.md","sha256":"missing","role":"target"}
    ],
    "dependency_set_sha256":"<规范化依赖清单摘要>",
    "additional_reads":[],
    "atomic_snapshot":false,
    "changed_during_read":[]
  }
}
```

示例仅节选 protection；真实返回必须列完整集合，不能仅返回这三项。read_id 由 `secrets` 类随机源生成，进程内保存，日志避免输出可重用引用。

读取成功的固定附加字段为 `documents`（第 5.2 节六文件对象数组）、`project_info`（共享选择报告）、`specification`（state、name、files）、`source_alignment`（status、bound_requirements_sha256、current_requirements_sha256、reasons）、`tech_spec_binding`（recorded、prd_sha256、matches_current）、`prd_structure`、`confirmation`、`read_receipt`、`protection`、`history`。未请求历史时 history 为 null；specification.state 为 missing／none／selected／invalid／unavailable。source_alignment.status 为 matched／missing_source／unbound／invalid／outdated／unavailable，missing_source 只用于 PRD 明确绑定 missing 且当前源需求缺失。

confirmation 至少含 status、required_permitted_use、current_prd_sha256、reasons、records、valid_confirmation_ids；沿用共享 records 的逐条 result 与 reasons，valid_confirmation_ids 由实际 valid 项排序得到。来源或确认未满足保存门槛时照常交付可读材料，不能用空对象代替诊断。

## 6. 凭证保护集合与普通附加读取

### 6.1 强制集合

| 类别 | 内容 | 保护方式 |
| --- | --- | --- |
| 项目身份／登记 | project.json 全部原始内容 | 完整摘要；不能只比较 project_id |
| 背景与业务来源 | README、requirements、PRD | 全部摘要／缺失标识；来源绑定另做语义校验 |
| 目标 | 当前 tech-spec，首次缺失也作为预期状态 | 保存前比较，拒绝并发新建或覆盖 |
| 确认记录 | decisions.md，包括缺失状态 | 完整摘要；确认判定不只依赖头部 |
| 登记验证闭包 | 全部登记版本所指单文件，file-set 清单和每个成员 | 按路径安全规则采集、预算内逐项摘要；保留全登记校验语义 |
| 快照验证闭包 | 确认核验可能访问的快照、清单与成员 | 记录所有被核验依赖，不只确认 ID |
| 项目规范 | 已选规范的目录成员清单和正文版本 | 目录清单摘要＋各文件摘要，新增／删除也触发冲突 |
| 运行基线 | local.json、upstream-lock、采用代码、主文档与模板、双方法入口 | 与启动基线比较；发生变化须重新连接，不热替换 |
| 事务状态 | 未完成公共事务日志是否存在及可知摘要 | 存在即阻止保存，不进入恢复写入 |

同一路径去重并保留多个角色。集合摘要由排序后的路径、状态和摘要规范化编码计算；项目内路径和规范库路径分别带作用域，不能混淆根目录。

### 6.2 如何取得完整闭包

当前共享校验器没有通用“所有文件读取回调”。首版新增本地依赖采集逻辑，安全解析 project.json 登记、decisions 和文件集合清单，列出共享校验器可能触及的文件；不靠全局 monkey patch 拦截读取。

采用保守超集：所有登记版本的内容与成员、记录中声明的确认快照与成员都列入。采集器仅计算版本，不签发信任；有效性仍交给共享校验器。不能解析或出现未知登记类型时拒绝保存资格，不漏掉后继续。

读取流程：采集依赖图 A 与各版本 → 读取正文并运行共享校验 → 重新采集图 B 与各版本 → 比较图与内容。只有集合和版本一致才签发凭证。测试必须让共享校验器实际读到的每一依赖都包含在集合中，尤其是非 PRD 登记版本和嵌套清单成员。

这只能发现可观察变化，不是原子快照。即使前后摘要相同，也不能证明中间没有短暂改变。公共锁只能协调遵循同一约定的写入方。

### 6.3 普通附加读取

以下默认不加入保存凭证：用户粘贴材料、网页、外部协议、截图、临时笔记、旧 `docs/solution.md`、未选用的规范以及本次请求读取的方案历史。方案历史是恢复材料，其当前内容摘要会被核对，但不是当前目标的预期版本。

Agent 记录实际采用的来源和日期；关键资料变化要重评设计。工具返回只保证第 6.1 节集合，不能声称所有外部依据始终一致。首版普通工具不会读取任意附加路径，更不会扩大写入范围。

### 6.4 生命周期与消费

- 凭证绑定服务进程实例、项目真实路径／ID、foundation 基线、完整保护集合、单调时间签发点。
- 从签发起满 900 秒（elapsed >= 900）到期，进程重启、集合改变、代码／配置改变也不可继续使用。最多 64 个，淘汰后与不存在统一按失效处理。
- 读取和检查不消费凭证；检查不会延长有效期，也不会为旧候选换发凭证。
- 参数／能力／路径／凭证校验或无副作用预检拒绝时，不消费，返回 `read_id_consumed:false`；基线已变化的旧凭证即使未消费也不能继续保存。
- 紧接着进入可能创建锁、历史、临时文件或替换目标的保存内核前，先消费，返回 `read_id_consumed:true`。锁冲突、unchanged、已知失败或不确定结果均不恢复引用。
- Agent 重新读取后必须比较候选原有基线。服务只能校验引用对应的文件版本，不能证明模型确实修订过内容，不能把 read_id 当作设计适配证明。

## 7. 工具二：solution_inspect

### 7.1 输入

```json
{"project_path":"/absolute/projects/meeting-helper","target":"current"}
```

```json
{"project_path":"/absolute/projects/meeting-helper","target":"candidate","content":"# 完整方案正文\n\n## 0. 基线与用途\n…","profile":"AI"}
```

| 字段 | 必填／组合 | 说明 |
| --- | --- | --- |
| `project_path` | 必填 | 当前项目 |
| `target` | 必填 | current／candidate |
| `content` | candidate 必填，current 禁止 | 完整正文，不带工具受管 front matter |
| `profile` | candidate 必填，current 禁止 | Lite／Standard／AI，大小写精确 |

不接受 read_id，不生成／消费凭证。候选检查根据本次实际读取的 PRD 进行，不证明候选采用了旧会话材料的准确基线。

### 7.2 检查与返回

返回五块彼此独立的结果：

1. `checked_object`：对象类型、文件／正文摘要、profile、PRD 摘要；candidate 返回 `content_sha256`，current 返回 `file_sha256`，不混称同一对象。
2. `structure`：status 为 pass／issues／missing／unavailable，包含 issue 列表及 checker_version。
3. `prd_structure` 与 `source_alignment`：PRD 结构和源需求绑定。
4. `confirmation`：当前 PRD 用途确认五态、理由和有效记录；不是方案确认。
5. `coverage`：REQ 定义、AC 归属、各状态计数和未覆盖项；以及 `consistency` 表示检查前后是否稳定。

`issues` 项固定 `{code,severity,message,section,related_ids}`，可选 line。不能定位的 line 为 null，不能虚构行号。section 为 0—12 或 null。

必须检查：0—12 顶层章节是否唯一、REQ／AC 定义与引用、AC 所属 REQ、覆盖表七列、非法状态、遗漏 AC、重复／冲突覆盖、多 AC 行、covered 行必要字段、not_applicable 的显式理由、已保存受管头及 PRD 绑定。

Markdown 表格解析需忽略代码围栏内表格，处理转义竖线和行内代码；错误行报告行号，不静默跳过后称全通过。跨 AC 的方案设计引用可以重复；同一 AC 重复行首版报告问题，建议合并，不能仅去重掩盖冲突。

AI 检查模型职责、提示词、输出校验、工具／权限、评估和失败回退的明确描述位置。关键词只作为有限提示，不能证明语义正确；没有外部工具可以说明无工具及其边界，不因写“不适用”三个字一律拒绝 AI 方案。

检查技术时序章节及表示方式是否明确；Lite 可用完整文字调用链。Mermaid 只做标记／参与者引用等有限检查，未渲染时固定 `diagram_rendered:false`。

```json
{
  "checked_object":{"target":"candidate","content_sha256":"<正文摘要>","profile":"AI","prd_sha256":"<PRD摘要>"},
  "structure":{"status":"issues","checker_version":"solution-structure-v1","issues":[
    {"code":"coverage_status_invalid","severity":"error","message":"覆盖状态必须为约定枚举","section":11,"line":180,"related_ids":["AC-010"]}
  ]},
  "confirmation":{"status":"missing","required_permitted_use":"形成技术方案","reasons":["decisions_missing"]},
  "consistency":{"stable":true,"changed_paths":[]},
  "limitations":{"semantic_correctness_verified":false,"diagram_rendered":false,"model_evaluated":false},
  "downstream_started":false
}
```

结构检查得到 issues 不写文件、不自动修补、不创建历史。检查期间观察到变化时 `consistency.stable:false`，结果不能用于声称准确当前版通过。

## 8. 工具三：solution_save_tech_spec_draft

### 8.1 输入

```json
{
  "project_path":"/absolute/projects/meeting-helper",
  "read_id":"<本方案服务读取工具返回的引用>",
  "content":"# 工程方案\n\n## 0. 基线与用途\n…",
  "profile":"AI"
}
```

四字段全部必填，拒绝额外字段。不接收 target_path、确认 ID 列表、状态、approval_verified、allow_save、expected SHA、身份或 foundation。预期版本来自服务凭证，受管元数据来自内核实际核验。

正文必须非空、为用户请求保存的完整候选、无开头 YAML front matter；代码块中用于说明的 YAML 允许存在，不应用简单全文检索误杀。工具对正文结构缺口返回检查问题，不能把章节缺失一律当输入格式非法来绕过第 8.2 节允许保存 issues Draft 的约定。标题和正文不允许伪装为受管文件头。Agent 需按角色约定提供准确候选；工具不替模型确定用户是否要求保存。

### 8.2 保存资格

以下条件全部满足才进入目标写入：

- 启动允许保存，项目与凭证匹配且未到期／消费。
- 保护集合完整且未变化，当前无未完成公共事务。
- PRD 存在、UTF-8 可读、结构完整，REQ／AC 合法。
- 源需求绑定满足第 8.3 节。
- 当前项目、当前 PRD 内容摘要、精确用途“形成技术方案”的确认 valid。
- 所需登记、快照与阻塞项核验通过。
- profile 合法，正文与最终大小合法，目标／历史／临时位置安全。

候选结构存在 issues、open／blocked 或未选择规范时，允许保存 Draft 并完整报告；这些不替代用户的下游使用判断。非法指定规范、规范路径不可读或实际选择发生冲突时阻止保存，不能降级为“没有规范”。

### 8.3 源需求与规范选择的明确口径

| 状态 | 处理 |
| --- | --- |
| 当前 requirements 存在且 PRD `source_requirements_sha256` 精确匹配 | 来源对齐 |
| PRD 显式绑定 missing，当前源需求也确实 missing，且 PRD 确认有效 | 允许按这份独立 PRD 保存；披露没有源需求文件 |
| 源需求新增、修改或删除，与 PRD 绑定不符 | `source_alignment_conflict`，先由需求能力处理，不覆盖方案 |
| PRD 绑定缺失或格式无效 | `source_binding_missing`／`source_binding_invalid`，可讨论，不自动补头或猜测；需按需求约定处理后重读 |
| 规范字段缺失 | 返回 missing；保留未选状态，不加载 default，可保存带未决说明的 Draft |
| 规范显式 null | 返回 none，表示明确不用规范集 |
| 指定规范名称 | 返回 selected、准确名称及规范版本；解析失败拒绝保存 |

以上对源需求的门槛是本实施候选新增明确化，不应在没有核对现有项目影响的情况下静默部署。步骤 5 要用缺字段旧 PRD 测试兼容读取及明确拒绝，不自动迁移旧文件。

### 8.4 工具受管头

沿用工程模板的已有字段并加入规范状态，序列化顺序固定：

```yaml
---
artifact_kind: tech-spec
status: Draft
approval_verified: false
profile: AI
prd_path: docs/PRD.md
prd_sha256: <实际PRD摘要>
prd_confirmation_ids: [<排序去重后的有效确认ID>]
specification_state: missing
specification_name: null
---
```

specification_state 为 missing／none／selected，selected 时 name 为经过项目字段校验的名称。现有旧稿缺少新增规范字段可读且报告未记录；重新保存时由当前真实选择生成，不修改历史。

候选正文统一仅规范化末尾换行：去除末尾连续换行后补一个 LF，正文其他字节不改。渲染无当前时间、随机值或自增版本，避免相同保存制造变化；检查／保存示例都要说明采用此正文归一化。返回 `submitted_content_sha256` 与 `normalized_content_sha256`，若不同明确标记。

有效确认列表全部按 ID 排序；确认集合变化即使正文相同也会产生新的完整文件版本，并保留旧文件。项目、来源、规范集合的准确版本返回在 protection／input_binding，不强造模板未定义的人工版本号。

### 8.5 保存执行顺序

1. 无副作用校验能力、参数、项目、凭证、正文大小和可解析条件，记录预检查结果。
2. 与凭证比较当前输入；先发现冲突则不消费、不加锁，拒绝目标写入。
3. 消费 read_id；进入内核，按固定顺序获取 `.project-state.lock`，再获取 `.solution.lock`。无自动等待抢锁或删锁。
4. 锁内再次核对目录／身份、运行基线、事务状态、完整依赖集合、目标与输入版本。重新运行 PRD 结构和确认核验；不能依赖读取时 valid。
5. 构建准确受管头与完整文件；若与目标原始字节完全相同，核对稳定输入并返回 unchanged，不新建历史。
6. 若有旧目标，以完整旧字节摘要创建／复用 `docs/tech-spec-history/<sha>.md`；已存在必须同内容，不覆盖冲突历史。独占创建后 flush／fsync 并复核摘要。
7. 创建目标同目录临时文件，写入完整字节并持久化；替换前最后比较全部非目标输入及目标旧版本。发生变化停止替换，保留已知历史副作用并报告。
8. 原子替换目标并同步目录；记录明确的替换阶段状态。可复用共享原子写辅助，但如异常跨越替换点，必须有足够证据分类，不假定异常意味着没写。
9. 仍在公共锁保护期内复读目标，核对预期字节／元数据、旧稿历史、非目标输入集合及确认。若登记闭包含目标，按第 8.6 节报告，不能漏验。
10. 完成锁释放和临时文件清理；锁被替换或清理失败属于结果的一部分，不能掩盖目标已经写入。不能删除他人临时文件或锁。
11. 针对已复读的精确版本执行结构检查，返回其摘要；检查异常或内容再变化单独报告，不为检查失败重复保存。

### 8.6 登记闭包与目标重叠

旧登记如果仍直接指向 `docs/tech-spec.md`，替换目标可能让旧登记版本摘要失效。首版采用保守规则：写前识别目标是否属于任何登记内容／清单成员或确认快照依赖；若本次字节将变化，则拒绝为 `target_bound_to_registry`，要求由相应受信能力先处理登记快照关系。

不允许保存过程改写登记或把目标从依赖集合剔除以“避免冲突”。完全 unchanged 可在原登记有效、所有输入稳定时正常返回。这样后续写后复核的非目标集合有明确含义，也不会用一次方案保存破坏既有固定版本。

### 8.7 写入范围和事务说明

持久业务写入只包含目标及历史；公共锁、方案锁、自己创建的临时文件／目录属于必须披露的中间副作用。不更新 project.json、README、requirements、PRD、decisions、登记或确认快照。

没有新建多文件事务日志或第二套确认交易系统。历史先保留、目标后替换，不能承诺多个文件一起原子提交。历史已创建但目标未变时，报告历史副作用，不自动删历史“回滚”。进程硬崩溃后可能留下锁或临时文件，由实际恢复判断处理，不自动清扫。

## 9. 保存返回、失败分类与恢复

### 9.1 成功返回示例

```json
{
  "contract_version":"solution-tools-v1",
  "operation":"solution_save_tech_spec_draft",
  "project":{"project_id":"meeting-helper","project_path":"/absolute/projects/meeting-helper","identity_source":"persisted","identity_persisted":true},
  "write_outcome":"saved",
  "changed":true,
  "read_id_consumed":true,
  "target":{"path":"docs/tech-spec.md","sha256":"<新完整文件摘要>","status":"Draft","approval_verified":false,"profile":"AI"},
  "input_binding":{"prd_sha256":"<PRD摘要>","prd_confirmation_ids":["<本次实际有效ID>"],"dependency_set_sha256":"<读取依赖摘要>","specification_state":"missing","specification_name":null},
  "history":{"previous_sha256":"<旧完整文件摘要>","path":"docs/tech-spec-history/<旧完整文件摘要>.md","created":true,"verified":true},
  "post_write":{"target_verified":true,"metadata_verified":true,"history_verified":true,"inputs_unchanged":true,"confirmation_rechecked":true,"cleanup_complete":true},
  "inspection":{"checked_file_sha256":"<新完整文件摘要>","status":"issues","issue_codes":["coverage_open_items"]},
  "confirmation_written":false,
  "artifact_registered":false,
  "downstream_started":false
}
```

公共字段在示例中有节选，正式实现需按第 4 节完整返回。首次保存 history 的 previous_sha256、path 为 null，created 为 false，verified 为 null，附 `status:"not_applicable"`；不能编造旧版。unchanged 的 changed=false、history.created=false，仍报告实际核对与凭证已消费。

### 9.2 write_outcome 与判定证据

| 值 | 必须具备的证据 | 后续 |
| --- | --- | --- |
| saved | 目标写入明确，正文／受管头／历史／输入／清理的约定核对通过 | 报告 Draft；结构结果另看 |
| unchanged | 渲染结果与原始目标完全相同、输入稳定，目标未重写 | 不制造历史 |
| not_written | 明确未进入替换目标，或能够可靠证明本次未替换 | 说明历史／锁／临时副作用；按原因处理后重读 |
| saved_unverified | 明确已替换，但目标、历史、输入、锁释放等指定核对失败／不足 | 先读当前目标和历史，不立即重写 |
| unknown | 无法确定替换是否发生，例如共享写辅助在替换后抛错但无可核对阶段证据 | 先读取核对；同内容也不能补称整次调用成功 |

结构检查 issues 不将 saved 改成失败。结构检查器自身异常单独标 unavailable；写后文件核对已完成时，保存结论保留，不能把检查器异常解释为没保存。写入结果与检查结果的字段不得合并。

### 9.3 错误码分组

| 分组 | 必需错误码／原因 |
| --- | --- |
| 参数与能力 | invalid_arguments、tool_not_enabled、content_invalid、content_too_large、profile_invalid |
| 安装与基础 | dependency_missing、dependency_changed、foundation_invalid、runtime_baseline_changed、methods_invalid、upstream_changed |
| 目录与身份 | path_not_allowed、project_not_initialized、identity_conflict、unsafe_file、transaction_pending |
| 凭证与版本 | read_id_invalid、read_id_expired、read_id_project_mismatch、version_conflict、dependency_set_changed、dependency_limit_exceeded |
| PRD 与来源 | prd_missing、prd_unreadable、prd_structure_invalid、source_binding_missing、source_binding_invalid、source_alignment_conflict |
| 确认 | prd_confirmation_missing／outdated／invalid／unavailable，细节含校验器 reasons |
| 规范 | specification_invalid、specification_unreadable、specification_changed |
| 历史与写入 | history_missing、history_digest_mismatch、history_conflict、target_bound_to_registry、lock_conflict、write_failed、post_write_verification_failed、cleanup_failed |

code 表示主要原因；details 包含 changed_paths、expected／observed 摘要、失败阶段及已知副作用，不泄露密钥和完整环境。不能只依赖自然语言错误文本来分派恢复。

### 9.4 版本冲突示例

```json
{
  "write_outcome":"not_written",
  "read_id_consumed":false,
  "error":{
    "code":"version_conflict",
    "message":"候选采用的 PRD 版本已变化，未覆盖方案",
    "details":{"changed_paths":["docs/PRD.md"]},
    "next_action":"重新读取并比较业务变化，修订受影响设计后再提交"
  },
  "side_effects":{"target_replaced":false,"history_created":false,"temporary_created":false},
  "confirmation_written":false,
  "downstream_started":false
}
```

该示例表示内核前发现冲突；若在锁内才发现，read_id_consumed 必须为 true，不能照抄示例。

### 9.5 结果字段和诊断的执行口径

每次进入工具分派的保存调用，无论成功或失败，均返回 `write_outcome`、`read_id_consumed`、`side_effects`。side_effects 至少含 target_replaced、history_created、temporary_created、cleanup_complete，值为 true／false；只有确实无法判断某项时用 null，并说明 reasons。协议层在分派前拒绝的坏消息不伪造上述执行字段。

unknown 与 saved_unverified 返回可知 target／history 和失败阶段，不补全未知摘要。saved／unchanged 必须返回目标完整文件摘要、提交／归一化正文摘要、绑定输入和独立 inspection；结构检查异常返回 inspection.status=unavailable。unchanged 的 post_write 表示无替换的当前内容／输入核对，不虚构执行过写入。

第 9.3 节错误码列为主要分类集合。同一请求同时触发多项冲突时，主要 code 可按实际最先检测条件返回，其余已知原因列 details.reasons；测试不能要求未约定的优先顺序。只有单独隔离该原因的用例才要求对应准确 code。权限、版本和确认等关键错误不得只给笼统 write_failed。

## 10. PRD 正式确认链依赖

### 10.1 当前真正存在的入口

源码核对发现两条已有基础，不能简单表述为“没有确认实现”：

1. 旧宿主路径：`buzz-develop-helper/scripts/host_tools.py` 的 `confirmation.confirm-current`，使用 `main_collaboration.confirmation_from_host_context` 从已验签上下文构造证据，再调用 `confirm_current_session`。
2. Runtime 实验路径：`fusion-runtime-lab/src/fusion_runtime/buzz/host.py` 对确认单独处理，恢复等待确认节点；领域适配 `adapters/develop_helper.py` 调用旧确认内核。普通 `buzz/tools.py` 对直接确认仍拒绝 `command-invalid`，这是防止绕过 Runtime 的边界，不能误判成整条确认链没有实现。

现有 业务工具链计划（建设期引用未收录：`../../../fusion-runtime-lab/BUSINESS_TOOLCHAIN_PLAN.md`）与[总索引](../../../fusion-design/README.md)记录了临时领域项目中的历史验收，生产真实 Runner／独立方案服务接入未由此证明。本轮仅只读核对源码和记录，没有复跑、启动服务或复用旧临时身份。

上面两条均不是当前 requirements MCP／独立方案 MCP 已开放的确认写入能力。本会话普通回复和文件编辑不能自行构造受信证据。本业务案例“1A、2A、3采用”采纳的是方案取舍，不能补作针对准确 PRD 的用途确认。

### 10.2 valid 必须满足什么

沿用本地只读校验器的五态与现有持久记录格式：

- 项目 ID 与当前持久项目一致。
- 确认对象对应当前准确 PRD 内容摘要及已登记版本，不能把轻量需求或文件集合的摘要直接当 PRD 摘要。
- permitted_use 精确为“形成技术方案”；“同意”“可以继续”本身不是用途字段。
- 记录状态、证据字段与 schema 合法；当前会话证据满足既有 runtime_authenticated 记录约定。
- 登记版本反向引用确认 ID，登记内容与记录摘要匹配。
- 固定快照及其成员真实可读、摘要匹配。
- 当前用途不存在阻塞未决项；范围和非授权事项完整返回，不把局部用途扩成整项目实施许可。

这里的 valid 是现有持久记录契约的只读校验结论；方案进程不重新验证原始宿主签名、不签发证据，也不能仅凭持久 JSON 中的 runtime_authenticated 字段证明宿主认证曾真实发生。真实性依赖受信写入口和文件权限边界，真实验收需展示其来源。

当有多个匹配记录时返回有效 ID 集合；其他无效／旧版记录仍可诊断。不因存在一个错用途记录覆盖另一个真正有效记录。项目或用途不匹配的记录属于 ignored，不能满足保存资格；无任何匹配记录归 missing 并附原因。

### 10.3 核验时机

| 时点 | 行为 |
| --- | --- |
| 上下文读取 | 只读核验，返回观察时的五态；采集全部依赖 |
| 候选／当前检查 | 独立核验，绑定本次检查的 PRD 摘要 |
| 保存无副作用预检 | 发现明显失效可提前拒绝，不依赖此前观察 |
| 公共锁与方案锁内、替换前 | 对同一当前 PRD、登记、记录和快照重新核验 |
| 替换后仍持公共锁 | 再比较依赖并核验；变化则 saved_unverified，不宣称输入始终有效 |

所有写入方遵循公共锁时可避免协作写入互相踩踏；外部编辑不遵循公共锁仍有不可消除的检查间隙，必须保留该限制。

### 10.4 接入缺口与补验安排

| 依赖 | 当前状态 | 要补什么 | 是否阻塞隔离开发 |
| --- | --- | --- | --- |
| requirements 本地只读校验器 | 已有代码 | 方案进程加载、完整依赖保护与五态测试 | 不阻塞 |
| 正式登记／确认写内核 | 旧目录与 Runtime 有实现基础 | 核对可复用受信入口的实际部署、支持目录与项目绑定 | 不阻塞 |
| 当前独立 Agent 环境的受信入口 | 未接通、未验收 | 明确选定已存在宿主路径或单独建设最小受信入口；不能由方案进程代签 | 不阻塞工具开发，阻塞真实正向保存验收 |
| 当前业务 PRD | 未按新增选择同步；无有效用途确认 | 由需求能力按请求同步、展示准确版本，再由受信入口记录用途确认 | 不作为隔离写入夹具 |
| 本机 foundation/local.json | 当前缺失 | 步骤 8 准备准确真实配置并保留已有映射 | 不阻塞临时配置开发 |
| 独立方案客户端 | 尚无实现与加载 | 步骤 5 建代码，步骤 7 隔离验收，步骤 8 实际安装／调用 | 不提前宣称接通 |

补验顺序固定：

1. 步骤 5／7 在临时项目构造明确标注的确认夹具，验证校验和保存机制；夹具不是用户真实确认。
2. 在步骤 8 正向保存前，核对实际可用的受信入口、项目目录兼容性、凭据就绪状态与权限，不读出／复制凭据值，不启动旧生产流程来“顺便验证”。
3. 有兼容入口时，通过该入口登记并展示准确 PRD 版本，获取用户对用途“形成技术方案”的真实决定，留下固定快照与记录；确认后停止，不自动调方案或开发。
4. 独立方案服务实际读取并核验 valid，再按用户已有或当轮准确保存请求保存 Draft，验证复读、历史和恢复。
5. 没有兼容入口时，将“真实确认来源接入”列为单独任务，明确最小范围后实施；本步骤不把旧 Main 整套搬进方案 MCP，也不放宽确认规则。

## 11. 客户端配置预览／应用契约

### 11.1 configure_client.py 职责

固定脚本名，但首版只承诺实现 Cursor JSON 配置格式；Codex 或其他客户端的实际配置格式与重载方式在步骤 8 核对后再提供适配。不能把 Cursor JSON 直接写进其他客户端。

参数候选：`--client cursor --config-path <绝对mcp.json路径> --foundation <requirements绝对路径> --python-executable <解释器绝对路径>`；可选 `--allow-save`；默认只预览。应用需增加 `--apply --expected-config-sha <预览返回摘要或missing>`。回退使用同一脚本的 `--rollback <备份清单绝对路径>`，默认同样只预览；实际回退还需 --apply 与当前配置摘要。

配置路径由安装操作者明确选择，首版不自动搜索所有客户端、不默认写入 ~/.cursor。测试只操作临时路径；真实应用归步骤 8。

### 11.2 条目示例

```json
{
  "solution-designer": {
    "type":"stdio",
    "command":"/absolute/path/to/python3",
    "args":["-B","/absolute/path/to/Solution Designer/mcp_server.py","--foundation","/absolute/path/to/requirements","--allow-save"]
  }
}
```

命令与 args 分离，目录中的空格作为参数内容保留，不拼接为 shell 字符串。不写密钥或替换 requirements 条目；只读安装时省略 --allow-save。

### 11.3 预览、应用、回退

预览返回 config_path、expected_config_sha256、server_name、before_entry、after_entry、change_kind、other_server_names、would_create_backup、applied:false。预览不建目录、不建备份、不准备 local.json。

- 同名同内容：unchanged，不重写配置。
- 同名不同内容：entry_conflict，停止；首版不提供强制覆盖模式。需要升级时先形成针对准确旧条目的另行迁移方案。
- 新条目：在配置锁内再次比较整份摘要和旧条目，既有文件先保存原始字节与清单备份，备份失败不写配置。保留其他服务器及顶层字段。
- 配置不存在：预览返回 missing，应用仍核对缺失状态，独占创建，不覆盖并发生成文件；记录本次只新增条目的事实。
- 写入后复读核对条目与配置摘要。写后失败与未知结果不能笼统返回 applied:false 并诱导立即重试。
- 回退只在当前方案条目与备份所记 after_entry 精确一致时恢复原条目／移除本次新增条目，保留其他用户配置改动；不整文件覆盖备份。若原文件不存在但后来加入其他配置，不删除文件。
- 目标路径、祖先路径和备份不得通过软链越界；锁冲突、版本变化、条目改变明确拒绝。

主文档定位通过工具 description 返回准确本地路径，并提示业务文件操作前读取约定。无需将全文重复塞进每一个工具描述；发现工具不代表已经加载方法。

## 12. 详细建设顺序与文件分工

| 子项 | 本步骤需形成的产出 | 对应后续实施 |
| --- | --- | --- |
| 4.1 接口与字段 | 本文第 3—9 节、三套参数 schema、统一返回／错误对象 | mcp_server.py 的目录和分派，内核返回类型 |
| 4.2 版本依赖 | 第 6 节集合／采集算法／消费规则，保护与附加读取边界 | 本地依赖采集器和凭证管理 |
| 4.3 保存与历史 | 第 8—9 节资格、受管头、阶段记录与恢复语义 | 适配 solution 内核及写后验证 |
| 4.4 共享与来源 | 第 2—3 节固定布局、八模块、来源和失效条件 | 受控加载与基础检查 |
| 4.5 真实确认 | 第 10 节入口源码、现状缺口、正向链补验安排 | 只读校验接入；真正写入口单独补齐 |
| 4.6 客户端 | 第 11 节参数／准确条目／版本与备份规则 | configure_client.py，先临时配置验证 |
| 4.7 验证范围 | 第 13 节用例与证据口径 | 步骤 5 自验、步骤 7 独立验收、步骤 8 真实验证 |

建议步骤 5 内部实施顺序：

1. 安装布局／加载器与临时 foundation 检查；工具只开放只读。
2. 项目绑定、上下文完整读取、依赖集合和凭证；确认五态。
3. 当前／候选检查器，修正旧检查器的定义归属、覆盖表和统一章节差异。
4. 无写入资格判断、冲突分类与历史读取。
5. 保存内核：双锁、凭证消费、历史、替换、写后核对及异常阶段记录。
6. stdio 协议路径贯通，避免只测 Python 函数就判 MCP 已用。
7. 临时客户端配置预览、应用与回退，完善来源清单和真实运行说明。

不要求在步骤 4 提前创建上述代码。两个角色规则主文档继续维护调用时机和行为，不复制参数表；实现出来后再在步骤 6 校准为实际可用说明。

## 13. 验证矩阵与需要的证据

本节编号是契约追踪索引；逐项前置、输入、执行、文件观察、通过／失败和证据要求见[详细测试清单](solution-tools-test-checklist.md)。清单保留以下 26 个编号，不以重复建表产生另一套产品标准。步骤 5 的命令及文件映射见本文第 16 节和清单第 4 节。

### 13.1 隔离开发必须覆盖

| 编号 | 场景 | 必须观察的结果 |
| --- | --- | --- |
| C01 | 只读／允许保存启动 | 工具数分别 2／3；直接构造未开放调用仍拒绝 |
| C02 | 中文／ASCII 目录、映射与持久身份 | 根目录正确，不能由目录名猜错项目或借用同 ID |
| C03 | 根目录外、嵌套、软链、硬链、路径穿越 | 拒绝读取／写入；无越界副作用 |
| C04 | 缺依赖、同名模块污染、旧布局、上游漂移 | 明确拒绝；没有旧 scripts 回退或错误 sys.path 导入 |
| C05 | 双方法入口错指、断链、规范缺失／null／名称 | 方法异常拒绝；三种规范选择不混同 |
| R01 | PRD／方案缺失、空文件、不可读、无效 UTF-8 | 状态准确，空文件不变成首次缺失；不能伪造摘要 |
| R02 | 核心文件、登记非 PRD 版本、清单成员／快照变化 | 集合和内容变化均被发现，未覆盖文件不签发可保存凭证 |
| R03 | 普通外部材料或历史读取 | 明确标附加；不会扩大写范围或当前目标基线 |
| R04 | TTL、跨项目、跨进程、64 引用淘汰 | 凭证正确失效；检查不消费或续期 |
| R05 | 读取期间改图、文件 ABA 变化 | 可观察变化报告；不承诺无法检测的 ABA 也被完全排除 |
| I01 | Lite／Standard／AI 完整与不完整候选 | 统一 0—12；AI 检查限制准确，不强造网络 API |
| I02 | 未知／重复 ID、AC 归属错误、多 AC 行、转义竖线 | 可定位问题，不能用正文提及 AC 冒充覆盖行 |
| I03 | current 与 candidate、检查期间文件变化 | 摘要对象准确；不把旧版／未保存候选的检查移给当前文件 |
| A01 | 五态、错项目／用途／版本／登记引用／快照／阻塞项 | 保存资格按实际分类；不接受布尔值或头部标记代替 |
| A02 | 读取后确认改变，锁内／替换前／写后改变 | 再核验有效，失败阶段与 write_outcome 准确 |
| W01 | 首次保存、同内容、修改保存 | Draft 与元数据真实，unchanged 不重写，历史摘要匹配 |
| W02 | 同正文但 profile／确认列表／规范变化 | 完整文件版本变化可解释，不误判 unchanged |
| W03 | 目标并发新建、输入变化、公共锁／方案锁冲突 | 不覆盖，消费时机准确；不删锁 |
| W04 | 历史已存在一致／冲突，坏历史，读旧稿恢复 | 一致复用；冲突不覆盖；恢复走当前条件的新保存 |
| W05 | 写历史后失败、替换前失败、替换后异常、清理异常 | 正确区分五种结果，报告历史／锁／临时副作用 |
| W06 | 目标仍属于登记依赖、公共事务未完成 | 明确拒绝变化写入，不绕过登记或恢复事务 |
| W07 | PRD 源绑定一致／missing／缺字段／变更；规范未选 | 资格与第 8.3 节一致，旧稿可读而不静默补数据 |
| W08 | 结构 issues／检查器异常与目标复读失败 | 保存与检查结论分开，不重复保存来掩盖问题 |
| P01 | 1 MiB 消息、128 KiB 最终稿、依赖预算边界 | 明确拒绝，无静默截断，无超限基线 |
| F01 | 临时配置预览、同条目、冲突、并发、备份失败、回退 | 预览零写入，保留其他条目和后续修改 |
| E01 | 移走旧融合目录后的新进程 stdio 流程 | 只依赖方案＋显式 requirements＋锁定上游＋临时业务目录运行 |

定向用例服务于实际风险，不为数量重复测试相同实现。修改共享 requirements 代码才扩大其受影响回归；本阶段没有共享代码改动时，不为写文档重跑全部历史测试。

### 13.2 真实补验与独立验收

步骤 7 覆盖未在步骤 3 试用的 Lite／Standard，核对独立进程、完整读写保护和隔离运行。若后续采用独立验收者，按实际派发执行，本文件不自动创建或委派其他 Agent。

步骤 8 记录真实客户端发现／调用、保存及历史、修改冲突、新会话恢复，以及通过真实受信入口产生的当前 PRD 用途确认。真实模型效果只在相应业务选型、凭据与调用范围明确后另验；文件工具通过不能替代会议待办识别效果。

每份实施回报至少包括实际文件、采用依赖摘要、运行命令、退出码、测试数与失败、写入范围／保护文件变化、五态和结果分类证据、未验项。历史测试记录只标引用来源，不能写成当轮已重跑。

## 14. 步骤 4 退出条件与当前状态

| 退出条件 | 本文对应内容 | 本轮状态 |
| --- | --- | --- |
| 三工具字段、返回、能力和目录范围可供实现 | 第 3—5、7—9、16 节 | 实施准备文本与准确文件已齐备，尚无代码可调用 |
| 强制集合与普通附加读取边界明确 | 第 6 节 | 已明确；采集器完整性与竞态保护待代码验证 |
| 确认、结构、保存和下游用途分开 | 第 2、7—10 节 | 已明确，不以一个 ready 字段统称 |
| 历史、并发、失败和恢复可执行 | 第 8—9 节 | 已列阶段和证据要求，待故障注入验证 |
| 共享、foundation、双方法入口及配置方式明确 | 第 3、11 节 | 已列固定取舍；真实配置仍缺失 |
| 真实有效确认来源及补验安排明确 | 第 10 节 | 已核对已有源码路径与历史记录；当前独立服务接入未验 |
| 示例和验证范围可供实施者采用 | 第 5、7—9、11、13、16 节及配套清单 | 已提供说明示例、26 项细则和目标命令，不冒充实际返回 |

当前交付为“步骤 4 实施准备稿与配套验收依据”。新增的来源绑定门槛、目标登记重叠拒绝、候选检查参数与配置范围已纳入本稿实施条件。用户后续明确要求“按本文实施步骤 5”即可在该范围采用，无需逐项重复确认；本轮优化文档本身不构成编码派发。文档已形成不等于接口实现、独立验收或真实链路通过。

## 15. 来源与维护

- 方案建设计划（建设期引用未收录：`solution-designer-construction-plan.md`）、[角色主文档](solution-design.md)、[文件操作约定](agent-file-workflow.md)与[工程模板](templates/tech-spec-template.md)：目标和角色边界。
- [requirements MCP 入口](../requirements/cursor_mcp.py)：共享项目、能力、凭证和错误模式，作为参考而非跨进程复用对象。
- [基础检查](../requirements/file_tools/check_foundation.py)、[公共锁](../requirements/file_tools/project_state.py)、[项目定位](../requirements/file_tools/project_init.py)、[需求基础](../requirements/file_tools/requirements.py)、[项目选择](../requirements/file_tools/project_info.py)：显式共享基础。
- [恢复核验](../requirements/file_tools/recovery.py)、[确认记录](../requirements/file_tools/confirmation_records.py)、[成果登记](../requirements/file_tools/artifact_records.py)：现有只读格式与校验语义。
- 旧方案内核（建设期引用未收录：`../../../buzz-develop-helper/scripts/solution.py`）、旧宿主工具（建设期引用未收录：`../../../buzz-develop-helper/scripts/host_tools.py`）、旧确认内核（建设期引用未收录：`../../../buzz-develop-helper/scripts/main_collaboration.py`）：提取／适配与受信入口来源，不能成为独立方案进程正常运行回退。
- Runtime Host（建设期引用未收录：`../../../fusion-runtime-lab/src/fusion_runtime/buzz/host.py`）、Runtime 领域适配（建设期引用未收录：`../../../fusion-runtime-lab/src/fusion_runtime/adapters/develop_helper.py`）、直接工具边界（建设期引用未收录：`../../../fusion-runtime-lab/src/fusion_runtime/buzz/tools.py`）、业务工具链记录（建设期引用未收录：`../../../fusion-runtime-lab/BUSINESS_TOOLCHAIN_PLAN.md`）：仅核对确认来源，不修改、不启动该区域。

本稿后续变化记录在本文件及 SOURCES；主文档保持参数无关。只有实际实现和验证后，才把“拟定”改为“已提供”，并在建设计划记录对应证据。

## 16. Fizz 开工任务范围与交付约定

### 16.1 任务身份、授权和基线

任务名称为“Solution Designer／步骤 5：方案工具实现与隔离自验”。本节提供可直接采用的派发范围，Fizz 手册只作为执行入口；只有用户实际要求实施后才开工。若用户仅指定 5A／5B／5C，执行该部分并核对依赖；明确授权完整步骤 5 则连续完成三部分，无需逐部分审批或默认等待 Honey。

无正式机器调度协议时，使用上述名称、实际用户指令及本稿版本，不让用户填写或补造 phase、task_id、attempt、authority_ref。已有正式协议时保留真实字段和返工历史。基线由 Fizz 开工时读取实际文件、相关 Git 状态、已有修改及必要摘要产生，不在本文写一个未来必然过期的 HEAD。

### 16.2 准确文件范围

以下路径均以工作区根目录为起点，只有获授权部分涉及的文件可写，不等于授权整个目录。

| 路径 | 可写条件／职责 |
| --- | --- |
| `fusion-runtime/workflows/Solution Designer/mcp_server.py` | 5A—5B，三工具 schema、分派、stdio、凭证与能力控制 |
| `fusion-runtime/workflows/Solution Designer/shared_loader.py` | 5A，固定布局的受控加载与共享依赖摘要检查 |
| `fusion-runtime/workflows/Solution Designer/file_tools/__init__.py` | 5A—5B，仅本地包入口 |
| `fusion-runtime/workflows/Solution Designer/file_tools/dependencies.py` | 5A—5B，项目／规范／确认依赖集合及版本比较，不签发信任 |
| `fusion-runtime/workflows/Solution Designer/file_tools/solution.py` | 5A—5B，上下文、检查、历史与受控保存内核 |
| `fusion-runtime/workflows/Solution Designer/configure_client.py` | 5C，客户端临时配置预览／应用／回退 |
| `fusion-runtime/workflows/Solution Designer/SOURCES.json` | 各部分记录实际代码来源、受信基础闭包及当前摘要，不刷新上游锁 |
| `fusion-runtime/workflows/Solution Designer/README.md` | 各部分仅更新真实运行说明与当前已实现／未实现范围，角色规则留步骤 6 |
| `fusion-runtime/tests/solution_test_support.py` | 独立临时布局、PRD／方案／确认夹具、stdio 测试驱动；不得导入旧确认签发器 |
| `fusion-runtime/tests/test_solution_context_tools.py` | 5A 及 5B 受影响部分：安装、目录、读取、确认、依赖和凭证 |
| `fusion-runtime/tests/test_solution_inspect_tools.py` | 5A 及 5B 受影响部分：当前／候选检查与覆盖解析 |
| `fusion-runtime/tests/test_solution_save_tools.py` | 5B：首次／重复／修改保存、并发、历史和失败结果 |
| `fusion-runtime/tests/test_solution_client_config.py` | 5C：临时配置、备份、冲突与回退 |

确需不同拆分文件时，先在开工文件清单说明准确路径、职责和对范围的影响；表外新正式文件或任何共享文件修改须报告最小追加范围，不先写后报。无需把常规函数拆分或测试方法命名逐项交用户决定。

本轮实施输入只读：本实施说明、测试清单、两份手册、建设总计划、solution-design.md、agent-file-workflow.md、模板与方法入口。不得为实现通过修改这些标准。步骤 6 的规则校准需要相应授权，不能混入步骤 5。

默认禁止修改 requirements 共享代码／配置／锁、Develop_Helper、buzz-develop-helper、fusion-runtime-lab、其他 Runtime、真实业务项目（包括 pirs-cursor-test）、用户客户端配置及 Git 状态。可定向读取本文列出的参考源码；不能读取真实业务正文来构造测试夹具。测试写入只在系统临时根目录下的专用项目／隔离副本／客户端配置进行。

### 16.3 分段完成条件和测试映射

| 部分 | 交付条件 | 当段适用编号 |
| --- | --- | --- |
| 5A 只读链 | 固定基础加载；独立 stdio 的读取／检查工具；项目／来源／规范／确认报告；完整依赖与凭证；方案历史读取；只读无副作用 | C01 只读分支、C02—C05、R01—R05、I01—I03、A01 的只读分支、P01 的读取／消息分支、E01 的只读阶段 |
| 5B 保存链 | 按第 8—9 节完成保存及五态拒绝；双锁、历史、复读、凭证消费；故障与不确定结果不误报 | C01 保存分支、A01 保存拒绝、A02、W01—W08、P01 保存分支；复验受影响的 C／R／I 项，E01 读写阶段 |
| 5C 配置辅助与汇总 | 临时配置预览／应用／回退；真实 README 与来源；四组正式用例完整执行、无旧目录隔离链完成 | F01、E01 完整流程及全部已交付适用编号 |

5A 不要求未实现的保存／配置工具先通过，但必须标明缺口；不得提前公开一个可调用却未实现的保存工具。完整三工具能力数量在 5B 验证。5A 的 --allow-save 可以明确拒绝为未交付能力，不能宣称已开启保存。完成完整步骤 5 时上述临时边界必须消除，满足第 3 节最终契约。

### 16.4 命令、完成报告和停止条件

从工作区根目录执行。以下是实现交付后的目标命令，当前测试文件尚未创建，不为文档自检运行它们：

```sh
python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_solution_context_tools.py'
python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_solution_inspect_tools.py'
python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_solution_save_tools.py'
python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_solution_client_config.py'
python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_solution_*.py'
```

分段交付执行对应组；完整交付直接执行最后一条覆盖四组，不要求先逐组重复跑完。命令必须发现实际测试，退出码 0 但 tests=0、导入失败或必需用例意外跳过不能通过。静态文档／语法检查对实际新增文件执行，不能以未跟踪文件不在 diff 中为由忽略。

requirements 基础文件保持原样时核对版本及已有可关联的有效基线；新连接由方案测试验证。首次复用路径缺少有效证据或发现共享行为风险时，说明涉及哪些现行组并补跑；完整需求组的参考命令为 `python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_requirements*.py'`，不是每次必跑或固定历史计数门槛。不得迁回退役考卷或旧 Main 私有签发器。

报告包含授权范围、实际文件及摘要、各编号的通过／失败／未验、命令／退出码／测试数／日志、临时项目真实文件效果、禁止范围核对、findings 和真实链待验项。当前范围全部开发完成且适用自验通过，回报 DEV_READY_FOR_REVIEW；实质缺依赖或必须越界则 DEV_BLOCKED，保留可独立完成部分。不自签 Honey 结论，不修改建设总计划或权威状态。

遇到需要修改受保护文件、变更契约／验收条件、放宽确认、安装依赖、使用真实项目、准备真实配置、启停服务、付费模型调用或 Git 写入时，停止受影响部分并报告准确原因与最小新增范围。缺真实确认入口／真实 local.json 本身不阻塞隔离实现。未知保存结果先读取核对，禁止盲目重试。完成授权部分后停止，不发送消息、不启动 Honey 或步骤 6—8；已有明确连续范围授权按原范围执行。

### 16.5 文档优化记录

2026-11-01：v1.1 在原契约上补齐准确修改文件、5A／5B／5C 适用用例、可执行的目标测试命令、开发与独立验收入口；澄清正文结构问题与输入拒绝、错误优先级、包入口摘要、返回预算和结果字段。新增详细测试清单，保留原 26 个用例编号。没有实现代码、修改业务材料或接通真实确认链。

2026-11-01：v1.2 按用户要求简化 Fizz／Honey 手册为角色执行入口，移除其旧任务专章和重复建设说明；更新本文与测试清单的引用。接口、准确文件范围、完成条件及原 26 项验收要求保持不变。
