# WFLA CAS Autofill
A Python-based GUI tool for automating the generation and submission of IB CAS (Creativity, Activity, Service) activity records and reflections for the WFLA High School Integrated System. This tool leverages the DeepSeek LLM API to generate CAS-compliant content and uses Playwright for browser automation to interact with the school's web system.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Core Functionality](#core-functionality)
- [Troubleshooting](#troubleshooting)
- [Notes](#notes)

## Overview
This tool is designed to streamline the creation of IB CAS activity records and reflections for students using the WFLA High School Integrated System (`http://101.227.232.33:8001/`). It combines:
- A user-friendly Tkinter GUI for input management
- Playwright-powered browser automation to interact with the school's web interface (including iframe handling, date picker interaction, and form filling)
- DeepSeek API integration to generate CAS-compliant content that meets IB's requirements for specificity, word count, and structure

## Features
### Core Capabilities
- **Automated System Login**: Logs into the WFLA CAS system with user-provided credentials
- **CAS Activity Record Generation**:
  - Single record creation (custom date, club, C/A/S hours)
  - Weekly batch record generation (specified weekday, date range, periodic activity consistency)
- **CAS Reflection Generation**:
  - Concise reflection summaries (18–22 words, single sentence)
  - Detailed reflection content (550+ words, 4–7 paragraphs with concrete details)
- **GUI Tools**:
  - Custom date picker (supports weekday filtering for batch generation)
  - Dropdowns for club selection and weekday choice
  - Secure input fields for credentials/API keys
- **Content Compliance**:
  - Adheres to IB CAS guidelines (specific details, word count ranges, history-related content requirements)
  - Avoids repetitive themes/descriptions for batch generation
  - Automatically fills rich-text editors (KindEditor) and LayUI date pickers

### Technical Features
- Robust iframe handling for nested web content
- Resilient date parsing and calendar navigation (supports LayUI laydate components)
- Error handling for DeepSeek API calls (retry logic for short/invalid content)
- Input validation (date format, integer parsing, word count checks)

## Prerequisites
Before using the tool, ensure you have the following:
1. **Python Version**: Python 3.8 or higher (compatible with Tkinter and Playwright)
2. **System Access**: Valid username/password for the WFLA High School Integrated System (`http://101.227.232.33:8001/`)
3. **DeepSeek API Key**: A valid API key for the DeepSeek Chat API (required for content generation)
4. **Dependencies**:
   - Python packages: `requests`, `playwright`, `tkinter` (included with most Python installations)
   - Playwright-supported browser (automatically installed via Playwright CLI)

## Installation
### Step 1: Download the Code
Save the `CAS_AUTOFILL.py` file to your local machine.

### Step 2: Set Up a Virtual Environment (Optional but Recommended)
```bash
# Create a virtual environment
python -m venv cas_autofill_env

# Activate the environment
# Windows
cas_autofill_env\Scripts\activate
# macOS/Linux
source cas_autofill_env/bin/activate
```

### Step 3: Install Dependencies
```bash
# Install core packages
pip install requests playwright

# Install Tkinter (if missing)
# Ubuntu/Debian
sudo apt-get install python3-tk
# macOS (Homebrew)
brew install python-tk
# Windows: Tkinter is included with official Python installers (enable during setup)
```

### Step 4: Install Playwright Browsers
Playwright requires a browser binary to run automation:
```bash
playwright install
```

## Configuration
### 1. DeepSeek API Key
- Obtain an API key from the [DeepSeek Developer Platform](https://platform.deepseek.com/).
- The key is used to authenticate requests to the DeepSeek Chat API (`https://api.deepseek.com/v1/chat/completions`).

### 2. WFLA System Credentials
- Your username and password for the WFLA High School Integrated System (`http://101.227.232.33:8001/`).

## Usage
### 1. Launch the Tool
Run the script from your activated virtual environment:
```bash
python CAS_AUTOFILL.py
```
A GUI window titled `WFLA CAS Autofill - V4.3.1 (Records + Reflection + Weekly Batch)` will open.

### 2. Basic Setup
1. Enter your **Username** (WFLA system account), **Password** (WFLA system password), and **DeepSeek API Key** in the "Account" section.
2. Click the relevant tab to access either **Activity Records** or **Activity Reflection** functionality.

### 3. Activity Records (Single Record)
1. Click **Fetch clubs** to load the list of available clubs from the WFLA system.
2. Select a club from the dropdown.
3. Click **Pick** next to the "Date (calendar)" field to open the custom date picker and select a valid date.
4. Enter an optional **Activity theme** (or let the DeepSeek API generate one if using batch mode).
5. Input hours for **C (Creativity)**, **A (Activity)**, and **S (Service)**.
6. Click **Run single record** to generate the CAS record (via DeepSeek) and submit it to the WFLA system.

### 4. Activity Records (Weekly Batch)
1. Select a club from the "Club" dropdown.
2. Enter a **Club description** (to guide LLM content generation).
3. Select a **Weekday** (e.g., Monday) for recurring weekly records.
4. Click **Pick** to set a **Start date** and **End date** for the batch (only dates matching the selected weekday will be included).
5. Enter a **Periodic activity** description (for consistent weekly activity context).
6. Input C/A/S hours (applied to all batch records).
7. Run the batch generation (button logic included in the code—triggers weekly record creation with unique themes/descriptions).

### 5. Activity Reflection
1. Navigate to the **Activity Reflection** tab (UI elements for reflection input are included in the codebase).
2. Enter club details, reflection focus, and title.
3. Generate a concise **reflection summary** (18–22 words) or detailed **reflection content** (550+ words) via the DeepSeek API.
4. The tool will auto-fill the reflection content into the WFLA system's rich-text editor (KindEditor).

## Core Functionality
### Key Modules
| Module | Purpose |
|--------|---------|
| `parse_date_ymd` | Validates and parses dates in `YYYY/MM/DD` format |
| `iter_weekly_dates` | Generates weekly dates between a start/end range (for batch generation) |
| `select_date_layui` | Automates interaction with the LayUI calendar component in the WFLA system |
| `deepseek_chat` | Base function for calling the DeepSeek Chat API (handles auth, payload, and error checking) |
| `generate_activity_record_deepseek` | Generates 120–180 word CAS activity records (80% concrete details) |
| `generate_weekly_theme_desc_deepseek` | Generates unique weekly themes (4–10 words) and descriptions (80+ words) |
| `generate_reflection_summary_deepseek` | Generates 18–22 word reflection summaries (single sentence) |
| `generate_reflection_content_deepseek` | Generates 550+ word detailed reflections (4–7 paragraphs, 70–85% concrete details) |
| `login_and_wait_home` | Automates login to the WFLA system and verifies successful navigation |
| `fill_kindeditor_body` | Populates the KindEditor rich-text iframe with generated content |
| `DatePicker` | Custom Tkinter date picker for GUI date selection |
| `V42App` | Main Tkinter GUI application class (handles all UI elements and user interactions) |

### Content Generation Rules
The LLM-generated content adheres to strict IB CAS guidelines:
- **Activity Records**: 120–180 words, 1–2 paragraphs, 80% concrete details (e.g., materials used, specific tasks, questions addressed). For history-related activities, includes 2+ specific historical facts/terms.
- **Weekly Themes**: 4–10 words (no dates/quotes), unique (avoids last 8 themes), paired with 80+ word descriptions with 3+ concrete details.
- **Reflections**: 550+ words (4–7 paragraphs), 70–85% concrete details (e.g., feedback received, task changes, specific decisions). History-related reflections include 2+ historical takeaways and their impact on thinking.
- **Summaries**: 18–22 words, single sentence, ends with punctuation.

## Troubleshooting
### Common Issues & Fixes
1. **Playwright Timeout Errors**
   - Check network connectivity to the WFLA system.
   - Increase timeout values in the code (e.g., `wait_for` calls, `_find_iframe_src_contains` timeout).
   - Verify the system’s DOM structure (iframes/locators may have changed).

2. **DeepSeek API Errors**
   - Confirm your API key is valid and has remaining quota.
   - Check network access to `https://api.deepseek.com`.
   - Verify the API payload (model name, temperature, max_tokens) is compatible with DeepSeek’s API specs.

3. **Club List Fetch Failure**
   - Ensure login credentials are correct (the tool validates login via "WFLA高中综合系统" text detection).
   - Check iframe locators for the club selection dialog (update CSS/xpath if the system UI changes).

4. **Date Picker Issues**
   - Ensure the selected date is valid (e.g., no February 30th).
   - Verify the LayUI calendar locator (`#layui-laydate1`) is still valid for the system.

5. **GUI Unresponsive**
   - Check Tkinter installation (run `python -m tkinter` to test).
   - Close other Tkinter instances or restart the tool.

## Notes
1. **System Compatibility**: The tool is tailored to the WFLA system’s specific DOM structure (iframe paths, locators, and UI components). If the system is updated, you may need to adjust CSS/xpath locators in the code.
2. **DeepSeek API Limits**: Monitor your API usage to avoid rate limits or quota exhaustion. The tool includes retry logic (3–4 attempts) for short/invalid content.
3. **IB Compliance**: While the tool generates CAS-compliant content, always review and edit the output to align with your actual activities (IB requires authentic reflection/records).
4. **Security**: Credentials and API keys are stored in memory only (never saved to disk). Close the tool when not in use to protect sensitive data.
5. **Date Validation**: The tool validates dates for valid months/days/leap years—ensure input dates are within valid ranges.

## License
This project is provided as-is for educational use within WFLA. No official license is assigned—modify and distribute at your own discretion, adhering to IB guidelines and school policies.
