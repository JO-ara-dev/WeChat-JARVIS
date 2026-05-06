---
name: parallel-doc-generator
description: 三Agent并行文档生成技能 - 自动将内容生成真正的PPT/Word/Excel文档
version: 1.0.0
author: J.V
created: 2026-05-05
---

# 🎯 parallel-doc-generator — 三Agent并行文档生成器

## 技能简介

当老大说「生成一份PPT」「做成Word文档」「搞个Excel表格」时，自动启动**三Agent并行工作流**，将内容转化为真正的可双击打开的文档文件（非网页链接）。

## 触发指令

| 关键词 | 说明 |
|:------|:-----|
| 「生成PPT」「做个PPT」「做成演示文稿」 | 生成 `.pptx` 文件 |
| 「生成Word」「做个文档」「写个Word」 | 生成 `.docx` 文件 |
| 「生成Excel」「做个表格」「统计表」 | 生成 `.xlsx` 文件 |
| 「把XX做成文档」「转换成文件」 | 根据内容自动判断文档类型 |

## 工作流程

```
① 需求分析 (J.V think)
    ├── 确定文档类型（PPT/Word/Excel）
    ├── 提取内容结构（封面/目录/正文/结尾）
    └── 确认排版风格

② Plan任务分解 (plan_task)
    ├── 步骤1: 检查/安装依赖库
    ├── 步骤2: code-executor编写生成脚本
    ├── 步骤3: 运行脚本生成文档
    └── 步骤4: 交付文件给老大

③ ⚡ 三Agent并行执行 (swarm_execute)
    ├── 🛠️ system-admin → pip install 依赖库
    ├── 💻 code-executor → 编写 generate_xxx.py
    └── 💻 code-executor → 编写 deliver_xxx.py

④ 执行生成 (run_code / delegate_task)
    └── 运行脚本 → 输出 .pptx/.docx/.xlsx 文件

⑤ 📂 交付
    └── 汇报文件路径、大小、页数给老大
```

## 依赖库映射

| 文档类型 | Python库 | pip安装源 |
|:---------|:---------|:----------|
| 📊 PPT (.pptx) | `python-pptx` | 清华源 |
| 📝 Word (.docx) | `python-docx` | 清华源 |
| 📗 Excel (.xlsx) | `openpyxl` | 清华源 |

## 调用示例

```
老大：「贾维斯，把我之前课表做成PPT」
J.V: 查课表 → 提取内容 → 三Agent并行 → 交付robot_schedule.pptx

老大：「帮我把工业机器人的笔记整理成Word」
J.V: 查记忆 → 整理内容 → 三Agent并行 → 交付notes.docx
```

## 注意事项

- ⚡ 优先使用 `swarm_execute` 实现三Agent并行，而非串行 delegate_task
- 🚫 生成的是**真实文档文件**，不是HTML/网页，不要用 expose
- 📂 文件命名规则：`{内容关键词}_{类型}.{ext}`，如 `robot_overview.pptx`
- 🔧 pip安装统一用清华源：`-i https://pypi.tuna.tsinghua.edu.cn/simple`
- ✅ 脚本生成后先检查内容完整性，再执行生成
- 📏 PPT每页控制在5-8行要点，不要大段文字

## 执行代码

以下为配套的 Python 工具函数，注册为 `parallel_doc_generator` 工具：

```python
import os
import subprocess
import sys
from pathlib import Path

WORK_DIR = Path("D:/code/opencode/微信 AI 牛马管家")

def ensure_dependency(lib_name: str) -> bool:
    """检查并安装依赖库"""
    try:
        __import__(lib_name.replace('-', '_'))
        return True
    except ImportError:
        pip_cmd = f"{sys.executable} -m pip install {lib_name} -i https://pypi.tuna.tsinghua.edu.cn/simple"
        result = subprocess.run(pip_cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0

def get_doc_lib(doc_type: str) -> str:
    """根据文档类型返回对应的Python库名"""
    mapping = {
        'ppt': 'python-pptx',
        'pptx': 'python-pptx',
        'word': 'python-docx',
        'docx': 'python-docx',
        'excel': 'openpyxl',
        'xlsx': 'openpyxl',
    }
    return mapping.get(doc_type.lower(), 'python-pptx')

def generate_script_path(doc_type: str) -> Path:
    """生成脚本文件路径"""
    return WORK_DIR / f"generate_{doc_type.lower()}.py"
```

---

*此技能由 Harness 自进化引擎自动注册，基于 2026-05-05 PPT生成任务经验沉淀*
