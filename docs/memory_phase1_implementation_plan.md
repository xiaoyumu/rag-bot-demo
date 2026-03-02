# 第一阶段实施方案：短期预算 + 画像记忆（止血版）

本文档定义长短期记忆方案的第一阶段落地计划。目标是以最小改造成本，先解决上下文膨胀问题，并让用户偏好/约束稳定生效。

## 当前实现状态（2026-03-02）

已完成：

- 配置扩展：`MEMORY_ENABLE`、`MEMORY_PROFILE_ENABLE`、`MEMORY_SHORT_MAX_TOKENS`、`MONGODB_PROFILE_COLLECTION`、`MEMORY_PROFILE_MAX_ITEMS`。
- Mongo profile 存储：新增 `get_profile`、`upsert_profile` 与 `session_id` 唯一索引。
- 短期预算裁剪：新增 `PromptBudgetManager`，接入 chat pipeline。
- 规则提取与注入：新增 `extract_profile_patch`、`render_profile_context`，并注入 rewrite/answer prompt。
- 降级保护：profile 读写异常不会中断主链路。
- 可观测性：新增历史裁剪与 profile 命中日志（计数、估算 token、上下文长度）。
- 自动化测试：新增预算裁剪、profile 规则提取与 pipeline 回归测试。

待完成（本阶段剩余）：

- 增补 API 层集成测试覆盖更长会话链路；
- 结合真实运行日志微调 `MEMORY_SHORT_MAX_TOKENS` 默认值；
- 在 README 中补充 memory feature flags 使用说明。

## 1. 阶段目标

- 控制多轮会话入模上下文长度，避免超过 LLM 上下文限制。
- 引入轻量级“画像记忆”（仅偏好/约束），提升回答一致性。
- 保持现有 RAG 主链路稳定，支持 feature flag 一键回退。

## 2. 范围与非目标

### 2.1 本阶段范围

- 短期历史 token 预算裁剪（PromptBudgetManager）。
- Mongo 新增 profile 存储（不引入向量索引）。
- 规则提取偏好/约束并写入 profile。
- 在 rewrite/answer prompt 中注入 profile 上下文。

### 2.2 本阶段不做

- 不做长期记忆（fact/decision）自动抽取。
- 不做 memory item 向量化与语义召回。
- 不做复杂冲突合并与 TTL 淘汰策略。

## 3. 现状问题

当前 `history_messages` 直接拼接到 rewrite 与 answer prompt，存在风险：

- 会话越长，prompt token 越大；
- 低价值历史挤占知识库上下文；
- 用户偏好/约束仅在短期窗口内有效，稳定性不足。

## 4. 设计原则

- 最小侵入：尽量只改 `config`、`pipeline`、`rewrite`、`chains`、`mongodb_chat_store`。
- 可回退：全部能力受 `MEMORY_ENABLE` 和子开关控制。
- 可观测：记录裁剪前后消息数、profile 命中项数与注入长度。
- 先规则后模型：Phase 1 使用规则提取，不依赖额外 LLM 调用。

## 5. 技术方案

### 5.1 短期记忆预算裁剪

新增 `PromptBudgetManager`，对 `history_messages` 做近似 token 预算截断。

建议策略：

1. 以“从近到远”保留历史；
2. 用近似公式估算 token（例如 `len(text) / 2.8`）；
3. 到达预算上限立即停止追加；
4. 至少保留最近一轮用户消息（若存在）。

建议配置：

- `MEMORY_SHORT_MAX_TOKENS=1200`

### 5.2 画像记忆（Profile Memory）

新增 profile 集合（建议：`chat_profiles`），按 `session_id`（可扩展 `user_id`）存储：

```json
{
  "session_id": "xxx",
  "profile": {
    "language": "zh-CN",
    "style": "concise",
    "constraints": ["no_network"]
  },
  "updated_at": "ISO8601"
}
```

### 5.3 规则提取（不依赖 LLM）

从用户输入中匹配常见偏好/约束并更新 profile：

- 语言偏好：中文/英文
- 风格偏好：简洁/详细
- 约束偏好：不要联网、不要猜测、仅基于上下文回答

同 key 采用覆盖更新，`constraints` 采用集合并集去重。

