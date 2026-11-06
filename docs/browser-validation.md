# 新协议独立 HTTP 与浏览器验证

日期：2026-11-06。本文件说明本轮新建执行器，实际执行记录须另行保存。当前完成的是执行器、用例和确定性检查，不据此宣称真实模型或浏览器验证通过。未生成 PDF，也不使用开发/保留评测题。

## 隔离与执行

`scripts/browser_validation.py`创建随机`browser_*` PostgreSQL schema，仅在其中建立表和合成身份。API与worker为独立子进程，通过本机真实HTTP通信。子进程从0600临时配置文件构造`Settings(_env_file=None)`，不读取项目`.env`；令牌只写一次到0600临时文件，不加入源码、公共报告或截图。结束后停止自建API/worker、删除随机schema、配置、令牌和临时图片目录，原项目数据不变。

应用默认入口已改为显式app工厂；执行器直接导入工厂并提供Settings，不做临时工作目录切换。调用者dotenv错误/不可信的子进程回归用于验证导入不读取它。

执行前必须提交当前实现、冻结应用提交，完成前端构建，并准备与`docs/evidence/real-model/model-manifest.json`相同digest的本机Ollama权重。执行器不会启动或停止共享Ollama服务，不自动下载权重。输出文件与截图目录必须新建，旧失败不覆盖。

```bash
cd frontend
npm run build
cd ..
LUME_TEST_DATABASE_URL=独立测试库连接串 caffeinate -i \
  uv run --frozen python -m scripts.browser_validation run \
  --application-baseline 冻结应用提交 \
  --read-seconds 10 \
  --output ../outputs/lume-validation-cycle/browser-run-03-sustained.json
```

端口默认由执行器选择本机未绑定端口，可用`--port`显式指定；已有端口不抢占。`caffeinate`只是macOS宿主保护，不证明主机不会休眠或时钟不会变化。服务原期限、累计额度与租约条件不因浏览器超时而放宽。

## 三类浏览器检查

`frontend/tests/reviewed-workbench.spec.ts`通过界面登录和提问，不伪造模型或业务响应：

1. 全新合成`BROWSER_CONN_47`在`browser-stage-r1`的已验证连接上限，检查发布原文、真实来源展示。
2. 只有连接参数而没有单文件容量记录，检查资料不足状态、固定说明和空引用。
3. 实际勾选核图，检查提交参数、正常答案引用本任务真实`image_observation`、观察文字非空、受控图片实际解码，以及桌面/移动截图；该检查不判断视觉文字与像素事实是否正确。

所有正常答案还从数据库检查support_review合法且接受、核查不能被当成原文引用，模型调用计数与ActionRecord相符。退出重新连接后核图选项应重置。普通浏览器完成、图片可见和引用合法都不能当作语义正确率或真实QQ接入验收。

## 有边界的Web API读取并发测量

浏览器三项通过后，执行器调用`scripts/read_load_validation.py`中的测量函数。仅对本次合成身份的`health`、获准空间、获准消息和本人已完成答案做GET；单请求timeout为10秒。默认`--read-seconds 0`保留并发1/4/8各96请求的原语义，四条路径各24次；另有每条路径1次预热，预热不混入测量请求。

设置`--read-seconds 10`后，每档使用固定数量并发worker连续发起GET，直到同时满足至少96个请求和至少10秒单调计时窗口，最后等待已发起请求完成。每档最多20000个请求；若先达到该上限而窗口未满足，就停止并记录`safety_cap_triggered=true`、`window_satisfied=false`，不空等来凑时长。记录实际请求数和各路径轮转数量，不能仍按96或288计算吞吐。此时四条路径数量可能相差1。独立读取脚本对应参数为`--minimum-seconds`，默认同为0。

报告同时给出`minimum_request_count`、`minimum_seconds`、`maximum_request_count`、是否触及上限、是否由上限导致目标未满足，以及全部窗口是否满足。浏览器通过与读取窗口满足是分别记录的结果，不能把触及安全上限的短窗口冒充10秒持续观察。

原始记录含HTTP状态、传输错误类别、每次耗时、墙钟/单调计时、p50/p95及每秒完成HTTP请求数。分位数采用最近秩：排序后索引`ceil(p*n)-1`，p为0.50/0.95；总体包括完成的错误响应和传输错误尝试，成功2xx数量另列。吞吐为该档全部完成尝试数除以单调计时窗口。

单请求延迟从并发worker分派请求后计至响应或传输错误，不含尚未发起请求的本地等待；整档单调窗口包含所有请求的调度和完成。每次尝试与整档窗口均保留墙钟、单调耗时，以便暴露宿主暂停/时钟改变等混杂条件。

执行器比较读取窗口前后的模型调用记录及持久动作数，不一致就判验证失败。即使开启每档10秒持续窗口，此数据也只是本机、单API进程、少量合成资料的只读端点观察，不含模型推理，不称为系统/模型QPS、容量边界、服务SLA或完整负载验收。单独运行read_load_validation时，调用方未验证模型空闲，报告会明确标示这一缺口。

## 报告边界

公共报告保留任务、动作、观察、实际原文与最终content，图片在模型请求记录中只保留摘要/字节数；内部思维和凭据不导出。Playwright JSON会替换临时令牌字面值及本机路径，原始服务日志留在临时目录且不归档。记录不是完整未处理的HTTP抓包，也不代替独立数据库审计、人工标签复核、保留集质量实验、真实QQ或生产授权同步验证。
