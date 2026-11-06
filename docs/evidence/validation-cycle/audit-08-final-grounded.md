# 开发集真实试跑逐题审阅

仅为开发诊断；参考标签人审0题。任务完成不等于回答正确，ID集合覆盖不等于逐断言支持。

实际任务状态：{"completed": 12, "insufficient": 4}

## q-dev-001 / fact

CACHE_TTL_17 在 atlas-staging-r3 最后验证的 TTL 和代次键分别是什么？

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 消息 d-cache-m3
合成验证单 DV-C01：atlas-staging-r3 已使用 generation_key=g17、TTL=73秒，指定旧条目用例不再复现；本结论仅覆盖该测试环境。

已读消息：["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3", "d-cache-m4"]
原图观察：[]
引用容器所含证据：["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3", "d-cache-m4"]
实际选择展示：["d-cache-m3"]
送入核查的提议来源：["d-cache-m3"]

草稿最小集合：[["d-cache-m3"]]
草稿集合已观察：True；已引用：True。

草稿集合已选中展示：True。
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": ["atlas-staging-r3"]}, "assessment": {"fact": {"quotes": [{"quote": "合成验证单 DV-C01：atlas-staging-r3 已使用 generation_key=g17、TTL=73秒，指定旧条目用例不再复现；本结论仅覆盖该测试环境。", "source": "S1"}], "verdict": "supported"}, "unit": {"quotes": [{"quote": "合成验证单 DV-C01：atlas-staging-r3 已使用 generation_key=g17、TTL=73秒，指定旧条目用例不再复现；本结论仅覆盖该测试环境。", "source": "S1"}], "verdict": "supported"}, "scope": {"quotes": [{"quote": "合成验证单 DV-C01：atlas-staging-r3 已使用 generation_key=g17、TTL=73秒，指定旧条目用例不再复现；本结论仅覆盖该测试环境。", "source": "S1"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "合成验证单 DV-C01：atlas-staging-r3 已使用 generation_key=g17、TTL=73秒，指定旧条目用例不再复现；本结论仅覆盖该测试环境。", "source": "S1"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-002 / context

梳理 CACHE_TTL_17 的起始现象、最初建议、修订依据及已验证结果，说明结论适用于哪里。

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 消息 d-cache-m0
合成事件 CACHE_TTL_17：atlas-staging-r3 的配置缓存仍返回旧条目，本地记录显示 TTL 为30秒。

2. 消息 d-cache-m1
建议把 TTL 改为90秒来减少刷新；这是尚未执行、尚未验证的建议。

3. 消息 d-cache-m2
核查发现旧条目源于缓存代次键未同步。修订方案是切换 generation_key=g17，再把 TTL 设为73秒，不能仅延长 TTL。

4. 消息 d-cache-m3
合成验证单 DV-C01：atlas-staging-r3 已使用 generation_key=g17、TTL=73秒，指定旧条目用例不再复现；本结论仅覆盖该测试环境。

已读消息：["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3", "d-cache-m4"]
原图观察：[]
引用容器所含证据：["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3", "d-cache-m4"]
实际选择展示：["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3"]
送入核查的提议来源：["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3"]

草稿最小集合：[["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3"]]
草稿集合已观察：True；已引用：True。

草稿集合已选中展示：True。
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": []}, "assessment": {"fact": {"quotes": [{"quote": "合成事件 CACHE_TTL_17：atlas-staging-r3 的配置缓存仍返回旧条目，本地记录显示 TTL 为30秒。", "source": "S1"}, {"quote": "建议把 TTL 改为90秒来减少刷新；这是尚未执行、尚未验证的建议。", "source": "S2"}, {"quote": "核查发现旧条目源于缓存代次键未同步。修订方案是切换 generation_key=g17，再把 TTL 设为73秒，不能仅延长 TTL。", "source": "S3"}, {"quote": "合成验证单 DV-C01：atlas-staging-r3 已使用 generation_key=g17、TTL=73秒，指定旧条目用例不再复现；本结论仅覆盖该测试环境。", "source": "S4"}], "verdict": "supported"}, "unit": {"quotes": [{"quote": "合成验证单 DV-C01：atlas-staging-r3 已使用 generation_key=g17、TTL=73秒，指定旧条目用例不再复现；本结论仅覆盖该测试环境。", "source": "S4"}], "verdict": "supported"}, "scope": {"quotes": [{"quote": "合成验证单 DV-C01：atlas-staging-r3 已使用 generation_key=g17、TTL=73秒，指定旧条目用例不再复现；本结论仅覆盖该测试环境。", "source": "S4"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "合成验证单 DV-C01：atlas-staging-r3 已使用 generation_key=g17、TTL=73秒，指定旧条目用例不再复现；本结论仅覆盖该测试环境。", "source": "S4"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-003 / visual

