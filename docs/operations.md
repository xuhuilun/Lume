# 运行、接口与边界

## 进程和配置

API负责认证与任务受理，worker独立领取资料处理或查证。默认单worker顺序执行，未进行吞吐或多实例压力测量。API默认仅监听127.0.0.1，公网部署需另设HTTPS和访问控制代理，尤其不得记录带注册凭据的QQ回调路径。

默认期限90秒、租约15秒，活跃任务通过匹配状态与代次的心跳续租；崩溃后可在原期限内重新领取，累计额度和期限不重置。任务最多12次模型尝试、8次工具动作、2次图像观察，输入上下文为字符上限；这些是可配置默认值，不是优化或性能结论。

`lume reindex`发布当前规则并重新安排活跃来源，旧执行者不得发布过期产物。`lume disable-user NAME`撤销该身份的后续API及模型输入资格；已经发送的内容无法撤回。`lume user NAME --token-file PATH`由本地运行管理者生成随机令牌，文件仅首次以0600权限写入；不提供匿名注册接口。

## 首版API

所有`/api`业务接口使用`Authorization: Bearer ...`，`/api/health`除外。响应格式由工作台运行时校验其使用字段，不依赖TypeScript注解自动保护网络输入。

| 接口 | 作用 |
| --- | --- |
| GET /api/me | 核对身份 |
| GET/POST /api/spaces | 列出获准空间/由管理者创建空间 |
| PUT /api/spaces/{space}/grants/{user} | 由有维护范围的管理者设置读取与维护资格 |
| POST /api/spaces/{space}/imports | 接受`messages`数组，保存版本并安排处理 |
| GET /api/spaces/{space}/messages、/jobs | 读取当前消息/维护处理状态 |
| POST /api/messages/{id}/deactivate | 在维护范围内停用来源 |
| GET/POST /api/tasks | 本人任务列表/提交问题 |
| GET /api/tasks/{id}、/{id}/events | 状态及受控阶段，不含答案正文 |
| POST /api/tasks/{id}/cancel | 幂等受理取消，不能据此证明外部模型停止计算 |
| GET /api/answers/{id} | 检查全部直接/传递来源依赖后返回答案 |
| GET /api/observations/{id}、/api/images/{id} | 按归属、版本与当前资格读取证据 |

任务提交示例：`{"question":"E_CONN_42如何处理","space_ids":["获准空间ID"],"history_ids":[],"require_image":false}`。返回202及任务身份只表示受理。`history_ids`是已有答案ID；当前范围不能覆盖其全部依赖时拒绝回用。

`require_image`默认为false；在工作台选中“核查原图”即提交true，并冻结到该任务config。此时正常答案必须引用本任务semantic=true的image_observation，普通消息/候选或演示模式不具备此资格；拒绝为IMAGE_EVIDENCE_REQUIRED时没有答案发布。该标记表示已取得视觉服务的非空返回，不证明图像事实正确。没有可用原图时可返回insufficient，不放宽条件。普通模式保留由模型选择核图的路径，自动视觉意图识别仍待独立评价。

Ollama输入的message_context仅保留消息原文及图片id/filename，不把OCR、视觉描述或图片处理状态当作已核原图事实；它们仍保留在受控API、持久观察和检索索引中。Ollama生成schema按实际观察限制可用动作和目标，非空候选先读取原文；Runner仍独立校验资格、目标、预算及引用。请求使用think=false，该设置在本轮服务和权重上实际返回，不能假设任意模型均兼容。

接入格式示例：

```json
{"messages":[{"source_id":"synthetic-m1","text":"用于示例的历史处理","sent_at":"2026-11-01T08:00:00Z","author":"合成用户","images":[]}]}
```

可选`reply_to`及`reply_kind`分别标明已知消息键或QQ显式索引；图片以`filename`和`base64`或受白名单控制的`url`描述。单次请求受字节上限约束；图片仅允许PNG/JPEG/WEBP，并检查字节和像素。接入批次按整体事务提交，尚无逐对象部分提交；失败前写入的未关联图片可能成为孤立文件，自动回收未实现，不能直接删除仍被引用的文件。

## 表示与结果限制

当前一条消息版本对应一个图文文字检索单元，中文词项采用字符/双字片段，技术标识保留相应token。图文派生表达及上下文受输入上限约束，不声称完整保留全部视觉或长讨论信息。embeddinggemma等实际模型有自己的上下文限制，超限会记录处理失败，而非据此判断来源没有相关事实。

