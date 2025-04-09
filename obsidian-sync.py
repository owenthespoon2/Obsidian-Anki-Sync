import os
import yaml
import requests
import json
from pathlib import Path
from datetime import datetime, timedelta
import time
import urllib.parse
import sys
import logging # Import logging module

# --- Configuration ---

# !! IMPORTANT: Update these paths and names for your system !!
OBSIDIAN_VAULT_PATH = Path("C:/Users/owena/My Drive/Obsidian Notes/Current Notes") # Base path for vault
OBSIDIAN_VAULT_NAME = "Current Notes" # The actual name of your vault as seen in Obsidian
GRAMMAR_NOTES_DIR = OBSIDIAN_VAULT_PATH / "2. Permanent Notes"
REPORT_DIR = OBSIDIAN_VAULT_PATH / "4. Structure Notes"
REPORT_FILENAME = "Grammar Study Summary.md"
LOG_FILENAME = "anki_sync_log.txt" # Log file will be created in the script's directory

# AnkiConnect Configuration
ANKICONNECT_URL = "http://localhost:8765" # Default AnkiConnect URL
ANKI_DECK_NAME = "Japanese::Grammar::Japanese Grammar - Obsidian" # Use '::' for sub-decks
ANKI_NOTE_TYPE_NAME = "Obsidian Grammar Sync" # **MUST MATCH the note type you created in Anki**

# Fields expected in the Anki Note Type (ensure these match your manual setup)
ANKI_NOTE_FIELDS = [
    "AnkiExpression", "EnglishSituationPrompt", "Meaning", "Structure",
    "ExamplesJP", "ExamplesEN", "UsageNotes", "ObsidianFilename",
    "ObsidianModTime", "ObsidianVaultName"
]

# --- Logging Setup ---
# Configure logging to write to a file and include timestamps
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_handler = logging.FileHandler(LOG_FILENAME, mode='w', encoding='utf-8') # 'w' overwrites log each run
log_handler.setFormatter(log_formatter)

logger = logging.getLogger()
# Set to DEBUG to get detailed field logs, INFO for less verbose output
logger.setLevel(logging.DEBUG)
logger.addHandler(log_handler)

# --- AnkiConnect Helper Functions ---

def invoke_anki_connect(action, **params):
    """Sends a request to the AnkiConnect API with enhanced error reporting via logging."""
    payload = json.dumps({"action": action, "version": 6, "params": params})
    headers = {'Content-Type': 'application/json'}
    error_prefix = f"AnkiConnect Error (Action: {action}):"
    # Log the request being sent at DEBUG level (optional, can be verbose)
    # logger.debug(f"AnkiConnect Request: Action={action}, Params={params}")
    try:
        response = requests.post(ANKICONNECT_URL, data=payload, headers=headers, timeout=30)
        response.raise_for_status()
        response_json = response.json()

        if response_json.get('error'):
            error_message = response_json['error']
            # Don't log duplicate errors globally here if allowDuplicate is True in params
            # Check if the error is specifically a duplicate error AND allowDuplicate was intended
            is_duplicate_error = "duplicate" in error_message
            allow_duplicate_set = False
            if action == "addNote" and "note" in params and "options" in params["note"]:
                allow_duplicate_set = params["note"]["options"].get("allowDuplicate", False)

            if not (is_duplicate_error and allow_duplicate_set):
                 logger.error(f"{error_prefix} {error_message}")
                 # Provide more specific guidance for common errors
                 if "collection is not available" in error_message: logger.error("  -> Is Anki open with the correct profile loaded?")
                 elif "failed to connect" in error_message.lower(): logger.error(f"  -> Cannot connect to AnkiConnect at {ANKICONNECT_URL}. Is Anki running with AnkiConnect enabled?")
                 elif "deck name conflicts" in error_message: logger.error(f"  -> Deck name '{params.get('deck', ANKI_DECK_NAME)}' might conflict with an existing note type name.")
                 elif "note type not found" in error_message: logger.error(f"  -> Note type '{params.get('modelName', ANKI_NOTE_TYPE_NAME)}' was not found in Anki.")
                 elif "empty" in error_message: logger.error(f"  -> Anki rejected note as empty. Check note type fields & templates.")

            # Still return None even if it was an expected duplicate error,
            # but the calling function might check getLastError if needed.
            return None

        # Log success at DEBUG level
        # logger.debug(f"AnkiConnect Success: Action={action}, Result={response_json.get('result')}")
        return response_json.get('result')

    except requests.exceptions.Timeout:
        logger.error(f"{error_prefix} Connection timed out. Anki might be busy or unresponsive.")
        return None
    except requests.exceptions.ConnectionError:
        logger.error(f"{error_prefix} Connection refused. Is Anki running and AnkiConnect installed/enabled at {ANKICONNECT_URL}?")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"{error_prefix} Network error: {e}")
        return None
    except json.JSONDecodeError:
        logger.error(f"{error_prefix} Could not decode AnkiConnect response: {response.text}")
        return None
    except Exception as e:
        logger.exception(f"{error_prefix} An unexpected error occurred during API call.")
        return None

