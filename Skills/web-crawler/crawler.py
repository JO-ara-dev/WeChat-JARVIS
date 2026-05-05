"""
教务网爬虫模块 - 使用 Playwright + 系统 Edge 浏览器
流程：启动 Edge -> 手动登录 -> 自动检测课表页 -> 等待用户确认 -> 抓取 HTML -> 解析课表 -> 入库
"""

import asyncio
import os
import re
from typing import Optional
from playwright.async_api import async_playwright, Page, BrowserContext
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import db_manager

load_dotenv()
LOGIN_URL = os.getenv("CRAWLER_LOGIN_URL", "")
SCHEDULE_URL_PATTERN = "Schedule/Query/Default.aspx"

# 节次映射：行ID -> (起始节次, 结束节次)
ROW_TO_NODES = {
    "TableRow2": (1, 2),
    "TableRow3": (3, 4),
    "TableRow4": (5, 6),
    "TableRow5": (7, 8),
    "TableRow6": (9, 10),
}

# 单元格在行内的索引（0=节次标题列，1-5=周一到周五）
COL_INDEX_TO_WEEKDAY = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}

# 正则：匹配 A/B 开头的房间号，如 A1N409, B301, A4S502, A2-307
RE_LOCATION = re.compile(r"[AB]\d[A-Za-z\-]?\d*", re.IGNORECASE)

# 正则：匹配周次，如 "2-11周" "2,4-11周" "14周(单)"
RE_WEEKS = re.compile(r"(\d+(?:[-,]\d+)*)\s*周")

# 正则：实践环节 第X周 或 第X-Y周
RE_PRACTICE_WEEKS = re.compile(r"第(\d+(?:-\d+)?)周")

# 正则：实践环节双引号内的课程名
RE_PRACTICE_NAME = re.compile(r'[\u201c"\u300c]([^\u201d"\u300d]+)[\u201d"\u300d]')


async def wait_for_login_and_get_schedule() -> str:
    """
    主流程：
    1. 启动 Edge 浏览器（有头模式）
    2. 打开登录页，等待用户手动登录
    3. 监听新标签页，检测课表页面
    4. 等待用户确认后，抓取 HTML 并返回
    """
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                channel="msedge",
                headless=False,
            )
            context: BrowserContext = await browser.new_context()
            page: Page = await context.new_page()

            # 跳转到登录页
            await page.goto(LOGIN_URL)
            print("[crawler] 已打开登录页，请在浏览器中手动登录...")
            print(f"[crawler] 登录地址: {LOGIN_URL}")
            print("[crawler] 登录完成后，请在教务系统中点击进入【课表查询】页面")

            # 监听新标签页
            schedule_page: Page | None = None

            async def on_new_page(new_page: Page):
                nonlocal schedule_page
                try:
                    await new_page.wait_for_load_state("domcontentloaded", timeout=10000)
                    url = new_page.url
                    print(f"[crawler] 检测到新标签页: {url}")
                    if SCHEDULE_URL_PATTERN in url:
                        schedule_page = new_page
                        print("[crawler] 已锁定课表页面！")
                except Exception as e:
                    print(f"[crawler] 标签页监听异常: {e}")

            context.on("page", on_new_page)

            # 轮询等待课表页出现
            print("[crawler] 等待课表页面加载中...")
            while schedule_page is None:
                for pg in context.pages:
                    if SCHEDULE_URL_PATTERN in pg.url:
                        schedule_page = pg
                        print("[crawler] 已在已有标签页中发现课表页面！")
                        break
                if schedule_page is None:
                    await asyncio.sleep(1)

            # 等待用户手动筛选
            print()
            print("=" * 50)
            print("[牛马管家] 老板，请在浏览器里选好学期、班级")
            print("          并点【查看课表】，确认课表显示出来后，")
            print("          请回到这里按回车键，小的再开始干活！")
            print("=" * 50)
            print()
            input(">>> 按回车键开始抓取课表...")

            # 等待课表页完全加载
            await schedule_page.wait_for_load_state("networkidle", timeout=30000)
            print("[crawler] 课表页面加载完成")

            # 抓取 HTML
            html = await schedule_page.content()
            print(f"[crawler] HTML 抓取成功，长度: {len(html)} 字符")

            return html

    except Exception as e:
        print(f"[crawler] 爬虫异常: {e}")
        raise
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass


