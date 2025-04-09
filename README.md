# Obsidian to Anki Grammar Sync

A Python script to automatically generate and update Anki flashcards from Japanese grammar notes stored in Obsidian, and generate study summary reports back into Obsidian.

## Overview

This script bridges the gap between detailed note-taking in Obsidian and spaced repetition practice in Anki for learning Japanese grammar. It scans your Obsidian vault for specific notes, extracts grammar information from YAML frontmatter, creates/updates corresponding Anki cards, retrieves study statistics from Anki, and generates a summary report in Obsidian highlighting recent studies, struggling points, and items due soon.

## Features

- **Obsidian Vault Scanning:** Scans a specified directory for Markdown notes (`.md`).
- **Tag-Based Detection:** Identifies relevant grammar notes based on a specific tag (e.g., `#grammarpoint`) in the YAML frontmatter.
- **YAML Data Extraction:** Parses YAML frontmatter to extract fields like `ankiExpression`, `englishSituationPrompt`, `meaning`, `structure`, examples, usage notes, etc.
- **Multiple Prompts:** Supports multiple `englishSituationPrompt` entries in the YAML, creating a separate Anki card for each prompt associated with the same grammar point (`AnkiExpression`).
- **Anki Integration:** Uses the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on to interact with a running Anki instance.
- **Custom Note Type:** Designed to work with a specific, user-created Anki Note Type for structured data storage.
- **Sub-Deck Creation:** Creates notes within a specified hierarchical deck structure in Anki (e.g., `Japanese::Grammar::Your Deck`).
- **Note Updates:** Checks the modification time of Obsidian notes against timestamps stored in Anki notes and updates Anki notes if the Obsidian source is newer (using a delete-and-re-add strategy).
- **Study Analysis:** Retrieves review history (lapses, ease factor, due dates) for synced notes from Anki.
- **Obsidian Report Generation:** Creates a Markdown summary file in Obsidian (`Grammar Study Summary.md`) listing recently studied, struggling, and due-soon grammar points, with `obsidian://` links back to the source notes.
- **File Logging:** Generates a detailed log file (`anki_sync_log.txt`) for monitoring and troubleshooting.

## Requirements

- **Python 3.x:** The script is written in Python 3.
- **Anki:** The Anki desktop application must be installed.
- **AnkiConnect Add-on:** The AnkiConnect add-on must be installed and enabled in Anki. (Add-on code: `2055492159`)
- **Python Libraries:** `requests` and `PyYAML`.

## Setup Instructions

**1. Install AnkiConnect:**
    - Open Anki.
    - Go to `Tools` > `Add-ons`.
    - Click `Get Add-ons...`.
    - Enter the code `2055492159` and click `OK`.
    - Restart Anki.
    - Ensure AnkiConnect is enabled in the Add-ons list.

**2. Create Custom Anki Note Type (CRITICAL STEP):**

    You **must** manually create a specific Note Type in Anki *before* running the script for the first time.
    - Go to `Tools` > `Manage Note Types...` > `Add`.
    - Choose `Clone: Basic` and click `OK`.
    - Name the new note type **exactly** what is specified in the script's `ANKI_NOTE_TYPE_NAME` variable (default is `Obsidian Grammar Sync`).
    - Select the new note type and click `Fields...`.
    - Ensure the following fields exist, in the desired order (having `AnkiExpression` or `EnglishSituationPrompt` first is recommended), and are named exactly (case-sensitive). You can use the `Add`, `Delete`, `Rename`, and `Reposition` buttons. The script expects these fields (defined in `ANKI_NOTE_FIELDS`):
        1.  `AnkiExpression` (Recommended first field)
        2.  `EnglishSituationPrompt`
        3.  `Meaning`
        4.  `Structure`
        5.  `ExamplesJP`
        6.  `ExamplesEN`
        7.  `UsageNotes`
        8.  `ObsidianFilename`
        9.  `ObsidianModTime`
        10. `ObsidianVaultName`
    - Click `Save`.
    - Select the note type again and click `Cards...`. Configure the Front and Back templates. You can use the HTML/CSS provided in the script development discussion or create your own using the field names above (e.g., Front: `{{EnglishSituationPrompt}}`, Back: `{{AnkiExpression}}<br>{{Meaning}}...`).

