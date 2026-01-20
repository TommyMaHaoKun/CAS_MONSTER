import threading
import queue
import re
import time
import requests
import tkinter as tk
from tkinter import ttk, messagebox

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

URL = "http://101.227.232.33:8001/"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_CHAT_ENDPOINT = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"


# -----------------------------
# Core helpers (from V4.0 logic)
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
    core_prompt = f"You are going to write an activity record for {club_name} club, and it should be more than 100 words. It should be informative, not listing cliches."

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


def list_clubs_in_add_dialog(add_ctx):
    # Open dropdown and read dd[lay-value]
    club_input = add_ctx.locator(
        "div.layui-form-item:has(label:has-text('Select a club')) "
        "div.layui-form-select input[placeholder='Please select']"
    )
    club_input.wait_for(timeout=10000)
    club_input.click()

    options = add_ctx.locator("dd[lay-value]").filter(has_not=add_ctx.locator(".layui-select-tips"))
    options.first.wait_for(timeout=10000)
    texts = [t.strip() for t in options.all_inner_texts() if t.strip()]
    return texts


def select_club_by_text(add_ctx, club_name: str):
    club_input = add_ctx.locator(
        "div.layui-form-item:has(label:has-text('Select a club')) "
        "div.layui-form-select input[placeholder='Please select']"
    )
    club_input.wait_for(timeout=10000)
    club_input.click()
    add_ctx.locator(f"dd:has-text('{club_name}')").click()


