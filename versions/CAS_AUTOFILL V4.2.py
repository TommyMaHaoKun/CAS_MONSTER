import threading
import queue
import re
import time
import html
import requests
import tkinter as tk
from tkinter import ttk, messagebox

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

URL = "http://101.227.232.33:8001/"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_CHAT_ENDPOINT = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"


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
    return y, mo, d


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
    user_content = (
        f"Write an IB CAS Activity Record for the club '{club_name}'.\n"
        f"Context:\n"
        f"- Date: {date_ymd}\n"
        f"- Activity theme: {theme}\n"
        f"- Hours: C={c_hours}, A={a_hours}, S={s_hours}\n\n"
        f"Requirements:\n"
        f"- English, realistic high school tone.\n"
        f"- 1–2 coherent paragraphs, no bullet points.\n"
        f"- Include: what I did, what I learned, challenges, impact, next steps.\n"
        f"- 120–180 words (must be >= 100 words).\n"
        f"- Avoid generic clichés. Be specific."
    )

    messages = [
        {"role": "system", "content": "You write realistic CAS records for IB students. Be specific, avoid clichés."},
        {"role": "user", "content": user_content},
    ]

    last_text = ""
    for _ in range(3):
        resp = deepseek_chat(api_key, model, messages, temperature=0.55, max_tokens=360)
        text = resp["choices"][0]["message"]["content"].strip()
        last_text = text
        if word_count(text) >= 100:
            return text
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": "Too short. Expand to 120–180 words, keep specific and realistic."})

    return last_text


