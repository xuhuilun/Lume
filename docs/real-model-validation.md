# 真实模型联调复现说明

本说明对应`scripts/validate_real_models.py`。执行计划见[real-model-validation-plan.md](real-model-validation-plan.md)。程序验证使用四条固定人工合成消息及一张合成图片，不读取已有聊天资料，不调用QQ。

## 准备与执行

本轮使用macOS arm64、16 GB统一内存和Ollama 0.40.11。为限制并发占用，验证服务只监听本机独立端口，最多加载一个模型，不影响默认11434端口配置。

```bash
OLLAMA_HOST=127.0.0.1:11435 OLLAMA_NO_CLOUD=1 \
OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_NUM_PARALLEL=1 \
OLLAMA_CONTEXT_LENGTH=4096 ollama serve
```

在其他终端下载既有适配器配置指定的模型。下载与推理分开；下载成功不表示模型推理或任务验收成功。权重保留在Ollama自身模型目录，不加入源码归档。

```bash
OLLAMA_HOST=127.0.0.1:11435 ollama pull embeddinggemma
OLLAMA_HOST=127.0.0.1:11435 ollama pull qwen3:4b
OLLAMA_HOST=127.0.0.1:11435 ollama pull qwen2.5vl:3b
```

使用独立测试数据库连接，并将结果写入不同文件。优先通过环境设置连接串，避免将密码直接写入可见命令；不要将连接串提交Git。脚本只向本机Ollama发送合成内容，不接受远程模型地址。

```bash
uv run --frozen python scripts/validate_real_models.py \
  --ollama-url http://127.0.0.1:11435 \
  --output ../outputs/lume-real-model/run-01-baseline.json
```

运行前设置`LUME_TEST_DATABASE_URL`，需具备创建schema及使用vector扩展权限。脚本创建随机`modelcheck_*` schema和内存令牌，结束时仅移除该schema与临时图片目录。不会初始化、重建或清空public表。不要在企业生产数据库上执行实验。程序通过ASGI transport调用真实业务API函数，与真实数据库和Ollama通信；这不是浏览器或公网HTTP部署验收。

默认沿用90秒任务期限。若排障需要用`--task-timeout`改变期限，须单独命名结果并披露；不得覆盖默认配置下的失败，或据此声称默认期限已经达标。

## 记录与判读

结果包含源码提交、工作树状态、验证脚本SHA256、选中权重的digest与量化信息、配置身份、向量维数及实际向量、结构化动作、图像观察、处理状态、任务轨迹、答案、引用、依赖及清理状态。只记录模型最终结构化决策，不记录内部思维文本；不输出身份令牌和数据库连接串。

`status=returned`只表示该阶段函数返回。任务可能返回failed、limited或insufficient，必须结合终态判断。`workflow_checks`是预先固定的流程判据，不是准确率：向量返回、首次动作search、视觉返回、四条派生就绪、图片处理完成、文本答案发布、图片答案实际引用image_observation、无依据问题标为insufficient、临时schema清理。任一流程判据失败或调用异常时进程非零退出，报告仍保留。语义正确性另作人工对照，不能因JSON合法而判定。

联调问题固定为：v1.8连接池故障的处理与复测；图中pool_size和status；资料未记录的v9.9显存容量。参考事实分别为pool_size由5改为20后复测恢复且仅明确适用于v1.8、图中20/healthy、无资料支持显存数字。第三项不能凭常识补造数值。模型输出与参考存在差异时，应记录差异；本脚本不是隐藏测试集，不能用于泛化效果结论。

## 阶段状态

2026-11-03：隔离模型服务已启动，三种权重下载中；原25项后端案例通过（4.23秒为套件耗时，不是业务延迟），Ruff与格式检查通过。尚未将模型下载、推理或端到端流程登记为通过，实际结果随运行记录补充。

## 官方依据

- [向量接口](https://docs.ollama.com/api/embed)：`truncate=false`超限报错，不能将超限解释为没有证据。
- [结构化输出](https://docs.ollama.com/capabilities/structured-outputs)：JSON schema约束输出结构，应用仍应验证。
- [思考模式](https://docs.ollama.com/capabilities/thinking)：`think`控制取决于模型，内部思维与最终内容分离，默认行为不能靠“不输出思维”的自然语言指令推断。
- [本地服务与并发配置](https://docs.ollama.com/faq)：端口、上下文和已加载模型均为显式实验条件。

这次先完成联调，再开展经审核的参考证据集与质量比较；不将上述四条消息作为正式评测集，不生成论文PDF。
