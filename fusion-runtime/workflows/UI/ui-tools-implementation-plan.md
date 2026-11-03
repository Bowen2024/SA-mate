# 步骤 4：UI 工具与文件契约实施说明

> 发布说明（2026-11-03）：本规格保留原接口与保护要求；角色工具已经实现，本次验证范围见发布记录。正文中原建设状态按原日期理解，建设管理材料未收录。

日期：2026-11-02（Asia/Shanghai）。版本：v1.0。契约标识：`ui-tools-v1`。状态：建设规格，尚未实现。

本文按用户授权固化步骤 4，供后续实现和独立验收使用。接口名称、路径、限额和保障均为实现要求，不能据本文宣称工具可调用。当前只交付本文及[详细测试清单](ui-tools-test-checklist.md)，不创建工具代码、不安装客户端、不改业务候选。

唯一角色入口仍为 [ui-design.md](ui-design.md)，自然语言操作顺序由[文件操作约定](agent-file-workflow.md)维护，整体决定与进度见建设方案（建设期引用未收录：`ui-module-construction-plan.md`）。工具不判断产品价值、视觉正确或用户是否认可，不签发正式确认。

## 1. 首版选择与实际依据

### 1.1 采用的工程安排

| 项目 | v1 安排 |
| --- | --- |
| N-05 成果布局 | 新项目默认 docs/prototypes/demo/；允许明确指定受限的其他项目内子目录。设计说明为 docs/ui-style.md，公共清单为 ui/artifact-manifest.json。已有合法集合沿用路径，不自动搬迁 |
| N-06 编辑与接收 | 通用编辑工具仅修改专属候选树；MCP 校验后受控物化到当前成果，留完整集合版本与事务前像。采用可恢复的逐文件接收，不宣称整棵目录原子替换 |
| N-07 工具面 | 三项只读能力、三项按启动开关开放的写入能力，共六项；按各自职责划分，不照搬其他模块数量 |
| 首版使用方式 | 本机单用户 stdio MCP，项目每次显式指定；不依赖 Main、需求 MCP 或方案服务在线 |
| 正式业务权限 | 不更新项目根 README／project.json 的受管索引，不登记、不确认、不交接、不部署、不执行页面脚本 |
| 用户反馈与视觉检查 | 可带未决／未验项保存候选版本；文件接收成功不代表演示验收通过，不以步骤 3 后补事项阻塞契约建设 |
| 历史恢复 | 历史完整读取后生成新候选，依当前输入正常接收；事务恢复与用户选择旧版是两种操作 |

这些是在 D-09 内部实现委托及本次建设授权下固定的首版工程选择，未声称用户逐一指定了具体工具名。以后扩大写范围、传输或安全边界须另行核对，不通过内部实现变更悄悄扩权。

### 1.2 实际候选与复用来源

步骤 3 候选位于 `/absolute/path/to/isolated-demo/`，该目录由用户在 Cursor 后续指定。五个主要文件为 index.html、assets/app.js、assets/styles.css、README.md、docs/ui-style.md。它是外部只读导入参考，不自动成为受控业务项目或新工具的写入白名单。

| 来源 | 采用内容与限制 |
| --- | --- |
| [阶段 B](methods/develop-helper/harness-core/skills/sdd-product-design/phase-B.md)及[设计风格方法](methods/develop-helper/harness-core/skills/ui-design-standard/SKILL.md) | 页面、设计和浏览器检查语义；不继承自动改 PRD、标 Confirmed、派发 Planner |
| [artifact_records.py](../requirements/file_tools/artifact_records.py) | 兼容 schema_version=1 的 file-set 清单与路径／摘要检查，不直接提供 UI 保存 |
| [project_state.py](../requirements/file_tools/project_state.py) | 公共项目锁和 atomic_replace 原语；既有根索引事务与 UI 私有事务分别处理 |
| 步骤 1 验证（建设期引用未收录：`runtime-dependency-verification.md`）及[SOURCES.json](SOURCES.json) | 九文件共享闭包、采用摘要与真实依赖边界，不把探针当生产加载器 |
| [方案工具说明](../Solution%20Designer/solution-tools-implementation-plan.md)与[shared_loader.py](../Solution%20Designer/shared_loader.py) | 显式项目、受控加载、能力开关与错误分层的实现参考；不导入整个方案服务或继承其 PRD 正式确认门槛 |

本轮只读复核上游 250 项指纹及已采用共享文件，与现有锁／来源记录一致。不刷新来源锁，不将本文文档自查当运行通过。

## 2. 服务、依赖与能力开关

### 2.1 未来启动形态

```text
python3 -B <UI目录>/mcp_server.py --foundation <requirements绝对目录>
python3 -B <UI目录>/mcp_server.py --foundation <requirements绝对目录> --allow-write
python3 -B <UI目录>/mcp_server.py --foundation <requirements绝对目录> --allow-write --import-root <获准只读导入父目录>
```

以上命令在工具实现后才可执行。服务名 `ui-designer-file-tools`，服务版本初始为 `0.1.0`，独立契约版本为 ui-tools-v1。不提供默认项目、任意代码导入、force、任意根目录写入、确认布尔值或自动初始化参数。

| 参数 | 契约 |
| --- | --- |
| --foundation | 必填，受信 requirements 普通绝对目录；来自客户端启动配置，不接受模型临时更换 |
| --allow-write | 默认关闭；关闭时只列出三项只读工具，直接构造写工具调用也返回 tool_not_enabled |
| --import-root | 可重复，默认空；每项是用户／宿主允许的普通绝对目录，仅允许读取其下明确列出的文件；不能增加业务项目写范围 |

