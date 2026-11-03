# 开发集真实系统试跑

日期：2026-11-03。本轮按预先计划执行16道开发题，未运行32道保留题。参考标签仍为助手草稿，人审0题；本记录提供真实执行与错误分析，不提供正式语义准确率。

## 执行条件

实际执行源码为[a54e2f5](https://github.com/xuhuilun/Lume/commit/a54e2f5089caa5e40523e4a69bc25b05de5f1306)，应用业务逻辑与5ca664f一致。输入数据manifest摘要为410134ca19cd3e8e14bbb411771698612d7bd1b3cf9ebdb666d83c604b6d60c2。执行开始时工作树干净，运行端不解析参考答案或题型。

Ollama 0.40.11，本机单模型加载、单并发、4096服务上下文；embeddinggemma/BF16、qwen3:4b/Q4_K_M、qwen2.5vl:3b/Q4_K_M的digest与上一阶段完全相同。模型版本标识改用模型名称与digest映射的稳定摘要；该标识是新建实验索引的命名，不改变权重或推理选项。具体rules_id及全部参数保留在执行记录中。

通过真实ASGI业务API、新建随机PostgreSQL schema和真实Ollama执行。创建4个开发空间，只导入24条消息及4张图片，全部24个派生job就绪。每道任务独立、无历史答案回用；任务期限90秒，累计模型12/工具8/图像2预算，retrieval_k=12、RRF常数60、OCR语言eng，均与计划一致。

查询通过白名单转换，只提交question、space_ids、require_image。离线ID留在外部日志；视觉4题显式要求原图，最后一道范围题请求另外3个开发空间。哈希核验会读取冻结文件字节，但不会解析参考标签作为执行数据；保留消息没有导入、保留问题没有发给模型。

## 实际执行记录

| 项目 | 观察 | 解释 |
| --- | --- | --- |
| 导入与派生 | 24条消息、4张图；24个job均ready | 合成资料；不是上游真实业务验收 |
| 任务终态 | 16个completed，无failed/limited/insufficient | 仅表示发布了答案，已发现其中存在明显错误 |
| 模型接口调用 | 100次均返回；其中准备阶段28、任务阶段72 | 40次向量、52次规划、8次视觉；不等于16题均正确 |
| 工具行为 | 每题只进行1次search和1次read_context；4题追加inspect_image | 未观察到继续读取其他候选或追加检索 |
| 引用链 | 16题引用均属于本任务已读观察，4道核图题引用实际图像观察 | 合法引用ID不保证内容支持或视觉理解正确 |
| 请求范围 | 本轮全部观察依赖均在各题冻结范围内 | 静态合成权限条件下的局部观察，不是生产安全证明 |
| 回归 | 首轮60项通过；补强离线审阅绑定后61项通过，无跳过 | 33原程序/18数据/10试跑工具检查；与模型语义评价分开 |

逐调用记录见[run-01-baseline.json](evidence/development-pilot/run-01-baseline.json)，逐题问题、答案和证据集合见[audit-02-question-linked.md](evidence/development-pilot/audit-02-question-linked.md)，初步问题分类见[development-pilot-findings.md](development-pilot-findings.md)。记录保留模型最终content、实际请求资料和用量；图片只记录原图摘要/字节数，内部思维文本、base64长串和凭据不进入归档。它是执行器整理的结构化记录，不是完整未处理HTTP抓包。

e4ef185仅增强离线审阅的原问题绑定与显示，没有再次执行模型，也没有覆盖基线结果。run-01中的脚本SHA已按git中的a54e2f5快照核对，避免把后续审阅代码错称为最初执行代码。两份离线审阅输出均保留。

## 如何复现

先启动与真实模型联调相同的本机Ollama服务；准备独立测试数据库，并通过环境设置LUME_TEST_DATABASE_URL，不把连接凭据写进Git。默认入口会拒绝模型digest、数据摘要或应用逻辑与冻结基线不符的条件。

```bash
uv run --frozen python -m scripts.development_pilot run \
  --output ../outputs/lume-development-pilot/run-02-new-observation.json
uv run --frozen python -m scripts.development_pilot audit \
  --run ../outputs/lume-development-pilot/run-02-new-observation.json \
  --output ../outputs/lume-development-pilot/audit-03-new-observation.json
```

输出文件必须不存在，复测另起文件。运行端只解析开发查询和经筛选的开发语料；audit是结束后独立读取开发参考的离线步骤，不调用模型，不计算语义质量分数。运行时随机UUID、排序同分、模型缓存/加载及计算条件可能影响复测，不保证逐字同答或相同耗时。

本轮最大模型prompt_eval_count为2853，未以延长期限或提高预算换取完成。单设备题级耗时含模型调度与加载，不是负载测试或服务SLA。没有执行词项/向量/融合及核图/追加查证的正式对比，因此Q-01—Q-03仍不视为完成。

## 后续处理和清理

基线中存在把建议当结论、错误单位、不同情景混用、无依据数字和图像相对位置错误，见逐项分析。先改进证据选择与补查、资料不足判定以及视觉观察完整性，再用开发题复测；不得读取保留答案调参、按问题ID写死答案或把草稿覆盖检查当作语义评分。

ASGI执行结束后，随机schema和临时图片目录已移除，独立Ollama已停止；原项目数据库和模型权重保留。服务日志仍在Git忽略的本地运行目录，不进入交付包。真实QQ、正式质量/负载、人审和论文回填仍未完成，未生成PDF。
