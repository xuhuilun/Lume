# Lume

面向即时通讯消息的多模态知识检索 Agent 原型，以 QQ 为接入示例。将消息、显式回复和图片组织为带版本的资料，在允许范围内检索、读取上下文和核查原图，再展示回答与来源。

![Lume 查证工作台](docs/assets/workbench.png)

本项目为硕士论文的可复现实验原型。当前核心程序、真实 PostgreSQL/pgvector、Ollama实际权重及浏览器链路已有合成资料联调记录；真实 QQ 账号接入、独立质量评价与负载评价尚未完成。所有内置消息和图片都是人工构造资料，不是企业生产数据。调试样例不能用于声称检索准确率或企业适用性。

## 已有能力

- 消息稳定身份、不可变版本、重复接入去重、停用与来源失效。
- 显式空间读取/维护资格，管理角色不自动取得所有原文。
- 受控图片存储、Tesseract OCR，以及 Ollama 视觉观察接口。
- PostgreSQL 词项检索、pgvector 精确向量检索与 RRF；同一来源不重复计票。
- 持久任务、独立 worker、模型/工具预算、取消、短租约心跳、领取代次及条件提交。
- 观察归属与引用检查；答案依赖覆盖未最终引用的模型输入及历史传递依赖。
- 可显式要求核查原图；此时正常答案必须引用本任务实际视觉观察，不能用OCR或普通消息替代。模型输入中的图片仅提供身份和文件名，OCR/描述继续用于检索索引。
- React 工作台：范围选择、提问、阶段、取消、答案、原文与图片；跨身份和迟到响应隔离。
- QQ 官方 Webhook 挑战、Ed25519 验签、时间窗、去重及预配置群白名单。尚未用真实账号联调。

`demo` 模式使用明确标识的哈希测试向量和抽取式回放，能离线复现流程，**不代表语义模型或大模型质量**；不会根据演示图片编造视觉结论。`ollama` 模式提供实际模型调用适配器，须自行准备服务和权重。

## 启动

需要 Python 3.12、uv、Node.js 22+，以及 PostgreSQL 17 和 pgvector。Tesseract为可选OCR执行器，未安装时记录`OCR_NOT_INSTALLED`，不伪装识别成功。

```bash
git clone https://github.com/xuhuilun/Lume.git
cd Lume
uv sync --frozen --extra dev --python 3.12
cp .env.example .env
```

在`.env`中配置`LUME_DATABASE_URL`。仓库提供数据库的`compose.yaml`；使用它时先在本机设置`POSTGRES_PASSWORD`，并使连接串中的密码一致，再执行`docker compose up -d db`。示例连接串中的密码只表示开发占位值，请替换；本轮实际验证使用隔离的本机PostgreSQL，不声称已验证Docker启动。

```bash
uv run lume init --name admin --token-file .runtime/admin-token
uv run lume seed --user admin
uv run lume worker --drain
cd frontend
npm ci
npm run build
cd ..
```

分别在两个终端运行：

```bash
uv run lume worker
```

```bash
uv run lume serve --port 8000
```

