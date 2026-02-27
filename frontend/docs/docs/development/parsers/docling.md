# Docling 解析器

Docling 是 IBM 开源的文档处理引擎，专为企业级文档解析设计。它支持 PDF、Word、PPT、HTML 等多种格式，擅长处理复杂的版面布局、表格、公式等元素。CatWiki 已无缝集成 Docling 作为核心解析后端之一。

## 环境要求

在部署 Docling 之前，请确保您的设备满足以下条件：

- **硬件**：包含 NVIDIA 显卡（如 RTX 30/40 系列），显存建议 > 8G（用于 OCR 和大文件处理）。
- **驱动**：NVIDIA 显卡驱动版本建议 > 550.54.14，且已安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)。
- **软件**：已安装 Docker 和 Docker Compose。

## 部署服务

### Docker Compose 部署 (推荐)

使用官方 CUDA 12.6 镜像可获得极致性能。以下配置利用 Docling 的原生机制实现**全自动模型下载**，无需任何初始化脚本。

创建 `docker-compose.yml`：

```yaml
services:
  docling-serve:
    image: ghcr.io/docling-project/docling-serve-cu126:main
    container_name: docling-serve
    ports:
      - "8002:5001"
    environment:
      # 1. 指定 HuggingFace 国内镜像源，加速下载
      HF_ENDPOINT: "https://hf-mirror.com"
      DOCLING_SERVE_ENABLE_UI: "true"
      NVIDIA_VISIBLE_DEVICES: "0"
      DOCLING_SERVE_API_KEY: "4GiLk4WPeh"
      DOCLING_NUM_THREADS: "50"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ["0"]
              capabilities: [ gpu ]
    restart: always
```

### 启动服务

```bash
docker compose up -d
```

启动完成后，访问 `http://<server-ip>:8004/docs` 可进入 Swagger 交互式文档界面。

## CatWiki 集成配置

部署完成后，在 CatWiki 管理后台进行如下配置：

1. 进入 **设置** → **文档解析**
2. 点击 **添加解析器**
3. 填写配置：
   - **名称**：`Docling` (可自定义)
   - **类型**：选择 `Docling`
   - **API 端点**：`http://<docling-ip>:8004` (注意端口是映射出来的 8004)
4. 点击 **测试连接**。
5. 启用并保存。

## 适用场景

Docling 特别适合以下场景：

- 🏢 **企业文档**：批量处理报告、技术说明书等。
- 📊 **结构化提取**：精准提取 PDF 中的多行复杂表格。
- 🖼️ **图文混排**：支持提取文档图片并生成公开链接，供 AI 直接引用。
- ⚖️ **轻量级需求**：相比 MinerU，Docling 对资源的需求相对可控。

## 常见问题

### Q: GPU 加速没有生效？
请检查 Docker 运行时（Runtime）是否已正确配置。可通过 `docker info | grep -i runtime` 确认是否包含 `nvidia`。如果未配置，请参考 [NVIDIA 容器工具安装说明](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html#configuring-docker)。

### Q: 解析超大 PDF 时内存溢出 (OOM)？
Docling 在处理数百页的复杂 PDF 时会消耗较多显存/内存。建议：
- 增加宿主机的 Swap 空间或容器内存限制。
- 将超长文档切分后再上传。

## 相关链接

- [docling-serve GitHub 仓库](https://github.com/docling-project/docling-serve)
- [docling-serve 官方部署指南](https://github.com/docling-project/docling-serve/blob/main/docs/deployment.md)
