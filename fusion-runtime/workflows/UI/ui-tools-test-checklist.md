# UI 文件工具详细测试清单

> 发布说明（2026-11-03）：本规格保留原接口与保护要求；角色工具已经实现，本次验证范围见发布记录。正文中原建设状态按原日期理解，建设管理材料未收录。

日期：2026-11-02（Asia/Shanghai）。版本：v1.0，匹配 ui-tools-v1。状态：测试规格，尚未实施工具或执行下列代码验收。

本清单与[实施说明](ui-tools-implementation-plan.md)共同作为实现与独立验收依据。47 个编号保持稳定；修改契约时同步受影响的准备、动作、返回和文件判定，不通过降低断言取得通过。步骤 1 的 22 项依赖探针和步骤 2 的静态走查是历史证据，不算以下 47 项已通过。

## 1. 夹具、执行范围与证据

全部文件写入、损坏注入、进程终止、锁清理和恢复试验只在系统临时目录进行，不使用真实业务项目、全局客户端配置或真实候选做故障试验。

| 夹具 | 准备方式 |
| --- | --- |
| F 基础 | 复制采用的九文件 foundation、来源记录及上游到临时普通目录；保留相同上游 snapshot，生成临时配置及双方法链接，业务父目录不在任何 Git 仓库中 |
| P 项目 | 使用现有初始化能力建立临时三文件项目；包含中文目录与明确内部 ID 映射，不建远端；源需求／PRD／tech-spec 按用例创建或缺失 |
| I 外部导入 | 临时只读目录，放 index.html、assets/app.js、assets/styles.css、README.md、docs/ui-style.md 五文件；全部为虚构内容，测试 binary 用另加小文件 |
| B0 无成果 | P 中没有清单、当前指针、docs/ui-style.md 或目标文件；公共父目录可存在为空 |
| B1 当前版本 | 依工具 prepare→inspect→accept 建立首版；5A 的纯只读测试可以手工构造同格式夹具，但标明不是保存成功证据 |
| B2 修改候选 | 从 B1 prepare(current)，修改 JS、增加素材、删除一个旧受管素材，更新 candidate.json；保留设计／README／入口 |
| H 历史 | 至少两个已核对的内容版本及对应回执，记录真实 revision_sha256；不假造生产确认 |
| Q 登记引用 | 按现有登记格式构造本地测试记录，分别直接引用可变目标、引用固定快照、含损坏清单；标明为测试夹具 |

故障点使用内部依赖注入／测试桩或临时子进程，不增加 MCP fail_after、force 或跳过检查参数。每项记录项目身份、采用版本、准确请求、实际返回、当前／历史／候选文件摘要及禁止范围前后对比。

统一文件判定：遍历普通文件相对路径和原始字节 SHA，软链单独记录原始目标；不能只核对“文件存在”。只读场景比较整个临时项目与基础树，连空目录、锁、回执和缓存也不能新增。合法写场景分别比较允许变化和必须不变的集合。

独立验收者对正式实现、测试、文档保持只读，在临时副本执行；开发自验报告仅作线索。发现问题返回实际证据，不修改业务标准或正式代码。

## 2. 来源、项目与读取

### UI-T01 固定依赖和正确来源

准备 F，记录九文件摘要、双方法真实目标和完整上游指纹。以明确 --foundation 启动服务。

预期：只从固定别名包加载采用文件，module.__file__ 均在临时 foundation；读取工具可用；不依赖旧 scripts、方案服务或需求 MCP 在线。缺任一源码应 dependency_missing，改变采用字节应 dependency_changed，不能刷新 SOURCES 或回退导入。基础树除已声明服务临时内存外无写入。

### UI-T02 运行基线改变

服务启动并成功 read 后，分别改变临时配置、上游锁、本地主规则／模板、采用源码。再次调用六工具中适用操作。

预期 runtime_baseline_changed，当前业务成果不变；旧 read_id／inspection_id 不得继续写入。复原后是否重新启动按服务契约执行，不热替换。改变源文件的测试不影响真实原件。

### UI-T03 配置、入口与目录隔离

分别缺 config/local.json、断方法链接、双入口指向不同上游、上游内容漂移、foundation／projects_root 重叠。

预期 foundation_invalid 或 methods_invalid（按实际失败环节），不生成默认配置、不改链接、不刷新锁；合法 F 的检查通过只证明路径／内容。错误中的 next_action 可指导核对，不宣称 Buzz 或权限隔离已接通。

