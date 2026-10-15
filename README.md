# 工学云自动打卡（服务器版）

每天都打卡：**早上上班、晚上下班**（各带一次 +1h 补跑）。成功不发信，失败即时告警，每天一封日报。

## 目录

```
main.py / requirements.txt
manager/  step/  util/
user/config.json
models/ocr.onnx  models/yolov5n.onnx
```

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
timedatectl set-timezone Asia/Shanghai
```

## 配置

`user/config.json` 为多用户数组。建议：

```json
"clockIn": {
  "location": { "address": "...", "latitude": "...", "longitude": "...", "province": "...", "city": "...", "area": "..." },
  "time": { "start": "8:00", "end": "17:00", "float": 1 }
}
```

- 不再使用 `everyday` / `twice_daily` 等 mode；**每天都会打**
- 正式打卡类型由命令行 `--force` 决定
- `float`：随机延迟分钟数；试跑可加 `--no-float`

SMTP 配在任一用户下即可（多用户通常指向同一收件邮箱）。

## 运行

```bash
# 上班
python main.py --no-wait --force START

# 下班
python main.py --no-wait --force END

# 试跑（不随机睡）
python main.py --no-wait --no-float --force START

# 只核对当天上下班记录，不提交打卡
python main.py --no-wait --check
```

## 邮件策略

- 全部成功或跳过的一轮 **静默不发信**
- 任一用户失败 → **立即告警**，主题 `[失败n] 工学云上班 x/y`，正文含每个失败用户的异常原因摘要
- `--check` 每天发 **一封日报**（好坏都发），用于确认 cron 和账号当天确实有动作

## cron（早 8 上班 / 晚 17 下班，各 +1h 补跑，晚 19:30 日报）

补跑轮靠"今日已有记录则跳过"去重，已到位的用户只多三个查询请求、不碰验证码。

```cron
0 8  * * *  cd /opt/gongxueyun && /opt/gongxueyun/.venv/bin/python main.py --no-wait --force START >> /opt/gongxueyun/cron.log 2>&1
0 9  * * *  cd /opt/gongxueyun && /opt/gongxueyun/.venv/bin/python main.py --no-wait --force START >> /opt/gongxueyun/cron.log 2>&1
0 17 * * *  cd /opt/gongxueyun && /opt/gongxueyun/.venv/bin/python main.py --no-wait --force END   >> /opt/gongxueyun/cron.log 2>&1
0 18 * * *  cd /opt/gongxueyun && /opt/gongxueyun/.venv/bin/python main.py --no-wait --force END   >> /opt/gongxueyun/cron.log 2>&1
30 19 * * * cd /opt/gongxueyun && /opt/gongxueyun/.venv/bin/python main.py --no-wait --check       >> /opt/gongxueyun/cron.log 2>&1
```

## 许可证

MIT，见 [LICENSE](LICENSE)。接口说明见 [api.md](api.md)。