在 Atlas cache board 原图中，Canary 卡片的圆点是什么颜色，位于卡片左端还是右端？

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 图像观察（模型识别结果，需结合原图核对）
Canary组件内的标记颜色为蓝色，位于组件内部左侧。

2. 消息 d-cache-m4
Atlas cache board 是本事件的合成观察面板。请核查图中 Canary 卡片圆点；文字消息不描述其颜色或位置。

已读消息：["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3", "d-cache-m4"]
原图观察：["d-cache-panel"]
引用容器所含证据：["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3", "d-cache-m4", "d-cache-panel"]
实际选择展示：["d-cache-m4", "d-cache-panel"]
送入核查的提议来源：["d-cache-m4", "d-cache-panel"]

草稿最小集合：[["d-cache-panel"]]
草稿集合已观察：True；已引用：True。

草稿集合已选中展示：True。
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": []}, "assessment": {"fact": {"quotes": [{"quote": "Canary组件内的标记颜色为蓝色，位于组件内部左侧。", "source": "S1"}], "verdict": "supported"}, "unit": {"quotes": [{"quote": "Canary组件内的标记颜色为蓝色，位于组件内部左侧。", "source": "S1"}], "verdict": "supported"}, "scope": {"quotes": [{"quote": "Canary组件内的标记颜色为蓝色，位于组件内部左侧。", "source": "S1"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "Canary组件内的标记颜色为蓝色，位于组件内部左侧。", "source": "S1"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-004 / unanswerable

atlas-staging-r3 单实例支持的最大并发请求数是多少？

实际状态：insufficient；草稿预期：insufficient。

当前已读资料不足以支持本次问题，无法给出可靠结论。

已读消息：["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3", "d-cache-m4"]
原图观察：[]
引用容器所含证据：[]
实际选择展示：[]
送入核查的提议来源：["d-cache-m3", "d-cache-m4"]

草稿最小集合：[]
草稿集合已观察：None；已引用：None。

草稿集合已选中展示：None。
发布前核查：[{"valid": true, "accepted": false, "issues": [], "scope_constraints": {"missing": [], "required": ["atlas-staging-r3"]}, "assessment": {"fact": {"quotes": [], "verdict": "unsupported"}, "unit": {"quotes": [], "verdict": "not_required"}, "scope": {"quotes": [], "verdict": "unsupported"}, "status": {"quotes": [], "verdict": "unsupported"}}}]
人工语义复核：待完成。

## q-dev-005 / fact

在 harbor-integration-r4，UPLOAD_PART_06 最终验证了多大分片，摘要字段有什么要求？

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 消息 d-upload-m3
合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。

2. 消息 d-upload-m2
边界用例要求当前链路采用6 MiB分片，并携带 part_digest。问题修订为同时调整分片尺寸和校验字段，不是只扩大分片。

已读消息：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3", "d-upload-m4"]
原图观察：[]
引用容器所含证据：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3", "d-upload-m4"]
实际选择展示：["d-upload-m2", "d-upload-m3"]
送入核查的提议来源：["d-upload-m2", "d-upload-m3"]

草稿最小集合：[["d-upload-m3"]]
草稿集合已观察：True；已引用：True。

草稿集合已选中展示：True。
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": ["harbor-integration-r4"]}, "assessment": {"fact": {"quotes": [{"quote": "合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。", "source": "S1"}], "verdict": "supported"}, "unit": {"quotes": [{"quote": "合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。", "source": "S1"}], "verdict": "supported"}, "scope": {"quotes": [{"quote": "合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。", "source": "S1"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。", "source": "S1"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-006 / context

