#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
警視庁 学科試験 予約空き枠チェッカー（只检查、不预约）

读取预约网站「空き状況カレンダー」所用的同一个公开接口，
发现空位时通过桌面通知 / 手机推送(ntfy) 提醒你，然后你自己去网站手动预约。

用法:
    python3 menkyo_checker.py           # 持续运行，每隔 INTERVAL_MIN 分钟检查一次
    python3 menkyo_checker.py --once    # 只检查一次
    python3 menkyo_checker.py --test    # 发一条测试通知，确认通知能收到

只用 Python 标准库，无需安装任何东西。
"""

import datetime as dt
import json
import os
import platform
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ========================= 设置（按需修改） =========================

# 考场: 270=府中, 280=鮫洲, 250=江東（江東仅限教習所卒業等、技能・取得時講習免除的人）
PLACES = {"270": "府中", "280": "鮫洲", "250": "江東"}

# 受験区分（预约网站第一步里选的那个）:
#   "11" = 教習所卒業等 + 只要普通的免許証
#   "61" = 教習所卒業等 + 要マイナ免許証（マイナ単独 或 两张都要）
# 两种的名额是分开显示的，请选自己实际要办的那种。
COURSE_CODE = os.environ.get("COURSE_CODE") or "11"

# 只关心这个日期范围内的空位（None = 不限制）。格式 "2026-12-25"
EARLIEST_DATE = None
LATEST_DATE = None

# 不能去的日子，例如 ["2026-12-03", "2026-12-10"]
EXCLUDE_DATES = []

# 往后查几个月（含本月）。教習所卒業的预约窗口约 90 天，4 足够
MONTHS_AHEAD = 4

# 检查间隔（分钟）。请不要调到 5 以下，避免给网站造成负担
INTERVAL_MIN = 10

# 手机推送（可选）: 在手机装 ntfy App，订阅一个只有你知道的主题名，
# 然后把同一个名字填在这里，例如 "joey-menkyo-8f3k2x"。留空则只有电脑通知。
NTFY_TOPIC = os.environ.get("NTFY_TOPIC") or ""

# ====================================================================

API_URL = os.environ.get(
    "MENKYO_API_URL",
    "https://license-test-tokyo-prd-police-pref-api.tokyo-madoguchi-yoyaku.com/calgetres",
)
BOOKING_URL = "https://license-test.tokyo-madoguchi-yoyaku.com/police-pref-tokyo/index.html"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
STATE_FILE = os.environ.get("MENKYO_STATE_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "menkyo_state.json"
)
MIN_INTERVAL_MIN = 5


def log(msg):
    print(f"[{dt.datetime.now():%m-%d %H:%M:%S}] {msg}", flush=True)


def months_to_check():
    today = dt.date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(MONTHS_AHEAD):
        out.append(f"{y}{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def fetch_month(yyyymm, place_code):
    """返回 {date(YYYYMMDD): 剩余名额}。与网站日历页的请求相同。"""
    query = urllib.parse.urlencode(
        {"date": yyyymm, "coursecode": COURSE_CODE, "placecode": place_code, "user": "pub"}
    )
    req = urllib.request.Request(
        f"{API_URL}?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != "A0001":
        raise RuntimeError(f"接口返回异常 code={data.get('code')!r}")
    remain = {}
    for item in data.get("body") or []:
        date = str(item.get("date", ""))
        try:
            left = int(item.get("capacity", 0)) - int(item.get("reservation", 0))
        except (TypeError, ValueError):
            continue
        remain[date] = remain.get(date, 0) + max(left, 0)
    return remain


def parse_date(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").date() if s else None


def wanted(date_str):
    try:
        d = dt.datetime.strptime(date_str, "%Y%m%d").date()
    except ValueError:
        return False
    if d <= dt.date.today():
        return False
    lo, hi = parse_date(EARLIEST_DATE), parse_date(LATEST_DATE)
    if lo and d < lo:
        return False
    if hi and d > hi:
        return False
    return d.isoformat() not in EXCLUDE_DATES


def check_all():
    """返回 (空位字典 {"府中 2026-12-03(木)": 剩余}, 出错数, 已公开的最晚日期)。"""
    openings, errors, latest_published = {}, 0, ""
    weekdays = "月火水木金土日"
    for yyyymm in months_to_check():
        for code, name in PLACES.items():
            try:
                remain = fetch_month(yyyymm, code)
            except Exception as e:  # 网络错误等：记下来，下一轮再试
                errors += 1
                log(f"  ! {name} {yyyymm} 获取失败: {e}")
                remain = {}
            for date_str, left in remain.items():
                latest_published = max(latest_published, date_str)
                if left > 0 and wanted(date_str):
                    d = dt.datetime.strptime(date_str, "%Y%m%d").date()
                    key = f"{name} {d.isoformat()}({weekdays[d.weekday()]})"
                    openings[key] = left
            time.sleep(1.5)  # 请求之间留间隔，别给网站添负担
    return openings, errors, latest_published


def notify(title, message):
    log(f"🔔 {title}: {message}")
    system = platform.system()
    try:
        if system == "Darwin":
            script = (
                f"display notification {json.dumps(message, ensure_ascii=False)} "
                f"with title {json.dumps(title, ensure_ascii=False)} sound name \"Glass\""
            )
            subprocess.run(["osascript", "-e", script], check=False, timeout=15)
        elif system == "Windows":
            import winsound

            for _ in range(3):
                winsound.Beep(1200, 400)
        else:
            sys.stdout.write("\a")
    except Exception as e:
        log(f"  ! 桌面通知失败: {e}")
    if NTFY_TOPIC:
        try:
            req = urllib.request.Request(
                f"https://ntfy.sh/{urllib.parse.quote(NTFY_TOPIC)}",
                data=message.encode("utf-8"),
                headers={
                    "Title": urllib.parse.quote(title),
                    "Priority": "high",
                    "Click": BOOKING_URL,
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=20).close()
        except Exception as e:
            log(f"  ! 手机推送失败: {e}")


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
    except OSError as e:
        log(f"  ! 状态保存失败: {e}")


def run_once(state):
    openings, errors, latest = check_all()
    prev = state.get("openings", {})
    new = {k: v for k, v in openings.items() if k not in prev}

    if openings:
        log("当前空位: " + " / ".join(f"{k} 剩{v}" for k, v in sorted(openings.items())))
    else:
        log(f"暂无空位（出错 {errors} 次，已公开到 {latest or '不明'}）")

    if new:
        lines = [f"{k} 剩{v}名" for k, v in sorted(new.items())]
        notify("学科試験 有空位了！", "、".join(lines[:6]) + (" 等" if len(lines) > 6 else ""))
        log(f"  → 请尽快手动预约: {BOOKING_URL}")

    # 有新月份的名额公开时也提醒一次（例如 1 月的名额开放）
    prev_latest = state.get("latest_published", "")
    if latest and prev_latest and latest[:6] > prev_latest[:6]:
        notify("学科試験 新月份名额已公开", f"{latest[:4]}年{int(latest[4:6])}月的名额开放了，快去看看")

    # 接口全部失败时保留上一次的状态，避免恢复后把旧空位当成新空位重复提醒
    if errors == 0 or openings:
        state["openings"] = openings
    if latest:
        state["latest_published"] = max(latest, prev_latest)

    # 连续全部失败时提醒一次（--once 模式下靠状态文件跨次计数，供云端定时运行使用）
    total = len(PLACES) * MONTHS_AHEAD
    streak = state.get("fail_streak", 0) + 1 if errors >= total else 0
    state["fail_streak"] = streak
    if streak == 6:
        notify("学科試験チェッカー", "连续多次无法获取数据，网站可能在维护或接口有变化，请看一下")
    save_state(state)
    return errors


def main():
    if "--test" in sys.argv:
        notify("学科試験チェッカー 测试", "如果你看到/听到这条，说明通知正常 ✅")
        return
    interval = max(INTERVAL_MIN, MIN_INTERVAL_MIN)
    state = load_state()
    if not NTFY_TOPIC and os.environ.get("GITHUB_ACTIONS"):
        log("⚠️ 没有设置 NTFY_TOPIC，发现空位也无法推送到手机")
    log(
        f"开始检查: 考场={'・'.join(PLACES.values())} 区分={COURSE_CODE} "
        f"间隔={interval}分钟 (Ctrl+C 停止)"
    )
    fail_streak = 0
    while True:
        try:
            errors = run_once(state)
        except Exception as e:
            errors = 1
            log(f"  ! 本轮检查异常: {e}")
        total = len(PLACES) * MONTHS_AHEAD
        if "--once" in sys.argv:
            # MENKYO_STRICT=1 时，全部请求失败则以错误码退出（手动试运行时方便看出问题）
            if errors >= total and os.environ.get("MENKYO_STRICT") == "1":
                sys.exit(1)
            return
        fail_streak = fail_streak + 1 if errors >= total else 0
        # 连续失败时拉长间隔，正常时加一点随机抖动
        wait = interval * 60 * (3 if fail_streak >= 3 else 1) + random.randint(0, 60)
        time.sleep(wait)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止。")
