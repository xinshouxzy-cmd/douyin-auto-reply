# -*- coding: utf-8 -*-
"""
抖音多账号私信自动回复工具 v3
==========================
独立 EXE，内置浏览器驱动管理
每一号独立 Chrome 窗口，扫码登录后自动监控回复
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
PROFILES_DIR = os.path.join(BASE_DIR, "chrome_data")

os.makedirs(PROFILES_DIR, exist_ok=True)

DOUYIN_IM_URL = "https://www.douyin.com/messages"
DOUYIN_LOGIN_URL = "https://www.douyin.com"
POLL_INTERVAL = 8

running_accounts = {}
stop_flag = threading.Event()

# ====== 配置 ======

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"accounts": [
            {"name": "账号1", "reply_text": "您好！感谢关注遵义农商银行，您的消息已收到~", "enabled": True},
        ]}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ====== Chrome ======

def find_chrome():
    for p in [
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        os.path.expandvars("%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe"),
        os.path.expandvars("%PROGRAMFILES%\\Google\\Chrome\\Application\\chrome.exe"),
        os.path.expandvars("%PROGRAMFILES(X86)%\\Google\\Chrome\\Application\\chrome.exe"),
    ]:
        if os.path.exists(p): return p
    return None

def get_driver_path():
    try:
        import shutil
        from selenium.webdriver.chrome.service import Service
        d = shutil.which("chromedriver")
        if d: return d

        try:
            from webdriver_manager.chrome import ChromeDriverManager
            return ChromeDriverManager().install()
        except: pass

        exe = "chromedriver.exe" if sys.platform == "win32" else "chromedriver"
        local = os.path.join(BASE_DIR, exe)
        if os.path.exists(local): return local
    except: pass
    return None

def new_chrome(profile_name, log_func):
    """为指定账号创建 Chrome 窗口"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        log_func("缺少 selenium")
        return None

    chrome = find_chrome()
    if not chrome:
        log_func("未找到 Chrome，请先安装: https://www.google.com/chrome/")
        return None

    profile = os.path.join(PROFILES_DIR, profile_name)
    os.makedirs(profile, exist_ok=True)

    opts = Options()
    opts.binary_location = chrome
    opts.add_argument(f"--user-data-dir={profile}")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--no-first-run")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-sync")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_experimental_option("detach", True)

    drv = get_driver_path()
    svc = Service(executable_path=drv) if drv else Service()
    try:
        d = webdriver.Chrome(service=svc, options=opts)
    except Exception as e:
        log_func(f"Chrome 启动失败: {str(e)[:80]}")
        log_func("可能原因: Chrome 版本不匹配，正在尝试自动修复...")
        try:
            # 不带 driver_path 重试（让 Selenium 自动找）
            svc2 = Service()
            d = webdriver.Chrome(service=svc2, options=opts)
        except:
            return None

    d.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    d.set_window_size(450, 750)
    return d


# ====== 工作线程 ======