UPLOAD_PART_06 为什么不能只沿用最初的扩大片建议？请串起故障、建议、边界修订及验证范围。

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 消息 d-upload-m0
合成事件 UPLOAD_PART_06：harbor-integration-r4 的分片合并校验失败，故障样例使用4 MiB分片。

2. 消息 d-upload-m1
有人建议统一改成8 MiB分片；该建议尚未通过网关边界用例。

3. 消息 d-upload-m2
边界用例要求当前链路采用6 MiB分片，并携带 part_digest。问题修订为同时调整分片尺寸和校验字段，不是只扩大分片。

4. 消息 d-upload-m3
合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。

已读消息：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3", "d-upload-m4"]
原图观察：[]
引用容器所含证据：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3", "d-upload-m4"]
实际选择展示：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3"]
送入核查的提议来源：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3"]

草稿最小集合：[["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3"]]
草稿集合已观察：True；已引用：True。

草稿集合已选中展示：True。
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": []}, "assessment": {"fact": {"quotes": [{"quote": "边界用例要求当前链路采用6 MiB分片，并携带 part_digest。问题修订为同时调整分片尺寸和校验字段，不是只扩大分片。", "source": "S3"}, {"quote": "有人建议统一改成8 MiB分片；该建议尚未通过网关边界用例。", "source": "S2"}, {"quote": "合成事件 UPLOAD_PART_06：harbor-integration-r4 的分片合并校验失败，故障样例使用4 MiB分片。", "source": "S1"}, {"quote": "合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。", "source": "S4"}], "verdict": "supported"}, "unit": {"quotes": [{"quote": "合成事件 UPLOAD_PART_06：harbor-integration-r4 的分片合并校验失败，故障样例使用4 MiB分片。", "source": "S1"}, {"quote": "合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。", "source": "S4"}], "verdict": "supported"}, "scope": {"quotes": [{"quote": "合成事件 UPLOAD_PART_06：harbor-integration-r4 的分片合并校验失败，故障样例使用4 MiB分片。", "source": "S1"}, {"quote": "合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。", "source": "S4"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。", "source": "S4"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-007 / visual

请看 Harbor upload board 的 Upload 卡片：圆点为哪种颜色，在卡片内靠左还是靠右？

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 图像观察（模型识别结果，需结合原图核对）
Upload组件内的标记颜色为橙色，位于组件内部右侧。

2. 消息 d-upload-m4
Harbor upload board 是本事件的人工合成面板，附有 Upload 卡片；卡片圆点信息只在原图中给出。

已读消息：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3", "d-upload-m4"]
原图观察：["d-upload-panel"]
引用容器所含证据：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3", "d-upload-m4", "d-upload-panel"]
实际选择展示：["d-upload-m4", "d-upload-panel"]
送入核查的提议来源：["d-upload-m4", "d-upload-panel"]

草稿最小集合：[["d-upload-panel"]]
草稿集合已观察：True；已引用：True。

草稿集合已选中展示：True。
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": []}, "assessment": {"fact": {"quotes": [{"quote": "Upload组件内的标记颜色为橙色，位于组件内部右侧。", "source": "S1"}], "verdict": "supported"}, "unit": {"quotes": [], "verdict": "not_required"}, "scope": {"quotes": [{"quote": "Harbor upload board 是本事件的人工合成面板，附有 Upload 卡片；卡片圆点信息只在原图中给出。", "source": "S2"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "Harbor upload board 是本事件的人工合成面板，附有 Upload 卡片；卡片圆点信息只在原图中给出。", "source": "S2"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-008 / unanswerable

生产上传网关允许的单文件最大容量是多少 GiB？

实际状态：insufficient；草稿预期：insufficient。

当前已读资料不足以支持本次问题，无法给出可靠结论。

已读消息：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3", "d-upload-m4"]
原图观察：[]
引用容器所含证据：[]
实际选择展示：[]
送入核查的提议来源：["d-upload-m1", "d-upload-m2", "d-upload-m3"]

