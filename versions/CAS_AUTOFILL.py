import threading
import queue
import re
import time
import html
import json
import calendar
from datetime import date as dt_date, timedelta
import requests
import tkinter as tk
from tkinter import ttk, messagebox

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

URL = "http://101.227.232.33:8001/"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_CHAT_ENDPOINT = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
CONVERSATION_CLUB = "谈话记录(Conversation)"


# -----------------------------
# Core helpers
# -----------------------------

def parse_date_ymd(s: str):
    m = re.match(r"^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*$", s)
    if not m:
        raise ValueError("Date format must be YYYY/MM/DD (e.g., 2025/11/19)")
    y, mo, d = map(int, m.groups())
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        raise ValueError("Invalid month/day.")
    try:
        dt_date(y, mo, d)
    except ValueError as exc:
        raise ValueError("Invalid date (check month/day/leap year).") from exc
    return y, mo, d


def iter_weekly_dates(start_dt: dt_date, end_dt: dt_date):
    cur = start_dt
    while cur <= end_dt:
        yield cur
        cur += timedelta(days=7)


def pick_context(page, iframe_css: str):
    if page.locator(iframe_css).count() > 0:
        return page.frame_locator(iframe_css)
    return page


def _find_iframe_src_contains(page, must_contain: list[str], timeout_ms: int = 15000):
    """Return the first iframe src that contains all substrings (best-effort)."""
    end = time.time() + timeout_ms / 1000
    while time.time() < end:
        for h in page.locator("iframe").element_handles():
            src = h.get_attribute("src") or ""
            if src and all(s in src for s in must_contain):
                return src
        time.sleep(0.12)
    return None


def _frame_locator_by_src(page, src: str):
    # Escape for CSS attribute selector
    esc = src.replace("\\", "\\\\").replace('"', '\\"')
    return page.frame_locator(f'iframe[src="{esc}"]')


def int_from_text(t: str) -> int:
    m = re.search(r"\d+", t)
    if not m:
        raise ValueError(f"Cannot parse integer from {t!r}")
    return int(m.group())


def select_date_layui(scope, target_year: int, target_month: int, target_day: int):
    """LayUI laydate calendar (#layui-laydate1) picker."""
    cal = scope.locator("#layui-laydate1")
    cal.wait_for(state="visible", timeout=10000)

    def current_ym():
        y_txt = cal.locator(".laydate-set-ym span[lay-type='year']").inner_text()
        m_txt = cal.locator(".laydate-set-ym span[lay-type='month']").inner_text()
        return int_from_text(y_txt), int_from_text(m_txt)

    # Year navigation
    for _ in range(60):
        cy, _ = current_ym()
        if cy == target_year:
            break
        cal.locator("i.laydate-next-y" if cy < target_year else "i.laydate-prev-y").click()
        time.sleep(0.03)

    # Month navigation
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


def deepseek_chat(api_key: str, model: str, messages: list, temperature: float = 0.5, max_tokens: int = 600) -> dict:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    r = requests.post(DEEPSEEK_CHAT_ENDPOINT, headers=headers, json=payload, timeout=90)
    if r.status_code != 200:
        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text}
        raise RuntimeError(f"DeepSeek API error HTTP {r.status_code}: {j}")
    return r.json()


def word_count(s: str) -> int:
    if re.search(r"[A-Za-z]", s):
        return len(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", s))
    return len(re.findall(r"\S", s))


def parse_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9]*\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except Exception:
        m = re.search(r"\{.*\}", cleaned, re.S)
        if not m:
            raise ValueError("No JSON object found in response.")
        return json.loads(m.group(0))


# -----------------------------
# DeepSeek generation
# -----------------------------

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
    is_conversation = club_name.strip() == CONVERSATION_CLUB
    min_words = 175 if is_conversation else 100
    word_target = "180每220" if is_conversation else "120每180"
    user_content = (
        f"Write an IB CAS Activity Record for the club '{club_name}'.\n"
        f"Context:\n"
        f"- Date: {date_ymd}\n"
        f"- Activity theme: {theme}\n"
        f"- Hours: C={c_hours}, A={a_hours}, S={s_hours}\n\n"
        f"Hard output rules (MUST follow):\n"
        f"- Output ONLY the final record text.\n"
        f"- Do NOT add a title, labels (e.g., 'Record:'), prefaces, explanations, word counts, or any extra lines.\n"
        f"- No bullet points, no markdown, no quotes.\n\n"
        f"Content requirements:\n"
        f"- English, realistic high school tone.\n"
        f"- 1–2 coherent paragraphs.\n"
        f"- {word_target} words (must be >= {min_words} words).\n"
        f"- The first 80% of the text must be concrete and specific: include at least 3–5 details "
        f"(what exactly I did, what material/topic I covered, what example I used, what question I handled, what I changed/improved).\n"
        f"- If this is a history-related activity (e.g., speech/lecture/presentation), include at least TWO specific pieces of history knowledge "
        f"(e.g., a named event/person, a date/time range, a cause-effect claim, a key term, a historiographical point) that I learned or used.\n"
        f"- Only in the LAST 1–2 sentences, allow brief general reflection (impact/next steps). Avoid generic clichés elsewhere."
    )


    messages = [
    {"role": "system", "content": "You write IB CAS Activity Records. Output ONLY the final prose (no headings/labels/prefaces). Prioritize concrete, evidence-based details; generic clichés only allowed in the last 1–2 sentences."},
    {"role": "user", "content": user_content},
    ]


    last_text = ""
    for _ in range(3):
        resp = deepseek_chat(api_key, model, messages, temperature=0.55, max_tokens=360)
        text = resp["choices"][0]["message"]["content"].strip()
        last_text = text
        if word_count(text) >= min_words:
            return text
        messages.append({"role": "assistant", "content": text})
        messages.append({
            "role": "user",
            "content": f"Too short. Expand to {word_target} words, keep specific and realistic."
        })

    return last_text


def generate_weekly_theme_desc_deepseek(
    api_key: str,
    club_name: str,
    date_ymd: str,
    club_desc: str,
    periodic_desc: str,
    used_themes: list[str],
    used_descs=None,
    model: str = "deepseek-chat",
) -> tuple[str, str]:
    avoid = "; ".join(used_themes[-8:]) if used_themes else "none"
    periodic_line = f"- Periodic activity: {periodic_desc}" if periodic_desc else "- Periodic activity: none"
    user_content = (
        f"Create ONE unique Activity theme and Activity Description for the club '{club_name}'.\n"
        f"Club description: {club_desc}\n"
        f"Date: {date_ymd}\n"
        f"{periodic_line}\n\n"
        f"Return a JSON object with keys theme and description only.\n"
        f"Rules:\n"
        f"- theme: 4-10 words, English, no date, no quotes.\n"
        f"- description: English, single paragraph, more than 80 words.\n"
        f"- Include at least 3 concrete details (what I did, materials/topics, specific examples, or changes).\n"
        f"- If a periodic activity is provided, keep it consistent but vary the details week to week.\n"
        f"- Avoid repetition across entries. Do NOT reuse any themes, topics, or examples from: {avoid}.\n"
        f"- Vary the activity focus across weeks (e.g., discussion, research, source analysis, workshop, debate, planning).\n"
        f"- No bullet points, no markdown, no labels."
    )

    messages = [
        {"role": "system", "content": "Return ONLY a valid JSON object with keys theme and description."},
        {"role": "user", "content": user_content},
    ]

    used_norm = {t.strip().lower() for t in used_themes}
    used_descs_norm = {d.strip().lower() for d in (used_descs or [])}
    last_theme = ""
    last_desc = ""

    for _ in range(4):
        resp = deepseek_chat(api_key, model, messages, temperature=0.6, max_tokens=320)
        raw = resp["choices"][0]["message"]["content"].strip()
        try:
            obj = parse_json_object(raw)
            theme = str(obj.get("theme", "")).strip()
            desc = str(obj.get("description", "")).strip()
        except Exception:
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "Return only valid JSON with keys theme and description."})
            continue

        theme = re.sub(r"\s+", " ", theme)
        desc = re.sub(r"\s+", " ", desc)
        last_theme, last_desc = theme, desc

        theme_wc = word_count(theme)
        if not theme or theme_wc < 4 or theme_wc > 10:
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "Revise: theme must be 4-10 words."})
            continue

        if theme.strip().lower() in used_norm:
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "Revise: theme repeats a previous entry. Make it clearly different."})
            continue

        if word_count(desc) <= 80:
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "Revise: description must be more than 80 words, one paragraph."})
            continue
        if desc.strip().lower() in used_descs_norm:
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "Revise: description repeats a previous entry. Write new content."})
            continue

        return theme, desc

    return last_theme, last_desc


