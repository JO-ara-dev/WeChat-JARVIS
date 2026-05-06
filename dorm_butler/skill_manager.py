"""
技能管理器 - Skills Manifest 解析、意图分类、技能注册
"""
import os
import json
import re
import logging
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
_MANIFEST_PATH = _PROJECT_ROOT / "Skills" / "manifest.json"
_SKILLS_DIR = _PROJECT_ROOT / "Skills"
_README_PATH = _SKILLS_DIR / "README.md"

logger = logging.getLogger("WCF")

SKILL_MD_TEMPLATE = """---
name: {name}
description: {description}
trigger_keywords: {trigger_keywords}
tools: {tools}
executable: {executable}
version: 1.0
created: {created}
---

# {title}

## 能力描述

{description}

## 适用场景

{scenarios}

## 调用流程

```
{workflow}
```

## 工具参数

{params_doc}

## 示例

{examples}

## 注意事项

{notes}
"""


def load_manifest() -> list[dict]:
    """加载技能清单"""
    if not _MANIFEST_PATH.exists():
        logger.warning(f"manifest.json 不存在: {_MANIFEST_PATH}")
        return []
    with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("skills", [])


def classify_intent(user_message: str, client, skills: list[dict] = None, model: str = "GLM-4.7-Flash", mgr=None, provider=None) -> dict:
    """
    前置意图分类：用指定模型快速判断用户意图，匹配技能。

    返回: {"matched_skill": "skill-name" | None, "confidence": float, "keywords": [...]}
    """
    if skills is None:
        skills = load_manifest()

    if not skills:
        return {"matched_skill": None, "confidence": 0, "keywords": []}

    skills_list_text = json.dumps(
        [
            {
                "name": s["name"],
                "description": s["description"],
                "trigger_keywords": s["trigger_keywords"],
            }
            for s in skills
        ],
        ensure_ascii=False,
        indent=2,
    )

    classification_prompt = (
        "你是一个意图分类器。分析用户消息的核心意图，匹配到最合适的技能。\n\n"
        "## 可用技能列表\n"
        f"{skills_list_text}\n\n"
        "## 规则\n"
        "- 优先理解消息的核心任务（写网页？查课表？搜资料？），而非零散关键词\n"
        "- 消息中同时出现多个技能的关键词时，选核心任务对应的技能\n"
        "- 例如「写一个课表网页」→ 核心是写网页，匹配 web-designer 而非 course-manager\n"
        "- 例如「今天有什么课」→ 核心是查课表，匹配 course-management\n"
        "- 明确匹配时 confidence 设为 0.8-1.0\n"
        "- 模糊匹配时 confidence 设为 0.5-0.7\n"
        "- 完全不匹配时 matched_skill=null, confidence=0\n"
        "- keywords 提取消息中 2-5 个核心关键词\n\n"
        "仅返回 JSON 对象：\n"
        '{"matched_skill": "skill-name" | null, "confidence": 0.0-1.0, "keywords": ["词1", "词2"]}'
    )

    try:
        if mgr and provider:
            from .agent_manager import call_with_fallback, FallbackError
            try:
                response = call_with_fallback(
                    mgr, provider, model,
                    {"temperature": 0, "max_tokens": 300, "response_format": {"type": "json_object"}},
                    [{"role": "user", "content": classification_prompt},
                     {"role": "user", "content": f"用户消息：{user_message}"}],
                )
            except FallbackError:
                logger.warning("[意图分类] 容灾失败，降级返回空匹配")
                return {"matched_skill": None, "confidence": 0, "keywords": []}
        else:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": classification_prompt},
                            {"role": "user", "content": f"用户消息：{user_message}"}],
                temperature=0,
                max_tokens=300,
                timeout=15,
                response_format={"type": "json_object"},
            )
        result_text = response.choices[0].message.content or "{}"
        result_text = result_text.strip()

        # 多级降级 JSON 解析
        json_obj = None

        # 策略1：直接解析（response_format=json_object 多数情况有效）
        try:
            json_obj = json.loads(result_text)
        except json.JSONDecodeError:
            pass

        # 策略2：去掉 markdown 代码块再解析
        if json_obj is None:
            md_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", result_text)
            if md_match:
                try:
                    json_obj = json.loads(md_match.group(1))
                except json.JSONDecodeError:
                    pass

        # 策略3：按括号范围截取
        if json_obj is None:
            start = result_text.find("{")
            end = result_text.rfind("}")
            if start >= 0 and end > start:
                try:
                    json_obj = json.loads(result_text[start:end + 1])
                except json.JSONDecodeError:
                    pass

        if json_obj is None:
            logger.warning(f"[意图分类] 无法解析 JSON，原始返回: {result_text[:300]}")
            return {"matched_skill": None, "confidence": 0, "keywords": []}

        result = json_obj

        matched = result.get("matched_skill")
        confidence = result.get("confidence", 0)
        keywords = result.get("keywords", [])

        # 验证 matched_skill 是否在清单中
        if matched and not any(s["name"] == matched for s in skills):
            matched = None

        logger.info(
            f"[意图分类] matched={matched} confidence={confidence} keywords={keywords}"
        )
        return {"matched_skill": matched, "confidence": confidence, "keywords": keywords}

    except Exception as e:
        logger.error(f"[意图分类失败] {e}")
        return {"matched_skill": None, "confidence": 0, "keywords": []}


