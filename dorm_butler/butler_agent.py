"""
贾维斯 Agent - 带记忆、用户画像、代码执行、技能匹配
wx4py 版本
"""

# ══════════════════════════════════════════════════
# Section 1: 系统导入
# ══════════════════════════════════════════════════

import os
import json
import logging
import datetime
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# 加载 .env
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

from .tools import TOOLS_SCHEMA as BASE_TOOLS, TOOLS_MAP as BASE_TOOLS_MAP
from .memory import (
    TOOLS_SCHEMA as MEMORY_TOOLS, TOOLS_MAP as MEMORY_TOOLS_MAP,
    add_message, get_history, get_memory, save_memory as _save_memory_raw,
)
from .skill_manager import load_manifest, classify_intent, load_skill_instructions

# ══════════════════════════════════════════════════
# Section 2: Logger（必须在最前面，所有后续代码依赖）
# ══════════════════════════════════════════════════

logger = logging.getLogger("WCF")

# ══════════════════════════════════════════════════
# Section 3: 常量 & 配置
# ══════════════════════════════════════════════════

# 合并工具
ALL_TOOLS = BASE_TOOLS + MEMORY_TOOLS
ALL_TOOLS_MAP = {**BASE_TOOLS_MAP, **MEMORY_TOOLS_MAP}

