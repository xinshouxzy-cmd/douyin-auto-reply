# -*- coding: utf-8 -*-
"""
抖音多账号私信自动回复工具
==========================
打包命令: pyinstaller --onefile --windowed --name "抖音自动回复" auto_reply_gui.py
"""

import os
import sys
import json
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# 工作目录
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
PROFILES_DIR = os.path.join(BASE_DIR, "chrome_data")

os.makedirs(PROFILES_DIR, exist_ok=True)

CHROME_PATH = os.path.join(BASE_DIR, "chrome-win64", "chrome.exe")
if not os.path.exists(CHROME_PATH):
    CHROME_PATH = None

DOUYIN_IM_URL = "https://www.douyin.com/messages"
POLL_INTERVAL = 5

running_accounts = {}
stop_flag = threading.Event()

# ========== 配置管理 ==========

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"accounts": [
            {"name": "账号1", "profile": "account_1", "reply_text": "您好！感谢关注遵义农商银行，您的消息已收到，稍后会有客户经理联系您~", "enabled": True},
            {"name": "账号2", "profile": "account_2", "reply_text": "您好！感谢关注遵义农商银行，您的消息已收到，稍后会有客户经理联系您~", "enabled": True},
            {"name": "账号3", "profile": "account_3", "reply_text": "您好！感谢关注遵义农商银行，您的消息已收到，稍后会有客户经理联系您~", "enabled": True},
            {"name": "账号4", "profile": "account_4", "reply_text": "您好！感谢关注遵义农商银行，您的消息已收到，稍后会有客户经理联系您~", "enabled": True},
        ]}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ========== Chrome 管理 ==========

def auto_install_driver():
    """自动下载 chromedriver"""
    try:
        import urllib.request
        import zipfile
        import platform

        print("[系统] 正在检测 chromedriver...")

        # 先检查当前目录
        exe_name = "chromedriver.exe" if sys.platform == "win32" else "chromedriver"
        local_driver = os.path.join(BASE_DIR, exe_name)
        if os.path.exists(local_driver):
            return local_driver

        # 检查 PATH
        import shutil
        if shutil.which("chromedriver"):
            return "chromedriver"

        print("[系统] 未找到 chromedriver，尝试自动下载...")
        print("[系统] 如自动下载失败，请手动下载:")
        print("       https://googlechromelabs.github.io/chrome-for-testing/")
        print("       放到程序目录即可")
        return None
    except Exception as e:
        print(f"[系统] 驱动检测失败: {e}")
        return None


def create_driver(profile_name, log_func=print):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        log_func("[错误] 缺少 selenium，请确保已正确打包")
        return None

    profile_dir = os.path.join(PROFILES_DIR, profile_name)
    os.makedirs(profile_dir, exist_ok=True)

    options = Options()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option("detach", True)

    if CHROME_PATH and os.path.exists(CHROME_PATH):
        options.binary_location = CHROME_PATH

    driver_path = auto_install_driver()
    service = Service(executable_path=driver_path) if driver_path else Service()

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        log_func("[错误] 启动 Chrome 失败，请确认已安装 Chrome 浏览器")
        return None

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.set_window_size(450, 750)
    return driver


# ========== 自动回复逻辑 ==========