草稿最小集合：[]
草稿集合已观察：None；已引用：None。

草稿集合已选中展示：None。
发布前核查：[{"valid": true, "accepted": false, "issues": [], "scope_constraints": {"missing": [], "required": []}, "assessment": {"fact": {"quotes": [{"quote": "合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。", "source": "S1"}, {"quote": "有人建议统一改成8 MiB分片；该建议尚未通过网关边界用例。", "source": "S2"}, {"quote": "边界用例要求当前链路采用6 MiB分片，并携带 part_digest。问题修订为同时调整分片尺寸和校验字段，不是只扩大分片。", "source": "S3"}], "verdict": "unsupported"}, "unit": {"quotes": [], "verdict": "not_required"}, "scope": {"quotes": [], "verdict": "not_required"}, "status": {"quotes": [], "verdict": "not_required"}}}]
人工语义复核：待完成。

## q-dev-009 / fact

QUEUE_RETRY_23 在 cedar-qa-r6 通过验证的初始退避时间和最大尝试次数是多少？前提是什么？

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 消息 d-backoff-m0
合成事件 QUEUE_RETRY_23：cedar-qa-r6 的任务在重试时被重复消费；记录中缺少幂等键。

2. 消息 d-backoff-m3
合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。

3. 消息 d-backoff-m4
Cedar retry board 是合成面板，Worker 卡片的圆点需从附件原图核查，正文没有颜色说明。

已读消息：["d-backoff-m0", "d-backoff-m1", "d-backoff-m2", "d-backoff-m3", "d-backoff-m4"]
原图观察：[]
引用容器所含证据：["d-backoff-m0", "d-backoff-m1", "d-backoff-m2", "d-backoff-m3", "d-backoff-m4"]
实际选择展示：["d-backoff-m0", "d-backoff-m3", "d-backoff-m4"]
送入核查的提议来源：["d-backoff-m0", "d-backoff-m3", "d-backoff-m4"]

草稿最小集合：[["d-backoff-m3"]]
草稿集合已观察：True；已引用：True。

草稿集合已选中展示：True。
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": ["cedar-qa-r6"]}, "assessment": {"fact": {"quotes": [{"quote": "合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。", "source": "S2"}], "verdict": "supported"}, "unit": {"quotes": [{"quote": "合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。", "source": "S2"}], "verdict": "supported"}, "scope": {"quotes": [{"quote": "合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。", "source": "S2"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。", "source": "S2"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-010 / context

请说明 QUEUE_RETRY_23 从重复消费到修订验证的过程，区分未执行建议与需要满足的前提。

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 消息 d-backoff-m0
合成事件 QUEUE_RETRY_23：cedar-qa-r6 的任务在重试时被重复消费；记录中缺少幂等键。

2. 消息 d-backoff-m1
最初建议固定等待2秒后无限重试。该建议未执行，不是已通过方案。

3. 消息 d-backoff-m2
修订采用指数退避，base_delay=3秒、max_attempts=4，并要求 idempotency_key；缺少幂等键时不能套用该结论。

4. 消息 d-backoff-m3
合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。

已读消息：["d-backoff-m0", "d-backoff-m1", "d-backoff-m2", "d-backoff-m3", "d-backoff-m4"]
原图观察：[]
引用容器所含证据：["d-backoff-m0", "d-backoff-m1", "d-backoff-m2", "d-backoff-m3", "d-backoff-m4"]
实际选择展示：["d-backoff-m0", "d-backoff-m1", "d-backoff-m2", "d-backoff-m3"]
送入核查的提议来源：["d-backoff-m0", "d-backoff-m1", "d-backoff-m2", "d-backoff-m3"]

草稿最小集合：[["d-backoff-m0", "d-backoff-m1", "d-backoff-m2", "d-backoff-m3"]]
草稿集合已观察：True；已引用：True。