def _parse_cell(text: str, week_day: int, start_node: int, end_node: int) -> list[dict]:
    """
    解析一个单元格的文本，返回课程字典列表。
    
    教务网单元格格式（用 | 分隔）：
      课程名  地点  校区|教师  班级  周次
    如果同一节有多门课（如不同周），会重复上面的模式：
      课程1  地点  校区|教师1  班级  周次|课程2  地点  校区|教师2  班级  周次
    """
    text = text.replace("\xa0", " ").replace("\u00a0", " ").strip()
    if not text:
        return []

    segments = [s.strip() for s in text.split("|") if s.strip()]
    if not segments:
        return []

    courses = []
    i = 0
    while i < len(segments):
        seg = segments[i]

        # 跳过纯班级号段
        if re.match(r"^[\d,\-\s]+$", seg):
            i += 1
            continue

        # ── 提取课程名和地点 ──
        name = seg
        location = ""

        # 提取地点
        loc_match = RE_LOCATION.search(name)
        if loc_match:
            location = loc_match.group(0)
            name = name[:loc_match.start()] + name[loc_match.end():]

        # 去掉末尾的校区标识
        name = re.sub(r"(校区)\s*$", "", name).strip()
        # 去掉特殊符号 ㊣
        name = re.sub(r"^[㊣]", "", name)
        # 去掉括号
        name = re.sub(r"[\[\]【】()（）]", "", name).strip()

        if not name:
            i += 1
            continue

        # ── 下一段应该是 教师  班级  周次 ──
        teacher = ""
        weeks = ""
        if i + 1 < len(segments):
            next_seg = segments[i + 1]
            # 如果下一段不是新课程（不含地点且不含课程特征），就是教师段
            if not RE_LOCATION.search(next_seg):
                # 这是教师段：教师名  班级号  周次
                parts_in_teacher = next_seg.split()
                if parts_in_teacher:
                    candidate = parts_in_teacher[0]
                    # 如果第一个词是班级号（8位数字开头），不是教师
                    if re.match(r"^\d{8,}", candidate):
                        teacher = ""
                    else:
                        teacher = candidate
                    # 从剩余部分找周次
                    for p in parts_in_teacher:
                        wm = RE_WEEKS.search(p)
                        if wm:
                            weeks = wm.group(1)
                            break
                i += 1

        # 如果还没找到周次，继续往后找
        if not weeks and i + 1 < len(segments):
            for j in range(i + 1, min(i + 3, len(segments))):
                wm = RE_WEEKS.search(segments[j])
                if wm:
                    weeks = wm.group(1)
                    break

        courses.append({
            "name": name,
            "location": location,
            "teacher": teacher,
            "weeks": weeks,
            "week_day": week_day,
            "start_node": start_node,
            "end_node": end_node,
        })

        i += 1

    return courses


def parse_schedule(html_content: str) -> tuple[list[dict], Optional[str]]:
    """
    解析课表 HTML，返回 (课程列表, 实践环节文本)。
    """
    soup = BeautifulSoup(html_content, "lxml")
    table = soup.find("table", id="TabSchedule")
    if not table:
        print("[crawler] 未找到 table#TabSchedule")
        return [], None

    courses: list[dict] = []

    for row_id, (start_node, end_node) in ROW_TO_NODES.items():
        row = table.find(id=row_id)
        if not row:
            print(f"[调试] {row_id} 未找到，跳过")
            continue

        # 按位置取单元格（跳过第0列的节次标题）
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        for col_idx, week_day in COL_INDEX_TO_WEEKDAY.items():
            if col_idx >= len(cells):
                continue

            cell = cells[col_idx]
            raw_text = cell.get_text(separator="|", strip=True)
            raw_text = raw_text.replace("\xa0", " ").replace("\u00a0", " ")

            if not raw_text.strip():
                continue

            print(f"[调试] 周{week_day} 第{start_node}-{end_node}节 原始: {raw_text[:120]}")

            parsed = _parse_cell(raw_text, week_day, start_node, end_node)
            for c in parsed:
                print(f"[调试]   -> {c['name']} | 地点:{c['location']} | {c['weeks']}周 | 老师:{c['teacher']}")
                courses.append(c)

    # ── 实践环节解析（仅终端展示，不入库）──
    practice_info = None
    lab_span = soup.find("span", id="Lab_Sjhj")
    if lab_span:
        practice_text = lab_span.get_text(strip=True)
        if practice_text:
            practice_info = practice_text

            segments = [s.strip() for s in practice_text.split(";") if s.strip()]

            print()
            print("【待处理实践环节】")
            for seg in segments:
                weeks_match = RE_PRACTICE_WEEKS.search(seg)
                weeks_val = weeks_match.group(1) if weeks_match else ""

                name_match = RE_PRACTICE_NAME.search(seg)
                name_val = name_match.group(1).strip() if name_match else ""

                loc_match = RE_LOCATION.search(seg)
                location_val = loc_match.group(0) if loc_match else ""

                if name_val:
                    print(f"  - {name_val}  |  {weeks_val}周  |  地点:{location_val or '见备注'}")
            print()
            print("[牛马管家] 老板，这些实践课时间太乱，小的没敢乱记，您回头受累自己对一下。")
            print()

    print(f"[crawler] 解析完成，共 {len(courses)} 门课程（不含实践环节）")
    return courses, practice_info


def save_courses_to_db(courses: list[dict]) -> int:
    """
    将课程列表写入数据库，返回写入数量。
    写入前先清空旧数据，避免重复。
    """
    conn = db_manager.get_conn()
    conn.execute("DELETE FROM courses")
    conn.commit()
    conn.close()

    count = 0
    for c in courses:
        try:
            db_manager.add_course(
                name=c["name"],
                week_day=c["week_day"],
                start_node=c["start_node"],
                end_node=c["end_node"],
                location=c["location"],
                weeks=c["weeks"],
            )
            count += 1
        except Exception as e:
            print(f"[crawler] 写入课程失败: {c} -> {e}")

    return count


async def fetch_schedule_html() -> str:
    """对外接口：启动爬虫获取课表 HTML"""
    return await wait_for_login_and_get_schedule()


if __name__ == "__main__":
    db_manager.init_db()

    html = asyncio.run(fetch_schedule_html())

    with open("data/schedule_raw.html", "w", encoding="utf-8") as f:
        f.write(html)

    courses, practice = parse_schedule(html)

    count = save_courses_to_db(courses)

    print()
    print("=" * 50)
    print("[牛马管家] 老板，小的已经把教务网翻了个底朝天，")
    print(f"          一共为您抢救回了 [{count}] 门课的信息！")
    print("          已经全存进库里了，您受累过目。")
    print("=" * 50)