def auto_reply_worker(account, log_func):
    name = account["name"]
    profile = account["profile"]
    reply_text = account.get("reply_text", "")

    if not reply_text.strip():
        log_func(f"[{name}] 未设置回复内容，跳过")
        return

    log_func(f"[{name}] 启动中...")
    driver = create_driver(profile, log_func)
    if not driver:
        log_func(f"[{name}] 启动失败")
        return

    try:
        driver.get(DOUYIN_IM_URL)
        log_func(f"[{name}] Chrome 已打开，请登录抖音")
        log_func(f"[{name}] 登录后浏览器会保持在消息页面")

        replied_set = set()
        error_count = 0

        while not stop_flag.is_set():
            try:
                if driver.current_url and "messages" not in driver.current_url and "im" not in driver.current_url:
                    try:
                        driver.get(DOUYIN_IM_URL)
                    except:
                        pass

                # 注入 JS 检测未读消息并回复
                js = f"""
                (function() {{
                    let replied = [];
                    let replyText = {json.dumps(reply_text, ensure_ascii=False)};
                    try {{
                        // 查找有未读标记的对话
                        let items = document.querySelectorAll('[class*="conversation"], [class*="chat-item"], div[data-index]');
                        for (let item of items) {{
                            let badge = item.querySelector('[class*="unread"], [class*="badge"], [class*="count"], sup');
                            if (badge && badge.textContent.trim()) {{
                                let text = badge.textContent.trim();
                                if (text !== '0' && text !== '') {{
                                    let convId = item.getAttribute('data-id') || item.getAttribute('data-conversation-id');
                                    let desc = (item.textContent || '').substring(0, 50).trim();
                                    // 点击进入对话
                                    item.click();
                                    replied.push({{id: convId, desc: desc, unread: text}});
                                }}
                            }}
                        }}
                    }} catch(e) {{}}
                    return JSON.stringify(replied);
                }})();
                """
                unread = json.loads(driver.execute_script(js))

                for conv in unread:
                    time.sleep(2)
                    # 发送回复
                    send_js = f"""
                    (function() {{
                        let reply = {json.dumps(reply_text, ensure_ascii=False)};
                        let sent = false;
                        try {{
                            // 找输入框
                            let input = document.querySelector('textarea, [contenteditable="true"]');
                            if (!input) input = document.querySelector('div[data-placeholder], div[class*="rich-input"]');
                            if (input) {{
                                input.focus();
                                if (input.contentEditable === 'true') {{
                                    input.textContent = reply;
                                }} else {{
                                    input.value = reply;
                                }}
                                input.dispatchEvent(new Event('input', {{bubbles: true}}));
                                
                                setTimeout(function() {{
                                    // 找发送按钮或按 Enter
                                    let btn = document.querySelector('button[class*="send"], button[class*="Send"], div[class*="send"]');
                                    if (btn) btn.click();
                                    else input.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', code: 'Enter', bubbles: true}}));
                                }}, 300);
                                
                                sent = true;
                            }}
                        }} catch(e) {{}}
                        return JSON.stringify({{sent: sent, desc: '{conv.get("desc", "")}'[:30]}});
                    }})();
                    """
                    result = json.loads(driver.execute_script(send_js))
                    if result.get("sent"):
                        log_func(f"[{name}] 已回复: {conv.get('desc', '')[:30]}...")
                        replied_set.add(conv.get("id", str(time.time())))

                error_count = 0
                time.sleep(POLL_INTERVAL)

            except Exception as e:
                error_count += 1
                if error_count > 10:
                    log_func(f"[{name}] 连续错误，刷新页面...")
                    try:
                        driver.refresh()
                    except:
                        try:
                            driver = create_driver(profile, log_func)
                            if driver:
                                driver.get(DOUYIN_IM_URL)
                        except:
                            log_func(f"[{name}] 无法恢复，请重启程序")
                            break
                    error_count = 0
                time.sleep(5)

    finally:
        try:
            driver.quit()
        except:
            pass
        log_func(f"[{name}] 已停止")


# ========== GUI ==========

class AutoReplyGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("抖音多账号自动回复 - 遵义农商银行")
        self.root.geometry("700x550")
        self.root.resizable(True, True)

        # 顶部标题
        title_frame = tk.Frame(self.root, bg="#c41230")
        title_frame.pack(fill=tk.X)
        tk.Label(title_frame, text="抖音多账号私信自动回复", fg="white", bg="#c41230",
                 font=("微软雅黑", 16, "bold"), pady=10).pack()

        # 账号配置区域
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 账号标签页
        self.config = load_config()
        self.account_frames = []
        self.account_vars = []

        for i, acc in enumerate(self.config["accounts"]):
            self._add_account_tab(i, acc)

        # 底部按钮
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        tk.Button(btn_frame, text="+ 添加账号", command=self.add_account, width=12).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="保存配置", command=self.save_all, bg="#4CAF50", fg="white", width=12).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="▶ 全部启动", command=self.start_all, bg="#c41230", fg="white", width=12,
                  font=("微软雅黑", 10, "bold")).pack(side=tk.RIGHT, padx=4)
        tk.Button(btn_frame, text="⏹ 全部停止", command=self.stop_all, bg="#666", fg="white", width=12).pack(side=tk.RIGHT, padx=4)

        # 日志区域
        log_frame = tk.LabelFrame(self.root, text="运行日志", font=("微软雅黑", 9))
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.log("✅ 程序已启动")
        self.log(f"📁 配置目录: {BASE_DIR}")
        self.log(f"🔧 配置文件: {CONFIG_FILE}")
        self.log(f"📂 Chrome数据: {PROFILES_DIR}")
        self.log("")
        self.log("【使用说明】")
        self.log("1. 在每个账号标签页填写「自动回复内容」")
        self.log("2. 勾选需要启用的账号")
        self.log("3. 点击「全部启动」")
        self.log("4. 首次使用需要在弹出的 Chrome 中登录抖音")
        self.log("5. 登录后程序自动监控私信并回复")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _add_account_tab(self, i, acc):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=f"  {acc['name']}  ")
        self.account_frames.append(frame)

        self.notebook.select(frame)

        # 账号名称
        tk.Label(frame, text="账号名称:", font=("微软雅黑", 9)).pack(anchor=tk.W, padx=20, pady=(16, 2))
        name_var = tk.StringVar(value=acc.get("name", f"账号{i+1}"))
        tk.Entry(frame, textvariable=name_var, width=40, font=("微软雅黑", 10)).pack(anchor=tk.W, padx=20)

        # 启用开关
        enabled_var = tk.BooleanVar(value=acc.get("enabled", True))
        tk.Checkbutton(frame, text="启用此账号", variable=enabled_var,
                       font=("微软雅黑", 9)).pack(anchor=tk.W, padx=20, pady=(10, 2))

        # 回复内容
        tk.Label(frame, text="自动回复内容（收到任何私信都回复这段话）:",
                 font=("微软雅黑", 9, "bold"), fg="#c41230").pack(anchor=tk.W, padx=20, pady=(10, 2))
        reply_var = tk.StringVar(value=acc.get("reply_text", ""))
        reply_entry = tk.Text(frame, height=5, width=60, font=("微软雅黑", 10))
        reply_entry.insert("1.0", acc.get("reply_text", ""))
        reply_entry.pack(anchor=tk.W, padx=20, fill=tk.X)

        # 状态
        status_var = tk.StringVar(value="⚪ 未启动")
        tk.Label(frame, textvariable=status_var, font=("微软雅黑", 9),
                 fg="gray").pack(anchor=tk.W, padx=20, pady=(10, 2))

        self.account_vars.append({
            "name": name_var,
            "enabled": enabled_var,
            "reply": reply_entry,
            "status": status_var,
            "profile": acc.get("profile", f"account_{i+1}"),
        })

    def add_account(self):
        n = len(self.config["accounts"]) + 1
        acc = {
            "name": f"账号{n}",
            "profile": f"account_{n}",
            "reply_text": "",
            "enabled": True
        }
        self.config["accounts"].append(acc)
        self._add_account_tab(n - 1, acc)
        self.log(f"[系统] 已添加账号{n}")

    def save_all(self):
        for i, vars_dict in enumerate(self.account_vars):
            self.config["accounts"][i]["name"] = vars_dict["name"].get()
            self.config["accounts"][i]["enabled"] = vars_dict["enabled"].get()
            self.config["accounts"][i]["reply_text"] = vars_dict["reply"].get("1.0", tk.END).strip()
        save_config(self.config)
        self.log("[系统] 配置已保存")

    def start_all(self):
        self.save_all()
        stop_flag.clear()

        enabled_count = 0
        for i, acc in enumerate(self.config["accounts"]):
            if acc["enabled"] and acc["reply_text"].strip():
                enabled_count += 1
                self.account_vars[i]["status"].set("🟢 运行中")
                t = threading.Thread(target=auto_reply_worker,
                                     args=(acc, lambda msg, a=acc["name"]: self.log_safe(f"[{a}] {msg}")),
                                     daemon=True)
                t.start()
                running_accounts[acc["name"]] = t
            elif acc["enabled"] and not acc["reply_text"].strip():
                self.account_vars[i]["status"].set("🟡 未设置回复内容")
            else:
                self.account_vars[i]["status"].set("⚫ 已禁用")

        if enabled_count == 0:
            messagebox.showwarning("提示", "没有启用的账号或未设置回复内容")
        else:
            self.log(f"[系统] 已启动 {enabled_count} 个账号监控")

    def stop_all(self):
        stop_flag.set()
        for vars_dict in self.account_vars:
            vars_dict["status"].set("⏹ 已停止")
        running_accounts.clear()
        self.log("[系统] 已停止所有账号")

    def log(self, msg):
        self.log_text.insert(tk.END, f"{msg}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def log_safe(self, msg):
        self.root.after(0, lambda: self.log(msg))

    def on_close(self):
        self.stop_all()
        self.root.destroy()


if __name__ == "__main__":
    gui = AutoReplyGUI()
    gui.root.mainloop()
