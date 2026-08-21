import argparse
import logging
import os
import sys
import traceback
from datetime import datetime, timezone, timedelta

from manager.ConfigManager import ConfigManager
from step.clockIn import clock_in
from step.fetchPlan import fetch_plan
from step.login import login
from manager.UserInfoManager import UserInfoManager
from manager.PlanInfoManager import PlanInfoManager
from util.EmailService import send_run_summary
from util.HelperFunctions import (
    get_checkin_types,
    desensitize_phone,
    desensitize_name,
    desensitize_address,
    apply_time_float_delay,
    sleep_between_users,
    current_force_label,
)

CST = timezone(timedelta(hours=8))


class CSTFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ct = datetime.fromtimestamp(record.created, tz=CST)
        if datefmt:
            return ct.strftime(datefmt)
        return ct.strftime("%Y-%m-%d %H:%M:%S") + f",{int(ct.microsecond / 1000):03d}"


def setup_logging():
    log_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "main.log")
    formatter = CSTFormatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])
    else:
        root.setLevel(logging.INFO)


def _wait_exit(no_wait: bool):
    if no_wait or os.environ.get("NO_WAIT") == "1" or not sys.stdin.isatty():
        return
    try:
        input("按回车键退出...")
    except EOFError:
        pass


def execute_tasks_for_user(user_index: int) -> dict:
    """处理单个用户，返回汇总用结果字典。"""
    phone = "未知"
    phone_masked = "***"
    try:
        ConfigManager.set_current_user(user_index)
        UserInfoManager.set_current_user(user_index)
        PlanInfoManager.set_current_user(user_index)

        phone = ConfigManager.get("user", "phone", default="未知") or "未知"
        phone_masked = desensitize_phone(phone)
        location = desensitize_address(
            ConfigManager.get("clockIn", "location", "address") or ""
        )
        logging.info(f"========== 开始处理用户 {user_index + 1}: {phone_masked} ==========")

        base = {
            "index": user_index + 1,
            "phone": phone_masked,
            "name": "",
            "location": location,
            "checkin_type": current_force_label(),
        }

        if not login():
            logging.warning(f"用户 {phone_masked} 登录失败")
            return {**base, "status": "失败", "detail": "登录失败", "ok": False}

        logging.info(f"用户类型：{UserInfoManager.get('roleKey')}")
        base["name"] = desensitize_name(UserInfoManager.get("nikeName"))

        if UserInfoManager.get("userType") != "student":
            logging.error(f"用户 {phone_masked} 不是学生，跳过打卡")
            return {**base, "status": "失败", "detail": "非学生账号", "ok": False}

        if not fetch_plan():
            logging.warning(f"用户 {phone_masked} 未获取到打卡信息")
            return {**base, "status": "失败", "detail": "获取实习计划失败", "ok": False}

        checkin_types = get_checkin_types()
        apply_time_float_delay()

        logging.info(
            f"本次打卡类型：{[c.get('display') for c in checkin_types]}"
        )

        # 每次只应有一张
        last_result = None
        all_ok = True
        for checkin in checkin_types:
            last_result = clock_in(force_type=checkin)
            logging.info(last_result)
            if not (last_result or {}).get("ok", False):
                all_ok = False

        status = (last_result or {}).get("status") or ("成功" if all_ok else "失败")
        detail = (last_result or {}).get("content") or ""
        ctype = checkin_types[0].get("display") if checkin_types else base["checkin_type"]
        loc = (last_result or {}).get("location") or location

        logging.info(f"用户 {phone_masked} 打卡任务完成，状态={status}")
        return {
            **base,
            "checkin_type": ctype,
            "status": status,
            "detail": detail,
            "location": loc,
            "ok": all_ok,
        }

    except Exception:
        logging.error(f"用户 {phone_masked} 执行打卡任务时发生异常")
        logging.error(traceback.format_exc())
        return {
            "index": user_index + 1,
            "phone": phone_masked,
            "name": "",
            "checkin_type": current_force_label(),
            "status": "失败",
            "detail": "程序异常，详见日志",
            "location": "",
            "ok": False,
        }


def execute_tasks(no_wait: bool = False) -> int:
    setup_logging()
    try:
        label = current_force_label()
        logging.info(f"开始执行打卡任务（本轮：{label}）")

        user_count = ConfigManager.get_user_count()
        if user_count == 0:
            logging.error("未找到任何用户配置")
            _wait_exit(no_wait)
            return 1

        logging.info(f"共检测到 {user_count} 个用户配置")

        results = []
        for i in range(user_count):
            if i > 0:
                sleep_between_users()
            results.append(execute_tasks_for_user(i))

        success_count = sum(1 for r in results if r.get("ok"))
        logging.info(
            f"========== 所有用户处理完成: {success_count}/{user_count} 成功 =========="
        )
        send_run_summary(results, label)
        _wait_exit(no_wait)
        return 0 if success_count == user_count else 1

    except Exception:
        logging.error("执行打卡任务时发生异常")
        logging.error(traceback.format_exc())
        _wait_exit(no_wait)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="工学云自动打卡：每天上下班各跑一次，每次只打一张卡"
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="结束后不等待回车（cron/服务器用）",
    )
    parser.add_argument(
        "--no-float",
        action="store_true",
        help="禁用时间浮动与用户间隔（试跑用）",
    )
    parser.add_argument(
        "--force",
        choices=["START", "END", "HOLIDAY", "MORNING", "EVENING"],
        help="强制打卡类型：上班 START / 下班 END（推荐 cron 使用）",
    )
    args = parser.parse_args(argv)
    if args.force:
        os.environ["CHECKIN_FORCE"] = args.force
    if args.no_float:
        os.environ["NO_FLOAT"] = "1"
    no_wait = args.no_wait or os.environ.get("NO_WAIT") == "1"
    return execute_tasks(no_wait=no_wait)


if __name__ == "__main__":
    sys.exit(main())
