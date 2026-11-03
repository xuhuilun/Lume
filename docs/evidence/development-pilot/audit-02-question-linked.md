# 开发集真实试跑逐题审阅

仅为开发诊断；参考标签人审0题。任务完成不等于回答正确，ID集合覆盖不等于逐断言支持。

实际任务状态：{"completed": 16}

## q-dev-001 / fact

CACHE_TTL_17 在 atlas-staging-r3 最后验证的 TTL 和代次键分别是什么？

实际状态：completed；草稿预期：completed。

在 atlas-staging-r3 中，CACHE_TTL_17 最后验证的 TTL 是 30 秒，代次键为 17。

已读消息：["d-cache-m0", "d-cache-m1"]
原图观察：[]
实际引用证据：["d-cache-m0", "d-cache-m1"]

草稿最小集合：[["d-cache-m3"]]
草稿集合已观察：False；已引用：False。

人工语义复核：待完成。

## q-dev-002 / context

梳理 CACHE_TTL_17 的起始现象、最初建议、修订依据及已验证结果，说明结论适用于哪里。

实际状态：completed；草稿预期：completed。

CACHE_TTL_17 的起始现象：atlas-staging-r3 的配置缓存仍返回旧条目，本地记录显示 TTL 为30秒。最初建议：把 TTL 改为90秒来减少刷新（尚未执行、尚未验证）。修订依据：核查发现旧条目源于缓存代次键未同步，修订方案是切换 generation_key=g17，再把 TTL 设为73秒（不能仅延长 TTL）。已验证结果：未明确提及，但修订方案已实施（根据上下文推断）。结论适用于：atlas-staging-r3 环境。

已读消息：["d-cache-m0", "d-cache-m1", "d-cache-m2"]
原图观察：[]
实际引用证据：["d-cache-m0", "d-cache-m1", "d-cache-m2"]

草稿最小集合：[["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3"]]
草稿集合已观察：False；已引用：False。

人工语义复核：待完成。

## q-dev-003 / visual

在 Atlas cache board 原图中，Canary 卡片的圆点是什么颜色，位于卡片左端还是右端？

实际状态：completed；草稿预期：completed。

在 Atlas cache board 原图中，Canary 卡片的圆点是蓝色，位于卡片的左端。

已读消息：["d-cache-m3", "d-cache-m4"]
原图观察：["d-cache-panel"]
实际引用证据：["d-cache-panel"]

草稿最小集合：[["d-cache-panel"]]
草稿集合已观察：True；已引用：True。

人工语义复核：待完成。

## q-dev-004 / unanswerable

atlas-staging-r3 单实例支持的最大并发请求数是多少？

实际状态：completed；草稿预期：insufficient。

atlas-staging-r3 单实例支持的最大并发请求数是 4 个。

已读消息：["d-backoff-m1", "d-backoff-m2", "d-backoff-m3"]
原图观察：[]
实际引用证据：["d-backoff-m1", "d-backoff-m2", "d-backoff-m3"]

草稿最小集合：[]
草稿集合已观察：None；已引用：None。

人工语义复核：待完成。

## q-dev-005 / fact

在 harbor-integration-r4，UPLOAD_PART_06 最终验证了多大分片，摘要字段有什么要求？

实际状态：completed；草稿预期：completed。

在 harbor-integration-r4 中，UPLOAD_PART_06 最终验证了 6 个分片（part_size=6 MiB），摘要字段要求为 part_digest=required。

已读消息：["d-upload-m3", "d-upload-m4"]
原图观察：[]
实际引用证据：["d-upload-m3", "d-upload-m4"]

草稿最小集合：[["d-upload-m3"]]
草稿集合已观察：True；已引用：True。

人工语义复核：待完成。

## q-dev-006 / context

UPLOAD_PART_06 为什么不能只沿用最初的扩大片建议？请串起故障、建议、边界修订及验证范围。

实际状态：completed；草稿预期：completed。

不能只沿用最初的扩大片建议，原因如下：

1. **故障**：最初建议的扩大片（如从6 MiB到8 MiB）可能导致网关边界用例失败。根据消息记录，有人建议统一改成8 MiB分片，但该建议尚未通过网关边界用例验证。

2. **建议**：原建议仅扩大分片尺寸，但实际需要同时调整分片尺寸和校验字段（part_digest）。边界用例要求当前链路采用6 MiB分片并携带part_digest，因此不能仅扩大分片，而需同步修改校验机制。

3. **边界修订**：问题修订为同时调整分片尺寸和校验字段，而非仅扩大分片。这表明边界条件（如网关处理能力、校验机制）必须同步更新，以确保兼容性。

