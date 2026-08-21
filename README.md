# 工学云自动打卡（服务器版）

每天都打卡：**早上上班、晚上下班**（两次运行、两封汇总邮件）。

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

```bash
cp user/config.example.json user/config.json
# 再编辑 user/config.json 填入真实账号
```

`user/config.json` 为多用户数组（可复制多份对象）。建议：

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
```

每跑完一轮只发 **一封汇总邮件**（含全部用户明细）。一天两次 = 两封（上班汇总 + 下班汇总）。

## cron（早 8 / 晚 17，每天）

```cron
0 8 * * *   cd /opt/gongxueyun && /opt/gongxueyun/.venv/bin/python main.py --no-wait --force START >> /opt/gongxueyun/cron.log 2>&1
0 17 * * *  cd /opt/gongxueyun && /opt/gongxueyun/.venv/bin/python main.py --no-wait --force END >> /opt/gongxueyun/cron.log 2>&1
```

## 许可证

MIT，见 [LICENSE](LICENSE)。接口说明见 [api.md](api.md)。
