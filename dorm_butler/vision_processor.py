"""
视觉处理模块 - 双AI协作链路
流程：图片预处理 -> Wanx视觉提取 -> DeepSeek意图分析 -> 存入待确认表
"""

import os
import sys
import json
import base64
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter
from openai import OpenAI
from openai import APIError, APITimeoutError, APIConnectionError

# 加载 .env
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

from . import db_manager

# ───────────────────────── 常量 ─────────────────────────

PROCESSED_IMAGE_PATH = str(_PROJECT_ROOT / "data" / "temp_processed.png")

WANX_PROMPT = (
    "请精准提取图片中所有关于上课、时间、地点、作业、考试的文字信息，"
    "保留原始格式输出。"
)

DEEPSEEK_SYSTEM_PROMPT = (
    "你是宿舍 AI 助手贾维斯(J.A.R.V.I.S)，职责是从文字中提取课表和作业信息。\n\n"
    "课表格式规则：\n"
    "- 横排是星期（周一到周五），竖排是节次（第1-2节、第3-4节...）\n"
    "- 每门课占连续两节（如第1-2节、第3-4节、第5-6节、第7-8节）\n"
    "- 周末（周六、周日）绝对没有课！\n"
    "- week_day: 1=周一, 2=周二, 3=周三, 4=周四, 5=周五\n\n"
    "输出规则：\n\n"
    "1. 若包含课表信息，输出：\n"
    '{"intent": "add_courses", "details": {"courses": [\n'
    '  {"course_name": "课程名", "week_day": 1, "start_node": 1, "end_node": 2, "location": "教室", "weeks": "1-16"}\n'
    ']}}\n\n'
    "2. 若包含调课/换地点，输出：\n"
    '{"intent": "update_course", "details": {...}}\n\n'
    "3. 若包含作业/DDL，输出：\n"
    '{"intent": "add_task", "details": {...}}\n\n'
    "4. 否则：\n"
    '{"intent": "chat"}\n\n'
    "严格只输出 JSON。"
)


# ───────────────────────── 图像预处理 ─────────────────────────

def preprocess_image(image_path: str) -> str:
    img = Image.open(image_path)

    if img.mode == "RGBA":
        img = img.convert("RGB")

    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
    img = ImageEnhance.Contrast(img).enhance(1.6)
    img = ImageEnhance.Sharpness(img).enhance(2.2)
    img = ImageEnhance.Brightness(img).enhance(1.1)

    max_height = 2000
    if img.height > max_height:
        ratio = max_height / img.height
        new_width = int(img.width * ratio)
        img = img.resize((new_width, max_height), Image.Resampling.LANCZOS)

    os.makedirs(os.path.dirname(PROCESSED_IMAGE_PATH), exist_ok=True)
    img.save(PROCESSED_IMAGE_PATH, quality=95)
    return PROCESSED_IMAGE_PATH


# ───────────────────────── 阿里云 Wanx (眼睛) ─────────────────────────

def ocr_with_wanx(image_path: str) -> str:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("找不到 DashScope API Key，请检查 .env 文件！")

    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    mime = "image/png" if image_path.endswith(".png") else "image/jpeg"
    data_url = f"data:{mime};base64,{image_data}"

    try:
        response = client.chat.completions.create(
            model="qwen-vl-plus",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": WANX_PROMPT},
                    ],
                }
            ],
            max_tokens=3000,
            timeout=60,
        )
        return response.choices[0].message.content.strip()

    except (APITimeoutError, APIConnectionError, APIError):
        raise


# ───────────────────────── DeepSeek (大脑) ─────────────────────────

def analyze_with_deepseek(text: str) -> dict:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("找不到 DeepSeek API Key，请检查 .env 文件！")

    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"),
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=1500,
            timeout=30,
        )
        result_text = response.choices[0].message.content.strip()

    except (APITimeoutError, APIConnectionError, APIError):
        raise

    try:
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            result_text = "\n".join(json_lines)

        return json.loads(result_text)

    except json.JSONDecodeError:
        return {"intent": "chat"}


# ───────────────────────── 主流水线 ─────────────────────────

def process_image(image_path: str, user_id: str = "unknown") -> dict:
    processed_path = preprocess_image(image_path)
    extracted_text = ocr_with_wanx(processed_path)

    if not extracted_text or len(extracted_text.strip()) < 5:
        return {"intent": "chat", "details": {}, "extracted_text": "", "pending_id": None}

    analysis = analyze_with_deepseek(extracted_text)
    intent = analysis.get("intent", "chat")
    details = analysis.get("details", {})

    pending_id = None
    if intent in ("update_course", "add_task", "add_courses") and details:
        data_json = json.dumps(details, ensure_ascii=False)
        pending_id = db_manager.add_pending(
            user_id=user_id,
            intent=intent,
            data_json=data_json,
            confidence=analysis.get("confidence", 0.0),
        )

    return {
        "intent": intent,
        "details": details,
        "extracted_text": extracted_text,
        "pending_id": pending_id,
    }
