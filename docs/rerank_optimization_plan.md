# Rerank 优化方案（FlashRank）

本文档沉淀当前项目的 `rerank` 优化策略，便于后续持续调参与复盘。  
目标：在可控延迟下，提升 `score` 对“真实相关性”的区分能力。

---

## 1. 当前实现概览

当前聊天链路中的精排阶段：

1. 向量检索返回候选 chunks（含 `distance`）
2. FlashRank 对候选重排，输出 `score`
3. 按 `RAG_RERANK_MIN_SCORE` 过滤低分
4. 若全部被过滤，按 `RAG_MIN_CHUNKS_KEEP` 保底
5. 进入答案生成

说明：

- `distance`：向量距离（Weaviate 返回）
- `score`：FlashRank 相关性分（用于展示与过滤）

---

## 2. 已落地的优化项

### 2.1 低分过滤 + 保底策略

- 新增配置：
  - `RAG_RERANK_MIN_SCORE`（默认 `0.15`）
  - `RAG_MIN_CHUNKS_KEEP`（默认 `1`）
- 行为：
  - `score < min_score` 的 chunk 会被过滤
  - 若全部过滤，保留前 `min_keep` 条，避免无上下文

### 2.2 问候语短路（降低无效检索）

- 对 `hi/hello/你好/在吗` 等纯寒暄直接走友好回复
- 不触发 rewrite/retrieve/rerank
- 降低无意义请求的平均时延与资源占用

### 2.3 UI 可观测性优化

- 返回并展示 `rewritten_query`（改写后的问题）
- 引用区默认折叠，仅展示：
  - 文件名
  - chunk 位置
  - score
- 点击后展开查看 `source/document_id/chunk 文本`

### 2.4 FlashRank 输入增强

- 传入重排文本由“仅正文”改为“`source + content`”
- 新增长度裁剪配置：
  - `FLASHRANK_MAX_PASSAGE_CHARS`（默认 `1200`）
- 目的：减少长文本噪音，提升 score 稳定性

### 2.5 分数快照日志

- 新增配置：
  - `RAG_LOG_RERANK_SCORES`（默认 `true`）
  - `RAG_RERANK_SCORE_LOG_MAX_ITEMS`（默认 `3`）
- 日志内容：
  - count/scored/min/max/avg
  - top 若干条 `source:score`
  - query 摘要
- 用途：基于真实分布校准阈值

---

## 3. 推荐模型候选（中文场景）

优先候选：

1. `BAAI/bge-reranker-base`
   - 中文效果通常明显优于 `ms-marco-MiniLM-L-12-v2`
   - 精度/速度较平衡，适合 CPU 环境起步
2. `BAAI/bge-reranker-v2-m3`
   - 多语与复杂语义匹配更强
   - 资源开销更高，延迟通常更大

建议：

- 先用 `BAAI/bge-reranker-base` 完成稳定上线
- 再做 A/B 对比评估是否升级到 `v2-m3`

---

## 4. 两套参数模板

### 4.1 低延迟优先（CPU 友好）

```env
FLASHRANK_MODEL_NAME=BAAI/bge-reranker-base
RAG_RETRIEVAL_TOP_K=8
RAG_RERANK_TOP_N=3
FLASHRANK_MAX_PASSAGE_CHARS=700

RAG_RERANK_MIN_SCORE=0.18
RAG_MIN_CHUNKS_KEEP=1

RAG_LOG_RERANK_SCORES=true
RAG_RERANK_SCORE_LOG_MAX_ITEMS=2
```

### 4.2 高准确优先（可接受更高延迟）

```env
FLASHRANK_MODEL_NAME=BAAI/bge-reranker-base
RAG_RETRIEVAL_TOP_K=16
RAG_RERANK_TOP_N=5
FLASHRANK_MAX_PASSAGE_CHARS=1200

RAG_RERANK_MIN_SCORE=0.12
RAG_MIN_CHUNKS_KEEP=1

RAG_LOG_RERANK_SCORES=true
RAG_RERANK_SCORE_LOG_MAX_ITEMS=5
```

---

## 5. 调参方法（建议流程）

1. 固定模型（先 `bge-reranker-base`）
2. 先定延迟预算（例如 P95 < 1.2s）
3. 在预算内调 `top_k/top_n/max_passage_chars`
4. 观察分数快照日志分布
5. 每次仅调整 `RAG_RERANK_MIN_SCORE` 一个参数（步进 `0.02`）
6. 记录问答样例命中率与主观质量

原则：

- 候选不足时优先调大 `top_k`
- 误召回多时优先调高 `min_score`
- 时延过高优先减小 `max_passage_chars` 和 `top_k`

---

## 6. 常见问题与排查

### 6.1 score 普遍偏低

- 检查模型是否适合中文（MS MARCO 英文模型常见）
- 检查 chunk 是否过长或噪音多
- 检查 rewrite 是否丢失关键实体词

### 6.2 命中率低但分数看起来“正常”

- 问题通常在“候选集质量”而非 rerank 本身
- 先提升召回：适当增加 `RAG_RETRIEVAL_TOP_K`

### 6.3 时延高

- 降低 `RAG_RETRIEVAL_TOP_K`
- 降低 `FLASHRANK_MAX_PASSAGE_CHARS`
- 降低 `RAG_RERANK_TOP_N`

---

## 7. 后续可迭代项

1. 混合检索（向量 + 关键词/BM25）后统一 rerank
2. 加入离线评测集（50~200 条）做版本回归
3. 对分数做业务阈值分层（强相关/弱相关/不采用）

---

## 8. 一句话结论

在本项目中，提升 FlashRank score 准确度的最有效路径是：  
**先换中文更强模型，再通过“候选质量 + 输入长度 + 分数日志”进行数据化调参。**
