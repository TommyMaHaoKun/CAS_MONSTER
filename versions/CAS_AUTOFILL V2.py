from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
import time

URL = "http://101.227.232.33:8001/"

USERNAME = input('Your Username: ')
PASSWORD = input('Your Password: ')

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=100  # Slight delay to see the actions occur
        )
        page = browser.new_page()

        print("--- 正在启动 CAS V2 脚本 ---")

        # 1) 打开登录页
        page.goto(URL, wait_until="domcontentloaded")

        # 2) 登录流程
        user_sel = "input[placeholder='Please enter your login account']"
        pass_sel = "input[placeholder='Please enter your password']"

        try:
            page.wait_for_selector(user_sel, state="visible", timeout=10000)
            page.fill(user_sel, USERNAME)
            page.fill(pass_sel, PASSWORD)

            # 点击登录按钮
            login_btn_sel = "button.login-btn"
            page.click(login_btn_sel)
        except PWTimeoutError:
            print("❌ 错误：无法找到登录框或登录按钮")
            browser.close()
            return

        # 3) 验证登录是否成功
        try:
            # 等待首页标志性文字出现
            page.wait_for_selector("text=WFLA高中综合系统", timeout=15000)
            print("✅ 登录成功")
        except PWTimeoutError:
            print("❌ 登录未确认成功：超时未检测到首页。")
            browser.close()
            return

        # ================= V2 新增功能 =================
        
        # 4) 点击 'Club Info'
        # 这里使用 text=... 选择器，Playwright 会自动寻找包含该文本的元素
        print("👉 正在寻找并点击 'Club Info'...")
        try:
            # 这里的 text=Club Info 对应截图中的 <span class="layui-left-nav">Club Info</span>
            page.click("text=Club Info", timeout=5000)
            print("   已点击 'Club Info' (菜单应已展开)")
        except PWTimeoutError:
            print("❌ 找不到 'Club Info' 菜单，请检查页面是否加载完成")

        # 5) 点击 'Activity Records'
        # 必须等待上一步菜单展开后，这个按钮才可见
        print("👉 正在寻找并点击 'Activity Records'...")
        try:
            # 这里的 text=Activity Records 对应截图中的子菜单项
            # 如果文本点击不稳定，也可以改用 CSS 选择器: a[layuimini-href='Stu/Cas/RecordList']
            page.click("text=Activity Records", timeout=5000)
            print("✅ 已点击 'Activity Records'，页面正在加载...")
            
            # (可选) 这里可以添加等待页面加载的逻辑，比如等待表格出现
            # page.wait_for_selector("table", timeout=5000) 
            
        except PWTimeoutError:
            print("❌ 找不到 'Activity Records' 按钮")

        # ===============================================

        print("\n脚本执行完毕。按 Enter 关闭浏览器...")
        input()
        browser.close()

if __name__ == "__main__":
    main()
