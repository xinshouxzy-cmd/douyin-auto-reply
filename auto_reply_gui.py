# -*- coding: utf-8 -*-
"""
抖音多账号私信自动回复
==========================
Playwright 内置浏览器，解压即用，无需安装任何东西
"""

import os
import sys
import json
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
PROFILES_DIR = os.path.join(BASE_DIR, "browser_data")

os.makedirs(PROFILES_DIR, exist_ok=True)

DOUYIN_IM = "https://www.douyin.com/messages"
POLL = 8
stopped = threading.Event()


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"accounts": [{"name": "账号1", "reply_text": "您好！感谢关注遵义农商银行，您的消息已收到~", "enabled": True}]}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def open_browser(name, log):
    # 优先使用内置浏览器
    builtin = os.path.join(BASE_DIR, "ms-playwright")
    if os.path.exists(builtin):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = builtin
    
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    
    profile = os.path.join(PROFILES_DIR, name)
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=profile,
        headless=False,
        no_viewport=True,
        args=[
            "--disable-blink-features=AutomationControlled",
        ]
    )
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return p, ctx, page


def worker(acc, log, done_cb, login_event):
    name = acc["name"]
    reply = acc.get("reply_text", "").strip()
    if not reply:
        log(f"[{name}] 未设置回复内容")
        done_cb(name, "no_reply")
        return

    log(f"[{name}] 打开浏览器窗口...")
    try:
        p, ctx, page = open_browser(f"profile_{name}", log)
    except Exception as e:
        log(f"[{name}] ❌ 失败: {e}")
        done_cb(name, "failed")
        return

    try:
        page.goto("https://www.douyin.com", wait_until="domcontentloaded", timeout=60000)
        log(f"[{name}] 请在浏览器窗口扫码登录，登录成功后点「确认已登录」按钮")

        # 等待用户手动确认登录
        while not login_event.is_set() and not stopped.is_set():
            time.sleep(0.5)
        
        if stopped.is_set():
            log(f"[{name}] 已取消")
            return

        if not logged:
            log(f"[{name}] 登录超时")
            done_cb(name, "timeout")
            return

        page.goto(DOUYIN_IM, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        done_cb(name, "ok")
        log(f"[{name}] ✅ 登录成功，监控中")

        while not stopped.is_set():
            try:
                if "messages" not in (page.url or ""):
                    page.goto(DOUYIN_IM, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(2)

                has_new = page.evaluate("""() => {
                    for (let el of document.querySelectorAll('[class*="conversation"], [class*="session"]')) {
                        let b = el.querySelector('sup, [class*="badge"], [class*="unread"], [class*="count"]');
                        if (b) { let t = b.textContent.trim(); if (t && /\\d/.test(t)) return true; }
                    }
                    return false;
                }""")

                if has_new:
                    page.evaluate("""() => {
                        for (let el of document.querySelectorAll('[class*="conversation"], [class*="session"]')) {
                            let b = el.querySelector('sup, [class*="badge"], [class*="unread"], [class*="count"]');
                            if (b) { let t = b.textContent.trim(); if (t && /\\d/.test(t)) { el.click(); return; } }
                        }
                    }""")
                    time.sleep(3)
                    page.keyboard.type(reply)
                    time.sleep(0.5)
                    page.keyboard.press("Enter")
                    log(f"[{name}] 📤 已自动回复")

                time.sleep(POLL)
            except Exception as e:
                time.sleep(POLL)

    except Exception as e:
        log(f"[{name}] 异常: {e}")
    finally:
        try:
            ctx.close()
            p.stop()
        except:
            pass
        log(f"[{name}] 已停止")


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("抖音多账号自动回复 - 遵义农商银行")
        self.root.geometry("650x660")

        tk.Frame(self.root, bg="#c41230", height=44).pack(fill=tk.X)
        tk.Label(self.root, text="抖音多账号私信自动回复", fg="white", bg="#c41230",
                 font=("微软雅黑", 15, "bold")).pack(pady=8)

        self.keys = tk.Frame(self.root)
        self.keys.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.rows = []

        bf = tk.Frame(self.root)
        bf.pack(fill=tk.X, padx=10, pady=(0, 6))
        tk.Button(bf, text="+ 添加账号", command=self.add, width=11, font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text="💾 保存", command=self.save, bg="#4CAF50", fg="white", width=11, font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text="▶ 全部登录", command=self.start, bg="#c41230", fg="white", width=11, font=("微软雅黑", 10, "bold")).pack(side=tk.RIGHT, padx=4)
        tk.Button(bf, text="⏹ 停 止", command=self.stop_all, bg="#666", fg="white", width=11, font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=4)

        lf = tk.LabelFrame(self.root, text="运行日志", font=("微软雅黑", 9))
        lf.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.logbox = scrolledtext.ScrolledText(lf, height=8, font=("Consolas", 9))
        self.logbox.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.log("✅ 就绪 — 填写回复内容后点「全部登录」")
        self.log("内置浏览器引擎，无需安装 Chrome 或任何其他软件")

        self.cfg = load_config()
        self.refresh()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

    def log(self, msg):
        self.logbox.insert(tk.END, f"{msg}\n")
        self.logbox.see(tk.END)

    def refresh(self):
        for r in self.rows:
            r["frame"].destroy()
        self.rows.clear()
        for i, a in enumerate(self.cfg.get("accounts", [])):
            self._row(i, a)

    def     _row(self, i, a):
        f = tk.Frame(self.keys, bd=1, relief=tk.GROOVE)
        f.pack(fill=tk.X, padx=4, pady=2)

        r1 = tk.Frame(f)
        r1.pack(fill=tk.X, padx=8, pady=(6, 2))
        nv = tk.StringVar(value=a.get("name", ""))
        tk.Entry(r1, textvariable=nv, width=14, font=("微软雅黑", 10, "bold")).pack(side=tk.LEFT)
        sv = tk.StringVar(value="⚪ 未启动")
        tk.Label(r1, textvariable=sv, font=("微软雅黑", 9), fg="gray", width=14).pack(side=tk.LEFT, padx=6)
        ev = tk.BooleanVar(value=a.get("enabled", True))
        tk.Checkbutton(r1, text="启用", variable=ev).pack(side=tk.LEFT, padx=2)
        tk.Button(r1, text="🗑", command=lambda ii=i: self.rm(ii), fg="red", bd=0, width=3).pack(side=tk.RIGHT)
        tk.Button(r1, text="确认已登录", command=lambda ii=i: self.confirm_login(ii),
                  bg="#25f4ee", fg="#000", font=("微软雅黑", 8)).pack(side=tk.RIGHT, padx=4)

        r2 = tk.Frame(f)
        r2.pack(fill=tk.X, padx=8, pady=(2, 6))
        tk.Label(r2, text="回复:", font=("微软雅黑", 9)).pack(side=tk.LEFT)
        rv = tk.StringVar(value=a.get("reply_text", ""))
        tk.Entry(r2, textvariable=rv, width=40, font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)

        self.rows.append({"frame": f, "name": nv, "reply": rv, "enabled": ev, "status": sv, "login_event": threading.Event()})

    def add(self):
        n = len(self.cfg["accounts"]) + 1
        self.cfg["accounts"].append({"name": f"账号{n}", "reply_text": "您好！感谢关注遵义农商银行，您的消息已收到~", "enabled": True})
        self.refresh()
        self.log("[系统] 已添加账号")

    def rm(self, i):
        if messagebox.askyesno("确认", f"删除 {self.cfg['accounts'][i]['name']}？"):
            del self.cfg["accounts"][i]
            save_config(self.cfg)
            self.refresh()

    def save(self):
        for i, w in enumerate(self.rows):
            self.cfg["accounts"][i].update(name=w["name"].get(), reply_text=w["reply"].get(), enabled=w["enabled"].get())
        save_config(self.cfg)
        self.log("💾 已保存")

    def start(self):
        self.save()
        stopped.clear()
        cnt = 0
        for i, a in enumerate(self.cfg["accounts"]):
            if not a["enabled"]:
                continue
            self.rows[i]["status"].set("🟡 请扫码...")
            self.rows[i]["login_event"].clear()
            t = threading.Thread(target=worker, args=(a,
                lambda m: self.root.after(0, self.log, m),
                lambda n, s: self.root.after(0, self._done, i, s),
                self.rows[i]["login_event"]), daemon=True)
            t.start()
            cnt += 1
            time.sleep(1.5)
        if cnt:
            self.log(f"已打开 {cnt} 个窗口，请逐个扫码登录")

    def confirm_login(self, i):
        self.rows[i]["login_event"].set()
        self.rows[i]["status"].set("🟢 监控中")
        self.log(f"[{self.cfg['accounts'][i]['name']}] 用户已确认登录")

    def _done(self, i, s):
        m = {"ok": "🟢 监控中", "timeout": "🔴 超时", "failed": "🔴 失败", "no_reply": "🟡 无回复"}
        self.rows[i]["status"].set(m.get(s, s))
        m = {"ok": "🟢 监控中", "timeout": "🔴 超时", "failed": "🔴 失败", "no_reply": "🟡 无回复"}
        self.rows[i]["status"].set(m.get(s, s))

    def stop_all(self):
        stopped.set()
        for w in self.rows:
            if w["status"].get() in ("🟢 监控中", "🟡 等登录..."):
                w["status"].set("⏹ 已停")

    def quit(self):
        self.stop_all()
        self.root.destroy()


if __name__ == "__main__":
    App().root.mainloop()