def generate_reflection_summary_deepseek(
    api_key: str,
    club_name: str,
    title: str,
    club_desc: str = "",
    reflection_desc: str = "",
    model: str = "deepseek-chat",
) -> str:
    extra_context = ""
    if club_desc:
        extra_context += f"Club description: {club_desc}\n"
    if reflection_desc:
        extra_context += f"Reflection focus: {reflection_desc}\n"
    user_content = (
    f"Write a concise English summary for an IB CAS reflection.\n"
    f"Club: {club_name}\n"
    f"Title: {title}\n\n"
    f"{extra_context}"
    f"Hard output rules (MUST follow):\n"
    f"- Output ONLY ONE sentence and NOTHING ELSE.\n"
    f"- Do NOT add 'Summary:' or any label, no quotes, no extra whitespace lines.\n"
    f"- No bullet points, no markdown.\n\n"
    f"Length/style requirements:\n"
    f"- About 20 words (target 18–22 words).\n"
    f"- Must end with punctuation."
    )


    messages = [
    {"role": "system", "content": "Return exactly one natural English sentence only. No labels, no preface, no extra text."},
    {"role": "user", "content": user_content},
]


    last = ""
    for _ in range(4):
        resp = deepseek_chat(api_key, model, messages, temperature=0.45, max_tokens=80)
        text = resp["choices"][0]["message"]["content"].strip()
        text = re.sub(r"\s+", " ", text)
        last = text

        # keep only first line/sentence if model returns extras
        text = text.split("\n")[0].strip()
        # remove leading/trailing quotes
        text = text.strip('"')

        wc = word_count(text)
        if 18 <= wc <= 22 and text.endswith(('.', '!', '?')):
            return text

        messages.append({"role": "assistant", "content": text})
        messages.append({
            "role": "user",
            "content": "Revise: 1 sentence, 18–22 words, end with punctuation, no bullets, no extra text."
        })

    return last


def generate_reflection_content_deepseek(
    api_key: str,
    club_name: str,
    title: str,
    club_desc: str = "",
    reflection_desc: str = "",
    model: str = "deepseek-chat",
) -> str:
    extra_context = ""
    if club_desc:
        extra_context += f"Club description: {club_desc}\n"
    if reflection_desc:
        extra_context += f"Reflection focus: {reflection_desc}\n"
    user_content = (
    f"Write an IB CAS Activity Reflection in English.\n"
    f"Club: {club_name}\n"
    f"Title: {title}\n\n"
    f"{extra_context}"
    f"Hard output rules (MUST follow):\n"
    f"- Output ONLY the reflection body text.\n"
    f"- Do NOT add a title, labels (e.g., 'Reflection:'), section headers, prefaces, explanations, or word counts.\n"
    f"- No bullet points, no markdown, no quotes.\n\n"
    f"Structure/length:\n"
    f"- At least 550 words (target 600–750).\n"
    f"- 4–7 paragraphs.\n\n"
    f"Content requirements (anti-generic):\n"
    f"- The first 70–85% must be specific and evidence-based: include at least 6–10 concrete details "
    f"(exact tasks, decisions, what I said/did, what feedback I received, what I changed, specific examples).\n"
    f"- If this is history-related (speech/lecture/presentation), include at least TWO concrete history takeaways "
    f"(named event/person, date/time range, causation argument, key term, or historiographical insight) and explain how they shaped my thinking.\n"
    f"- Only in the FINAL paragraph, allow brief general statements about growth/impact/next steps; avoid generic phrases elsewhere."
    )


    messages = [
    {"role": "system", "content": "You write long-form IB CAS reflections. Output ONLY the final body text (no headings/labels/prefaces). Front-load concrete details and evidence; generic wrap-up only allowed in the last paragraph."},
    {"role": "user", "content": user_content},
    ]


    last = ""
    for _ in range(3):
        resp = deepseek_chat(api_key, model, messages, temperature=0.55, max_tokens=1400)
        text = resp["choices"][0]["message"]["content"].strip()
        last = text
        if word_count(text) >= 550:
            return text
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": "Too short. Expand to 600–750 words. Keep it specific; no bullet points."})

    return last


# -----------------------------
# Site-specific DOM helpers
# -----------------------------

def login_and_wait_home(page, user: str, pw: str):
    page.goto(URL, wait_until="domcontentloaded")
    page.fill("input[placeholder='Please enter your login account']", user)
    page.fill("input[placeholder='Please enter your password']", pw)
    page.click("button.login-btn")
    page.wait_for_selector("text=WFLA高中综合系统", timeout=20000)


def list_clubs_in_add_dialog(add_ctx):
    club_input = add_ctx.locator(
        "div.layui-form-item:has(label:has-text('Select a club')) "
        "div.layui-form-select input[placeholder='Please select']"
    )
    club_input.wait_for(timeout=10000)
    club_input.click()

    options = add_ctx.locator("dd[lay-value]").filter(has_not=add_ctx.locator(".layui-select-tips"))
    options.first.wait_for(timeout=10000)
    clubs = [t.strip() for t in options.all_inner_texts() if t.strip()]
    return [c for c in clubs if c.lower() != "please select"]


def select_club_by_text(add_ctx, club_name: str):
    club_input = add_ctx.locator(
        "div.layui-form-item:has(label:has-text('Select a club')) "
        "div.layui-form-select input[placeholder='Please select']"
    )
    club_input.wait_for(timeout=10000)
    club_input.click()
    add_ctx.locator(f"dd:has-text('{club_name}')").click()


def open_records_list_ctx(page):
    page.click("text=Club Info")
    page.click("text=Activity Records")
    # prefer the known iframe, fallback to page
    return pick_context(page, "iframe[src*='Stu/Cas/RecordList']")


