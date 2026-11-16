# menkyo-checker

警視庁「学科試験」预约网站的空位检查脚本。**只检查并提醒，不会自动预约。**

- 每约 10 分钟由 GitHub Actions 运行一次，检查 府中・鮫洲・江東 三个考场
- 出现新的空位、或新月份的名额公开时，自动在本仓库新建一个 Issue 并 @ 仓库主人，GitHub App 会推送通知
- 收到提醒后，自己到[预约网站](https://license-test.tokyo-madoguchi-yoyaku.com/police-pref-tokyo/index.html)手动预约

## 设置

不需要额外设置，推送到 main 后定时任务自动运行。可选项：

- Settings → Secrets and variables → Actions → **Secrets** 里加 `NTFY_TOPIC`，可同时通过 [ntfy](https://ntfy.sh) App 推送
- 同一页面的 **Variables** 里加 `COURSE_CODE`：`61` = 要マイナ免許証（默认），`11` = 只要普通免許証

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
