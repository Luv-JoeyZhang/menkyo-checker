# menkyo-checker

警視庁「学科試験」预约网站的空位检查脚本。**只检查并提醒，不会自动预约。**

- 每约 10 分钟在 GitHub Actions 上运行一次，检查 府中・鮫洲・江東 三个考场
- 出现新的空位、或新月份的名额公开时，通过 [ntfy](https://ntfy.sh) 推送到手机
- 收到提醒后，自己到[预约网站](https://license-test.tokyo-madoguchi-yoyaku.com/police-pref-tokyo/index.html)手动预约

## 设置

- Settings → Secrets and variables → Actions → **Secrets**：`NTFY_TOPIC` = ntfy App 里订阅的主题名（必填，否则没有提醒）
- 同一页面的 **Variables**（可选）：`COURSE_CODE`，`61` = 要マイナ免許証（默认），`11` = 只要普通免許証
- GitHub 自带的定时不准，实际由外部定时服务（cron-job.org）每 10 分钟调用 `workflow_dispatch` 触发
- 改动 `.github/test-notify` 文件并推送 = 发一条测试提醒

日期范围、排除日期等其他设置在 `menkyo_checker.py` 开头修改。

## 本地运行

```
python3 menkyo_checker.py --test   # 测试通知
python3 menkyo_checker.py --once   # 检查一次
python3 menkyo_checker.py          # 持续运行
```

## 注意

- 检查间隔请不要低于 5 分钟，避免给预约网站造成负担
- 预约每人限 1 件；拿到驾照后请在 Actions 页面停用这个 workflow
