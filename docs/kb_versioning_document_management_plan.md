# 知识库版本控制与文档管理方案

## 目标
- 支持知识库双版本：`draft` 与 `publish`。
- chat 支持按版本对话（可选 `draft`/`publish`，默认 `publish`）。
- 支持按 `document_id` 更新文档（仅更新 `draft`）。
- 测试界面增加文档管理 UI。
- 上传后的 chunks 额外备份到 MongoDB，并维护 embedding 缓存（vector + provider/model + text_hash），Mongo 仍不直接参与在线检索。

## 已确认规则
- 发布策略：只允许 `draft -> publish` 提升发布。
- 更新范围：按 `document_id` 更新时仅替换 `draft` 版本。
- MongoDB 角色：备份/审计 + embedding 缓存，不参与 chat 检索。

## 整体流程
1. 上传/更新文档时写入 `draft`。
2. 同 `document_id` 再次上传时，先替换 `draft` 旧 chunks，再写入新 chunks。
3. 触发发布操作后，将该 `document_id` 的 `draft` 覆盖到 `publish`。
4. chat 请求携带 `kb_version`，检索阶段仅命中对应版本。
5. 每次 ingest 成功时，同步把 chunk 文本和元数据备份到 MongoDB。

## 后端改造点

### 1) Weaviate 版本化能力
- 文件：`app/integrations/weaviate_client.py`
- 新增字段：
  - `document_id`
  - `kb_version`（`draft`/`publish`）
- 扩展能力：
  - 向量检索增加版本过滤（where/filter）。
  - 按 `document_id + kb_version` 删除 chunks。
  - 按 `document_id` 执行发布复制（先清理 publish，再写入 draft 内容到 publish）。

### 2) Ingest 支持按 document_id 更新
- 文件：`app/services/ingest/pipeline.py`
- 变更点：
  - ingest 入参支持外部传入 `document_id`（不传则可沿用现有生成逻辑）。
  - 写入 chunk 时带上 `document_id` 和 `kb_version="draft"`。
  - 更新时执行“draft 全量替换”语义。

- 文件：`app/api/routes/ingest.py`
- 变更点：
  - 扩展 `POST /api/ingest/files`，支持 form 字段 `document_id`。
  - 新增发布接口：`POST /api/ingest/documents/{document_id}/publish`。

### 3) Chat 版本选择
- 文件：`app/schemas/chat.py`
  - `ChatRequest` 增加 `kb_version`（默认 `publish`，仅允许 `draft/publish`）。

- 文件：`app/api/routes/chat.py`
  - 透传 `kb_version` 到服务层。

- 文件：`app/services/rag/pipeline.py`、`app/services/rag/retriever.py`
  - 检索时传递版本参数，并走 Weaviate 版本过滤查询。

### 4) MongoDB chunk 备份 + embedding 缓存
- 新增文件：`app/integrations/mongodb_chunk_store.py`
- 建议集合：`kb_chunks`（可配置）
- `kb_chunks` 建议保存字段：
  - `document_id`
  - `kb_version`
  - `chunk_id`
  - `text`
  - `source`
  - `doc_hash`
  - `chunk_index`
  - `total_chunks`
  - `ingested_at`
- `kb_embeddings` 建议保存字段：
  - `embedding_key`（如 `sha256(provider:model:text_hash)`）
  - `provider`
  - `model`
  - `text_hash`
  - `vector`
  - `vector_dim`
  - `created_at`
  - `updated_at`
- 索引建议：
  - 唯一索引：`chunk_id`
  - 组合索引：`document_id + kb_version + chunk_index`
  - 唯一索引：`provider + model + text_hash`（`kb_embeddings`）

- 文件：`app/services/ingest/pipeline.py`
  - ingest 成功链路中增加 Mongo 备份写入。
  - 更新替换时同步清理 Mongo 中对应 `document_id + draft` 旧记录。

### 5) 配置项
- 文件：`app/core/config.py`
  - 增加 `mongodb_chunk_collection`（环境变量 `MONGODB_CHUNK_COLLECTION`，默认 `kb_chunks`）。
- 同步 `.env` / `.env.example` 说明该集合为备份审计用途。

## 测试界面 UI 改造
- 文件：`app/web/index.html`
  - 新增 `document_id` 输入框（上传/更新共用）。
  - 新增 chat 版本选择下拉（`draft`/`publish`）。
  - 新增发布按钮（按当前 `document_id` 发布）。
  - 增加文档管理结果显示区域。

- 文件：`app/web/app.js`
  - 上传请求附带 `document_id`。
  - chat 请求附带 `kb_version`。
  - 新增发布 API 调用与结果提示。

## 测试计划
- `tests/test_ingest_api.py`
  - 按 `document_id` 更新 draft 成功。
  - 重复更新替换语义正确（旧 chunk 不残留）。
  - publish 接口成功/异常分支覆盖。
  - Mongo 备份存在且字段正确；embedding 缓存字段存在并可命中复用。

- `tests/test_chat_api.py`
  - 默认 `publish` 检索行为。
  - `kb_version=draft` 版本隔离行为。
  - 非法版本参数校验。

- 视需要新增：
  - `tests/test_weaviate_client_versioning.py`
  - `tests/test_mongodb_chunk_store.py`

## 实施顺序
1. 扩展 Weaviate 字段与版本过滤能力。
2. 落地 ingest 的 `document_id` 更新 draft 与 publish 接口。
3. 接入 MongoDB chunk 备份 + embedding 缓存。
4. 接入 chat `kb_version` 参数与检索过滤。
5. 更新测试界面文档管理 UI。
6. 补齐测试并回归 ingest/chat 基础能力。
