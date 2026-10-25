# 原生插件配置

入口：AstrBot → 插件 → **NekoNekoNin · 天使之魂增强版** → **配置**。本版不新增独立 Web 设置页。

以 AstrBot 4.29.1 的原生配置组件核对下拉标签、滑块、条件显示与高级折叠。配置键保持兼容；保存会重载插件，正在处理的请求应先完成。

| 配置键 | 界面名称 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `provider_id` | 基础 · 记忆整理模型 | （留空） | 选择已配置的聊天模型，用于记忆整理与反馈；留空时不具备完整的自动整理能力。 |
| `conversation_scope_map` | [旧版兼容项] 会话映射（严格隔离版不使用共享映射） | "{}" | 保留旧版配置兼容；增强版使用完整会话来源隔离记忆，不通过此项合并群或私聊。 |
| `retrieval.embedding_provider_id` | 用于向量化的嵌入模型提供商ID（可选） | （留空） | 填写已配置的嵌入模型提供商 ID；留空时仍可使用关键词检索。不能用不支持嵌入的聊天模型代替。 |
| `retrieval.rerank_provider_id` | 用于检索重排的提供商ID（推荐） | （留空） | 可选，用于重新排列检索候选；留空时按运行时的可用能力回退。请核对提供商是否支持重排。 |
| `retrieval.enable_local_embedding` | 启用本地嵌入模型支持 | false | 开启后将使用本地嵌入模型（BAAI/bge-small-zh-v1.5）。并非必须，实测整体提升有限。 |
| `retrieval.embedding_batch_size` | 向量请求批次大小 | 50 | 单次向量请求包含的文本条数。部分提供商（如 DashScope）限制较小，超限时会自动减半重试。 |
| `retrieval.embedding_timeout` | 向量请求超时时间（秒） | 5 | 单次向量请求的超时时间，超时后会重试或报错。范围 5-120 秒。 |
| `retrieval.rerank_max_docs` | 重排候选数量上限 | 64 | 送入重排模型的候选数上限，超过按 BM25 顺序截断。bge-reranker-v2-m3 建议 ≤64，实测 90 段 1.1s 可过，243 段 2s 超时。 |
| `retrieval.rerank_max_tokens_per_doc` | 重排单段 token 上限 | 1024 | 单段送入重排前的 token 截断预算，bge-reranker-v2-m3 硬上限 8192/对，推荐 1024，超限按 0.25/0.48 估算截断。 |
| `memory_behavior.important_memory_immediate` | 重要信息优先整理 | true | 本轮用户明确要求记住、表达具体稳定偏好、提出约定或更正信息时，回复后立即提交后台整理；仍由模型筛选，不会把每句话直接保存。 |
| `memory_behavior.reflection_turn_threshold` | 普通聊天累计整理轮数 | 3 | 普通内容累计到此轮数后整理，建议范围 1–20；重要信息优先整理不受此轮数限制。 |
| `memory_behavior.reflection_idle_seconds` | 停聊后整理等待秒数 | 30 | 有未整理内容且会话空闲达到此时间后可整理；扫描周期和模型繁忙情况会影响实际完成时间。 |
| `memory_behavior.reflection_tick_seconds` | 待整理内容检查周期秒数 | 10 | 最小 10 秒；检查当前会话的重要信息、已累计轮数和空闲内容。 |
| `memory_behavior.default_passive_strength` | 被动记忆的初始强度值 | 10 | 此数值影响被动记忆在遗忘过程中的存活能力，推荐范围10-50。主动记忆不受此影响。 |
| `memory_behavior.min_message_length` | 触发记忆处理的最小消息字符数 | 5 | 过滤过短的消息，以提高记忆质量。 |
| `memory_behavior.short_term_memory_capacity` | 短期记忆通道的容量倍数 | 1 | 设置为2则容量翻倍，设置为3则容量变为3倍。 |
| `enable_soul_system.enabled` | 启用灵魂系统 | true | 是否启用灵魂状态系统 |
| `enable_soul_system.recall_depth_mid` | 社交倾向-回归值 (建议检索记忆数) | 7 | 决定内向／外向人格的基准值，影响检索记忆的数量。范围：3-20（系统自动限制） |
| `enable_soul_system.impression_depth_mid` | 对话姿态-回归值 (建议生成记忆数) | 3 | 决定指导／好奇人格的基准值，影响生成新记忆的数量。范围：1-10（系统自动限制） |
| `enable_soul_system.expression_desire_mid` | 健谈程度-回归值 (归一化) | 0.5 | 决定话少／话多人格的基准值，影响发言长度。范围：0.0-1.0（系统自动限制） |
| `enable_soul_system.creativity_mid` | 创造性-回归值 (归一化) | 0.7 | 决定严肃／调皮人格的基准值，影响LLM温度参数。范围：0.0-1.0（系统自动限制） |
| `note_assistant.enable_recall` | 在增强检索中检索笔记 | true | 开启后，回忆记忆时会一并检索笔记知识库并注入相关笔记；关闭则增强检索不再涉及笔记。 |
| `note_assistant.enable_create` | 允许 AI 自主生成笔记 | true | 开启后会向 LLM 注册 angel_note_create 工具，AI 可在学习或交流中主动整理并归档笔记；关闭则不注册该工具。 |
| `note_assistant.top_k` | 注入LLM的笔记数量上限 | 3 | 控制实际注入给应答模型的笔记条数。建议 3-20。 |
| `memory_behavior.decay_policy_override.enabled` | 启用自定义遗忘策略参数 | false | 关闭时完全使用系统默认参数。 |
| `memory_behavior.decay_policy_override.tier0_threshold` | T0->T1 升档阈值（useful_score） | 3.0 | 达到该分数后，记忆从自然遗忘档升到召回判定档。 |
| `memory_behavior.decay_policy_override.tier1_threshold` | T1->T2 升档阈值（useful_score） | 10.0 | 达到该分数后进入长期保留档。建议不小于 tier0_threshold。 |
| `memory_behavior.decay_policy_override.consolidate_speed` | 每次被判定有用时 useful_score 增量 | 2.5 | 值越大，记忆升档越快。建议范围 0.5-5.0，必须 > 0。 |
| `memory_behavior.decay_policy_override.forget_speed` | 全局遗忘速度倍率 | 1.0 | 值越大，整体遗忘越快。建议范围 0.5-3.0。 |
| `memory_behavior.decay_policy_override.tier0_forget_speed` | T0（自然遗忘档）遗忘速度倍率 | 1.0 | 与 forget_speed 相乘后作用于 T0 自然衰减周期。 |
| `memory_behavior.decay_policy_override.cycle_tier0_days` | T0 自然遗忘基础周期（天） | 3 | 实际周期会按 forget_speed 与 tier0_forget_speed 调整。 |
