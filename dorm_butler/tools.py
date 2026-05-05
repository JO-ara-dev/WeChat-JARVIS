"""
牛马管家工具集 - 供 DeepSeek Agent 调用
每个函数返回 dict: {"success": bool, "data": ..., "message": str}
"""

import os
import sys
import json
import re
import time
import socket
import logging
import datetime
import urllib.request
from . import db_manager

logger = logging.getLogger("WCF")


# ─── 任务规划与 TODO 跟踪 ───

_agent_todos: dict[str, list[dict]] = {}  # user_id -> [{id, content, status, priority}]
_todo_counter: dict[str, int] = {}  # user_id -> next_id


def plan_task(user_id: str, task_description: str) -> dict:
    """
    任务规划：将复杂任务分解为步骤列表。
    在开始执行复杂任务前调用，生成执行计划。
    """
    steps = task_description.split("\n")
    steps = [s.strip() for s in steps if s.strip()]
    
    if user_id not in _todo_counter:
        _todo_counter[user_id] = 0
    if user_id not in _agent_todos:
        _agent_todos[user_id] = []
    
    plan = []
    for step in steps:
        _todo_counter[user_id] += 1
        plan.append({
            "id": _todo_counter[user_id],
            "content": step,
            "status": "pending",
            "priority": "medium"
        })
    
    _agent_todos[user_id] = plan
    return {
        "success": True,
        "data": {"steps": plan, "total": len(plan)},
        "message": f"已规划 {len(plan)} 个步骤"
    }


def update_todo(user_id: str, step_id: int, status: str) -> dict:
    """更新任务步骤状态：pending / in_progress / completed / cancelled"""
    if user_id not in _agent_todos:
        return {"success": False, "message": "没有待办列表"}
    
    for todo in _agent_todos[user_id]:
        if todo["id"] == step_id:
            todo["status"] = status
            return {"success": True, "data": _agent_todos[user_id], "message": f"步骤 {step_id} → {status}"}
    
    return {"success": False, "message": f"未找到步骤 {step_id}"}


def get_todos(user_id: str) -> dict:
    """获取当前任务列表"""
    if user_id not in _agent_todos or not _agent_todos[user_id]:
        return {"success": True, "data": [], "message": "没有待办任务"}
    
    pending = [t for t in _agent_todos[user_id] if t["status"] != "completed"]
    completed = [t for t in _agent_todos[user_id] if t["status"] == "completed"]
    return {
        "success": True,
        "data": {"pending": pending, "completed": completed},
        "message": f"待完成: {len(pending)}, 已完成: {len(completed)}"
    }


def reflect(user_id: str, summary: str) -> dict:
    """
    反射总结：任务完成后总结学到了什么。
    调用 save_memory 持久化经验。
    """
    todos = _agent_todos.get(user_id, [])
    completed = sum(1 for t in todos if t["status"] == "completed")
    failed = sum(1 for t in todos if t["status"] == "cancelled")
    
    # 清理
    _agent_todos.pop(user_id, None)
    _todo_counter.pop(user_id, None)
    
    return {
        "success": True,
        "data": {"completed": completed, "failed": failed, "summary": summary},
        "message": f"任务总结：完成 {completed} 步，失败 {failed} 步。{summary}"
    }


# ─── Harness 自进化 Pipeline：Self-Heal → Evolve → Reuse ───

def self_heal(user_id: str, error_context: str) -> dict:
    """自愈：执行失败后，自动分析错误原因并尝试修复。"""
    import re as _re
    fixes = []
    error_lower = error_context.lower()
    
    if "module not found" in error_lower or "modulenotfounderror" in error_lower:
        match = _re.search(r"named ['\"]([^'\"]+)['\"]", error_context)
        module_name = match.group(1) if match else "unknown"
        fixes.append(f"pip install {module_name}")
    if "permission denied" in error_lower or "access denied" in error_lower:
        fixes.append("try running as administrator")
    if "timeout" in error_lower or "timed out" in error_lower:
        fixes.append("increase timeout or check network")
    if "connection refused" in error_lower:
        fixes.append("check if target service is running / port is correct")
    if not fixes:
        fixes.append("analyze the exact error message and search for solutions")
    
    return {
        "success": True,
        "data": {"error": error_context, "fixes": fixes},
        "message": f"found {len(fixes)} possible fixes"
    }


def evolve_pipeline(user_id: str, task_type: str, solution: str, tools_used: str = "[]") -> dict:
    """进化：成功的任务方案注册为可复用 Pipeline。tools_used 是 JSON 数组字符串。"""
    pipeline_key = f"pipeline_{task_type}"
    pipeline_data = json.dumps({
        "solution": solution,
        "tools_used": json.loads(tools_used) if tools_used else [],
        "created_at": datetime.datetime.now().isoformat()
    }, ensure_ascii=False)
    db_manager.set_config(pipeline_key, pipeline_data)
    return {
        "success": True,
        "data": {"pipeline_key": pipeline_key},
        "message": f"Pipeline registered: {task_type}"
    }


def reuse_pipeline(user_id: str, task_type: str) -> dict:
    """复用：查找之前注册的 Pipeline。"""
    pipeline_key = f"pipeline_{task_type}"
    pipeline_data = db_manager.get_config(pipeline_key)
    if not pipeline_data:
        return {"success": False, "message": f"no pipeline for {task_type}"}
    try:
        data = json.loads(pipeline_data)
        return {"success": True, "data": data, "message": f"found: {data['solution'][:100]}"}
    except json.JSONDecodeError:
        return {"success": False, "message": "pipeline data corrupted"}


# ─── 自我更新（需确认 + 备份 + 最高模型）───

