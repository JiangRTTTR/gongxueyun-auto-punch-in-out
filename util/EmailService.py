import logging
import smtplib
from datetime import datetime, timezone, timedelta
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from manager.ConfigManager import ConfigManager

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))


def send_email_notification(title: str, content: str) -> bool:
    """使用当前 ConfigManager 用户下的 SMTP 配置发信。"""
    smtp_config = ConfigManager.get("smtp", default={}) or {}

    if not smtp_config.get("enable", False):
        logger.info("SMTP 未启用，跳过邮件发送")
        return False

    host = smtp_config.get("host")
    port = smtp_config.get("port", 465)
    username = smtp_config.get("username")
    password = smtp_config.get("password")
    from_name = smtp_config.get("from", "工学云打卡通知")
    to_list = smtp_config.get("to", [])

    if not host or not username or not password:
        logger.warning("SMTP 配置不完整，跳过邮件发送")
        return False

    if not to_list:
        logger.warning("未配置收件人邮箱，跳过邮件发送")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{from_name} <{username}>"
        msg["To"] = ", ".join(to_list)
        msg["Subject"] = Header(title, "utf-8")

        now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
        text_content = f"{content}\n\n发送时间：{now}\n"
        html_body = content.replace("\n", "<br>\n")
        html_content = f"""<!DOCTYPE html>
<html><body style="font-family: sans-serif; line-height: 1.5;">
<pre style="font-family: Consolas, monospace; white-space: pre-wrap;">{html_body}</pre>
<p style="color:#999;font-size:12px;">发送时间：{now}</p>
</body></html>"""

        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        if int(port) == 465:
            server = smtplib.SMTP_SSL(host, int(port), timeout=15)
        else:
            server = smtplib.SMTP(host, int(port), timeout=15)
            server.starttls()

        server.login(username, password)
        server.sendmail(username, to_list, msg.as_string())
        server.quit()

        logger.info(f"邮件发送成功，收件人: {to_list}")
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False


def send_run_summary(results: list[dict[str, Any]], checkin_label: str) -> bool:
    """
    本轮全部用户打卡汇总（一上或一下各发一封）。
    results 每项建议字段：
      index, phone, name, checkin_type, status, detail, location, ok
    status: 成功 / 跳过 / 失败
    """
    total = len(results)
    ok_count = sum(1 for r in results if r.get("ok"))
    fail_count = total - ok_count
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"工学云【{checkin_label}】打卡汇总",
        f"时间：{now}",
        f"结果：{ok_count}/{total} 成功" + (f"，失败 {fail_count}" if fail_count else ""),
        "",
        "---------- 明细 ----------",
    ]
    for r in results:
        idx = r.get("index", "?")
        phone = r.get("phone", "***")
        name = r.get("name") or ""
        ctype = r.get("checkin_type") or checkin_label
        status = r.get("status") or ("成功" if r.get("ok") else "失败")
        detail = (r.get("detail") or "").strip()
        location = r.get("location") or ""
        who = f"{phone}" + (f" ({name})" if name and name != "***" else "")
        lines.append(f"{idx}. {who}")
        lines.append(f"   类型：{ctype}　状态：{status}")
        if location:
            lines.append(f"   地点：{location}")
        if detail:
            lines.append(f"   说明：{detail}")
        lines.append("")

    content = "\n".join(lines).rstrip() + "\n"
    if fail_count:
        title = f"[失败{fail_count}] 工学云{checkin_label}汇总 {ok_count}/{total}"
    else:
        title = f"[{ok_count}/{total}] 工学云{checkin_label}汇总"

    # 使用第一个启用了 SMTP 的用户配置发送
    original = getattr(ConfigManager, "_current_user_index", 0)
    try:
        for i in range(ConfigManager.get_user_count()):
            ConfigManager.set_current_user(i)
            smtp = ConfigManager.get("smtp", default={}) or {}
            if smtp.get("enable"):
                return send_email_notification(title, content)
        logger.info("没有任何用户启用 SMTP，跳过汇总邮件")
        return False
    finally:
        ConfigManager.set_current_user(original)
