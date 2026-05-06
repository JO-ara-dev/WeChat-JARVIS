"""
仪表盘日志桥接模块
- 线程安全的日志广播缓冲
- 供 FastAPI WebSocket 消费
- 供所有模块写入
"""

import logging
import datetime
import queue
import collections

MAX_BUFFER = 500
MAX_RECENT = 200

log_buffer = queue.Queue(maxsize=MAX_BUFFER)
_recent_logs = collections.deque(maxlen=MAX_RECENT)


def get_recent_logs():
    """返回最近 N 条日志供新 WebSocket 客户端追平"""
    return list(_recent_logs)


def drain_buffer():
    """非阻塞地取出缓冲中所有待发送日志条目。
    返回列表，可能为空。
    """
    entries = []
    while True:
        try:
            entry = log_buffer.get_nowait()
            entries.append(entry)
        except queue.Empty:
            break
    return entries


class BroadcastLogHandler(logging.Handler):
    """
    自定义日志 Handler：
    每当有日志记录产生，就 push 到全局 log_buffer，
    并追加到 _recent_logs 双端队列。
    """

    def emit(self, record):
        try:
            msg = self.format(record)
            safe_msg = msg.encode('utf-8', errors='ignore').decode('utf-8')
            entry = {
                "time": datetime.datetime.now().isoformat(timespec="seconds"),
                "level": record.levelname,
                "msg": safe_msg,
            }
            try:
                log_buffer.put_nowait(entry)
            except queue.Full:
                pass
            _recent_logs.append(entry)
        except Exception:
            pass


def install():
    """
    安装 BroadcastLogHandler 到根 Logger 和 'WCF' logger。
    在 butler_agent._init_modules() 中调用。
    """
    handler = BroadcastLogHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.addHandler(handler)

    wcf = logging.getLogger("WCF")
    wcf.addHandler(handler)

    logging.getLogger("dashboard").info("日志桥接已安装")
    return handler
