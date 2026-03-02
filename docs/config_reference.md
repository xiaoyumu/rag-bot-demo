# 配置手册（`app/core/config.py`）

本文档整理项目所有运行配置项，按模块说明用途、典型场景和推荐配置方式。  
配置来源：环境变量（`.env`）+ `pydantic-settings`。

---

## 1. 应用基础配置

### `APP_NAME`
- 用途：应用名称，用于日志和监控标识。
- 场景：多服务部署时识别具体服务。
- 建议：保持稳定，避免频繁变更。

### `APP_ENV`
- 用途：环境标识（`dev/test/prod`）。
- 场景：按环境加载不同依赖地址、日志策略。
- 建议：本地用 `dev`，测试用 `test`，生产用 `prod`。

### `APP_HOST`
- 用途：服务监听地址。
- 场景：容器内网访问、单机调试。
- 建议：容器/服务器用 `0.0.0.0`，本机可用 `127.0.0.1`。

### `APP_PORT`
- 用途：服务监听端口。
- 场景：本地开发、反向代理转发。
- 建议：开发常见 `8000`，生产按网关规划统一。

### `LOG_LEVEL`
- 用途：日志级别（`DEBUG/INFO/WARNING/ERROR`）。
- 场景：故障排查时提升详细度。
- 建议：生产默认 `INFO`，排障临时切 `DEBUG` 后恢复。

---

## 2. Weaviate（向量库）配置

### `WEAVIATE_URL`
- 用途：Weaviate HTTP 地址。
- 场景：集合管理、查询请求入口。
- 建议：开发指向本地，生产优先内网地址。

### `WEAVIATE_API_KEY`
- 用途：Weaviate API 鉴权密钥。
- 场景：托管或启用鉴权的环境。
- 建议：仅放 `.env` 或密钥系统，勿入库。

### `WEAVIATE_COLLECTION`
- 用途：知识块集合名。
- 场景：知识库数据命名与隔离。
- 建议：上线后尽量不改，避免迁移复杂度。

### `WEAVIATE_GRPC_HOST`
- 用途：Weaviate gRPC 主机。
- 场景：性能优化通道。
- 建议：通常与 `WEAVIATE_URL` 同主机。

### `WEAVIATE_GRPC_PORT`
- 用途：Weaviate gRPC 端口。
- 场景：服务端端口自定义时同步配置。
- 建议：默认 `50051`，与服务端一致。

### `WEAVIATE_GRPC_SECURE`
- 用途：gRPC 是否启用 TLS。
- 场景：公网或跨网络传输。
- 建议：生产建议 `true`；本地可 `false`。

---

## 3. DeepSeek（LLM）配置

### `DEEPSEEK_BASE_URL`
- 用途：DeepSeek API 地址。
- 场景：官方 API 或企业网关代理。
- 建议：默认官方地址，企业环境改为代理地址。

### `DEEPSEEK_API_KEY`
- 用途：DeepSeek 鉴权密钥。
- 场景：rewrite/answer 调用。
- 建议：必须走密钥管理，不写进代码。

### `DEEPSEEK_CHAT_MODEL`
- 用途：回答生成模型名。
- 场景：按质量、成本、速度切换模型。
- 建议：先固定版本，再做灰度评估。

### `DEEPSEEK_TIMEOUT_SECONDS`
- 用途：DeepSeek 请求超时（秒）。
- 场景：上游抖动、长回答避免无限等待。
- 建议：一般 `30~90`，默认 `60`。

---

## 4. Ollama（Embedding）配置

### `OLLAMA_BASE_URL`
- 用途：Ollama 服务地址。
- 场景：本机 embedding 或内网推理服务。
- 建议：本地用 `localhost`，远程优先内网。

### `OLLAMA_EMBEDDING_MODEL`
- 用途：向量化模型名称。
- 场景：召回质量与吞吐权衡。
- 建议：尽量固定具体版本，避免 `latest` 漂移。

### `EMBEDDING_PROVIDER`
- 用途：embedding 提供方标识（用于缓存键和审计字段）。
- 场景：多 provider 并存时避免缓存串用。
- 建议：当前固定 `ollama`，后续可扩展。

### `EMBEDDING_MODEL`
- 用途：embedding 统一模型标识（用于缓存键和审计字段）。
- 场景：显式与 provider 组合形成缓存命中维度。
- 建议：为空时回退 `OLLAMA_EMBEDDING_MODEL`；生产建议显式设置固定版本。

### `OLLAMA_TIMEOUT_SECONDS`
- 用途：embedding 请求超时（秒）。
- 场景：批量入库和高并发检索保护。
- 建议：`30~120`，CPU 场景可适当调高。

---

## 5. RAG 检索/重排配置

### `RAG_CHUNK_SIZE`
- 用途：切片长度。
- 场景：控制检索粒度与上下文完整度。
- 建议：中文场景 `400~1200` 常见。

### `RAG_CHUNK_OVERLAP`
- 用途：切片重叠长度。
- 场景：跨段语义连续性保留。
- 建议：通常为 `chunk_size` 的 `15%~30%`。

### `RAG_RETRIEVAL_TOP_K`
- 用途：向量粗召回数量。
- 场景：候选池大小控制。
- 建议：CPU 先 `8~12`，质量优先可 `16~24`。

