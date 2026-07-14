# -*- coding: utf-8 -*-
"""
交互式评论页面分析工具
运行 → 你手动点到评论页 → 回车确认 → 我抓取并分析DOM结构
"""
import os, time, threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(BASE_DIR, "browser_data")
os.makedirs(PROFILES_DIR, exist_ok=True)


def open_browser(name):
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
        args=["--disable-blink-features=AutomationControlled"]
    )
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return p, ctx, page


def analyze_page(page, label=""):
    """分析当前页面：URL + 所有可能包含评论的DOM结构"""
    print(f"\n{'='*60}")
    print(f"📋 分析: {label}")
    
    url = page.evaluate("() => location.href")
    title = page.evaluate("() => document.title")
    print(f"🔗 URL: {url}")
    print(f"📄 Title: {title}")
    
    # 1. 查找所有包含"评论"文字的可见元素
    print(f"\n--- 包含'评论'或'回复'的可见元素 ---")
    elems = page.evaluate("""() => {
        const results = [];
        const all = document.querySelectorAll('*');
        all.forEach(el => {
            const t = el.textContent || '';
            if ((t.includes('评论') || t.includes('回复')) && t.length < 200) {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    results.push({
                        tag: el.tagName,
                        class: el.className?.toString().substring(0, 80),
                        text: t.substring(0, 100),
                        x: Math.round(rect.x), y: Math.round(rect.y),
                        w: Math.round(rect.width), h: Math.round(rect.height),
                        id: el.id || ''
                    });
                }
            }
        });
        return results;
    }""")
    
    for e in elems[:15]:
        print(f"  [{e['tag']}] class={e['class'][:50]} id={e['id']} | pos=({e['x']},{e['y']}) size={e['w']}x{e['h']}")
        if e['text']:
            print(f"    📝 \"{e['text'][:80]}\"")
    
    # 2. 查找可能是评论列表项的容器
    print(f"\n--- 可能的评论列表容器 ---")
    containers = page.evaluate("""() => {
        const results = [];
        // 常见评论列表容器class关键词
        const patterns = ['comment', 'reply', 'message', 'feedback', 'interaction'];
        patterns.forEach(p => {
            const els = document.querySelectorAll('[class*="' + p + '"]');
            els.forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 200 && rect.height > 30) {
                    const children = el.children.length;
                    results.push({
                        tag: el.tagName,
                        class: el.className?.toString().substring(0, 60),
                        children: children,
                        w: Math.round(rect.width),
                        h: Math.round(rect.height),
                        text: (el.textContent || '').substring(0, 80)
                    });
                }
            });
        });
        return results;
    }""")
    
    for c in containers[:10]:
        print(f"  [{c['tag']}] class={c['class'][:50]} children={c['children']} size={c['w']}x{c['h']}")
        if c['text']:
            print(f"    📝 \"{c['text'][:80]}\"")
    
    # 3. 查找输入框和按钮
    print(f"\n--- 输入框 ---")
    inputs = page.evaluate("""() => {
        const results = [];
        document.querySelectorAll('input, textarea, [contenteditable="true"]').forEach(el => {
            const rect = el.getBoundingClientRect();
            if (rect.width > 50 && rect.height > 10) {
                results.push({
                    tag: el.tagName,
                    class: el.className?.toString().substring(0, 60),
                    placeholder: el.placeholder || '',
                    w: Math.round(rect.width), h: Math.round(rect.height)
                });
            }
        });
        return results;
    }""")
    for inp in inputs[:8]:
        print(f"  [{inp['tag']}] class={inp['class'][:50]} placeholder=\"{inp['placeholder']}\" size={inp['w']}x{inp['h']}")
    
    # 4. 完整页面DOM摘要
    print(f"\n--- 页面DOM摘要（前50个可见元素） ---")
    summary = page.evaluate("""() => {
        const result = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
        let node, count = 0;
        while (node = walker.nextNode()) {
            if (count > 50) break;
            const rect = node.getBoundingClientRect();
            if (rect.width > 100 || rect.height > 20) {
                const cls = (node.className || '').toString().substring(0, 40);
                const txt = (node.textContent || '').substring(0, 60);
                if (cls || txt) {
                    result.push(`<${node.tagName.toLowerCase()} class="${cls}"> "${txt}"`);
                    count++;
                }
            }
        }
        return result;
    }""")
    for s in summary[:30]:
        print(f"  {s}")


def main():
    print("=" * 60)
    print("  抖音评论页面 交互式分析工具")
    print("=" * 60)
    print()
    print("操作步骤：")
    print("  1. 浏览器打开后，扫码登录抖音")
    print("  2. 手动导航到你能看到评论列表的页面")
    print("  3. 回到终端，按 Enter → 我抓取当前页面")
    print("  4. 重复 2-3，直到找到正确页面")
    print("  输入 'ok' 确认这就是评论页面 → 我导出详细分析结果")
    print("  输入 'quit' 退出")
    print()
    
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    profile = os.path.join(PROFILES_DIR, "analyzer")
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=profile,
        headless=False, no_viewport=True,
        args=["--disable-blink-features=AutomationControlled"]
    )
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.douyin.com", timeout=60000)
    
    print("✅ 浏览器已打开，请登录并导航到评论页面")
    
    analysis_count = 0
    while True:
        cmd = input(f"\n[{analysis_count}] 按 Enter 抓取 / 'ok' 确认 / 'quit' 退出 > ").strip().lower()
        
        if cmd == "quit":
            break
        elif cmd == "ok":
            label = f"✅ 确认为评论页面 (第{analysis_count}次确认)"
            analyze_page(page, label)
            # 导出详细JSON
            dump = page.evaluate("""() => {
                const result = {url: location.href, title: document.title};
                // 抓取页面中所有可见的、尺寸合理的元素
                const elements = [];
                document.querySelectorAll('*').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 50 && rect.height > 15 && rect.width < 2000) {
                        elements.push({
                            tag: el.tagName,
                            class: (el.className || '').toString(),
                            id: el.id || '',
                            text: (el.textContent || '').substring(0, 150),
                            html: el.outerHTML.substring(0, 300),
                            rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)}
                        });
                    }
                });
                result.elements = elements.slice(0, 200);
                return result;
            }""")
            
            outpath = os.path.join(BASE_DIR, "comment_page_analysis.json")
            import json
            with open(outpath, "w", encoding="utf-8") as f:
                json.dump(dump, f, ensure_ascii=False, indent=2)
            print(f"\n📁 详细分析已导出到: {outpath}")
            break
        else:
            analysis_count += 1
            analyze_page(page, f"第{analysis_count}次抓取")
    
    print("\n正在关闭浏览器...")
    ctx.close()
    p.stop()
    print("完成")


if __name__ == "__main__":
    main()