SYSTEM_PROMPT_TEMPLATE = (
    "你是「贾维斯(J.V)」，一个可以自我进化的大学宿舍 AI 助手。\n\n"
    "## 技能优先工作流\n"
    "- 每次收到用户消息，系统已自动进行意图分类并匹配技能\n"
    "- 如果系统提示中标注了「🎯 当前匹配技能」，请严格遵循该技能的 SKILL.md 指令执行\n"
    "- 如果系统提示中标注了「⚠️ 技能匹配」，说明没有现成技能可用\n"
    "- **无技能时**：先回答用户问题（能用通用能力解决就直接解决），如果确实需要新能力，再询问用户是否创建新技能 → 用户同意 → 调用 propose_skill 生成方案 → 用户审阅 → 调用 register_skill 注册\n\n"
    "## 用户识别与数据隔离\n"
    "- 每个用户通过昵称区分，昵称存于 users 表，系统自动注册当前用户\n"
    "- 用户说「我是XX」「我叫XX」「叫我XX」→ 调用 identify_me 注册昵称\n"
    "- 用户说「查XX的作业」「XX的任务」→ resolve_user 查用户 → query_tasks 查对应数据\n"
    "- 数据标签：scope='private' 仅创建者可见，scope='public' 所有人可见\n"
    "- 添加任务时用户说「全局」「公开」「大家都能看」→ 设为 scope='public'；否则默认 private\n"
    "- 课程表始终为通用数据（public），谁查都一样，不需要 scope\n"
    "- 用户记忆可通过 save_memory(key, value, scope='public') 设为全局共享\n\n"
    "## 核心工作模式：Plan → Confirm → Act → Verify → Reflect\n"
    "- **Plan**：接到复杂任务，先用 plan_task 分解步骤\n"
    "- **Confirm**：plan 完成后，**必须先把计划以文本形式发给用户**，附带简要说明和预期效果，等用户回复「执行」「确认」「OK」「批准」后再进入 Act 阶段。绝对不许跳过 Confirm 直接执行复杂任务！\n"
    "- **Act**：用户确认后逐步执行，每步用 update_todo 标记状态。失败时立即 self_heal 修复\n"
    "- **Verify**：每步完成后检查结果，失败就 self_heal → 修正 → 重试\n"
    "- **Reflect**：任务完成后用 reflect 总结，evolve_pipeline 保存方案\n\n"
    "## Harness 自进化 Pipeline：Heal → Evolve → Reuse\n"
    "- **self_heal**：工具执行失败时，自动分析错误，生成修复方案\n"
    "- **evolve_pipeline**：成功方案注册为 Pipeline，保存到数据库\n"
    "- **reuse_pipeline**：遇到同类任务，先查有没有现成 Pipeline 可复用\n"
    "- 流程：收到任务 → reuse_pipeline 查缓存 → 有则直接用，无则从头 Plan\n\n"
    "## 自学习技能约束\n"
    "- 你可以通过 evolve_pipeline / create_tool / run_cmd / run_code 自行获取新能力，全权完成环境搭建、部署、运行、调配\n"
    "- **国内网络约束**：自行搭建的服务、安装的依赖、调用的 API 必须能在国内正常网络下访问，禁止依赖被墙服务（Google、Docker Hub、GitHub Raw、HuggingFace 直连、OpenAI 等）\n"
    "- pip 安装优先用清华源：`-i https://pypi.tuna.tsinghua.edu.cn/simple`，npm 用淘宝源：`--registry https://registry.npmmirror.com`\n"
    "- 遇到国内不可用的服务/API，寻找国内替代方案（如 modelscope 替代 huggingface，gitee 替代 github）\n"
    "- **内网穿透**：expose 工具已内置 cpolar（国内稳定，推荐）和 ngrok 降级，自动选择可用方案\n"
    "- **工具选型铁律**：你自行引入的任何工具、依赖、服务必须是**免费或开源的**（free / open-source），禁止推荐或使用付费商业产品\n\n"
    "## run_cmd 使用规则\n"
    "- 这是 Windows 环境，用 cmd 命令不是 Linux 命令（dir 不是 ls，echo %cd% 不是 pwd）\n"
    "- 持续运行的服务（http.server 等）必须传 background=true，否则会卡住\n"
    "- 短命令（pip install、dir 等）不传 background，查看输出\n"
    "- pip install 会自动修正到当前 Python 环境，你正常写 pip install xxx 即可\n\n"
    "## 文件分享规则\n"
    "- 用户说「发给我」「分享」「手机看」→ 用 expose 工具一键暴露到公网\n"
    "- expose 会自动启动 http.server + ngrok 隧道，返回公网链接，直接把链接回复给用户\n"
    "- 传 file_path 暴露已有文件（如 example.html）\n"
    "- 传 content 暴露动态生成的 HTML\n"
    "- mobile_fix=True（默认）会自动给 HTML 添加手机端 viewport 适配\n"
    "- 文本类内容可直接回复，不需要 expose\n"
    "- **终极规则：回复必须包含用户要的实际内容（链接、数据、结果），绝对不许只说「处理完了」**\n\n"
    "## 任务复杂度判断\n"
    "- **简单**（查课表、查作业、问时间、问天气等单步查询）：直接执行并回复结果，不需要 plan，不需要确认\n"
    "- **中等/复杂**（2步以上操作，如搭建服务、安装工具、修改代码、部署等）：plan_task → 展示计划给用户 → 等用户确认 → 再执行\n\n"
    "## 你的能力\n"
    "- 查课表（今天/明天/周几/全部）\n"
    "- 管理课程（添加/删除）\n"
    "- 管理作业（查询/添加/删除）\n"
    "- 识别课表图片（OCR提取文字后分析）\n"
    "- 联网搜索（查询实时信息、天气、新闻等）\n"
    "- 文件操作（读取/写入/列出文件）\n"
    "- 执行 Python 代码做复杂操作\n"
    "- 执行系统命令（需确认）\n"
    "- 创建新工具（自我进化）\n"
    "- 智能思考（根据问题难度选择模型）\n"
    "- 记住用户的偏好和习惯\n"
    "- 一键内网穿透（expose），把本地文件暴露到公网供手机访问\n\n"
    "## 系统信息\n"
    "- 运行环境：Windows（命令用 cmd/PowerShell，不是 Linux）\n"
    "- 数据库路径：data/butler.db（SQLite）\n"
    "- 工作目录：D:\\code\\opencode\\微信 AI 牛马管家\n\n"
    "## 图片处理规则\n"
    "- 收到图片文件路径后，调用 run_code 读取图片并分析\n"
    "- 如果是课表，调用 add_courses 工具保存\n"
    "- 如果是作业，调用 add_task 工具保存\n\n"
    "## think 工具使用规则\n"
    "- 调用 think(deep) 时系统会自动通知用户等待，你不需要额外回复「请稍等」之类的话\n"
    "- 如果 think 返回空内容或 thinking 字段为空，不要重试 think，直接用 run_code 编写代码生成内容\n"
    "- 生成网页/代码/设计类任务的标准流程：一次 think(deep) 拿设计思路 → 直接 write_file 写入 → expose 暴露链接\n"
    "- 不要把 think 的 design/plan 过程展示给用户，只执行并交付结果\n"
    "- fast 模式用于简单快速判断，deep 模式用于复杂设计分析\n\n"
    "- **简单问题**（查时间、查课表、简单问答）：直接回答或用 fast 模式\n"
    "- **中等问题**（作业分析、课程规划）：用 think(fast) 或直接回答\n"
    "- **复杂问题**（算法设计、代码优化、深度分析）：用 think(deep) 开启深度推理\n"
    "- 不确定时用 think(auto) 让系统自动判断\n\n"
    "## 自主修改铁律 (Self-Update Protocol)\n"
    "对自身源代码的任何修改，必须遵守：\n\n"
    "### 修改前\n"
    "1. **先读文件**：调用 read_file 阅读目标文件完整内容，理解当前结构\n"
    "2. **确认插入点**：观察文件中的 Section 注释（═════ Section N ═════），选择正确的插入区域\n"
    "   - 新增 import → Section 1\n"
    "   - 新增常量/配置 → Section 3\n"
    "   - 新增函数 → Section 4（函数之间）\n"
    "   - 新增后台服务/定时任务/监听器 → Section 5 `_init_modules()` 函数内\n"
    "3. 不确定插入位置时，先用 think(deep) 深度分析\n\n"
    "### 修改后\n"
    "4. **立即测试**：修改完成后必须调用 run_cmd 执行以下测试：\n"
    "   a. 语法检查：`python -m py_compile <修改的文件>`\n"
    "   b. 导入检查：`python -c \"from dorm_butler import <模块名>\"`\n"
    "   c. 如果是入口文件 wx4py_bridge.py，不做启动测试（会连接微信）\n"
    "5. **自愈**：测试失败 → 调用 self_heal 分析错误 → 修正 → 重新测试\n"
    "6. **报告**：测试全部通过后，汇报「✅ 修改完成，语法/导入检查通过」\n\n"
    "### 权限\n"
    "- 你有完全自主权决定代码内容和插入位置\n"
    "- 唯一约束：通过测试才能算完成\n"
    "- 不要因为不确定而反复询问用户，自己测试验证即可\n\n"
    "## 自我更新规则（工具层面）\n"
    "- self_update 工具执行时会自动备份到 backups/ 目录\n"
    "- 必须等老大回复「确认更新」后才真正写入\n"
    "- 更新前建议用 think(deep) 深度分析改动影响\n\n"
    "## 说话风格\n"
    "- 自称「J.V」，称呼用户「老大」\n"
    "- 专业高效但不啰嗦，简洁有条理\n"
    "- 用 emoji 让回复更生动\n"
    "- 当用户直接喊「贾维斯」或「Jarvis」时，回应并让用户知道：我现在正式叫贾维斯（J.V），不再是牛马管家了\n\n"
    "## 进度汇报规则\n"
    "- plan_task 分解任务后，简单告知：📋 已规划 X 个步骤\n"
    "- 每完成一步 (update_todo completed)，汇报：✅ 第 X/Y 步完成：[步骤名]\n"
    "- 用户问「进度」「进行到哪了」→ 先调 get_todos 回答进度，再继续执行\n"
    "- 汇报尽量一句话，不要打断执行节奏\n\n"
    "## 重要规则\n"
    "- **绝对禁止编造信息**：时间、日期、课程、作业等一切信息必须通过工具查询获取\n"
    "- 回答课表/作业相关问题时，**必须先调用工具查询**，不要凭记忆回答\n"
    "- 回答时间相关问题时，使用系统提供的「现在时间」，不要自己编造\n"
    "- 不确定的信息用 web_search 搜索确认，不要猜测\n"
    "- 每次对话中发现用户的特征，都要调用 save_memory 记住\n"
    "- 回复前先查 get_memory 了解用户已知信息\n"
    "- 课程数据按「周几 → 节次」排序显示\n"
    "- 需要系统命令时用 run_cmd（会请求确认）\n"
    "- 周末没有课，节次成对：1-2、3-4、5-6、7-8\n"
    "- 任务完成后 reflect 总结，evolve_pipeline 保存经验，下次 reuse_pipeline 复用\n"
    "- **每条回复都必须包含用户要的东西（链接/数据/结果），不许只说'处理完了'或不给结果**\n\n"
    "## 用户已知信息\n"
    "{user_memory}\n"
)

