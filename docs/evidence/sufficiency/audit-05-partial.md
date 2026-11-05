# 开发集真实试跑逐题审阅

仅为开发诊断；参考标签人审0题。任务完成不等于回答正确，ID集合覆盖不等于逐断言支持。

实际任务状态：{"completed": 5, "insufficient": 2, "running": 1}

## q-dev-001 / fact

CACHE_TTL_17 在 atlas-staging-r3 最后验证的 TTL 和代次键分别是什么？

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 消息 d-cache-m3
合成验证单 DV-C01：atlas-staging-r3 已使用 generation_key=g17、TTL=73秒，指定旧条目用例不再复现；本结论仅覆盖该测试环境。

2. 消息 d-cache-m2
核查发现旧条目源于缓存代次键未同步。修订方案是切换 generation_key=g17，再把 TTL 设为73秒，不能仅延长 TTL。

已读消息：["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3", "d-cache-m4"]
原图观察：[]
引用容器所含证据：["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3", "d-cache-m4"]
实际选择展示：["d-cache-m2", "d-cache-m3"]
送入核查的提议来源：["d-cache-m2", "d-cache-m3"]

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
在 Atlas cache board 原图中，Canary 卡片的圆点是蓝色，位于卡片的左端。

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
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": []}, "assessment": {"fact": {"quotes": [{"quote": "在 Atlas cache board 原图中，Canary 卡片的圆点是蓝色，位于卡片的左端。", "source": "S1"}], "verdict": "supported"}, "unit": {"quotes": [], "verdict": "not_required"}, "scope": {"quotes": [{"quote": "在 Atlas cache board 原图中，Canary 卡片的圆点是蓝色，位于卡片的左端。", "source": "S1"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "在 Atlas cache board 原图中，Canary 卡片的圆点是蓝色，位于卡片的左端。", "source": "S1"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-004 / unanswerable

atlas-staging-r3 单实例支持的最大并发请求数是多少？

实际状态：insufficient；草稿预期：insufficient。

当前已读资料不足以支持本次问题，无法给出可靠结论。

已读消息：["d-cache-m0", "d-cache-m1", "d-cache-m2", "d-cache-m3", "d-cache-m4"]
原图观察：[]
引用容器所含证据：[]
实际选择展示：[]
送入核查的提议来源：["d-cache-m2", "d-cache-m3"]

草稿最小集合：[]
草稿集合已观察：None；已引用：None。

草稿集合已选中展示：None。
发布前核查：[{"valid": true, "accepted": false, "issues": [], "scope_constraints": {"missing": [], "required": ["atlas-staging-r3"]}, "assessment": {"fact": {"quotes": [], "verdict": "unsupported"}, "unit": {"quotes": [], "verdict": "not_required"}, "scope": {"quotes": [], "verdict": "not_required"}, "status": {"quotes": [], "verdict": "not_required"}}}]
人工语义复核：待完成。

## q-dev-005 / fact

在 harbor-integration-r4，UPLOAD_PART_06 最终验证了多大分片，摘要字段有什么要求？

实际状态：completed；草稿预期：completed。

已读取的来源依据：

1. 消息 d-upload-m3
合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。

已读消息：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3", "d-upload-m4"]
原图观察：[]
引用容器所含证据：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3", "d-upload-m4"]
实际选择展示：["d-upload-m3"]
送入核查的提议来源：["d-upload-m3"]

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
发布前核查：[{"valid": true, "accepted": true, "issues": [], "scope_constraints": {"missing": [], "required": []}, "assessment": {"fact": {"quotes": [{"quote": "边界用例要求当前链路采用6 MiB分片，并携带 part_digest。问题修订为同时调整分片尺寸和校验字段，不是只扩大分片。", "source": "S3"}, {"quote": "合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。", "source": "S4"}], "verdict": "supported"}, "unit": {"quotes": [{"quote": "边界用例要求当前链路采用6 MiB分片，并携带 part_digest。问题修订为同时调整分片尺寸和校验字段，不是只扩大分片。", "source": "S3"}], "verdict": "supported"}, "scope": {"quotes": [{"quote": "边界用例要求当前链路采用6 MiB分片，并携带 part_digest。问题修订为同时调整分片尺寸和校验字段，不是只扩大分片。", "source": "S3"}], "verdict": "supported"}, "status": {"quotes": [{"quote": "合成验证单 DV-U02：harbor-integration-r4 使用 part_size=6 MiB、part_digest=required，合并后摘要与源文件相同；未测试生产环境。", "source": "S4"}], "verdict": "supported"}}}]
人工语义复核：待完成。

## q-dev-007 / visual

请看 Harbor upload board 的 Upload 卡片：圆点为哪种颜色，在卡片内靠左还是靠右？

实际状态：insufficient；草稿预期：completed。

当前已读资料不足以支持本次问题，无法给出可靠结论。

已读消息：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3", "d-upload-m4"]
原图观察：["d-upload-panel"]
引用容器所含证据：[]
实际选择展示：[]
送入核查的提议来源：["d-upload-m4", "d-upload-panel"]

草稿最小集合：[["d-upload-panel"]]
草稿集合已观察：True；已引用：False。

草稿集合已选中展示：False。
发布前核查：[{"valid": true, "accepted": false, "issues": [], "scope_constraints": {"missing": [], "required": []}, "assessment": {"fact": {"quotes": [], "verdict": "unsupported"}, "unit": {"quotes": [], "verdict": "not_required"}, "scope": {"quotes": [], "verdict": "not_required"}, "status": {"quotes": [], "verdict": "not_required"}}}]
人工语义复核：待完成。

## q-dev-008 / unanswerable

生产上传网关允许的单文件最大容量是多少 GiB？

实际状态：running；草稿预期：insufficient。

本题无已发布答案。

已读消息：["d-upload-m0", "d-upload-m1", "d-upload-m2", "d-upload-m3", "d-upload-m4"]
原图观察：[]
引用容器所含证据：[]
实际选择展示：[]
送入核查的提议来源：[]

草稿最小集合：[]
草稿集合已观察：None；已引用：None。

草稿集合已选中展示：None。
发布前核查：[]
人工语义复核：待完成。
