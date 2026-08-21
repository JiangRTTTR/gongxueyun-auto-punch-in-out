import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone

from manager.ConfigManager import ConfigManager

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))

TYPE_LABELS = {
    "START": "上班",
    "END": "下班",
    "HOLIDAY": "休息/节假日",
}


def get_current_month_info() -> dict:
    """获取当前月份（CST）的开始和结束时间。"""
    now = datetime.now(CST)
    start_of_month = datetime(now.year, now.month, 1)
    if now.month == 12:
        next_month_start = datetime(now.year + 1, 1, 1)
    else:
        next_month_start = datetime(now.year, now.month + 1, 1)
    end_of_month = next_month_start - timedelta(days=1)
    return {
        "startTime": start_of_month.strftime("%Y-%m-%d %H:%M:%S"),
        "endTime": end_of_month.strftime("%Y-%m-%d 23:59:59"),
    }


def desensitize_name(name: str | None) -> str:
    if not name:
        return "***"
    name = str(name).strip()
    if not name:
        return "***"
    n = len(name)
    if n < 3:
        return f"{name[0]}*"
    return f"{name[0]}{'*' * (n - 2)}{name[-1]}"


def desensitize_phone(phone: str | None) -> str:
    if not phone:
        return "***"
    phone = str(phone).strip()
    n = len(phone)
    if n < 7:
        return phone[:1] + "*" * (n - 1) if n > 1 else "*"
    return f"{phone[:3]}{'*' * (n - 7)}{phone[-4:]}"


def desensitize_address(address: str | None) -> str:
    if not address:
        return ""
    address = str(address).strip()
    if not address:
        return address
    parts = address.split("·")
    if len(parts) >= 3:
        parts = parts[:2] + ["***"]
        return " · ".join(p.strip() for p in parts)
    return address[:3] + "***" if len(address) > 3 else "***"


def _parse_hhmm(value: str | None, default_hour: int, default_minute: int = 0) -> tuple[int, int]:
    if not value:
        return default_hour, default_minute
    text = str(value).strip().replace("：", ":")
    try:
        parts = text.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return max(0, min(23, hour)), max(0, min(59, minute))
    except (TypeError, ValueError):
        return default_hour, default_minute


def resolve_checkin_type() -> dict[str, str]:
    """
    本次只打一张卡。
    优先 CHECKIN_FORCE / --force；否则按 time.start~end 中点推断。
    默认时间：08:00 / 17:00。
    """
    force = (os.environ.get("CHECKIN_FORCE") or os.environ.get("CLOCK_TYPE") or "").strip().upper()
    if force in ("START", "MORNING"):
        return {"type": "START", "display": "上班"}
    if force in ("END", "EVENING"):
        return {"type": "END", "display": "下班"}
    if force in ("HOLIDAY",):
        return {"type": "HOLIDAY", "display": "休息/节假日"}

    start_h, start_m = _parse_hhmm(ConfigManager.get("clockIn", "time", "start"), 8, 0)
    end_h, end_m = _parse_hhmm(ConfigManager.get("clockIn", "time", "end"), 17, 0)
    now = datetime.now(CST)
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m
    now_minutes = now.hour * 60 + now.minute

    if end_minutes <= start_minutes:
        midpoint = (start_minutes + end_minutes + 24 * 60) // 2
        cmp = now_minutes if now_minutes >= start_minutes else now_minutes + 24 * 60
        check_type = "START" if cmp < midpoint else "END"
    else:
        midpoint = (start_minutes + end_minutes) // 2
        check_type = "START" if now_minutes < midpoint else "END"

    return {"type": check_type, "display": TYPE_LABELS[check_type]}


def get_checkin_type() -> dict[str, str]:
    """兼容旧调用名。"""
    return resolve_checkin_type()


def get_checkin_types() -> list[dict[str, str]]:
    """
    每天都打卡；每次进程只返回一张（上班或下班）。
    正式环境请用 cron 早 8 点 --force START、晚 17 点 --force END。
    """
    return [resolve_checkin_type()]


def current_force_label() -> str:
    force = (os.environ.get("CHECKIN_FORCE") or "").strip().upper()
    if force in ("START", "MORNING"):
        return "上班"
    if force in ("END", "EVENING"):
        return "下班"
    if force in ("HOLIDAY",):
        return "休息/节假日"
    t = resolve_checkin_type()
    return t.get("display") or "自动"


def apply_time_float_delay() -> None:
    """按 clockIn.time.float（分钟）随机延迟。可用 --no-float / NO_FLOAT=1 关闭。"""
    if os.environ.get("NO_FLOAT") == "1":
        logging.info("已禁用时间浮动延迟")
        return
    float_minutes = ConfigManager.get("clockIn", "time", "float", default=0) or 0
    try:
        float_minutes = float(float_minutes)
    except (TypeError, ValueError):
        float_minutes = 0
    if float_minutes <= 0:
        return
    delay = random.uniform(0, float_minutes * 60)
    logging.info(f"时间浮动延迟 {delay:.1f} 秒")
    time.sleep(delay)


def sleep_between_users(min_seconds: float = 5, max_seconds: float = 30) -> None:
    if os.environ.get("NO_FLOAT") == "1":
        return
    delay = random.uniform(min_seconds, max_seconds)
    logging.info(f"用户间隔等待 {delay:.1f} 秒")
    time.sleep(delay)