# --- Other Functions (check_or_create_deck, validate_note_type, extract_yaml_frontmatter, find_grammar_notes, extract_data_for_anki, get_existing_anki_notes_info, update_notes_in_anki, get_anki_study_data, analyze_study_data, generate_obsidian_report) ---
# These functions remain the same as in v3 (obsidian_anki_sync_v3_filelog)
# ... (Paste the unchanged functions from the previous version here) ...
# --- [Start of Unchanged Functions - Paste from v3 here] ---
def check_or_create_deck(deck_name):
    """Checks if the deck exists in Anki, creates it if not. Handles sub-decks."""
    logger.info(f"Checking/Creating Anki deck: '{deck_name}'...")
    try:
        deck_names = invoke_anki_connect("deckNames")
        if deck_names is None:
            logger.error("  Error: Could not retrieve deck names from Anki.")
            return False

        if deck_name not in deck_names:
            logger.info(f"  Deck '{deck_name}' not found. Attempting to create...")
            result = invoke_anki_connect("createDeck", deck=deck_name)
            if result is None:
                logger.error(f"  Error: Failed to create deck '{deck_name}'. Check AnkiConnect logs.")
                return False
            else:
                logger.info(f"  Deck '{deck_name}' created successfully.")
                return True
        else:
            logger.info(f"  Deck '{deck_name}' already exists.")
            return True
    except Exception as e:
        logger.exception(f"  Error during deck check/creation for '{deck_name}'.")
        return False

def validate_note_type(note_type_name, required_fields):
    """Checks if the required note type and its fields exist in Anki."""
    logger.info(f"Validating Anki note type: '{note_type_name}'...")
    try:
        model_names = invoke_anki_connect("modelNames")
        if model_names is None:
            logger.error("  Error: Could not retrieve note type names from Anki.")
            return False

        if note_type_name not in model_names:
            logger.error(f"  Error: Note type '{note_type_name}' does not exist in Anki.")
            logger.error(f"  Please create it manually with the required fields: {', '.join(required_fields)}")
            return False

        field_names = invoke_anki_connect("modelFieldNames", modelName=note_type_name)
        if field_names is None:
             logger.error(f"  Error: Could not retrieve fields for note type '{note_type_name}'.")
             return False

        missing_fields = [f for f in required_fields if f not in field_names]
        if missing_fields:
            logger.error(f"  Error: Note type '{note_type_name}' is missing required fields: {', '.join(missing_fields)}.")
            logger.error(f"  Please add these fields manually in Anki (Tools > Manage Note Types).")
            return False

        logger.info(f"  Note type '{note_type_name}' found with all required fields.")
        return True

    except Exception as e:
        logger.exception(f"  Error during note type validation for '{note_type_name}'.")
        return False

def extract_yaml_frontmatter(content, filepath):
    """Extracts YAML frontmatter from markdown content with error reporting."""
    if not content.startswith("---"):
        return None, content

    parts = content.split('---', 2)
    if len(parts) < 3:
        logger.warning(f"  Invalid frontmatter structure in {filepath.name}. Skipping frontmatter.")
        return None, content

    yaml_content = parts[1]
    main_content = parts[2]

    try:
        frontmatter = yaml.safe_load(yaml_content)
        if not isinstance(frontmatter, dict):
             logger.warning(f"  Frontmatter in {filepath.name} is not a valid dictionary. Skipping.")
             return None, main_content
        return frontmatter, main_content
    except yaml.YAMLError as e:
        logger.error(f"  Error parsing YAML in {filepath.name}: {e}")
        return None, content
    except Exception as e:
        logger.exception(f"  Unexpected error parsing YAML in {filepath.name}.")
        return None, content