### `RAG_RERANK_TOP_N`
- 用途：重排后保留条数。
- 场景：控制生成上下文噪音与 token 成本。
- 建议：常用 `3~5`。

### `RAG_RERANK_MIN_SCORE`
- 用途：低分过滤阈值。
- 场景：屏蔽弱相关 chunk。
- 建议：从 `0.12~0.20` 起步，配合日志调参。

### `RAG_MIN_CHUNKS_KEEP`
- 用途：全被过滤时保底保留数量。
- 场景：避免“无上下文”导致体验断崖。
- 建议：一般设 `1`，严格拒答可设 `0`。

### `RAG_LOG_RERANK_SCORES`
- 用途：是否输出 rerank 分数快照日志。
- 场景：调优阶段观察分数分布。
- 建议：调参时 `true`，稳定后可按需关闭。

### `RAG_RERANK_SCORE_LOG_MAX_ITEMS`
- 用途：日志中展示的样本条数上限。
- 场景：控制日志体积与可读性。
- 建议：`2~5`。

### `RAG_ENABLE_REWRITE`
- 用途：是否默认开启 query 改写。
- 场景：多轮对话、口语问题增强可检索性。
- 建议：默认开启，超低延迟场景可按请求关闭。

### `RAG_ENABLE_RERANK`
- 用途：是否默认开启精排。
- 场景：高准确问答。
- 建议：默认开启；资源紧张可临时关闭观测收益。

---

## 6. FlashRank 配置

### `FLASHRANK_MODEL_NAME`
- 用途：重排模型名称。
- 场景：按语言和精度需求切换模型。
- 建议：中文优先可评估 `BAAI/bge-reranker-base`。

### `FLASHRANK_CACHE_DIR`
- 用途：模型缓存目录。
- 场景：离线部署、容器重启复用。
- 建议：使用持久化目录。

### `FLASHRANK_OFFLINE_ONLY`
- 用途：仅允许离线加载模型。
- 场景：内网/合规环境禁止在线下载。
- 建议：生产建议 `true`。

### `FLASHRANK_MAX_PASSAGE_CHARS`
- 用途：重排单条候选文本最大长度。
- 场景：限制 CPU 开销并减少长文本噪音。
- 建议：CPU 常见 `600~1200`。

---

## 7. MongoDB 配置

### `MONGODB_URI`
- 用途：Mongo 连接串。
- 场景：聊天历史与画像持久化。
- 建议：生产启用认证、白名单与最小权限账号。

### `MONGODB_DB_NAME`
- 用途：数据库名。
- 场景：按项目/环境隔离数据。
- 建议：不同环境分库，避免污染。

### `MONGODB_CHAT_COLLECTION`
- 用途：聊天消息集合名。
- 场景：会话历史读取与追踪。
- 建议：稳定命名，避免频繁改动。

### `MONGODB_PROFILE_COLLECTION`
- 用途：用户画像集合名。
- 场景：长期偏好、记忆信息存储。
- 建议：与聊天集合分离治理。

### `MONGODB_CHUNK_COLLECTION`
- 用途：文档块元数据集合名。
- 场景：文档管理、版本追踪、删除同步。
- 建议：保持与向量库主键映射一致。

### `MONGODB_EMBEDDING_COLLECTION`
- 用途：embedding 缓存集合名（存向量与 provider/model/text_hash）。
- 场景：跨文档、跨版本复用向量，降低重复 embedding 成本。
- 建议：默认 `kb_embeddings`，上线后保持稳定便于索引治理。

---

## 8. Memory 配置

### `RAG_HISTORY_MAX_TURNS`
- 用途：最大历史轮数。
- 场景：控制上下文长度。
- 建议：常见 `4~10`。

### `MEMORY_ENABLE`
- 用途：记忆功能总开关。
- 场景：多轮持续对话增强。
- 建议：先测试环境验证后上线。

### `MEMORY_PROFILE_ENABLE`
- 用途：画像抽取/注入开关。
- 场景：个性化回复（语言偏好、约束）。
- 建议：涉及隐私时先做合规审查。

### `MEMORY_SHORT_MAX_TOKENS`
- 用途：短期历史 token 上限。
- 场景：防止历史占满上下文窗口。
- 建议：常见 `800~2000`。

### `MEMORY_PROFILE_MAX_ITEMS`
- 用途：注入画像条目最大数量。
- 场景：平衡个性化与主任务信息占比。
- 建议：`3~8`。

---

## 9. Ingest 配置

### `INGEST_MAX_FILE_SIZE_MB`
- 用途：单文件导入大小上限（MB）。
- 场景：保护服务资源，避免超大文件压垮进程。
- 建议：根据机器资源设 `10~50`。

---

## 10. 快速起步推荐（CPU）

```env
RAG_RETRIEVAL_TOP_K=8
RAG_RERANK_TOP_N=3
RAG_RERANK_MIN_SCORE=0.15
RAG_MIN_CHUNKS_KEEP=1
FLASHRANK_MAX_PASSAGE_CHARS=800
RAG_LOG_RERANK_SCORES=true
RAG_RERANK_SCORE_LOG_MAX_ITEMS=3
```

---

## 11. 维护建议

- 统一在 `.env.example` 维护默认值和说明。
- 配置变更采用“单参数逐步调优”，并记录前后指标。
- 涉及模型更换时，固定一组评测问题做回归对比。