def self_update(user_id: str, file_path: str, old_code: str, new_code: str, reason: str, confirmed: bool = False) -> dict:
    """
    更新自身源代码。安全措施：
    1. 必须用户确认
    2. 自动备份
    3. 建议用 deep 模式思考
    """
    import os as _os
    import shutil
    from datetime import datetime as _dt
    
    base_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    full_path = _os.path.abspath(_os.path.join(base_dir, file_path))
    
    # 安全目录限制
    allowed_dirs = [
        _os.path.join(base_dir, "dorm_butler"),
        base_dir,
    ]
    if not any(full_path.startswith(d) for d in allowed_dirs):
        return {"success": False, "message": f"安全限制：只能更新 dorm_butler/ 和根目录代码"}
    
    if not full_path.endswith(".py"):
        return {"success": False, "message": "只能更新 .py 源文件"}
    
    if not confirmed:
        # 创建备份预览
        backup_dir = _os.path.join(base_dir, "backups")
        _os.makedirs(backup_dir, exist_ok=True)
        timestamp = _dt.now().strftime("%Y%m%d_%H%M%S")
        backup_path = _os.path.join(backup_dir, f"{_os.path.basename(file_path)}.{timestamp}.bak")
        
        try:
            shutil.copy2(full_path, backup_path)
        except Exception:
            pass
        
        return {
            "success": True,
            "data": {
                "need_confirm": True,
                "file": file_path,
                "reason": reason,
                "backup": backup_path,
                "old_preview": old_code[:120],
                "new_preview": new_code[:120]
            },
            "message": (
                f"🔧 代码更新申请\n"
                f"文件：{file_path}\n"
                f"原因：{reason}\n"
                f"备份：{backup_path}\n\n"
                f"旧代码：\n{old_code[:200]}\n\n"
                f"新代码：\n{new_code[:200]}\n\n"
                f"请回复「确认更新」来应用，回复「取消」放弃。"
            )
        }
    
    # 确认后执行
    try:
        backup_dir = _os.path.join(base_dir, "backups")
        _os.makedirs(backup_dir, exist_ok=True)
        timestamp = _dt.now().strftime("%Y%m%d_%H%M%S")
        backup_path = _os.path.join(backup_dir, f"{_os.path.basename(file_path)}.{timestamp}.bak")
        shutil.copy2(full_path, backup_path)
        
        # 读取完整文件
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        if old_code not in content:
            return {"success": False, "message": "old_code not found in file, file may have changed"}
        
        new_content = content.replace(old_code, new_code, 1)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        return {
            "success": True,
            "data": {"file": file_path, "backup": backup_path},
            "message": (
                f"已更新 {file_path}，备份在 {backup_path}\n"
                f"⚠️ 请立即调用 run_cmd 执行语法检查：python -m py_compile {file_path}\n"
                f"并执行导入检查：python -c \"from dorm_butler import <模块名>\""
            )
        }
    except Exception as e:
        return {"success": False, "message": f"更新失败: {str(e)}"}


WEEKDAY_NAMES = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def get_current_week() -> int:
    """根据 semester_start 配置计算当前是第几周
    semester_start 所在的那一整周算第1周（从该周周一开始算）
    """
    start_str = db_manager.get_config("semester_start")
    if not start_str:
        return 0
    try:
        start_date = datetime.date.fromisoformat(start_str)
        # 找到 start_date 所在周的周一
        days_since_monday = start_date.weekday()  # 0=周一
        week_monday = start_date - datetime.timedelta(days=days_since_monday)
        
        today = datetime.date.today()
        delta = (today - week_monday).days
        if delta < 0:
            return 0
        return delta // 7 + 1
    except (ValueError, TypeError):
        return 0


def is_course_in_week(course: dict, week: int) -> bool:
    """检查课程是否在指定周次上课"""
    weeks_str = course.get("weeks", "1-16")
    if not weeks_str:
        return True
    try:
        for part in weeks_str.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                if int(start) <= week <= int(end):
                    return True
            else:
                if int(part) == week:
                    return True
    except (ValueError, TypeError):
        return True
    return False


def query_courses(weekday: int = None) -> dict:
    """查询课程，weekday 1-5，不传则查全部。自动过滤非当前周的课程。"""
    current_week = get_current_week()

    if weekday:
        courses = db_manager.get_courses_by_weekday(weekday)
        day_name = WEEKDAY_NAMES[weekday] if 1 <= weekday <= 7 else f"周{weekday}"
        if current_week > 0:
            courses = [c for c in courses if is_course_in_week(c, current_week)]
        if not courses:
            week_info = f"（第{current_week}周）" if current_week > 0 else ""
            return {"success": True, "data": [], "message": f"{day_name}{week_info}没有课"}
        courses.sort(key=lambda c: c.get("start_node", 0))
        week_info = f"（第{current_week}周）" if current_week > 0 else ""
        return {"success": True, "data": courses, "message": f"{day_name}{week_info}有 {len(courses)} 门课"}
    else:
        all_courses = db_manager.get_all_courses()
        if not all_courses:
            return {"success": True, "data": [], "message": "数据库里没有任何课程"}
        if current_week > 0:
            all_courses = [c for c in all_courses if is_course_in_week(c, current_week)]
        all_courses.sort(key=lambda c: (c.get("week_day", 9), c.get("start_node", 0)))
        week_info = f"（第{current_week}周）" if current_week > 0 else ""
        return {"success": True, "data": all_courses, "message": f"共 {len(all_courses)} 门课{week_info}"}


def add_courses(courses: list) -> dict:
    """批量添加课程"""
    if not courses:
        return {"success": False, "data": None, "message": "没有课程数据"}
    added = 0
    for c in courses:
        try:
            db_manager.add_course(
                name=c.get("course_name", "未知课程"),
                week_day=int(c.get("week_day", 1)),
                start_node=int(c.get("start_node", 1)),
                end_node=int(c.get("end_node", 2)),
                location=c.get("location", ""),
                weeks=c.get("weeks", "1-16"),
            )
            added += 1
        except Exception:
            pass
    return {"success": True, "data": {"added": added}, "message": f"成功添加 {added} 门课程"}


def delete_courses(weekday: int = None) -> dict:
    """删除课程"""
    if weekday:
        courses = db_manager.get_courses_by_weekday(weekday)
        count = 0
        for c in courses:
            if db_manager.delete_course(c["id"]):
                count += 1
        day_name = WEEKDAY_NAMES[weekday] if 1 <= weekday <= 7 else f"周{weekday}"
        return {"success": True, "data": {"deleted": count}, "message": f"删除了 {day_name} 的 {count} 门课"}
    else:
        count = db_manager.clear_all_courses()
        return {"success": True, "data": {"deleted": count}, "message": f"清空了全部 {count} 条课程"}