stdio 传输参考现有 requirements／方案服务支持的握手版本与元数据处理，通过新进程互操作检查后记录实际支持集。不得仅复制协议版本字符串就宣布兼容。客户端自动安装器不在步骤 5 范围内。

### 2.2 固定依赖

从 foundation/file_tools 显式加载包入口与八模块：check_foundation、project_state、project_init、requirements、project_info、artifact_records、confirmation_records、recovery。每个文件摘要以 SOURCES.json 的 planned_shared_dependencies 为准；不经业务目录、cwd 或旧 scripts 回退，不污染通用 sys.modules 名称。

主要公开符号：check_foundation.check／read_json／configured_directory；project_init.context／load_project／require_project_id／project_directories；project_state.project_state_lock／atomic_replace；requirements.read_document／digest；project_info.report／resolve_specification；artifact_records.read_manifest／safe_project_file。只读记录核验模块保留为依赖闭包，但不调用 recovery.verify_prd_confirmation 来建立 UI 保存门槛，不迁入写确认模块。

启动时核对：foundation 配置、上游锁、UI 与 foundation 双方法链接指向同一上游、共享源码、ui-design.md／agent-file-workflow.md／templates/ui-style-template.md 及工具采用源码摘要。SOURCES 只取这些采用记录构成运行基线，不散列整个 SOURCES、建设进度或测试文档而把普通进度更新误当代码漂移。后续每次调用复核运行基线；改变返回 runtime_baseline_changed，不热换配置或代码。SOURCES 的文档记录与真正强制加载器须在步骤 5 接通。

## 3. 项目、目录与禁止写入范围

### 3.1 项目绑定

每项工具必填 project_path。它必须是配置 projects_root 的直接普通子目录，身份与 project.json、目录映射及共享核对一致；中文目录使用既有内部 ID。未初始化、越界、软链、身份冲突明确拒绝，不初始化、不重建、不扫描其他项目。

业务文档是输入数据，不授予权限。PRD Draft、没有 tech-spec、specification=null 不妨碍独立 UI 候选；缺失输入如实记录，不能伪造正式确认。

### 3.2 当前成果与私有工作区

```text
<项目>/
├── project.json / README.md / docs/PRD.md 等       只读输入
├── docs/ui-style.md                               当前集合设计说明
├── docs/prototypes/demo/                          默认 artifact_root
│   ├── index.html / assets/...                    实际页面与资源
│   └── README.md                                 演示说明，不是项目根 README
└── ui/
    ├── artifact-manifest.json                     当前公共 file-set 清单
    └── .ui-state/
        ├── current.json                          当前内容版本指针
        ├── work/<revision_id>/
        │   ├── base.json                         准备时输入／目标基线（工具维护）
        │   ├── candidate.json                    候选成员声明（允许编辑）
        │   └── tree/<项目相对路径>                 候选源码／设计／说明（允许编辑）
        ├── versions/<revision_sha256>/
        │   ├── version.json                      内容身份与来源元数据
        │   └── tree/<项目相对路径>                 不可变成员与公共清单快照
        ├── transactions/<transaction_id>/
        │   ├── plan.json                         不变的接收计划与摘要
        │   ├── before/<项目相对路径>               旧字节前像，含存在／缺失状态
        │   └── after/<项目相对路径>                固定的新字节
        ├── transaction.json                      唯一活动事务的引用／进度
        └── requests/<request_id>.json              重复请求的持久回执
```

artifact_root 默认 docs/prototypes/demo。已有合法当前集合时从清单及 current 元数据恢复其目录；调用方显式传入的目录必须一致，不允许借保存搬迁。首次可以指定其他非空的项目内子目录，但不得是项目根、docs 根、materials、.git、.sdd、UI 私有状态区或任意输入／受管索引区域，不得与 docs/ui-style.md 重叠。

v1 每项目只维护一个当前 UI 集合；历史可以保留不同方案，不隐式增加多个当前指针。需要并列多演示入口时先调整契约，不能让两个工具实例各自覆盖同一公共清单。

当前成员只能位于 artifact_root 下，或精确为 docs/ui-style.md。清单固定为 ui/artifact-manifest.json；工具私有文件只允许在 ui/.ui-state/ 下。根 .project-state.lock 使用已有公共锁，其他项目文件不写。

首次接收若没有合法当前清单，所有计划写入的公共目标必须不存在（允许空目录）；预存 docs/ui-style.md 或非空目标不自动纳管，返回 unmanaged_target_exists。已有合法清单但缺少 UI 私有指针时，允许以实际清单及完整成员建立 legacy 基线并在首次接收归档，来源未知标为未知。旧布局不符合成员规则时只读报告 unsupported_layout，不迁移或覆盖。

这限定 v1 的保护能力；不声称能无约束接管任何现成应用。外部试验的导入使用第 5 节映射，原目录保持不变。

已接收集合的公共成员若被外部直接修改而与清单／指针不符，v1 只读报告 collection_invalid 并保留实际变化，不自动刷新清单、合并或覆盖。正常修改在候选树进行；直接修改公共成果后的重新纳管属于明确的漂移处置范围，不借普通 accept 隐式完成。

### 3.3 路径和未知成员

