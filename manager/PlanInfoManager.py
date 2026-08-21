import json
import logging
from pathlib import Path
from typing import Any, Optional
import sys

logger = logging.getLogger(__name__)

# ======================
# 根目录 & planInfo 路径
# ======================
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

USER_DIR = BASE_DIR / "user"
USER_DIR.mkdir(parents=True, exist_ok=True)

PLAN_INFO_PATH = USER_DIR / "planInfo.json"


class PlanInfoManager:
    """
    管理 planInfo.json（多用户）：
    - 支持多用户数组格式，与 UserInfoManager / ConfigManager 按 index 对齐
    - 兼容旧版单用户 {"planInfo": {...}} 格式，读取时自动转为数组
    - 提供任意字段访问（大小写不敏感）
    """
    _planinfo_cache: list | dict | None = None
    _current_user_index: int = 0

    @classmethod
    def _lower_keys(cls, d: dict) -> dict:
        """递归将字典键转换为小写"""
        new_d = {}
        for k, v in d.items():
            if isinstance(v, dict):
                v = cls._lower_keys(v)
            new_d[k.lower()] = v
        return new_d

    @classmethod
    def _load_from_file(cls) -> Optional[list | dict]:
        if not PLAN_INFO_PATH.exists():
            logger.warning(f"planInfo.json 不存在: {PLAN_INFO_PATH.resolve()}")
            return None
        try:
            with open(PLAN_INFO_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "planInfo" in data:
                # 旧版单用户格式 → 转为数组，便于后续按 index 扩展
                return [data]
            logger.warning(f"planInfo.json 格式无法识别: {PLAN_INFO_PATH.resolve()}")
            return None
        except Exception as e:
            logger.error(f"读取 planInfo.json 失败: {e}")
            return None

    @classmethod
    def load(cls) -> Optional[list | dict]:
        """获取缓存中的全部 planInfo 数据，如果没有缓存则从文件加载"""
        if cls._planinfo_cache is not None:
            return cls._planinfo_cache
        cls._planinfo_cache = cls._load_from_file()
        return cls._planinfo_cache

    @classmethod
    def set_current_user(cls, index: int):
        """设置当前操作的用户索引"""
        cls._current_user_index = index

    @classmethod
    def get_current_user_planinfo(cls) -> Optional[dict]:
        """获取当前用户的 planInfo（键名已转小写）"""
        cache_data = cls.load()
        if not cache_data:
            return None
        if isinstance(cache_data, list):
            if 0 <= cls._current_user_index < len(cache_data):
                item = cache_data[cls._current_user_index]
                planinfo = item.get("planInfo") if isinstance(item, dict) else None
                if planinfo:
                    return cls._lower_keys(planinfo)
            return None
        if isinstance(cache_data, dict):
            planinfo = cache_data.get("planInfo")
            if planinfo:
                return cls._lower_keys(planinfo)
        return None

    @classmethod
    def set_planinfo(cls, planinfo: dict):
        """更新当前用户的 planInfo 并写回文件"""
        cache_data = cls.load()
        if cache_data is None:
            cache_data = []

        if isinstance(cache_data, list):
            while len(cache_data) <= cls._current_user_index:
                cache_data.append({})
            cache_data[cls._current_user_index] = {"planInfo": planinfo}
        else:
            cache_data = [{"planInfo": planinfo}]

        cls._planinfo_cache = cache_data
        try:
            PLAN_INFO_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(PLAN_INFO_PATH, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=4)
            logger.info(
                f"planInfo.json 已更新 (用户 {cls._current_user_index + 1}): "
                f"{PLAN_INFO_PATH.resolve()}"
            )
        except Exception as e:
            logger.error(f"写入 planInfo.json 失败: {e}")

    @classmethod
    def get(cls, *keys: str, default: Any = None) -> Any:
        """通用访问方法，大小写不敏感，仅读取当前用户 planInfo"""
        planinfo = cls.get_current_user_planinfo()
        if not planinfo:
            return default
        data = planinfo
        for key in keys:
            key_lower = key.lower()
            if isinstance(data, dict) and key_lower in data:
                data = data[key_lower]
            else:
                return default
        return data

    @classmethod
    def get_plan_id(cls) -> Optional[str]:
        """获取当前用户的 planId"""
        return cls.get("planId")