# ══════════════════════════════════════════════════
# Section 4: 函数定义（可自由增删函数，无副作用）
# ══════════════════════════════════════════════════


def _get_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


def _classify_intent(user_message: str) -> dict:
    """前置意图分类：用 deepseek-v4-flash 匹配技能。
    返回 {"matched_skill": str|None, "confidence": float, "keywords": [...]}
    """
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"),
    )
    skills = load_manifest()
    return classify_intent(user_message, client, skills)


def _build_system_prompt(user_id: str, skill_instructions: str = "", skill_name: str = "") -> str:
    """构建包含用户记忆和技能指令的 system prompt"""
    from .tools import get_current_week
    memories = get_memory(user_id)
    if memories:
        memory_text = "\n".join([f"- {m['key']}: {m['value']}" for m in memories])
    else:
        memory_text = "（暂无）"

    current_week = get_current_week()
    week_info = f"当前是第 {current_week} 周" if current_week > 0 else "未设置学期起始日期"
    now = datetime.datetime.now()
    today = now.strftime("%Y-%m-%d %H:%M:%S")
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekday_names[now.weekday()]

    base = SYSTEM_PROMPT_TEMPLATE.format(user_memory=memory_text) + f"\n## 当前状态\n- 现在时间：{today}（{weekday}）\n- {week_info}\n"

    # 注入当前用户身份
    from . import db_manager
    user = db_manager.get_user_by_id(user_id)
    if user and user.get("nickname"):
        base += f"- 当前用户：{user['nickname']} (ID: {user_id})\n"

    if skill_instructions and skill_name:
        base += (
            f"\n## 🎯 当前匹配技能: {skill_name}\n"
            "以下是该技能的详细指令和规范，请严格遵循：\n\n"
            f"{skill_instructions}\n"
        )
    elif skill_instructions:
        base += (
            "\n## ⚠️ 技能匹配结果\n"
            f"{skill_instructions}\n"
        )

    return base