def open_reflection_list_ctx(page):
    page.click("text=Club Info")
    page.click("text=Activity Reflection")
    # The content is usually inside a dynamically-created iframe. Find it by src.
    src = _find_iframe_src_contains(page, ["Stu/Cas", "Reflection"], timeout_ms=20000)
    if src and "AddReflection" not in src:
        return _frame_locator_by_src(page, src)

    # Fallback patterns (best-effort)
    for css in ["iframe[src*='Stu/Cas/Reflection']", "iframe[src*='Stu/Cas/Reflec']"]:
        if page.locator(css).count() > 0:
            return page.frame_locator(css)

    # Last resort: return page (some versions don't iframe the list)
    return page


def open_add_record_ctx(record_list_ctx, page):
    # Click Add button
    btn = record_list_ctx.locator("button[data-method='add']")
    if btn.count() == 0:
        btn = record_list_ctx.locator("button:has-text('Add')")
    btn.first.click()

    add_iframe_css = "iframe[src*='/Stu/Cas/AddRecord']"
    if record_list_ctx.locator(add_iframe_css).count():
        return record_list_ctx.frame_locator(add_iframe_css)
    if page.locator(add_iframe_css).count():
        return page.frame_locator(add_iframe_css)
    # fallback: the add iframe is created inside a layer; pick any visible layer iframe with AddRecord
    return page.frame_locator(add_iframe_css)


def open_add_reflection_ctx(reflection_list_ctx, page):
    btn = reflection_list_ctx.locator("button[data-method='add']")
    if btn.count() == 0:
        btn = reflection_list_ctx.locator("button:has-text('Add')")
    btn.first.click()

    add_iframe_css = "iframe[src*='/Stu/Cas/AddReflection']"
    if reflection_list_ctx.locator(add_iframe_css).count():
        return reflection_list_ctx.frame_locator(add_iframe_css)
    if page.locator(add_iframe_css).count():
        return page.frame_locator(add_iframe_css)
    return page.frame_locator(add_iframe_css)


def fill_kindeditor_body(add_ctx, text: str):
    """KindEditor uses an iframe for the editable body."""
    # Some pages may have multiple editor iframes; pick the first visible one.
    editor_iframe = add_ctx.locator("iframe.ke-edit-iframe")
    editor_iframe.first.wait_for(timeout=15000)
    editor_frame = add_ctx.frame_locator("iframe.ke-edit-iframe")
    body = editor_frame.locator("body.ke-content")
    body.wait_for(timeout=15000)

    # Set text via JS (fast, avoids typing slow_mo)
    body.evaluate("(el, v) => { el.innerText = v; }", text)
    # Trigger a small event to ensure editor registers change
    body.click()
    body.press("End")


def click_learning_outcomes(add_ctx, selected: list[str]):
    """Click LayUI styled checkboxes by their input title attribute."""
    for name in selected:
        # LayUI uses: <input type='checkbox' title='Awareness'> then a sibling div.layui-form-checkbox
        box = add_ctx.locator(
            f"xpath=//input[@type='checkbox' and @title='{name}']/following-sibling::div[contains(@class,'layui-form-checkbox')]"
        )
        if box.count() == 0:
            # fallback: click by visible text
            box = add_ctx.locator(f"div.layui-form-checkbox:has-text('{name}')")
        box.first.click(force=True)
        time.sleep(0.05)


# -----------------------------
# GUI App
# -----------------------------

class DatePicker(tk.Toplevel):
    DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    def __init__(self, master, initial_date, on_select, allowed_weekday=None):
        super().__init__(master)
        self.title("Select date")
        self.resizable(False, False)
        self.on_select = on_select
        self.cal = calendar.Calendar(firstweekday=calendar.MONDAY)
        self.today = dt_date.today()
        self.allowed_weekday = allowed_weekday

        self.year, self.month, _day = initial_date

        self._build_ui()
        self._render()

        self.transient(master)
        self.grab_set()
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build_ui(self):
        self.style = ttk.Style(self)
        self.style.configure("CalDim.TButton", foreground="gray50")
        self.style.configure("CalToday.TButton", background="#b7e1b5")
        self.style.map("CalToday.TButton", background=[("active", "#a6d49f")])
        self.style.configure("CalDimToday.TButton", foreground="gray50", background="#b7e1b5")
        self.style.map("CalDimToday.TButton", background=[("active", "#a6d49f")])
        self.style.configure("CalValid.TButton", background="#b7e1b5")
        self.style.map("CalValid.TButton", background=[("active", "#a6d49f")])
        self.style.configure("CalInvalid.TButton", foreground="#7a1d1d", background="#f3b3b3")
        self.style.map(
            "CalInvalid.TButton",
            background=[("disabled", "#f3b3b3"), ("active", "#ee9c9c")],
            foreground=[("disabled", "#7a1d1d")],
        )
        self.style.configure("CalDimValid.TButton", foreground="gray35", background="#d7ead2")
        self.style.map("CalDimValid.TButton", background=[("active", "#cfe5ca")])
        self.style.configure("CalDimInvalid.TButton", foreground="#7a1d1d", background="#f0c6c6")
        self.style.map(
            "CalDimInvalid.TButton",
            background=[("disabled", "#f0c6c6"), ("active", "#e9b4b4")],
            foreground=[("disabled", "#7a1d1d")],
        )

        nav = ttk.Frame(self, padding=(8, 8, 8, 0))
        nav.pack(fill="x")

        ttk.Button(nav, text="<<", width=3, command=self._prev_year).pack(side="left")
        ttk.Button(nav, text="<", width=3, command=self._prev_month).pack(side="left", padx=(2, 6))
        self.lbl_month = ttk.Label(nav, text="", width=16, anchor="center")
        self.lbl_month.pack(side="left", expand=True)
        ttk.Button(nav, text=">", width=3, command=self._next_month).pack(side="left", padx=(6, 2))
        ttk.Button(nav, text=">>", width=3, command=self._next_year).pack(side="left")
        ttk.Button(nav, text="Back to today", command=self._back_to_today).pack(side="left", padx=(8, 0))

        self.calendar_frame = ttk.Frame(self, padding=(8, 4, 8, 8))
        self.calendar_frame.pack(fill="both", expand=True)
        for c in range(7):
            self.calendar_frame.columnconfigure(c, uniform="cal", weight=1, minsize=34)
        for i, name in enumerate(self.DAY_LABELS):
            ttk.Label(self.calendar_frame, text=name, anchor="center").grid(
                row=0, column=i, padx=2, pady=2, sticky="nsew"
            )
        self._day_widgets = []

    def _render(self):
        self.lbl_month.configure(text=f"{calendar.month_name[self.month]} {self.year}")
        for child in self._day_widgets:
            child.destroy()
        self._day_widgets = []

        first_weekday, days_in_month = calendar.monthrange(self.year, self.month)
        prev_year, prev_month = (self.year - 1, 12) if self.month == 1 else (self.year, self.month - 1)
        next_year, next_month = (self.year + 1, 1) if self.month == 12 else (self.year, self.month + 1)
        days_in_prev = calendar.monthrange(prev_year, prev_month)[1]

        for r in range(6):
            for c in range(7):
                cell_index = r * 7 + c
                day_num = cell_index - first_weekday + 1

                in_month = True
                if day_num < 1:
                    disp_day = days_in_prev + day_num
                    disp_year, disp_month = prev_year, prev_month
                    style = "CalDim.TButton"
                    in_month = False
                elif day_num > days_in_month:
                    disp_day = day_num - days_in_month
                    disp_year, disp_month = next_year, next_month
                    style = "CalDim.TButton"
                    in_month = False
                else:
                    disp_day = day_num
                    disp_year, disp_month = self.year, self.month
                    style = "TButton"
                    in_month = True

                state = "normal"
                if self.allowed_weekday is not None:
                    allowed = dt_date(disp_year, disp_month, disp_day).weekday() == self.allowed_weekday
                    if in_month:
                        style = "CalValid.TButton" if allowed else "CalInvalid.TButton"
                    else:
                        style = "CalDimValid.TButton" if allowed else "CalDimInvalid.TButton"
                    state = "normal" if allowed else "disabled"
                else:
                    is_today = (
                        disp_year == self.today.year
                        and disp_month == self.today.month
                        and disp_day == self.today.day
                    )
                    if is_today and style == "CalDim.TButton":
                        style = "CalDimToday.TButton"
                    elif is_today:
                        style = "CalToday.TButton"

                btn = ttk.Button(
                    self.calendar_frame,
                    text=str(disp_day),
                    style=style,
                    state=state,
                    command=lambda y=disp_year, m=disp_month, d=disp_day: self._select_date(y, m, d),
                )
                btn.grid(row=r + 1, column=c, padx=2, pady=2, sticky="nsew")
                self._day_widgets.append(btn)
            self.calendar_frame.rowconfigure(r + 1, uniform="calrow", weight=1, minsize=30)

    def _select_date(self, year: int, month: int, day: int):
        self.on_select(year, month, day)
        self.destroy()

    def _prev_month(self):
        if self.month == 1:
            self.month = 12
            self.year -= 1
        else:
            self.month -= 1
        self._render()

    def _next_month(self):
        if self.month == 12:
            self.month = 1
            self.year += 1
        else:
            self.month += 1
        self._render()

    def _prev_year(self):
        self.year -= 1
        self._render()

    def _next_year(self):
        self.year += 1
        self._render()

    def _back_to_today(self):
        self.year = self.today.year
        self.month = self.today.month
        self._render()