def account_worker(acc, log_func, on_login_done):
    name = acc["name"]
    reply = acc.get("reply_text", "").strip()
    profile = f"profile_{name}"

    if not reply:
        log_func(f"[{name}] 未设置回复内容")
        on_login_done(name, "no_reply")
        return

    log_func(f"[{name}] 打开 Chrome...")
    driver = new_chrome(profile, log_func)
    if not driver:
        on_login_done(name, "failed")
        return

    try:
        # 先打开登录页
        driver.get(DOUYIN_LOGIN_URL)
        log_func(f"[{name}] Chrome 已打开，请扫码登录抖音")
        log_func(f"[{name}] 登录后浏览器会自动跳转到消息页...")

        # 等待用户登录（检测页面是否已登录状态）
        logged_in = False
        for _ in range(120):
            time.sleep(2)
            try:
                current = driver.current_url
                # 如果已跳转到 douyin.com 的任意页面（非登录页），说明已登录
                if "douyin.com" in current and "login" not in current.lower() and "passport" not in current.lower():
                    logged_in = True
                    break
                # 检测是否有用户信息元素
                try:
                    el = driver.find_element("css selector", "[data-e2e='user-info'], .user-info, img[alt*='avatar']")
                    if el: logged_in = True; break
                except: pass
            except: pass

        if not logged_in:
            log_func(f"[{name}] 登录超时（2分钟），已跳过")
            on_login_done(name, "timeout")
            return

        # 登录成功，跳转到消息页
        driver.get(DOUYIN_IM_URL)
        time.sleep(3)
        on_login_done(name, "ok")
        log_func(f"[{name}] ✅ 登录成功，开始监控私信")

        # 监控循环
        while not stop_flag.is_set():
            try:
                if "messages" not in (driver.current_url or "") and "im" not in (driver.current_url or ""):
                    driver.get(DOUYIN_IM_URL)
                    time.sleep(3)

                # 检测未读消息并回复
                js = f"""
                let results = [];
                try {{
                    let items = document.querySelectorAll('[class*="conversation"], [class*="session"], div[data-e2e]');
                    for (let item of items) {{
                        let badge = item.querySelector('[class*="unread"], sup, [class*="badge"], [class*="count"]');
                        if (badge) {{
                            let txt = badge.textContent.trim();
                            if (txt && txt !== '0' && /\\d/.test(txt)) {{
                                item.click();
                                results.push({{clicked: true}});
                            }}
                        }}
                    }}
                }} catch(e) {{}}
                JSON.stringify(results);
                """
                unread = json.loads(driver.execute_script(js))

                if unread:
                    time.sleep(2)
                    send_js = f"""
                    let done = false;
                    try {{
                        let input = document.querySelector('textarea, [contenteditable="true"], div[contenteditable]');
                        if (!input) input = document.querySelector('[class*="input"], [class*="editor"]');
                        if (input) {{
                            if (input.tagName === 'TEXTAREA') input.value = {json.dumps(reply, ensure_ascii=False)};
                            else input.textContent = {json.dumps(reply, ensure_ascii=False)};
                            input.dispatchEvent(new Event('input', {{bubbles: true}}));
                            setTimeout(function() {{
                                let btn = document.querySelector('button[class*="send"], div[class*="send"], span[class*="send"]');
                                if (btn) btn.click();
                                else if (input.dispatchEvent) input.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', code: 'Enter', bubbles: true}}));
                            }}, 500);
                            done = true;
                        }}
                    }} catch(e) {{}}
                    JSON.stringify({{done: done}});
                    """
                    result = json.loads(driver.execute_script(send_js))
                    if result.get("done"):
                        log_func(f"[{name}] 📤 已自动回复")

                time.sleep(POLL_INTERVAL)

            except Exception as e:
                time.sleep(POLL_INTERVAL)

    except Exception as e:
        log_func(f"[{name}] 异常: {e}")
    finally:
        try: driver.quit()
        except: pass
        log_func(f"[{name}] 已停止")


