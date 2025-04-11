import os
import yaml
import requests
import json
from pathlib import Path
from datetime import datetime, timedelta
import time
import urllib.parse
import sys
# Removed logging import

# --- Configuration ---

# !! IMPORTANT: Update these paths and names for your system !!
# Set the base path for your Obsidian vault
OBSIDIAN_VAULT_PATH = Path("C:/Users/owena/My Drive/Obsidian Notes/Current Notes") # CHANGE THIS
# Set the name of your Obsidian vault as it appears in Obsidian
OBSIDIAN_VAULT_NAME = "Current Notes" # CHANGE THIS
# Set the directory within your vault where grammar notes are stored
GRAMMAR_NOTES_DIR = OBSIDIAN_VAULT_PATH / "2. Permanent Notes" # CHANGE THIS if needed
# Set the directory where the study summary report will be saved
REPORT_DIR = OBSIDIAN_VAULT_PATH / "4. Structure Notes" # CHANGE THIS if needed
# Filename for the study summary report
REPORT_FILENAME = "Grammar Study Summary.md"
# LOG_FILENAME removed

# AnkiConnect Configuration
# Default AnkiConnect URL
ANKICONNECT_URL = "http://localhost:8765"
# Target Anki deck name (use '::' for sub-decks)
ANKI_DECK_NAME = "1. Grammar::Japanese Grammar - Obsidian" # CHANGE THIS if your top level isn't "1. Grammar"
# Anki Note Type name (MUST MATCH the note type created in Anki)
ANKI_NOTE_TYPE_NAME = "Obsidian Grammar Sync" # CHANGE THIS if needed

# Fields expected in the Anki Note Type (MUST MATCH your Anki setup)
ANKI_NOTE_FIELDS = [
    "AnkiExpression", "EnglishSituationPrompt", "Meaning", "Structure",
    "ExamplesJP", "ExamplesEN", "UsageNotes", "ObsidianFilename",
    "ObsidianModTime", "ObsidianVaultName", "TargetJP"
]

# --- Logging Setup Removed ---

# --- AnkiConnect Helper Functions ---

def invoke_anki_connect(action, **params):
    """Sends a request to the AnkiConnect API with enhanced error reporting via print."""
    payload = json.dumps({"action": action, "version": 6, "params": params})
    headers = {'Content-Type': 'application/json'}
    error_prefix = f"[ERROR] AnkiConnect Error (Action: {action}):"
    # print(f"[DEBUG] AnkiConnect Request: Action={action}, Params={params}") # Uncomment for very detailed logs
    try:
        response = requests.post(ANKICONNECT_URL, data=payload, headers=headers, timeout=30)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        response_json = response.json()

        # Check for errors reported within the JSON response
        if response_json.get('error'):
            error_message = response_json['error']
            # Special handling for expected 'duplicate' errors when allowDuplicate is True
            is_duplicate_error = "duplicate" in error_message.lower()
            allow_duplicate_set = False
            if action == "addNote" and "note" in params and "options" in params["note"]:
                allow_duplicate_set = params["note"]["options"].get("allowDuplicate", False)

            # Print the error unless it's an expected duplicate
            if not (is_duplicate_error and allow_duplicate_set):
                 print(f"{error_prefix} {error_message}")
                 # Provide more specific guidance for common errors
                 if "collection is not available" in error_message: print("  -> Is Anki open with the correct profile loaded?")
                 elif "failed to connect" in error_message.lower(): print(f"  -> Cannot connect to AnkiConnect at {ANKICONNECT_URL}. Is Anki running with AnkiConnect enabled?")
                 elif "deck name conflicts" in error_message: print(f"  -> Deck name '{params.get('deck', ANKI_DECK_NAME)}' might conflict with an existing note type name.")
                 elif "note type not found" in error_message: print(f"  -> Note type '{params.get('modelName', ANKI_NOTE_TYPE_NAME)}' was not found in Anki.")
                 elif "empty" in error_message: print(f"  -> Anki rejected note as empty. Check note type fields & templates.")

            # Return None on error (including expected duplicates)
            return None

        # print(f"[DEBUG] AnkiConnect Success: Action={action}, Result={response_json.get('result')}") # Uncomment for detailed success logs
        return response_json.get('result')

    except requests.exceptions.Timeout:
        print(f"{error_prefix} Connection timed out. Anki might be busy or unresponsive.")
        return None
    except requests.exceptions.ConnectionError:
        print(f"{error_prefix} Connection refused. Is Anki running and AnkiConnect installed/enabled at {ANKICONNECT_URL}?")
        return None
    except requests.exceptions.RequestException as e: # Catches other requests errors like HTTPError
        print(f"{error_prefix} Network error: {e}")
        return None
    except json.JSONDecodeError:
        print(f"{error_prefix} Could not decode AnkiConnect response: {response.text}")
        return None
    except Exception as e:
        # Catch any other unexpected errors during the API call process
        print(f"{error_prefix} An unexpected error occurred during API call.")
        # Optionally print traceback for unexpected errors
        import traceback
        traceback.print_exc()
        return None

