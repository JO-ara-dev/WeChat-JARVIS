"""
J.A.R.V.I.S Agent 配置管理器 (AgentManager)

提供集中化的 Agent 配置读写、API 客户端创建、提示词动态更新能力。
所有 Agent 配置存储在 agent_config.json 中，通过本类实现：

- 线程安全的文件读写（内存锁 + 文件锁双重保护）
- 三家 API 提供商（智谱/DeepSeek/阿里）的统一客户端创建
- 子 Agent 提示词动态更新并持久化（自进化核心能力）
- 主 Agent 和子 Agent 的统一查询接口

作者: J.A.R.V.I.S Team
"""

import json
import os
import threading
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from copy import deepcopy

logger = logging.getLogger("AgentManager")

# ── API Provider 元配置 ────────────────────────────────────────────
# 所有提供商的基础 URL 和 API Key 环境变量名在此集中定义。
# agent_config.json 中的 providers 段会继承这些默认值。
PROVIDER_META = {
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "api_key_env": "ZHIPU_API_KEY",
        "description": "智谱 GLM 系列 (BigModel.cn)",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "description": "DeepSeek 系列",
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "description": "阿里百炼 DashScope 系列",
    },
}


class AgentManager:
    """
    J.A.R.V.I.S 的 Agent 配置管理中枢。

    职责：
    1. 加载 / 持久化 agent_config.json
    2. 线程安全的配置读写（防止高并发群消息下的读写冲突）
    3. 从环境变量读取各提供商的 API Key，创建统一的 OpenAI 兼容客户端
    4. 提供 update_agent_prompt() 方法，支持管理员群指令动态修改 Agent 人格
    5. 原子写入：先写临时文件，成功后再 rename，防止写入中断导致配置文件损坏

    用法:
        manager = AgentManager("dorm_butler/agent_config.json")

        # 创建各提供商客户端
        zhipu_client = manager.create_client("zhipu")
        deepseek_client = manager.create_client("deepseek")

        # 查询 Agent 配置
        main = manager.get_main_agent()
        code_exec = manager.get_agent("code-executor")
        all_agents = manager.list_agents()

        # 自进化：修改子 Agent 提示词
        manager.update_agent_prompt(
            "vision-analyst",
            "你是图片识别专家，新增能力：支持识别手写数学公式..."
        )
    """

    # 类级别状态缓存，用于抑制重复的 __init__ 日志刷屏
    _last_logged_state = None

    # ────────────────────────────────────────────────────────────────
    # 构造与初始化
    # ────────────────────────────────────────────────────────────────

    def __init__(self, config_path: str):
        """
        初始化配置管理器，从 JSON 文件加载配置。

        Args:
            config_path: agent_config.json 的文件路径（相对或绝对路径均可）

        Raises:
            FileNotFoundError: 文件不存在且无法创建时（仅在极少数情况下）
        """
        self._config_path = Path(config_path)
        # 双重锁机制:
        #   _lock:       保护内存中的 _config 字典（读/写）
        #   _write_lock: 保护磁盘文件写入（防止并行 write 竞争）
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._config: Dict[str, Any] = {}
        self._load()
        agent_count = len(self._config.get("sub_agents", []))
        main_name = self._config.get("main_agent", {}).get("name", "未定义")
        current_state = (main_name, agent_count)
        if current_state != AgentManager._last_logged_state:
            logger.info(f"AgentManager 已加载 | 主Agent: {main_name} | 子Agent: {agent_count} 个")
            AgentManager._last_logged_state = current_state
        else:
            logger.debug(f"AgentManager 已加载 | 主Agent: {main_name} | 子Agent: {agent_count} 个 (状态未变化)")

    # ────────────────────────────────────────────────────────────────
    # 文件 I/O（线程安全 + 原子写入）
    # ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        """
        从 agent_config.json 加载配置到内存。

        容错设计:
        - 文件不存在 → 创建空配置并保存
        - JSON 解析失败 → 使用空配置，记录错误
        - 任何异常都不中断程序启动
        """
        with self._lock:
            default_config = {
                "providers": deepcopy(PROVIDER_META),
                "main_agent": {},
                "sub_agents": [],
                "defaults": {},
            }

            try:
                if not self._config_path.exists():
                    logger.warning(f"配置文件不存在: {self._config_path}，将创建默认配置")
                    self._config = default_config
                    self._save()
                    return

                with open(self._config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)

                # 合并：确保 providers 包含所有元配置中的字段
                providers = loaded.get("providers", {})
                for pname, pmeta in PROVIDER_META.items():
                    if pname not in providers:
                        providers[pname] = deepcopy(pmeta)
                    else:
                        # 用默认值补全缺失字段
                        for key, val in pmeta.items():
                            providers[pname].setdefault(key, val)
                loaded["providers"] = providers

                # 确保必要字段存在
                loaded.setdefault("main_agent", {})
                loaded.setdefault("sub_agents", [])
                loaded.setdefault("defaults", {})

                self._config = loaded

            except json.JSONDecodeError as e:
                logger.error(f"配置文件 JSON 解析失败: {e}，使用空配置 | 路径: {self._config_path}")
                self._config = default_config
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}，使用空配置 | 路径: {self._config_path}")
                self._config = default_config

    def _save(self) -> None:
        """
        将内存中的配置原子化持久化到磁盘。

        原子写入流程:
        1. 写入临时文件 agent_config.json.tmp
        2. 写入完成且校验通过 → 用 os.replace 原子替换原文件
        3. 如果写入中断 → 临时文件残留，原文件完好无损

        线程安全: 持有 _write_lock，保证同一时刻只有一个线程在写文件。
        """
        with self._write_lock:
            try:
                # 确保目录存在
                self._config_path.parent.mkdir(parents=True, exist_ok=True)

                tmp_path = self._config_path.with_suffix(".json.tmp")

                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._config, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())  # 确保写入到物理磁盘

                # 校验临时文件可读
                with open(tmp_path, "r", encoding="utf-8") as f:
                    json.load(f)  # 校验 JSON 合法性

                # 原子替换
                os.replace(tmp_path, self._config_path)
                logger.debug(f"配置已保存到 {self._config_path}")

            except json.JSONDecodeError:
                logger.error("配置写入校验失败，原文件未改动")
                if tmp_path.exists():
                    tmp_path.unlink()
                raise
            except Exception as e:
                logger.error(f"保存配置文件失败: {e}")
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
                raise

    # ────────────────────────────────────────────────────────────────
    # API Provider 操作
    # ────────────────────────────────────────────────────────────────

    def get_api_key(self, provider: str) -> str:
        """
        从环境变量读取指定提供商的 API Key。

        查找优先级:
        1. agent_config.json → providers.[provider].api_key_env → 环境变量名
        2. PROVIDER_META 元配置 → api_key_env → 环境变量名

        Args:
            provider: 提供商名称 ("zhipu" / "deepseek" / "dashscope")

        Returns:
            API Key 字符串，若未设置则返回 ""
        """
        env_var = (
            self._config.get("providers", {})
            .get(provider, {})
            .get("api_key_env", "")
        )
        if not env_var:
            env_var = PROVIDER_META.get(provider, {}).get("api_key_env", "")

        key = os.getenv(env_var, "")
        if not key:
            logger.warning(
                f"环境变量 {env_var} ({provider}) 未设置，"
                f"该提供商的 API 调用将失败"
            )
        return key

    def get_base_url(self, provider: str) -> str:
        """
        获取指定提供商的 API Base URL。

        Args:
            provider: 提供商名称

        Returns:
            Base URL 字符串（含末尾斜杠）
        """
        url = (
            self._config.get("providers", {})
            .get(provider, {})
            .get("base_url", "")
        )
        if not url:
            url = PROVIDER_META.get(provider, {}).get("base_url", "")
        return url

    def create_client(self, provider: str) -> "OpenAI":
        """
        根据提供商名称创建 OpenAI 兼容客户端。

        支持三家:
        - zhipu:    智谱 GLM (https://open.bigmodel.cn/api/paas/v4/)
        - deepseek: DeepSeek (https://api.deepseek.com/v1)
        - dashscope: 阿里百炼 (https://dashscope.aliyuncs.com/compatible-mode/v1)

        Args:
            provider: 提供商名称

        Returns:
            OpenAI 客户端实例

        Raises:
            ValueError: API Key 未设置
            ImportError: openai 包未安装
        """
        api_key = self.get_api_key(provider)
        if not api_key:
            env_var = PROVIDER_META[provider]["api_key_env"]
            raise ValueError(
                f"提供商 '{provider}' 的 API Key 未设置。"
                f"请在 .env 中设置 {env_var}=你的密钥"
            )

        base_url = self.get_base_url(provider)
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url=base_url)

    def create_client_for_agent(self, agent_name: str) -> "OpenAI":
        """
        根据 Agent 名称创建对应的 OpenAI 客户端。
        自动查找 Agent 的 provider 字段并创建客户端。

        Args:
            agent_name: Agent 名称

        Returns:
            OpenAI 客户端实例

        Raises:
            ValueError: Agent 不存在或 Provider 未知
        """
        agent = self.get_agent(agent_name)
        if not agent:
            raise ValueError(f"Agent '{agent_name}' 不存在")
        provider = agent.get("provider", "")
        if not provider:
            raise ValueError(f"Agent '{agent_name}' 未配置 provider")
        return self.create_client(provider)

    # ────────────────────────────────────────────────────────────────
    # Agent 查询接口
    # ────────────────────────────────────────────────────────────────

    def get_main_agent(self) -> Dict[str, Any]:
        """
        获取主 Agent (JARVIS大脑) 的完整配置。

        Returns:
            主 Agent 配置字典的深拷贝，修改不影响内存中的配置
        """
        with self._lock:
            return deepcopy(self._config.get("main_agent", {}))

    def get_sub_agents(self) -> List[Dict[str, Any]]:
        """
        获取所有子 Agent 的完整配置列表。

        Returns:
            子 Agent 配置列表的深拷贝
        """
        with self._lock:
            return deepcopy(self._config.get("sub_agents", []))

    def get_agent(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """
        按名称查找 Agent（先查主Agent，再查子Agent列表）。

        Args:
            agent_name: Agent 名称 (如 "code-executor")

        Returns:
            Agent 配置字典的深拷贝，未找到返回 None
        """
        with self._lock:
            main = self._config.get("main_agent", {})
            if main.get("name") == agent_name:
                return deepcopy(main)

            for agent in self._config.get("sub_agents", []):
                if agent.get("name") == agent_name:
                    return deepcopy(agent)

        return None

    def list_agents(self) -> List[Dict[str, str]]:
        """
        列出所有 Agent 的摘要信息（用于管理层监控和群指令展示）。

        Returns:
            [{
                "name": "code-executor",
                "model": "deepseek-v4-pro",
                "provider": "deepseek",
                "description": "代码编写与审查",
                "role": "sub",
                "max_turns": 8
            }, ...]
        """
        result = []
        with self._lock:
            main = self._config.get("main_agent", {})
            if main:
                result.append({
                    "name":       main.get("name", ""),
                    "model":      main.get("model", ""),
                    "provider":   main.get("provider", ""),
                    "description": main.get("description", ""),
                    "role":       "main",
                    "max_turns":  main.get("max_turns", 20),
                })

            for agent in self._config.get("sub_agents", []):
                result.append({
                    "name":        agent.get("name", ""),
                    "model":       agent.get("model", ""),
                    "provider":    agent.get("provider", ""),
                    "description": agent.get("description", ""),
                    "role":        "sub",
                    "max_turns":   agent.get("max_turns", 5),
                    "tools":       agent.get("tools", []),
                    "keywords":    agent.get("trigger_keywords", []),
                })
        return result

    def get_defaults(self) -> Dict[str, Any]:
        """获取默认配置（max_turns、review_model 等）。深拷贝返回。"""
        with self._lock:
            return deepcopy(self._config.get("defaults", {}))

    # ────────────────────────────────────────────────────────────────
    # 提示词自进化
    # ────────────────────────────────────────────────────────────────

    def update_agent_prompt(self, agent_name: str, new_prompt: str) -> bool:
        """
        动态更新指定 Agent 的 System Prompt，并持久化到配置文件。

        **这是 J.A.R.V.I.S 自进化能力的核心方法。**
        管理员在群内 @机器人 发送特殊管理指令（如 "更新 vision-analyst 的提示词"）时，
        主 Agent 识别意图后调用此方法，修改子 Agent 的人格/行为规则并永久保存。

        调用示例（群指令场景）:
            管理员: "@贾维斯 把 code-executor 的提示词改为：增加 Rust 语言支持，代码风格优先使用 Rust"
            → JARVIS大脑 解析意图 → manager.update_agent_prompt("code-executor", new_prompt)

        Args:
            agent_name: Agent 名称 (如 "vision-analyst"、"code-executor")
            new_prompt: 新的 System Prompt 完整文本

        Returns:
            True 表示更新成功并已持久化
            False 表示未找到该 Agent

        线程安全: 持有锁防止并发更新冲突。
        原子写入: 先写临时文件，成功后 os.replace，写入中断不损坏原文件。
        """
        found = False
        old_prompt = ""

        with self._lock:
            # 先查主Agent
            main = self._config.get("main_agent", {})
            if main.get("name") == agent_name:
                old_prompt = main.get("system_prompt", "")
                main["system_prompt"] = new_prompt
                found = True
            else:
                # 查子Agent列表
                for agent in self._config.get("sub_agents", []):
                    if agent.get("name") == agent_name:
                        old_prompt = agent.get("system_prompt", "")
                        agent["system_prompt"] = new_prompt
                        found = True
                        break

        if not found:
            logger.warning(f"update_agent_prompt: Agent '{agent_name}' 不存在")
            return False

        # 持久化到磁盘
        self._save()

        if old_prompt:
            logger.info(
                f"[自进化] Agent '{agent_name}' 提示词已更新\n"
                f"  旧版 ({len(old_prompt)} 字): {old_prompt[:80]}...\n"
                f"  新版 ({len(new_prompt)} 字): {new_prompt[:80]}..."
            )
        else:
            logger.info(
                f"[自进化] Agent '{agent_name}' 提示词已初始化 "
                f"({len(new_prompt)} 字): {new_prompt[:80]}..."
            )
        return True

    def update_agent_model(self, agent_name: str, new_model: str) -> bool:
        """
        动态切换 Agent 使用的模型（需要重启子Agent生效）。

        Args:
            agent_name: Agent 名称
            new_model:  新模型名 (如 "GLM-4-Plus")

        Returns:
            True 表示更新成功
        """
        found = False

        with self._lock:
            main = self._config.get("main_agent", {})
            if main.get("name") == agent_name:
                main["model"] = new_model
                found = True
            else:
                for agent in self._config.get("sub_agents", []):
                    if agent.get("name") == agent_name:
                        agent["model"] = new_model
                        found = True
                        break

        if not found:
            logger.warning(f"update_agent_model: Agent '{agent_name}' 不存在")
            return False

        self._save()
        logger.info(f"[自进化] Agent '{agent_name}' 模型切换为: {new_model}")
        return True

    def reload(self) -> None:
        """强制重新加载配置文件（用于外部修改配置后的热加载）。"""
        self._load()
        logger.info("AgentManager 已热加载配置")


# ═════════════════════════════════════════════════════════════════════
# 测试块 — 模拟群指令更新 Agent 提示词
# ═════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    模拟场景:
    管理员在群里说 "@贾维斯 更新 vision-analyst 的提示词，增加手写数学公式识别能力"
    → J.A.R.V.I.S 解析意图 → 调用 AgentManager.update_agent_prompt()
    → 提示词生效 → 持久化到 agent_config.json
    """

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    print("=" * 60)
    print("  J.A.R.V.I.S AgentManager 测试")
    print("  模拟群指令更新 Agent 提示词")
    print("=" * 60)

    # 1. 初始化管理器
    config_path = Path(__file__).parent / "agent_config.json"
    if not config_path.exists():
        print(f"\n[SKIP] 跳过测试：找不到配置文件 {config_path}")
        print("请先运行主程序生成配置，或手动创建 agent_config.json")
        exit(0)

    manager = AgentManager(str(config_path))
    print()

    # 2. 展示当前所有 Agent
    print("当前 Agent 矩阵:")
    print("-" * 60)
    for agent in manager.list_agents():
        role_tag = "[主]" if agent["role"] == "main" else "[子]"
        print(f"  {role_tag:6s} {agent['name']:18s} | {agent['model']:20s} | {agent['provider']:10s}")
        print(f"  {'':6s} {'':18s} | {'工具数: ' + str(len(agent.get('tools', []))):20s} | 轮次: {agent.get('max_turns', '?')}")
    print()

    # 3. 模拟群指令：更新 vision-analyst 的提示词
    new_prompt = """你是 vision-analyst，J.A.R.V.I.S 的视觉解析与 OCR 子Agent（已升级 v2）。

## 新增能力
- **手写数学公式识别**: 支持识别手写的数学/物理/化学公式，并转换为 LaTeX 格式
- **多页文档识别**: 支持一次分析多张连续图片，整合为一份文档
- **流程图识别**: 支持识别手绘流程图、思维导图，转换为 Mermaid 格式

## 保留能力
- 识别图片中的文字（OCR 提取）
- 解析课表截图，提取课程信息
- 解析任务/作业截图
- 识别手写笔记、表格

## 输出格式
- 公式: 使用 ```latex ... ``` 代码块
- 流程图: 使用 ```mermaid ... ``` 代码块"""

    print(f"模拟群指令: @贾维斯 更新 vision-analyst 的提示词，增加手写公式和流程图识别能力")
    print("-" * 60)

    # 更新前的提示词
    before = manager.get_agent("vision-analyst")
    print(f"\n[更新前] 提示词长度: {len(before['system_prompt'])} 字")
    print(f"  首行: {before['system_prompt'].split(chr(10))[0]}")

    # 执行更新
    success = manager.update_agent_prompt("vision-analyst", new_prompt)
    print(f"\n[更新结果] {'[OK]' if success else '[FAIL]'}")

    # 更新后的提示词
    after = manager.get_agent("vision-analyst")
    print(f"\n[更新后] 提示词长度: {len(after['system_prompt'])} 字")
    print(f"  首行: {after['system_prompt'].split(chr(10))[0]}")

    # 4. 验证持久化：重新加载后提示词仍然存在
    print("\n" + "=" * 60)
    print("  验证持久化：重新加载配置文件")
    print("=" * 60)
    manager.reload()
    reloaded = manager.get_agent("vision-analyst")
    persisted = reloaded["system_prompt"] == new_prompt
    print(f"\n[持久化] {'[OK] 已持久化到文件' if persisted else '[FAIL] 持久化失败'}")

    print("\n" + "=" * 60)
    print("  测试完成！")
    print("=" * 60)
    print(f"\n配置文件位置: {config_path}")