### 5.4 Prompt 注入方式

在 rewrite 与 answer prompt 增加 `Profile context` 段落：

- 有 profile 时注入精简文本；
- 无 profile 时跳过；
- profile 文本优先级高于历史对话。

## 6. 代码改造清单（Phase 1）

## 6.1 配置层

文件：`app/core/config.py`

新增字段：

- `memory_enable: bool`（`MEMORY_ENABLE`）
- `memory_profile_enable: bool`（`MEMORY_PROFILE_ENABLE`）
- `memory_short_max_tokens: int`（`MEMORY_SHORT_MAX_TOKENS`）
- `memory_profile_collection: str`（`MONGODB_PROFILE_COLLECTION`，默认 `chat_profiles`）
- `memory_profile_max_items: int`（`MEMORY_PROFILE_MAX_ITEMS`）

## 6.2 Mongo 存储层

文件：`app/integrations/mongodb_chat_store.py`

新增能力：

- `get_profile(session_id: str) -> dict[str, str | list[str]]`
- `upsert_profile(session_id: str, patch: dict) -> None`
- 为 profile 集合建立 `session_id` 唯一索引。

## 6.3 RAG 服务层

新增文件：`app/services/rag/prompt_budget.py`

- `PromptBudgetManager.trim_history(messages, max_tokens) -> list[dict[str, str]]`

新增文件：`app/services/rag/profile_memory.py`

- `extract_profile_patch(user_text: str) -> dict`
- `render_profile_context(profile: dict, max_items: int) -> str`

改造文件：`app/services/rag/pipeline.py`

- 在获取短期历史后执行预算裁剪；
- 在处理当前问题前提取 profile patch 并 upsert；
- 读取 profile，并传入 rewrite/answer。

改造文件：

- `app/services/rag/rewrite.py`
- `app/services/rag/chains.py`

新增参数 `profile_context: str | None`，并写入 prompt 模板。

## 7. 接口与签名草案

```python
# app/services/rag/prompt_budget.py
class PromptBudgetManager:
    def trim_history(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> list[dict[str, str]]:
        ...
```

```python
# app/services/rag/profile_memory.py
def extract_profile_patch(user_text: str) -> dict:
    ...

def render_profile_context(profile: dict, max_items: int = 6) -> str:
    ...
```

```python
# app/integrations/mongodb_chat_store.py
async def get_profile(self, session_id: str) -> dict:
    ...

async def upsert_profile(self, session_id: str, patch: dict) -> None:
    ...
```

## 8. 配置建议（.env）

建议新增：

- `MEMORY_ENABLE=true`
- `MEMORY_PROFILE_ENABLE=true`
- `MEMORY_SHORT_MAX_TOKENS=1200`
- `MONGODB_PROFILE_COLLECTION=chat_profiles`
- `MEMORY_PROFILE_MAX_ITEMS=6`

## 9. 测试计划

### 9.1 单元测试

- `trim_history` 在不同长度输入下都不超预算；
- `extract_profile_patch` 能识别语言/风格/约束关键词；
- `render_profile_context` 输出稳定、长度可控。

### 9.2 集成测试

- 连续 30+ 轮会话仍能正常返回，不触发上下文超限；
- 用户先说“请用中文且简洁”，后续多轮回答保持一致；
- 开关关闭（`MEMORY_ENABLE=false`）时行为与当前版本一致。

### 9.3 回归风险点

- prompt 结构变化可能影响 rewrite 质量；
- 规则提取误判可能造成不期望风格偏移；
- profile 写入失败需降级为不影响主链路。

## 10. 里程碑与工期建议

- Day 1：配置与 Mongo profile 存储、索引；
- Day 2：PromptBudgetManager 与 pipeline 接入；
- Day 3：规则提取与 prompt 注入改造；
- Day 4：单测、集成测试与开关回退验证；
- Day 5：灰度观察日志指标并微调阈值。

## 11. 验收标准

- 超长会话下 prompt 长度稳定受控；
- 偏好/约束在多轮中可复用；
- 主链路无新增 500 错误；
- 关闭开关可完全回退现状。

---

第一阶段完成后，再进入第二阶段：长期记忆抽取（fact/decision）+ 向量索引召回。