def query_tasks(user_id: str = "") -> dict:
    """查询待完成作业。传入 user_id 时按 scope 隔离：只返回自己的(private) + 全局的(public)"""
    from . import db_manager
    tasks = db_manager.get_pending_tasks(user_id=user_id if user_id else None)
    if not tasks:
        return {"success": True, "data": [], "message": "没有待完成的作业"}
    return {"success": True, "data": tasks, "message": f"共 {len(tasks)} 条待办"}


def add_task(user_id: str = "", content: str = "", ddl: str = None, scope: str = "private") -> dict:
    """添加作业任务"""
    from . import db_manager
    # 获取当前用户昵称
    user = db_manager.get_user_by_id(user_id) if user_id else None
    creator_nickname = user.get("nickname", user_id) if user else user_id
    task_id = db_manager.add_task(
        content=content, ddl=ddl,
        creator_id=user_id, creator_nickname=creator_nickname, scope=scope,
    )
    scope_label = "🌍 全局" if scope == "public" else "👤 个人"
    return {"success": True, "data": {"task_id": task_id, "scope": scope, "creator_nickname": creator_nickname},
            "message": f"已添加{scope_label}任务: {content}"}


def delete_task(user_id: str = "", task_id: int = 0) -> dict:
    """删除指定任务。传入 user_id 时检查所有权（只能删自己的或 public 的）"""
    from . import db_manager
    if db_manager.delete_task(task_id, user_id=user_id if user_id else None):
        return {"success": True, "data": None, "message": f"已删除任务 ID={task_id}"}
    return {"success": False, "data": None, "message": f"任务 ID={task_id} 不存在或无权删除"}


# ─── 用户昵称与识别 ───

def set_nickname(user_id: str, nickname: str) -> dict:
    """设置当前用户的昵称"""
    from . import db_manager
    db_manager.register_user(user_id, nickname)
    if db_manager.set_nickname(user_id, nickname):
        return {"success": True, "data": {"user_id": user_id, "nickname": nickname},
                "message": f"昵称已设为「{nickname}」"}
    return {"success": False, "message": f"设置昵称失败，可能是昵称重复"}


def resolve_user(identifier: str) -> dict:
    """通过昵称或用户ID查找用户信息"""
    from . import db_manager
    user = db_manager.get_user_by_nickname(identifier)
    if not user:
        user = db_manager.get_user_by_id(identifier)
    if not user:
        users = db_manager.search_users_by_nickname(identifier)
        if users:
            return {"success": True, "data": users, "message": f"找到 {len(users)} 个匹配用户"}
        return {"success": False, "data": None, "message": f"未找到用户: {identifier}"}
    return {"success": True, "data": user, "message": f"找到用户: {user.get('nickname', user.get('user_id'))}"}


def identify_me(user_id: str, nickname: str) -> dict:
    """用户声明自己的身份：「我是XX」「我叫XX」"""
    from . import db_manager
    db_manager.register_user(user_id, nickname)
    return {"success": True, "data": {"user_id": user_id, "nickname": nickname},
            "message": f"记住了！你是「{nickname}」👋"}


def web_search(query: str) -> dict:
    """联网搜索"""
    import urllib.request
    import urllib.parse
    
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.bing.com/search?q={encoded_query}&mkt=zh-CN"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        
        # 简单提取搜索结果片段
        import re
        
        # 提取文本内容并去重
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text)
        # 截取前2000字符作为摘要
        text = text[:2000]
        
        return {"success": True, "data": {"query": query, "snippet": text}, "message": f"搜索完成: {query}"}
    except Exception as e:
        return {"success": False, "data": None, "message": f"搜索失败: {str(e)}"}


def read_file(file_path: str, limit: int = None, offset: int = 0) -> dict:
    """
    读取文件内容。支持分段读取大文件。
    limit: 最多读取行数，不传则读全部
    offset: 起始行号（从0开始），不传默认第0行
    """
    import os
    
    # 安全限制：只允许读取项目目录下的文件
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.abspath(os.path.join(base_dir, file_path))
    
    if not full_path.startswith(base_dir):
        return {"success": False, "data": None, "message": "安全限制：只能读取项目目录下的文件"}
    
    try:
        if not os.path.exists(full_path):
            return {"success": False, "data": None, "message": f"文件不存在: {file_path}"}
        
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        
        # 应用 offset 和 limit
        start = max(0, offset)
        end = start + limit if limit is not None else total_lines
        end = min(end, total_lines)
        
        selected = lines[start:end]
        content = "".join(selected)
        
        return {
            "success": True,
            "data": {
                "path": file_path,
                "content": content,
                "total_lines": total_lines,
                "returned_lines": len(selected),
                "offset": start,
                "limit": limit,
            },
            "message": f"读取成功: 第{start+1}-{end}行 / 共{total_lines}行"
        }
    except Exception as e:
        return {"success": False, "data": None, "message": f"读取失败: {str(e)}"}


def write_file(file_path: str, content: str) -> dict:
    """写入文件内容"""
    import os
    
    # 安全限制：只允许写入项目目录下的文件
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.abspath(os.path.join(base_dir, file_path))
    
    if not full_path.startswith(base_dir):
        return {"success": False, "data": None, "message": "安全限制：只能写入项目目录下的文件"}
    
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return {"success": True, "data": {"path": file_path}, "message": f"写入成功: {file_path}"}
    except Exception as e:
        return {"success": False, "data": None, "message": f"写入失败: {str(e)}"}


def list_files(dir_path: str = ".") -> dict:
    """列出目录下的文件"""
    import os
    
    # 安全限制：只允许列出项目目录下的文件
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.abspath(os.path.join(base_dir, dir_path))
    
    if not full_path.startswith(base_dir):
        return {"success": False, "data": None, "message": "安全限制：只能列出项目目录下的文件"}
    
    try:
        if not os.path.exists(full_path):
            return {"success": False, "data": None, "message": f"目录不存在: {dir_path}"}
        
        items = []
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            is_dir = os.path.isdir(item_path)
            size = os.path.getsize(item_path) if not is_dir else 0
            items.append({
                "name": item,
                "type": "directory" if is_dir else "file",
                "size": size
            })
        
        return {"success": True, "data": {"path": dir_path, "items": items}, "message": f"列出成功: {dir_path}"}
    except Exception as e:
        return {"success": False, "data": None, "message": f"列出失败: {str(e)}"}