草稿集合已选中展示：True。
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": []}, "assessment": {"fact": {"quotes": [{"quote": "合成事件 QUEUE_RETRY_23：cedar-qa-r6 的任务在重试时被重复消费；记录中缺少幂等键。", "source": "S1"}, {"quote": "最初建议固定等待2秒后无限重试。该建议未执行，不是已通过方案。", "source": "S2"}, {"quote": "修订采用指数退避，base_delay=3秒、max_attempts=4，并要求 idempotency_key；缺少幂等键时不能套用该结论。", "source": "S3"}, {"quote": "合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。", "source": "S4"}], "verdict": "supported"}, "unit": {"quotes": [{"quote": "合成事件 QUEUE_RETRY_23：cedar-qa-r6 的任务在重试时被重复消费；记录中缺少幂等键。", "source": "S1"}, {"quote": "最初建议固定等待2秒后无限重试。该建议未执行，不是已通过方案。", "source": "S2"}, {"quote": "修订采用指数退避，base_delay=3秒、max_attempts=4，并要求 idempotency_key；缺少幂等键时不能套用该结论。", "source": "S3"}, {"quote": "合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。", "source": "S4"}], "verdict": "supported"}, "scope": {"quotes": [{"quote": "合成事件 QUEUE_RETRY_23：cedar-qa-r6 的任务在重试时被重复消费；记录中缺少幂等键。", "source": "S1"}, {"quote": "最初建议固定等待2秒后无限重试。该建议未执行，不是已通过方案。", "source": "S2"}, {"quote": "修订采用指数退避，base_delay=3秒、max_attempts=4，并要求 idempotency_key；缺少幂等键时不能套用该结论。", "source": "S3"}, {"quote": "合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。", "source": "S4"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "合成事件 QUEUE_RETRY_23：cedar-qa-r6 的任务在重试时被重复消费；记录中缺少幂等键。", "source": "S1"}, {"quote": "最初建议固定等待2秒后无限重试。该建议未执行，不是已通过方案。", "source": "S2"}, {"quote": "修订采用指数退避，base_delay=3秒、max_attempts=4，并要求 idempotency_key；缺少幂等键时不能套用该结论。", "source": "S3"}, {"quote": "合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。", "source": "S4"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-011 / visual

Cedar retry board 里 Worker 卡片的圆点是什么颜色，位于卡片的哪一端？

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 图像观察（模型识别结果，需结合原图核对）
Worker组件内的标记颜色为紫色，位于组件内部左侧。

2. 消息 d-backoff-m4
Cedar retry board 是合成面板，Worker 卡片的圆点需从附件原图核查，正文没有颜色说明。

已读消息：["d-backoff-m0", "d-backoff-m1", "d-backoff-m2", "d-backoff-m3", "d-backoff-m4"]
原图观察：["d-backoff-panel"]
引用容器所含证据：["d-backoff-m0", "d-backoff-m1", "d-backoff-m2", "d-backoff-m3", "d-backoff-m4", "d-backoff-panel"]
实际选择展示：["d-backoff-m4", "d-backoff-panel"]
送入核查的提议来源：["d-backoff-m4", "d-backoff-panel"]

草稿最小集合：[["d-backoff-panel"]]
草稿集合已观察：True；已引用：True。

草稿集合已选中展示：True。
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": []}, "assessment": {"fact": {"quotes": [{"quote": "Worker组件内的标记颜色为紫色，位于组件内部左侧。", "source": "S1"}], "verdict": "supported"}, "unit": {"quotes": [{"quote": "Worker组件内的标记颜色为紫色，位于组件内部左侧。", "source": "S1"}], "verdict": "supported"}, "scope": {"quotes": [{"quote": "Worker组件内的标记颜色为紫色，位于组件内部左侧。", "source": "S1"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "Worker组件内的标记颜色为紫色，位于组件内部左侧。", "source": "S1"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-012 / unanswerable

cedar-prod 的重试初始等待时间已经配置成多少秒？

实际状态：insufficient；草稿预期：insufficient。

当前已读资料不足以支持本次问题，无法给出可靠结论。

已读消息：["d-backoff-m0", "d-backoff-m1", "d-backoff-m2", "d-backoff-m3", "d-backoff-m4"]
原图观察：[]
引用容器所含证据：[]
实际选择展示：[]
送入核查的提议来源：["d-backoff-m2", "d-backoff-m3"]

