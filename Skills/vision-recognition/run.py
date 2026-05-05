"""
视觉识别 - 命令行运行入口
用法: python run.py <图片路径>
示例: python run.py data/test.png
依赖: dorm_butler.vision_processor
"""
import sys
import os

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dorm_butler import db_manager
from dorm_butler.vision_processor import process_image

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python run.py <图片路径>")
        print("示例: python run.py data/test.png")
        sys.exit(1)

    image_path = sys.argv[1]
    if not os.path.exists(image_path):
        print(f"错误: 文件不存在 - {image_path}")
        sys.exit(1)

    db_manager.init_db()

    print("=" * 50)
    print("[J.A.R.V.I.S] 开始视觉识别...")
    print("=" * 50)

    result = process_image(image_path)

    print()
    print("=" * 50)
    print(f"意图: {result['intent']}")
    if result.get("details"):
        import json
        print(f"详情: {json.dumps(result['details'], ensure_ascii=False, indent=2)}")
    if result.get("pending_id"):
        print(f"待确认ID: {result['pending_id']}")
    print("=" * 50)
