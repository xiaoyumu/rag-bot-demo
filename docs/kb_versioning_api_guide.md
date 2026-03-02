# 知识库版本控制 API 使用说明

本文档描述当前已支持的文档管理与版本控制接口，便于前后端联调。

## 1. 上传到 draft

- 方法：`POST /api/ingest/files`
- Content-Type：`multipart/form-data`
- 字段：
  - `files`: 文件（可多个）
  - `document_id`: 可选。传入时用于“按 document_id 更新 draft”（建议单文件）

示例（curl）：

```bash
curl -X POST "http://localhost:8000/api/ingest/files" \
  -F "document_id=doc-001" \
  -F "files=@demo.md"
```

## 2. 发布 draft -> publish

- 方法：`POST /api/ingest/documents/{document_id}/publish`
- 说明：会将目标文档的 `draft` 全量覆盖到 `publish`。

示例：

```bash
curl -X POST "http://localhost:8000/api/ingest/documents/doc-001/publish"
```

## 3. 文档列表

- 方法：`GET /api/ingest/documents`
- 可选参数：
  - `kb_version`: `draft` 或 `publish`，不传表示全部

示例：

```bash
curl "http://localhost:8000/api/ingest/documents?kb_version=draft"
```

## 4. 文档详情（chunk 预览）

- 方法：`GET /api/ingest/documents/{document_id}`
- 参数：
  - `kb_version`: `draft` 或 `publish`（默认 `draft`）

示例：

```bash
curl "http://localhost:8000/api/ingest/documents/doc-001?kb_version=publish"
```

## 5. 删除文档

- 方法：`DELETE /api/ingest/documents/{document_id}`
- 参数：
  - `kb_version`: `draft` / `publish` / `all`（默认 `all`）
- 说明：会同时删除 Weaviate 与 Mongo 备份中的对应记录。

示例：

```bash
curl -X DELETE "http://localhost:8000/api/ingest/documents/doc-001?kb_version=all"
```

## 5.1 一键清空知识库（危险操作）

- 方法：`DELETE /api/ingest/documents`
- 必填参数：
  - `confirm_text=CLEAR ALL`
- 说明：会清空 Weaviate + MongoDB 备份中的所有知识库 chunks。

示例：

```bash
curl -X DELETE "http://localhost:8000/api/ingest/documents?confirm_text=CLEAR%20ALL"
```

## 6. Chat 按版本检索

- 方法：`POST /api/chat`
- JSON 字段补充：
  - `kb_version`: `draft` 或 `publish`（默认 `publish`）

示例：

```json
{
  "question": "这个文档讲了什么？",
  "session_id": "demo-session",
  "enable_rewrite": true,
  "enable_rerank": true,
  "kb_version": "publish"
}
```

## 7. 关键行为约定

- `document_id` 更新只替换 `draft`。
- 发布永远是 `draft -> publish`。
- Mongo 会保存 chunk 备份（文本+元数据）以及 embedding 缓存（vector + provider/model + text_hash），仍不直接参与在线检索。