def find_grammar_notes(directory):
    """Finds all markdown files with the '#grammarpoint' tag in their YAML."""
    logger.info(f"Scanning for grammar notes ({directory})...")
    grammar_files = []
    if not directory.is_dir():
        logger.error(f"  Error: Notes directory not found: {directory}")
        return []

    for filepath in directory.rglob("*.md"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            frontmatter, _ = extract_yaml_frontmatter(content, filepath)

            if frontmatter:
                tags = frontmatter.get("tags", [])
                if isinstance(tags, str):
                    tags = [tags]

                if isinstance(tags, list) and "grammarpoint" in tags:
                    grammar_files.append(filepath)

        except FileNotFoundError:
             logger.warning(f"  File listed but not found during scan: {filepath}")
        except Exception as e:
            logger.exception(f"  Error processing file {filepath} during scan.")

    logger.info(f"Scan complete. Found {len(grammar_files)} notes tagged with #grammarpoint.")
    return grammar_files

def extract_data_for_anki(filepath, vault_path, vault_name):
    """Extracts data, handles multiple prompts, gets mod time and relative path."""
    logger.info(f"  Extracting data from: {filepath.name}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        frontmatter, _ = extract_yaml_frontmatter(content, filepath)

        if not frontmatter:
            logger.warning(f"    No valid frontmatter found in {filepath.name}. Skipping.")
            return None

        # --- Extract Core Fields ---
        anki_expression = str(frontmatter.get("ankiExpression", "")).strip()
        if not anki_expression:
            anki_expression = filepath.stem
            logger.warning(f"    'ankiExpression' missing in {filepath.name}. Using filename '{anki_expression}' as identifier.")

        logger.debug(f"    Raw AnkiExpression: '{frontmatter.get('ankiExpression', '')}', Used: '{anki_expression}'")

        meaning = str(frontmatter.get("meaning", "N/A")).strip()
        structure = str(frontmatter.get("structure", "N/A")).strip()
        usage_notes = str(frontmatter.get("usageNotes", "N/A")).strip()

        # --- Handle Examples ---
        examples_jp_raw = frontmatter.get("exampleSentences", [])
        examples_en_raw = frontmatter.get("exampleSentencesEnglish", [])

        examples_jp = [str(item).strip() for item in examples_jp_raw] if isinstance(examples_jp_raw, list) else [str(examples_jp_raw).strip()]
        examples_en = [str(item).strip() for item in examples_en_raw] if isinstance(examples_en_raw, list) else [str(examples_en_raw).strip()]

        len_diff = len(examples_jp) - len(examples_en)
        if len_diff > 0:
            examples_en.extend([""] * len_diff)
        elif len_diff < 0:
            examples_jp.extend([""] * abs(len_diff))

        examples_jp_str = "\n".join(examples_jp)
        examples_en_str = "\n".join(examples_en)

        # --- Handle Multiple Prompts ---
        prompts_raw = frontmatter.get("englishSituationPrompt", [])
        logger.debug(f"    Raw englishSituationPrompt: {prompts_raw}") # Log raw prompts

        if isinstance(prompts_raw, str):
            prompts = [prompts_raw.strip()] if prompts_raw.strip() else []
        elif isinstance(prompts_raw, list):
            prompts = [str(p).strip() for p in prompts_raw if str(p).strip()] # Filter out empty strings
        else:
            prompts = []
            logger.warning(f"    'englishSituationPrompt' in {filepath.name} is not a string or list. Type: {type(prompts_raw)}")


        if not prompts:
             logger.warning(f"    No valid 'englishSituationPrompt'(s) found in {filepath.name}. Skipping note.")
             return None

        logger.debug(f"    Processed prompts: {prompts}") # Log processed prompts

        # --- Get File Metadata ---
        try:
            mod_time_float = os.path.getmtime(filepath)
            mod_time_str = datetime.fromtimestamp(mod_time_float).isoformat()
        except Exception as e:
             logger.warning(f"    Could not get modification time for {filepath.name}: {e}. Using current time.")
             mod_time_str = datetime.now().isoformat()

        try:
            relative_path = filepath.relative_to(vault_path).as_posix()
        except ValueError:
             logger.warning(f"    Could not determine relative path for {filepath.name} within {vault_path}. Storing absolute path.")
             relative_path = filepath.as_posix()


        # --- Prepare Data Structure ---
        note_info = {
            "ankiExpression": anki_expression,
            "prompts": prompts,
            "fields_content": {
                "Meaning": meaning,
                "Structure": structure,
                "ExamplesJP": examples_jp_str,
                "ExamplesEN": examples_en_str,
                "UsageNotes": usage_notes,
                "ObsidianFilename": relative_path,
                "ObsidianModTime": mod_time_str,
                "ObsidianVaultName": vault_name,
            },
            "sourceFile": filepath
        }

        logger.info(f"    Successfully extracted data for '{anki_expression}' with {len(prompts)} prompt(s).")
        return note_info

    except Exception as e:
        logger.exception(f"    Error extracting data from {filepath.name}.")
        return None

def get_existing_anki_notes_info(deck_name, note_type_name):
    """Gets info (noteId, modTime, filename, prompt) for existing notes."""
    logger.info(f"Fetching existing note data from Anki (Deck: '{deck_name}', Type: '{note_type_name}')...")
    existing_notes = {}

    query = f'"deck:{deck_name}" "note:{note_type_name}"'
    try:
        note_ids = invoke_anki_connect("findNotes", query=query)
        if note_ids is None:
            logger.error("  Error: Failed to find notes in Anki.")
            return {}
        if not note_ids:
            logger.info("  No existing notes found matching criteria.")
            return {}

        logger.info(f"  Found {len(note_ids)} existing notes. Fetching details...")

        batch_size = 100
        retrieved_count = 0
        for i in range(0, len(note_ids), batch_size):
            batch_ids = note_ids[i:i+batch_size]
            notes_info_batch = invoke_anki_connect("notesInfo", notes=batch_ids)

            if notes_info_batch:
                retrieved_count += len(notes_info_batch)
                for note in notes_info_batch:
                    try:
                        fields = note.get('fields', {})
                        expression = fields.get("AnkiExpression", {}).get("value")
                        mod_time = fields.get("ObsidianModTime", {}).get("value")
                        filename = fields.get("ObsidianFilename", {}).get("value")
                        prompt = fields.get("EnglishSituationPrompt", {}).get("value")
                        note_id = note.get('noteId')

                        if not expression or note_id is None:
                             logger.warning(f"    Skipping Anki note ID {note_id} due to missing AnkiExpression or noteId.")
                             continue

                        if expression not in existing_notes:
                            existing_notes[expression] = []

                        existing_notes[expression].append({
                             "noteId": note_id,
                             "obsidianModTime": mod_time,
                             "obsidianFilename": filename,
                             "prompt": prompt
                        })
                    except Exception as e:
                         logger.warning(f"    Error processing Anki note info for ID {note.get('noteId')}: {e}")
            else:
                 logger.warning(f"  Failed to retrieve info for batch starting at index {i}.")


        logger.info(f"  Successfully retrieved details for {retrieved_count} notes, grouped by {len(existing_notes)} unique AnkiExpressions.")
        return existing_notes

    except Exception as e:
        logger.exception("  Error retrieving existing Anki notes.")
        return {}

def update_notes_in_anki(anki_expression, existing_anki_notes_list, obsidian_note_info, deck_name, note_type_name):
    """Updates Anki notes: Deletes all existing for the expression, then adds current versions."""
    note_ids_to_delete = [note["noteId"] for note in existing_anki_notes_list]

    logger.info(f"  Updating notes for AnkiExpression: '{anki_expression}'")
    logger.info(f"    Found {len(note_ids_to_delete)} existing note(s) to replace.")

    if not note_ids_to_delete:
         logger.warning("    Warning: Update requested, but no existing note IDs found to delete.")
    else:
        logger.info(f"    Deleting existing notes: {note_ids_to_delete}...")
        try:
            delete_result = invoke_anki_connect("deleteNotes", notes=note_ids_to_delete)
            if delete_result is None:
                logger.error(f"    Error: Failed to delete existing notes for '{anki_expression}'. Update aborted.")
                return 0
            logger.info("    Existing notes deleted successfully.")
        except Exception as e:
            logger.exception(f"    Error during note deletion for '{anki_expression}'. Update aborted.")
            return 0

    logger.info(f"    Adding current version of notes for '{anki_expression}'...")
    # Use the new add_new_notes_to_anki which calls addNote individually
    added_count = add_new_notes_to_anki(obsidian_note_info, deck_name, note_type_name)
    return added_count

def get_anki_study_data(deck_name, note_type_name):
    """Retrieves card info and relevant note fields for study analysis."""
    logger.info(f"\nRetrieving study data (Deck: '{deck_name}', Type: '{note_type_name}')...")
    study_data = []
    query = f'"deck:{deck_name}" "note:{note_type_name}"'

    try:
        card_ids = invoke_anki_connect("findCards", query=query)
        if card_ids is None:
            logger.error("  Error: Failed to find cards in Anki.")
            return []
        if not card_ids:
            logger.info("  No cards found matching criteria for study analysis.")
            return []

        logger.info(f"  Found {len(card_ids)} cards. Fetching details...")

        cards_info = invoke_anki_connect("cardsInfo", cards=card_ids)
        if not cards_info:
            logger.error("  Error: Failed to retrieve detailed card info.")
            return []

        note_ids = list(set(card['note'] for card in cards_info))
        notes_info_list = invoke_anki_connect("notesInfo", notes=note_ids)
        notes_info_dict = {note['noteId']: note for note in notes_info_list} if notes_info_list else {}

        processed_count = 0
        for card in cards_info:
            note_info = notes_info_dict.get(card['note'])
            if note_info and note_info.get('fields'):
                fields = note_info['fields']
                expression = fields.get("AnkiExpression", {}).get("value", "N/A")
                filename = fields.get("ObsidianFilename", {}).get("value")
                vault_name = fields.get("ObsidianVaultName", {}).get("value")
                prompt = fields.get("EnglishSituationPrompt", {}).get("value", "N/A")

                if not filename or not vault_name:
                     logger.warning(f"    Skipping card ID {card['cardId']} due to missing ObsidianFilename or ObsidianVaultName field.")
                     continue

                study_data.append({
                    "cardId": card['cardId'], "noteId": card['note'], "ankiExpression": expression,
                    "obsidianFilename": filename, "obsidianVaultName": vault_name,
                    "englishSituationPrompt": prompt, "interval": card['interval'], "due": card['due'],
                    "lapses": card['lapses'], "reps": card['reps'], "easeFactor": card.get('factor', 2500),
                    "lastReview": card.get('mod')
                })
                processed_count += 1
            else:
                logger.warning(f"    Could not find note info or fields for card ID {card['cardId']}")

        logger.info(f"  Retrieved study details for {processed_count} cards.")
        return study_data

    except Exception as e:
        logger.exception("  Error retrieving study data.")
        return []

def analyze_study_data(study_data, days_recent=7, struggle_lapses=3, struggle_ease_factor=2000, due_soon_days=3):
    """Analyzes study data to find recent, struggling, and due cards."""
    logger.info("Analyzing study data...")
    analysis = {"recent": set(), "struggling": set(), "due_soon": set()}
    now = datetime.now()
    today_anki_epoch_approx = (now - datetime(1970, 1, 1)).days
    logger.info(f"  Approximated Anki 'today' number: {today_anki_epoch_approx}")

    for card in study_data:
        identifier_tuple = (card['obsidianFilename'], card['englishSituationPrompt'], card['ankiExpression'])

        if card['lastReview']:
             try:
                 last_review_dt = datetime.fromtimestamp(card['lastReview'])
                 if now - last_review_dt <= timedelta(days=days_recent):
                     analysis["recent"].add(identifier_tuple)
             except Exception as e:
                 logger.warning(f"    Could not parse last review timestamp {card['lastReview']} for card {card['cardId']}: {e}")

        is_struggling = False
        if card['lapses'] >= struggle_lapses: is_struggling = True
        if card['easeFactor'] < struggle_ease_factor and card['reps'] > 0: is_struggling = True
        if is_struggling: analysis["struggling"].add(identifier_tuple)

        try:
            if isinstance(card['due'], int) and 0 < (card['due'] - today_anki_epoch_approx) <= due_soon_days:
                 analysis["due_soon"].add(identifier_tuple)
        except TypeError:
             logger.warning(f"    Could not interpret 'due' value {card['due']} for card {card['cardId']}")

    analysis_list = {
        key: sorted(list(value), key=lambda x: (x[2], x[0], x[1]))
        for key, value in analysis.items()
    }
    logger.info("Analysis complete:")
    logger.info(f"  Recent: {len(analysis_list['recent'])} items")
    logger.info(f"  Struggling: {len(analysis_list['struggling'])} items")
    logger.info(f"  Due Soon: {len(analysis_list['due_soon'])} items")
    return analysis_list

def generate_obsidian_report(analysis, report_path):
    """Generates a Markdown report file with obsidian:// links."""
    logger.info(f"Generating report at: {report_path}")

    def create_obsidian_uri(filename, vault_name, display_text):
        try:
            encoded_filename = urllib.parse.quote(filename, safe='')
            encoded_vault = urllib.parse.quote(vault_name, safe='')
            uri = f"obsidian://open?vault={encoded_vault}&file={encoded_filename}"
            return f"[{display_text}]({uri})"
        except Exception as e:
             logger.error(f"    Error creating Obsidian URI for {filename}: {e}")
             return f"{display_text} (Link Error)"

    content = f"# Grammar Study Summary ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n"
    content += f"Analyzed Anki deck: `{ANKI_DECK_NAME}`\n"
    content += f"Note type: `{ANKI_NOTE_TYPE_NAME}`\n\n"

    # --- Recently Studied ---
    content += "## Recently Studied Grammar Points\n"
    if analysis["recent"]:
        last_expr = None
        for filename, prompt, expression in analysis["recent"]:
            if expression != last_expr: content += f"\n**{expression}:**\n"; last_expr = expression
            link_text = f"{prompt} ({filename.split('/')[-1]})"
            link = create_obsidian_uri(filename, OBSIDIAN_VAULT_NAME, link_text)
            content += f"- {link}\n"
    else: content += "- None\n"
    content += "\n"

    # --- Struggling ---
    content += "## Grammar Points Needing More Attention\n(Based on lapses or low ease factor)\n"
    if analysis["struggling"]:
        last_expr = None
        for filename, prompt, expression in analysis["struggling"]:
             if expression != last_expr: content += f"\n**{expression}:**\n"; last_expr = expression
             link_text = f"{prompt} ({filename.split('/')[-1]})"
             link = create_obsidian_uri(filename, OBSIDIAN_VAULT_NAME, link_text)
             content += f"- {link}\n"
    else: content += "- None\n"
    content += "\n"

    # --- Due Soon ---
    content += "## Grammar Points Due Soon\n(Estimated based on Anki scheduling)\n"
    if analysis["due_soon"]:
        last_expr = None
        for filename, prompt, expression in analysis["due_soon"]:
            if expression != last_expr: content += f"\n**{expression}:**\n"; last_expr = expression
            link_text = f"{prompt} ({filename.split('/')[-1]})"
            link = create_obsidian_uri(filename, OBSIDIAN_VAULT_NAME, link_text)
            content += f"- {link}\n"
    else: content += "- None\n"
    content += "\n"

    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Report generated successfully: {report_path}")
    except Exception as e:
        logger.exception(f"Error writing report file {report_path}.")
# --- [End of Unchanged Functions] ---


# --- Anki Note Management (Add/Update/Delete) ---
# --- MODIFIED Function: Uses addNote instead of addNotes ---
def add_new_notes_to_anki(obsidian_note_info, deck_name, note_type_name):
    """Adds multiple Anki notes for a single Obsidian note (one per prompt) using individual addNote calls."""
    anki_expression = obsidian_note_info["ankiExpression"]
    logger.info(f"  Preparing to add new notes individually for AnkiExpression: '{anki_expression}'")
    added_count = 0
    failed_count = 0

    for prompt in obsidian_note_info["prompts"]:
        fields_data = obsidian_note_info["fields_content"].copy()
        fields_data["AnkiExpression"] = anki_expression
        fields_data["EnglishSituationPrompt"] = prompt

        final_fields = {f: fields_data.get(f, "") for f in ANKI_NOTE_FIELDS}

        # --- Log field details at DEBUG level ---
        logger.debug(f"    DEBUG: Preparing note with fields for prompt '{prompt}':")
        is_an_expression_empty = False
        is_prompt_empty = False
        if not final_fields.get("AnkiExpression", "").strip():
             logger.warning("      WARNING: AnkiExpression field is effectively empty!")
             is_an_expression_empty = True
        if not final_fields.get("EnglishSituationPrompt", "").strip():
             logger.warning("      WARNING: EnglishSituationPrompt field is effectively empty!")
             is_prompt_empty = True

        for field_name, field_value in final_fields.items():
             display_value = str(field_value)[:100] + '...' if len(str(field_value)) > 100 else str(field_value)
             logger.debug(f"      - {field_name}: '{display_value}'")
        # --- End field logging ---


        if not prompt:
             logger.warning(f"    Skipping note for expression '{anki_expression}' because the prompt string is empty.")
             failed_count += 1
             continue

        if is_an_expression_empty and is_prompt_empty:
            logger.error(f"    ERROR: Skipping note for expression '{anki_expression}' because BOTH AnkiExpression and EnglishSituationPrompt are empty. Check Obsidian note.")
            failed_count += 1
            continue

        # --- Prepare payload for singular addNote ---
        note_payload = {
            "deckName": deck_name,
            "modelName": note_type_name,
            "fields": final_fields,
            "options": {
                # Explicitly allow duplicates when adding individually,
                # as multiple notes might share the same AnkiExpression (first field).
                "allowDuplicate": True,
                 # You might want to refine duplicate scope if needed, but allowDuplicate=True
                 # should prevent the error based on the first field alone.
                 # "duplicateScope": "deck",
                 # "duplicateScopeOptions": { ... }
            },
            "tags": ["obsidian_sync", f"expr_{anki_expression}"]
        }

        logger.info(f"    Attempting to add note for prompt: '{prompt}' via 'addNote'...")
        try:
            result = invoke_anki_connect("addNote", note=note_payload)
            if result is not None:
                logger.info(f"      Successfully added note (ID: {result}).")
                added_count += 1
            else:
                # Check if the error was specifically a duplicate error despite allowDuplicate=True
                # This might indicate a stricter duplicate check based on more fields or card templates.
                last_error = invoke_anki_connect("getLastError")
                if last_error and "duplicate" in last_error:
                     logger.warning(f"      Note for prompt '{prompt}' failed: Anki reported duplicate even with allowDuplicate=True. Check Anki's duplicate handling settings or card templates.")
                elif last_error and "empty" in last_error:
                     logger.error(f"      Note for prompt '{prompt}' failed: Anki reported 'cannot create note because it is empty'.")
                else:
                     logger.error(f"      Note for prompt '{prompt}' failed. API call returned None or non-duplicate error.")
                failed_count += 1
        except Exception as e:
            logger.exception(f"    Error during single addNote call for prompt '{prompt}'.")
            failed_count += 1

    logger.info(f"  Finished adding notes for '{anki_expression}': {added_count} added, {failed_count} failed.")
    return added_count # Return the number of notes successfully added


# --- Main Execution ---
def main():
    """Main function to orchestrate the process."""
    start_time = time.time()
    logger.info("--- Starting Obsidian-Anki Grammar Sync (v4 - Fix Duplicate Error) ---")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Obsidian Vault: '{OBSIDIAN_VAULT_NAME}' at {OBSIDIAN_VAULT_PATH}")
    logger.info(f"Anki Deck: '{ANKI_DECK_NAME}', Note Type: '{ANKI_NOTE_TYPE_NAME}'")
    logger.info(f"Log file: {LOG_FILENAME}")

    # 1. Preliminary Checks
    logger.info("\n--- Performing Initial Checks ---")
    if not invoke_anki_connect("version"):
        logger.critical("CRITICAL: AnkiConnect is not responding. Please ensure Anki is running with AnkiConnect enabled.")
        return 1

    if not check_or_create_deck(ANKI_DECK_NAME):
        logger.critical("CRITICAL: Failed to verify or create the Anki deck. Exiting.")
        return 1

    if not validate_note_type(ANKI_NOTE_TYPE_NAME, ANKI_NOTE_FIELDS):
        logger.critical("CRITICAL: Anki note type validation failed. Please fix the note type in Anki. Exiting.")
        return 1

    # 2. Get Existing Anki Notes Info
    logger.info("\n--- Retrieving Existing Anki Note Data ---")
    existing_anki_notes = get_existing_anki_notes_info(ANKI_DECK_NAME, ANKI_NOTE_TYPE_NAME)

    # 3. Find and Process Obsidian Notes
    logger.info("\n--- Scanning and Processing Obsidian Notes ---")
    obsidian_files = find_grammar_notes(GRAMMAR_NOTES_DIR)
    if not obsidian_files:
        logger.info("No relevant Obsidian notes found. Skipping sync.")

    total_added_notes_count = 0 # Track total notes added across all expressions
    updated_expressions_count = 0
    processed_files_count = 0
    skipped_expressions_count = 0 # Renamed from skipped_notes_count
    error_files_count = 0 # Renamed from error_notes_count
    processed_expressions = set()

    for filepath in obsidian_files:
        processed_files_count += 1
        logger.info(f"Processing Obsidian file {processed_files_count}/{len(obsidian_files)}: {filepath.name}")
        obsidian_note_data = extract_data_for_anki(filepath, OBSIDIAN_VAULT_PATH, OBSIDIAN_VAULT_NAME)

        if not obsidian_note_data:
            error_files_count += 1
            logger.warning(f"Skipping {filepath.name} due to extraction errors.")
            continue

        expression = obsidian_note_data["ankiExpression"]
        processed_expressions.add(expression)
        obsidian_mod_time = obsidian_note_data["fields_content"]["ObsidianModTime"]

        notes_added_this_expression = 0 # Track notes added specifically for this expression run

        if expression in existing_anki_notes:
            anki_note_list = existing_anki_notes[expression]
            anki_mod_time = anki_note_list[0].get("obsidianModTime")
            update_needed = False
            if anki_mod_time:
                 if obsidian_mod_time > anki_mod_time: update_needed = True
            else:
                 logger.warning(f"  Existing Anki note for '{expression}' missing ObsidianModTime. Forcing update.")
                 update_needed = True

            anki_filename = anki_note_list[0].get("obsidianFilename")
            obsidian_filename = obsidian_note_data["fields_content"]["ObsidianFilename"]
            if anki_filename != obsidian_filename:
                 logger.info(f"  Obsidian filename changed for '{expression}' ('{anki_filename}' -> '{obsidian_filename}'). Forcing update.")
                 update_needed = True

            if update_needed:
                logger.info(f"  Update needed for AnkiExpression: '{expression}'.")
                # update_notes_in_anki now returns count of notes added during the update
                notes_added_this_expression = update_notes_in_anki(expression, anki_note_list, obsidian_note_data, ANKI_DECK_NAME, ANKI_NOTE_TYPE_NAME)
                if notes_added_this_expression > 0:
                     updated_expressions_count += 1
                # If update failed (returned 0), it's implicitly an error for this file
                elif not any(note['noteId'] for note in anki_note_list): # Only count as error if no notes existed before update attempt failed
                    error_files_count += 1

            else:
                logger.info(f"  Skipping AnkiExpression: '{expression}' (Anki note is up-to-date).")
                skipped_expressions_count += 1
        else:
            logger.info(f"  New AnkiExpression found: '{expression}'. Adding notes...")
            # add_new_notes_to_anki now returns count of notes added
            notes_added_this_expression = add_new_notes_to_anki(obsidian_note_data, ANKI_DECK_NAME, ANKI_NOTE_TYPE_NAME)
            # If adding failed (returned 0), count as error for this file
            if notes_added_this_expression == 0:
                 error_files_count += 1

        total_added_notes_count += notes_added_this_expression

    # Adjust error count calculation - error_files_count now tracks files that failed extraction or failed add/update
    # Let's refine the summary logic slightly

    # 4. Check for Orphaned Anki Notes
    logger.info("\n--- Checking for Orphaned Anki Notes ---")
    orphaned_expressions = set(existing_anki_notes.keys()) - processed_expressions
    if orphaned_expressions:
         logger.warning(f"  Found {len(orphaned_expressions)} AnkiExpression(s) with notes in Anki but no corresponding '#grammarpoint' tagged file found in Obsidian:")
         notes_to_delete = []
         for expr in orphaned_expressions:
             logger.warning(f"    - {expr} (Filename in Anki: {existing_anki_notes[expr][0].get('obsidianFilename', 'N/A')})")
             notes_to_delete.extend([note['noteId'] for note in existing_anki_notes[expr]])
         logger.warning(f"  Consider manually deleting these {len(notes_to_delete)} notes in Anki or re-tagging/restoring the Obsidian files.")
    else:
         logger.info("  No orphaned Anki notes found.")


    logger.info("\n--- Sync Summary ---")
    logger.info(f"Obsidian notes scanned: {len(obsidian_files)}")
    logger.info(f"Obsidian notes processed (attempted sync): {processed_files_count - error_files_count}")
    logger.info(f"Anki expressions updated: {updated_expressions_count}")
    logger.info(f"Total new Anki notes added (incl. updates): {total_added_notes_count}")
    logger.info(f"Anki expressions skipped (up-to-date): {skipped_expressions_count}")
    logger.info(f"Obsidian notes skipped (extraction error): {error_files_count}") # Files that failed extraction


    # 5. Study Analysis and Reporting
    logger.info("\n--- Generating Study Report ---")
    study_data = get_anki_study_data(ANKI_DECK_NAME, ANKI_NOTE_TYPE_NAME)
    if study_data:
        analysis_results = analyze_study_data(study_data)
        report_full_path = REPORT_DIR / REPORT_FILENAME
        generate_obsidian_report(analysis_results, report_full_path)
    else:
        logger.info("No study data retrieved or processed. Skipping report generation.")

    end_time = time.time()
    logger.info(f"\n--- Script Finished in {end_time - start_time:.2f} seconds ---")
    return 0


if __name__ == "__main__":
    # Setup basic console output for initial messages
    print("*"*50)
    print(" OBSIDIAN-ANKI SYNC SCRIPT (V4 - Fix Duplicate Error)")
    print("*"*50)
    print(f"Logging output to: {LOG_FILENAME}")
    print("IMPORTANT:")
    print("1. Ensure Anki is running with the AnkiConnect add-on installed and enabled.")
    print(f"2. Ensure the Anki Note Type '{ANKI_NOTE_TYPE_NAME}' exists with required fields.")
    print("3. Backup your Anki collection and Obsidian vault before running extensively.")
    print("4. Verify the configuration paths and names at the top of the script.")
    print("*"*50)

    exit_code = main()
    logging.shutdown()
    sys.exit(exit_code)
