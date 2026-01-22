# MCP HTTP 适配规范（Core 侧）

本规范定义 Core 如何把 `tool.list` / `tool.invoke` 映射到现有 MCP 的 HTTP 接口，
以便保持 MCP 现有实现不变，同时让 UI 统一走 Core 的 JSON-RPC 通道。

## 1. 适配目标
- UI/Overlay 只对接 Core（JSON-RPC/WS）
- Core 通过 HTTP 调用 MCP
- MCP 保持独立部署与版本演进

## 2. Tool 定义映射
Core 的 `tool.list` 返回的数据结构，来源于 MCP 的工具描述。

**Core 输出（JSON-RPC）**
```json
{
  "tool_id": "ocr.detect_text",
  "name": "OCR Detect Text",
  "description": "Detects text from image.",
  "input_schema": { "type": "object", "properties": { "image": { "type": "string" } } },
  "output_schema": { "type": "object", "properties": { "text": { "type": "string" } } }
}
```

**MCP 侧期望（HTTP）**
- `GET /tools`
  - 返回数组，字段与上面一致或可被映射

> 如果 MCP 现有字段不同，可在 Core 做字段转换映射。

## 3. tool.invoke 映射
Core 收到：
```json
{
  "session_id": "sess_123",
  "tool_id": "ocr.detect_text",
  "input": { "image": "base64..." }
}
```

Core 转发为 HTTP：
```
POST /tools/ocr.detect_text
Content-Type: application/json
{
  "session_id": "sess_123",
  "input": { "image": "base64..." }
}
```

MCP 返回：
```json
{ "output": { "text": "hello" } }
```

Core 响应给 UI：
```json
{ "output": { "text": "hello" } }
```

## 4. 错误映射
Core 建议标准化错误码：
- MCP 4xx → Core JSON-RPC error.code = 1101 (Tool error)
- MCP 5xx/超时 → Core JSON-RPC error.code = 1201 (Core internal)

Core 需要保留 MCP 原始错误细节：
```json
{
  "code": 1101,
  "message": "Tool invoke failed",
  "data": { "status": 400, "detail": "invalid input" }
}
```

## 5. 超时与重试建议
- 超时：3~8 秒（根据工具类型设不同阈值）
- 重试：幂等工具允许 1~2 次重试
- 限流：同一 session 的并发调用建议 <= 4

## 6. MCP 服务发现
建议在 Core 中支持以下配置：
- `MCP_BASE_URL`（例如 `http://127.0.0.1:7001`）
- `MCP_TIMEOUT_MS`
- `MCP_RETRY_COUNT`

## 7. 版本与兼容性
- MCP / Core 之间通过 `GET /health` 或 `GET /version` 探测
- 建议 MCP 返回 `api_version`，Core 校验最低版本