所有项目／集合路径采用规范 POSIX 相对形式：拒绝绝对路径、空段、`.`、`..`、反斜线、控制字符、非 NFC 文本及大小写折叠后冲突；不静默重命名。逐段核对真实路径，拒绝软链、硬链接、设备文件和目标父目录置换。绝对 project_path／import.root 也不得含 `..` 或通过软链。

artifact_root 下未列入旧清单的文件视为用户未知文件：记录目录清单，保持原样，不删除、不纳为成员。候选若要写到这些路径则 unmanaged_target_exists。接收期间出现未知文件变化，报告变化，不删除或覆盖以求一致。

## 4. 成果、版本与输入保护集合

### 4.1 三种不同描述

| 对象 | 必要字段／规则 |
| --- | --- |
| 公共 artifact-manifest.json | schema_version=1、entrypoint、files；files 每项严格为 path、sha256，按路径排序；entrypoint 属于 files；清单不包含自己 |
| 可编辑 candidate.json | schema_version=1、entrypoint（未完成时可为 null）、files（项目相对路径字符串数组）；只能声明允许成员，摘要由检查器计算；不能编辑 artifact_root 或基线 |
| 不可变版本 packet | schema_version、project_id、artifact_root、entrypoint、design_path、readme_path、files、sources、restored_from；用于计算 revision_sha256 |

design_path 固定 docs/ui-style.md；readme_path 为 artifact_root/README.md，均须列入完整候选。entrypoint 是存在的本地 .html 源入口，位于 artifact_root；框架演示的启动细节写入演示 README。v1 不接收仅有远端链接或只含构建产物、无法定位源入口的集合。

version.json 包含 packet、revision_sha256、清单原始字节摘要、创建时间、origin（accepted／legacy）、文件检查 diagnostics 及版本格式。业务未决项以集合中的设计说明为依据，不由工具伪造判断。packet 用 UTF-8、键排序、无多余空白、ensure_ascii=false 的规范 JSON 计算 SHA-256；files 和 sources 按路径／source_key 排序。文件摘要基于原始字节，不换行归一化；时间不进入身份，legacy 的未知来源用空 sources 并明示。

sources 每项为 source_key、state（present／missing）、sha256（存在时 64 位小写十六进制，缺失时字符串 missing）。项目源键为 project:<相对路径>；外部源键为 import:<规范绝对根>:<相对路径>。只有业务只读输入、追加参考和明确导入源进入 packet.sources；当前目标／清单／指针／工具日志只受基线保护，不进入 sources，避免保存结果反过来改变自身身份、导致相同成果无法 unchanged。restored_from 为 null 或历史 revision_sha256，current 准备保留当前值，history 准备设置为所选历史 SHA，empty／import 为 null。公共清单由 files 派生，避免摘要循环。

集合正文／来源相同则复用同一内容目录，不凭时间生成重复版本；来源改变即使页面未变，也记录新来源绑定。恢复生成新候选和接收事件，内容寻址可能复用已存在的同一版本，不能删除中间历史或承诺每次都增加一个物理目录。

所有内部 digest 都使用上述规范 JSON 的 UTF-8 字节 SHA-256：baseline_digest 对排序后的完整保护描述及目录清单计算；base_digest 对 base.json 除自身摘要外的不变字段计算；candidate_digest 对 base_digest、完整 candidate.json、实际成员路径／原始字节摘要及映射后入口计算。它们不是同一个摘要，不能互相替代；read_id 绑定 baseline_digest，inspection_id 同时绑定 base_digest 与 candidate_digest。回执参数摘要对该工具准确参数对象计算，不包含客户端未传入的隐式猜测字段。

### 4.2 读取与准备保护的闭包

固定读取 project.json、根 README.md、docs/requirements.md、docs/PRD.md、docs/tech-spec.md、docs/decisions.md，以及当前清单、指针、当前集合成员／版本描述、artifact_root 目录清单和相关不存在目标状态。不存在也进入基线；不可读与格式损坏不能假装 missing。

source_paths 增加实际采用的项目内参考（例如 materials 中的设计说明），不能指向凭据、私有状态、项目外或可执行命令。外部导入明确列出的全部文件也进入保护集合。源码、配置、上游锁与角色／模板属于服务运行基线，独立于项目 read_id。

保存前比较来源、当前版本、所有旧成员、目录清单、新目标的缺失状态及元数据。candidate 基于旧来源形成时，不能用一次新的读取替换凭证掩盖差异；工具拒绝变化，Agent 负责差异的语义修订。

不遍历所有旧正式确认来建立 UI 业务门槛。但必须解析 project.json 中已存在成果版本的明确内容引用；若计划写／删路径被已登记版本直接引用（包括清单、已列成员或其清单展开成员），返回 registered_path_in_use，先由既有 Main 机制固定旧版快照。展开所读清单和成员描述也加入保护闭包，在接收前／后比较；不能只比较 project.json。登记结构或被展开清单不可读时返回 registry_unreadable，不能跳过保护。正式确认缺失本身不阻止独立候选。

### 4.3 资源上限