### UI-T04 中文项目与明确绑定

以中文目录 P 和映射 ID 调 ui_read_context；另试其他项目 ID 对应目录、未初始化目录及 projects_root 本身。

预期正确 P 返回持久 project_id 和实际路径；其余分别 identity_conflict／project_not_initialized／path_not_allowed。反复切换两个合法项目不串状态，不补建 project.json，不重建／移动目录。

### UI-T05 路径和文件类型拒绝

对 project_path、source_paths、artifact_root、candidate 成员及导入成员分别注入 ..、绝对项目成员、重复斜线、反斜线、非 NFC、大小写碰撞、软链父目录／文件、硬链接和特殊文件。

预期参数或 path_not_allowed，OS 不支持路径用 path_not_supported；不得越界读写，不静默规范化成另一路径。合法有空格／中文普通文件通过。通过第三方父目录替换模拟路径竞态时拒绝，不覆盖新父目录中的对象。

### UI-T06 完整输入闭包与读取期间变化

P 中建立固定六份输入、额外设计参考及 B1。调用 read，核对输入／目标／目录清单、存在／缺失描述与 baseline_digest；在多文件读取中途修改 PRD 或清单成员。

预期稳定时描述完整并给 read_id；不稳定时 state=unstable、read_id=null。损坏／不可读不是 missing。记录读工具返回正文和省略标志，不能仅凭摘要声称模型已读材料。项目树无任何写入。

### UI-T07 限额与响应预算

分别构造单源文本超过 128 KiB、追加源超过 64、保护描述超过 1024、返回正文超过预算、单 RPC 超过 1 MiB；另试二进制资源与合法小文本。

预期超限 input_too_large／limit_exceeded／response_too_large／协议大小拒绝，不发不完整基线凭证。正文因预算省略必须有 content_omitted=true，完整描述仍需保留；描述自身放不下则拒绝。二进制不能误走 UTF-8 文档解码。

### UI-T08 Draft、缺可选文档与规范选择

P 只有轻量场景，PRD／tech-spec／decisions 缺失；再测试 PRD Draft、specification=null 和未记录规范三种情况。

预期独立 UI read／prepare 不要求“形成技术方案”确认，不伪造 REQ／AC 或审批布尔值；null 不回退 default，缺失保持缺失。真实存在但不可读的源仍应拒绝签有效基线，不把错误解释为没有要求。

### UI-T09 新建、合法旧集合和不支持布局

分别使用 B0、存在合法公共清单但无 current.json 的 legacy 集合、没有清单却预存 ui-style.md／非空目标，以及成员越出 artifact_root 的旧集合。

预期 B0 可准备；合法 legacy 能完整读取并在后续接收前归档；无清单的已有目标 unmanaged_target_exists；不支持旧布局 unsupported_layout。原文件保留，不通过首次保存接管未知内容，不搬迁目录来绕过限制。

## 3. 候选、导入与检查

### UI-T10 empty／current 候选准备

用 B0 的 read_id prepare(empty)；用 B1 的 read_id prepare(current)。核对 request_id 回执、revision_id、base.json、tree 与 candidate.json。

预期 prepared，editable_paths 仅为当前候选 tree 和声明；基线摘要准确，current 模式完整复制成员而不是仅部分文件。公共成果、源输入、项目索引和版本指针不变。empty 在已有集合时拒绝非法模式组合。

### UI-T11 实际五文件导入映射

F 启动时配置 I 的导入父目录。read_context 固定 import_source 五文件并 prepare(import)，以默认 artifact_root 为目标。

预期映射与实施说明第 5.2 节五行一致；外部 README 进入演示目录，设计进入项目 docs/ui-style.md，根 README 保持原始字节。index 及 assets 的相对引用可保持。原导入目录前后字节与成员不变，工作区不是原目录的软链。

### UI-T12 导入权限、冲突与来源变化

分别不配置 --import-root、选择白名单外根、列出未包含的入口／设计／README、映射成重复目标、导入 .env 或密钥文件；read 后修改 I 的 JS，再 prepare。

预期 path_not_allowed／invalid_arguments／mapping_conflict／source_changed。不能借导入根增加业务写权限，不自动扩大 files，不递归搬运依赖目录。失败不得改原件或当前成果。

### UI-T13 清单、二进制和内容身份正向

