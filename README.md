Here is a complete `README.md` for your project, based on the source code provided.

---

# WFLA CAS Autofill (V4.3.1)

**WFLA CAS Autofill** is a specialized automation tool designed for students at WFLA to manage their IB CAS (Creativity, Activity, Service) documentation. It automates the generation and submission of activity records and reflections by combining browser automation with the DeepSeek generative AI.

## 🌟 Key Features

* **Browser Automation**: Uses **Playwright** to log into the school system, navigate menus, and interact with complex UI elements like LayUI calendars and KindEditor text areas.
* **AI Content Generation**: Integrates with the **DeepSeek API** to produce high-quality, realistic CAS content (120–180 words for records; 600–750 words for reflections).
* **Weekly Batch Processing**: Automatically calculates weekly dates for a recurring activity and generates unique themes and descriptions for every single week in a date range.
* **Anti-Generic Logic**: The AI is specifically prompted to include concrete evidence (e.g., historical facts, specific tasks, decisions) to avoid academic clichés.
* **Full GUI Interface**: A comprehensive Tkinter-based dashboard featuring an integrated calendar picker and learning outcome selectors.

## 🛠️ Requirements

* **Python 3.8+**
* **Playwright**: For web automation.
* **Requests**: For API communication.
* **DeepSeek API Key**: Required for content generation.
* **Tkinter**: Standard Python GUI library.

## 📦 Installation

1. **Clone the Repository**:
```bash
git clone https://github.com/your-repo/wfla-cas-autofill.git
cd wfla-cas-autofill

```


2. **Install Python Dependencies**:
```bash
pip install playwright requests

```


3. **Install Playwright Browsers**:
```bash
playwright install chromium

```


4. **Run the Application**:
```bash
python CAS_AUTOFILL.py

```



## 🖥️ Usage Guide

### 1. Configuration

In the **Account** section, enter your school system credentials and your DeepSeek API Key.

### 2. Activity Records

* **Single Record**: Select your club, pick a date using the "Pick" button, and enter the CAS hours. Click **Run single record** to generate and submit.
* **Weekly Batch**:
* Select the club and providing a brief description.
* Choose a weekday (e.g., Monday) and a date range (Start/End).
* The tool will automatically iterate through every occurrence of that weekday and generate unique, non-repetitive entries for each date.



### 3. Activity Reflections

* Switch to the **Activity Reflection** tab.
* Input the number of reflections and provide titles for each (one per line).
* Check the relevant **Learning Outcomes** (e.g., Awareness, Collaboration, Ethics).
* Click **Run** to generate long-form (550+ words) reflections that are automatically filled into the system's editor.

## ⚠️ Important Notes

* **API Usage**: Ensure your DeepSeek API account has sufficient credits, as the tool uses multiple prompts to meet word count requirements.
* **Environment**: The tool is designed to work with the specific school system URL: `http://101.227.232.33:8001/`.
* **Review Content**: Always review the AI-generated content before submission to ensure it aligns with your actual experiences.

## ⚖️ License

This project is for educational and administrative assistance purposes only.