| 项目 | 固定上限与处理 |
| --- | --- |
| 当前／候选集合 | 256 成员，不含自动生成清单；单文件 32 MiB，集合字节总量 64 MiB |
| 清单、candidate.json | 每份 128 KiB；以实际序列化大小检查，成员数未超不代表大小一定合法 |
| 项目源文档 | 单份文本 128 KiB；追加 source_paths 最多 64；必要源超限返回 input_too_large，不截断后签凭证 |
| 保护描述总数 | 1024，含存在／缺失目标、输入及导入；超限拒绝，不悄悄缩小闭包 |
| 路径 | 单路径 UTF-8 最多 1024 字节、最多 16 段；实际 OS 无法创建时返回 path_not_supported |
| 版本／事务描述 | 单份 2 MiB；大文件字节存单独 before／after，不塞入日志 |
| 工作区 | 每项目最多 8 个未结束候选；超限 workspace_limit，不自动删除用户候选 |
| 凭证 | read_id／inspection_id 有效 15 分钟，进程内最多 128 个；新发超限拒绝，不替换仍有效凭证 |
| stdio 消息 | 1 MiB；返回内容预算 768 KiB，先保留完整版本描述，正文不足预算用 content_omitted=true 明示，不签缺失描述的凭证 |
| 历史读取 | 列表默认 20，最多 100；支持 after_revision 游标，具体版本按摘要读取；不自动清理历史 |

以上限额是首版接口要求，不改共享模块的既有常量。二进制素材按字节传递／散列，不通过 UTF-8 文档读取器。MCP 不传整套源码或 base64 图片，成员编辑使用受限候选文件树。

## 5. 工具参数与返回

### 5.1 通用规则

六项工具全部必填 project_path，所有对象拒绝未知字段与错误类型，不把 bool 当作整数。摘要为 64 位小写十六进制；revision_id／transaction_id 由工具生成，格式分别 R-／T- 加 32 位小写十六进制；请求 request_id 为调用方生成的标准小写 UUID。凭证为不可猜测的进程内令牌，不当身份授权。

只读响应包含 contract_version、operation、project（project_id、project_path）、state、diagnostics、checks；写入响应另含 write_outcome、request_id、revision_id、transaction_id（如有）、revision_sha256（如有）、verification、receipt_replay。错误为 error.code、message、details、next_action，不返回 approved=true 或 ready_for_development=true。

所有成功／失败结果均含契约、operation 和已核实的 project（身份未核实时为 null），diagnostics 为 `{code,message,paths}` 数组，checks 为检查对象数组。写结果中不适用的 revision_id／transaction_id／revision_sha256 用 null，不省略成含糊状态；error 在成功时为 null，失败时有固定四字段。工具错误以 isError=true 返回，带未决业务事项的合法保存仍为 isError=false。

| 对象／工具 | 必须返回的专有字段及类型 |
| --- | --- |
| 文件保护描述 | key、scope（project／import）、path、import_root（非导入为 null）、role、kind（file／directory）、state（present／missing）、sha256、size_bytes；目录另有 entries 字符串数组 |
| 描述规范 | key 为 project:<path> 或 import:<root>:<path>；role 为 input／current／registry_reference／planned_target／control；missing 的 sha256=missing、size_bytes=0；目录 size_bytes=0、sha256 为规范排序 entries 的摘要 |
| ui_read_context | state=empty／stable／unstable／incomplete；dependency_descriptors、baseline_digest、runtime_baseline_digest、current、history（摘要数组）、import_mapping、contents、read_id（不可发放时 null） |
| current 描述 | kind=none／managed／legacy、revision_sha256（无持久版本时 null）、artifact_root、manifest（描述或 null）；legacy 只读时不伪称已有历史目录 |
| contents | `{key,content,content_omitted}` 数组，content 为 UTF-8 字符串或 null；这是返回正文，不缩减完整保护描述 |
| ui_prepare_revision | state=prepared，workspace_path、editable_paths、base_digest、candidate_digest、next_action；以及通用写结果 |
| ui_inspect | state=empty／stable／candidate_incomplete／candidate_ready／candidate_closed／incomplete／not_activated；issues、verification_scope、inspection_id、candidate_digest、base_digest、proposed_revision_sha256、changes（added／modified／removed 路径数组）、transaction（非事务为 null） |
| ui_accept_revision | state=stable 或 incomplete；current_revision、changes、versions（本次保存／复用的旧新 SHA 数组）与通用写结果；未写入拒绝不伪造 current_revision |
| ui_read_history | state=history_list／history；versions（摘要数组）、next_after_revision（无下一页为 null）、version（单版本描述或 null）、contents；不发写凭证 |
| ui_recover_revision | state=stable 或 incomplete；current_revision、recovery_action、transaction_status 与通用写结果；失败可将 transaction_status 置 blocked |

checks／issues 每项为 `{code,scope,checked,passed,paths,message}`；未运行时 checked=false、passed=null，不写假 true。通用 error.details 为 JSON 对象、next_action 为非空字符串。未知成员和 UI 业务未验诊断分开，不能用 diagnostics 掩盖阻止接收的文件错误。文件保护目录描述中的 entries 使用相对该目录的直接子项名称及类型编码，固定编码 `F:<name>`／`D:<name>`，拒绝链接而不为其生成可写基线；只需要核对未知子树时继续生成其目录描述，不把未知文件纳为成员。

current_revision 为当前持久版本 SHA 字符串或 null，不是上次请求的历史版本。参数或身份错误导致无法核实时，state=unavailable，相关尚未取得的专有字段可为 null；不能用 stable 代表“没有执行检查”。上表的具体 state 用于已经完成对应读取／检查的结果。

读工具不创建目录、锁、配置、历史或持久回执；只生成进程内凭证。写能力关闭时不创建任何文件。所有工具不运行脚本、模型、包安装、Git 修改或浏览器；实际视觉证据由角色负责。

### 5.2 ui_read_context（只读）

