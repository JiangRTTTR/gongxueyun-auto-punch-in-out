import logging
import smtplib
import time
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
    except Exception as e:
        logger.error(f"邮件构造失败: {e}")
        return False

    last_error = None
    for attempt in range(2):
        try:
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
            last_error = e
            if attempt == 0:
                logger.warning(f"邮件发送失败({e})，3 秒后重试")
                time.sleep(3)

    logger.error(f"邮件发送失败(已重试): {last_error}")
    return False



def send_run_summary(results: list[dict[str, Any]], checkin_label: str) -> bool:
    """
    成功/跳过轮次静默不发信；只有存在失败用户时才发告警。
    results 每项字段：index, phone, name, checkin_type, status, detail, location, ok
    status: 成功 / 跳过 / 失败
    """
    total = len(results)
    failed = [r for r in results if not r.get("ok")]
    if not failed:
        logger.info(f"本轮 {total}/{total} 全部到位，按静默策略不发送通知邮件")
        return False

    ok_count = total - len(failed)
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"工学云【{checkin_label}】打卡告警",
        f"时间：{now}",
        f"结果：{ok_count}/{total} 到位，失败 {len(failed)}",
        "",
        "---------- 失败明细 ----------",
    ]
    for r in failed:
        idx = r.get("index", "?")
        phone = r.get("phone", "***")
        name = r.get("name") or ""
        ctype = r.get("checkin_type") or checkin_label
        detail = (r.get("detail") or "").strip() or "无返回信息"
        location = r.get("location") or ""
        who = f"{phone}" + (f" ({name})" if name and name != "***" else "")
        lines.append(f"{idx}. {who}")
        lines.append(f"   类型：{ctype}")
        lines.append(f"   原因：{detail}")
        if location:
            lines.append(f"   地点：{location}")
        lines.append("")

    skipped = [r for r in results if r.get("status") == "跳过"]
    if skipped:
        lines.append(
            f"已到位（无需处理）：{', '.join(str(r.get('index')) for r in skipped)}"
        )

    content = "\n".join(lines).rstrip() + "\n"
    title = f"[失败{len(failed)}] 工学云{checkin_label} {ok_count}/{total}"

    # 使用第一个启用了 SMTP 的用户配置发送
    original = getattr(ConfigManager, "_current_user_index", 0)
    try:
        for i in range(ConfigManager.get_user_count()):
            ConfigManager.set_current_user(i)
            smtp = ConfigManager.get("smtp", default={}) or {}
            if smtp.get("enable"):
                return send_email_notification(title, content)
        logger.warning(f"没有任何用户启用 SMTP，告警邮件未发送：{content}")
        return False
    finally:
        ConfigManager.set_current_user(original)


def send_daily_report(rows: list[dict[str, Any]]) -> bool:
    """每日哨兵信：无论是否缺卡都发一封，用来证明 cron 和账号当天确实有动作。"""
    today = datetime.now(CST).strftime("%Y-%m-%d")
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

    def status_of(row: dict, ctype: str) -> str:
        if row.get("error"):
            return "查询失败"
        value = (row.get("records") or {}).get(ctype)
        return value.split(" ")[-1][:8] if value else "缺"

    missing = [
        row
        for row in rows
        if row.get("error")
        or not (row.get("records") or {}).get("START")
        or not (row.get("records") or {}).get("END")
    ]
    if missing:
        conclusion = f"缺卡/异常：{len(missing)} 人（详见下方）"
        title = f"[缺卡{len(missing)}] 工学云{today}日报"
    else:
        conclusion = "全部到位"
        title = f"工学云{today}日报 全部到位"

    lines = [
        f"工学云打卡日报 {today}",
        f"时间：{now}",
        f"结论：{conclusion}",
        "",
        "---------- 明细（打卡时间） ----------",
    ]
    for row in rows:
        who = row.get("phone", "***") + (
            f" ({row['name']})" if row.get("name") and row["name"] != "***" else ""
        )
        lines.append(
            f"{row.get('index', '?')}. {who}"
            f"　上班 {status_of(row, 'START')}　下班 {status_of(row, 'END')}"
        )
        if row.get("error"):
            lines.append(f"   查询失败：{row['error']}")

    content = "\n".join(lines).rstrip() + "\n"

    original = getattr(ConfigManager, "_current_user_index", 0)
    try:
        for i in range(ConfigManager.get_user_count()):
            ConfigManager.set_current_user(i)
            smtp = ConfigManager.get("smtp", default={}) or {}
            if smtp.get("enable"):
                return send_email_notification(title, content)
        logger.warning(f"没有任何用户启用 SMTP，日报未发送：{content}")
        return False
    finally:
        ConfigManager.set_current_user(original)

