# 内网穿透 - 源码引用

## dorm_butler/tools.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `_is_port_open()` | 660-667 | 检测端口是否已监听 |
| `_get_ngrok_tunnels()` | 670-678 | 通过 ngrok 本地 API 获取隧道 |
| `_inject_mobile_viewport()` | 681-696 | 给 HTML 注入 viewport meta |
| `_get_project_dir()` | 699-700 | 获取项目根目录 |
| `expose()` | 703-793 | 主函数：启动 http.server + ngrok → 返回公网 URL |

### 调用链

```
expose(user_id, port=8765, file_path? / content?, mobile_fix=True)
  ↓
1. 确定目标文件（file_path 或 content 生成临时文件）
2. mobile_fix=true → _inject_mobile_viewport() 添加适配
3. _is_port_open(port) → 未监听则 Popen http.server
4. _get_ngrok_tunnels() → 无则 Popen ngrok
5. 轮询最多 20 次（10s）等待隧道就绪
6. 拼接 public_url + rel_path → 返回
```

### 外部依赖

- `ngrok` 需安装并加入系统 PATH
- 端口默认 8765
- http.server 以子进程后台运行

### 工具 Schema

`tools.py:1135-1151` — `expose` 的 OpenAPI function calling 格式。
