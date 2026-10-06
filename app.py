"""

    streamlit run app.py

main() is the glue: it reads the Gemini API key (environment variable or
Streamlit Secrets), creates the search history, shows the sidebar, and
runs the search screen. Every other person's module is imported and
used from here.

MedSimplify - Plain-Language Drug Information App
====================================================
A Streamlit application that lets a user type a medication name and:
  1. Fetches official drug labeling info from the openFDA Drug Labeling API
  2. Checks the openFDA Recall/Enforcement API for active recalls
  3. Uses the Gemini API to rewrite dense medical text into plain language
  4. Saves every search to a local JSON file so the user can revisit history
  5. Offers live "did you mean" name suggestions while the user types

Python concepts demonstrated (per assignment spec):
  - File handling      -> SearchHistory reads and writes a JSON file on disk
  - Exception handling -> custom exceptions for invalid names, empty results,
                           network errors, and AI errors
  - Regular expressions -> Medication.clean_text() and extract_warning_keywords()
  - OOP                -> Medication, FDAClient, AITranslator, SearchHistory

Tech stack: Python, Streamlit, Requests, JSON, Gemini API, openFDA APIs.
"""

from __future__ import annotations

import os

from history_stores import SearchHistory
from search_ui import render_search_tab
from st_compat import st


def get_api_key() -> str:
    """Read the Gemini key from the GEMINI_API_KEY environment variable,
    or from Streamlit Secrets if one is set there. Never hard-code it."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    try:
        secret_key = st.secrets.get("GEMINI_API_KEY", "")
        if isinstance(secret_key, str) and secret_key.strip():
            api_key = secret_key.strip()
    except Exception:
        pass  # no secrets file — fall back to the environment variable
    return api_key


def main() -> None:
    st.set_page_config(page_title="MedSimplify", page_icon="💊", layout="centered")
    st.title("💊 MedSimplify")
    st.caption(
        "Type a medication name to see its usage, warnings, and side effects "
        "in simple language, and check for active recalls."
    )

    # session_state keeps values between Streamlit reruns (every click
    # reruns the whole script).
    session_state = st.session_state
    api_key = get_api_key()
    history = SearchHistory()

    # --- Sidebar: AI status + search history ------------------------------
    with st.sidebar:
        st.header("Settings")
        st.write(
            "🤖 Cloud AI is enabled."
            if api_key
            else "🤖 No Gemini API key configured."
        )

        st.divider()
        st.header("Search History")
        entries = history.get_all()
        if entries:
            for e in entries[:15]:
                flag = "⚠️" if e["recall_found"] else ""
                st.write(f"{flag} **{e['query']}** — {e['timestamp']}")
            if st.button("Clear history"):
                history.clear()
                st.rerun()
        else:
            st.write("No searches yet.")

    # --- Main content ------------------------------------------------------
    render_search_tab(history, session_state, api_key)


if __name__ == "__main__":
    main()