| 参数 | 必填 | 类型／语义 |
| --- | --- | --- |
| project_path | 是 | 项目普通绝对目录 |
| artifact_root | 否 | 首次默认 docs/prototypes/demo；已有集合必须与现存一致 |
| source_paths | 否 | 项目内额外来源相对路径数组，默认 [] |
| import_source | 否 | 导入描述对象，见下表；默认无导入 |

import_source 严格包含 root、files、entrypoint、design_path、readme_path；root 是 --import-root 允许范围下的目录，其余是该目录内规范相对路径，后三项必须列入 files。root 必须与当前项目、UI 安装目录、foundation、上游均不重叠，避免导入源同时成为写入目标。files 不超过 256，只读枚举明确文件，不递归扫描未知目录；禁止 .git、依赖缓存、.env*、密钥文件和私有工具状态。工具限制不替代 Agent 对所选材料的判断。

映射固定：design_path → docs/ui-style.md；readme_path → artifact_root/README.md；其他成员 → artifact_root/<原相对路径>。entrypoint 按相同规则映射。映射冲突、README 或设计重复命名导致同目标时拒绝，不覆盖。比如本次五文件对应：

| 外部相对路径 | 默认目标相对路径 |
| --- | --- |
| index.html | docs/prototypes/demo/index.html |
| assets/app.js | docs/prototypes/demo/assets/app.js |
| assets/styles.css | docs/prototypes/demo/assets/styles.css |
| README.md | docs/prototypes/demo/README.md |
| docs/ui-style.md | docs/ui-style.md |

返回完整 dependency_descriptors、baseline_digest、当前集合／历史摘要、导入映射、适用正文、诊断和 read_id。基线读取前后不同则 state=unstable、read_id=null；明确损坏、越界或超限时不发凭证。输入 Draft／缺可选文档仅形成诊断，不要求 PRD 正式确认。

### 5.3 ui_prepare_revision（写入）

| 参数 | 必填 | 类型／语义 |
| --- | --- | --- |
| project_path、read_id、request_id | 是 | 项目、有效读取令牌、请求 UUID |
| mode | 是 | empty／current／import／history |
| history_revision | 条件 | mode=history 时必填历史版本 SHA；其他模式禁止 |

empty 仅在没有当前集合且目标清洁时建立空树；current 复制当前合法成员；import 仅使用 read_id 已固定的 import_source 和映射；history 复制合法历史并保留 restored_from，输入基线仍采用本次读取的当前来源。current／history／import 不把旧来源绑定冒充当前来源已适配，返回历史来源差异供 Agent 判断。

重新核对读基线后在公共锁内建立工作区；read_id 在开始建立工作区时消费，前置拒绝不消费。准备时先固定 base.json／内容摘要／准备回执，再返回允许编辑的 tree 与 candidate.json；其他私有元数据不可编辑。准备不修改公共当前成果。失败仅可能留下可识别的未完成工作区，不冒充已 prepared。

返回 revision_id、workspace_path、editable_paths、base_digest、candidate_digest、write_outcome=prepared、next_action。工作区不因服务重启失效；重启后可重新 inspect，不能复用旧 read_id 或 inspection_id。

### 5.4 ui_inspect（只读）

| 参数 | 必填 | 类型／语义 |
| --- | --- | --- |
| project_path、target | 是 | target=current／candidate／transaction |
| revision_id | 条件 | target=candidate 必填，其他禁止 |
| transaction_id | 条件 | 仅 target=transaction 可提供；省略时读活动事务，提供时可核对指定的未激活／遗留事务 |

candidate 检查声明与完整实际 tree：未列普通文件也返回 unlisted_file（排除固定缓存名，不把缓存纳入成果）；不执行 HTML／JS。只核对路径、格式、成员、入口、设计与 README 存在、依赖声明、变更清单和来源一致性。浏览器记录缺失报告为未验，不冒充文件结构错误；结构检查不修补业务文案或图表。

tree 必须是完整候选而非补丁。返回 added／modified／removed、candidate_digest、proposed_revision_sha256、issues、verification_scope。文件、基线与布局均通过时发 inspection_id，绑定进程、项目、revision_id、candidate_digest、base_digest、运行基线与 removed 路径；不允许调用方传 inspection_ok=true。候选缺文件、混入凭据、来源变化或含未解决文件错误时 inspection_id=null。

current 可只读检查新项目无成果状态或合法清单／指针；有活动事务时 state=incomplete，不能发放可接受的新 read_id。transaction 返回计划、各目标 actual=before／after／other、源变化、回执状态与可用恢复动作，不修改事务。

### 5.5 ui_accept_revision（写入）

| 参数 | 必填 | 类型／语义 |
| --- | --- | --- |
| project_path、revision_id、inspection_id、request_id | 是 | 准确项目、候选、当前进程有效检查令牌、请求 UUID |
| delete_paths | 是 | 要删除的旧受管成员路径数组，无删除也传 []；必须与检查结果 removed 精确相同 |

不接收正文、任意目标路径、外部导入根、来源摘要替换或 force。再次核对完整候选、基线与受管范围后按第 7 节接收。inspection_id 在活动事务持久化时消费；开始写入后即使失败也不能复用。前置未写入拒绝不消费，但候选或输入已变则检查凭证失效。

内容及来源与当前完全相同且验证通过时 write_outcome=unchanged，不新建版本目录，不覆盖当前公共文件；记录幂等回执。部分变化不能被“相同文件跳过”绕过集合核对。

### 5.6 ui_read_history（只读）