# --- Other Helper Functions ---

def check_or_create_deck(deck_name):
    """Checks if the deck exists in Anki, creates it if not. Handles sub-decks."""
    print(f"[INFO] Checking/Creating Anki deck: '{deck_name}'...")
    try:
        deck_names = invoke_anki_connect("deckNames")
        if deck_names is None:
            print("[ERROR]   Could not retrieve deck names from Anki.")
            return False

        if deck_name not in deck_names:
            print(f"[INFO]   Deck '{deck_name}' not found. Attempting to create...")
            result = invoke_anki_connect("createDeck", deck=deck_name)
            if result is None:
                print(f"[ERROR]   Failed to create deck '{deck_name}'. Check AnkiConnect errors above.")
                return False
            else:
                print(f"[INFO]   Deck '{deck_name}' created successfully.")
                time.sleep(1) # Short delay after deck creation
                return True
        else:
            print(f"[INFO]   Deck '{deck_name}' already exists.")
            return True
    except Exception as e:
        print(f"[ERROR]   Error during deck check/creation for '{deck_name}': {e}")
        return False

def validate_note_type(note_type_name, required_fields):
    """Checks if the required note type and its fields exist in Anki."""
    print(f"[INFO] Validating Anki note type: '{note_type_name}'...")
    try:
        model_names = invoke_anki_connect("modelNames")
        if model_names is None:
            print("[ERROR]   Could not retrieve note type names from Anki.")
            return False

        if note_type_name not in model_names:
            print(f"[ERROR]   Note type '{note_type_name}' does not exist in Anki.")
            print(f"[ERROR]   Please create it manually with AT LEAST these fields: {', '.join(required_fields)}")
            return False

        field_names = invoke_anki_connect("modelFieldNames", modelName=note_type_name)
        if field_names is None:
             print(f"[ERROR]   Could not retrieve fields for note type '{note_type_name}'.")
             return False

        # Check if all required fields are present
        missing_fields = [f for f in required_fields if f not in field_names]
        if missing_fields:
            print(f"[ERROR]   Note type '{note_type_name}' is missing required fields: {', '.join(missing_fields)}.")
            print(f"[ERROR]   Please add these fields manually in Anki (Tools > Manage Note Types > Select '{note_type_name}' > Fields...).")
            return False

        print(f"[INFO]   Note type '{note_type_name}' found with all required fields.")
        return True

    except Exception as e:
        print(f"[ERROR]   Error during note type validation for '{note_type_name}': {e}")
        return False