**3. Install Python Libraries:**

    Open your terminal or command prompt and run:
    ```bash
    pip install requests pyyaml
    ```

**4. Configure the Python Script:**

    - Download or copy the Python script (e.g., `obsidian-sync.py`).
    - Open the script in a text editor or IDE (like VSCode).
    - **Crucially, edit the variables in the `--- Configuration ---` section** near the top of the script to match your system and preferences. Search for these variable names:
        - `OBSIDIAN_VAULT_PATH = Path("C:/Users/owena/My Drive/Obsidian Notes/Current Notes")`: Change this to the **full, correct path** to the root of your Obsidian vault. Use forward slashes (`/`) even on Windows.
        - `OBSIDIAN_VAULT_NAME = "Current Notes"`: Change this to the **exact name** of your Obsidian vault as it appears in Obsidian (used for creating `obsidian://` links).
        - `GRAMMAR_NOTES_DIR = OBSIDIAN_VAULT_PATH / "2. Permanent Notes"`: Adjust the sub-directory path relative to your vault path where your tagged grammar notes are stored.
        - `REPORT_DIR = OBSIDIAN_VAULT_PATH / "4. Structure Notes"`: Adjust the sub-directory path where the `Grammar Study Summary.md` report should be saved.
        - `ANKI_DECK_NAME = "Japanese::Grammar::Japanese Grammar - Obsidian"`: Set the desired Anki deck name, using `::` for sub-decks.
        - `ANKI_NOTE_TYPE_NAME = "Obsidian Grammar Sync"`: **Must exactly match** the name you gave the note type in Anki (Step 2).
        - `LOG_FILENAME = "anki_sync_log.txt"`: Name of the log file created in the script's directory.
        - `logger.setLevel(logging.DEBUG)`: Change `DEBUG` to `logging.INFO` if you want less detailed logs after confirming everything works.

## Usage

1.  **Run Anki:** Make sure the Anki desktop application is running with the correct profile loaded and the AnkiConnect add-on is enabled.
2.  **Run the Script:** Open your terminal or command prompt, navigate (`cd`) to the directory where you saved the script, and run it using Python:
    ```bash
    python obsidian-sync.py
    ```
    (Replace `obsidian-sync.py` with the actual filename if different).
3.  **Check Output:** The script will print progress to the console (unless disabled) and write detailed logs to `anki_sync_log.txt`.
4.  **Verify in Anki:** Check the specified Anki deck for newly created or updated notes.
5.  **Check Obsidian Report:** Look for the `Grammar Study Summary.md` file in the configured report directory within your Obsidian vault.

**Important:** It's highly recommended to **back up your Anki collection and Obsidian vault** before running the script extensively for the first time.

## Troubleshooting

- **AnkiConnect Errors:** Ensure Anki is running, the add-on is installed and enabled, and the `ANKICONNECT_URL` in the script is correct (usually `http://localhost:8765`). Check AnkiConnect's configuration within Anki's Add-ons menu if needed.

- **"Note type not found" Error:** Double-check that the `ANKI_NOTE_TYPE_NAME` in the script exactly matches the name you gave the note type in Anki (case-sensitive). Verify all required fields listed in `ANKI_NOTE_FIELDS` exist in the Anki note type.

- **"Cannot create note because it is empty" Error:** This usually means Anki cannot generate a card from the provided fields. Check:
    - The **field order** in the Anki Note Type (`Tools > Manage Note Types > Fields...`). Ensure the first field (e.g., `AnkiExpression`) is expected to always have content.
    - The **Card Templates** (`Tools > Manage Note Types > Cards...`). Make sure the templates correctly reference fields that contain data. Try simplifying the templates for testing.

- **"Duplicate note" Error:** This *should* be resolved in script version v4 (which uses `addNote` individually with `allowDuplicate: True`), but if it reappears, it might indicate issues with Anki's stricter duplicate checking rules or card template configurations.

- **Check Logs:** The `anki_sync_log.txt` file (created in the same directory as the script) contains detailed information about the script's execution, including data extraction, fields being sent to Anki, and any errors encountered. This is the best place to look for clues when troubleshooting.