| 参数 | 必填 | 类型／语义 |
| --- | --- | --- |
| project_path | 是 | 准确项目 |
| revision_sha256 | 否 | 指定内容版本；提供时禁止 after_revision／limit |
| after_revision | 否 | 列表游标：前一页最后版本 SHA，必须存在 |
| limit | 否 | 列表条数，默认 20，上限 100 |

列表按 version.json 首次建立时间、SHA 排序（时间降序，SHA 升序），只读返回 next_after_revision。指定版本时复核 packet 摘要、成员和清单原始字节后返回完整描述、来源和有限文本；旧字节不能重渲染或改路径再假称原历史。损坏返回 history_invalid，不自动修复。读取不设为当前，恢复走 read_context→prepare(history)→inspect→accept。

### 5.7 ui_recover_revision（写入）

| 参数 | 必填 | 类型／语义 |
| --- | --- | --- |
| project_path、transaction_id、request_id | 是 | 准确项目、活动事务、请求 UUID |
| action | 是 | resume／rollback；依据实际用户恢复意图选择，不自动回滚 |

先 inspect(transaction) 读取事实。resume 仅在来源仍与计划一致、每个目标为已知 before／after 时继续写成 after；rollback 仅在尚无终态 saved 回执、所有目标为已知 before／after 时按完整 before 恢复（before 缺失的新文件才允许删除）。第三方新状态 other 一律 recovery_conflict，不覆盖。

来源已变化时 resume 拒绝；可经明确恢复请求 rollback 已知写入，保留源变化诊断。rollback 不修改上游输入或正式确认，保留不可变历史与回执，也不把旧版说成适配了最新来源。终态 saved 回执已落盘时只允许 resume 校验并清理遗留活动日志，rollback 返回 already_committed。已提交版本的业务回退改走正常历史恢复。

### 5.8 调用顺序示意（未执行）

下面仅是 tools/call 的参数示意，路径／凭证是说明值，不代表实际项目、工具可用或调用成功。prepare(empty) 后须由 Agent 在获准候选 tree 中补齐成员及 candidate.json，再进行 inspect；不能把空候选直接接收。

```json
[
  {"name":"ui_read_context","arguments":{"project_path":"/private/tmp/UI-CONTRACT-FIXTURE/projects/采购测试","source_paths":[]}},
  {"name":"ui_prepare_revision","arguments":{"project_path":"/private/tmp/UI-CONTRACT-FIXTURE/projects/采购测试","read_id":"<读取返回的令牌>","request_id":"11111111-1111-4111-8111-111111111111","mode":"empty"}},
  {"name":"ui_inspect","arguments":{"project_path":"/private/tmp/UI-CONTRACT-FIXTURE/projects/采购测试","target":"candidate","revision_id":"R-11111111111111111111111111111111"}},
  {"name":"ui_accept_revision","arguments":{"project_path":"/private/tmp/UI-CONTRACT-FIXTURE/projects/采购测试","revision_id":"R-11111111111111111111111111111111","inspection_id":"<检查返回的令牌>","request_id":"22222222-2222-4222-8222-222222222222","delete_paths":[]}}
]
```

## 6. 凭证、重复请求与持久版本

read_id 与 inspection_id 在进程重启后失效，绑定准确项目和运行基线；不可跨项目、跨服务或跨候选使用。workspace 中的 base.json 保留准备时事实，服务重启重新检查而不是刷新旧来源。工具元数据相互摘要关联，损坏拒绝，不从可编辑 candidate.json 采信基线。

工作区是否结束由已核对的准备／接收回执确定：prepared 且未接受的工作区计入配额，准备中断的残留也计入；accept 终态回执已经落盘的工作区为只读已结束候选，不再签发新的 inspection_id。需要继续修改时另 prepare(current／history)，不编辑已结束候选再重放原检查。accepted／legacy 版本树同样只读。

每个写请求必须有 request_id。公共锁内先检查同项目 requests/<id>.json：相同 operation 和准确参数摘要且已完成，返回原回执、receipt_replay=true，不再消费令牌／生成工作区／重复接收。不同参数或操作复用 ID 返回 request_reused。进程重启仍可回放已完成请求，即使旧令牌不在内存；必须验证持久回执及相应版本／工作区，并返回独立 current_revision，不能暗示旧结果仍是当前。

相同 request_id 尚未完成时返回 operation_incomplete 及实际工作区／事务引用，先 inspect／recover，不开始第二笔。prepare 的未完成复制只留下工作区而没有公共接收，v1 不提供自动续拷／删除：返回残留位置和缺失项，可使用新请求另建候选；达到配额时先由操作者明确处理已核实的孤立试验工作区。正常 prepared 回执回放只核对不可编辑基线和工作区身份，不能因用户合法编辑 tree 就把原准备结果当损坏；最新候选仍须重新 inspect。损坏回执返回 receipt_invalid，不自动覆盖。写能力关闭时不因发现回执而开放写工具；可用只读工具查询事实。

不可变版本已存在时必须逐项核对后复用；不覆盖同 SHA 下不同字节，不修补损坏历史。历史和事务目录不运行其中脚本。v1 没有自动历史清理或垃圾回收工具，磁盘不足明确失败，不能删掉旧版换成功。

## 7. 多文件接收与崩溃恢复算法

### 7.1 正常接收顺序

