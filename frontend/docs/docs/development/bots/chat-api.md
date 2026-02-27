# 问答机器人 (OpenAI 兼容)

> [!IMPORTANT]
> **本接口为 OpenAI 兼容接口，支持“即插即用”！**
> 您可以直接在支持 OpenAI 协议的第三方客户端中填写 CatWiki 地址，无需任何代码修改即可实现知识库能力的无缝接入。

问答机器人 API 完全兼容 OpenAI Chat Completion 标准协议。这意味着您可以将其作为 OpenAI 的掉包替换方案，无缝接入 Cherry Studio、NextChat、Chatbox 等主流 AI 客户端，或是集成到您自己的业务系统中。

## 1. 核心接入信息

通过该接口，外部应用可以利用 CatWiki 的“知识库检索 + AI 推理”核心能力。

### 1.1 接口凭据
- **API Base (接口地址)**: `http://localhost:3000/v1/bot`
  - *注：在客户端配置时，通常填写该地址。完整的端点为 `/v1/bot/chat/completions`*。
- **API Key (密钥)**: 在 CatWiki 后台为特定站点生成的授权令牌。
  - **关键点**：每一个 API Key 都直接绑定了一个特定的“知识库站点”，调用时无需手动传入站点 ID，系统会自动识别。

### 1.2 兼容配置
在接入第三方 AI 客户端（如 Cherry Studio）时，请使用以下路径信息：

- **API Base (接口基地址)**: `http://localhost:3000/v1/bot`
- **完整端点预览**:
  - **对话**: `http://localhost:3000/v1/bot/chat/completions`
  - **模型**: `http://localhost:3000/v1/bot/models`

## 2. 客户端接入示例

以 **Cherry Studio** 或 **NextChat** 为例，配置方式如下：

1.  **添加自定义模型服务 (OpenAI 兼容)**：
    - **API 地址**: `http://您的服务器IP:3000/v1/bot`
    - **API 密钥**: `您的站点 API Key`
2.  **模型名称**: 
    - 您可以手动填写 `catwiki`。
    - 或者点击“获取模型列表”，客户端会自动拉取该站点配置的生效模型。

### CURL 命令行调用
```bash
curl -X POST http://localhost:3000/v1/bot/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "messages": [
      {"role": "user", "content": "根据知识库内容，介绍一下 CatWiki"}
    ],
    "model": "catwiki",
    "stream": true
  }'
```

---

## 3. 技术特性

- **OpenAI 协议对齐**：支持 `messages` 历史上下文、`stream` 流式输出、`temperature` 等标准参数。
- **自动知识增强 (RAG)**：API 内部自动完成：
    1. **问题重写**：针对对话上下文优化查询。
    2. **向量检索**：从关联站点调取最相关的知识切片。
    3. **引用归注**：在返回的 Token 流中包含知识来源（取决于客户端解析能力）。
- **长连接保障**：基于标准 HTTP 协议，具备极高的稳定性和兼容性，支持内网穿透集成。