def create_tool(tool_name: str, tool_code: str, tool_description: str) -> dict:
    """创建新工具"""
    import os
    
    # 安全限制
    forbidden = ["import subprocess", "import os.system", "exec(", "eval(", "__import__"]
    for f in forbidden:
        if f in tool_code:
            return {"success": False, "message": f"安全限制：禁止 {f}"}
    
    try:
        # 动态创建工具函数
        exec(tool_code, globals())
        
        # 将工具添加到 TOOLS_MAP
        if tool_name in globals():
            TOOLS_MAP[tool_name] = globals()[tool_name]
            return {"success": True, "message": f"工具创建成功: {tool_name}"}
        else:
            return {"success": False, "message": f"工具函数未定义: {tool_name}"}
    except Exception as e:
        return {"success": False, "message": f"创建失败: {str(e)}"}


# ─── cmd 执行确认队列 ───
_pending_cmds: dict[str, dict] = {}  # user_id -> {"cmd": str, "description": str}


def run_cmd(user_id: str, command: str, description: str, confirmed: bool = False, background: bool = False) -> dict:
    """
    执行系统命令。需要用户确认后才能执行。
    
    background=True: 后台运行（用于 http.server 等持续服务），不阻塞
    用法：
    - 第一次调用传 confirmed=False，返回确认请求
    - 用户回复「确认」后，再次调用传 confirmed=True 执行
    """
    import subprocess
    import os
    
    # 危险命令黑名单
    dangerous = ["format", "del /f", "rm -rf", "shutdown", "reboot", "diskpart", "fdisk"]
    for keyword in dangerous:
        if keyword.lower() in command.lower():
            return {"success": False, "message": f"安全限制：禁止危险命令 ({keyword})"}
    
    # 自动修正 pip 路径：确保 pip install 安装到当前 Python 环境
    cmd_stripped = command.strip()
    if cmd_stripped.startswith("pip ") or cmd_stripped.startswith("pip3 "):
        parts = cmd_stripped.split(None, 1)
        args = parts[1] if len(parts) > 1 else ""
        command = f'"{sys.executable}" -m pip {args}'
        logger.info(f"自动修正 pip→同环境: {command[:100]}")
    
    if not confirmed:
        _pending_cmds[user_id] = {"cmd": command, "description": description}
        return {
            "success": True, 
            "data": {"need_confirm": True, "command": command, "description": description},
            "message": f"确认执行？\n命令：{command}\n说明：{description}\n\n请回复「确认」来执行，回复「取消」放弃。"
        }
    
    # 确认后执行
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    try:
        if background:
            # 后台模式：用 Popen，不等待
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=project_dir,
            )
            _pending_cmds.pop(user_id, None)
            return {
                "success": True,
                "data": {"pid": proc.pid, "background": True},
                "message": f"后台进程已启动 (PID: {proc.pid})"
            }
        
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=30,  # 非后台命令30秒超时
            cwd=project_dir,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if not output.strip():
            output = f"(OK, returncode={result.returncode})"
        
        _pending_cmds.pop(user_id, None)
        return {"success": True, "data": {"output": output, "returncode": result.returncode}, "message": "命令执行完成"}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "命令超时(30s)，如果是持续运行的服务请用 background=True"}
    except Exception as e:
        return {"success": False, "message": f"执行失败: {str(e)}"}


def think(question: str, mode: str = "auto") -> dict:
    """
    深度思考工具 - 根据任务难度选择模型
    
    mode:
    - "fast": 快速模式，使用 deepseek-v4-flash（简单问题）
    - "deep": 深度模式，使用 deepseek-v4-pro（复杂问题）
    - "auto": 自动模式，根据问题复杂度自动选择
    """
    import os
    from openai import OpenAI
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    # 自动判断模式
    if mode == "auto":
        # 简单的复杂度判断
        complex_keywords = ["分析", "设计", "优化", "算法", "架构", "证明", "推导", "比较", "评估", "为什么", "原理", "策略"]
        simple_keywords = ["查询", "什么是", "几点", "天气", "今天", "明天", "多少"]
        
        has_complex = any(kw in question for kw in complex_keywords)
        has_simple = any(kw in question for kw in simple_keywords)
        
        if has_complex and not has_simple:
            mode = "deep"
        else:
            mode = "fast"
    
    try:
        if mode == "deep":
            # 深度模式：使用 pro 模型，不设 timeout 让深度思考自然完成
            response = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[{"role": "user", "content": question}],
                max_tokens=8000,
            )
            msg = response.choices[0].message
            answer = msg.content or getattr(msg, "reasoning_content", None) or ""
            return {
                "success": True,
                "data": {
                    "answer": answer,
                    "model": "deepseek-v4-pro",
                    "mode": "deep"
                },
                "message": f"[深度思考] {answer[:100] if answer else '(思考完成但无内容)'}..."
            }
        else:
            # 快速模式：使用 flash 模型
            response = client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=[{"role": "user", "content": question}],
                max_tokens=2000,
                temperature=0.3,
            )
            msg = response.choices[0].message
            answer = msg.content or getattr(msg, "reasoning_content", None) or ""
            return {
                "success": True,
                "data": {
                    "answer": answer,
                    "model": "deepseek-v4-flash",
                    "mode": "fast"
                },
                "message": f"[快速回答] {answer[:100]}..."
            }
    except Exception as e:
        return {"success": False, "data": None, "message": f"思考失败: {str(e)}"}


# ─── 内网穿透：一键暴露内容到公网 ───

