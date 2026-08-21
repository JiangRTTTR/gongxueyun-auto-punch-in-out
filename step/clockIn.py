import logging
from datetime import datetime, timezone, timedelta

from manager.ConfigManager import ConfigManager
from manager.UserInfoManager import UserInfoManager
from util.ApiService import ApiService
from util.HelperFunctions import get_checkin_type, desensitize_name, desensitize_phone, desensitize_address

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))


def clock_in(force_type: dict[str, str] | None = None) -> dict[str, str]:
    """
    执行打卡。不发送单人邮件（由 main 汇总发送）。
    返回字段：title, content, status(成功|跳过|失败), ok(bool)
    """
    logging.info("执行签到打卡")
    current_time = datetime.now(CST)

    checkin = force_type or get_checkin_type()
    checkin_type = checkin.get("type")
    display_type = checkin.get("display") or checkin_type

    api_client = ApiService()
    checkin_list = api_client.get_checkin_info()
    if not isinstance(checkin_list, list):
        checkin_list = []

    for record in checkin_list:
        if not isinstance(record, dict):
            continue
        if record.get("type") != checkin_type:
            continue
        create_time = record.get("createTime")
        if not create_time:
            continue
        try:
            record_time = datetime.strptime(str(create_time), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning(f"无法解析打卡时间: {create_time}")
            continue
        if record_time.date() == current_time.date():
            log = f"今日[{display_type}]卡已打，无需重复打卡"
            logger.info(log)
            return {
                "title": "工学云签到任务通知",
                "content": log,
                "status": "跳过",
                "ok": True,
            }

    user_name = desensitize_name(UserInfoManager.get("nikeName"))
    logger.info(f"用户 {user_name} 开始 {display_type} 打卡")

    last_address = None
    if checkin_list and isinstance(checkin_list[0], dict):
        last_address = checkin_list[0].get("address")

    checkin_info = {
        "type": checkin_type,
        "lastDetailAddress": last_address,
        "attachments": None,
        "description": "",
    }

    success = api_client.submit_clock_in(checkin_info) or {
        "result": False,
        "message": "打卡接口无返回",
    }

    location = ConfigManager.get("clockIn", "location", "address") or ""
    location_masked = desensitize_address(location)

    if success.get("result"):
        msg = success.get("message") or "打卡成功"
        logger.info(msg)
        return {
            "title": "工学云签到成功通知",
            "content": msg,
            "status": "成功",
            "ok": True,
            "location": location_masked,
        }

    err = success.get("message") or "打卡失败"
    logger.warning(f"打卡失败：{err}")
    return {
        "title": "fail",
        "content": err,
        "status": "失败",
        "ok": False,
        "location": location_masked,
    }
