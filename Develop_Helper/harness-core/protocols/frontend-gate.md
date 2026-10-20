# 前端 Mock 用户门禁

有前端 Mock 阶段的新计划，在最后一个 `type=frontend` 任务中设置唯一的 `user_gate`。此任务依赖本轮其他前端任务（可经传递依赖），负责整体 Mock 收口；不得用单个页面完成代替全部前端完成。无前端任务不创建此门禁。任务文件仍为 `.sdd/tasks.json`（路径：`<active_project_path>/.sdd/tasks.json`）。

## 任务字段

```json
{
  "user_gate": {
    "kind": "frontend_mock_review",
    "frontend_task_ids": ["T-001", "T-002", "T-003"],
    "required_services": ["实际必需的外部服务名称"],
    "status": "pending",
    "user_confirmation": null,
    "configuration_confirmation": null,
    "rework_task_ids": []
  }
}
```

- `frontend_task_ids`：包含门禁所在任务及本轮所有前端任务；最后一项前端任务的 technicalChecks 包含全部页面的 Mock 主流程与关键异常，复用前序稳定证据，只补测跨页与最终改动。
- `required_services`：引用顶层 `external_services` 中完整交付必需的服务，配置项名称取其 `config_keys`；配置文件位置取技术方案。无外部服务为 `[]`，不得虚构 API Key。
- `status`：`pending`（前端开发中）、`awaiting_user`（等用户）、`changes_requested`（用户要求修改）、`passed`（已放行）。由编排器维护，任务自身 `passed` 仅表示 Tester 通过。
- `user_confirmation`：本次用户对实际前端 Mock 的明确认可记录，初始 `null`。原型确认、初始开发授权、沉默、Tester PASS 均不能代替。
- `configuration_confirmation`：用户在后端配置文件填入 API 地址、模型及凭据等必要项后，记录非空/占位检查结果与真实调用授权范围；不保存配置值。无需服务时明确记录“不适用”。配置齐备不代表真实服务已验收。
- `rework_task_ids`：用户拒绝后，本轮获准修复的前端任务 ID；其他任务仍暂停。

## 调度规则

两种 [推进模式](execution-mode.md) 都保留本门禁。`step_gate` 只管理逐任务确认，不覆盖本 `user_gate`；同一任务同时触发时合并向用户交接，分别记录满足的条件。用户指定前端返工时，逐步模式按 rework_task_ids 一次放行一个任务。

每次派发 Developer 或 Tester 前，运行只读检查：`scripts/sdd_dispatch.py --tasks <active_project_path>/.sdd/tasks.json`（脚本路径：`<harness_root>/scripts/sdd_dispatch.py`）。只读取这个 JSON，不搜索项目、不调用外部服务；输出门禁状态、开发/验收候选和原因。候选仍须检查名额、写入范围、版本、运行端口与测试数据冲突。本脚本不自动启动智能体，也不自行确认门禁。

1. 门禁前：前端与独立后端可以并行，正常派发其 Developer/Tester；真实联调和交付任务必须等门禁通过，不能抢跑。
2. 最后一个前端任务通过 Tester 后，先把门禁设为 `awaiting_user`，再处理就绪队列；停止一切新的 Developer、Tester、返工与联调派发，不因后端已完成或仍在运行而跳过。即使状态尚未来得及写回，检查脚本也根据前端全部通过判定暂停。
3. 已运行的后端 Developer/Tester 可完成当前派发范围并返回成果；通知其不扩展下一任务，不影响前端展示或用户填写配置。收尾不等于继续派发；需要后续 Tester 的成果保留 `testing` 等待恢复，收到 FAIL 只记录，不立即补派修复。不强杀进程、不清空工作区、不等待全部后端完成才向用户交接。
4. 立即向用户提供 Mock 访问地址/启动命令、页面与操作清单、已验及未验范围；列出后端需填写的具体配置文件绝对路径和字段名，要求在本地填写密钥。明确需要用户验收前端并完成配置后才能继续，结束本轮自动推进。已确认且未变的配置只核对状态，不要求重填。
5. 用户要求修改：置 `changes_requested`，清空旧 `user_confirmation`，将受影响前端任务写入 `rework_task_ids`，保留原验收历史；跨页或共享前端变更应同时重新打开最后的整体收口任务，并纳入 rework_task_ids。只允许这些任务的修复与复验；全部再次通过后回到 `awaiting_user`。涉及契约变化先更新相关方案，后端继续暂停。新前端任务须纳入门禁覆盖与最终收口依赖。
6. 用户明确认可 Mock，且所有必需配置已齐备并有记录，才置 `passed`；必需服务顶层状态须为 `confirmed`。只说“界面可以”但配置缺失，或只填了 Key 但尚未认可界面，均保持暂停。通用“继续”不能代替缺失条件。配置恢复后真实连通性由后续 Tester 验证，不靠读取 `.env` 宣布通过。
7. 恢复先回收在途结果，复用已完成产物与证据；不重建任务、不清零返工、不重跑已稳定前端。前端有新变更导致本次用户确认失效时，重新开启门禁。

已有全部完成的历史计划不补设未发生的用户确认。尚在执行的旧计划需在下一次派发前补齐门禁且保留已有状态；本轮新增前端工作也适用。只含后端的计划不被此门禁阻塞。
