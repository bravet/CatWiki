# Admin API

Admin API 提供完整的 CRUD 操作和管理功能，需要身份认证。

## 🔐 认证

所有 Admin API 都需要 JWT Token 认证。

### 获取 Token

```typescript
const response = await apiClient.adminUsers.loginAdmin({
  requestBody: {
    email: "admin@example.com",
    password: "admin123"
  }
})

const token = response.data.token
```

### 使用 Token

```typescript
// 在请求头中添加 Token
headers: {
  'Authorization': `Bearer ${token}`
}
```

---

## 📚 API 端点

### 用户管理

- `POST /admin/api/v1/users:login` - 用户登录
- `POST /admin/api/v1/users:invite` - 邀请用户
- `GET /admin/api/v1/users` - 获取用户列表
- `GET /admin/api/v1/users/{id}` - 获取用户详情
- `POST /admin/api/v1/users` - 创建用户
- `PUT /admin/api/v1/users/{id}` - 更新用户
- `PUT /admin/api/v1/users/{id}/password` - 修改密码
- `POST /admin/api/v1/users/{id}:resetPassword` - 重置密码
- `DELETE /admin/api/v1/users/{id}` - 删除用户

### 站点管理

- `GET /admin/api/v1/sites` - 获取站点列表
- `GET /admin/api/v1/sites/{id}` - 获取站点详情
- `GET /admin/api/v1/sites:byDomain/{domain}` - 通过域名获取站点
- `POST /admin/api/v1/sites` - 创建站点
- `PUT /admin/api/v1/sites/{id}` - 更新站点
- `DELETE /admin/api/v1/sites/{id}` - 删除站点

### 文档管理

- `GET /admin/api/v1/documents` - 获取文档列表
- `GET /admin/api/v1/documents/{id}` - 获取文档详情
- `POST /admin/api/v1/documents` - 创建文档
- `PUT /admin/api/v1/documents/{id}` - 更新文档
- `DELETE /admin/api/v1/documents/{id}` - 删除文档
- `POST /admin/api/v1/documents:batchVectorize` - 批量向量化
- `POST /admin/api/v1/documents/{id}:vectorize` - 向量化文档
- `POST /admin/api/v1/documents/{id}:removeVector` - 移除向量

### 合集管理

- `GET /admin/api/v1/collections` - 获取合集列表
- `GET /admin/api/v1/collections/{id}` - 获取合集详情
- `GET /admin/api/v1/collections:tree` - 获取合集树
- `POST /admin/api/v1/collections` - 创建合集
- `PUT /admin/api/v1/collections/{id}` - 更新合集
- `POST /admin/api/v1/collections/{id}:move` - 移动合集
- `DELETE /admin/api/v1/collections/{id}` - 删除合集

### 文件管理

- `POST /admin/api/v1/files:upload` - 上传文件
- `POST /admin/api/v1/files:batchUpload` - 批量上传
- `GET /admin/api/v1/files:list` - 列出文件
- `GET /admin/api/v1/files/{path}:download` - 下载文件
- `GET /admin/api/v1/files/{path}:info` - 获取文件信息
- `GET /admin/api/v1/files/{path}:presignedUrl` - 获取预签名 URL
- `DELETE /admin/api/v1/files/{path}` - 删除文件

### 缓存管理

- `GET /admin/api/v1/cache:stats` - 获取缓存统计
- `POST /admin/api/v1/cache:clear` - 清空缓存

### 系统配置

- `GET /admin/api/v1/system-configs` - 获取所有配置
- `DELETE /admin/api/v1/system-configs/{config_key}` - 删除指定配置
- `GET /admin/api/v1/system-configs/ai-config` - 获取 AI 配置
- `PUT /admin/api/v1/system-configs/ai-config` - 更新 AI 配置
- `POST /admin/api/v1/system-configs/ai-config/test-connection` - 测试模型连接
- `GET /admin/api/v1/system-configs/bot-config` - 获取机器人配置
- `PUT /admin/api/v1/system-configs/bot-config` - 更新机器人配置
- `GET /admin/api/v1/system-configs/doc-processor` - 获取文档处理服务配置
- `PUT /admin/api/v1/system-configs/doc-processor` - 更新文档处理服务配置

- `POST /admin/api/v1/system-configs/doc-processor/test` - 测试文档处理服务连接

### 租户管理 (EE)

- `GET /admin/api/v1/tenants` - 获取租户列表 (Admin Only)
- `POST /admin/api/v1/tenants` - 创建租户 (Admin Only)
- `GET /admin/api/v1/tenants/current` - 获取当前上下文租户
- `GET /admin/api/v1/tenants/{id}` - 获取租户详情
- `PUT /admin/api/v1/tenants/{id}` - 更新租户信息
- `DELETE /admin/api/v1/tenants/{id}` - 级联删除租户及数据

### 统计信息

- `GET /admin/api/v1/stats:siteStats` - 获取站点统计

---

## 📖 详细文档

完整的 API 文档请访问：http://localhost:3000/docs

---

## 📚 相关文档

- [API 概览](/development/api/overview)
- [Client API](/development/api/client)
- [SDK 使用指南](/development/tech/sdk-usage)