1. 在解析和读取权限检查后验证项目与运行基线；以公共 project_state_lock 协调本模块和 Main 等既有工具。锁存在返回 lock_busy，不自动删锁。根 `.project-state-transaction.json` 存在则 main_transaction_pending，不由 UI 恢复。
2. 公共锁内重新核对基线、登记引用、候选摘要、改动／删除范围、新目标不存在状态及路径真实位置。活动 UI 事务未结束时拒绝新 prepare／accept。
3. 先把完整旧集合（如有）保存为不可变历史，完整校验；无当前指针的合法旧清单记为 legacy 版本。首次创建没有旧集合则不伪造完整历史。
4. 建立事务目录，复制 before 和 after 字节并 fsync。before 含所有将写／删目标、清单、current.json 的原始字节或 missing；after 含新公共成员、清单和指针。固定 plan.json：project_id、事务／请求、候选／输入摘要、目标与旧新摘要、版本引用、删除集及 plan_sha256。来源只读描述，不写上游。
5. 事务计划与新完整版本验证通过后持久化活动 transaction.json，再开始公共目标替换。日志只引用固定字节与摘要，不包含可执行步骤或任意路径命令。开始写入前再次比较相应 before，避免外部编辑被覆盖。
6. 逐成员以同目录临时文件＋fsync＋atomic_replace 写入新字节，受管删除核对旧摘要后执行；再写公共清单，最后写 current.json。目录创建只限计划父目录，记录本次创建；失败时保留状态，不清理未知目录。
7. 复读完整当前集合、清单、指针、历史、来源与未知目录清单。输入或用户文件在过程中变化时不宣称 saved；保留事务供检查。成功后持久化终态 saved 请求回执，再移除活动日志，最后返回；不删除历史、事务证据或候选。

日志／版本／回执元数据采用 UTF-8 JSON 固定格式，写入都需原子替换与目录同步。状态判断以真实文件和摘要为准，不仅依靠日志的 progress 布尔值。

元数据 schema_version 均为 1，拒绝未知版本。base.json 含项目、revision_id、准备请求、mode、artifact_root、来源／目标完整描述、目录清单、base_digest、restored_from 和准备时运行基线；candidate.json 不能改这些字段。current.json 含 schema_version、project_id、revision_sha256、manifest_sha256、artifact_root、最后接收 transaction_id／request_id。plan.json 含不可变身份／输入／目标描述及 before／after 文件引用，plan_sha256 对不含自身摘要的规范计划计算；活动日志仅含 schema_version、项目、事务、plan_sha256 与阶段。回执含 schema_version、项目、operation、request_id、原始参数摘要、状态（incomplete／completed）、workspace／transaction／版本引用和实际结果。上述普通文件及其交叉摘要用于检查损坏与错误绑定，不宣称对拥有任意文件写权限的攻击者提供多用户鉴权。

活动日志阶段为 staged／applying／verifying／committed，只是恢复线索，不能代替实际字节核验。created_at 采用 UTC 的 `YYYY-MM-DDTHH:MM:SS.ffffffZ`；同时间历史按 SHA 排序。packet.files 与公共清单 files 同形，仅 path／sha256；size_bytes 留在保护描述中，不加入现有清单成员对象。

### 7.2 恢复与中间可见性

活动 UI 日志存在时，读工具报告 incomplete，普通写入停止；inspect(transaction) 仍可查询。恢复先验证日志格式／计划摘要、所有引用均在正确私有目录、项目身份、路径、大小以及 before／after 字节，然后按各目标真实状态继续或回滚。

若进程在活动日志创建前死亡，指定事务检查应显示 not_activated，并比对公共目标是否仍全为 before。可响应的该阶段失败写终态 not_written 回执；不可响应留下 incomplete 回执。对无活动日志、无 saved 回执且公共目标全为 before 的指定事务，显式 recover(rollback) 仅关闭私有未完成记录，返回 rolled_back／not_written，不改公共文件；不完整的 before／after 复制不用于覆盖。无活动日志但发现 after／other、指针异常或证据不足时 transaction_invalid，不推断“肯定没有写过”。

进程异常退出可能遗留公共锁。v1 不自动断言锁已失效或删除它；由宿主／操作者核对在途进程并按明确授权清理后再恢复。故障测试可以在临时夹具中明确处理已死亡进程的锁，不能把这种测试清理算作工具自动恢复能力。

逐文件接收期间文件浏览器可能看到中间状态；本契约不承诺普通静态服务器具备原子版本切换。预览使用候选 tree，或已校验的不可变版本；读取当前成果须同时确认无活动日志、指针与清单／成员一致。不把当前文件集短暂可访问当作一致性证明。

公共锁只协调遵守协议的调用，不阻止外部编辑器。核对发现 other 状态时停止并报告，不为完成恢复覆盖第三方改动。临时文件、空目录或不可变孤立版本可能保留，回报具体位置；不进行隐式全目录清理。

## 8. 结果与错误分类

### 8.1 写入结果

| write_outcome | 意义与必须返回的事实 |
| --- | --- |
| prepared | 候选工作区与基线已核对建立，公共成果未变 |
| saved | 当前集合、历史、来源与回执已核对，活动事务已关闭；只证明文件接收 |
| unchanged | 集合与来源未变化，当前公共文件未重写；回执可新增 |
| not_written | 未改公共成果；若留下准备失败元数据必须明确列出，不承诺零磁盘副作用 |
| unknown | 已开始修改但无法确定完整效果，或部分写入；返回 transaction_id、逐成员事实和 next_action=inspect_transaction |
| saved_unverified | 计划新字节可能已全部写入，但复读／来源／历史核对失败；保留日志，禁止盲目重试 |

