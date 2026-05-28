# 记忆模型

本模板的记忆 = 一个 `MemoryStore` 接口 + 默认 `InMemoryStore`，挂在图的 recall（turn 起召回）/ write（turn 末写入）两个节点上。

## 数据模型
- `Preference{key,value}`：结构化偏好，KV、latest-wins（同 key 覆写）。
- `Observation{text}`：自由文本观察，保留近期 N 条。
- `RecalledMemory{prefs, observations}`：recall 返回，注入 agent 的 system prompt。

## 流程
`recall_memory` 调 `store.recall(user_id, query)` → 写 `state.recalled_memory` →
agent 拼进 system → `write_memory` 用**确定性抽取**（`memory/extractor.py`，当前只抽昵称，不调 LLM）
把偏好 `upsert` 回 store。图拓扑：`START → {classify ∥ recall} → agent → write → END`。

## 默认实现 InMemoryStore
进程内 dict，always-on 全量召回（不做相似度），重启即丢。零依赖、开箱即用。

## 已提供的 opt-in 实现（P6）
1. **LLM 富抽取**（`memory/llm_extractor.py`）：抽 `response_format/verbosity/tone/answer_style` 等 enum 偏好；fail-soft。开关 `ENABLE_LLM_PREF_EXTRACTION=1`（默认关 → `write_memory` 不打 LLM）。已单测覆盖。
2. **pgvector 语义召回 + 持久化**（`memory/pgvector_store.py` + `embedding.py`）：偏好走 KV 表（`UNIQUE(user_id,key)` latest-wins），观察走 embedding + `<=>` cosine top-k。配 `AGENT_PG_DSN` + `AGENT_EMBED_BASE_URL` + 装 `[pg]` 启用；`AGENT_EMBED_DIM` 默认 1536，换 embedding 模型时要同步改维度。`main.py` lifespan 会调用 `setup_memory_store_from_settings()`，完成 `PgVectorStore.setup()` 后注入全局 store。
   - 只配 `AGENT_PG_DSN` 时只启用 Postgres checkpointer，记忆仍是 in-memory；语义记忆需要同时配 embedding。
   - > ⚠️ **PG/embedding 真集成未经本仓自动化验证**（CI 无 PG）。请在你的真库（装 pgvector）+ embedding 端点上跑 `setup()` + 续聊验证。
   - 初始化失败会关闭已创建的 pool 并回到默认 in-memory store，避免资源泄漏。
   - 刻意不做 ConflictDetector：KV latest-wins 已覆盖高价值偏好；语义层只检索（会漏，符合“高价值偏好走 KV always-on”原则）。

## 再扩展
其它后端实现 `MemoryStore` 协议即可，节点/agent 不改。

> 取舍参考：结构化 KV（精确、always-on、latest-wins）适合“必须每轮生效”的偏好；
> 语义召回（pgvector）适合开放式经验记忆，但召回不保证命中。详见抽取源 talentos-agent
> 的双车道设计。
