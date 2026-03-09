# 企业微信智能机器人

> [!NOTE]
> **"企业微信智能机器人"是企业微信管理后台提供的一种独立能力**，与传统的"自建应用机器人"相比，它主要面向流式会话和群聊交互。

企业微信智能机器人通过 **WebSocket 长连接**方式集成，无需配置公网回调地址，部署更灵活。与普通的"自建应用"不同，智能机器人配置更为精简，只需 **Bot ID** 和 **Secret** 两项凭据。

## 推荐场景
- **对内办公助手**：将其加入内部员工群，作为 IT 支持、行政查询或内部知识库的入口。
- **业务数据播报**：利用其长连接能力，结合 CatWiki 的 AI 分析，在群内推送带分析性质的日报。
- **私域内部协同**：仅限企业内部员工使用，无法直接对普通外部微信用户提供服务。


## 1. 企业微信管理后台配置

### 1.1 开启智能机器人
1. 登录 [企业微信管理后台](https://work.weixin.qq.com/wework_admin/loginpage_wx)。
2. 进入 **"安全与管理" -> "管理工具" -> "智能机器人"**。
   ![管理工具](/images/roboot/wecom-smart/wecom-smart-1.png)
3. 点击 **"开启智能机器人"**（如果尚未开启）。
4. **创建机器人**：点击"添加机器人"，选择最新推荐的 **"长连接"** 模式。长连接模式无需配置公网回调地址，服务端会主动推送消息。
   ![创建机器人](/images/roboot/wecom-smart/wecom-smart-2.png)

### 1.2 获取凭据
1. 创建完成后，在机器人详情页可以看到 **Bot ID** 和 **Secret**。
2. **记录凭据**：
   - 复制 **Bot ID**（格式类似 `aiboXXXXXXXXXXXXXXXX`）。
   - 复制 **Secret**。
   ![获取凭据](/images/roboot/wecom-smart/wecom-smart-3.png)

## 2. CatWiki 后台配置

1. 进入 CatWiki 后台 **"站点设置" -> "AI 机器人"**。
   ![AI机器人集成](/images/screenshots/8.png)

2. 找到 **"企业微信智能机器人"**，开启开关。
3. **填入配置**：
   - **Bot ID**：填入从企微后台获取的 Bot ID。
   - **Secret**：填入从企微后台获取的 Secret。

   ![AI机器人集成](/images/roboot/wecom-smart/wecom-smart-4.png)
4. 点击界面上的 **"保存"**。CatWiki 后端将自动建立 WebSocket 长连接，保存成功即可生效，无需额外的验证步骤。

> [!TIP]
> 与旧版 Webhook 回调模式不同，长连接模式**无需公网 IP 或域名**，CatWiki 部署在内网也能正常工作。

## 3. 技术特性
- **连接方式**：WebSocket 长连接（`wss://openws.work.weixin.qq.com`），由 CatWiki 主动发起连接。
- **流式回复**：✅ 原生支持（通过 `aibot_respond_msg` 的 stream 模式实现实时流式输出）。
- **心跳保活**：由企微服务器发送 `aibot_ping`，CatWiki 自动回复 `aibot_pong`。
- **自动重连**：连接异常断开后自动重连，采用指数退避策略（5s → 10s → 20s → ... → 60s）。
- **热更新**：在后台修改 Bot ID / Secret 后，无需重启服务，保存即自动生效。
