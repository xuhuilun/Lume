# 证据补查与原文选择开发记录

日期：2026-11-05。未生成PDF，未改论文正文。仅使用16题开发资料，保留32题未执行，参考标签人审0题，未计算正式质量分数。

## 实现与检查

982b20b增加明确技术标识的两路过滤、同空间12条/4跳显式回复图，以及模型选依据、程序展示完整原文的回答契约。Ollama不再直接发布模型自由数字总结；选择相关性与充分性仍需评价。无数据库列变化或新增依赖。

367dcda修正核图answer必须包含实际image_evidence，同时允许最多3项额外依据。发布层仍检查任务归属及实际图像观察。最终规则为Ollama v4 / Demo v2；已有安装按operations说明停服务、重建索引、重启，不能静默采用新行为。

3项初始失败回归及1项核图选择失败均已先复现。最终82项后端回归通过，无跳过；Ruff检查及27个Python文件格式检查通过。浏览器本轮未复测，早期浏览器记录不代表新协议验收。

## 已完成和中断的运行

- run-02：982b20b，16题完整执行，11 completed / 4 failed / 1 insufficient。4道核图题均已取得实际图像观察，但模型只选择普通消息，发布层以IMAGE_EVIDENCE_REQUIRED阻止发布；原始失败保留。
- run-03：367dcda，已记录14题，13 completed / 1 running；最后2题未开始。前3道核图题实际发布图像观察。第14题的单调时钟elapsed为14.059秒，started_at至报告结束的UTC壁钟差606.873秒。结合租约失效时取消在途工作、旧领取者不写终态的代码，高度支持宿主暂停/时钟跳变导致15秒租约过期；没有系统睡眠日志，不能确定具体外部原因。执行器发现非终态后停止并清理随机schema，此次不算完整复测。
- 同367dcda应用版本的run-04已完整重新执行16题：15 completed / 1 insufficient。源码提交为b63a895（相对367dcda仅文档变化），开始时工作树干净。权重、数据、调用预算、90秒任务期限和4096服务上下文不变；本轮以caffeinate -i临时抑制自动休眠，不放宽租约条件。此宿主条件变化另行记录，不能声称两轮是完全相同运行环境的单因素比较。

run-02的原文选择已取得此前漏读的验证消息，但q-dev-004/008/012仍选择缺少所问字段或仅覆盖测试环境的材料，没有正确声明不足。原文展示能防止自由添加数字，不等于系统能正确判断资料充分性。图像文字仍可能漏颜色、看错组件内相对位置。

全部运行使用真实ASGI业务API、PostgreSQL/pgvector随机schema及本机实际Ollama权重，数据均为合成资料。不是HTTP网络/浏览器验收、真实QQ联调、负载实验或生产质量结论。时间日志包括模型装载和调度，不作为服务性能指标。


## run-04 的实际观察

| 项目 | 记录 | 边界 |
| --- | --- | --- |
| 资料 | 4个开发空间、24消息、4图、24个job ready | 人工合成，无真实企业数据 |
| 任务终态 | 15 completed、1 insufficient，无failed/limited | completed不表示答对 |
| 模型调用 | 99次均返回：40向量、51规划、8视觉；准备28、任务71 | 真实固定权重接口，不是替身；没有质量分数 |
| 可追踪展示 | 15个已发布普通答案逐项等于所选持久原文/图像观察 | 不证明选择充分，也不校正视觉模型文字 |
| 范围 | 16题全部观察依赖属于请求范围，4道核图题都实际选择本题图像观察 | 局部合成静态资格检查，非生产隔离证明 |
| 提示与记录 | 最大prompt_eval_count=3867，4096服务上下文；本次独立服务日志未见输入截断告警 | 字符预算不等于模型token预算；不是完整服务行为证明 |
| 参考覆盖 | 4道事实题选中验证消息，4道上下文题选择4段过程原文；4道视觉题选中原图观察 | 只对助手草稿作ID集合检查，不能转写为语义正确率 |