def generate_reflection_summary_deepseek(
    api_key: str,
    club_name: str,
    title: str,
    model: str = "deepseek-chat",
) -> str:
    user_content = (
        f"Write a concise English summary for an IB CAS reflection.\n"
        f"Club: {club_name}\n"
        f"Title: {title}\n\n"
        f"Hard requirements:\n"
        f"- Exactly ONE sentence.\n"
        f"- About 20 words (target 18–22 words).\n"
        f"- No bullet points. No quotes."
    )

    messages = [
        {"role": "system", "content": "You write concise, natural academic summaries."},
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
    model: str = "deepseek-chat",
) -> str:
    user_content = (
        f"Write an IB CAS Activity Reflection in English.\n"
        f"Club: {club_name}\n"
        f"Title: {title}\n\n"
        f"Hard requirements:\n"
        f"- At least 550 words (target 600–750).\n"
        f"- 4–7 paragraphs, no bullet points.\n"
        f"- Include: context, what I did, what I learned, challenges, evidence/examples, impact, next steps.\n"
        f"- Avoid generic phrases; use concrete details appropriate for a high school club."
    )

    messages = [
        {"role": "system", "content": "You write long-form CAS reflections for IB students with specific details."},
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
    return [t.strip() for t in options.all_inner_texts() if t.strip()]


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

    def __init__(self):
        super().__init__()
        self.title("WFLA CAS Autofill – V4.2 (Records + Reflection + DeepSeek)")
        self.geometry("1080x700")
        self.minsize(980, 640)

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
        left.pack(side="left", fill="both", expand=False)

        right = ttk.Frame(top)
        right.pack(side="right", fill="both", expand=True, padx=(14, 0))

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

        self.tabs = ttk.Notebook(left)
        self.tabs.pack(fill="x", expand=False)

        tab_rec = ttk.Frame(self.tabs, padding=10)
        tab_ref = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab_rec, text="Activity Records")
        self.tabs.add(tab_ref, text="Activity Reflection")

        # --- Records tab
        lf_rec = ttk.Labelframe(tab_rec, text="Record", padding=10)
        lf_rec.pack(fill="x")

        self.var_rec_club = tk.StringVar()
        self.var_rec_date = tk.StringVar(value="2025/11/19")
        self.var_rec_theme = tk.StringVar(value="A Lecture about the Great Depression")
        self.var_rec_c = tk.StringVar(value="2")
        self.var_rec_a = tk.StringVar(value="0")
        self.var_rec_s = tk.StringVar(value="2")

        self.combo_rec_club = self._row(
            lf_rec, 0, "Club",
            lambda p: ttk.Combobox(p, textvariable=self.var_rec_club, width=31, state="readonly", values=[])
        )
        self._row(lf_rec, 1, "Date (YYYY/MM/DD)", lambda p: ttk.Entry(p, textvariable=self.var_rec_date, width=34))
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
        self.btn_rec_fetch = ttk.Button(rec_btns, text="Fetch clubs", command=self.on_fetch_clubs_records)
        self.btn_rec_fetch.pack(side="left", ipadx=8)
        self.btn_rec_run = ttk.Button(rec_btns, text="Run record autofill", style="Accent.TButton", command=self.on_run_record)
        self.btn_rec_run.pack(side="left", padx=(10, 0), ipadx=8)

        # --- Reflection tab
        lf_ref = ttk.Labelframe(tab_ref, text="Reflection", padding=10)
        lf_ref.pack(fill="x")

        self.var_ref_club = tk.StringVar()
        self.var_ref_title = tk.StringVar(value="Reflection on the Great Depression Lecture")

        self.combo_ref_club = self._row(
            lf_ref, 0, "Club",
            lambda p: ttk.Combobox(p, textvariable=self.var_ref_club, width=31, state="readonly", values=[])
        )
        self._row(lf_ref, 1, "Title", lambda p: ttk.Entry(p, textvariable=self.var_ref_title, width=34))

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
        self.btn_ref_fetch = ttk.Button(ref_btns, text="Fetch clubs", command=self.on_fetch_clubs_reflection)
        self.btn_ref_fetch.pack(side="left", ipadx=8)
        self.btn_ref_run = ttk.Button(ref_btns, text="Run reflection autofill", style="Accent.TButton", command=self.on_run_reflection)
        self.btn_ref_run.pack(side="left", padx=(10, 0), ipadx=8)

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
        ttk.Label(footer, text="V4.2 – Records + Reflection (DeepSeek)").pack(side="left", padx=(12, 0))

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
        y, mo, d = parse_date_ymd(date)
        if not theme:
            raise ValueError("Activity theme cannot be empty.")
        for name, val in [("C", c), ("A", a), ("S", s)]:
            if not re.match(r"^\d+(\.\d+)?$", val):
                raise ValueError(f"{name} hours must be a number.")
        return club, (y, mo, d), theme, c, a, s

    def _validate_reflection(self):
        club = self.var_ref_club.get().strip()
        title = self.var_ref_title.get().strip()
        if not club:
            raise ValueError("Please fetch and select a club (Reflection).")
        if not title:
            raise ValueError("Title cannot be empty.")
        selected = [k for k, v in self.outcome_vars.items() if v.get()]
        if not selected:
            raise ValueError("Select at least one Learning Outcome.")
        return club, title, selected

    def _set_buttons_running(self, running: bool):
        state = "disabled" if running else "normal"
        for b in [self.btn_rec_fetch, self.btn_rec_run, self.btn_ref_fetch, self.btn_ref_run]:
            b.configure(state=state)

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
        self._log("[Records] Fetch clubs: logging in and opening Add Record...")

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
                    self._log(f"[Records] Fetched {len(clubs)} clubs.")
                    browser.close()

                def update_ui():
                    self.combo_rec_club.configure(values=self.clubs_records)
                    if self.clubs_records:
                        self.var_rec_club.set(self.clubs_records[0])
                    self._set_buttons_running(False)

                self.after(0, update_ui)

            except Exception as e:
                self._log(f"[Records] ❌ Fetch clubs failed: {e}")
                self.after(0, lambda: self._set_buttons_running(False))

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()

    def on_fetch_clubs_reflection(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            user, pw, _key = self._validate_account()
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        self._set_buttons_running(True)
        self._log("[Reflection] Fetch clubs: logging in and opening Add Reflection...")

        def task():
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False, slow_mo=60)
                    page = browser.new_page()

                    login_and_wait_home(page, user, pw)
                    refl_list_ctx = open_reflection_list_ctx(page)
                    add_ctx = open_add_reflection_ctx(refl_list_ctx, page)

                    clubs = list_clubs_in_add_dialog(add_ctx)
                    if not clubs:
                        raise RuntimeError("No clubs found in dropdown (Reflection).")

                    self.clubs_reflection = clubs
                    self._log(f"[Reflection] Fetched {len(clubs)} clubs.")
                    browser.close()

                def update_ui():
                    self.combo_ref_club.configure(values=self.clubs_reflection)
                    if self.clubs_reflection:
                        self.var_ref_club.set(self.clubs_reflection[0])
                    self._set_buttons_running(False)

                self.after(0, update_ui)

            except Exception as e:
                self._log(f"[Reflection] ❌ Fetch clubs failed: {e}")
                self.after(0, lambda: self._set_buttons_running(False))

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()

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

    def on_run_reflection(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            user, pw, key = self._validate_account()
            club, title, selected = self._validate_reflection()
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        self._set_buttons_running(True)
        self._log("[Reflection] Run started: generating summary + reflection + autofilling...")

        def task():
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False, slow_mo=60)
                    page = browser.new_page()

                    login_and_wait_home(page, user, pw)
                    refl_list_ctx = open_reflection_list_ctx(page)
                    add_ctx = open_add_reflection_ctx(refl_list_ctx, page)

                    self._log(f"[Reflection] Selecting club: {club}")
                    select_club_by_text(add_ctx, club)

                    # Title
                    add_ctx.locator("input[name='Title']").fill(title)

                    # DeepSeek generation
                    self._log("[Reflection] Calling DeepSeek to generate 20-word summary...")
                    summary = generate_reflection_summary_deepseek(
                        api_key=key,
                        club_name=club,
                        title=title,
                        model="deepseek-chat",
                    )
                    self._log("[Reflection] Summary generated.")

                    self._log("[Reflection] Calling DeepSeek to generate >= 550-word reflection...")
                    reflection_text = generate_reflection_content_deepseek(
                        api_key=key,
                        club_name=club,
                        title=title,
                        model="deepseek-chat",
                    )
                    self._log("[Reflection] Reflection generated.")
                    self._set_preview_reflection(summary, reflection_text)

                    # Fill Content Summary
                    add_ctx.locator("textarea[name='Summary']").fill(summary)

                    # Fill Reflection content (KindEditor)
                    fill_kindeditor_body(add_ctx, reflection_text)

                    # Click Learning Outcomes
                    self._log(f"[Reflection] Selecting Learning Outcome: {', '.join(selected)}")
                    click_learning_outcomes(add_ctx, selected)

                    # Save
                    add_ctx.locator("button[lay-filter='add']:has-text('Save')").click()
                    self._log("[Reflection] ✅ Save clicked.")

                    time.sleep(2)
                    browser.close()

                self._log("[Reflection] ✅ Run finished.")
                self.after(0, lambda: self._set_buttons_running(False))

            except PWTimeoutError as e:
                self._log(f"[Reflection] ❌ Timeout: {e}")
                self.after(0, lambda: self._set_buttons_running(False))
            except Exception as e:
                self._log(f"[Reflection] ❌ Error: {e}")
                self.after(0, lambda: self._set_buttons_running(False))

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()


if __name__ == "__main__":
    app = V42App()
    app.mainloop()