向量检索采用精确距离，没有HNSW/IVFFlat索引或查询计划优化。模型或查询路径失败当前结束任务，未实现论文设想的单路降级。配置身份包含模型名称和操作员版本标识，不能据此宣称自动锁定了远程权重。

图像观察与回答属于模型输出，程序检查结构、来源、资格和显式任务要求，不证明语义正确。演示模式不作视觉判断；真实Ollama已完成2026-11-03固定合成资料联调，见real-model-validation.md。无真实企业数据、模型准确率、生产用户、QPS或响应时间达标结论。

证据选择改进将Ollama规则身份升为v4、演示模式升为v2。更新任一已有安装后停止API/worker，执行`lume reindex`、`lume worker --drain`后重启；旧规则任务不会静默沿用新提示或协议。实验脚本按实际权重摘要生成版本标识，普通安装仍需操作员维护MODEL_REVISION。


## 原文依据展示与开发复测

新Ollama协议仅返回依据选择或资料不足。正常展示内容来自持久观察中的完整消息原文，或明确标为模型识别结果的图像观察。最多4项、答案上限12000字符；超限会记录EVIDENCE_TOO_LARGE，不静默截取。选择无依据时EVIDENCE_REQUIRED，非法归属/成员为INVALID_EVIDENCE。原文存在不表示所问事实已得到验证，操作员仍需核对限定和图像事实。

read_context现返回window对象，含max_messages=12、max_hops=4、truncated及ambiguous_links；不再是一层父子窗口标记。检索观察包含exact_anchors，表示本次字面过滤。技术标识不存在时两路不回退到无关来源；没有标识的查询仍可宽召回。

开发复测入口可显式指定--application-baseline提交，默认仍指向旧冻结基线；程序会拒绝应用目录与该提交不一致的执行。每次输出必须新建文件，保留旧失败记录。执行阶段不解析参考标签或保留题，离线审计只读取开发标签。需要复现时使用本轮记录内source_commit及模型摘要，不能以当前main替代历史执行版本。


核图专用answer结构必含image_evidence，evidence容纳至多3项额外消息/图像选择；普通answer保持至多4项选择。两者均转换为内部选择后重新绑定持久来源，不能绕过require_image。v3开发运行的图像选择遗漏及失败保留，修正后的最终规则为Ollama v4 / Demo v2。

## 充分性核查升级

最终Ollama规则现为v5，Demo仍v2；answer_contract由服务端冻结为reviewed-excerpts-v1，客户端不能覆盖。已有Ollama安装停API/worker、执行reindex与worker --drain后重启。旧v4任务不会静默采用新核查；本轮实验使用隔离schema，不自动改原数据。

support_review计入模型12次累计额度；额外调用可能增加耗时或触及原90秒期限，失败与limited不能统计为资料不足。合法核查拒绝为insufficient，坏结构或非原文引文为SUPPORT_REVIEW_INVALID/failed；缺少核查、跨任务/错配摘要、未通过核查均不能正常发布。核查观察不是citation来源。显式环境名采用精确匹配，未声明的别名对应关系可能导致保守拒绝。

开发执行日志按purpose区分planning/embedding/vision/support_review；审阅另列提议来源、实际发布来源及四维核查，不能把核查调用增加视为质量提升。保留题未运行、人审0、正式质量与负载仍需后续执行。

## v6图像标记与显式服务工厂

Ollama规则升v6、Demo保持v2。标记颜色/相对位置问题采用本次原图的OCR标签锚定、可见像素边框/色块候选及模型配对核查，颜色与位置由像素/组件几何计算。只适用于可识别显式标签、边框与高饱和标记的界面图；无唯一标签、边框、标记或存在歧义时semantic=false，不能回退文字猜测。general仍支持其他图像文字/数值问题。OCR是本次原图读取的一部分，不是将索引描述冒充原图。候选显示上限16，但歧义统计使用截断前全部合格候选；透明和半透明像素不提供颜色/边框事实。

API导入不再创建默认应用或读取当前目录.env。正常启动继续使用`lume serve`，其显式传入已创建配置与会话；直接使用Uvicorn时入口为`uvicorn lume.api:create_app --factory`，旧`lume.api:app`入口不再提供。隔离测试显式传Settings(_env_file=None)，不得借测试读取原项目配置。升级仍按停服务、reindex、处理派生后重启流程。