相较旧基线，run-04展示的验证原文保留了TTL=73秒/g17、6 MiB及摘要要求、3秒/4次及幂等键前提、15%/cfg_rev=27/cfg_gate=true等限定。过程题同时展示起点、建议、修订和验证；没有把“建议尚未执行”改成执行结论。但回答形式与可见上下文范围都已改变，不能把这次观察写成单一检索算法改进的因果效果。

以下错误仍在，不能以合法引用掩盖：

- q-dev-004询问最大并发数，选择TTL/代次键记录；来源不包含并发上限，仍被标为completed。
- q-dev-008询问生产单文件容量，选择6 MiB分片记录；分片尺寸不等于文件上限，且来源明示未测试生产，仍被标为completed。
- q-dev-012询问cedar-prod配置，却选择cedar-qa-r6验证消息；环境不匹配，仍被标为completed。
- q-dev-016因本次范围内无对应Maple依据，实际返回insufficient；没有越界取得Maple来源。
- q-dev-007的Upload圆点实际为橙色、在目标卡片右端；视觉观察为“圆点在卡片内靠左”，漏颜色且位置错。程序如实展示该观察，未替它补造颜色。
- q-dev-015的Beta圆点为蓝色、在卡片右端；视觉观察称蓝色/左端，位置错。
- q-dev-003蓝色/左端、q-dev-011紫色/左侧与开发PNG的助手初步目视对照一致；不是独立人工验收，标签人审仍0。

图像检查仅查看4张开发PNG，未查看保留题输出或使用保留标签调参。当前仍需改进“所问字段/环境是否被直接支持”的判断及目标组件相对位置识别，再安排参考材料人工复核和独立质量实验。真实QQ、HTTP/浏览器新协议验收与负载仍未完成；论文Q-01—Q-03不能据此标记完成。

## 记录与复现

- [run-02原始记录](evidence/evidence-improvement/run-02-source-excerpts.json)、[逐题审阅](evidence/evidence-improvement/audit-02-source-excerpts.md)
- [run-03部分记录](evidence/evidence-improvement/run-03-required-image-slot.json)、[逐题审阅](evidence/evidence-improvement/audit-03-partial.md)
- [run-04完整记录](evidence/evidence-improvement/run-04-complete-repeat.json)、[逐题审阅](evidence/evidence-improvement/audit-04-complete-repeat.md)
- [执行产物一致性核查](evidence/evidence-improvement/execution-verification.json)、[宿主条件](evidence/evidence-improvement/host-execution.json)
- [后端JUnit](evidence/evidence-improvement/backend-regressions.xml)、[模拟时钟前跳复现](evidence/evidence-improvement/clock-jump-reproduction.xml)

每个执行器快照的SHA与相应运行报告一致。产物核查分别检查已选消息/图像观察、完整原文展示、引用容器、实际范围和所有输入依赖。audit新增selected_evidence_ids，避免把一个引用容器中的全部消息都当作实际展示的消息。原始记录保留已处理的最终content和用量，图片记录摘要与字节数，不导出base64、内部思维或凭据；不是完整原始HTTP抓包。

复现本轮应用时检出367dcda，依真实模型说明准备同digest权重、独立测试数据库与本机服务，再执行（输出文件必须不存在）：

```bash
LUME_TEST_DATABASE_URL=独立测试库连接串 caffeinate -i \
  uv run --frozen python -m scripts.development_pilot run \
  --application-baseline 367dcdae3f741c18c00187747c90ba64961660a3 \
  --output ../outputs/lume-evidence-improvement/run-new.json
uv run --frozen python -m scripts.development_pilot audit \
  --run ../outputs/lume-evidence-improvement/run-new.json \
  --output ../outputs/lume-evidence-improvement/audit-new.json
```

caffeinate仅适用于macOS，属于宿主进程保护；其他主机应记录自己的睡眠策略。不得把示例连接串写进Git。运行结束的随机schema、临时图像目录已清理，独立Ollama随后停止；原项目数据库与已安装权重保留。没有自动变更原项目数据或重建它的索引。已有安装需要按[运行说明](operations.md)升级规则；本轮查看交付物无需手动操作。
