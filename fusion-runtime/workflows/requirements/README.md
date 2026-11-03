# 需求角色与 MCP 文件工具

发布版：2026-11-03。唯一角色入口为 [requirements.md](requirements.md)，文件操作按[约定](agent-file-workflow.md)。Agent 读取 A／R 方法组织讨论，MCP 负责项目检查、初始化、需求与 PRD 读写、补录、历史和恢复。原程序 Workflow 已退役，不在本次源码发布范围内。

## 角色流程

```mermaid
flowchart TD
    U["用户：目标、材料与本轮意图"] --> R["Agent：读取需求角色与 A 方法"]
    R --> P{"需要操作项目吗"}
    P -->|仅讨论| M["沿用当前材料与已有选择"]
    P -->|需要| C["MCP：检查已有项目；明确新建时初始化"]
    C --> READ["MCP：读取项目、需求、PRD 与版本；按需恢复"]
    READ --> M
    M --> T{"本次交付"}
    T -->|轻量需求| A["Agent：澄清场景、范围、业务规则与验收"]
    T -->|完整 PRD| SOURCE["读取已保存需求与已有 PRD；明确要求时也可直接整理 PRD"]
    SOURCE --> A
    A --> Q{"关键取舍需要外部依据吗"}
    Q -->|需要| RESEARCH["Agent：按 R 有限调研，带来源与限制返回 A"]
    RESEARCH --> A
    Q -->|已有依据或不需要| D["形成或修改候选，保留事实、假设与未决项"]
    D --> SAVE{"用户请求保存且工具能力开放吗"}
    SAVE -->|否| OUT["交付候选与实际状态，本轮结束"]
    SAVE -->|是| BIND["保存前明确项目；必要时初始化并读取当前版本"]
    BIND --> WRITE["MCP：用本项目读取引用保存需求或 PRD Draft"]
    WRITE --> RESULT{"保存结果"}
    RESULT -->|成功或未变化| DONE["核对正文、历史与来源版本，报告后结束"]
    RESULT -->|版本冲突| READ
    RESULT -->|未知或未核实| VERIFY["先复读实际文件与历史，再判断后续操作"]
    VERIFY --> OUT
```

轻量需求与 PRD 分别保存；需求变化时先按请求同步需求，再读取新版并更新 PRD。两次保存不承诺原子同步。保存不签发正式确认，也不自动进入方案角色；仅讨论不初始化项目。工具未开放时交付候选并说明缺口。

先按[接入说明](../../../docs/getting-started.md)生成本机配置并检查来源。入口 `cursor_mcp.py` 默认只读；`--allow-initialize` 开放初始化，`--allow-save` 开放需求／PRD 保存及项目选择补录。每次传入完整 `project_path`，当前仍限配置业务根目录的直接子目录。读取引用在对应项目内使用，进程重启后重新读取。

普通保存沿用版本冲突、历史和写后复读；未知结果先读取核对。需求保存、PRD 保存、正式确认、登记和下游启动分别处理。正式确认校验使用本地只读闭包，不提供确认签发入口。

文件工具位于 `file_tools/`，来源见 [SOURCES.json](file_tools/SOURCES.json)。方案与 UI 共用这里的九文件基础、配置与来源锁，不要求本需求 MCP 在线。

## 测试与历史迁移

从仓库根目录运行 `python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_requirements_*.py'`。测试使用临时项目，隔离夹具确认不是真实用户确认。

已有安装的可选迁移辅助仍保留 `--prepare-local-config-from buzz-develop-helper` 和 `--migrate-from-foundation buzz-develop-helper`，分别处理本地配置复制和准确旧 Cursor 条目迁移。新安装不依赖旧目录，按接入说明直接生成自己的本机配置。辅助程序默认预览，应用需使用预览返回的准确命令。

本次发布锁适配仓库中的固定上游快照，排除个人项目登记与学习状态；来源变化见[发布记录](../../../upstream/independent-roles-publication.json)。当前发布不迁移本机业务项目或客户端配置。
