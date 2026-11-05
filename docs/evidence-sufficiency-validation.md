# 发布前充分性核查实际记录

日期：2026-11-05。未生成PDF、未修改论文正文。开发数据标签仍为助手草稿、人审0；32道保留题未执行，未计算正式语义正确率。

## 本轮实现

应用冻结提交dc77d0e，完整执行源码提交977f173（仅执行器恢复、测试和计划文档变化，应用仍与dc77d0e一致）。原文选择后独立调用同一Ollama生成模型核查fact/unit/scope/status，support_review计入模型额度；发布层重新校验持久核查、摘要、原文片段及显式环境边界。不是独立模型、人工审阅或语义证明器。

Ollama规则v5、answer_contract=reviewed-excerpts-v1；Demo仍v2。无新依赖、数据库列或用户提交字段变化。仍保持90秒期限、模型12/工具8/图像2预算、字符上限32000、服务上下文4096及原有固定权重。正常展示仍为所选完整持久原文；无效核查failed，有效不足insufficient，异常/预算不伪装成正确拒答。

显式环境兜底只识别“名称-阶段[-数字或r/v修订]”，阶段词取prod/production/qa/test/staging/sandbox/integration/dev/uat；精确词界、大小写归一，不支持别名等价推断。test-driven和run-integration-tests误匹配已通过先红后绿的回归修复。即使原文出现同名环境，也不自动证明所问字段属于该环境。

## 自检与执行条件

- 全部115项后端检查通过，无跳过；Ruff和29个Python文件格式检查通过。
- 回归覆盖四维拒绝、坏引文/格式、核查归属和摘要、假通过标志、额度、在途撤权/来源停用/取消、过期恢复及活跃租约保护。
- 真实Ollama 0.40.11，embeddinggemma、qwen3:4b、qwen2.5vl:3b权重digest与旧基线一致；本机单模型、单并发、4096上下文，使用caffeinate -i保护执行器。
- 真实ASGI业务API、随机PostgreSQL/pgvector schema；4个开发空间、24条消息、4张图、24个派生job ready。没有真实企业/QQ数据，也不是HTTP网络或浏览器验收。
- 模型输入不含题号、参考标签或预期终态。支持核查仅接收问题、核图要求及S标签所选原文，不接收候选排名。程序规则没有问题ID或固定答案。

## 重放与中断记录

probe-01/02/03均为未提交工作树的开发重放，实际请求schema与返回已保存，不能归属于后来的冻结提交。首次8题中5个结果结构无效；第二次出现QA误当prod及一处改写引文；第三次3个原始误答与1个缺颜色观察被有效拒绝，4个可回答事实/过程正例通过，未发生格式错误。这些是针对开发失败的诊断，不是正式质量实验。

run-05只记录前8题：5 completed / 2 insufficient / 1 running；第8题墙钟64.279秒、单调计时30.081秒，在途核查被取消，之后未执行，随机schema已清理。时间差支持宿主暂停/时钟变化推断，但没有OS事件日志确认具体原因。没有把取消或未执行题填成正确拒答。

执行器随后增加正常过期领取恢复：只恢复本题、确认租约确已过期；原期限、累计预算与最多2次恢复不重置，活跃租约不抢占。应用未改。run-06完整重跑16题，本次实际恢复次数为0，故不能把它说成真实暂停恢复验收；暂停场景由模拟时钟回归验证。

## run-06 完整开发观察

| 项目 | 实际记录 | 解释 |
| --- | --- | --- |
| 任务终态 | 10 completed / 6 insufficient，无failed/limited | 发布数量不等于正确数量 |
| 接口调用 | 114次均返回：40 embedding / 51 planning / 8 vision / 15 support_review | 准备28、任务86；没有隐藏核查调用 |
| 核查 | 15次结构及引文合法，10接受、5拒绝；另1题规划直接不足 | 合法拒绝仍可能是误拒 |
| 原文及范围 | 10个普通答案均等于实际所选持久原文/图像观察；16题全部依赖在请求范围 | 不证明语义支持或像素正确 |
| 配置与预算 | 单题模型最多7次；最大prompt_eval_count=3872 | 原预算未提高，未计作性能指标 |
| 来源与执行器 | 核查摘要、来源选择、调用计数与冻结执行器SHA一致 | 检查基于结构化执行产物，不是独立HTTP抓包或清理后数据库审计 |