def load_skill_instructions(skill_name: str) -> str:
    """读取技能 SKILL.md 指令"""
    skill_md = _SKILLS_DIR / skill_name / "SKILL.md"
    if skill_md.exists():
        with open(skill_md, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def get_skill_by_name(name: str) -> dict | None:
    """根据名称查找技能定义"""
    skills = load_manifest()
    for s in skills:
        if s["name"] == name:
            return s
    return None


def generate_skill_proposal(intent_desc: str, user_message: str, client) -> str:
    """
    用 AI 生成新技能的 SKILL.md 草案。

    返回 SKILL.md 的 Markdown 内容字符串。
    """
    existing_skills = load_manifest()
    existing_names = [s["name"] for s in existing_skills]
    existing_tools = []
    for s in existing_skills:
        existing_tools.extend(s.get("tools", []))

    prompt = (
        "你是一个技能设计师。根据用户的需求，生成一个新技能的 SKILL.md 文档。\n\n"
        "## 已有技能（不要重复）\n"
        f"{json.dumps(existing_names, ensure_ascii=False)}\n\n"
        "## 已有工具（优先复用）\n"
        f"{json.dumps(list(set(existing_tools)), ensure_ascii=False)}\n\n"
        "## SKILL.md 格式要求\n"
        "使用以下 YAML frontmatter + Markdown 格式：\n"
        "```\n"
        "---\n"
        "name: skill-name\n"
        "description: 一句话描述\n"
        "trigger_keywords: 关键词1, 关键词2, 关键词3\n"
        "tools: tool1, tool2\n"
        "version: 1.0\n"
        "---\n\n"
        "# 技能标题\n\n"
        "## 能力描述\n...\n\n"
        "## 适用场景\n...\n\n"
        "## 调用流程\n...\n\n"
        "## 工具参数\n...\n\n"
        "## 示例\n...\n\n"
        "## 注意事项\n...\n"
        "```\n\n"
        "## 要求\n"
        "- 技能名称用英文小写+连字符\n"
        "- 触发关键词用中文，逗号分隔\n"
        "- 优先复用已有工具，除非必须新增\n"
        "- 调用流程用文本流程图\n"
        "- 必须包含至少一个示例\n\n"
        f"## 用户意图描述\n{intent_desc}\n\n"
        f"## 用户原始消息\n{user_message}\n\n"
        "请生成完整的 SKILL.md 内容（包括 YAML frontmatter），只输出 Markdown，不要解释。"
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
            timeout=30,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"[生成技能方案失败] {e}")
        return f"# 技能方案生成失败\n\n错误：{e}"


def register_skill(name: str, skill_md_content: str) -> dict:
    """
    注册新技能：创建目录、写入 SKILL.md、更新 manifest.json 和 README.md。

    返回 {"success": bool, "message": str}
    """
    # 1. 验证 name 格式
    if not re.match(r"^[a-z0-9-]+$", name):
        return {"success": False, "message": "技能名称只能包含小写字母、数字和连字符"}

    # 2. 检查是否已存在
    skill_dir = _SKILLS_DIR / name
    if skill_dir.exists():
        return {"success": False, "message": f"技能 {name} 已存在"}

    # 3. 从 SKILL.md 内容解析 YAML frontmatter
    yaml_match = re.match(r"^---\s*\n(.*?)\n---", skill_md_content, re.DOTALL)
    if not yaml_match:
        return {"success": False, "message": "SKILL.md 缺少 YAML frontmatter"}

    yaml_text = yaml_match.group(1)
    meta = {}
    for line in yaml_text.strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()

    skill_name_from_md = meta.get("name", name)
    description = meta.get("description", "")
    trigger_keywords_str = meta.get("trigger_keywords", "")
    trigger_keywords = [kw.strip() for kw in trigger_keywords_str.split(",") if kw.strip()]
    tools_str = meta.get("tools", "")
    tools = [t.strip() for t in tools_str.split(",") if t.strip()]
    executable = meta.get("executable", "").strip() or None

    # 4. 创建目录和文件
    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        with open(skill_dir / "SKILL.md", "w", encoding="utf-8") as f:
            f.write(skill_md_content)
    except Exception as e:
        return {"success": False, "message": f"文件写入失败: {e}"}

    # 5. 更新 manifest.json
    try:
        manifest = load_manifest()
        manifest.append({
            "name": name,
            "folder": f"{name}/",
            "trigger_keywords": trigger_keywords,
            "tools": tools,
            "executable": executable,
            "description": description,
        })
        with open(_MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump({"skills": manifest}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {"success": False, "message": f"更新 manifest.json 失败: {e}"}

    # 6. 同步 README.md
    try:
        sync_readme()
    except Exception as e:
        logger.warning(f"同步 README.md 失败: {e}")

    return {
        "success": True,
        "message": f"技能 {name} 注册成功！",
        "data": {
            "name": name,
            "dir": str(skill_dir),
            "trigger_keywords": trigger_keywords,
            "tools": tools,
        },
    }


def sync_readme():
    """根据 manifest.json 同步更新 README.md 的技能表格"""
    skills = load_manifest()
    if not skills:
        return

    # 读取现有 README.md
    readme_content = ""
    if _README_PATH.exists():
        with open(_README_PATH, "r", encoding="utf-8") as f:
            readme_content = f.read()

    # 构建技能索引表格行
    table_rows = ""
    for i, s in enumerate(skills, 1):
        executable = s.get("executable") or "—"
        keywords = ", ".join(s.get("trigger_keywords", [])[:4])
        table_rows += f"| {i} | {s['description']} | [{s['folder']}]({s['folder']}) | {executable} | {keywords} |\n"

    # 替换表格部分（| # | 技能 | ... 到第一个空行后的非表格行）
    table_pattern = re.compile(
        r"(\| # \| 技能 \| 文件夹 \| 可执行 \| 触发关键词 \|\n\|-+\|.*?\n)((?:\| \d+ \|.*?\n)*)",
        re.DOTALL,
    )
    new_table_header = (
        "| # | 技能 | 文件夹 | 可执行 | 触发关键词 |\n"
        "|---|------|--------|--------|------------|\n"
    )

    if table_pattern.search(readme_content):
        readme_content = table_pattern.sub(
            new_table_header + table_rows, readme_content
        )
    else:
        # 表格不存在，追加到末尾
        readme_content += "\n" + new_table_header + table_rows

    with open(_README_PATH, "w", encoding="utf-8") as f:
        f.write(readme_content)