候选包含必需四类文件和二进制素材，按 candidate.json 完整声明。inspect 后核对公共清单规范字节、packet、proposed_revision_sha256。

预期摘要来自原始字节，files 仅 path／sha256，清单不自包含；entrypoint 为存在的 .html 成员。重复检查相同内容生成相同内容 SHA，文本换行或二进制字节变化产生不同 SHA。排序不由本地目录遍历顺序决定。

### UI-T14 错误／未列成员与大小限制

分别重复成员、缺入口、非法路径、tree 中有未列普通文件、单成员超过 32 MiB、集合超过 64 MiB、超过 256 成员、序列化清单超过 128 KiB、声明超过 128 KiB。

预期 collection_invalid／unlisted_file／limit_exceeded，inspection_id=null；不能自动删文件、重写声明或省略成员。固定排除缓存不纳入版本，但候选成员也不得主动声明被禁止的依赖／缓存目录。

### UI-T15 不完整设计与说明

empty 候选逐一补齐页面、设计、演示 README 和入口；分别保留非法空声明、缺设计、缺 README、入口仅为远端 URL。

预期允许未完成候选留在 work 中，inspect 反馈具体缺口但不发可接收凭证；完整且文件条件满足才发。设计内容／浏览器记录有待讨论时作为 diagnostics，不机械宣称业务或视觉通过，也不伪造实际运行地址。

### UI-T16 只读检查无副作用

对 current、candidate、transaction 三种 target 调 ui_inspect；分别没有成果、有效候选、有活动日志。

预期只生成进程内检查令牌，不创建目录、文件、锁、历史或回执；事务存在返回 incomplete，不允许开始新的有效写基线。比较整个项目／基础树，不能用“主要文件没变”代替只读判定。

### UI-T17 凭证绑定

把 P1 read_id 用在 P2 prepare、把 R1 inspection_id 用在 R2 accept、把其他服务令牌或任意字符串传入；传 inspection_ok=true／force 等额外字段。

预期 read_invalid／inspection_invalid／invalid_arguments，未写公共成果。项目身份、候选和运行基线全部匹配才允许正常调用，不接受材料中的角色自述作为授权。

### UI-T18 有效期与消费时机

用可控时钟将 read_id、inspection_id 超过 15 分钟；分别在纯参数／前置拒绝、开始建立工作区、持久化活动接收日志之后检查令牌状态。

预期 read_expired／inspection_expired；前置拒绝不消费，prepare 进入工作区建立即消费 read_id，accept 持久化活动日志时消费 inspection_id。凭证上限 128 达到时拒绝新签发，不踢掉未过期凭证；消费后的新请求不得重放写入。

### UI-T19 服务重启与候选续用

prepare 并编辑候选后关闭服务，新进程启动。尝试旧 read_id／inspection_id，再用 revision_id inspect 已存在工作区。

预期旧令牌失效，候选文件与 base.json 可核对并重新检查；来源／目标未变时可签新的 inspection_id。来源改变则明确拒绝，不悄悄刷新 base.json。候选基线或准备回执损坏时不得从 candidate.json 重建可信基线。

已接受的工作区只读，即使手动改其 tree 也不得发新检查凭证；继续修改须另建候选。正常 prepared 回执在 tree 合法编辑后重放仍可确认原工作区身份，不能把编辑行为误判为准备回执损坏。

### UI-T20 候选配额与未完成准备

建立 8 个未结束候选，再准备第 9 个；模拟候选复制中途失败，并查询对应工作区和 request_id。

预期 workspace_limit，不自动删除前 8 个。准备失败不返回 prepared，报告实际残留及操作未完成／拒绝事实；公共成果不变。新请求不无意续写不明工作区，关闭候选不通过修改公开业务文件实现。

## 4. 接收、历史、回执与并发

### UI-T21 首次完整接收

B0 完整候选 inspect 后，accept 传准确 inspection_id、request_id 和 delete_paths=[]。

预期 saved，公共成员、规范清单、current.json、完整版本快照与终态回执均可复读；不存在旧版本时不伪造 v0 历史。verification 六项有实际证据，活动日志已关闭。源需求、项目 README／project.json 及外部 I 完全不变。

### UI-T22 相同内容与来源

从 B1 current 准备相同候选，检查并接收，使用新的请求 UUID。随后仅改变来源并显式重新准备适配后的候选，保持页面字节相同。

