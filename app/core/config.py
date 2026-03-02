from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 用途：应用名称，用于日志标识、监控标签、部署识别。
    # 场景：多服务部署时区分不同服务；接入监控系统时作为 service name。
    # 建议：保持稳定，不要频繁变更；可按“项目名-环境”命名。
    app_name: str = Field(default="rag-bot-demo", alias="APP_NAME")
    # 用途：运行环境标识（如 dev/test/prod）。
    # 场景：按环境切换配置、日志级别、外部依赖地址。
    # 建议：本地开发用 dev，测试环境用 test，生产用 prod。
    app_env: str = Field(default="dev", alias="APP_ENV")
    # 用途：Web 服务监听地址。
    # 场景：容器内通常监听 0.0.0.0；本机单机调试可用 127.0.0.1。
    # 建议：Docker/K8s 使用 0.0.0.0，避免外部无法访问容器服务。
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    # 用途：Web 服务监听端口。
    # 场景：本地调试、反向代理转发、容器端口映射。
    # 建议：开发常用 8000；生产按网关规划统一端口策略。
    app_port: int = Field(default=8000, alias="APP_PORT")
    # 用途：日志输出级别。
    # 场景：排查问题时提升到 DEBUG；日常运行保持 INFO 或 WARNING。
    # 建议：生产用 INFO，短期问题定位可临时切 DEBUG，结束后恢复。
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # 用途：Weaviate HTTP 地址，用于集合管理与查询请求。
    # 场景：本地单机、内网服务、云端托管向量库。
    # 建议：开发环境指向本地；生产使用内网地址并配合鉴权。
    weaviate_url: str = Field(default="http://localhost:8080", alias="WEAVIATE_URL")
    # 用途：Weaviate API Key 鉴权令牌。
    # 场景：托管 Weaviate 或启用鉴权的私有部署。
    # 建议：有鉴权必须配置；敏感值放 .env，不要写入代码仓库。
    weaviate_api_key: str = Field(default="", alias="WEAVIATE_API_KEY")
    # 用途：知识块集合名（类似表名）。
    # 场景：单知识库或多知识库隔离时区分集合。
    # 建议：上线后尽量稳定，变更会影响旧数据读写与迁移成本。
    weaviate_collection: str = Field(default="KnowledgeChunk", alias="WEAVIATE_COLLECTION")
    # 用途：Weaviate gRPC 主机地址（高性能查询通道）。
    # 场景：启用 gRPC 的查询/写入性能优化。
    # 建议：通常与 WEAVIATE_URL 同主机；云环境按服务发现地址配置。
    weaviate_grpc_host: str = Field(default="localhost", alias="WEAVIATE_GRPC_HOST")
    # 用途：Weaviate gRPC 端口。
    # 场景：默认 50051；若网关转发或安全策略变更需同步调整。
    # 建议：与服务端实际暴露端口保持一致。
    weaviate_grpc_port: int = Field(default=50051, alias="WEAVIATE_GRPC_PORT")
    # 用途：是否使用 TLS 连接 Weaviate gRPC。
    # 场景：公网/跨网段建议开启；内网隔离环境可按需关闭。
    # 建议：生产尽量 true，本地开发可 false 简化联调。
    weaviate_grpc_secure: bool = Field(default=False, alias="WEAVIATE_GRPC_SECURE")

    # 用途：DeepSeek API 基础地址。
    # 场景：官方服务或兼容网关代理。
    # 建议：默认官方地址；接企业网关时改为内部代理地址。
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    # 用途：DeepSeek 鉴权密钥。
    # 场景：调用改写与生成模型时鉴权。
    # 建议：必须放 .env，生产使用密钥管理系统轮换。
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    # 用途：聊天生成模型名。
    # 场景：按质量/成本切换模型规格。
    # 建议：先固定一个稳定模型，评测后再做灰度切换。
    deepseek_chat_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_CHAT_MODEL")
    # 用途：DeepSeek 请求超时秒数。
    # 场景：网络抖动、长回答、上游拥塞时控制失败等待时间。
    # 建议：一般 30~90；过小易误超时，过大影响用户等待体验。
    deepseek_timeout_seconds: int = Field(default=60, alias="DEEPSEEK_TIMEOUT_SECONDS")

    # 用途：Ollama 服务地址（用于 embedding）。
    # 场景：本机模型服务、局域网模型网关。
    # 建议：本地部署优先 localhost，远程部署请走内网专线。
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    # 用途：Embedding 模型名称。
    # 场景：切换向量模型以平衡召回质量与速度。
    # 建议：上线前固定版本，避免“latest”漂移带来召回波动。
    ollama_embedding_model: str = Field(default="nomic-embed-text-v2-moe:latest", alias="OLLAMA_EMBEDDING_MODEL")
    # 用途：Embedding 提供方标识（用于缓存键与审计）。
    # 场景：未来引入多 embedding 供应商时做统一标识与复用隔离。
    # 建议：当前使用 ollama，后续可扩展为 openai/azure 等。
    embedding_provider: str = Field(default="ollama", alias="EMBEDDING_PROVIDER")
    # 用途：Embedding 统一模型标识（用于缓存键与审计）。
    # 场景：兼容旧配置；未显式设置时回退到 OLLAMA_EMBEDDING_MODEL。
    # 建议：建议显式配置固定版本，避免模型漂移影响缓存命中。
    embedding_model: str = Field(default="", alias="EMBEDDING_MODEL")
    # 用途：Ollama embedding 请求超时秒数。
    # 场景：批量入库或高并发检索时控制等待上限。
    # 建议：30~120 视机器性能调整，CPU 环境可适当放宽。
    ollama_timeout_seconds: int = Field(default=60, alias="OLLAMA_TIMEOUT_SECONDS")

    # 用途：文档切片最大字符长度。
    # 场景：入库分块时控制每块信息密度。
    # 建议：中文场景常见 400~1200；过大会稀释检索精度，过小会丢上下文。
    rag_chunk_size: int = Field(default=1000, alias="RAG_CHUNK_SIZE")
    # 用途：相邻切片重叠字符数。
    # 场景：跨段语义连续性保留，减少边界信息断裂。
    # 建议：一般为 chunk_size 的 15%~30%。
    rag_chunk_overlap: int = Field(default=200, alias="RAG_CHUNK_OVERLAP")
    # 用途：向量检索粗召回数量（Top-K）。
    # 场景：候选池太小会漏召回，太大增加 rerank 成本。
    # 建议：CPU 环境先用 8~12，质量优先可提升到 16~24。
    rag_retrieval_top_k: int = Field(default=8, alias="RAG_RETRIEVAL_TOP_K")
    # 用途：重排后保留给生成模型的候选数（Top-N）。
    # 场景：控制上下文噪音与 token 成本。
    # 建议：常用 3~5；复杂问答可提高到 6~8。
    rag_rerank_top_n: int = Field(default=4, alias="RAG_RERANK_TOP_N")
    # 用途：rerank 最低分阈值，低于该值的候选会被过滤。
    # 场景：减少弱相关 chunk 干扰回答。
    # 建议：从 0.12~0.20 试起，结合日志分布逐步微调。
    rag_rerank_min_score: float = Field(default=0.15, alias="RAG_RERANK_MIN_SCORE")
    # 用途：当全部低于阈值时，最少保留的 chunk 数量。
    # 场景：防止“全过滤”导致无上下文无法作答。
    # 建议：一般设 1；若希望严格拒答可设 0。
    rag_min_chunks_keep: int = Field(default=1, alias="RAG_MIN_CHUNKS_KEEP")
    # 用途：是否记录 rerank 分数快照日志。
    # 场景：调参期观测分数分布；稳定后可关闭减少日志量。
    # 建议：调优阶段 true，生产稳定期可按需关闭。
    rag_log_rerank_scores: bool = Field(default=True, alias="RAG_LOG_RERANK_SCORES")
    # 用途：每次日志中最多展示多少条 top 分数样本。
    # 场景：控制日志可读性与体积。
    # 建议：2~5 即可，过大价值不高且增加日志噪音。
    rag_rerank_score_log_max_items: int = Field(default=3, alias="RAG_RERANK_SCORE_LOG_MAX_ITEMS")
    # 用途：是否启用问题改写（rewrite）。
    # 场景：多轮对话、口语问题、上下文不完整问题更需要改写。
    # 建议：默认开启；若追求极低时延可按请求关闭。
    rag_enable_rewrite: bool = Field(default=True, alias="RAG_ENABLE_REWRITE")
    # 用途：是否启用 rerank 精排。
    # 场景：对答案准确性要求高时建议开启。
    # 建议：默认开启；性能受限时可临时关闭观察延迟收益。
    rag_enable_rerank: bool = Field(default=True, alias="RAG_ENABLE_RERANK")
    # 用途：FlashRank 模型名称。
    # 场景：切换英文/中文/多语 reranker。
    # 建议：中文优先可考虑 bge-reranker 系列，并做离线评测后定版。
    flashrank_model_name: str = Field(default="ms-marco-MiniLM-L-12-v2", alias="FLASHRANK_MODEL_NAME")
    # 用途：FlashRank 模型缓存目录。
    # 场景：离线运行、容器持久化、预热加载。
    # 建议：使用持久化目录，避免重启后重复下载/拷贝模型。
    flashrank_cache_dir: str = Field(default=".cache/flashrank", alias="FLASHRANK_CACHE_DIR")
    # 用途：FlashRank 是否只允许离线模型加载。
    # 场景：生产内网、无外网环境、合规要求禁止在线下载。
    # 建议：生产 true；开发可按需 false 便于首次拉取模型。
    flashrank_offline_only: bool = Field(default=True, alias="FLASHRANK_OFFLINE_ONLY")
    # 用途：传给 reranker 的单条候选最大字符数。
    # 场景：避免过长片段拉高 CPU 时延并稀释相关性。
    # 建议：CPU 场景 600~1200；质量优先可适度调高。
    flashrank_max_passage_chars: int = Field(default=1200, alias="FLASHRANK_MAX_PASSAGE_CHARS")
    # 用途：MongoDB 连接串。
    # 场景：保存会话消息、用户画像等持久化数据。
    # 建议：生产启用账号密码和网络白名单，优先走内网连接。
    mongodb_uri: str = Field(default="mongodb://localhost:27017", alias="MONGODB_URI")
    # 用途：MongoDB 数据库名。
    # 场景：按项目或环境隔离数据。
    # 建议：不同环境使用不同库名，避免测试污染生产数据。
    mongodb_db_name: str = Field(default="rag_bot_demo", alias="MONGODB_DB_NAME")
    # 用途：聊天消息集合名。
    # 场景：会话历史读取、上下文拼接。
    # 建议：上线后保持稳定，迁移时配套脚本。
    mongodb_chat_collection: str = Field(default="chat_messages", alias="MONGODB_CHAT_COLLECTION")
    # 用途：用户画像/偏好信息集合名。
    # 场景：长期记忆、个性化回复风格。
    # 建议：与 chat 集合分离，便于独立治理与索引优化。
    mongodb_profile_collection: str = Field(default="chat_profiles", alias="MONGODB_PROFILE_COLLECTION")
    # 用途：文档块元数据集合名（与向量库配合）。
    # 场景：文档管理、版本追踪、删除同步。
    # 建议：与向量库数据建立可追踪主键映射。
    mongodb_chunk_collection: str = Field(default="kb_chunks", alias="MONGODB_CHUNK_COLLECTION")
    # 用途：Embedding 缓存集合名（存向量与 provider/model 元数据）。
    # 场景：跨文档复用 embedding，减少重复向量化开销。
    # 建议：上线后尽量稳定命名，便于索引维护与容量评估。
    mongodb_embedding_collection: str = Field(default="kb_embeddings", alias="MONGODB_EMBEDDING_COLLECTION")
    # 用途：保留多少轮历史对话参与 chat。
    # 场景：控制 token 成本与上下文长度。
    # 建议：常见 4~10；复杂任务可提高，注意时延和成本。
    rag_history_max_turns: int = Field(default=6, alias="RAG_HISTORY_MAX_TURNS")
    # 用途：是否启用 memory（短期/长期记忆功能总开关）。
    # 场景：需要多轮连续理解和用户偏好记忆时开启。
    # 建议：先在测试环境开启验证，再逐步放量到生产。
    memory_enable: bool = Field(default=False, alias="MEMORY_ENABLE")
    # 用途：是否启用用户画像抽取与注入。
    # 场景：需要个性化回复、语言偏好、约束偏好时开启。
    # 建议：隐私合规场景要先做字段审查与脱敏策略。
    memory_profile_enable: bool = Field(default=False, alias="MEMORY_PROFILE_ENABLE")
    # 用途：短期历史可用 token 上限。
    # 场景：防止历史过长挤占知识库上下文窗口。
    # 建议：常见 800~2000；结合模型上下文长度整体规划。
    memory_short_max_tokens: int = Field(default=1200, alias="MEMORY_SHORT_MAX_TOKENS")
    # 用途：注入回答的画像条目最大数量。
    # 场景：控制画像信息对提示词的占用。
    # 建议：3~8 较常见，过多会分散模型注意力。
    memory_profile_max_items: int = Field(default=6, alias="MEMORY_PROFILE_MAX_ITEMS")
    # 用途：单文件导入大小限制（MB）。
    # 场景：保护服务避免超大文件导致内存/CPU 压力。
    # 建议：结合机器资源设置，常见 10~50MB。
    ingest_max_file_size_mb: int = Field(default=20, alias="INGEST_MAX_FILE_SIZE_MB")

    # 用途：指定环境变量文件和编码，忽略未定义额外字段。
    # 场景：本地开发快速加载 .env；线上也可由系统环境变量覆盖。
    # 建议：保持 utf-8，便于中文配置注释和跨平台一致性。
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