def extract_yaml_frontmatter(content, filepath):
    """Extracts YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return None, content

    parts = content.split('---', 2)
    if len(parts) < 3:
        print(f"[WARN]   Invalid frontmatter structure in {filepath.name}. Skipping frontmatter.")
        return None, content

    yaml_content = parts[1]
    main_content = parts[2]

    try:
        frontmatter = yaml.safe_load(yaml_content)
        if not isinstance(frontmatter, dict):
             print(f"[WARN]   Frontmatter in {filepath.name} is not a valid dictionary. Skipping.")
             return None, main_content
        return frontmatter, main_content
    except yaml.YAMLError as e:
        print(f"[ERROR]   Error parsing YAML in {filepath.name}: {e}")
        return None, content
    except Exception as e:
        print(f"[ERROR]   Unexpected error parsing YAML in {filepath.name}: {e}")
        return None, content

def find_grammar_notes(directory):
    """Finds all markdown files with the 'grammarpoint' tag in their YAML."""
    print(f"[INFO] Scanning for grammar notes in: {directory}")
    grammar_files = []
    if not directory.is_dir():
        print(f"[ERROR]   Notes directory not found: {directory}")
        return []

    all_md_files = list(directory.rglob("*.md")) # Get all files first for progress indication
    print(f"[INFO] Found {len(all_md_files)} markdown files to check...")

    for i, filepath in enumerate(all_md_files):
        # Optional: Print progress every N files
        # if (i + 1) % 50 == 0:
        #     print(f"[INFO]   Checked {i + 1}/{len(all_md_files)} files...")
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
                    # print(f"[DEBUG]  Found grammarpoint tag in: {filepath.name}") # Uncomment for detail

        except FileNotFoundError:
             print(f"[WARN]   File listed but not found during scan: {filepath}")
        except Exception as e:
            print(f"[ERROR]   Error processing file {filepath} during scan: {e}")

    print(f"[INFO] Scan complete. Found {len(grammar_files)} notes tagged with #grammarpoint.")
    return grammar_files

# --- MODIFIED function: Handles list validation and pairing ---
def extract_data_for_anki(filepath, vault_path, vault_name):
    """Extracts data, handles multiple prompt/target pairs, gets mod time and relative path."""
    # print(f"[DEBUG]  Extracting data from: {filepath.name}") # More verbose
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        frontmatter, _ = extract_yaml_frontmatter(content, filepath)

        if not frontmatter:
            # Warning already printed by extract_yaml_frontmatter if structure was invalid
            # print(f"[WARN]    No valid frontmatter found in {filepath.name}. Skipping.") # Redundant?
            return None

        # --- Extract Core Fields ---
        anki_expression = str(frontmatter.get("ankiExpression", "")).strip()
        if not anki_expression:
            anki_expression = filepath.stem
            print(f"[WARN]    'ankiExpression' missing or empty in {filepath.name}. Using filename '{anki_expression}' as identifier.")

        # print(f"[DEBUG]    Raw AnkiExpression: '{frontmatter.get('ankiExpression', '')}', Used: '{anki_expression}'")

        meaning = str(frontmatter.get("meaning", "N/A")).strip()
        structure = str(frontmatter.get("structure", "N/A")).strip()

        # --- Handle Examples ---
        examples_jp_raw = frontmatter.get("exampleSentences", [])
        examples_en_raw = frontmatter.get("exampleSentencesEnglish", [])
        examples_jp = [str(item).strip() for item in examples_jp_raw] if isinstance(examples_jp_raw, list) else [str(examples_jp_raw).strip()]
        examples_en = [str(item).strip() for item in examples_en_raw] if isinstance(examples_en_raw, list) else [str(examples_en_raw).strip()]
        len_diff = len(examples_jp) - len(examples_en)
        if len_diff > 0: examples_en.extend([""] * len_diff)
        elif len_diff < 0: examples_jp.extend([""] * abs(len_diff))
        examples_jp_str = "\n".join(examples_jp)
        examples_en_str = "\n".join(examples_en)

        # --- Handle Usage Notes ---
        usage_notes_raw = frontmatter.get("usageNotes", [])
        if isinstance(usage_notes_raw, list):
            usage_notes_list = [str(item).strip() for item in usage_notes_raw if str(item).strip()]
            usage_notes = "\n".join(usage_notes_list) if usage_notes_list else "N/A"
        else:
            usage_notes = str(usage_notes_raw).strip() if str(usage_notes_raw).strip() else "N/A"

        # --- Handle Multiple Prompts and Target Sentences ---
        prompts_raw = frontmatter.get("englishSituationPrompt", [])
        targets_raw = frontmatter.get("targetSentencesJP", [])

        # print(f"[DEBUG]    Raw englishSituationPrompt: {prompts_raw}")
        # print(f"[DEBUG]    Raw targetSentencesJP: {targets_raw}")

        if isinstance(prompts_raw, str): prompts = [prompts_raw.strip()] if prompts_raw.strip() else []
        elif isinstance(prompts_raw, list): prompts = [str(p).strip() for p in prompts_raw if str(p).strip()]
        else: prompts = []; print(f"[WARN]    'englishSituationPrompt' in {filepath.name} is not a string or list. Type: {type(prompts_raw)}")

        if isinstance(targets_raw, str): targets = [targets_raw.strip()] if targets_raw.strip() else []
        elif isinstance(targets_raw, list): targets = [str(t).strip() for t in targets_raw if str(t).strip()]
        else: targets = []; print(f"[WARN]    'targetSentencesJP' in {filepath.name} is not a string or list. Type: {type(targets_raw)}")

        # --- Validation and Pairing ---
        prompt_target_pairs = []
        if not prompts:
            print(f"[WARN]    No valid 'englishSituationPrompt'(s) found in {filepath.name}. Skipping Anki generation.")
            return None
        elif 'targetSentencesJP' not in frontmatter:
             print(f"[WARN]    Anki generation skipped for {filepath.name}: 'targetSentencesJP' field is MISSING from YAML.")
             return None
        elif not targets:
            print(f"[WARN]    Anki generation skipped for {filepath.name}: 'targetSentencesJP' field is present but EMPTY.")
            return None
        elif len(prompts) != len(targets):
            print(f"[WARN]    Anki generation skipped for {filepath.name}: Mismatch between prompts ({len(prompts)}) and targets ({len(targets)}).")
            return None
        else:
            prompt_target_pairs = list(zip(prompts, targets))
            # print(f"[DEBUG]    Processed {len(prompt_target_pairs)} prompt-target pairs.")

        # --- Get File Metadata ---
        try:
            mod_time_float = os.path.getmtime(filepath)
            mod_time_str = datetime.fromtimestamp(mod_time_float).isoformat()
        except Exception as e:
             print(f"[WARN]    Could not get modification time for {filepath.name}: {e}. Using current time.")
             mod_time_str = datetime.now().isoformat()

        try:
            relative_path = filepath.relative_to(vault_path).as_posix()
        except ValueError:
             print(f"[WARN]    Could not determine relative path for {filepath.name} within {vault_path}. Storing absolute path.")
             relative_path = filepath.as_posix()

        # --- Prepare Data Structure ---
        note_info = {
            "ankiExpression": anki_expression,
            "prompt_target_pairs": prompt_target_pairs,
            "fields_content": {
                "Meaning": meaning, "Structure": structure,
                "ExamplesJP": examples_jp_str, "ExamplesEN": examples_en_str,
                "UsageNotes": usage_notes, "ObsidianFilename": relative_path,
                "ObsidianModTime": mod_time_str, "ObsidianVaultName": vault_name,
            },
            "sourceFile": filepath
        }
        # Info level log moved to main loop
        # print(f"[INFO]    Successfully extracted data for '{anki_expression}' with {len(prompt_target_pairs)} pair(s).")
        return note_info

    except Exception as e:
        print(f"[ERROR]   Error extracting data from {filepath.name}: {e}")
        return None

def get_existing_anki_notes_info(deck_name, note_type_name):
    """Gets info for existing notes, grouped by AnkiExpression."""
    print(f"[INFO] Fetching existing note data from Anki (Deck: '{deck_name}', Type: '{note_type_name}')...")
    existing_notes = {}
    query = f'"deck:{deck_name}" "note:{note_type_name}"'
    try:
        note_ids = invoke_anki_connect("findNotes", query=query)
        if note_ids is None: print("[ERROR]   Failed to find notes in Anki."); return {}
        if not note_ids: print("[INFO]   No existing notes found matching criteria."); return {}

        print(f"[INFO]   Found {len(note_ids)} existing notes. Fetching details...")
        notes_info = invoke_anki_connect("notesInfo", notes=note_ids) # Fetch all at once if possible

        if not notes_info:
            print("[ERROR]   Failed to retrieve details for existing notes.")
            return {}

        retrieved_count = 0
        for note in notes_info:
            try:
                fields = note.get('fields', {})
                expression = fields.get("AnkiExpression", {}).get("value")
                mod_time = fields.get("ObsidianModTime", {}).get("value")
                filename = fields.get("ObsidianFilename", {}).get("value")
                prompt = fields.get("EnglishSituationPrompt", {}).get("value")
                note_id = note.get('noteId')

                if not expression or note_id is None:
                     print(f"[WARN]    Skipping Anki note ID {note_id} due to missing AnkiExpression or noteId.")
                     continue

                if expression not in existing_notes: existing_notes[expression] = []
                existing_notes[expression].append({
                     "noteId": note_id, "obsidianModTime": mod_time,
                     "obsidianFilename": filename, "prompt": prompt
                })
                retrieved_count += 1
            except Exception as e:
                 print(f"[WARN]    Error processing Anki note info for ID {note.get('noteId')}: {e}")

        print(f"[INFO]   Successfully retrieved details for {retrieved_count} notes, grouped by {len(existing_notes)} unique AnkiExpressions.")
        return existing_notes

    except Exception as e:
        print(f"[ERROR]   Error retrieving existing Anki notes: {e}")
        return {}

# --- MODIFIED function: Iterates through pairs to add notes ---
def add_new_notes_to_anki(obsidian_note_info, deck_name, note_type_name):
    """Adds multiple Anki notes for a single Obsidian note (one per prompt/target pair)."""
    anki_expression = obsidian_note_info["ankiExpression"]
    prompt_target_pairs = obsidian_note_info.get("prompt_target_pairs", [])
    # print(f"[DEBUG]  Preparing to add {len(prompt_target_pairs)} notes for '{anki_expression}'") # Verbose
    added_count = 0
    failed_count = 0

    if not prompt_target_pairs: return 0 # Nothing to add

    for index, (prompt, target) in enumerate(prompt_target_pairs):
        # print(f"[DEBUG]    Processing pair {index + 1}/{len(prompt_target_pairs)}: Prompt='{prompt[:50]}...'") # Verbose
        fields_data = obsidian_note_info["fields_content"].copy()
        fields_data["AnkiExpression"] = anki_expression
        fields_data["EnglishSituationPrompt"] = prompt
        fields_data["TargetJP"] = target
        final_fields = {f: fields_data.get(f, "") for f in ANKI_NOTE_FIELDS}

        # Basic check before sending to Anki
        if not final_fields.get("AnkiExpression", "").strip() and not final_fields.get("EnglishSituationPrompt", "").strip():
            print(f"[ERROR]     Skipping pair {index + 1} for '{anki_expression}': BOTH Expression and Prompt are empty.")
            failed_count += 1
            continue

        note_payload = {
            "deckName": deck_name, "modelName": note_type_name,
            "fields": final_fields,
            "options": { "allowDuplicate": True },
            "tags": ["obsidian_sync", f"expr_{anki_expression}"]
        }

        # print(f"[DEBUG]      Attempting to add note via 'addNote'...") # Verbose
        try:
            result = invoke_anki_connect("addNote", note=note_payload)
            if result is not None:
                # print(f"[DEBUG]        Successfully added note (ID: {result}).") # Verbose
                added_count += 1
            else:
                last_error = invoke_anki_connect("getLastError") # Check error only on failure
                if last_error and "duplicate" in last_error.lower():
                    print(f"[WARN]      Note failed for '{anki_expression}' (Prompt: '{prompt[:50]}...'): Anki reported duplicate even with allowDuplicate=True.")
                elif last_error and "empty" in last_error.lower():
                     print(f"[ERROR]     Note failed for '{anki_expression}' (Prompt: '{prompt[:50]}...'): Anki reported 'cannot create note because it is empty'.")
                else:
                     print(f"[ERROR]     Note failed for '{anki_expression}' (Prompt: '{prompt[:50]}...'). API call returned None or other error. Last Error: {last_error}")
                failed_count += 1
        except Exception as e:
            print(f"[ERROR]     Exception during addNote call for '{anki_expression}' (Prompt: '{prompt[:50]}...'): {e}")
            failed_count += 1

    # print(f"[DEBUG]  Finished adding notes for '{anki_expression}': {added_count} added, {failed_count} failed.") # Verbose
    return added_count

def update_notes_in_anki(anki_expression, existing_anki_notes_list, obsidian_note_info, deck_name, note_type_name):
    """Updates Anki notes: Deletes ALL existing notes for the expression, then adds current versions."""
    note_ids_to_delete = [note["noteId"] for note in existing_anki_notes_list]
    # print(f"[DEBUG]  Updating notes for '{anki_expression}'") # Verbose
    # print(f"[DEBUG]    Found {len(note_ids_to_delete)} existing note(s) to replace.") # Verbose

    if not note_ids_to_delete:
         print(f"[WARN]    Update requested for '{anki_expression}', but no existing note IDs found to delete.")
    else:
        # print(f"[DEBUG]    Deleting existing notes: {note_ids_to_delete}...") # Verbose
        try:
            delete_result = invoke_anki_connect("deleteNotes", notes=note_ids_to_delete)
            if delete_result is None:
                print(f"[ERROR]   Failed to delete existing notes for '{anki_expression}'. Update aborted.")
                return 0
            # print("[DEBUG]    Existing notes deleted successfully.") # Verbose
        except Exception as e:
            print(f"[ERROR]   Error during note deletion for '{anki_expression}'. Update aborted: {e}")
            return 0

    # print(f"[DEBUG]    Adding current version of notes for '{anki_expression}'...") # Verbose
    added_count = add_new_notes_to_anki(obsidian_note_info, deck_name, note_type_name)
    return added_count


def get_anki_study_data(deck_name, note_type_name):
    """Retrieves card info and relevant note fields for study analysis."""
    print(f"\n[INFO] Retrieving study data (Deck: '{deck_name}', Type: '{note_type_name}')...")
    study_data = []
    query = f'"deck:{deck_name}" "note:{note_type_name}"'
    try:
        card_ids = invoke_anki_connect("findCards", query=query)
        if card_ids is None: print("[ERROR]   Failed to find cards in Anki."); return []
        if not card_ids: print("[INFO]   No cards found matching criteria for study analysis."); return []

        print(f"[INFO]   Found {len(card_ids)} cards. Fetching details...")
        cards_info = invoke_anki_connect("cardsInfo", cards=card_ids)
        if not cards_info: print("[ERROR]   Failed to retrieve detailed card info."); return []

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
                     print(f"[WARN]    Skipping card ID {card['cardId']} due to missing ObsidianFilename or ObsidianVaultName field.")
                     continue

                study_data.append({
                    "cardId": card['cardId'], "noteId": card['note'], "ankiExpression": expression,
                    "obsidianFilename": filename, "obsidianVaultName": vault_name,
                    "englishSituationPrompt": prompt, "interval": card['interval'], "due": card['due'],
                    "lapses": card['lapses'], "reps": card['reps'], "easeFactor": card.get('factor', 2500),
                    "lastReview": card.get('mod') # 'mod' timestamp often approximates last review
                })
                processed_count += 1
            else:
                print(f"[WARN]    Could not find note info or fields for card ID {card['cardId']}")

        print(f"[INFO]   Retrieved study details for {processed_count} cards.")
        return study_data

    except Exception as e:
        print(f"[ERROR]   Error retrieving study data: {e}")
        return []

def analyze_study_data(study_data, days_recent=7, struggle_lapses=3, struggle_ease_factor=2000, due_soon_days=3):
    """Analyzes study data to find recent, struggling, and due cards."""
    print("[INFO] Analyzing study data...")
    analysis = {"recent": set(), "struggling": set(), "due_soon": set()}
    now = datetime.now()
    today_anki_epoch_approx = (now - datetime(1970, 1, 1)).days
    # print(f"[DEBUG]  Approximated Anki 'today' number: {today_anki_epoch_approx}") # Verbose

    for card in study_data:
        identifier_tuple = (card['obsidianFilename'], card['englishSituationPrompt'], card['ankiExpression'])

        if card['lastReview']:
             try:
                 last_review_dt = datetime.fromtimestamp(card['lastReview'])
                 if now - last_review_dt <= timedelta(days=days_recent):
                     analysis["recent"].add(identifier_tuple)
             except Exception as e:
                 print(f"[WARN]    Could not parse last review timestamp {card['lastReview']} for card {card['cardId']}: {e}")

        is_struggling = False
        if card['lapses'] >= struggle_lapses: is_struggling = True
        if card.get('factor', 2500) < struggle_ease_factor and card['reps'] > 0: is_struggling = True
        if is_struggling: analysis["struggling"].add(identifier_tuple)

        try:
            card_type = card.get('type', -1)
            if isinstance(card['due'], int) and card_type == 2: # type 2 = review card
                days_until_due = card['due'] - today_anki_epoch_approx
                if 0 < days_until_due <= due_soon_days:
                     analysis["due_soon"].add(identifier_tuple)
        except TypeError:
             print(f"[WARN]    Could not interpret 'due' value {card['due']} for card {card['cardId']}")

    analysis_list = {
        key: sorted(list(value), key=lambda x: (x[2], x[0], x[1]))
        for key, value in analysis.items()
    }
    print("[INFO] Analysis complete:")
    print(f"[INFO]   Recent: {len(analysis_list['recent'])} items")
    print(f"[INFO]   Struggling: {len(analysis_list['struggling'])} items")
    print(f"[INFO]   Due Soon: {len(analysis_list['due_soon'])} items")
    return analysis_list


def generate_obsidian_report(analysis, report_path):
    """Generates a Markdown report file with obsidian:// links."""
    print(f"[INFO] Generating report at: {report_path}")

    def create_obsidian_uri(filename, vault_name, display_text):
        try:
            encoded_filename = urllib.parse.quote(filename, safe='')
            encoded_vault = urllib.parse.quote(vault_name, safe='')
            uri = f"obsidian://open?vault={encoded_vault}&file={encoded_filename}"
            return f"[{display_text}]({uri})"
        except Exception as e:
             print(f"[ERROR]   Error creating Obsidian URI for {filename}: {e}")
             return f"{display_text} (Link Error)"

    content = f"# Grammar Study Summary ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n"
    content += f"Analyzed Anki deck: `{ANKI_DECK_NAME}`\n"
    content += f"Note type: `{ANKI_NOTE_TYPE_NAME}`\n\n"

    # --- Sections: Recent, Struggling, Due Soon ---
    for key, title in [("recent", "Recently Studied"), ("struggling", "Needing More Attention"), ("due_soon", "Due Soon")]:
        content += f"## {title} Grammar Points\n"
        if key == "struggling": content += "(Based on lapses or low ease factor)\n"
        if key == "due_soon": content += "(Estimated based on Anki scheduling)\n"

        if analysis[key]:
            last_expr = None
            for filename, prompt, expression in analysis[key]:
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
        print(f"[INFO] Report generated successfully: {report_path}")
    except Exception as e:
        print(f"[ERROR] Error writing report file {report_path}: {e}")