预期前者 unchanged，不重写公共文件、不创建重复内容目录；后者来源 packet 改变，记录新的来源绑定。不可用新读凭证直接接收基于旧来源的候选。统计历史按内容身份核对，不要求每次保存新增目录。

### UI-T23 成员修改、增加与删除

使用 B2。先 accept 传空 delete_paths 或不完全匹配 removed，再按检查结果传完整删除集。

预期第一次拒绝，第二次 saved；旧完整集合仍可还原，新增／修改准确，只有声明的旧受管成员被删除。未知文件、旧历史和来源不变；只更新一部分成员不能被报告为集合成功。

### UI-T24 用户未知文件与目标冲突

在 artifact_root 添加未受管文件；让候选写同路径。另在 read 后新增目标文件或修改现有受管 JS。

预期分别 unmanaged_target_exists／target_changed。未知文件保持原样，不能通过扫描自动登记或删除；目录清单变化被识别。并发服务读取同一 B1 后分别接收不同候选，至多一方成功，另一方不得覆盖新当前成果。

### UI-T25 检查后候选／来源变化

inspect 发 inspection_id 后修改 tree 中 CSS、candidate.json、PRD、额外设计参考或导入源文件，再 accept。

预期 candidate_changed 或 source_changed，公共成果未改；inspection_id 失效，必须比较差异。相同文件换路径或少列成员不能维持旧 candidate_digest。只更换读令牌不能覆盖旧候选事实。

### UI-T26 历史列表与游标

H 建立多个已知时间／同时间不同 SHA 版本。调用 ui_read_history 默认列表、指定 limit、after_revision，再指定单一 revision_sha256。

预期默认 20、上限 100，排序与规范一致，无遗漏或重复；非法／不存在游标拒绝。单版本读取核对完整字节与来源，列表／读取均不改变 current.json 或业务文件。

### UI-T27 损坏历史拒绝

分别篡改版本 packet、版本 SHA、清单原始字节、二进制成员，或移走某成员；尝试历史读取、复用已有 SHA 目录及 prepare(history)。

预期 history_invalid，缺失版本为 history_not_found；不修补旧目录、不覆盖相同 SHA 历史、不生成可接收恢复候选。错误要指出损坏对象，不能简单当没有历史。

### UI-T28 旧版恢复采用当前基线

从 H 选择旧版，先读取当前输入，再 prepare(history)，核对 restored_from 与当前 sources；检查并接收。

预期恢复是新候选／接收事件，保留中间历史；原历史来源作为说明保留，不冒充当前已适配。内容寻址按 packet 复用允许重复目录；恢复过程中来源再变应拒绝。旧版恢复不回滚业务源文档或正式确认。

### UI-T29 已登记引用保护

Q 分别直接引用当前 JS、公共清单、通过另一清单引用当前成员，以及只引用固定快照；另损坏登记格式或引用清单。

预期直接／间接可变引用与接收目标交叉则 registered_path_in_use；损坏 registry_unreadable；只有不相交固定快照时可正常接收。测试读取与接收之间改变引用清单也必须识别，不仅比较 project.json。UI 不自行替 Main 写确认快照、改索引或消除保护。

### UI-T30 重复请求正向

分别对 prepare、accept、recover 使用同一 request_id 和完全相同参数连续调用，再重启服务重放；核对其对应工作区、版本与回执。

预期 receipt_replay=true，无第二次文件操作，不要求已消费的旧令牌重新存在。旧接收结果不再是当前时返回独立 current_revision，不能冒充刚保存了旧版。回放对应历史或工作区缺失时明确拒绝，不重造已结束成果。

### UI-T31 重复 ID、未完成与坏回执

相同 ID 改参数／换操作；中断后重发尚未完成的请求；损坏持久回执或其引用；在关闭写能力的服务重放写请求。

预期 request_reused／operation_incomplete／receipt_invalid／tool_not_enabled。未完成请求返回可核对的 revision_id／transaction_id，不启动第二笔接收；调用方先检查再恢复，不通过重复请求自动回滚或清理。

### UI-T32 公共锁与两类在途日志

分别预置公共项目锁、根 Main .project-state-transaction.json、UI 活动 transaction.json。尝试新 prepare／accept，并调用只读 inspect(transaction)。

