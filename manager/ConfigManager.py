import json
import logging
from pathlib import Path
from typing import Any, Optional
import sys

logger = logging.getLogger(__name__)

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

USER_DIR = BASE_DIR / "user"
USER_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = USER_DIR / "config.json"


class ConfigManager:
    """管理 config.json，支持多用户数组与单用户对象。"""

    _config_cache: list | dict | None = None
    _current_user_index: int = 0

    @classmethod
    def _load_from_file(cls) -> Optional[list | dict]:
        if not CONFIG_PATH.exists():
            logger.warning(f"config.json 不存在: {CONFIG_PATH.resolve()}")
            return None
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            return [data]
        except Exception as e:
            logger.error(f"读取 config.json 失败: {e}")
            return None

    @classmethod
    def load(cls) -> Optional[list | dict]:
        if cls._config_cache is not None:
            return cls._config_cache
        cls._config_cache = cls._load_from_file()
        return cls._config_cache

    @classmethod
    def reload(cls) -> Optional[list | dict]:
        """强制从文件重新加载（供 action.py 写入配置后调用）。"""
        cls._config_cache = None
        return cls.load()

    @classmethod
    def get_user_count(cls) -> int:
        config_data = cls.load()
        if not config_data:
            return 0
        if isinstance(config_data, list):
            return len(config_data)
        return 1

    @classmethod
    def set_current_user(cls, index: int):
        cls._current_user_index = index

    @classmethod
    def get_current_user_config(cls) -> Optional[dict]:
        config_data = cls.load()
        if not config_data:
            return None
        if isinstance(config_data, list):
            if 0 <= cls._current_user_index < len(config_data):
                user_config = config_data[cls._current_user_index]
                return user_config.get("config") if isinstance(user_config, dict) else None
            return None
        return config_data.get("config") if isinstance(config_data, dict) else None

    @classmethod
    def get(cls, *keys: str, default: Any = None) -> Any:
        config_data = cls.get_current_user_config()
        if not config_data:
            return default
        data = config_data
        for key in keys:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                return default
        return data

    @classmethod
    def set(cls, keys: list[str], value: Any):
        config_data = cls.load()
        if not config_data:
            return

        if isinstance(config_data, list):
            if 0 <= cls._current_user_index < len(config_data):
                user_config = config_data[cls._current_user_index]
                if "config" not in user_config or not isinstance(user_config["config"], dict):
                    user_config["config"] = {}
                data = user_config["config"]
            else:
                return
        else:
            if "config" not in config_data or not isinstance(config_data["config"], dict):
                config_data["config"] = {}
            data = config_data["config"]

        for key in keys[:-1]:
            if key not in data or not isinstance(data[key], dict):
                data[key] = {}
            data = data[key]
        data[keys[-1]] = value
        cls._config_cache = config_data
        cls._write_back()

    @classmethod
    def _write_back(cls):
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cls._config_cache, f, ensure_ascii=False, indent=4)
            logger.info(f"config.json 已更新: {CONFIG_PATH.resolve()}")
        except Exception as e:
            logger.error(f"写入 config.json 失败: {e}")
