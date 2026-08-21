import logging

from manager.ConfigManager import ConfigManager
from manager.UserInfoManager import UserInfoManager
from util.ApiService import ApiService
from util.HelperFunctions import desensitize_phone

logger = logging.getLogger(__name__)


def login() -> bool:
    """
    登录流程：
    1. 本地 token 存在且手机号一致则跳过
    2. 否则调用 ApiService.login()
    """
    logging.info("检查登录状态")
    token = UserInfoManager.get_token()
    config_phone = ConfigManager.get("user", "phone") or ""
    cache_phone = UserInfoManager.get("phone") or ""
    is_same = desensitize_phone(config_phone) == desensitize_phone(cache_phone)

    if is_same and token:
        logger.info("检测到本地 token，跳过登录")
        return True

    if is_same:
        logger.info("未检测到 token，开始执行登录")
    else:
        logger.info("检测到用户信息不一致，执行重新登录")

    api_client = ApiService()
    success = api_client.login()
    if success:
        logger.info("登录成功")
    else:
        logger.warning("登录失败")
    return success
