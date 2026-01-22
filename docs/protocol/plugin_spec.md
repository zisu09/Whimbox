# 插件规范（草案）

Whimbox 插件以“工具集合”的形式提供能力，Core 负责统一调度与执行。

## 1. 目录结构
```
plugins/
  my_plugin/
    plugin.json
    main.py
    tools/
      example_tool.py
    assets/
      ...
```

## 2. plugin.json 字段
```json
{
  "id": "my_plugin",
  "name": "示例插件",
  "version": "0.1.0",
  "author": "someone",
  "description": "插件描述",
  "entry": "main.py:register",
  "api_version": "1.0",
  "min_core_version": "0.0.0",
  "permissions": ["screen", "input"],
  "tools": [
    {
      "id": "demo.hello",
      "name": "Hello Tool",
      "description": "Say hello",
      "input_schema": {
        "type": "object",
        "properties": { "name": { "type": "string" } },
        "required": ["name"]
      },
      "output_schema": {
        "type": "object",
        "properties": { "message": { "type": "string" } }
      }
    }
  ]
}
```

## 3. 自动注册入口
插件入口只需要提供模块文件，Core 会从模块中读取 `TOOL_FUNCS` 自动注册。

`main.py` 需要提供：
```python
def hello(session_id: str, input: dict, context: dict) -> dict:
    ...

TOOL_FUNCS = {
    "demo.hello": hello
}
```

`plugin.json` 的 `entry` 只需填写文件名：
```json
{ "entry": "main.py" }
```

## 4. 调用约定
- Core 统一维护 `tool.list` / `tool.invoke`
- 工具函数签名建议为：
```python
def tool_func(session_id: str, input: dict, context: dict) -> dict:
    ...
```

## 5. 权限建议
可选权限：`screen` / `input` / `net` / `filesystem`

Core 可在首次调用时提示用户授权，或在配置中预授权。

