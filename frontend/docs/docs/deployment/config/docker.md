# Docker 配置

本文档提供 Docker 环境的详细配置说明。

## 📋 Docker Compose 配置

CatWiki 使用 Docker Compose 管理多个服务容器。

### 开发环境配置

配置文件：`docker-compose.dev.yml`

**服务列表：**
- `postgres` - PostgreSQL 数据库
- `rustfs` - RustFS 对象存储
- `backend-init` - 后端初始化服务
- `backend` - FastAPI 后端服务
- `admin-frontend` - 管理后台前端
- `client-frontend` - 客户端前端
- `docs-frontend` - 文档站点

### 生产环境配置

配置文件：`deploy/docker/docker-compose.yml`

详见 [Docker 部署指南](/deployment/guide/docker)。

---

## 🔧 常用配置

### 端口映射

```yaml
services:
  backend:
    ports:
      - "3000:3000"  # 后端 API
  
  admin-frontend:
    ports:
      - "8001:8001"  # 管理后台
  
  client-frontend:
    ports:
      - "8002:8002"  # 客户端
  
  docs-frontend:
    ports:
      - "8003:8003"  # 文档站点
```

### 资源限制

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
    reservations:
      cpus: '0.5'
      memory: 512M
```

---

## 📚 相关文档

- [环境配置](/deployment/config/environment)
- [Docker 部署](/deployment/guide/docker)
- [快速开始](/development/start/quick-start)