def _is_port_open(port: int) -> bool:
    """检测端口是否已被监听"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        return s.connect_ex(('127.0.0.1', port)) == 0
    finally:
        s.close()


def _get_tunnel_info() -> list:
    """通过隧道工具本地 API 获取当前隧道列表（ngrok 兼容格式）"""
    try:
        req = urllib.request.Request('http://127.0.0.1:4040/api/tunnels')
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return data.get('tunnels', [])
    except Exception:
        return []


def _inject_mobile_viewport(html_content: str) -> tuple:
    """给 HTML 注入移动端 viewport meta（如果没有的话）。返回 (content, injected)"""
    if '<meta name="viewport"' in html_content.lower():
        return html_content, False

    head_match = re.search(r'<head[^>]*>', html_content, re.IGNORECASE)
    if head_match:
        insert_pos = html_content.index(head_match.group()) + len(head_match.group())
        inject = '\n    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">'
        return html_content[:insert_pos] + inject + html_content[insert_pos:], True

    body_pos = html_content.lower().find('<body')
    if body_pos == -1:
        body_pos = 0
    inject = '<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">\n'
    return html_content[:body_pos] + inject + html_content[body_pos:], True


def _get_project_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find_tunnel_provider() -> str:
    """探测可用的内网穿透工具，返回 'cpolar' 或 'ngrok' 或 None"""
    import shutil

    provider = os.getenv("TUNNEL_PROVIDER", "auto").strip().lower()

    if provider == "cpolar":
        if shutil.which("cpolar"):
            return "cpolar"
        return None
    if provider == "ngrok":
        if shutil.which("ngrok"):
            return "ngrok"
        return None

    # auto 模式：cpolar 优先（国内稳定）
    if shutil.which("cpolar"):
        return "cpolar"
    if shutil.which("ngrok"):
        return "ngrok"
    return None


def _start_cpolar_tunnel(port: int, timeout: int = 30) -> str:
    """启动 cpolar 隧道，监控日志提取公网 URL。返回 URL 或 None"""
    import subprocess as _sp
    import tempfile
    import glob

    log_base = os.path.join(tempfile.gettempdir(), f'_cpolar_{port}')
    logger.info(f"[cpolar] 启动隧道，端口 {port}（日志: {log_base}.log）...")

    _sp.Popen(
        ['cpolar', 'http', str(port), '--log=' + log_base.replace('\\', '/') + '.log', '--log-level=info'],
        stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
        creationflags=0x08000000,
    )

    start_time = time.time()
    while time.time() - start_time < timeout:
        # cpolar 会在文件名后追加日期后缀（如 .log.20260505），用 glob 匹配
        for log_path in glob.glob(log_base + '.log*'):
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        match = re.search(r'Tunnel established at (https?://[^\s"]+)', line)
                        if match:
                            return match.group(1)
            except Exception:
                pass
        time.sleep(0.5)

    return None


def _start_ngrok_tunnel(port: int, timeout: int = 30) -> str:
    """启动 ngrok 隧道，通过本地 API 轮询获取公网 URL。返回 URL 或 None"""
    import subprocess as _sp

    for t in _get_tunnel_info():
        if str(port) in t.get('config', {}).get('addr', ''):
            return t.get('public_url', '')

    logger.info(f"[ngrok] 启动隧道，端口 {port}...")
    _sp.Popen(
        ['ngrok', 'http', str(port), '--log=stdout'],
        stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
        creationflags=0x08000000,
    )

    for _ in range(timeout):
        time.sleep(1)
        for t in _get_tunnel_info():
            if str(port) in t.get('config', {}).get('addr', ''):
                return t.get('public_url', '')

    return None


def expose(user_id: str, port: int = 8765, file_path: str = None, content: str = None, mobile_fix: bool = True) -> dict:
    """
    一键暴露内容到公网：启动 http.server + 内网穿透隧道，返回公网 URL。
    优先 cpolar（国内稳定），降级 ngrok。
    调用后直接回复返回的链接给用户即可。

    参数：
    - port: 本地端口（默认 8765）
    - file_path: 项目内的文件路径，如 "example.html"
    - content: 动态 HTML 内容字符串（与 file_path 二选一）
    - mobile_fix: 是否自动给 HTML 添加手机端适配（默认 true）
    """
    import subprocess as _sp

    project_dir = _get_project_dir()

    # 1. 确定目标文件
    injected_msg = ""
    if content:
        if mobile_fix:
            content, injected = _inject_mobile_viewport(content)
            injected_msg = "（已自动添加移动端适配）" if injected else ""
        tmp_path = os.path.join(project_dir, "data", "_exposed.html")
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        target_path = tmp_path
    elif file_path:
        target_path = os.path.abspath(os.path.join(project_dir, file_path))
        if not target_path.startswith(project_dir):
            return {"success": False, "message": "安全限制：只能暴露项目目录下的文件"}
        if not os.path.exists(target_path):
            return {"success": False, "message": f"文件不存在: {file_path}"}
        if mobile_fix and target_path.endswith('.html'):
            with open(target_path, 'r', encoding='utf-8') as f:
                raw = f.read()
            fixed, injected = _inject_mobile_viewport(raw)
            if injected:
                tmp_path = os.path.join(project_dir, "data", "_exposed_mobile.html")
                os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    f.write(fixed)
                target_path = tmp_path
                injected_msg = "（已自动添加移动端适配）"
    else:
        return {"success": False, "message": "请指定 file_path 或 content"}

    # 2. 如果端口未监听，启动 http.server
    if not _is_port_open(port):
        logger.info(f"端口 {port} 未监听，启动 http.server...")
        http_cmd = f'"{sys.executable}" -m http.server {port} --directory "{project_dir}"'
        _sp.Popen(
            http_cmd, shell=True,
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
            cwd=project_dir,
            creationflags=0x08000000,
        )
        time.sleep(1.5)
        if not _is_port_open(port):
            return {"success": False, "message": f"http.server 启动失败，端口 {port} 未就绪"}

    # 3. 探测可用隧道工具
    provider = _find_tunnel_provider()
    if not provider:
        return {
            "success": False,
            "message": "未找到内网穿透工具。请安装 cpolar（https://cpolar.com，国内稳定）"
                       "或 ngrok（https://ngrok.com），确保已加入 PATH 并配置 auth token"
        }

    # 4. 启动隧道获取公网 URL
    public_url = None
    if provider == "cpolar":
        public_url = _start_cpolar_tunnel(port)
    elif provider == "ngrok":
        public_url = _start_ngrok_tunnel(port)

    if not public_url:
        return {"success": False, "message": f"{provider} 隧道连接超时（30s），请检查网络或稍后重试"}

    rel_path = os.path.relpath(target_path, project_dir).replace('\\', '/')
    full_url = f"{public_url}/{rel_path}"

    return {
        "success": True,
        "data": {"public_url": full_url},
        "message": f"{injected_msg}\n🔗 公网链接：{full_url}"
    }


# ─── 技能管理：生成方案 + 注册技能 ───

def propose_skill(user_id: str, intent_description: str, user_message: str = "") -> dict:
    """
    生成新技能的 SKILL.md 方案草案。
    AI 调用此工具后，会得到一份技能设计文档，需要展示给用户审阅。
    用户确认后，再调用 register_skill 正式注册。
    """
    from openai import OpenAI

    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)

    from .skill_manager import generate_skill_proposal

    skill_md = generate_skill_proposal(intent_description, user_message, client)

    if not skill_md:
        return {"success": False, "message": "技能方案生成失败，请重试"}

    return {
        "success": True,
        "data": {
            "stage": "proposal",
            "skill_md_preview": skill_md[:500],
            "skill_md_full": skill_md,
        },
        "message": (
            "📋 技能方案已生成，请老大审阅以下内容：\n\n"
            f"{skill_md}\n\n"
            "如果满意，请回复「确认注册」或「注册技能」来正式创建此技能。\n"
            "如需修改，请说明修改意见。"
        ),
    }


def register_skill(user_id: str, name: str, skill_md_content: str, confirmed: bool = False) -> dict:
    """
    正式注册新技能：创建技能目录、写入 SKILL.md、更新 manifest.json 和 README.md。
    必须在用户确认后才能执行（confirmed=True）。
    """
    from .skill_manager import register_skill as _register

    if not confirmed:
        return {
            "success": True,
            "data": {"stage": "confirm", "name": name},
            "message": (
                f"即将注册技能「{name}」，请确认：\n"
                "回复「确认注册」来执行，回复「取消」放弃。"
            ),
        }

    result = _register(name, skill_md_content)
    return result


# ─── 多 Agent 协作：任务分发 ───

import threading as _threading

# 线程安全：异步结果池 + 并发控制
_result_lock = _threading.Lock()
_pending_sub_results: dict[str, dict] = {}
_sub_semaphore = _threading.Semaphore(6)


def _run_sub_agent(user_id: str, agent_name: str, agent_config: dict, task_key: str,
                   task_description: str, context: str):
    """后台线程执行子Agent"""
    from .sub_agent import SubAgent
    sub = SubAgent(agent_name, agent_config, user_id)
    result = sub.execute(task_description, context)
    with _result_lock:
        _pending_sub_results[task_key] = result
    _sub_semaphore.release()


def delegate_task(user_id: str, agent_name: str, task_description: str,
                  context: str = "", progress_callback=None) -> dict:
    """
    主Agent将任务分发给子Agent独立执行（异步，不阻塞）。
    调用后立即返回状态，主Agent可继续对话。
    用 get_pending_result 获取执行结果。
    """
    from .sub_agent import load_agents

    agents = load_agents()
    agent_config = None
    for a in agents:
        if a["name"] == agent_name:
            agent_config = a
            break

    if not agent_config:
        available = [a["name"] for a in agents]
        return {"success": False, "message": f"未找到子Agent: {agent_name}，可用: {available}"}

    # 并发控制
    if not _sub_semaphore.acquire(blocking=False):
        return {"success": False, "message": f"所有 6 个Agent当前繁忙，请稍后重试"}

    # 通知用户
    tools_str = ", ".join(agent_config.get("tools", [])[:4])
    if progress_callback:
        progress_callback(
            f"已调用 {agent_name} Agent\n"
            f"擅长：{agent_config.get('description', '通用任务')}\n"
            f"工具：{tools_str}\n"
            f"正在执行任务...（可用 get_pending_result 查询结果）"
        )

    task_key = f"{user_id}:{agent_name}:{int(time.time())}"
    t = _threading.Thread(
        target=_run_sub_agent,
        args=(user_id, agent_name, agent_config, task_key, task_description, context),
        daemon=True,
    )
    t.start()

    return {
        "success": True,
        "data": {"agent": agent_name, "task_key": task_key, "status": "dispatched"},
        "message": f"已分派 [{agent_name}]，后台执行中。"
    }


def get_pending_result(user_id: str) -> dict:
    """
    检查当前用户是否有子Agent返回了结果。
    非阻塞：有结果就返回，没有就返回 pending 状态。
    """
    with _result_lock:
        for key, result in list(_pending_sub_results.items()):
            if key.startswith(user_id + ":"):
                del _pending_sub_results[key]
                # 提取 agent_name
                parts = key.split(":")
                agent_name = parts[1] if len(parts) > 1 else "unknown"
                return {
                    "success": True,
                    "data": {"agent": agent_name, "result": result},
                    "message": f"[{agent_name}] 执行完成，请审核结果并回复用户。"
                }
    return {"success": True, "data": None, "message": "暂无完成的子Agent结果"}


def swarm_execute(user_id: str, workflow_json: str = "", progress_callback=None) -> dict:
    """
    多Agent协作编排：并行派发多个Agent，等待全部完成后汇总。
    支持 Agent 间 REQUEST/RESULT 通信协议。

    workflow_json: JSON 字符串，格式:
    {
        "parallel": [
            {"task_id": "1", "agent": "web-designer", "task": "设计猫妖风格主页"},
            {"task_id": "2", "agent": "researcher", "task": "查猫妖背景资料"}
        ],
        "final": {"agent": "code-executor", "task": "汇总所有结果生成HTML"},
        "interop": true
    }
    """
    import json as _json
    from .agent_swarm import AgentSwarm, clear_all_messages

    try:
        workflow = _json.loads(workflow_json)
    except _json.JSONDecodeError:
        return {"success": False, "message": "workflow_json 格式错误"}

    clear_all_messages()
    swarm = AgentSwarm(user_id)

    # 注册并行任务
    for task in workflow.get("parallel", []):
        swarm.add_task(task["task_id"], task["agent"], task["task"])

    if progress_callback:
        progress_callback(f"Swarm 启动：{len(swarm.tasks)} 个Agent并行执行...")

    # 启动并行
    swarm.launch_parallel(progress_callback)

    # 汇总结果
    summary = []
    for tid, info in swarm.tasks.items():
        result = info.get("result", {})
        output = result.get("output", "") if result else ""
        summary.append(f"[{info['agent']}] {info['status']}: {output[:100]}")

    # 有 final 阶段
    final_output = ""
    if workflow.get("final"):
        from .sub_agent import load_agents, SubAgent
        agents_config = {a["name"]: a for a in load_agents()}
        final_cfg = agents_config.get(workflow["final"]["agent"])
        if final_cfg:
            context = "\n\n## 其他Agent的产出\n" + "\n".join(summary)
            sub = SubAgent(workflow["final"]["agent"], final_cfg, user_id)
            final_result = sub.execute(workflow["final"]["task"], context)
            final_output = final_result.get("output", "")

    return {
        "success": True,
        "data": {
            "summary": summary,
            "final_output": final_output[:1500],
        },
        "message": f"Swarm 完成：{len(swarm.tasks)} 个并行任务" + (", final已执行" if final_output else "")
    }


def list_agents(user_id: str = "") -> dict:
    """查看所有子Agent的当前状态（空闲/繁忙）"""
    from .sub_agent import get_agent_states, load_agents

    states = get_agent_states()
    busy = sum(1 for s in states.values() if s["status"] == "busy")
    idle = sum(1 for s in states.values() if s["status"] == "idle")

    return {
        "success": True,
        "data": states,
        "message": f"当前 {busy} 繁忙 / {idle} 空闲"
    }


# ── 工具定义（OpenAI function calling 格式）──

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "plan_task",
            "description": "任务规划：在执行复杂任务前，先分解为具体步骤。每行一个步骤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "task_description": {"type": "string", "description": "任务步骤，每行一个"}
                },
                "required": ["user_id", "task_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": "更新任务步骤状态。每完成一步就更新一次。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "step_id": {"type": "integer", "description": "步骤ID"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"], "description": "新状态"}
                },
                "required": ["user_id", "step_id", "status"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_todos",
            "description": "查看当前任务进度。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reflect",
            "description": "任务完成后总结反思，持久化经验教训。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "summary": {"type": "string", "description": "总结：完成了什么、学到了什么、有什么可以改进的"}
                },
                "required": ["user_id", "summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "self_heal",
            "description": "自愈：执行失败后自动分析错误原因并给出修复方案。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "error_context": {"type": "string", "description": "错误信息或上下文"}
                },
                "required": ["user_id", "error_context"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "evolve_pipeline",
            "description": "进化：将成功完成任务的经验注册为可复发 Pipeline。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "task_type": {"type": "string", "description": "任务类型关键词"},
                    "solution": {"type": "string", "description": "解决方案描述"},
                    "tools_used": {"type": "string", "description": "使用的工具列表 JSON 数组"}
                },
                "required": ["user_id", "task_type", "solution"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reuse_pipeline",
            "description": "复用：查找之前注册的 Pipeline 直接执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "task_type": {"type": "string", "description": "任务类型关键词"}
                },
                "required": ["user_id", "task_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "self_update",
            "description": "更新自身源代码。会自动备份，需用户确认后才执行。更新前建议用 think(deep) 深度思考。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "file_path": {"type": "string", "description": "要更新的源文件路径"},
                    "old_code": {"type": "string", "description": "要被替换的旧代码片段"},
                    "new_code": {"type": "string", "description": "替换的新代码片段"},
                    "reason": {"type": "string", "description": "更新原因说明"},
                    "confirmed": {"type": "boolean", "description": "是否已确认。首次 false，用户确认后 true"}
                },
                "required": ["user_id", "file_path", "old_code", "new_code", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_courses",
            "description": "查询课程表。不传参数查全部课程，传 weekday 查指定星期几的课程。自动根据学期起始日期过滤当前周的课程。",
            "parameters": {
                "type": "object",
                "properties": {
                    "weekday": {
                        "type": "integer",
                        "description": "星期几，1=周一 2=周二 3=周三 4=周四 5=周五。不传则查全部。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_courses",
            "description": "批量添加课程到数据库。用于从课表图片识别结果入库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "courses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "course_name": {"type": "string", "description": "课程名称"},
                                "week_day": {"type": "integer", "description": "星期几 1-5"},
                                "start_node": {"type": "integer", "description": "开始节次"},
                                "end_node": {"type": "integer", "description": "结束节次"},
                                "location": {"type": "string", "description": "教室"},
                                "weeks": {"type": "string", "description": "上课周次 如 1-16"}
                            },
                            "required": ["course_name", "week_day", "start_node", "end_node"]
                        }
                    }
                },
                "required": ["courses"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_courses",
            "description": "删除课程。传 weekday 删除指定星期的课，不传则清空全部课程。",
            "parameters": {
                "type": "object",
                "properties": {
                    "weekday": {
                        "type": "integer",
                        "description": "星期几 1-5，不传则删除全部"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_tasks",
            "description": "查询待完成的作业/任务列表。自动按当前用户的 scope 隔离：只显示自己的(private) 和公共的(public)。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "添加一条作业/任务。scope='public' 设为全局任务（所有人可见），scope='private'(默认)仅自己可见。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "作业内容"},
                    "ddl": {"type": "string", "description": "截止时间 YYYY-MM-DD HH:MM，可选"},
                    "scope": {"type": "string", "enum": ["private", "public"], "description": "private=仅自己可见，public=全局可见。默认 private"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "删除指定任务。只能删除自己创建的(private)或公共的(public)任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "任务ID"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索。用于查询实时信息、天气、新闻等不确定的内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容。可以读取代码、配置文件、数据文件等。支持 offset/limit 分段读取大文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径（相对于项目根目录）"},
                    "limit": {"type": "integer", "description": "最多读取行数，不传则读全部。大文件建议传 500-1000 避免 token 超限"},
                    "offset": {"type": "integer", "description": "起始行号（从0开始），不传默认第0行"}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入文件内容。可以创建新文件或修改现有文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径（相对于项目根目录）"},
                    "content": {"type": "string", "description": "文件内容"}
                },
                "required": ["file_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出目录下的文件和子目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir_path": {"type": "string", "description": "目录路径（相对于项目根目录，默认为当前目录）"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_tool",
            "description": "创建新工具。可以动态扩展自己的能力。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "description": "工具名称"},
                    "tool_code": {"type": "string", "description": "工具的Python代码（函数定义）"},
                    "tool_description": {"type": "string", "description": "工具描述"}
                },
                "required": ["tool_name", "tool_code", "tool_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_cmd",
            "description": "执行系统命令。Windows 环境用 cmd 命令，持续运行的服务（http.server等）用 background=true。执行前需用户确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "command": {"type": "string", "description": "要执行的命令（Windows cmd 格式）"},
                    "description": {"type": "string", "description": "命令说明"},
                    "background": {"type": "boolean", "description": "是否后台运行（用于长期服务如 http.server）"},
                    "confirmed": {"type": "boolean", "description": "是否已确认"}
                },
                "required": ["user_id", "command", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "think",
            "description": "深度思考工具。简单问题用 fast 模式，复杂问题用 deep 模式（开启深度思考）。auto 模式自动判断。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "要思考的问题"},
                    "mode": {
                        "type": "string",
                        "enum": ["fast", "deep", "auto"],
                        "description": "思考模式：fast=快速简单，deep=深度推理，auto=自动判断"
                    }
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pending_result",
            "description": "检查是否有子Agent返回了异步执行结果。非阻塞轮询：有结果就返回，没有就返回pending。用户追问或新消息时先调此工具检查。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "swarm_execute",
            "description": "多Agent协作编排：并行派发多个Agent协同完成任务。支持Agent间REQUEST/RESULT通信协议。适合复杂多步骤任务（写网页+查资料+识图→组装）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "workflow_json": {"type": "string", "description": "JSON格式的工作流定义：{\"parallel\":[{\"task_id\":\"1\",\"agent\":\"researcher\",\"task\":\"...\"},...],\"final\":{\"agent\":\"code-executor\",\"task\":\"汇总\"},\"interop\":true}"}
                },
                "required": ["user_id", "workflow_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_agents",
            "description": "查看所有子Agent的当前工作状态（哪些空闲、哪些正在执行任务）。用户问「Agent状态」「谁在忙」「哪些空闲」时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_nickname",
            "description": "设置当前用户的昵称。用户说「我叫XX」「我是XX」「叫我XX」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "nickname": {"type": "string", "description": "要设置的昵称"}
                },
                "required": ["nickname"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_user",
            "description": "通过昵称或用户ID查找用户。用于解析「@昵称」或「XX的作业」等引用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "identifier": {"type": "string", "description": "用户昵称或用户ID"}
                },
                "required": ["identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "identify_me",
            "description": "注册/声明当前用户的身份。用户说「我是XX」「我叫XX」时调用此工具记住身份。",
            "parameters": {
                "type": "object",
                "properties": {
                    "nickname": {"type": "string", "description": "用户声明的昵称"}
                },
                "required": ["nickname"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "expose",
            "description": "一键暴露内容到公网。启动 http.server + ngrok 内网穿透，返回公网 URL 供手机访问。用户说「发给我」「分享」「手机看」「把xxx暴露到公网」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "port": {"type": "integer", "description": "本地端口，默认 8765"},
                    "file_path": {"type": "string", "description": "项目内的文件路径，如 love_for_yangqingci.html。与 content 二选一"},
                    "content": {"type": "string", "description": "动态 HTML 内容字符串。与 file_path 二选一"},
                    "mobile_fix": {"type": "boolean", "description": "是否自动添加手机端适配，默认 true"}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": "将任务分发给指定的子Agent后台执行（异步，不阻塞）。调用后立即返回，用 get_pending_result 获取结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "agent_name": {"type": "string", "description": "子Agent名称"},
                    "task_description": {"type": "string", "description": "要执行的详细任务描述"},
                    "context": {"type": "string", "description": "额外上下文信息，可选"}
                },
                "required": ["user_id", "agent_name", "task_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_skill",
            "description": "当用户需要的能力没有对应技能时，生成新技能的 SKILL.md 方案草案。用户审阅确认后再用 register_skill 注册。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "intent_description": {"type": "string", "description": "用户意图和需求的详细描述"},
                    "user_message": {"type": "string", "description": "用户的原始消息"}
                },
                "required": ["user_id", "intent_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "register_skill",
            "description": "正式注册新技能。必须用户确认后才执行（confirmed=true）。会创建技能目录、SKILL.md，并更新技能清单。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "name": {"type": "string", "description": "技能名称（英文小写+连字符）"},
                    "skill_md_content": {"type": "string", "description": "SKILL.md 完整内容（包含 YAML frontmatter）"},
                    "confirmed": {"type": "boolean", "description": "是否已确认。首次 false，用户确认后 true"}
                },
                "required": ["user_id", "name", "skill_md_content"]
            }
        }
    },
]

# 工具分发表
TOOLS_MAP = {
    "plan_task": plan_task,
    "update_todo": update_todo,
    "get_todos": get_todos,
    "reflect": reflect,
    "self_heal": self_heal,
    "evolve_pipeline": evolve_pipeline,
    "reuse_pipeline": reuse_pipeline,
    "self_update": self_update,
    "query_courses": query_courses,
    "add_courses": add_courses,
    "delete_courses": delete_courses,
    "query_tasks": query_tasks,
    "add_task": add_task,
    "delete_task": delete_task,
    "set_nickname": set_nickname,
    "resolve_user": resolve_user,
    "identify_me": identify_me,
    "web_search": web_search,
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
    "create_tool": create_tool,
    "run_cmd": run_cmd,
    "think": think,
    "expose": expose,
    "propose_skill": propose_skill,
    "register_skill": register_skill,
    "delegate_task": delegate_task,
    "get_pending_result": get_pending_result,
    "swarm_execute": swarm_execute,
    "list_agents": list_agents,
}