各题的具体变化与剩余问题：

- q-dev-004：并发数问题只有TTL等记录，fact判unsupported，返回不足。
- q-dev-008：生产文件容量问题只有分片尺寸/测试记录，返回不足，未把6 MiB当成文件上限。
- q-dev-012：核查模型仍错误地把QA记录判为supported；程序发现显式cedar-prod在所选来源中缺失，否决发布并返回不足。此变化来自程序约束，不能声称模型已学会区分环境。
- q-dev-016：本次范围没有对应Maple来源，规划器直接声明不足，未越界。
- q-dev-007：实际图像观察仅“圆点在卡片内靠左”，没有颜色，核查拒绝。它仍把右端看成左端，本轮只是阻止不完整观察成为正常答案，没有修复像素识别。
- q-dev-014：规划器实际选择了起点/建议/修订/验证4条消息，但核查仍判fact/status不支持而拒绝。开发草稿与助手初步检查认为过程材料齐全，这是本轮暴露的误拒，不能把这次insufficient算成正确拒答。
- q-dev-015：视觉观察写成蓝色/左端，核查认为字段齐全而允许发布；原图圆点在卡片右端，错误仍在。纯文字核查不能替代原图理解。
- 其余4道事实题及3道过程题均发布所选原文；q-dev-003/011的图像观察也发布。该描述是执行和草稿对照，不是独立人工质量判定。

所选原文展示、充分性核查和实际事实正确性是三个不同问题。本轮改善3个原始不足误判，也引入/暴露1个过程题误拒，仍有视觉位置错误；不能据10/6状态计算准确率或宣称论文实验合格。参考标签人工复核、独立质量对比、真实QQ、新协议浏览器和负载仍待后续执行。

## 证据与复现

- [run-06完整记录](evidence/sufficiency/run-06-reviewed-complete.json)、[逐题审阅](evidence/sufficiency/audit-06-reviewed-complete.md)
- [一致性与预算核查](evidence/sufficiency/execution-verification.json)、[核查脚本](evidence/sufficiency/verify-run.py)
- [run-05部分记录](evidence/sufficiency/run-05-reviewed-excerpts.json)、[部分审阅](evidence/sufficiency/audit-05-partial.md)
- [开发重放来源说明](evidence/sufficiency/probe-provenance.json)、[首次](evidence/sufficiency/probe-01.json)、[第二次](evidence/sufficiency/probe-02.json)、[第三次](evidence/sufficiency/probe-03.json)
- [115项后端JUnit](evidence/sufficiency/backend-regressions.xml)

检出977f173可同时复现本次应用与执行器，准备独立测试数据库及同digest模型，再运行（输出必须新建）：

```bash
LUME_TEST_DATABASE_URL=独立测试库连接串 caffeinate -i \
  uv run --frozen python -m scripts.development_pilot run \
  --application-baseline dc77d0e0417264a09a31a520f14e491f489b0425 \
  --output ../outputs/lume-sufficiency/run-new.json
uv run --frozen python -m scripts.development_pilot audit \
  --run ../outputs/lume-sufficiency/run-new.json \
  --output ../outputs/lume-sufficiency/audit-new.json
```

已有安装按operations.md停服务、reindex、处理派生后重启，不混用v4旧任务。本轮随机schema与临时图片已清理，实验Ollama随后停止；原项目数据库、权重保留。没有自动重建原项目索引，没有改论文正文或生成PDF。单设备耗时包含模型加载/调度，且增加一次核查调用，不能作为服务SLA或单因素算法性能比较。
