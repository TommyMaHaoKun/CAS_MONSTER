from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
from getpass import getpass
import re
import time
import requests

URL = "http://101.227.232.33:8001/"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_CHAT_ENDPOINT = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"


def parse_date_ymd(s: str):
    m = re.match(r"^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*$", s)
    if not m:
        raise ValueError("Date format must be YYYY/MM/DD (e.g., 2025/11/19)")
    y, mo, d = map(int, m.groups())
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        raise ValueError("Invalid month/day.")
    return y, mo, d


def pick_context(page, iframe_css: str):
    if page.locator(iframe_css).count() > 0:
        return page.frame_locator(iframe_css)
    return page


def int_from_text(t: str) -> int:
    m = re.search(r"\d+", t)
    if not m:
        raise ValueError(f"Cannot parse integer from {t!r}")
    return int(m.group())


def select_date_layui(scope, target_year: int, target_month: int, target_day: int):
    cal = scope.locator("#layui-laydate1")
    cal.wait_for(state="visible", timeout=10000)

    def current_ym():
        y_txt = cal.locator(".laydate-set-ym span[lay-type='year']").inner_text()
        m_txt = cal.locator(".laydate-set-ym span[lay-type='month']").inner_text()
        return int_from_text(y_txt), int_from_text(m_txt)

    for _ in range(60):
        cy, _ = current_ym()
        if cy == target_year:
            break
        cal.locator("i.laydate-next-y" if cy < target_year else "i.laydate-prev-y").click()
        time.sleep(0.03)

    for _ in range(60):
        cy, cm = current_ym()
        if cy == target_year and cm == target_month:
            break
        cal.locator(
            "i.laydate-next-m"
            if (cy * 12 + cm) < (target_year * 12 + target_month)
            else "i.laydate-prev-m"
        ).click()
        time.sleep(0.03)

    cal.locator(f"td[lay-ymd='{target_year}-{target_month}-{target_day}']").click()


def choose_club(add_ctx) -> str:
    club_input = add_ctx.locator(
        "div.layui-form-item:has(label:has-text('Select a club')) "
        "div.layui-form-select input[placeholder='Please select']"
    )
    club_input.wait_for(timeout=10000)
    club_input.click()

    options = add_ctx.locator("dd[lay-value]").filter(
        has_not=add_ctx.locator(".layui-select-tips")
    )
    options.first.wait_for(timeout=10000)

    texts = [t.strip() for t in options.all_inner_texts() if t.strip()]
    if not texts:
        raise RuntimeError("No club options found.")

    print("\nAvailable clubs:")
    for i, t in enumerate(texts, 1):
        print(f"  {i}. {t}")

    while True:
        s = input("Select a club by number: ").strip()
        if s.isdigit() and 1 <= int(s) <= len(texts):
            idx = int(s) - 1
            options.nth(idx).click()
            selected = texts[idx]
            print(f"✅ Club selected: {selected}")
            return selected
        print("Invalid selection. Try again.")


def prompt_hours():
    def read_num(name):
        while True:
            s = input(f"Enter {name} hours: ").strip()
            if re.match(r"^\d+(\.\d+)?$", s):
                return s
            print("Invalid number.")
    return read_num("C"), read_num("A"), read_num("S")


def deepseek_chat(api_key: str, model: str, messages: list, temperature: float = 0.4, max_tokens: int = 350) -> dict:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    r = requests.post(DEEPSEEK_CHAT_ENDPOINT, headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text}
        raise RuntimeError(f"DeepSeek API error HTTP {r.status_code}: {j}")
    return r.json()