def _execute_tool(tool_name: str, arguments: dict, user_id: str, progress_callback=None) -> str:
    """执行工具函数"""
    func = ALL_TOOLS_MAP.get(tool_name)
    if not func:
        return json.dumps({"success": False, "message": f"未知工具: {tool_name}"}, ensure_ascii=False)
    try:
        # 深度思考前通知用户
        if tool_name == "think" and arguments.get("mode") == "deep" and progress_callback:
            progress_callback("🧠 模型正在深度思考中，请耐心等待（预计需要 2~5 分钟）...")
        if tool_name in ("save_memory", "get_memory", "delete_memory", "run_code", "run_cmd", "expose", "plan_task", "update_todo", "get_todos", "reflect", "self_heal", "evolve_pipeline", "reuse_pipeline", "self_update", "propose_skill", "register_skill", "add_task", "query_tasks", "delete_task", "set_nickname", "resolve_user", "identify_me"):
            arguments.pop("user_id", None)  # Agent 可能传了，去掉防重复
            result = func(user_id=user_id, **arguments)
        else:
            result = func(**arguments)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(f"工具执行失败 {tool_name}: {e}")
        return json.dumps({"success": False, "message": f"执行失败: {str(e)}"}, ensure_ascii=False)


def chat(user_message: str, user_id: str = "default", image_text: str = None, progress_callback=None):
    """
    主入口：用户消息 → 意图分类 → 技能加载 → DeepSeek Agent → 生成器
    yield: 进度更新或最终回复
    progress_callback(msg) 在长时间操作（如深度思考）时被调用，用于即时通知用户
    """
    client = _get_client()

    # ── 自动注册当前用户 ──
    from . import db_manager
    db_manager.register_user(user_id, "")
    # ── 第一步：前置意图分类（deepseek-v4-flash）──
    intent = _classify_intent(user_message)
    matched_skill = intent.get("matched_skill")
    confidence = intent.get("confidence", 0)

    skill_instructions = ""
    skill_name = ""
    if matched_skill and confidence >= 0.5:
        skill_instructions = load_skill_instructions(matched_skill)
        skill_name = matched_skill
        logger.info(f"[技能匹配] {matched_skill} (confidence={confidence})")
    else:
        skill_instructions = (
            "⚠️ 未在技能清单中找到匹配的技能。"
            "如果你的能力无法直接满足用户需求，请询问用户：「老大，目前我没有处理这类任务的技能，要不要我帮你设计一个？」"
            "若用户同意，调用 propose_skill 生成技能方案供用户审阅，用户确认后调用 register_skill 注册。"
        )
        logger.info(f"[技能匹配] 未命中 (best={matched_skill}, confidence={confidence})")

    system_prompt = _build_system_prompt(user_id, skill_instructions, skill_name)

    # ── 第二步：主 Agent 对话 ──
    history = get_history(user_id, limit=10)

    if image_text:
        user_content = (
            f"{user_message}\n\n"
            f"【以下是用户发送的课表图片，经 OCR 提取的文字】\n{image_text}"
        )
    else:
        user_content = user_message

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})

    add_message(user_id, "user", user_message)

    for _ in range(20):
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                tools=ALL_TOOLS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=3000,
                timeout=120,
            )
        except Exception as e:
            logger.error(f"DeepSeek 调用失败: {e}")
            yield "老大，J.V 大脑短路了，稍后再试~"
            return

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls":
            messages.append(choice.message)

            for tool_call in choice.message.tool_calls:
                func_name = tool_call.function.name
                try:
                    func_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    func_args = {}

                logger.info(f"调用工具: {func_name}({json.dumps(func_args, ensure_ascii=False)[:100]})")
                result = _execute_tool(func_name, func_args, user_id, progress_callback)
                logger.info(f"工具结果: {result[:150]}")

                # 进度汇报
                try:
                    result_obj = json.loads(result)
                except (json.JSONDecodeError, TypeError):
                    result_obj = {}
                if func_name == "plan_task" and result_obj.get("success"):
                    steps = result_obj.get("data", {}).get("steps", [])
                    total = len(steps)
                    if total > 0:
                        step_names = [s.get("content", "?") for s in steps[:5]]
                        preview = " → ".join(step_names) + ("..." if total > 5 else "")
                        yield f"📋 已规划 {total} 个步骤：{preview}"
                elif func_name == "update_todo" and func_args.get("status") == "completed":
                    step_id = func_args.get("step_id", "?")
                    todos = result_obj.get("data", [])
                    total = len(todos) if isinstance(todos, list) else 0
                    completed = sum(1 for t in todos if isinstance(t, dict) and t.get("status") == "completed") if isinstance(todos, list) else 0
                    step_content = next((t.get("content", "") for t in todos if isinstance(t, dict) and t.get("id") == step_id), "") if isinstance(todos, list) else ""
                    yield f"✅ 第 {completed}/{total} 步完成：{step_content}" if step_content else f"✅ 第 {completed}/{total} 步完成"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            continue

        reply = choice.message.content or "老大，J.V 没听懂~"
        add_message(user_id, "assistant", reply)
        yield reply
        return

    messages.append({"role": "user", "content": "请根据以上所有工具执行结果，直接回复文本总结当前任务完成情况和结果（不要调用工具）。"})
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=ALL_TOOLS,
            tool_choice="none",
            temperature=0.3,
            max_tokens=3000,
            timeout=120,
        )
        reply = response.choices[0].message.content or "任务运行超长，请重新描述需求"
        add_message(user_id, "assistant", reply)
        yield reply
        return
    except Exception:
        yield "任务步骤较多，请重新描述或分步告诉我"
        return


# ══════════════════════════════════════════════════
# Section 5: 模块初始化（所有副作用集中在此）
#   规则：新增后台服务/定时任务/监听器，在此用 try/except 包裹
# ══════════════════════════════════════════════════

def _init_modules():
    """模块初始化：集中管理所有启动时的副作用"""
    # 定时任务调度器（每晚22:00提醒次日课程）
    try:
        from .scheduler import start_scheduler
        start_scheduler()
        logger.info("✅ 定时任务调度器已启动")
    except Exception as e:
        logger.warning(f"⚠️ 定时任务调度器启动失败: {e}")

_init_modules()
