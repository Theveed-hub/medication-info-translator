# medication-info-translator

Type a medication name. The app fetches the FDA label, checks for recalls,
rewrites the information in simple language with Gemini, and saves your
search history to a local file.

## Run it

```
pip install streamlit requests
set GEMINI_API_KEY=your_key_here        (Windows)
export GEMINI_API_KEY=your_key_here     (Mac/Linux)
streamlit run app.py
```

Run it from *inside* this folder. Never upload your API key to GitHub.

## Who owns what

| File | Owner | What it does |
|---|---|---|
| `models.py` | **Sadiq** | `Medication` class, name validation, regex cleaning, custom exceptions |
| `fda_client.py` | **Joseph** | `FDAClient`: label lookup, recall check, "did you mean" suggestions |
| `search_ui.py` | **Favour** | Search box, results, recall banner, calls the AI, saves history |
| `ai_translator.py` | **Sadiq** | `AITranslator`: sends text to Gemini and returns plain language |
| `history_stores.py` | **Stephenie** | `SearchHistory`: saves and loads searches from a JSON file |
| `app.py` | **David** | Page layout, sidebar, API key, ties everything together |
| `st_compat.py` | **Shekinah** | Shared import helpers used by the other files |
| Testing, errors, demo, GitHub | **Person 8** | Tests the full app, checks error handling, prepares the demo |