# ====== GUI ======

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("抖音多账号自动回复 - 遵义农商银行")
        self.root.geometry("580x620")

        # Header
        hf = tk.Frame(self.root, bg="#c41230", height=44)
        hf.pack(fill=tk.X)
        tk.Label(hf, text="抖音多账号私信自动回复", fg="white", bg="#c41230",
                 font=("微软雅黑", 15, "bold")).pack(pady=8)

        # 账号列表
        self.list_frame = tk.Frame(self.root)
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.account_widgets = []

        # 底部按钮
        bf = tk.Frame(self.root)
        bf.pack(fill=tk.X, padx=10, pady=(0, 6))
        tk.Button(bf, text="+ 添加账号", command=self.add_account, width=11,
                  font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text="💾 保存配置", command=self.save, bg="#4CAF50", fg="white",
                  width=11, font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text="▶ 全部登录", command=self.start_all, bg="#c41230", fg="white",
                  width=11, font=("微软雅黑", 10, "bold")).pack(side=tk.RIGHT, padx=4)
        tk.Button(bf, text="⏹ 全部停止", command=self.stop_all, bg="#666", fg="white",
                  width=11, font=("微软雅黑", 10)).pack(side=tk.RIGHT, padx=4)

        # 日志
        lf = tk.LabelFrame(self.root, text="运行日志", font=("微软雅黑", 9))
        lf.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.log_widget = scrolledtext.ScrolledText(lf, height=8, font=("Consolas", 9))
        self.log_widget.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.log("✅ 程序已启动")
        self.log("【使用步骤】")
        self.log("  1. 在每个账号中填写名称和自动回复内容")
        self.log("  2. 点击「全部登录」打开 Chrome 窗口")
        self.log("  3. 在 Chrome 中扫码登录抖音")
        self.log("  4. 登录后程序自动监控私信并回复")
        self.log("")

        self.config = load_config()
        self.rebuild_list()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def log(self, msg):
        self.log_widget.insert(tk.END, f"{msg}\n")
        self.log_widget.see(tk.END)

    def rebuild_list(self):
        for w in self.account_widgets:
            w["frame"].destroy()
        self.account_widgets.clear()

        for i, acc in enumerate(self.config.get("accounts", [])):
            self._make_row(i, acc)

    def _make_row(self, i, acc):
        name = acc.get("name", f"账号{i+1}")
        reply = acc.get("reply_text", "")
        enabled = acc.get("enabled", True)

        row = tk.Frame(self.list_frame, bd=1, relief=tk.GROOVE)
        row.pack(fill=tk.X, padx=4, pady=3)

        # 第1行: 名称 + 状态 + 删除
        r1 = tk.Frame(row)
        r1.pack(fill=tk.X, padx=8, pady=(6, 2))

        name_var = tk.StringVar(value=name)
        tk.Entry(r1, textvariable=name_var, width=18, font=("微软雅黑", 10, "bold")).pack(side=tk.LEFT)

        status_var = tk.StringVar(value="⚪ 未登��")
        tk.Label(r1, textvariable=status_var, font=("微软雅黑", 9), fg="gray", width=14).pack(side=tk.LEFT, padx=8)

        enabled_var = tk.BooleanVar(value=enabled)
        tk.Checkbutton(r1, text="启用", variable=enabled_var).pack(side=tk.LEFT, padx=4)

        tk.Button(r1, text="🗑", command=lambda idx=i: self.delete_account(idx),
                  fg="red", font=("微软雅黑", 10), bd=0, width=3).pack(side=tk.RIGHT)

        # 第2行: 回复内容
        r2 = tk.Frame(row)
        r2.pack(fill=tk.X, padx=8, pady=(2, 6))
        tk.Label(r2, text="自动回复:", font=("微软雅黑", 9)).pack(side=tk.LEFT)
        reply_var = tk.StringVar(value=reply)
        tk.Entry(r2, textvariable=reply_var, width=40, font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)

        self.account_widgets.append({
            "frame": row,
            "name": name_var,
            "reply": reply_var,
            "enabled": enabled_var,
            "status": status_var,
        })

    def add_account(self):
        n = len(self.config["accounts"]) + 1
        self.config["accounts"].append({"name": f"账号{n}", "reply_text": "您好！感谢关注遵义农商银行，您的消息已收到~", "enabled": True})
        self.rebuild_list()
        self.log(f"[系统] 已添加账号{n}")

    def delete_account(self, i):
        if messagebox.askyesno("确认", f"删除 {self.config['accounts'][i]['name']}？"):
            del self.config["accounts"][i]
            save_config(self.config)
            self.rebuild_list()
            self.log(f"[系统] 已删除账号")

    def save(self):
        for i, w in enumerate(self.account_widgets):
            self.config["accounts"][i]["name"] = w["name"].get()
            self.config["accounts"][i]["reply_text"] = w["reply"].get()
            self.config["accounts"][i]["enabled"] = w["enabled"].get()
        save_config(self.config)
        self.log("[系统] 配置已保存")

    def start_all(self):
        self.save()
        stop_flag.clear()

        count = 0
        for i, acc in enumerate(self.config["accounts"]):
            if not acc["enabled"]: continue
            w = self.account_widgets[i]
            w["status"].set("🟡 等待登录...")
            t = threading.Thread(target=account_worker,
                                 args=(acc,
                                       lambda msg: self.root.after(0, self.log, msg),
                                       lambda n, s: self.set_status(i, s)),
                                 daemon=True)
            t.start()
            running_accounts[acc["name"]] = t
            count += 1
            time.sleep(1)

        if count == 0:
            messagebox.showwarning("提示", "没有启用的账号")
        else:
            self.log(f"[系统] 已打开 {count} 个 Chrome 窗口，请逐个扫码登录")

    def set_status(self, i, s):
        status_map = {"ok": "🟢 监控中", "timeout": "🔴 登录超时", "failed": "🔴 启动失败", "no_reply": "🟡 未设回复"}
        self.account_widgets[i]["status"].set(status_map.get(s, f"🔴 {s}"))

    def stop_all(self):
        stop_flag.set()
        for w in self.account_widgets:
            s = w["status"].get()
            if s in ("🟢 监控中", "🟡 等待登录..."):
                w["status"].set("⏹ 已停止")
        self.log("[系统] 已停止所有账号")

    def on_close(self):
        self.stop_all()
        self.root.destroy()


if __name__ == "__main__":
    App().root.mainloop()