打开[本地工作台](http://127.0.0.1:8000)，粘贴`.runtime/admin-token`文件中的令牌。令牌只保存在当前页面内存，刷新后需重新登录。初始化拒绝覆盖既有身份或令牌文件；数据库为初始schema版本1，不会静默迁移或删除现有数据。

## 模型与规则切换

在本机Ollama中准备[embeddinggemma](https://ollama.com/library/embeddinggemma)、[qwen3:4b](https://ollama.com/library/qwen3:4b)和[qwen2.5vl:3b](https://ollama.com/library/qwen2.5vl:3b)，并按设备能力检查实际可加载条件。仓库不自动下载权重，也不保证这些模型在当前设备上的速度或质量。

修改`.env`中的`LUME_PROVIDER=ollama`及相应模型、端点、`LUME_MODEL_REVISION`。记录实际权重身份，修改后停止API和worker，执行：

```bash
uv run lume reindex
uv run lume worker --drain
```

再启动两个服务。生成模型、向量模型、视觉模型及处理版本共同参与配置身份；旧任务不会在不同配置下静默继续。首版依赖操作员维护`MODEL_REVISION`，尚未自动校验远程权重摘要。

## QQ接入

配置`LUME_QQ_APP_ID`、`LUME_QQ_SECRET`及至少32字符的随机`LUME_QQ_WEBHOOK_TOKEN`，并以管理接口创建明确的群资料空间和资格。回调路径为`/integrations/qq/<webhook-token>`，该路径本身是注册凭据，不能公开或记入代理访问日志；CLI已经关闭API访问路径日志。

将此路径部署为QQ平台可以访问的HTTPS地址，再在开放平台配置事件。普通群@事件和开启后的群消息全量事件均可解析；不假设账号已获得全量或历史记录。未预配置且未开启接入的群会被确认但不入库，不会自动创建公开空间或授予群成员读取权。

详细协议依据、注册签名边界和未完成联调见[QQ核验记录](docs/qq-integration-research.md)。本版仅接收群消息，回答在Web工作台查看，不自动向QQ群发送消息。平台删除/编辑事件和历史批量拉取尚未实现；停用与新版本由管理导入处理。

## 测试与证据

```bash
LUME_TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/TEST_DB \
  uv run pytest -q
uv run ruff check backend
uv run ruff format --check backend
cd frontend && npm run build
```

测试在指定数据库中创建随机测试schema，完成后仅移除该schema；需具备创建schema及使用vector扩展的权限。未配置测试数据库时集成案例会跳过，跳过不能视为通过。

浏览器测试需运行已初始化并导入合成资料的API及worker，并准备第二个名为`browser-bob`的独立测试身份：

```bash
uv run lume user browser-bob --token-file .runtime/browser-bob-token
uv run lume seed --user browser-bob
cd frontend
npx playwright install chromium
LUME_UI_TOKEN_FILE=../.runtime/admin-token \
LUME_UI_SECOND_TOKEN_FILE=../.runtime/browser-bob-token \
  npx playwright test
```

首版执行记录为[25项后端测试与3项浏览器测试](docs/validation.md)，相关环境、首次失败及修订均保留。它们不能替代论文中34个计划项目的完整验收，更不能证明生产隔离、性能或大模型正确性。

2026-11-03续行增加真实模型联调和“核查原图”选项，共33项后端回归通过，并实际通过1项使用Ollama、独立API/worker与真实浏览器的核图案例。早期失败、固定权重身份和复现方式见[真实模型验证](docs/real-model-validation.md)。普通模式不据此宣称已准确自动识别所有视觉需求；三条调试问题不构成独立测试集。

## 文档与实现范围

- [架构](docs/architecture.md)、[实施计划](docs/implementation-plan.md)
- [运行与接口](docs/operations.md)
- [验证记录](docs/validation.md)、[源码与论文证据审校](docs/thesis-evidence-audit.md)
- [真实模型联调计划](docs/real-model-validation-plan.md)、[实际记录与复现](docs/real-model-validation.md)
- [48题合成参考证据集说明](docs/evaluation-dataset.md)、[逐题审阅册](docs/evaluation-reference-review.md)、[人工复核记录](docs/evaluation-human-review.md)

参考证据集包含12情景、72条消息和12张合成原图，按情景划为16题开发/32题保留。参考标签由助手编制，全部待人工复核；本阶段没有在这些问题上运行目标模型或计算质量分数。查询与离线标签分开，任务转换只传问题、范围和核图要求。构建、完整性检查及使用限制见上述说明；不能把结构检查通过称为人工标注完成。

首版尚无SSO、密码/会话登录、自动孤立文件清理、近似向量索引、检索单路降级或完整运行管理界面；历史回用通过API显式传入`history_ids`，首版界面每次独立提问。实现与论文方案的差异需要保留，后续以实际代码及测试改写对应章节。
