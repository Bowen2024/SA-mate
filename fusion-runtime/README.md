# 独立角色与 MCP 工具

这里发布需求、方案和 UI 三个角色、共享文件基础及隔离测试。`fusion-runtime` 是沿用的目录名；本目录不提供 LangGraph、通用工作流、Runner 或常驻 Host。

| 角色 | 唯一规则入口 | 工具服务 |
| --- | --- | --- |
| 需求 | [requirements.md](workflows/requirements/requirements.md) | [cursor_mcp.py](workflows/requirements/cursor_mcp.py) |
| 方案 | [solution-design.md](workflows/Solution%20Designer/solution-design.md) | [mcp_server.py](workflows/Solution%20Designer/mcp_server.py) |
| UI | [ui-design.md](workflows/UI/ui-design.md) | [mcp_server.py](workflows/UI/mcp_server.py) |

先读[接入说明](../docs/getting-started.md)，再按任务读取角色与方法。三个 stdio 服务分别启动；方案与 UI 复用 requirements 的基础代码和配置，无需需求服务在线。源码使用 Python 标准库；制作具体 UI 页面所需的前端环境由实际项目另行决定。

完整离线检查：`python3 -B -m unittest discover -s fusion-runtime/tests`。测试使用临时文件、项目及模拟确认；它们不签发业务确认，也不修改真实客户端配置。

当前仍使用固定业务根目录规则。按项目任意指定完整目录、独立环境正式确认写入和完整真实客户端链尚有待建设／验证，详见[当前状态](../docs/current-status.md)及[发布验证](../docs/independent-roles-publication.md)。
