from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
import re
import time

URL = "http://101.227.232.33:8001/"

def parse_int(text: str) -> int:
    m = re.search(r"\d+", text)
    if not m:
        raise ValueError(f"Cannot parse number from: {text!r}")
    return int(m.group())

def select_date_layui(calendar_root, target_year: int, target_month: int, target_day: int):
    """
    calendar_root: a Locator context that contains #layui-laydate1 and laydate controls.
    Works with LayUI laydate:
      - prev year:  i.laydate-prev-y
      - prev month: i.laydate-prev-m
      - next month: i.laydate-next-m
      - next year:  i.laydate-next-y
      - current ym: .laydate-set-ym span[lay-type='year'|'month']
      - day cell:   td[lay-ymd='YYYY-M-D']
    """
    cal = calendar_root.locator("#layui-laydate1")
    cal.wait_for(state="visible", timeout=10000)

    def current_ym():
        year_text = cal.locator(".laydate-set-ym span[lay-type='year']").inner_text()
        month_text = cal.locator(".laydate-set-ym span[lay-type='month']").inner_text()
        return parse_int(year_text), parse_int(month_text)

    # Move year first, then month (safe and simple)
    for _ in range(40):  # safety bound
        cy, cm = current_ym()
        if cy == target_year:
            break
        if cy < target_year:
            cal.locator("i.laydate-next-y").click()
        else:
            cal.locator("i.laydate-prev-y").click()
        time.sleep(0.05)

    for _ in range(40):  # safety bound
        cy, cm = current_ym()
        if cm == target_month and cy == target_year:
            break
        if (cy * 12 + cm) < (target_year * 12 + target_month):
            cal.locator("i.laydate-next-m").click()
        else:
            cal.locator("i.laydate-prev-m").click()
        time.sleep(0.05)

    # LayUI lay-ymd format is typically "YYYY-M-D" (no zero padding)
    lay_ymd = f"{target_year}-{target_month}-{target_day}"
    cal.locator(f"td[lay-ymd='{lay_ymd}']").click()

def main():
    USERNAME = input("Your Username: ").strip()
    PASSWORD = input("Your Password: ").strip()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=80)
        page = browser.new_page()

        print("--- V3: login -> Activity Records -> Add Record -> fill -> Save ---")

        # 1) Login
        page.goto(URL, wait_until="domcontentloaded")
        page.fill("input[placeholder='Please enter your login account']", USERNAME)
        page.fill("input[placeholder='Please enter your password']", PASSWORD)
        page.click("button.login-btn")

        page.wait_for_selector("text=WFLA高中综合系统", timeout=15000)
        print("✅ Logged in")

        # 2) Navigate: Club Info -> Activity Records (same as your V2)
        page.click("text=Club Info", timeout=8000)
        page.click("text=Activity Records", timeout=8000)
        print("✅ Opened Activity Records tab")

        # 3) The Activity Records content is typically loaded in an iframe (LayuiMini-style).
        #    Wait for the RecordList iframe and work inside it.
        record_iframe_sel = "iframe[src*='Stu/Cas/RecordList']"
        page.wait_for_selector(record_iframe_sel, timeout=15000)
        record = page.frame_locator(record_iframe_sel)

        # 4) Click Add (HTML: button[data-method='add'])
        record.locator("button[data-method='add']").click()
        print("✅ Clicked Add")

        # 5) The Add Record form appears as a LayUI layer iframe inside the record iframe.
        add_iframe_sel = "iframe[src*='/Stu/Cas/AddRecord']"
        record.locator(add_iframe_sel).wait_for(timeout=15000)
        addf = record.frame_locator(add_iframe_sel)

        # ---------- Fill form in Add Record iframe ----------

        # (a) Select a club: click the readonly input, then click the dd option text
        club_input = addf.locator(
            "div.layui-form-item:has(label:has-text('Select a club')) "
            "div.layui-form-select input[placeholder='Please select']"
        )
        club_input.click()

        addf.locator("dd:has-text('历史社(History Club)')").click()
        print("✅ Selected club: 历史社(History Club)")

        # (b) Event date: open date picker, navigate to 2025/11/19, click day cell
        date_input = addf.locator(
            "div.layui-form-item:has(label:has-text('Event date')) input"
        )
        date_input.click()
        # Date picker might render either in the AddRecord iframe or (less commonly) in the record iframe.
        # Try AddRecord iframe first; fallback to record iframe.
        if addf.locator("#layui-laydate1").count() > 0:
            calendar_scope = addf
        else:
            calendar_scope = record

        select_date_layui(calendar_scope, 2025, 11, 19)
        print("✅ Selected date: 2025-11-19")

        # (c) Activity theme
        addf.locator(
            "div.layui-form-item:has(label:has-text('Activity theme')) input"
        ).fill("A Lecture about the Great Depression")

        # (d) Accumulated hours: name=CDuration/ADuration/SDuration
        addf.locator("input[name='CDuration']").fill("2")
        addf.locator("input[name='ADuration']").fill("0")
        addf.locator("input[name='SDuration']").fill("2")

        # (e) Activity description: textarea name="Reflection"
        description = (
            "In this lecture we examined the Great Depression as a global economic crisis rather than a purely American event. "
            "The speaker explained how monetary contraction, banking failures, and collapsing international trade reinforced each other. "
            "We compared policy responses such as fiscal stimulus, bank regulation, and currency devaluation, and discussed why recovery "
            "paths differed across countries. I asked questions about the limits of the gold standard, how confidence shocks spread, and "
            "what historians consider the most decisive turning points. This session improved my ability to connect economic mechanisms "
            "with historical interpretation and to evaluate claims using evidence and clear causal reasoning."
        )
        addf.locator("textarea[name='Reflection']").fill(description)

        # (f) Save: <button class="layui-btn" lay-submit lay-filter="add">Save</button>
        addf.locator("button[lay-filter='add']:has-text('Save')").click()
        print("✅ Clicked Save")

        # Optional: wait briefly for layer to close / request to finish
        time.sleep(2)

        print("V3 done. Press Enter to close browser...")
        input()
        browser.close()

if __name__ == "__main__":
    try:
        main()
    except PWTimeoutError as e:
        print(f"❌ Timeout: {e}")
