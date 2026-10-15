import logging
from datetime import datetime, timezone, timedelta

from manager.ConfigManager import ConfigManager
from manager.UserInfoManager import UserInfoManager
from util.ApiService import ApiService
from util.HelperFunctions import brief_error, desensitize_name, desensitize_phone

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))

CHECK_TYPES = ("START", "END")


def check_today() -> dict:
    """
    只读查询：当天是否已有上班/下班记录。不调用提交、不碰验证码。
    返回 {index, phone, name, records: {START: time|None, END: ...}, error}
    """
    phone = ConfigManager.get("user", "phone") or "未知"
    row = {
        "index": ConfigManager.get_current_user_index() + 1,
        "phone": desensitize_phone(phone),
        "name": desensitize_name(UserInfoManager.get("nikeName")),
        "records": {t: None for t in CHECK_TYPES},
        "error": "",
    }

    try:
        records = ApiService().get_checkin_info()
    except Exception as e:
        row["error"] = brief_error(e)
        logger.warning(f"用户 {row['phone']} 今日记录查询失败: {row['error']}")
        return row

    if not isinstance(records, list):
        row["error"] = "接口未返回列表"
        return row

    today = datetime.now(CST).date()
    for record in records:
        if not isinstance(record, dict):
            continue
        ctype = record.get("type")
        if ctype not in CHECK_TYPES:
            continue
        create_time = record.get("createTime")
        if not create_time:
            continue
        try:
            record_time = datetime.strptime(str(create_time), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if record_time.date() != today:
            continue
        current = row["records"][ctype]
        if current is None or str(create_time) < current:
            row["records"][ctype] = str(create_time)

    return row
