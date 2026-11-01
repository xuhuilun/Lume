# QQ官方接入核验

访问日期：2026-11-01。只依据腾讯官方文档，未使用第三方协议登录。

- [事件订阅与通知](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html)：Dispatch、Webhook ACK、挑战验证与HTTPS配置，事件订阅受权限影响。
- [安全和授权](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/sign.html)：Ed25519；Secret重复至32字节种子；验证timestamp与原始HTTP body的组合。回调挑战单独签event_ts与plain_token。测试使用该页公开验证向量，不保存真实Secret。
- [群@机器人消息](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/group_at_message_create.html)：消息、群和成员OpenID、时间及附件，重复事件需去重。
- [群消息全量模式](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/group_message_create.html)：开启接收全部消息后推送，与@事件字段对应。页面访问初次失败，经官方概述链接读取成功；不将全量能力默认视为账号已开启。
- [消息收发概述](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/overview.html)：区分群、单聊及频道。本版仅接收群消息，不实现或测试真实发送。

引用关系只保留官方显式索引；无法映射的ref_msg_idx保留原始引用键，不根据邻近时间伪造回复。消息分群用于资料组织，Lume的读取许可仍由显式空间资格决定。公网QQ接入、权限实际开通及附件URL有效性须后续真实账号联调。
