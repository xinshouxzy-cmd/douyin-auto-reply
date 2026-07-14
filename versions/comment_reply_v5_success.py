# -*- coding: utf-8 -*-
"""
抖音评论自动回复 v5
+ 筛选「未回复」
+ 修复输入框定位（只回复指定评论的输入框，不碰顶部全局输入框）
+ 测试回复 = 当前时间
"""
import os, time, threading
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(BASE_DIR, "browser_data")
CREATOR_COMMENT = "https://creator.douyin.com/creator-micro/interactive/comment"
POLL = 15

os.makedirs(PROFILES_DIR, exist_ok=True)


def open_browser(name):
    builtin = os.path.join(BASE_DIR, "ms-playwright")
    if os.path.exists(builtin):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = builtin
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    profile = os.path.join(PROFILES_DIR, name)
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=profile, headless=False, no_viewport=True,
        args=["--disable-blink-features=AutomationControlled"]
    )
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return p, ctx, page


REPLIES = [
    {"keywords": ["贷款", "借钱", "怎么贷", "额度", "利息", "利率"],
     "reply": "您好！如需咨询贷款业务，请私信留下联系方式和所在区域，我们安排客户经理与您对接~"},
    {"keywords": ["社保", "医保", "社保卡", "养老"],
     "reply": "您好！社保卡业务可携带身份证到遵义农商银行任一网点办理~"},
    {"keywords": ["地址", "在哪", "位置", "网点"],
     "reply": "您好！遵义农商银行网点覆盖播州区、新蒲新区、汇川区，可就近选择~"},
    {"keywords": ["你好", "不错", "支持", "好的", "感谢", "谢谢"],
     "reply": "感谢您的关注与支持！遵义农商银行，您身边的百姓银行 🏦"},
]
FALLBACK = "感谢您的关注！如有金融业务需求，欢迎私信咨询~"


def match_reply(text):
    t = text.lower()
    for rule in REPLIES:
        for kw in rule["keywords"]:
            if kw in t:
                return rule["reply"]
    return FALLBACK


