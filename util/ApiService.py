import json
import logging
import random
import re
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import requests

from manager.ConfigManager import ConfigManager
from manager.PlanInfoManager import PlanInfoManager
from manager.UserInfoManager import UserInfoManager
from util.CaptchaUtils import recognize_blockPuzzle_captcha, recognize_clickWord_captcha
from util.CryptoUtils import create_sign, aes_encrypt, aes_decrypt
from util.HelperFunctions import get_current_month_info

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))

BASE_URL = "https://api.moguding.net:9000/"
HEADERS = {
    "user-agent": "Dart/2.17 (dart:io)",
    "content-type": "application/json; charset=utf-8",
    "accept-encoding": "gzip",
    "host": "api.moguding.net:9000",
}


class ApiService:
    def __init__(self):
        self.max_retries = 5

    def _post_request(
        self,
        url: str,
        headers: Dict[str, str],
        data: Dict[str, Any],
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        try:
            response = requests.post(
                f"{BASE_URL}{url}",
                headers=headers,
                json=data,
                timeout=15,
            )
            response.raise_for_status()
            rsp = response.json()

            if rsp.get("code") == 200 and rsp.get("msg") == "302":
                return rsp

            if rsp.get("code") in (200, 6111):
                return rsp

            msg = rsp.get("msg", "未知错误")
            if "token失效" in str(msg) and retry_count < self.max_retries:
                wait_time = 1 * (2 ** retry_count)
                time.sleep(wait_time)
                logger.warning("Token失效，正在重新登录...")
                if self.login():
                    headers["authorization"] = UserInfoManager.get_token()
                    logger.info("已更新 Authorization Token，重试请求")
                    return self._post_request(url, headers, data, retry_count + 1)

            logger.info(f"服务端返回详情: code={rsp.get('code')}, msg={msg}")
            raise ValueError(msg)

        except (requests.RequestException, ValueError) as e:
            # 含中文的业务错误（含 IP 频繁）不再盲目重试
            if re.search(r"[\u4e00-\u9fff]", str(e)) or retry_count >= self.max_retries:
                raise ValueError(str(e)) from e

            wait_time = 1 * (2 ** retry_count)
            logger.warning(
                f"重试 {retry_count + 1}/{self.max_retries}，等待 {wait_time:.2f} 秒"
            )
            time.sleep(wait_time)

        return self._post_request(url, headers, data, retry_count + 1)

    def pass_blockPuzzle_captcha(self, max_attempts: int = 5) -> str:
        attempts = 0
        while attempts < max_attempts:
            captcha_url = "session/captcha/v1/get"
            request_data = {
                "clientUid": str(uuid.uuid4()).replace("-", ""),
                "captchaType": "blockPuzzle",
            }
            captcha_info = self._post_request(captcha_url, HEADERS, request_data)
            slider_data = recognize_blockPuzzle_captcha(
                captcha_info["data"]["jigsawImageBase64"],
                captcha_info["data"]["originalImageBase64"],
            )
            check_slider_data = {
                "pointJson": aes_encrypt(
                    slider_data, captcha_info["data"]["secretKey"], "b64"
                ),
                "token": captcha_info["data"]["token"],
                "captchaType": "blockPuzzle",
            }
            check_result = self._post_request(
                "session/captcha/v1/check", HEADERS, check_slider_data
            )
            if check_result.get("code") != 6111:
                return aes_encrypt(
                    captcha_info["data"]["token"] + "---" + slider_data,
                    captcha_info["data"]["secretKey"],
                    "b64",
                )
            attempts += 1
            time.sleep(random.uniform(1, 3))
        raise Exception("通过滑块验证码失败")

    def solve_click_word_captcha(self, max_retries: int = 2) -> dict:
        retry_count = 0
        while retry_count < max_retries:
            captcha_request_payload = {
                "clientUid": str(uuid.uuid4()).replace("-", ""),
                "captchaType": "clickWord",
            }
            captcha_response = self._post_request(
                "/attendence/clock/v1/get",
                self._get_authenticated_headers(),
                captcha_request_payload,
            )
            captcha_solution = recognize_clickWord_captcha(
                captcha_response["data"]["originalImageBase64"],
                captcha_response["data"]["wordList"],
            )
            verification_payload = {
                "pointJson": aes_encrypt(
                    captcha_solution,
                    captcha_response["data"]["secretKey"],
                    "b64",
                ),
                "token": captcha_response["data"]["token"],
                "captchaType": "clickWord",
            }
            try:
                verification_response = self._post_request(
                    "/attendence/clock/v1/check",
                    self._get_authenticated_headers(),
                    verification_payload,
                )
            except ValueError as e:
                logger.warning(
                    f"验证码校验请求失败 (第{retry_count + 1}次): {e}，重试中..."
                )
                retry_count += 1
                time.sleep(random.uniform(1, 3))
                continue

            if verification_response.get("code") == 200:
                encrypted_result = aes_encrypt(
                    captcha_response["data"]["token"] + "---" + captcha_solution,
                    captcha_response["data"]["secretKey"],
                    "b64",
                )
                return {
                    "captcha": encrypted_result,
                    "clientUid": captcha_request_payload["clientUid"],
                }

            logger.warning(
                f"验证码校验失败 (第{retry_count + 1}次): "
                f"code={verification_response.get('code')}, "
                f"msg={verification_response.get('msg')}"
            )
            logger.warning(f"目标文字: {captcha_response['data'].get('wordList')}")
            retry_count += 1
            time.sleep(random.uniform(1, 3))

        raise Exception(f"通过点选验证码失败 (已重试{max_retries}次)")

    def _get_authenticated_headers(
        self, sign_data: Optional[List[Optional[str]]] = None
    ) -> Dict[str, str]:
        headers = {
            **HEADERS,
            "authorization": UserInfoManager.get_token(),
            "userid": UserInfoManager.get_userid(),
            "rolekey": UserInfoManager.get("roleKey"),
            "version": "5.31.6",
        }
        if sign_data:
            headers["sign"] = create_sign(*sign_data)
        return headers

    def login(self) -> bool:
        logger.info("执行登录")
        try:
            phone = ConfigManager.get("user", "phone")
            password = ConfigManager.get("user", "password")
            if not phone or not password:
                logger.error("登录失败：手机号或密码为空")
                return False

            data = {
                "phone": aes_encrypt(str(phone)),
                "password": aes_encrypt(str(password)),
                "captcha": self.pass_blockPuzzle_captcha(),
                "loginType": "android",
                "uuid": str(uuid.uuid4()).replace("-", ""),
                "device": "android",
                "version": "5.31.6",
                "t": aes_encrypt(str(int(time.time() * 1000))),
            }

            response = self._post_request("session/user/v6/login", HEADERS, data)
            encrypted_data = response.get("data")
            if not encrypted_data:
                logger.error("登录失败：返回数据为空")
                return False

            user_info = json.loads(aes_decrypt(encrypted_data))
            logger.info(
                f"登录成功 userId={user_info.get('userId')} "
                f"userType={user_info.get('userType')}"
            )
            UserInfoManager.set_userinfo(user_info)
            return True
        except Exception as e:
            logger.exception(f"登录过程发生异常：{e}")
            return False

    def fetch_plan(self) -> bool:
        try:
            data = {
                "pageSize": 999999,
                "t": aes_encrypt(str(int(time.time() * 1000))),
            }
            headers = self._get_authenticated_headers(
                sign_data=[
                    UserInfoManager.get_userid(),
                    UserInfoManager.get("roleKey"),
                ]
            )
            rsp = self._post_request("practice/plan/v3/getPlanByStu", headers, data)
            data_list = rsp.get("data")
            if not data_list or not isinstance(data_list, list):
                logger.warning("未获取到实习计划数据，rsp 内容: %s", rsp)
                return False

            plan_info = data_list[0]
            if not plan_info:
                logger.warning("实习计划数据为空")
                return False

            logger.info(
                "获取到实习计划 planId=%s postName=%s",
                plan_info.get("planId"),
                plan_info.get("postName"),
            )
            PlanInfoManager.set_planinfo(plan_info)
            return True
        except Exception as e:
            logger.exception("获取实习计划过程中发生异常: %s", e)
            return False

    def get_checkin_info(self) -> List[Dict[str, Any]]:
        url = "attendence/clock/v2/listSynchro"
        if UserInfoManager.get("userType") == "teacher":
            url = "attendence/clock/teacher/v1/listSynchro"
        headers = self._get_authenticated_headers()
        data = {
            **get_current_month_info(),
            "t": aes_encrypt(str(int(time.time() * 1000))),
        }
        rsp = self._post_request(url, headers, data)
        result = rsp.get("data") or []
        return result if isinstance(result, list) else []

    def submit_clock_in(self, checkin_info: Dict[str, Any]) -> dict:
        url = "attendence/clock/teacher/v2/save"
        sign_data = None
        plan_id = PlanInfoManager.get_plan_id()
        location = ConfigManager.get("clockIn", "location") or {}
        if not isinstance(location, dict):
            location = {}
        address = location.get("address") or ""
        device = ConfigManager.get("device") or ""

        if UserInfoManager.get("userType") != "teacher":
            url = "attendence/clock/v6/save"
            sign_data = [
                device,
                checkin_info.get("type"),
                plan_id,
                UserInfoManager.get_userid(),
                address,
            ]

        logger.info(f"打卡类型：{checkin_info.get('type')}")

        now_cst = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
        data = {
            "distance": None,
            "content": None,
            "lastAddress": None,
            "lastDetailAddress": checkin_info.get("lastDetailAddress"),
            "attendanceId": None,
            "country": "中国",
            "createBy": None,
            "createTime": now_cst,
            "description": checkin_info.get("description") or "",
            "device": device,
            "images": None,
            "isDeleted": None,
            "isReplace": None,
            "modifiedBy": None,
            "modifiedTime": None,
            "schoolId": None,
            "state": "NORMAL",
            "teacherId": None,
            "teacherNumber": None,
            "type": checkin_info.get("type"),
            "stuId": None,
            "planId": plan_id,
            "attendanceType": None,
            "username": None,
            "attachments": checkin_info.get("attachments"),
            "userId": UserInfoManager.get_userid(),
            "isSYN": None,
            "studentId": None,
            "applyState": None,
            "studentNumber": None,
            "memberNumber": None,
            "headImg": None,
            "attendenceTime": None,
            "depName": None,
            "majorName": None,
            "className": None,
            "logDtoList": None,
            "isBeyondFence": None,
            "practiceAddress": None,
            "tpJobId": None,
            "t": aes_encrypt(str(int(time.time() * 1000))),
            "version": "5.31.6",
        }
        data.update(location)

        headers = self._get_authenticated_headers(sign_data)
        responses = self._post_request(url, headers, data)

        if responses.get("msg") == "302":
            logger.info("检测到行为验证码，正在通过···")
            captcha_result = self.solve_click_word_captcha()
            data["captcha"] = captcha_result["captcha"]
            rsp = self._post_request(url, headers, data)
            logger.info(
                f"打卡接口返回(验证码后): code={rsp.get('code')}, msg={rsp.get('msg')}"
            )
            return self._check_clock_in_response(rsp)

        if responses.get("msg") == "304":
            return self._handle_verification(url, headers, data)

        logger.info(
            f"打卡接口返回: code={responses.get('code')}, msg={responses.get('msg')}"
        )
        return self._check_clock_in_response(responses)

    def _handle_verification(self, url, headers, data) -> dict:
        logger.warning("需要安全验证(304)，尝试点选验证码绕过...")
        result = self.solve_click_word_captcha()
        data.update({
            "appUuid": result["clientUid"],
            "captcha": result["captcha"],
        })
        rsp = self._post_request(url, headers, data)
        logger.info(f"验证处理后结果: code={rsp.get('code')}, msg={rsp.get('msg')}")
        return self._check_clock_in_response(rsp)

    def _check_clock_in_response(self, rsp: Dict[str, Any]) -> dict:
        code = rsp.get("code")
        msg = rsp.get("msg")
        data = rsp.get("data")

        if code == 6111:
            return {
                "result": False,
                "data": rsp,
                "message": str(msg) if msg else "验证码校验失败",
            }

        if code != 200:
            return {
                "result": False,
                "data": rsp,
                "message": str(msg) if msg else "打卡失败",
            }

        if msg == "success":
            return {"result": True, "data": rsp}

        if msg == "304":
            return {
                "result": False,
                "data": rsp,
                "message": "打卡失败(304)：需要安全认证",
            }

        if msg == "302":
            return {
                "result": False,
                "data": rsp,
                "message": "打卡失败(302)：仍需行为验证码",
            }

        if data is None:
            logger.warning(f"打卡接口返回 data 为空，msg={msg}")
            return {
                "result": False,
                "data": rsp,
                "message": f"打卡失败：服务器未返回打卡数据(msg={msg})",
            }

        return {"result": True, "data": rsp}