预期 lock_busy／main_transaction_pending／operation_incomplete，保留锁和日志；UI 不恢复 Main 事务。UI 事务仍可只读查看，read_context 不发新的有效写凭证。正常调用结束后公共锁正确释放。

## 5. 故障与恢复

所有用例必须同时记录“客户端是否收到响应”和“文件实际处于何种状态”；进程被终止时不能编造原调用返回值。恢复后重新启动读取，检查 current、清单、历史和输入，而非只信日志 progress。

### UI-T33 活动日志落盘前失败

在历史归档、after／before 复制或固定版本生成阶段注入异常，尚未创建活动 transaction.json。

预期公共成果未改，能响应时 not_written 并报告私有残留；read_id／inspection_id 消费符合各自时机。遗留未完成请求有可核对引用，不把临时数据当已接收版本。不得为清理而删除未知文件或旧历史。

若进程未响应即退出且无活动日志，指定 transaction_id 检查返回 not_activated。只有公共目标仍全为 before 且无 saved 回执时，显式 rollback 可以关闭未完成私有记录并返回 not_written；若有 after／other 或证据不足则 transaction_invalid，不能因缺日志猜测未发生写入。

### UI-T34 日志已落盘但未写首个公共文件

持久化活动日志后终止临时服务。检查全部公共文件仍为 before、完整事务 after 可读，再在处理临时死亡进程锁后恢复。

预期读状态 incomplete，无旧 inspection_id 重放；resume 能完成原计划，rollback 可回到 before 且不删未知文件。不能因“还没动页面”无日志记录地重新开一笔。

### UI-T35 部分成员替换后中断

B2 在第二个成员替换后终止；保留一个 before、一个 after、一个待删除旧成员。inspect 返回每个目标状态。

预期 unknown／中断事实可核对，resume 只完成剩余计划并最终 saved；rollback 则恢复完整 before。两种分支分别使用新夹具测试，不能混用恢复后的状态证明另一分支。

### UI-T36 公共清单之后、指针之前中断

在新成员和公共清单写完但 current.json 仍旧时终止。

预期不能把当前集合当正常可写基线，inspect 显示指针与文件版本不一致且有活动事务。resume 写正确指针并完成验证；rollback 恢复旧清单／指针／成员，不留新旧混合的成功结果。

### UI-T37 指针已更新但复读失败

写完 current.json 后，分别模拟成员读取失败、输入在最后核对期间变化、历史核对失败。

预期 saved_unverified 或 unknown（实际无法确定时），不能返回所有 verification=true；没有终态 saved 回执，活动日志保留。来源变化时 resume 拒绝，用户可选择安全 rollback；历史损坏不被自动重建覆盖。

### UI-T38 终态回执之后、活动日志清理之前中断

完整验证及 saved 回执持久化后终止，不删除活动日志。重启后先 inspect，再 recover(resume)／重复 accept 原请求。

预期核对已经提交的不可变版本和实际目标后关闭遗留日志，不重写公共成员、不生成重复历史；recover(rollback) 返回 already_committed。若外部文件已变化则报告 recovery_conflict，不为清理日志覆盖改动。

### UI-T39 恢复时来源已变化

部分写入后修改 PRD、设计参考、导入源或登记引用，保持所有公共目标仍属 before／after。调用 recover(resume)。

预期 source_changed 或 recovery_conflict，不能刷新计划输入摘要后继续。报告变动来源和剩余状态，当前成果不新增写入；原源文档保持新值。

### UI-T40 显式回滚与首次创建撤回

分别在 B2 部分写入、B0 首次接收部分写入时请求 rollback。另让上游已变化但所有目标仍已知。

预期 B2 回到完整旧集合，B0 只删除 before=missing 且 actual=已知 after 的新目标；未知文件、外部修改、输入、历史不删。返回 recovery_action=rollback、transaction_status=rolled_back 和真实 current_revision；上游变化诊断保留，不声称旧版适配最新需求。

### UI-T41 第三方状态不得覆盖

中断后外部编辑一个已写／待写成员为既非 before 也非 after 的字节，或删除／替换目标父目录。分别尝试 resume 与 rollback。

预期 recovery_conflict／path_not_allowed，两者都不覆盖第三方值；日志与 before／after 证据保留。不能靠“修复到可读”把真实冲突吞掉。

### UI-T42 日志损坏、磁盘失败和锁遗留

篡改 plan 摘要、事务项目、路径引用、before／after 字节、日志大小；模拟磁盘写满／fsync 失败；强制终止后保留公共锁。

