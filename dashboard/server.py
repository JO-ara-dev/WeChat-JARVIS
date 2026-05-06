"""
贾维斯 Web 仪表盘 - FastAPI 后端
提供：
  GET  /api/skills    → Skills/manifest.json
  GET  /api/agents    → agents.json + agent_config.json（合并）
  GET  /api/config    → agent_config.json（原始）
  WS   /ws/logs       → 实时日志流（打字机效果）
静态前端由 FastAPI StaticFiles 托管。
"""

import json
import asyncio
import logging
import threading
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
_CURRENT_DIR = Path(__file__).parent

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

logger = logging.getLogger("dashboard")

app = FastAPI(title="贾维斯仪表盘", version="1.0")

_ws_clients: list[WebSocket] = []


def _read_json(path: Path) -> dict:
    """安全读取 JSON 文件"""
    if not path.exists():
        return {"error": f"文件不存在: {path.name}"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"error": str(e)}


# ═══════════════════ REST API ═══════════════════

@app.get("/api/skills")
def api_skills():
    """返回 Skills 清单"""
    manifest_path = _PROJECT_ROOT / "Skills" / "manifest.json"
    return _read_json(manifest_path)


@app.get("/api/agents")
def api_agents():
    """
    返回合并后的 Agent 拓扑数据：
    - main_agent 来自 agent_config.json
    - sub_agents 来自 agents.json（整合 agent_config.json 的补充字段）
    """
    agents_path = _PROJECT_ROOT / "dorm_butler" / "agents.json"
    config_path = _PROJECT_ROOT / "dorm_butler" / "agent_config.json"

    agents_data = _read_json(agents_path)
    config_data = _read_json(config_path)

    result = {
        "main_agent": None,
        "sub_agents": [],
    }

    if "main_agent" in config_data:
        result["main_agent"] = {
            "name": config_data["main_agent"].get("name", "JARVIS大脑"),
            "description": config_data["main_agent"].get("description", ""),
            "model": config_data["main_agent"].get("model", ""),
            "provider": config_data["main_agent"].get("provider", ""),
            "sub_agent_count": len(agents_data.get("agents", [])),
        }

    if "agents" in agents_data:
        result["sub_agents"] = agents_data["agents"]

    return result


@app.get("/api/config")
def api_config():
    """返回 agent_config.json（子 Agent 的完整 system_prompt 太长，已截断）"""
    config_path = _PROJECT_ROOT / "dorm_butler" / "agent_config.json"
    data = _read_json(config_path)

    for sa in data.get("sub_agents", []):
        if "system_prompt" in sa and len(sa.get("system_prompt", "")) > 120:
            sa["system_prompt"] = sa["system_prompt"][:120] + "…"

    return data


# ═══════════════════ WebSocket 日志流 ═══════════════════

@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    await websocket.accept()
    print("[WS] 收到来自浏览器的新连接请求")

    from .log_bridge import get_recent_logs

    _ws_clients.append(websocket)
    logger.info(f"[WS] 客户端已连接 (当前 {len(_ws_clients)} 个)")

    try:
        for entry in get_recent_logs():
            await websocket.send_json(entry)

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.15)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"[WS] 异常: {e}")
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
        logger.info(f"[WS] 客户端已断开 (当前 {len(_ws_clients)} 个)")


# ═══════════════════ 集中广播循环 ═══════════════════

async def broadcast_loop():
    """集中广播日志条目到所有已连接客户端。
    使用 asyncio.gather + return_exceptions=True 确保
    单个客户端断开不会导致其他客户端的广播中断。
    """
    from .log_bridge import drain_buffer
    while True:
        entries = drain_buffer()
        if entries and _ws_clients:
            for entry in entries:
                safe_entry = json.loads(json.dumps(entry, default=str))
                tasks = [ws.send_json(safe_entry) for ws in _ws_clients]
                await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0.1)


async def agent_status_loop():
    """每隔 5 秒广播一次 AgentManager 状态，激活前端渲染引擎"""
    from datetime import datetime
    while True:
        await asyncio.sleep(5)
        if not _ws_clients:
            continue
        try:
            from dorm_butler.agent_manager import AgentManager
            config_path = _PROJECT_ROOT / "dorm_butler" / "agent_config.json"
            mgr = AgentManager(str(config_path))
            status = {
                "type": "agent_status",
                "main_agent": mgr.get_main_agent(),
                "sub_agents": mgr.list_agents(),
                "agent_count": len(mgr.list_agents()),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }
            safe_status = json.loads(json.dumps(status, default=str))
            tasks = [ws.send_json(safe_status) for ws in _ws_clients]
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            pass


@app.on_event("startup")
async def startup():
    asyncio.create_task(broadcast_loop())
    asyncio.create_task(agent_status_loop())


# ═══════════════════ 静态文件托管 ═══════════════════

static_dir = (_PROJECT_ROOT / "dashboard" / "static").resolve()
if static_dir.exists():
    @app.get("/")
    async def serve_dashboard():
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": "仪表盘就绪，请访问 /static/index.html"}

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ═══════════════════ 启动 ═══════════════════

def start_dashboard(host="127.0.0.1", port=9021):
    """
    在后台线程启动 uvicorn 服务。
    调用时机: butler_agent._init_modules()
    """
    import uvicorn

    from .log_bridge import install as install_log_bridge
    install_log_bridge()

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    logger.info(f"[仪表盘] 启动于 http://{host}:{port}")
    server.run()


def run_in_thread(host="127.0.0.1", port=9021):
    """在 daemon 线程中启动仪表盘"""
    t = threading.Thread(
        target=start_dashboard,
        args=(host, port),
        daemon=True,
        name="dashboard-server",
    )
    t.start()
    return t