# -----------------------------
# GUI App
# -----------------------------
class V41App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WFLA CAS Autofill – V4.1 (DeepSeek)")
        self.geometry("980x640")
        self.minsize(920, 600)

        self.log_q = queue.Queue()
        self.worker = None
        self.clubs = []

        self._build_style()
        self._build_ui()
        self.after(100, self._poll_logs)

    def _build_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", font=("Segoe UI", 10))
        style.configure("TCombobox", font=("Segoe UI", 10))
        style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))

    def _build_ui(self):
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        # Top split: left form, right preview/log
        top = ttk.Frame(root)
        top.pack(fill="both", expand=True)

        left = ttk.Frame(top)
        left.pack(side="left", fill="both", expand=False)

        right = ttk.Frame(top)
        right.pack(side="right", fill="both", expand=True, padx=(14, 0))

        # --- Left: Inputs
        ttk.Label(left, text="Input", style="Header.TLabel").pack(anchor="w", pady=(0, 8))

        lf1 = ttk.Labelframe(left, text="Account", padding=10)
        lf1.pack(fill="x", pady=(0, 10))

        self.var_user = tk.StringVar()
        self.var_pass = tk.StringVar()
        self.var_dskey = tk.StringVar()

        self._row(lf1, 0, "Username", lambda p: ttk.Entry(p, textvariable=self.var_user, width=34))
        self._row(lf1, 1, "Password", lambda p: ttk.Entry(p, textvariable=self.var_pass, show="•", width=34))
        self._row(lf1, 2, "DeepSeek API Key", lambda p: ttk.Entry(p, textvariable=self.var_dskey, show="•", width=34))


        lf2 = ttk.Labelframe(left, text="Activity", padding=10)
        lf2.pack(fill="x", pady=(0, 10))

        self.var_date = tk.StringVar(value="2025/11/19")
        self.var_theme = tk.StringVar(value="A Lecture about the Great Depression")
        self.var_c = tk.StringVar(value="2")
        self.var_a = tk.StringVar(value="0")
        self.var_s = tk.StringVar(value="2")

        self.var_club = tk.StringVar()

        self.combo_club = self._row(
            lf2, 0, "Club",
            lambda p: ttk.Combobox(p, textvariable=self.var_club, width=31, state="readonly", values=[])
        )

        self._row(lf2, 1, "Date (YYYY/MM/DD)", lambda p: ttk.Entry(p, textvariable=self.var_date, width=34))
        self._row(lf2, 2, "Activity theme", lambda p: ttk.Entry(p, textvariable=self.var_theme, width=34))


        def build_hours(p):
            hours_frame = ttk.Frame(p)
            ttk.Label(hours_frame, text="C").pack(side="left")
            ttk.Entry(hours_frame, textvariable=self.var_c, width=6).pack(side="left", padx=(4, 14))
            ttk.Label(hours_frame, text="A").pack(side="left")
            ttk.Entry(hours_frame, textvariable=self.var_a, width=6).pack(side="left", padx=(4, 14))
            ttk.Label(hours_frame, text="S").pack(side="left")
            ttk.Entry(hours_frame, textvariable=self.var_s, width=6).pack(side="left", padx=(4, 0))
            return hours_frame

        self._row(lf2, 3, "Hours (C/A/S)", build_hours)


        # Buttons
        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(6, 0))

        self.btn_fetch = ttk.Button(btns, text="Fetch clubs", command=self.on_fetch_clubs)
        self.btn_fetch.pack(side="left", ipadx=8)

        self.btn_run = ttk.Button(btns, text="Run autofill", style="Accent.TButton", command=self.on_run)
        self.btn_run.pack(side="left", padx=(10, 0), ipadx=8)

        self.btn_stop = ttk.Button(btns, text="Close browser (manual)", command=self.on_hint_stop)
        self.btn_stop.pack(side="left", padx=(10, 0), ipadx=8)

        # --- Right: Description preview + logs
        ttk.Label(right, text="Generated Description (Preview)", style="Header.TLabel").pack(anchor="w")

        self.txt_preview = tk.Text(right, height=14, wrap="word")
        self.txt_preview.pack(fill="both", expand=False, pady=(6, 10))
        self.txt_preview.configure(state="disabled")

        ttk.Label(right, text="Logs", style="Header.TLabel").pack(anchor="w")
        self.txt_log = tk.Text(right, height=16, wrap="word")
        self.txt_log.pack(fill="both", expand=True, pady=(6, 0))
        self.txt_log.configure(state="disabled")

        # Footer
        footer = ttk.Label(root, text="V4.1 GUI – Playwright + DeepSeek (single record per run)")
        footer.pack(anchor="w", pady=(10, 0))

    def _row(self, parent, r, label, widget_builder):
        """
        widget_builder: function(row_parent) -> widget
        Always create the widget INSIDE the row frame (no re-parenting issues).
        """
        row = ttk.Frame(parent)
        row.grid(row=r, column=0, sticky="ew", pady=4)
        parent.columnconfigure(0, weight=1)

        row.columnconfigure(1, weight=1)

        ttk.Label(row, text=label, width=20).grid(row=0, column=0, sticky="w")
        widget = widget_builder(row)
        widget.grid(row=0, column=1, sticky="ew")
        return widget



    def _log(self, msg: str):
        self.log_q.put(msg)

    def _set_preview(self, text: str):
        self.log_q.put(("__PREVIEW__", text))

    def _poll_logs(self):
        try:
            while True:
                item = self.log_q.get_nowait()
                if isinstance(item, tuple) and item[0] == "__PREVIEW__":
                    self.txt_preview.configure(state="normal")
                    self.txt_preview.delete("1.0", "end")
                    self.txt_preview.insert("end", item[1])
                    self.txt_preview.configure(state="disabled")
                else:
                    self.txt_log.configure(state="normal")
                    self.txt_log.insert("end", str(item) + "\n")
                    self.txt_log.see("end")
                    self.txt_log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(120, self._poll_logs)

    def _validate_inputs(self, need_club: bool):
        user = self.var_user.get().strip()
        pw = self.var_pass.get().strip()
        key = self.var_dskey.get().strip()
        date = self.var_date.get().strip()
        theme = self.var_theme.get().strip()
        c = self.var_c.get().strip()
        a = self.var_a.get().strip()
        s = self.var_s.get().strip()
        club = self.var_club.get().strip()

        if not user or not pw:
            raise ValueError("Username/Password cannot be empty.")
        if not key:
            raise ValueError("DeepSeek API Key cannot be empty.")
        parse_date_ymd(date)  # validate format
        if not theme:
            raise ValueError("Activity theme cannot be empty.")
        for name, val in [("C", c), ("A", a), ("S", s)]:
            if not re.match(r"^\d+(\.\d+)?$", val):
                raise ValueError(f"{name} hours must be a number.")
        if need_club and not club:
            raise ValueError("Please fetch and select a club first.")
        return user, pw, key, date, theme, c, a, s, club

    def _set_buttons(self, running: bool):
        self.btn_fetch.configure(state=("disabled" if running else "normal"))
        self.btn_run.configure(state=("disabled" if running else "normal"))

    def on_hint_stop(self):
        messagebox.showinfo(
            "Note",
            "The browser is controlled by Playwright during a run.\n"
            "If you want to stop, close the browser window manually; the run will fail and return to the app."
        )

    def on_fetch_clubs(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            user, pw, _, date, theme, c, a, s, _club = self._validate_inputs(need_club=False)
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        self._set_buttons(True)
        self._log("Fetching clubs: logging in and opening Add Record...")

        def task():
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False, slow_mo=60)
                    page = browser.new_page()

                    page.goto(URL, wait_until="domcontentloaded")
                    page.fill("input[placeholder='Please enter your login account']", user)
                    page.fill("input[placeholder='Please enter your password']", pw)
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

                    clubs = list_clubs_in_add_dialog(add_ctx)
                    if not clubs:
                        raise RuntimeError("No clubs found in dropdown.")

                    self._log(f"Fetched {len(clubs)} clubs.")
                    self.clubs = clubs

                    # Close browser after fetching
                    browser.close()

                # Update combobox on main thread
                def update_ui():
                    self.combo_club.configure(values=self.clubs)
                    if self.clubs:
                        self.var_club.set(self.clubs[0])
                    self._set_buttons(False)

                self.after(0, update_ui)

            except Exception as e:
                self._log(f"❌ Fetch clubs failed: {e}")
                self.after(0, lambda: self._set_buttons(False))

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()

    def on_run(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            user, pw, key, date, theme, c, a, s, club = self._validate_inputs(need_club=True)
            y, mo, d = parse_date_ymd(date)
            date_ymd = f"{y:04d}/{mo:02d}/{d:02d}"
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        self._set_buttons(True)
        self._log("Run started: logging in, generating description (DeepSeek), then autofilling...")

        def task():
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False, slow_mo=60)
                    page = browser.new_page()

                    # Login + navigate
                    page.goto(URL, wait_until="domcontentloaded")
                    page.fill("input[placeholder='Please enter your login account']", user)
                    page.fill("input[placeholder='Please enter your password']", pw)
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

                    # Select club (GUI-chosen)
                    self._log(f"Selecting club: {club}")
                    select_club_by_text(add_ctx, club)

                    # DeepSeek generation
                    self._log("Calling DeepSeek to generate description...")
                    description = generate_activity_record_deepseek(
                        api_key=key,
                        club_name=club,
                        date_ymd=date_ymd,
                        theme=theme,
                        c_hours=c,
                        a_hours=a,
                        s_hours=s,
                        model="deepseek-chat",
                    )
                    self._set_preview(description)
                    self._log("DeepSeek description generated.")

                    # Date
                    date_input = add_ctx.locator(
                        "div.layui-form-item:has(label:has-text('Event date')) input"
                    )
                    date_input.click()

                    cal_scope = add_ctx if add_ctx.locator("#layui-laydate1").count() else page
                    select_date_layui(cal_scope, y, mo, d)
                    self._log(f"Date selected: {date_ymd}")

                    # Theme + hours + description
                    add_ctx.locator(
                        "div.layui-form-item:has(label:has-text('Activity theme')) input"
                    ).fill(theme)

                    add_ctx.locator("input[name='CDuration']").fill(c)
                    add_ctx.locator("input[name='ADuration']").fill(a)
                    add_ctx.locator("input[name='SDuration']").fill(s)
                    add_ctx.locator("textarea[name='Reflection']").fill(description)

                    # Save
                    add_ctx.locator("button[lay-filter='add']:has-text('Save')").click()
                    self._log("✅ Save clicked.")

                    time.sleep(2)
                    browser.close()

                self._log("✅ Run finished.")
                self.after(0, lambda: self._set_buttons(False))

            except PWTimeoutError as e:
                self._log(f"❌ Timeout: {e}")
                self.after(0, lambda: self._set_buttons(False))
            except Exception as e:
                self._log(f"❌ Error: {e}")
                self.after(0, lambda: self._set_buttons(False))

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()


if __name__ == "__main__":
    app = V41App()
    app.mainloop()