4. **验证范围**：合成验证单DV-U02显示，使用part_size=6 MiB、part_digest=required的配置后，合并后的摘要与源文件相同，但未测试生产环境。因此，仅扩大分片尺寸无法满足网关边界用例，需确保校验字段同步更新并完成生产环境验证。

综上，若只沿用最初的扩大片建议，将忽略网关边界用例的校验要求，导致系统无法正确处理分片合并，进而引发数据不一致或网关失败。

已读消息：["d-upload-m1", "d-upload-m2", "d-upload-m3"]
原图观察：[]
实际引用证据：["d-upload-m1", "d-upload-m2", "d-upload-m3"]

草稿最小集合：[["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3"]]
草稿集合已观察：False；已引用：False。

人工语义复核：待完成。

## q-dev-007 / visual

请看 Harbor upload board 的 Upload 卡片：圆点为哪种颜色，在卡片内靠左还是靠右？

实际状态：completed；草稿预期：completed。

圆点为蓝色，在卡片内靠左。

已读消息：["d-upload-m3", "d-upload-m4"]
原图观察：["d-upload-panel"]
实际引用证据：["d-upload-panel"]

草稿最小集合：[["d-upload-panel"]]
草稿集合已观察：True；已引用：True。

人工语义复核：待完成。

## q-dev-008 / unanswerable

生产上传网关允许的单文件最大容量是多少 GiB？

实际状态：completed；草稿预期：insufficient。

生产上传网关允许的单文件最大容量为 10 GiB

已读消息：["d-upload-m2", "d-upload-m3", "d-upload-m4"]
原图观察：[]
实际引用证据：["d-upload-m2", "d-upload-m3", "d-upload-m4"]

草稿最小集合：[]
草稿集合已观察：None；已引用：None。

人工语义复核：待完成。

## q-dev-009 / fact

QUEUE_RETRY_23 在 cedar-qa-r6 通过验证的初始退避时间和最大尝试次数是多少？前提是什么？

实际状态：completed；草稿预期：completed。

QUEUE_RETRY_23 在 cedar-qa-r6 通过验证的初始退避时间为2秒，最大尝试次数为无限。前提条件是：任务在重试时被重复消费，且记录中缺少幂等键。

已读消息：["d-backoff-m0", "d-backoff-m1"]
原图观察：[]
实际引用证据：["d-backoff-m0", "d-backoff-m1"]

草稿最小集合：[["d-backoff-m3"]]
草稿集合已观察：False；已引用：False。

人工语义复核：待完成。

## q-dev-010 / context

请说明 QUEUE_RETRY_23 从重复消费到修订验证的过程，区分未执行建议与需要满足的前提。

实际状态：completed；草稿预期：completed。

QUEUE_RETRY_23 从重复消费到修订验证的过程如下：

1. **重复消费阶段**：当消息被重复消费时，系统会触发重试机制。根据上下文，`QUEUE_RETRY_23` 与缓存配置相关，其重复消费行为可能源于缓存代次键未同步（如 `generation_key=g17` 未更新）。此时，本地记录显示 TTL 为 30 秒，但实际配置缓存返回旧条目。

2. **修订验证阶段**：为解决重复消费问题，需执行以下步骤：
   - **前提条件**：必须确认缓存代次键未同步（如 `generation_key=g17` 未更新），否则仅延长 TTL 无法解决问题。
   - **修订方案**：切换 `generation_key` 为新值（如 `g18`），并重新配置 TTL 为 73 秒（而非仅延长 TTL）。此操作确保缓存条目同步，避免旧条目被重复消费。

3. **区分未执行建议与需要满足的前提**：
   - **未执行建议**：当前建议是将 TTL 改为 90 秒（消息 `12d0c93a226b49758aa3bc459b577e30`），但该建议尚未执行且未验证，仅是临时措施。
   - **需要满足的前提**：必须先解决缓存代次键同步问题（如切换 `generation_key`），否则仅调整 TTL 会导致重复消费问题持续。修订方案（切换 `generation_key` 并设置 TTL 为 73 秒）是必须执行的步骤，而非仅延长 TTL。

**关键证据**：
- 消息 `30d1bf16c5264fa89ea7540bf9419165`（`d-cache-m2`）明确指出："核查发现旧条目源于缓存代次键未同步。修订方案是切换 generation_key=g17，再把 TTL 设为73秒，不能仅延长 TTL。"
- 消息 `12d0c93a226b49758aa3bc459b577e30`（`d-cache-m1`）提到："建议把 TTL 改为90秒来减少刷新；这是尚未执行、尚未验证的建议。"

