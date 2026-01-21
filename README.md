## CAS Autofill V5.0.0 README

This program is a sophisticated automation tool designed to streamline the process of filling out **IB CAS (Creativity, Activity, Service)** records and reflections on the WFLA high school system. It leverages **Playwright** for web automation and the **DeepSeek API** to generate high-quality, specific, and realistic prose that meets IB requirements.

---

### Key Features

* **Single Record Entry:** Quickly fill out a one-time activity record with a custom theme and automatically generated description.
* **Weekly Batch Records:** Generate and fill multiple weekly records for a specific date range (e.g., every Monday from September to December).
* **High-Quality Reflection Generation:** Automatically generates long-form reflections (600–750 words) and 20-word summaries based on user-provided titles and descriptions.
* **Intelligent Content:** The DeepSeek integration ensures that text is concrete, includes specific details/examples, and avoids generic clichés.
* **Learning Outcome Support:** Automatically selects the correct checkboxes for CAS Learning Outcomes.
* **Interactive Calendar:** Built-in date picker to ensure correct date formatting for the WFLA system.

---

### Prerequisites

Before running the program, you must have the following installed:

1. **Python 3.8 or higher:** [Download Python](https://www.python.org/downloads/)
2. **DeepSeek API Key:** You need an active API key from [DeepSeek](https://platform.deepseek.com/).
3. **Required Python Packages:** You will need to install the dependencies listed below.

---

### Installation Instructions

#### For Windows Users

1. **Install Python:** Download the installer from python.org. Ensure you check the box that says **"Add Python to PATH"** during installation.
2. **Open Command Prompt:** Press `Win + R`, type `cmd`, and hit Enter.
3. **Install Dependencies:** Run the following commands:
```bash
pip install requests playwright
playwright install chromium

```


4. **Run the Program:** Navigate to the folder containing `CAS_AUTOFILL.py` and run:
```bash
python CAS_AUTOFILL.py

```



#### For Mac Users

1. **Install Python:** macOS usually comes with Python, but it's better to install the latest version via [Homebrew](https://brew.sh/) or the official installer.
2. **Open Terminal:** Press `Cmd + Space`, type `Terminal`, and hit Enter.
3. **Install Dependencies:** Run the following commands:
```bash
pip3 install requests playwright
playwright install chromium

```


4. **Run the Program:** Navigate to the folder containing `CAS_AUTOFILL.py` and run:
```bash
python3 CAS_AUTOFILL.py

```



---

### How to Use

#### 1. Setup

* Enter your **WFLA System Username** and **Password**.
* Paste your **DeepSeek API Key**.
* Click **"Fetch clubs"**. This will open a browser window, log you in, and retrieve the list of clubs you are currently enrolled in.

#### 2. Activity Records (Single or Batch)

* **Single Record:** Select the club, pick a date, enter a theme (e.g., "Weekly Debate Workshop"), and set the C/A/S hours. Click **"Run single record"**.
* **Weekly Batch:** This is ideal for recurring clubs.
* Select the club and providing a brief description of what the club usually does.
* Pick the start and end dates (they must be the same weekday).
* The program will iterate through every week in that range, generating a **unique** theme and description for each entry so they don't look repetitive.



#### 3. Activity Reflection

* Select your club and set the number of reflections you want to create.
* Provide a **Club Description** and a **Title** for each reflection (one per line).
* (Optional) Provide a brief focus for each reflection in the **Reflection Descriptions** box.
* Select the relevant **Learning Outcomes**.
* Click **"Run reflection autofill"**. The program will generate a ~600-word reflection and a 20-word summary for each title provided.

---

### Troubleshooting & Tips

* **Browser Control:** When the program is "Running," a Chromium browser window will appear. **Do not close it manually** unless you want to abort the process. The program needs to control this window to fill the forms.
* **API Timeouts:** Generating 600+ words of high-quality text can take 30–60 seconds per reflection. Please be patient.
* **WFLA System Changes:** If the school system updates its website layout (UI), the automation might fail. Ensure you are using the latest version of this script.
* **Writing Style:** For the best results, provide a specific "Club Description." This helps the AI generate more realistic details about your specific activities.

---

### Disclaimer

*This tool is intended to assist with the administrative burden of data entry. It is the user's responsibility to ensure that all generated content accurately reflects their actual CAS activities and adheres to their school's academic honesty policy.*

### Warning

*Using Deepseek to generate illegal contents (such as sex, drugs, violence, or politically sensitive contents) is strictly prohibited.*