# --- Main Execution Logic ---
def main():
    """Main function to orchestrate the Obsidian-Anki sync process."""
    start_time = time.time()
    print(f"\n--- Starting Obsidian-Anki Grammar Sync (v4.8 - Console Output) ---") # Updated version
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Obsidian Vault: '{OBSIDIAN_VAULT_NAME}' at {OBSIDIAN_VAULT_PATH}")
    print(f"Anki Deck: '{ANKI_DECK_NAME}', Note Type: '{ANKI_NOTE_TYPE_NAME}'")

    # 1. Preliminary Checks (AnkiConnect, Deck, Note Type)
    print("\n--- Performing Initial Checks ---")
    if not invoke_anki_connect("version"):
        print("[CRITICAL] AnkiConnect is not responding. Please ensure Anki is running with AnkiConnect enabled. Exiting.")
        return 1

    if not check_or_create_deck(ANKI_DECK_NAME):
        print("[CRITICAL] Failed to verify or create the Anki deck. Exiting.")
        return 1

    if not validate_note_type(ANKI_NOTE_TYPE_NAME, ANKI_NOTE_FIELDS):
        print("[CRITICAL] Anki note type validation failed. Please fix the note type in Anki. Exiting.")
        return 1
    print("[INFO] Initial checks passed.")

    # 2. Get Existing Anki Notes Info
    print("\n--- Retrieving Existing Anki Note Data ---")
    existing_anki_notes = get_existing_anki_notes_info(ANKI_DECK_NAME, ANKI_NOTE_TYPE_NAME)

    # 3. Find and Process Obsidian Notes
    print("\n--- Scanning and Processing Obsidian Notes ---")
    obsidian_files = find_grammar_notes(GRAMMAR_NOTES_DIR)
    if not obsidian_files:
        print("[INFO] No relevant Obsidian notes found tagged with #grammarpoint. Skipping sync.")

    total_added_notes_count = 0
    updated_expressions_count = 0
    processed_files_count = 0
    skipped_expressions_count = 0
    error_files_count = 0
    processed_expressions = set()

    for i, filepath in enumerate(obsidian_files):
        processed_files_count += 1
        print(f"\n[INFO] Processing Obsidian file {i + 1}/{len(obsidian_files)}: {filepath.name}")
        obsidian_note_data = extract_data_for_anki(filepath, OBSIDIAN_VAULT_PATH, OBSIDIAN_VAULT_NAME)

        if not obsidian_note_data:
            error_files_count += 1
            # Reason already printed by extract_data_for_anki
            continue

        expression = obsidian_note_data["ankiExpression"]
        processed_expressions.add(expression)
        obsidian_mod_time = obsidian_note_data["fields_content"]["ObsidianModTime"]
        notes_added_this_expression = 0

        if expression in existing_anki_notes:
            anki_note_list = existing_anki_notes[expression]
            anki_mod_time = anki_note_list[0].get("obsidianModTime") if anki_note_list else None
            update_needed = False
            if anki_mod_time:
                 if obsidian_mod_time > anki_mod_time:
                     print(f"[INFO]   Obsidian file is newer. Update needed.")
                     update_needed = True
            else:
                 print(f"[WARN]   Existing Anki note missing ObsidianModTime. Forcing update.")
                 update_needed = True

            anki_filename = anki_note_list[0].get("obsidianFilename") if anki_note_list else None
            obsidian_filename = obsidian_note_data["fields_content"]["ObsidianFilename"]
            if anki_filename != obsidian_filename:
                 print(f"[INFO]   Obsidian filename changed ('{anki_filename}' -> '{obsidian_filename}'). Forcing update.")
                 update_needed = True

            if update_needed:
                print(f"[INFO]   Updating Anki notes for '{expression}'...")
                notes_added_this_expression = update_notes_in_anki(expression, anki_note_list, obsidian_note_data, ANKI_DECK_NAME, ANKI_NOTE_TYPE_NAME)
                if notes_added_this_expression > 0:
                     updated_expressions_count += 1
                     print(f"[INFO]   Successfully updated '{expression}' ({notes_added_this_expression} cards).")
                else:
                     print(f"[ERROR]   Update failed to add any notes for '{expression}'.")
                     error_files_count += 1
            else:
                print(f"[INFO]   Skipping '{expression}' (Anki note is up-to-date).")
                skipped_expressions_count += 1
        else:
            print(f"[INFO]   New AnkiExpression found: '{expression}'. Adding notes...")
            notes_added_this_expression = add_new_notes_to_anki(obsidian_note_data, ANKI_DECK_NAME, ANKI_NOTE_TYPE_NAME)
            if notes_added_this_expression > 0:
                 print(f"[INFO]   Successfully added '{expression}' ({notes_added_this_expression} cards).")
            else:
                 print(f"[ERROR]   Failed to add any notes for new expression '{expression}'.")
                 error_files_count += 1

        total_added_notes_count += notes_added_this_expression

    # 4. Check for Orphaned Anki Notes
    print("\n--- Checking for Orphaned Anki Notes ---")
    orphaned_expressions = set(existing_anki_notes.keys()) - processed_expressions
    if orphaned_expressions:
         print(f"[WARN] Found {len(orphaned_expressions)} AnkiExpression(s) with notes in Anki but no corresponding '#grammarpoint' tagged file found in Obsidian:")
         notes_to_delete_ids = []
         for expr in orphaned_expressions:
             first_note_filename = existing_anki_notes[expr][0].get('obsidianFilename', 'N/A') if existing_anki_notes[expr] else 'N/A'
             print(f"[WARN]   - {expr} (Example Filename in Anki: {first_note_filename})")
             notes_to_delete_ids.extend([note['noteId'] for note in existing_anki_notes[expr]])
         print(f"[WARN] Consider manually deleting these {len(notes_to_delete_ids)} orphaned notes in Anki or re-tagging/restoring the Obsidian files.")
         # Add option here if you want automatic deletion later
    else:
         print("[INFO] No orphaned Anki notes found.")

    # 5. Print Sync Summary
    print("\n--- Sync Summary ---")
    print(f"Obsidian notes scanned: {len(obsidian_files)}")
    successful_sync_attempts = processed_files_count - error_files_count
    print(f"Obsidian notes processed successfully: {successful_sync_attempts}")
    print(f"Anki expressions updated: {updated_expressions_count}")
    print(f"Total new Anki notes added (incl. updates): {total_added_notes_count}")
    print(f"Anki expressions skipped (up-to-date): {skipped_expressions_count}")
    print(f"Obsidian notes failed (extraction/validation/Anki error): {error_files_count}")

    # 6. Study Analysis and Reporting
    print("\n--- Generating Study Report ---")
    study_data = get_anki_study_data(ANKI_DECK_NAME, ANKI_NOTE_TYPE_NAME)
    if study_data:
        analysis_results = analyze_study_data(study_data)
        report_full_path = REPORT_DIR / REPORT_FILENAME
        generate_obsidian_report(analysis_results, report_full_path)
    else:
        print("[INFO] No study data retrieved or processed. Skipping report generation.")

    end_time = time.time()
    print(f"\n--- Script Finished in {end_time - start_time:.2f} seconds ---")
    return 0

# --- Script Entry Point ---
if __name__ == "__main__":
    print("*"*50)
    print(" OBSIDIAN-ANKI SYNC SCRIPT (V4.8 - Console Output)") # Updated version
    print("*"*50)
    # print(f"Logging disabled. Outputting to console.") # Removed reference to log file
    print("IMPORTANT:")
    print("1. Ensure Anki is running with the AnkiConnect add-on installed and enabled.")
    print(f"2. Ensure the Anki Note Type '{ANKI_NOTE_TYPE_NAME}' exists with required fields:")
    print(f"   {', '.join(ANKI_NOTE_FIELDS)}")
    print("3. Backup your Anki collection and Obsidian vault before running extensively.")
    print("4. Verify the configuration paths and names at the top of the script.")
    print("*"*50)

    exit_code = main()
    # logging.shutdown() removed
    sys.exit(exit_code)