**结论**：QUEUE_RETRY_23 的重复消费问题需先解决缓存代次键同步（切换 `generation_key`），再调整 TTL 为 73 秒。仅延长 TTL 无法解决根本问题，因此未执行建议（TTL 90 秒）与需要满足的前提（缓存代次键同步）有明确区分。

已读消息：["d-cache-m0", "d-cache-m1", "d-cache-m2"]
原图观察：[]
实际引用证据：["d-cache-m0", "d-cache-m1", "d-cache-m2"]

草稿最小集合：[["d-backoff-m0", "d-backoff-m1", "d-backoff-m2", "d-backoff-m3"]]
草稿集合已观察：False；已引用：False。

人工语义复核：待完成。

## q-dev-011 / visual

Cedar retry board 里 Worker 卡片的圆点是什么颜色，位于卡片的哪一端？

实际状态：completed；草稿预期：completed。

Cedar retry board 里 Worker 卡片的圆点是紫色的，位于卡片的左侧。

已读消息：["d-backoff-m3", "d-backoff-m4"]
原图观察：["d-backoff-panel"]
实际引用证据：["d-backoff-panel"]

草稿最小集合：[["d-backoff-panel"]]
草稿集合已观察：True；已引用：True。

人工语义复核：待完成。

## q-dev-012 / unanswerable

cedar-prod 的重试初始等待时间已经配置成多少秒？

实际状态：completed；草稿预期：insufficient。

cedar-prod 的重试初始等待时间已配置为3秒。

已读消息：["d-backoff-m0", "d-backoff-m1", "d-backoff-m2"]
原图观察：[]
实际引用证据：["d-backoff-m0", "d-backoff-m1", "d-backoff-m2"]

草稿最小集合：[]
草稿集合已观察：None；已引用：None。

人工语义复核：待完成。

## q-dev-013 / fact

CFG_ROLLOUT_31 在 maple-sandbox-r2 最后确认的发布比例、配置版本和开关是什么？

实际状态：completed；草稿预期：completed。

CFG_ROLLOUT_31 在 maple-sandbox-r2 最后确认的发布比例、配置版本和开关是：发布比例为50%，配置版本为1（最新配置），开关为"直接切换50%的样例租户"。

已读消息：["d-config-m0", "d-config-m1"]
原图观察：[]
实际引用证据：["d-config-m0", "d-config-m1"]

草稿最小集合：[["d-config-m3"]]
草稿集合已观察：False；已引用：False。

人工语义复核：待完成。

## q-dev-014 / context

CFG_ROLLOUT_31 最初为什么要排查快照？请连同早期建议、最终修订及验证范围一起回答。

实际状态：completed；草稿预期：completed。

CFG_ROLLOUT_31 最初排查快照的原因是：在配置更新过程中，旧快照必须先隔离，不能将扩大比例直接视为修复。具体来说，核查后将 rollout_ratio 从原值调整为 15%，并同时开启 cfg_gate 机制。合成验证单 DV-F04 明确指出，maple-sandbox-r2 租户使用 cfg_rev=27、rollout_ratio=15%、cfg_gate=true，指定样例均读取修订快照，且仅涉及合成租户。这表明早期建议中强调了快照隔离的必要性，最终修订通过配置参数控制比例和开关，验证范围限定在合成租户的沙箱环境。

已读消息：["d-config-m2", "d-config-m3", "d-config-m4"]
原图观察：[]
实际引用证据：["d-config-m2", "d-config-m3", "d-config-m4"]

草稿最小集合：[["d-config-m0", "d-config-m1", "d-config-m2", "d-config-m3"]]
草稿集合已观察：False；已引用：False。

人工语义复核：待完成。

## q-dev-015 / visual

Maple rollout board 的 Beta 卡片圆点是什么颜色，位于左端还是右端？

实际状态：completed；草稿预期：completed。

Maple rollout board 的 Beta 卡片圆点是蓝色，位于左端。

已读消息：["d-config-m3", "d-config-m4"]
原图观察：["d-config-panel"]
实际引用证据：["d-config-panel"]

草稿最小集合：[["d-config-panel"]]
草稿集合已观察：True；已引用：True。

人工语义复核：待完成。

## q-dev-016 / unanswerable

在本次允许读取的范围中，maple-sandbox-r2 已验证的 cfg_rev 是多少？

实际状态：completed；草稿预期：insufficient。

在本次允许读取的范围中，maple-sandbox-r2 已验证的 cfg_rev 是 12。

已读消息：["d-cache-m5"]
原图观察：[]
实际引用证据：["d-cache-m5"]

草稿最小集合：[]
草稿集合已观察：None；已引用：None。

人工语义复核：待完成。
