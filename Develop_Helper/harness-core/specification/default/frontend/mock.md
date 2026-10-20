# 前端 Mock 数据（default）

> 来源：原 dev-standards/frontend.md §9 原样迁移。

**规范说明**

- 仅对任务明确要求的 Mock 范围模拟页面交互与跳转，不规定先完成全部页面的开发顺序。
- **凡在界面上展示的 Mock 数据，须带 `[Mock]` 标识**（或项目统一约定的可见标识），便于与真实数据区分。
- 对接真实接口后，移除 Mock 与标识。

### Mock 数据集中管理（强制）

**Mock 数据必须集中存放在 `frontend/src/mocks/` 目录，禁止散落在各个组件或页面文件中。**

```
frontend/src/mocks/
├── auth.ts        # 登录相关的 Mock 数据
├── items.ts       # 商品相关的 Mock 数据
├── orders.ts      # 订单相关的 Mock 数据
└── index.ts       # 统一导出
```

### Mock 数据格式对齐（强制）

以下示例仅展示业务信封字段；完整响应按实际契约补齐 timestamp、request_id、metadata，分页响应还需 pagination，不复用旧的 code 信封。

**每个 Mock 文件的数据结构必须与 `docs/tech-spec.md` §二中定义的接口响应格式完全一致。**

示例（`mocks/auth.ts`）：

```typescript
// 格式严格遵守 tech-spec.md §二中 POST /api/auth/login 的响应定义
export const loginSuccessResponse = {
  success: true,
  error: null,
  error_code: null,
  message: "success",
  data: {
    access_token: "mock-token-xxx",
    user: {
      id: 1,
      name: "[Mock] 测试用户",
      email: "test@example.com"
    }
  }
}

export const loginFailResponse = {
  success: false,
  error: "用户名或密码错误",
  error_code: "UNAUTHORIZED",
  message: null,
  data: null
}
```

**规则：**
- Mock 数据的 success、data、error、error_code、message 及实际契约中的元数据、分页字段必须和 tech-spec.md §二一致
- 后端开发完成替换时，只需要把 Mock 导入换成真实 API 调用，数据结构不用改
- 禁止在组件中硬编码 Mock 数据（如 `const users = [{id: 1, name: "test"}]`）

### Endpoint DTO 收敛（强制）

**内部实体可以是字段超集，但任何 Mock handler 返回给页面的响应必须按 endpoint 显式构造 DTO。**

强制规则：
- 禁止直接返回内部实体对象（如 `return doc`、`return user`、`return item`），必须为每个 endpoint 显式 map 出契约字段
- 禁止用一个宽泛实体类型承接同一功能域下所有接口响应；每个响应形态不同的 endpoint 必须有独立 TypeScript 响应类型
- 如果同一功能域有多个 endpoint（如 upload / list / status / detail），修复契约问题时必须一次性检查该功能域全部 handler 返回体、Mock 数据实体、service 类型和页面接收类型
- `frontend/src/types/` 中应区分内部实体类型与接口响应 DTO，例如 `DocumentEntity`、`KnowledgeDocumentListItem`、`KnowledgeUploadResponse`、`KnowledgeDocumentStatusResponse`
- 列表接口、详情接口、状态接口即使字段相似，也不得默认复用同一个 DTO；以 `docs/tech-spec.md` §二的 endpoint 响应为准

**错误示例：**

```typescript
// 错误：直接把内部实体返回给 status endpoint，容易带出 upload_time 等契约外字段
return HttpResponse.json({
  success: true,
  error: null,
  error_code: null,
  message: "success",
  data: doc,
})
```

**正确示例：**

```typescript
// 正确：按 GET /api/knowledge/documents/{id}/status 的契约显式构造 DTO
const statusResponse: KnowledgeDocumentStatusResponse = {
  doc_id: doc.doc_id,
  file_name: doc.file_name,
  status: doc.status,
  progress: doc.progress,
  message: doc.message,
  ...(doc.status === "indexed" ? { chunks_count: doc.chunks_count } : {}),
}

return HttpResponse.json({
  success: true,
  error: null,
  error_code: null,
  message: "success",
  data: statusResponse,
})
```