草稿最小集合：[]
草稿集合已观察：None；已引用：None。

草稿集合已选中展示：None。
发布前核查：[{"valid": true, "accepted": false, "issues": [], "scope_constraints": {"missing": ["cedar-prod"], "required": ["cedar-prod"]}, "assessment": {"fact": {"quotes": [{"quote": "修订采用指数退避，base_delay=3秒、max_attempts=4，并要求 idempotency_key；缺少幂等键时不能套用该结论。", "source": "S1"}, {"quote": "合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。", "source": "S2"}], "verdict": "supported"}, "unit": {"quotes": [{"quote": "修订采用指数退避，base_delay=3秒、max_attempts=4，并要求 idempotency_key；缺少幂等键时不能套用该结论。", "source": "S1"}, {"quote": "合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。", "source": "S2"}], "verdict": "supported"}, "scope": {"quotes": [{"quote": "修订采用指数退避，base_delay=3秒、max_attempts=4，并要求 idempotency_key；缺少幂等键时不能套用该结论。", "source": "S1"}, {"quote": "合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。", "source": "S2"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "修订采用指数退避，base_delay=3秒、max_attempts=4，并要求 idempotency_key；缺少幂等键时不能套用该结论。", "source": "S1"}, {"quote": "合成验证单 DV-Q03：cedar-qa-r6 在 idempotency_key 开启条件下，base_delay=3秒、max_attempts=4，重复投递样例只执行一次业务动作。", "source": "S2"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-013 / fact

CFG_ROLLOUT_31 在 maple-sandbox-r2 最后确认的发布比例、配置版本和开关是什么？

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 消息 d-config-m3
合成验证单 DV-F04：maple-sandbox-r2 使用 cfg_rev=27、rollout_ratio=15%、cfg_gate=true，指定样例均读取修订快照；只涉及合成租户。

已读消息：["d-config-m0", "d-config-m1", "d-config-m2", "d-config-m3", "d-config-m4"]
原图观察：[]
引用容器所含证据：["d-config-m0", "d-config-m1", "d-config-m2", "d-config-m3", "d-config-m4"]
实际选择展示：["d-config-m3"]
送入核查的提议来源：["d-config-m3"]

草稿最小集合：[["d-config-m3"]]
草稿集合已观察：True；已引用：True。

草稿集合已选中展示：True。
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": ["maple-sandbox-r2"]}, "assessment": {"fact": {"quotes": [{"quote": "合成验证单 DV-F04：maple-sandbox-r2 使用 cfg_rev=27、rollout_ratio=15%、cfg_gate=true，指定样例均读取修订快照；只涉及合成租户。", "source": "S1"}], "verdict": "supported"}, "unit": {"quotes": [{"quote": "合成验证单 DV-F04：maple-sandbox-r2 使用 cfg_rev=27、rollout_ratio=15%、cfg_gate=true，指定样例均读取修订快照；只涉及合成租户。", "source": "S1"}], "verdict": "supported"}, "scope": {"quotes": [{"quote": "合成验证单 DV-F04：maple-sandbox-r2 使用 cfg_rev=27、rollout_ratio=15%、cfg_gate=true，指定样例均读取修订快照；只涉及合成租户。", "source": "S1"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "合成验证单 DV-F04：maple-sandbox-r2 使用 cfg_rev=27、rollout_ratio=15%、cfg_gate=true，指定样例均读取修订快照；只涉及合成租户。", "source": "S1"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-014 / context

CFG_ROLLOUT_31 最初为什么要排查快照？请连同早期建议、最终修订及验证范围一起回答。

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 消息 d-config-m0
合成事件 CFG_ROLLOUT_31：maple-sandbox-r2 的配置版本混用，部分样例仍读取旧发布快照。

2. 消息 d-config-m1
最初建议直接切换50%的样例租户；这项建议还没有执行记录。

3. 消息 d-config-m2
核查后改为 rollout_ratio=15%，并同时开启 cfg_gate；旧快照必须先隔离，不能把扩大比例当作修复。

4. 消息 d-config-m3
合成验证单 DV-F04：maple-sandbox-r2 使用 cfg_rev=27、rollout_ratio=15%、cfg_gate=true，指定样例均读取修订快照；只涉及合成租户。

已读消息：["d-config-m0", "d-config-m1", "d-config-m2", "d-config-m3", "d-config-m4"]
原图观察：[]
引用容器所含证据：["d-config-m0", "d-config-m1", "d-config-m2", "d-config-m3", "d-config-m4"]
实际选择展示：["d-config-m0", "d-config-m1", "d-config-m2", "d-config-m3"]
送入核查的提议来源：["d-config-m0", "d-config-m1", "d-config-m2", "d-config-m3"]

草稿最小集合：[["d-config-m0", "d-config-m1", "d-config-m2", "d-config-m3"]]
草稿集合已观察：True；已引用：True。

草稿集合已选中展示：True。
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": []}, "assessment": {"fact": {"quotes": [{"quote": "最初建议直接切换50%的样例租户；这项建议还没有执行记录。", "source": "S2"}, {"quote": "核查后改为 rollout_ratio=15%，并同时开启 cfg_gate；旧快照必须先隔离，不能把扩大比例当作修复。", "source": "S3"}, {"quote": "合成验证单 DV-F04：maple-sandbox-r2 使用 cfg_rev=27、rollout_ratio=15%、cfg_gate=true，指定样例均读取修订快照；只涉及合成租户。", "source": "S4"}], "verdict": "supported"}, "unit": {"quotes": [], "verdict": "not_required"}, "scope": {"quotes": [{"quote": "合成验证单 DV-F04：maple-sandbox-r2 使用 cfg_rev=27、rollout_ratio=15%、cfg_gate=true，指定样例均读取修订快照；只涉及合成租户。", "source": "S4"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "最初建议直接切换50%的样例租户；这项建议还没有执行记录。", "source": "S2"}, {"quote": "核查后改为 rollout_ratio=15%，并同时开启 cfg_gate；旧快照必须先隔离，不能把扩大比例当作修复。", "source": "S3"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-015 / visual

Maple rollout board 的 Beta 卡片圆点是什么颜色，位于左端还是右端？

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 图像观察（模型识别结果，需结合原图核对）
Beta组件内的标记颜色为蓝色，位于组件内部右侧。

2. 消息 d-config-m4
Maple rollout board 为合成发布面板，Beta 卡片的圆点由原图表达，不在文字中标注。

已读消息：["d-config-m0", "d-config-m1", "d-config-m2", "d-config-m3", "d-config-m4"]
原图观察：["d-config-panel"]
引用容器所含证据：["d-config-m0", "d-config-m1", "d-config-m2", "d-config-m3", "d-config-m4", "d-config-panel"]
实际选择展示：["d-config-m4", "d-config-panel"]
送入核查的提议来源：["d-config-m4", "d-config-panel"]

草稿最小集合：[["d-config-panel"]]
草稿集合已观察：True；已引用：True。

草稿集合已选中展示：True。
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": []}, "assessment": {"fact": {"quotes": [{"quote": "Beta组件内的标记颜色为蓝色，位于组件内部右侧。", "source": "S1"}], "verdict": "supported"}, "unit": {"quotes": [{"quote": "Beta组件内的标记颜色为蓝色，位于组件内部右侧。", "source": "S1"}], "verdict": "supported"}, "scope": {"quotes": [{"quote": "Beta组件内的标记颜色为蓝色，位于组件内部右侧。", "source": "S1"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "Beta组件内的标记颜色为蓝色，位于组件内部右侧。", "source": "S1"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-016 / unanswerable

在本次允许读取的范围中，maple-sandbox-r2 已验证的 cfg_rev 是多少？

实际状态：insufficient；草稿预期：insufficient。

当前已读资料不足以支持本次问题，无法给出可靠结论。

已读消息：[]
原图观察：[]
引用容器所含证据：[]
实际选择展示：[]
送入核查的提议来源：[]

草稿最小集合：[]
草稿集合已观察：None；已引用：None。

草稿集合已选中展示：None。
发布前核查：[]
人工语义复核：待完成。
