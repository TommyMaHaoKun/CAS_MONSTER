from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

URL = "http://101.227.232.33:8001/"

USERNAME = input('Your Username:')
PASSWORD = input('Your Password:')

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=150  # 放慢便于观察；稳定后可删
        )
        page = browser.new_page()

        # 1) 打开登录页
        page.goto(URL, wait_until="domcontentloaded")

        # 2) 定位并填写用户名/密码（按你给的 placeholder）
        user_sel = "input[placeholder='Please enter your login account']"
        pass_sel = "input[placeholder='Please enter your password']"

        page.wait_for_selector(user_sel, timeout=10000)
        page.wait_for_selector(pass_sel, timeout=10000)

        page.fill(user_sel, USERNAME)
        page.fill(pass_sel, PASSWORD)

        # 3) 点击登录按钮（你给的 class：login-btn）
        login_btn_sel = "button.login-btn"
        page.wait_for_selector(login_btn_sel, timeout=10000)
        page.click(login_btn_sel)

        # 4) 判断是否登录成功：等待“首页特征元素”
        # 你截图里登录后顶部会出现 “WFLA高中综合系统”
        try:
            page.wait_for_selector("text=WFLA高中综合系统", timeout=15000)
            print("✅ 登录成功（V1 完成）")
        except PWTimeoutError:
            # 如果失败，给出调试信息：看看是否还停留在登录页/是否有报错提示
            print("❌ 登录未确认成功：15 秒内未检测到首页标志文本")
            # 尝试抓取页面可能的提示（LayUI 常见 .layui-form-mid 或 .layui-layer-content）
            for sel in [".layui-layer-content", ".layui-form-mid", ".layui-form-item .layui-form-mid", ".layui-form-item .layui-form-danger"]:
                if page.locator(sel).count() > 0:
                    txt = page.locator(sel).first.inner_text().strip()
                    if txt:
                        print(f"页面提示：{txt}")
                        break

        input("按 Enter 关闭浏览器...")
        browser.close()

if __name__ == "__main__":
    main()
