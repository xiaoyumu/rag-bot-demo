# Rerank 工作流说明（项目可重建指南）

本文档详细说明当前项目中 `rerank` 的实现方式、调用链路、配置依赖与重建步骤。  
目标是让你在不看全部代码的情况下，也能按步骤重建同样的流程。

---

## 1. Rerank 在整体 RAG 中的位置

当前聊天链路是：

1. 接收用户问题（`POST /api/chat`）
2. 可选 Question Rewrite（DeepSeek）
3. 向量检索（Ollama embedding + Weaviate Top-K 粗召回）
4. **FlashRank 重排（rerank）**
5. 取 Top-N 上下文
6. DeepSeek 生成最终答案

也就是：**rerank 是“检索后、生成前”的精排步骤**。

---

## 2. 代码入口与关键文件

- API 入口：`app/api/routes/chat.py`
- 聊天总编排：`app/services/rag/pipeline.py`
- 检索服务：`app/services/rag/retriever.py`
- 重排服务：`app/services/rag/reranker.py`
- 生成服务：`app/services/rag/chains.py`
- 配置定义：`app/core/config.py`

核心执行点在 `ChatRagService.chat()`：

- 先 `retrieve()` 得到候选 chunks
- 再 `_select_chunks()` 决定是否调用 `rerank()`
- 最后把重排后的 chunks 送去生成答案

---

## 3. 数据流（检索到重排）

### 3.1 粗召回输入（来自 Weaviate）

检索返回 `RetrievedChunk` 列表，字段包括：

- `chunk_id`
- `text`
- `source`
- `doc_hash`
- `chunk_index`
- `total_chunks`
- `distance`（向量距离，可选）
- `score`（重排分，可选，初始为空）

### 3.2 FlashRank 输入格式

在 `FlashRankRerankerService.rerank()` 中，会把候选块映射为：

- `id`: `chunk_id`（若空则使用索引字符串）
- `text`: chunk 正文

并构造 `RerankRequest(query, passages)` 调用 FlashRank。

### 3.3 FlashRank 输出处理

FlashRank 返回按相关性排序后的结果（含 `id`、`score`）。
服务层会：

1. 用 `id` 回映射到原始 `RetrievedChunk`
2. 把分数写回 `chunk.score`
3. 取前 `top_n` 作为最终上下文

---

## 4. 开关与配置

### 4.1 全局配置（`.env`）

- `RAG_ENABLE_RERANK=true|false`：全局默认是否重排
- `RAG_RERANK_TOP_N=4`：重排后保留多少条
- `FLASHRANK_MODEL_NAME=ms-marco-MiniLM-L-12-v2`
- `FLASHRANK_CACHE_DIR=.cache/flashrank`
- `FLASHRANK_OFFLINE_ONLY=true|false`

### 4.2 请求级覆盖（`POST /api/chat`）

请求体可传：

- `enable_rerank: true|false`

优先级规则：

- 若请求里传了 `enable_rerank`，按请求值
- 若请求未传，使用 `.env` 中 `RAG_ENABLE_RERANK`

---

## 5. 离线模型机制（关键）

项目当前默认离线模式：`FLASHRANK_OFFLINE_ONLY=true`。

这意味着：

- 启动 `FlashRankRerankerService` 时，先检查本地目录是否存在模型
- 期望目录：`<FLASHRANK_CACHE_DIR>/<FLASHRANK_MODEL_NAME>`
- 若目录不存在，立即抛错，不会尝试联网下载

对应代码行为在 `app/services/rag/reranker.py`：

- `offline_only=True` 且本地目录不存在 -> 抛 `RuntimeError`
- 本地目录存在 -> `Ranker(model_name, cache_dir)` 正常初始化

---

## 6. 失败与降级逻辑

### 6.1 正常路径

- 粗召回成功
- rerank 成功
- 返回 rerank 后 Top-N

### 6.2 失败处理

在当前实现中：

- 如果 `use_rerank=False`：直接使用粗召回前 `RAG_RERANK_TOP_N` 条
- 如果 `use_rerank=True` 但 `rerank()` 返回空：回退到粗召回前 N 条
- 若重排服务初始化失败（如离线模型缺失），会在构建 Chat 服务阶段报错

建议在生产可进一步增强：

- 重排初始化失败时自动降级为 `use_rerank=False`（避免整条 chat 失败）

---

## 7. 重建步骤（从 0 到可用）

按以下步骤可重建与当前项目一致的 rerank 流程：

1. **定义配置项**
   - 在 settings 中加入 `RAG_ENABLE_RERANK`、`RAG_RERANK_TOP_N`
   - 加入 `FLASHRANK_MODEL_NAME`、`FLASHRANK_CACHE_DIR`、`FLASHRANK_OFFLINE_ONLY`

2. **实现检索结果结构**
   - 定义 `RetrievedChunk`，至少包含 `chunk_id`、`text`、`source`、`score`

3. **实现重排服务**
   - 用 `flashrank.Ranker`
   - 输入 `query + passages`
   - 输出按 `score` 排序后的 chunk 列表

4. **在主 pipeline 中串联**
   - `retrieve()` -> `rerank()` -> `answer_generation()`
   - 支持请求级开关 `enable_rerank`

5. **实现离线模型检查**
   - `offline_only=true` 时，初始化前检查本地模型目录存在性

6. **暴露可观测信息**
   - 返回 `sources`（包含 `chunk_id`/`source`/`score`）
   - 日志里区分检索与重排阶段错误

7. **验证**
   - 有模型 + 开启 rerank：可用
   - 无模型 + 离线模式：应给出明确错误
   - 关闭 rerank：仍能回答（仅粗召回）

---

## 8. 最小验证用例

### 用例 A：重排生效

- 前提：本地已有 FlashRank 模型
- 请求：`enable_rerank=true`
- 期望：`sources` 中有 `score`，并且上下文排序与纯向量召回不同

### 用例 B：关闭重排

- 请求：`enable_rerank=false`
- 期望：不依赖 FlashRank，直接使用粗召回 Top-N

### 用例 C：离线模型缺失

- 前提：`FLASHRANK_OFFLINE_ONLY=true` 且模型目录不存在
- 期望：返回清晰错误（而不是隐式超时或无意义 500）

---

## 9. 运维建议

- 在部署前做一次模型预热（初始化 `Ranker`）
- 把 `.cache/flashrank` 做成可持久化目录
- 若环境网络受限，必须走离线预置，不要依赖首次在线下载
- 记录重排耗时指标，便于权衡质量和延迟

---

## 10. 一句话总结

本项目的 rerank 是典型“粗召回后精排”架构：  
**Weaviate 负责召回候选，FlashRank 负责排序提纯，DeepSeek 基于提纯后的上下文生成答案。**