def word_count(s: str) -> int:
    # For English: count word-like tokens; for Chinese: count non-space characters
    if re.search(r"[A-Za-z]", s):
        return len(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", s))
    return len(re.findall(r"\S", s))


def generate_activity_record_deepseek(
    api_key: str,
    club_name: str,
    date_ymd: str,
    theme: str,
    c_hours: str,
    a_hours: str,
    s_hours: str,
    model: str = "deepseek-chat",
) -> str:
    # Required by you: exact core prompt template
    core_prompt = f"You are going to write an activity record for {club_name} club, and it should be more than 100 words."

    user_content = (
        f"{core_prompt}\n\n"
        f"Context:\n"
        f"- Date: {date_ymd}\n"
        f"- Activity theme: {theme}\n"
        f"- Hours: C={c_hours}, A={a_hours}, S={s_hours}\n\n"
        f"Requirements:\n"
        f"- Write in English.\n"
        f"- Include: what I did, what I learned, challenges, impact on others/community, next steps.\n"
        f"- Keep it realistic for a high school club activity.\n"
        f"- 120–180 words (to safely exceed 100).\n"
        f"- No bullet points; use 1–2 coherent paragraphs.\n"
    )

    messages = [
        {"role": "system", "content": "You write realistic CAS reflections for IB students. Be specific and not generic."},
        {"role": "user", "content": user_content},
    ]

    last_text = ""
    for _ in range(3):
        resp = deepseek_chat(api_key, model, messages, temperature=0.5, max_tokens=320)
        text = resp["choices"][0]["message"]["content"].strip()
        last_text = text
        if word_count(text) >= 100:
            return text

        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": "Too short. Expand to 120–180 words, keep it specific and realistic."})

    return last_text


def main():
    username = input("Username: ").strip()
    password = getpass("Password: ")

    # Do NOT hardcode if you will share this script
    deepseek_key = getpass("DeepSeek API Key (input hidden): ").strip()

    y, mo, d = parse_date_ymd(input("Target date (YYYY/MM/DD): ").strip())
    date_ymd = f"{y:04d}/{mo:02d}/{d:02d}"

    theme = input("Activity theme: ").strip()
    c_hours, a_hours, s_hours = prompt_hours()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=60)
        page = browser.new_page()

        page.goto(URL, wait_until="domcontentloaded")
        page.fill("input[placeholder='Please enter your login account']", username)
        page.fill("input[placeholder='Please enter your password']", password)
        page.click("button.login-btn")

        page.wait_for_selector("text=WFLA高中综合系统", timeout=20000)

        page.click("text=Club Info")
        page.click("text=Activity Records")

        record_ctx = pick_context(page, "iframe[src*='Stu/Cas/RecordList']")
        record_ctx.locator("button[data-method='add']").click()

        add_iframe_css = "iframe[src*='/Stu/Cas/AddRecord']"
        add_ctx = (
            record_ctx.frame_locator(add_iframe_css)
            if record_ctx.locator(add_iframe_css).count()
            else page.frame_locator(add_iframe_css)
        )

        club_name = choose_club(add_ctx)

        print("\nGenerating CAS activity description with DeepSeek...")
        description = generate_activity_record_deepseek(
            api_key=deepseek_key,
            club_name=club_name,
            date_ymd=date_ymd,
            theme=theme,
            c_hours=c_hours,
            a_hours=a_hours,
            s_hours=s_hours,
            model="deepseek-chat",
        )

        print("\n----- Generated description (preview) -----\n")
        print(description)
        print("\n-----------------------------------------\n")

        date_input = add_ctx.locator(
            "div.layui-form-item:has(label:has-text('Event date')) input"
        )
        date_input.click()

        cal_scope = add_ctx if add_ctx.locator("#layui-laydate1").count() else page
        select_date_layui(cal_scope, y, mo, d)

        add_ctx.locator(
            "div.layui-form-item:has(label:has-text('Activity theme')) input"
        ).fill(theme)

        add_ctx.locator("input[name='CDuration']").fill(c_hours)
        add_ctx.locator("input[name='ADuration']").fill(a_hours)
        add_ctx.locator("input[name='SDuration']").fill(s_hours)
        add_ctx.locator("textarea[name='Reflection']").fill(description)

        add_ctx.locator("button[lay-filter='add']:has-text('Save')").click()

        time.sleep(2)
        input("DeepSeek autofill finished. Press Enter to close browser.")
        browser.close()


if __name__ == "__main__":
    try:
        main()
    except PWTimeoutError as e:
        print(f"❌ Timeout: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