class CommentReplyEngine:
    def __init__(self, account_name, log_cb):
        self.name = account_name
        self.log = log_cb

    def _go_to_comment_page(self):
        try:
            self.page.goto(CREATOR_COMMENT, timeout=30000)
        except:
            pass
        time.sleep(4)

    def _filter_unreplied(self):
        """点击「全部评论」→ 选择「未回复」"""
        # 点击「全部评论」下拉
        all_btn = self.page.locator('text=全部评论').first
        if all_btn.count():
            all_btn.click()
            time.sleep(1)
            # 在下拉菜单中点击「未回复」
            unreplied = self.page.locator('text=未回复').first
            if unreplied.count():
                unreplied.click()
                self.log(f"[{self.name}] ✅ 筛选：未回复")
                time.sleep(2)
        else:
            self.log(f"[{self.name}] ⚠️ 未找到「全部评论」按钮")

    def _scroll_load_all(self):
        for y in [500, 1000, 2000, 3000, 5000]:
            self.page.evaluate(f"window.scrollTo(0, {y})")
            time.sleep(0.5)

    def _get_comments(self):
        """只抓 container-sXKyMs"""
        return self.page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('[class*="container-sXKyMs"]').forEach((el, i) => {
                const text = el.textContent.trim();
                const match = text.match(/^(.+?)\\d{2}月\\d{2}日/);
                const user = match ? match[1].trim() : '';
                results.push({index: i, text: text, user: user, id: 'cmt_' + user + '_' + i});
            });
            return results;
        }""")

    def _reply(self, comment_index, reply_text):
        """回复：只操作指定评论容器内的元素"""
        containers = self.page.locator('[class*="container-sXKyMs"]')
        if comment_index >= containers.count():
            return False

        container = containers.nth(comment_index)

        # 1. 点击该评论内的「回复」按钮
        reply_btn = container.locator('text=回复').last
        if not reply_btn.count():
            return False
        reply_btn.scroll_into_view_if_needed()
        reply_btn.click()
        time.sleep(1.5)

        # 2. 在该评论容器内找弹出的回复输入框（排除顶部的全局输入框）
        #    回复输入框通常出现在 container 内部或紧挨容器之后
        input_box = container.locator(
            'textarea, [contenteditable="true"], [class*="input-"], [class*="reply-text"]'
        ).first
        if not input_box.count():
            # 回退：在整个页面找，但排除顶部那个
            all_inputs = self.page.locator(
                'textarea, [contenteditable="true"], [class*="input-"]'
            )
            for i in range(all_inputs.count()):
                inp = all_inputs.nth(i)
                # 跳过顶部搜索框（placeholder含"搜索"）
                placeholder = inp.get_attribute("placeholder") or ""
                if "搜索" in placeholder:
                    continue
                # 跳过顶部的全局评论框
                box = inp.bounding_box()
                if box and box["y"] < 100:
                    continue
                input_box = inp
                break

        if input_box.count():
            input_box.click()
            time.sleep(0.3)
            input_box.fill(reply_text)
            time.sleep(0.5)

            # 3. 点发送 — 找 enabled 的
            send_btn = self.page.locator('text=发送').last
            if send_btn.count():
                send_btn.click(force=True)
                return True
        return False

    def run_loop(self, stop_event, login_event):
        p, ctx, page = open_browser(f"profile_{self.name}")
        self.p = p
        self.ctx = ctx
        self.page = page

        page.goto("https://creator.douyin.com", timeout=60000)
        self.log(f"[{self.name}] 请扫码登录 → 手动点到「评论管理」→ 回车确认")

        while not login_event.is_set() and not stop_event.is_set():
            time.sleep(0.5)
        if stop_event.is_set():
            return

        self.log(f"[{self.name}] ✅ 开始监控")

        while not stop_event.is_set():
            try:
                self._go_to_comment_page()
                self._filter_unreplied()
                self._scroll_load_all()

                comments = self._get_comments()
                self.log(f"[{self.name}] 📋 {len(comments)} 条评论（未回复）")

                for cmt in comments:
                    if stop_event.is_set():
                        break
                    user = cmt["user"]
                    preview = cmt["text"][:50]

                    if user != "相信自己xlpp":
                        self.log(f"[{self.name}] 👤 {user}: {preview}... ⏭")
                        continue

                    # 测试回复 = 当前时间
                    now = datetime.now().strftime("%H:%M")
                    reply_text = now
                    self.log(f"[{self.name}] 🎯 {user}: {preview}... → 回复「{reply_text}」")

                    ok = self._reply(cmt["index"], reply_text)
                    if ok:
                        self.log(f"[{self.name}] ✅ 发送成功")
                    else:
                        self.log(f"[{self.name}] ⚠️ 发送失败")

                time.sleep(POLL)
            except Exception as e:
                self.log(f"[{self.name}] 异常: {e}")
                time.sleep(POLL)

        try:
            ctx.close()
            p.stop()
        except:
            pass


def test_single_account(account_name="测试账号"):
    stop_flag = threading.Event()
    login_flag = threading.Event()

    def _log(msg):
        print(msg)

    engine = CommentReplyEngine(account_name, _log)
    t = threading.Thread(target=engine.run_loop, args=(stop_flag, login_flag), daemon=True)
    t.start()

    print("\n请扫码登录 → 手动点到「评论管理」→ 回车确认")
    input()
    login_flag.set()
    print("\n监控中... Ctrl+C 停止")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_flag.set()
        time.sleep(3)
        print("已停止")


if __name__ == "__main__":
    print("=" * 50)
    print("  抖音评论自动回复 v5")
    print("  测试: 只回「相信自己xlpp」，内容=当前时间")
    print("=" * 50)
    test_single_account("测试账号")