预期 transaction_invalid／io_error 等并配合真实 write_outcome；不执行日志中的任意命令或越界路径，不删旧历史腾空间。锁存在则 lock_busy，不自动删锁；只在临时夹具经明确核对死亡进程后由测试操作者清锁，再验证恢复。

## 6. 文档、进程、边界与结果

### UI-T43 契约静态一致性

逐项对照六工具的 schema、必填／条件字段、模式组合、限额、错误、返回、目录、消费时机与本清单。核对主规则／操作约定只引用字段权威位置、README 区分规格与实现、SOURCES 摘要准确。

预期没有同名字段多义、工具数与能力开关矛盾、循环摘要或未指定的恢复行为；未来文件只作计划名称，已建链接必须可解析。此项可以在步骤 4 自查；通过不能替代 T01—T42 的程序验证。

### UI-T44 stdio 与参数入口

新进程分别只读／--allow-write 启动，做握手、tools/list 和真实 tools/call。核对只读 3 项、写入 6 项；逐项缺必填、传未知字段、错类型、非法 target／mode、条件字段冲突、超大消息、未握手调用。

预期按服务支持集响应，JSON-RPC 与业务错误分开；关闭写能力的隐式调用也拒绝。说明中指向唯一 ui-design.md，发现成功不宣称模型已读规则；非法调用无公共／私有写入副作用。

### UI-T45 净化环境与新进程隔离

只复制实际采用模块及必要文件，排除旧 scripts、实验运行时、方案服务和缓存。使用 -I -S -B，清除 PYTHONPATH／用户 site 等影响，预置同名诱导模块，限制原工作区回读。

预期合法临时布局完整读写与恢复通过，全部来源正确；缺共享依赖或方法直接报具体错误，不从真实源码／同名模块回退，不写字节码。不能仅复跑步骤 1 探针来宣布 UI 服务通过。

### UI-T46 准确写范围和正式边界

围绕完整准备／接收／恢复流程，前后比较上游、共享源码、真实配置替身、原导入目录、项目根 README／project.json、需求／PRD／方案、decisions、确认快照、其他项目及受管成果索引。

预期全部保持原始字节；只有明确当前成员、公共清单、私有状态和正常公共锁可变化。不开真实后台、不上传、不发消息、不部署，不创建正式确认或下游任务。通用编辑器权限与工具边界分开报告，不宣称能阻止所有环境外写入。

### UI-T47 结果分类与证据诚实

分别收集 prepared、saved、unchanged、not_written、unknown、saved_unverified 及 rollback 成功响应，核对逐项实际文件和 verification。故意缺浏览器记录、保留 UI 待决项、改变当前版本后重放旧成功回执。

预期文件接收可以正确完成并保留未验诊断，但不出现视觉已通过／approved／ready_for_development。unknown 和 saved_unverified 提供实际事务与检查动作；rollback 不被描述成新候选接收；旧回执明确 receipt_replay、实际 current_revision，不冒充最新状态。

## 7. 真实客户端与步骤 3 后补

本清单的程序项在临时环境验证保护机制。步骤 9 另从用户最小输入开始取得实际规则读取、工具发现与调用、候选编辑、接收、复读、历史、新会话恢复记录；配置安装／重载独立取证，不修改用户其他服务。

步骤 3 的页面反馈、修订记录与浏览器实测继续后补。其业务成功／失败／布局结果按真实页面和版本记录，不能用 T43 或 stdio 调用替代。独立验收者没有接到浏览器范围时限定结论，不把文件工具通过升级为产品已可用。

## 8. 报告与完成判定

开发报告包含准确代码范围、采用契约版本、适用 UI-T 编号、实际命令／退出码、测试结果、文件副作用证据、失败及未验项。自验就绪可以报告 DEV_READY_FOR_REVIEW；未实现的恢复或未跑项明确列出，不报告全部通过。

独立报告按编号给通过／失败／证据不足／被前置失败阻塞，列实际复现与文件效果。findings 修复后复验受影响编号，已有稳定证据不机械重跑。独立验收不代修正式实现或放宽契约。

步骤 4 本轮只完成规格与静态对照，不运行尚不存在的 test_ui_*.py，也不填写虚假代码通过数。当前 T01—T42、T44—T47 均待后续实现执行；T43 仅完成文档级自查，未取得独立审阅。
