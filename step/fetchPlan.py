import logging

from util.ApiService import ApiService

logger = logging.getLogger(__name__)


def fetch_plan() -> bool:
    """
    每次从服务器拉取最新实习计划并写入 PlanInfoManager。
    避免本地缓存计划过期或换计划后仍用旧 planId。
    """
    logging.info("获取打卡计划信息")
    api_client = ApiService()
    success = api_client.fetch_plan()
    if success:
        logger.info("打卡信息获取成功")
    else:
        logger.warning("打卡信息获取失败")
    return success