recover 返回上述相应结果，并有 recovery_action、transaction_status（resumed／rolled_back／already_closed）和实际 current_revision。已激活事务 rollback 成功的 write_outcome=saved 表示已核实恢复的旧当前集合，不表示接收了原新候选；首次 rollback 后 current_revision=null 且新目标已按已知前像撤除。未激活且公共目标未变的关闭返回 not_written，并说明仅关闭私有记录。

verification 含 document_set、manifest、pointer、history、inputs、unknown_files 六项 checked／passed 及失败对象；未运行项不写 true。receipt_replay=true 时明确结果来自已完成操作，复核对应不可变版本，current_revision 单独提供。

### 8.2 错误码与处理

| 分组 | 固定 code | 处理 |
| --- | --- | --- |
| 参数／能力 | invalid_arguments、tool_not_enabled | 不发凭证、不进入写入 |
| 依赖／服务 | dependency_missing、dependency_changed、foundation_invalid、methods_invalid、runtime_baseline_changed | 停止受影响调用，不换源或刷新锁 |
| 项目／路径 | path_not_allowed、path_not_supported、project_not_initialized、identity_conflict、unsupported_layout、unmanaged_target_exists | 保留现状，明确路径及条件 |
| 输入／清单 | input_unreadable、input_too_large、source_changed、collection_invalid、unlisted_file、mapping_conflict、registered_path_in_use、registry_unreadable | 不覆盖，修订正确候选或先处理既有登记 |
| 限额 | limit_exceeded、workspace_limit、response_too_large | 拒绝相关操作，不截掉保护集合 |
| 凭证／冲突 | read_expired、read_invalid、inspection_expired、inspection_invalid、target_changed、candidate_changed | 重新读差异或检查；不以新凭证掩盖旧候选 |
| 在途／回执 | lock_busy、main_transaction_pending、operation_incomplete、request_reused、receipt_invalid | 先核对相应在途事实，不删锁或重复执行 |
| 历史／恢复 | history_not_found、history_invalid、transaction_invalid、recovery_conflict、already_committed | 不覆盖或清理证据；明确可恢复与受阻内容 |
| 文件系统 | io_error、write_unknown、readback_failed | 配合 write_outcome 和失败阶段报告，不笼统重试 |

JSON-RPC 解析／方法错误与工具业务错误分开。错误 details 不回显凭据或无关文件正文，不把 Python 堆栈当普通用户所需的操作说明。

## 9. 实施范围与分段交付

后续步骤 5／6 在用户授权范围内实施，不因本说明存在自动开工。建议文件职责：

| 计划文件 | 责任 |
| --- | --- |
| mcp_server.py | 六工具 schema、能力开关、stdio 分派与错误封装 |
| shared_loader.py | 固定依赖、来源／配置／方法基线检查，不导入方案运行服务 |
| file_tools/__init__.py、context.py | 显式项目、输入闭包、路径与读取令牌 |
| file_tools/workspace.py | 准备、导入映射、候选完整检查和 inspection_id |
| file_tools/versions.py | 清单、规范内容身份、完整历史和只读历史读取 |
| file_tools/transactions.py | 公共锁、接收、回执、日志、逐文件恢复与回滚 |

普通实现拆分可以调整，但接口、范围、版本与恢复承诺的实质改变应先更新本文及清单，不靠实现后改标准通过。仅允许 UI 目录必要源码、来源／规则说明，以及 fusion-runtime/tests/test_ui_*.py 与明确的测试证据位置；不改共享九模块、上游、真实业务或全局配置。

| 分段 | 内容 | 测试映射 |
| --- | --- | --- |
| 5A | 来源／项目／只读 context、inspect(current／transaction)、history | UI-T01—T09、T13—T16、T26—T28、T43—T46 |
| 5B | prepare、导入、候选检查与检查凭证 | UI-T10—T20、T44—T46 |
| 5C | 正常接收、成员变更、历史、回执与只读保护 | UI-T21—T32、T47 |
| 6 | 故障注入、部分写入、恢复／回滚与服务重启 | UI-T33—T42、T45—T47 |

5A 中尚未有写工具时可用纯临时静态夹具构建历史／事务测试，不将夹具当正式写入通过。必要的故障恢复基本拒绝在 5C 一并落实，不能交付会覆盖冲突的保存器后才补保护；步骤 6 扩展故障矩阵和恢复实证。

建议将测试按 context、workspace、inspect、accept、history、recovery、stdio、isolation 分组，使用标准库临时夹具。未来可执行的聚合命令：

```sh
python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_ui_*.py'
```

当前不存在这些正式测试，不运行空发现来报告通过。配置安装与真实客户端链路在后续步骤 9 单独验证，不在步骤 5 顺手修改真实配置。

## 10. 本步完成标准与后续

本说明与测试清单覆盖六工具字段、限额、依赖、路径、输入闭包、候选、版本、回执、接收和恢复；N-05—N-07 已有明确首版安排。完成本步文档自查不等于独立审阅、代码实现或运行通过。

步骤 3 的反馈、修订与浏览器证据继续保留待补状态。当前候选只用于推导文件契约，不依据其页面细节新增业务规则。后续反馈改变成员或运行方式时更新受影响条款，不重做已稳定的角色方法。

本轮不修改外部候选、原始需求／PRD、不生成清单接收记录、不启动 MCP、其他 Agent、正式确认或下游任务。下一项实施以用户明确指定范围为准。