class V42App(tk.Tk):
    OUTCOMES = [
        "Awareness",
        "Challenge",
        "Initiative",
        "Collaboration",
        "Commitment",
        "Global Value",
        "Ethics",
        "New Skills",
    ]
    WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    def __init__(self):
        super().__init__()
        self.title("WFLA CAS Autofill - V5.0.0 (Records + Reflection + Weekly Batch)")
        self.geometry("1400x900")
        self.minsize(1240, 820)

        self.log_q = queue.Queue()
        self.worker = None

        self.clubs_records: list[str] = []
        self.clubs_reflection: list[str] = []

        self._build_style()
        self._build_ui()
        self.after(100, self._poll_logs)

    # ---------- UI ----------
    def _make_checkbox_images(self):
        """Create custom checkbox images: empty box and checked box (√)."""
        size = 14
        off = tk.PhotoImage(width=size, height=size)
        on = tk.PhotoImage(width=size, height=size)

        # background
        for img in (off, on):
            img.put("white", to=(0, 0, size, size))

        # border
        for x in range(size):
            off.put("black", (x, 0)); off.put("black", (x, size - 1))
            on.put("black", (x, 0));  on.put("black", (x, size - 1))
        for y in range(size):
            off.put("black", (0, y)); off.put("black", (size - 1, y))
            on.put("black", (0, y));  on.put("black", (size - 1, y))

        # draw a √ on "on" image (simple check mark)
        # down stroke
        for i in range(4):
            x = 3 + i
            y = 7 + i
            on.put("black", (x, y))
            on.put("black", (x, y + 1))  # thickness
        # up stroke
        for i in range(6):
            x = 6 + i
            y = 10 - i
            on.put("black", (x, y))
            on.put("black", (x, y + 1))  # thickness

        return off, on

    def _build_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("Fetch.TButton", font=("Segoe UI", 9, "bold"), padding=(6, 2))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"))

    def _row(self, parent, r, label, widget_builder):
        row = ttk.Frame(parent)
        row.grid(row=r, column=0, sticky="ew", pady=4)
        parent.columnconfigure(0, weight=1)

        row.columnconfigure(1, weight=1)
        ttk.Label(row, text=label, width=20).grid(row=0, column=0, sticky="w")
        widget = widget_builder(row)
        widget.grid(row=0, column=1, sticky="ew")
        return widget

    def _build_ui(self):
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        top = ttk.Frame(root)
        top.pack(fill="both", expand=True)

        left = ttk.Frame(top)
        left.pack(side="left", fill="both", expand=True)

        right = ttk.Frame(top, width=420)
        right.pack(side="right", fill="y", expand=False, padx=(14, 0))
        right.pack_propagate(False)

        # --- Left: Account + Tabs
        ttk.Label(left, text="Input", style="Header.TLabel").pack(anchor="w", pady=(0, 8))

        lf_acc = ttk.Labelframe(left, text="Account", padding=10)
        lf_acc.pack(fill="x", pady=(0, 10))

        self.var_user = tk.StringVar()
        self.var_pass = tk.StringVar()
        self.var_dskey = tk.StringVar()

        self._row(lf_acc, 0, "Username", lambda p: ttk.Entry(p, textvariable=self.var_user, width=34))
        self._row(lf_acc, 1, "Password", lambda p: ttk.Entry(p, textvariable=self.var_pass, show="•", width=34))
        self._row(lf_acc, 2, "DeepSeek API Key", lambda p: ttk.Entry(p, textvariable=self.var_dskey, show="•", width=34))
        self.btn_fetch_clubs = self._row(
            lf_acc, 3, "",
            lambda p: ttk.Button(p, text="Fetch clubs", style="Fetch.TButton", width=12, command=self.on_fetch_clubs_records)
        )

        self.tabs = ttk.Notebook(left)
        self.tabs.pack(fill="both", expand=True)

        tab_rec = ttk.Frame(self.tabs, padding=10)
        tab_batch = ttk.Frame(self.tabs, padding=10)
        tab_ref = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab_rec, text="Activity Records")
        self.tabs.add(tab_batch, text="Weekly Batch Records")
        self.tabs.add(tab_ref, text="Activity Reflection")

        # --- Records tab
        lf_rec = ttk.Labelframe(tab_rec, text="Single Record", padding=10)
        lf_rec.pack(fill="x")

        self.var_rec_club = tk.StringVar()
        self.var_rec_date = tk.StringVar(value="")
        self.var_rec_theme = tk.StringVar(value="")
        self.var_rec_c = tk.StringVar(value="")
        self.var_rec_a = tk.StringVar(value="")
        self.var_rec_s = tk.StringVar(value="")

        self.combo_rec_club = self._row(
            lf_rec, 0, "Club",
            lambda p: ttk.Combobox(p, textvariable=self.var_rec_club, width=31, state="readonly", values=[])
        )
        def build_date_picker(p):
            f = ttk.Frame(p)
            self.entry_rec_date = ttk.Entry(f, textvariable=self.var_rec_date, width=24, state="readonly")
            self.entry_rec_date.pack(side="left", fill="x", expand=True)
            ttk.Button(f, text="Pick", command=self._open_rec_date_picker).pack(side="left", padx=(6, 0))
            self.entry_rec_date.bind("<Button-1>", lambda _e: self._open_rec_date_picker())
            self.entry_rec_date.bind("<Return>", lambda _e: self._open_rec_date_picker())
            return f

        self._row(lf_rec, 1, "Date (calendar)", build_date_picker)
        self._row(lf_rec, 2, "Activity theme", lambda p: ttk.Entry(p, textvariable=self.var_rec_theme, width=34))

        def build_hours_rec(p):
            f = ttk.Frame(p)
            ttk.Label(f, text="C").pack(side="left")
            ttk.Entry(f, textvariable=self.var_rec_c, width=6).pack(side="left", padx=(4, 14))
            ttk.Label(f, text="A").pack(side="left")
            ttk.Entry(f, textvariable=self.var_rec_a, width=6).pack(side="left", padx=(4, 14))
            ttk.Label(f, text="S").pack(side="left")
            ttk.Entry(f, textvariable=self.var_rec_s, width=6).pack(side="left", padx=(4, 0))
            return f

        self._row(lf_rec, 3, "Hours (C/A/S)", build_hours_rec)

        rec_btns = ttk.Frame(tab_rec)
        rec_btns.pack(fill="x", pady=(10, 0))
        self.btn_rec_run = ttk.Button(rec_btns, text="Run single record", style="Accent.TButton", command=self.on_run_record)
        self.btn_rec_run.pack(side="left", ipadx=8)

        # --- Weekly Batch Records
        lf_batch = ttk.Labelframe(tab_batch, text="Weekly Batch Records", padding=10)
        lf_batch.pack(fill="x")

        self.var_batch_club = tk.StringVar()
        self.var_batch_club_desc = tk.StringVar(value="")
        self.var_batch_weekday = tk.StringVar(value="")
        self.var_batch_start = tk.StringVar(value="")
        self.var_batch_end = tk.StringVar(value="")
        self.var_batch_periodic = tk.StringVar(value="")
        self.var_batch_c = tk.StringVar(value="")
        self.var_batch_a = tk.StringVar(value="")
        self.var_batch_s = tk.StringVar(value="")

        self.combo_batch_club = self._row(
            lf_batch, 0, "Club",
            lambda p: ttk.Combobox(p, textvariable=self.var_batch_club, width=31, state="readonly", values=[])
        )
        self._row(
            lf_batch, 1, "Club description",
            lambda p: ttk.Entry(p, textvariable=self.var_batch_club_desc, width=34)
        )
        self.combo_batch_weekday = self._row(
            lf_batch, 2, "Weekday",
            lambda p: ttk.Combobox(p, textvariable=self.var_batch_weekday, width=31, state="readonly", values=self.WEEKDAYS)
        )
        self.combo_batch_weekday.bind("<<ComboboxSelected>>", self._on_batch_weekday_selected)

        def build_batch_start_picker(p):
            f = ttk.Frame(p)
            self.entry_batch_start = ttk.Entry(f, textvariable=self.var_batch_start, width=24, state="readonly")
            self.entry_batch_start.pack(side="left", fill="x", expand=True)
            self.btn_batch_start_pick = ttk.Button(
                f, text="Pick", state="disabled", command=self._open_batch_start_picker
            )
            self.btn_batch_start_pick.pack(side="left", padx=(6, 0))
            self.entry_batch_start.bind("<Button-1>", lambda _e: self._open_batch_start_picker())
            self.entry_batch_start.bind("<Return>", lambda _e: self._open_batch_start_picker())
            return f

        def build_batch_end_picker(p):
            f = ttk.Frame(p)
            self.entry_batch_end = ttk.Entry(f, textvariable=self.var_batch_end, width=24, state="readonly")
            self.entry_batch_end.pack(side="left", fill="x", expand=True)
            self.btn_batch_end_pick = ttk.Button(
                f, text="Pick", state="disabled", command=self._open_batch_end_picker
            )
            self.btn_batch_end_pick.pack(side="left", padx=(6, 0))
            self.entry_batch_end.bind("<Button-1>", lambda _e: self._open_batch_end_picker())
            self.entry_batch_end.bind("<Return>", lambda _e: self._open_batch_end_picker())
            return f

        self._row(lf_batch, 3, "Start date", build_batch_start_picker)
        self._row(lf_batch, 4, "End date", build_batch_end_picker)
        self._row(
            lf_batch, 5, "Periodic activity\n(optional)",
            lambda p: ttk.Entry(p, textvariable=self.var_batch_periodic, width=34)
        )
        def build_hours_batch(p):
            f = ttk.Frame(p)
            ttk.Label(f, text="C").pack(side="left")
            ttk.Entry(f, textvariable=self.var_batch_c, width=6).pack(side="left", padx=(4, 14))
            ttk.Label(f, text="A").pack(side="left")
            ttk.Entry(f, textvariable=self.var_batch_a, width=6).pack(side="left", padx=(4, 14))
            ttk.Label(f, text="S").pack(side="left")
            ttk.Entry(f, textvariable=self.var_batch_s, width=6).pack(side="left", padx=(4, 0))
            return f

        self._row(lf_batch, 6, "Hours (C/A/S)", build_hours_batch)
        self._row(
            lf_batch, 7, "Theme/Description",
            lambda p: ttk.Label(p, text="Generated automatically by DeepSeek", anchor="w")
        )

        batch_btns = ttk.Frame(tab_batch)
        batch_btns.pack(fill="x", pady=(8, 0))
        self.btn_batch_run = ttk.Button(
            batch_btns, text="Run weekly batch", style="Accent.TButton", command=self.on_run_record_batch
        )
        self.btn_batch_run.pack(side="left", ipadx=8)

        # --- Reflection tab
        lf_ref = ttk.Labelframe(tab_ref, text="Reflection", padding=10)
        lf_ref.pack(fill="x")

        self.var_ref_club = tk.StringVar()
        self.var_ref_count = tk.StringVar(value="1")
        self.var_ref_club_desc = tk.StringVar(value="")

        self.combo_ref_club = self._row(
            lf_ref, 0, "Club",
            lambda p: ttk.Combobox(p, textvariable=self.var_ref_club, width=31, state="readonly", values=[])
        )
        self._row(lf_ref, 1, "Number of reflections", lambda p: ttk.Entry(p, textvariable=self.var_ref_count, width=34))
        self._row(lf_ref, 2, "Club description", lambda p: ttk.Entry(p, textvariable=self.var_ref_club_desc, width=34))

        ttk.Label(lf_ref, text="Titles (one per line)", width=20).grid(row=4, column=0, sticky="w", pady=4)
        titles_frame = ttk.Frame(lf_ref)
        titles_frame.grid(row=4, column=1, sticky="ew", pady=4)
        lf_ref.columnconfigure(1, weight=1)
        self.txt_ref_titles = tk.Text(titles_frame, height=4, wrap="word")
        self.txt_ref_titles.pack(fill="both", expand=True)

        ttk.Label(lf_ref, text="Reflection descriptions\n(optional, one per line)", width=20).grid(
            row=5, column=0, sticky="w", pady=4
        )
        desc_frame = ttk.Frame(lf_ref)
        desc_frame.grid(row=5, column=1, sticky="ew", pady=4)
        self.txt_ref_desc = tk.Text(desc_frame, height=4, wrap="word")
        self.txt_ref_desc.pack(fill="both", expand=True)

        # Learning outcomes selector
        outcomes_box = ttk.Labelframe(tab_ref, text="Learning Outcome", padding=10)
        
        outcomes_box.pack(fill="x", pady=(10, 0))

        self.outcome_vars = {name: tk.BooleanVar(value=False) for name in self.OUTCOMES}

        grid = ttk.Frame(outcomes_box)
        grid.pack(fill="x")
        # custom checkbox icons (force √ instead of ☒)
        self.cb_img_off, self.cb_img_on = self._make_checkbox_images()

        # 2 rows x 4 columns
        for idx, name in enumerate(self.OUTCOMES):
            r = idx // 4
            c = idx % 4
            cb = tk.Checkbutton(
                grid,
                text=name,
                variable=self.outcome_vars[name],
                image=self.cb_img_off,
                selectimage=self.cb_img_on,
                indicatoron=0,          # remove default ☒ indicator
                compound="left",        # image on the left, text on the right
                padx=6,
                anchor="w"
            )
            cb.grid(row=r, column=c, sticky="w", padx=8, pady=4)


        ref_btns = ttk.Frame(tab_ref)
        ref_btns.pack(fill="x", pady=(10, 0))
        self.btn_ref_run = ttk.Button(ref_btns, text="Run reflection autofill", style="Accent.TButton", command=self.on_run_reflection)
        self.btn_ref_run.pack(side="left", ipadx=8)

        # --- Right: Previews + logs
        ttk.Label(right, text="Preview", style="Header.TLabel").pack(anchor="w")

        self.preview_tabs = ttk.Notebook(right)
        self.preview_tabs.pack(fill="both", expand=False, pady=(6, 10))

        prev_rec = ttk.Frame(self.preview_tabs, padding=6)
        prev_ref = ttk.Frame(self.preview_tabs, padding=6)
        self.preview_tabs.add(prev_rec, text="Record")
        self.preview_tabs.add(prev_ref, text="Reflection")

        self.txt_preview_record = tk.Text(prev_rec, height=10, wrap="word")
        self.txt_preview_record.pack(fill="both", expand=True)
        self.txt_preview_record.configure(state="disabled")

        # Reflection preview: summary + content
        ttk.Label(prev_ref, text="Content Summary (20 words)").pack(anchor="w")
        self.txt_preview_summary = tk.Text(prev_ref, height=3, wrap="word")
        self.txt_preview_summary.pack(fill="x", expand=False, pady=(4, 8))
        self.txt_preview_summary.configure(state="disabled")

        ttk.Label(prev_ref, text="Reflection content (>= 550 words)").pack(anchor="w")
        self.txt_preview_reflection = tk.Text(prev_ref, height=8, wrap="word")
        self.txt_preview_reflection.pack(fill="both", expand=True, pady=(4, 0))
        self.txt_preview_reflection.configure(state="disabled")

        ttk.Label(right, text="Logs", style="Header.TLabel").pack(anchor="w")
        self.txt_log = tk.Text(right, height=14, wrap="word")
        self.txt_log.pack(fill="both", expand=True, pady=(6, 0))
        self.txt_log.configure(state="disabled")

        footer = ttk.Frame(root)
        footer.pack(fill="x", pady=(10, 0))
        self.btn_stop = ttk.Button(footer, text="Close browser (manual)", command=self.on_hint_stop)
        self.btn_stop.pack(side="left")
        ttk.Label(footer, text="V5.0.0 - Records + Reflection + Weekly Batch (DeepSeek)").pack(side="left", padx=(12, 0))

    # ---------- logging / previews ----------

    def _log(self, msg: str):
        self.log_q.put(msg)

    def _set_preview_record(self, text: str):
        self.log_q.put(("__PREVIEW_REC__", text))

    def _set_preview_reflection(self, summary: str, content: str):
        self.log_q.put(("__PREVIEW_REF__", summary, content))

    def _poll_logs(self):
        try:
            while True:
                item = self.log_q.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__PREVIEW_REC__":
                    self.txt_preview_record.configure(state="normal")
                    self.txt_preview_record.delete("1.0", "end")
                    self.txt_preview_record.insert("end", item[1])
                    self.txt_preview_record.configure(state="disabled")
                elif isinstance(item, tuple) and item and item[0] == "__PREVIEW_REF__":
                    _, summary, content = item
                    self.txt_preview_summary.configure(state="normal")
                    self.txt_preview_summary.delete("1.0", "end")
                    self.txt_preview_summary.insert("end", summary)
                    self.txt_preview_summary.configure(state="disabled")

                    self.txt_preview_reflection.configure(state="normal")
                    self.txt_preview_reflection.delete("1.0", "end")
                    self.txt_preview_reflection.insert("end", content)
                    self.txt_preview_reflection.configure(state="disabled")
                else:
                    self.txt_log.configure(state="normal")
                    self.txt_log.insert("end", str(item) + "\n")
                    self.txt_log.see("end")
                    self.txt_log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(120, self._poll_logs)

    # ---------- validation ----------

    def _validate_account(self):
        user = self.var_user.get().strip()
        pw = self.var_pass.get().strip()
        key = self.var_dskey.get().strip()
        if not user or not pw:
            raise ValueError("Username/Password cannot be empty.")
        if not key:
            raise ValueError("DeepSeek API Key cannot be empty.")
        return user, pw, key

    def _validate_record(self):
        club = self.var_rec_club.get().strip()
        date = self.var_rec_date.get().strip()
        theme = self.var_rec_theme.get().strip()
        c = self.var_rec_c.get().strip()
        a = self.var_rec_a.get().strip()
        s = self.var_rec_s.get().strip()

        if not club:
            raise ValueError("Please fetch and select a club (Records).")
        if not date:
            raise ValueError("Please select a date from the calendar.")
        y, mo, d = parse_date_ymd(date)
        if not theme:
            raise ValueError("Activity theme cannot be empty.")
        for name, val in [("C", c), ("A", a), ("S", s)]:
            if not re.match(r"^\d+(\.\d+)?$", val):
                raise ValueError(f"{name} hours must be a number.")
        return club, (y, mo, d), theme, c, a, s

    def _validate_record_batch(self):
        club = self.var_batch_club.get().strip()
        club_desc = self.var_batch_club_desc.get().strip()
        weekday_label = self.var_batch_weekday.get().strip()
        start = self.var_batch_start.get().strip()
        end = self.var_batch_end.get().strip()
        periodic = self.var_batch_periodic.get().strip()
        c = self.var_batch_c.get().strip()
        a = self.var_batch_a.get().strip()
        s = self.var_batch_s.get().strip()

        if not club:
            raise ValueError("Please fetch and select a club (Weekly Batch).")
        if not club_desc:
            raise ValueError("Club description cannot be empty.")
        if not weekday_label:
            raise ValueError("Please select a weekday first.")
        if not start or not end:
            raise ValueError("Please select both start and end dates.")
        for name, val in [("C", c), ("A", a), ("S", s)]:
            if not re.match(r"^\d+(\.\d+)?$", val):
                raise ValueError(f"{name} hours must be a number.")

        y1, m1, d1 = parse_date_ymd(start)
        y2, m2, d2 = parse_date_ymd(end)
        start_dt = dt_date(y1, m1, d1)
        end_dt = dt_date(y2, m2, d2)
        weekday_idx = self.WEEKDAYS.index(weekday_label)

        if start_dt.weekday() != weekday_idx or end_dt.weekday() != weekday_idx:
            raise ValueError(f"Start and end dates must both be {weekday_label}.")
        if start_dt > end_dt:
            raise ValueError("End date must be the same day or after start date.")

        dates = list(iter_weekly_dates(start_dt, end_dt))
        if not dates:
            raise ValueError("No dates found for the selected range.")

        return club, club_desc, periodic, dates, c, a, s

    def _validate_reflection(self):
        club = self.var_ref_club.get().strip()
        count_raw = self.var_ref_count.get().strip()
        club_desc = self.var_ref_club_desc.get().strip()
        if not club:
            raise ValueError("Please fetch and select a club (Reflection).")
        if not count_raw.isdigit() or int(count_raw) <= 0:
            raise ValueError("Number of reflections must be a positive integer.")
        count = int(count_raw)
        if not club_desc:
            raise ValueError("Club description cannot be empty.")
        titles_raw = self.txt_ref_titles.get("1.0", "end").strip()
        titles = [t.strip() for t in titles_raw.splitlines() if t.strip()]
        if not titles:
            raise ValueError("Please input at least one title (one per line).")
        if len(titles) != count:
            raise ValueError("Number of titles must match the number of reflections.")

        desc_raw = self.txt_ref_desc.get("1.0", "end").strip()
        desc_lines = [d.strip() for d in desc_raw.splitlines() if d.strip()]
        if desc_lines and len(desc_lines) != count:
            raise ValueError("Reflection descriptions must match the number of reflections.")
        if not desc_lines:
            desc_lines = [""] * count
        selected = [k for k, v in self.outcome_vars.items() if v.get()]
        if not selected:
            raise ValueError("Select at least one Learning Outcome.")
        return club, club_desc, desc_lines, titles, selected

    def _set_buttons_running(self, running: bool):
        state = "disabled" if running else "normal"
        for b in [self.btn_fetch_clubs, self.btn_rec_run, self.btn_batch_run, self.btn_ref_run]:
            b.configure(state=state)

    def _open_rec_date_picker(self):
        raw = self.var_rec_date.get().strip()
        initial = None
        if raw:
            try:
                initial = parse_date_ymd(raw)
            except ValueError:
                initial = None
        if not initial:
            today = dt_date.today()
            initial = (today.year, today.month, today.day)
        DatePicker(self, initial, self._set_rec_date)

    def _set_rec_date(self, y: int, mo: int, d: int):
        self.var_rec_date.set(f"{y:04d}/{mo:02d}/{d:02d}")

    def _on_batch_weekday_selected(self, _event=None):
        self.var_batch_start.set("")
        self.var_batch_end.set("")
        self.btn_batch_start_pick.configure(state="normal")
        self.btn_batch_end_pick.configure(state="normal")

    def _get_batch_weekday_index(self):
        weekday_label = self.var_batch_weekday.get().strip()
        if not weekday_label:
            raise ValueError("Please select a weekday first.")
        return self.WEEKDAYS.index(weekday_label)

    def _open_batch_start_picker(self):
        try:
            weekday_idx = self._get_batch_weekday_index()
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        raw = self.var_batch_start.get().strip()
        initial = None
        if raw:
            try:
                initial = parse_date_ymd(raw)
            except ValueError:
                initial = None
        if not initial:
            today = dt_date.today()
            initial = (today.year, today.month, today.day)
        DatePicker(self, initial, self._set_batch_start, allowed_weekday=weekday_idx)

    def _open_batch_end_picker(self):
        try:
            weekday_idx = self._get_batch_weekday_index()
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        raw = self.var_batch_end.get().strip()
        initial = None
        if raw:
            try:
                initial = parse_date_ymd(raw)
            except ValueError:
                initial = None
        if not initial:
            today = dt_date.today()
            initial = (today.year, today.month, today.day)
        DatePicker(self, initial, self._set_batch_end, allowed_weekday=weekday_idx)

    def _set_batch_start(self, y: int, mo: int, d: int):
        self.var_batch_start.set(f"{y:04d}/{mo:02d}/{d:02d}")

    def _set_batch_end(self, y: int, mo: int, d: int):
        self.var_batch_end.set(f"{y:04d}/{mo:02d}/{d:02d}")

    # ---------- actions ----------

    def on_hint_stop(self):
        messagebox.showinfo(
            "Note",
            "The browser is controlled by Playwright during a run.\n"
            "To interrupt: close the Playwright browser window manually; the run will fail and return to the app."
        )

    def on_fetch_clubs_records(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            user, pw, _key = self._validate_account()
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        self._set_buttons_running(True)
        self._log("[Clubs] Fetch clubs: logging in and opening Add Record...")

        def task():
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False, slow_mo=60)
                    page = browser.new_page()

                    login_and_wait_home(page, user, pw)
                    record_list_ctx = open_records_list_ctx(page)
                    add_ctx = open_add_record_ctx(record_list_ctx, page)

                    clubs = list_clubs_in_add_dialog(add_ctx)
                    if not clubs:
                        raise RuntimeError("No clubs found in dropdown (Records).")

                    self.clubs_records = clubs
                    self.clubs_reflection = list(clubs)
                    if CONVERSATION_CLUB not in self.clubs_reflection:
                        self.clubs_reflection.append(CONVERSATION_CLUB)
                    self._log(
                        f"[Clubs] Fetched {len(self.clubs_records)} clubs for records, "
                        f"{len(self.clubs_reflection)} for reflection."
                    )
                    browser.close()

                def update_ui():
                    self.combo_rec_club.configure(values=self.clubs_records)
                    self.combo_batch_club.configure(values=self.clubs_records)
                    self.combo_ref_club.configure(values=self.clubs_reflection)
                    if self.clubs_records:
                        if not self.var_rec_club.get():
                            self.var_rec_club.set(self.clubs_records[0])
                        if not self.var_batch_club.get():
                            self.var_batch_club.set(self.clubs_records[0])
                    if self.clubs_reflection and not self.var_ref_club.get():
                        self.var_ref_club.set(self.clubs_reflection[0])
                    self._set_buttons_running(False)

                self.after(0, update_ui)

            except Exception as e:
                self._log(f"[Clubs] ❌ Fetch clubs failed: {e}")
                self.after(0, lambda: self._set_buttons_running(False))

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()

    def on_fetch_clubs_reflection(self):
        self.on_fetch_clubs_records()

    def on_run_record(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            user, pw, key = self._validate_account()
            club, (y, mo, d), theme, c, a, s = self._validate_record()
            date_ymd = f"{y:04d}/{mo:02d}/{d:02d}"
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        self._set_buttons_running(True)
        self._log("[Records] Run started: generating description + autofilling...")

        def task():
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False, slow_mo=60)
                    page = browser.new_page()

                    login_and_wait_home(page, user, pw)
                    record_list_ctx = open_records_list_ctx(page)
                    add_ctx = open_add_record_ctx(record_list_ctx, page)

                    self._log(f"[Records] Selecting club: {club}")
                    select_club_by_text(add_ctx, club)

                    self._log("[Records] Calling DeepSeek to generate record description...")
                    desc = generate_activity_record_deepseek(
                        api_key=key,
                        club_name=club,
                        date_ymd=date_ymd,
                        theme=theme,
                        c_hours=c,
                        a_hours=a,
                        s_hours=s,
                        model="deepseek-chat",
                    )
                    self._set_preview_record(desc)
                    self._log("[Records] DeepSeek description generated.")

                    # Date
                    date_input = add_ctx.locator(
                        "div.layui-form-item:has(label:has-text('Event date')) input"
                    )
                    date_input.click()
                    cal_scope = add_ctx if add_ctx.locator("#layui-laydate1").count() else page
                    select_date_layui(cal_scope, y, mo, d)
                    self._log(f"[Records] Date selected: {date_ymd}")

                    # Theme + hours + description
                    add_ctx.locator(
                        "div.layui-form-item:has(label:has-text('Activity theme')) input"
                    ).fill(theme)

                    add_ctx.locator("input[name='CDuration']").fill(c)
                    add_ctx.locator("input[name='ADuration']").fill(a)
                    add_ctx.locator("input[name='SDuration']").fill(s)

                    # Activity description textarea is named Reflection in Record form
                    add_ctx.locator("textarea[name='Reflection']").fill(desc)

                    add_ctx.locator("button[lay-filter='add']:has-text('Save')").click()
                    self._log("[Records] ✅ Save clicked.")

                    time.sleep(2)
                    browser.close()

                self._log("[Records] ✅ Run finished.")
                self.after(0, lambda: self._set_buttons_running(False))

            except PWTimeoutError as e:
                self._log(f"[Records] ❌ Timeout: {e}")
                self.after(0, lambda: self._set_buttons_running(False))
            except Exception as e:
                self._log(f"[Records] ❌ Error: {e}")
                self.after(0, lambda: self._set_buttons_running(False))

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()

    def on_run_record_batch(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            user, pw, key = self._validate_account()
            club, club_desc, periodic, dates, c, a, s = self._validate_record_batch()
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        self._set_buttons_running(True)
        self._log(f"[Batch] Run started: {len(dates)} weekly records.")

        def task():
            used_themes: list[str] = []
            used_descs: list[str] = []
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False, slow_mo=60)
                    page = browser.new_page()

                    login_and_wait_home(page, user, pw)
                    record_list_ctx = open_records_list_ctx(page)

                    total = len(dates)
                    for idx, dt_item in enumerate(dates, start=1):
                        date_ymd = f"{dt_item.year:04d}/{dt_item.month:02d}/{dt_item.day:02d}"
                        self._log(f"[Batch] ({idx}/{total}) Generating theme + description for {date_ymd}...")
                        theme, desc = generate_weekly_theme_desc_deepseek(
                            api_key=key,
                            club_name=club,
                            date_ymd=date_ymd,
                            club_desc=club_desc,
                            periodic_desc=periodic,
                            used_themes=used_themes,
                            used_descs=used_descs,
                            model="deepseek-chat",
                        )
                        if not theme or not desc:
                            raise RuntimeError(f"DeepSeek returned empty content for {date_ymd}.")

                        used_themes.append(theme)
                        used_descs.append(desc)
                        self._set_preview_record(f"{theme}\n\n{desc}")
                        self._log(f"[Batch] ({idx}/{total}) Filling record for {date_ymd}...")

                        add_ctx = open_add_record_ctx(record_list_ctx, page)
                        select_club_by_text(add_ctx, club)

                        date_input = add_ctx.locator(
                            "div.layui-form-item:has(label:has-text('Event date')) input"
                        )
                        date_input.click()
                        cal_scope = add_ctx if add_ctx.locator("#layui-laydate1").count() else page
                        select_date_layui(cal_scope, dt_item.year, dt_item.month, dt_item.day)

                        add_ctx.locator(
                            "div.layui-form-item:has(label:has-text('Activity theme')) input"
                        ).fill(theme)

                        add_ctx.locator("input[name='CDuration']").fill(c)
                        add_ctx.locator("input[name='ADuration']").fill(a)
                        add_ctx.locator("input[name='SDuration']").fill(s)

                        add_ctx.locator("textarea[name='Reflection']").fill(desc)

                        add_ctx.locator("button[lay-filter='add']:has-text('Save')").click()
                        self._log(f"[Batch] ({idx}/{total}) Save clicked.")

                        try:
                            page.locator("iframe[src*='/Stu/Cas/AddRecord']").wait_for(state="detached", timeout=10000)
                        except Exception:
                            time.sleep(1.2)

                    browser.close()

                self._log("[Batch] Run finished.")
            except PWTimeoutError as e:
                self._log(f"[Batch] Timeout: {e}")
            except Exception as e:
                self._log(f"[Batch] Error: {e}")
            finally:
                self.after(0, lambda: self._set_buttons_running(False))

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()

    def on_run_reflection(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            user, pw, key = self._validate_account()
            club, club_desc, desc_lines, titles, selected = self._validate_reflection()
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        self._set_buttons_running(True)
        self._log(f"[Reflection] Run started: {len(titles)} reflections.")

        def task():
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False, slow_mo=60)
                    page = browser.new_page()

                    login_and_wait_home(page, user, pw)
                    refl_list_ctx = open_reflection_list_ctx(page)

                    total = len(titles)
                    for idx, title in enumerate(titles, start=1):
                        reflection_desc = desc_lines[idx - 1]
                        self._log(f"[Reflection] ({idx}/{total}) Opening add dialog...")
                        add_ctx = open_add_reflection_ctx(refl_list_ctx, page)

                        self._log(f"[Reflection] ({idx}/{total}) Selecting club: {club}")
                        select_club_by_text(add_ctx, club)

                        # Title
                        add_ctx.locator("input[name='Title']").fill(title)

                        # DeepSeek generation
                        self._log(f"[Reflection] ({idx}/{total}) Generating 20-word summary...")
                        summary = generate_reflection_summary_deepseek(
                            api_key=key,
                            club_name=club,
                            title=title,
                            club_desc=club_desc,
                            reflection_desc=reflection_desc,
                            model="deepseek-chat",
                        )
                        self._log(f"[Reflection] ({idx}/{total}) Summary generated.")

                        self._log(f"[Reflection] ({idx}/{total}) Generating reflection content...")
                        reflection_text = generate_reflection_content_deepseek(
                            api_key=key,
                            club_name=club,
                            title=title,
                            club_desc=club_desc,
                            reflection_desc=reflection_desc,
                            model="deepseek-chat",
                        )
                        self._log(f"[Reflection] ({idx}/{total}) Reflection generated.")
                        self._set_preview_reflection(summary, reflection_text)

                        # Fill Content Summary
                        add_ctx.locator("textarea[name='Summary']").fill(summary)

                        # Fill Reflection content (KindEditor)
                        fill_kindeditor_body(add_ctx, reflection_text)

                        # Click Learning Outcomes
                        self._log(f"[Reflection] ({idx}/{total}) Selecting Learning Outcome: {', '.join(selected)}")
                        click_learning_outcomes(add_ctx, selected)

                        # Save
                        add_ctx.locator("button[lay-filter='add']:has-text('Save')").click()
                        self._log(f"[Reflection] ({idx}/{total}) Save clicked.")

                        try:
                            page.locator("iframe[src*='/Stu/Cas/AddReflection']").wait_for(state="detached", timeout=12000)
                        except Exception:
                            time.sleep(1.2)

                    browser.close()

                self._log("[Reflection] Run finished.")
                self.after(0, lambda: self._set_buttons_running(False))

            except PWTimeoutError as e:
                self._log(f"[Reflection] Timeout: {e}")
                self.after(0, lambda: self._set_buttons_running(False))
            except Exception as e:
                self._log(f"[Reflection] Error: {e}")
                self.after(0, lambda: self._set_buttons_running(False))

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()
if __name__ == "__main__":
    app = V42App()
    app.mainloop()

