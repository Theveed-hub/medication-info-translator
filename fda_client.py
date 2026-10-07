"""
fda_client.py  (FDA API Client)
=====================================================

All communication with openFDA: looking up a drug label (with a
generic-name -> brand-name -> free-text fallback chain), checking for
active recalls, and generating "did you mean" suggestions cheaply via
openFDA's count-query mode instead of a full label fetch per keystroke.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Callable, cast

from models import FDANetworkError, Medication, MedicationNotFoundError
from st_compat import (
    RequestException,
    _HTTPResponse,
    _StreamlitErrorAPI,
    _StreamlitExpanderFactoryAPI,
    _StreamlitSuccessAPI,
    _StreamlitWriteAPI,
    requests,
    st,
)


class FDAClient:
    """Thin wrapper around the openFDA Drug Labeling and Recall/Enforcement
    (Drug Enforcement) APIs."""

    LABEL_URL: str = "https://api.fda.gov/drug/label.json"
    ENFORCEMENT_URL: str = "https://api.fda.gov/drug/enforcement.json"

    def __init__(self, timeout: int = 10):
        self.timeout: int = timeout

    def _get(self, url: str, params: dict[str, str]) -> dict[str, object]:
        try:
            response = cast(
                Callable[..., _HTTPResponse],
                requests.get,
            )(url, params=params, timeout=self.timeout)
        except RequestException as exc:
            raise FDANetworkError(f"Could not reach openFDA: {exc}") from exc

        if response.status_code == 404:
            return {"results": []}
        if not response.ok:
            raise FDANetworkError(
                f"openFDA returned an error (status {response.status_code})."
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise FDANetworkError("openFDA returned an unreadable response.") from exc

        if not isinstance(data, dict):
            raise FDANetworkError("openFDA returned an unreadable response.")
        return cast(dict[str, object], data)

    def fetch_label(self, drug_name: str) -> Medication:
        """Look up a medication by generic or brand name. Tries generic
        name first, falls back to brand name, then a free-text search."""
        queries = [
            f'openfda.generic_name:"{drug_name}"',
            f'openfda.brand_name:"{drug_name}"',
            f'indications_and_usage:"{drug_name}"',
        ]
        for query in queries:
            data = self._get(self.LABEL_URL, {"search": query, "limit": "1"})
            results_value = data.get("results")
            results_list: list[object] = (
                cast(list[object], results_value) if isinstance(results_value, list) else []
            )
            for candidate in results_list:
                if isinstance(candidate, dict):
                    return Medication.from_openfda_result(drug_name, cast(dict[str, object], candidate))

        raise MedicationNotFoundError(
            "No FDA label information found for "
            + f'"{drug_name}". Check the spelling or try the generic name.'
        )

    def suggest_names(self, partial_name: str, limit: int = 8) -> list[str]:
        """Return up to `limit` candidate generic/brand names starting with
        the given partial text, for a "did you mean" search-as-you-type
        experience. Uses openFDA's count-query mode, which returns matching
        term/count pairs instead of full label records — much cheaper than
        running a full fetch_label for every keystroke."""
        cleaned = partial_name.strip()
        if len(cleaned) < 2:
            return []

        suggestions: list[str] = []
        seen_lower: set[str] = set()

        for count_field in ("openfda.generic_name.exact", "openfda.brand_name.exact"):
            query = f"{count_field}:{cleaned}*"
            try:
                data = self._get(
                    self.LABEL_URL,
                    {"search": query, "count": count_field, "limit": str(limit)},
                )
            except FDANetworkError:
                # Suggestions are a nice-to-have, not core functionality —
                # a transient failure here shouldn't block the user from
                # typing a name and searching normally.
                continue

            results_value = data.get("results")
            if not isinstance(results_value, list):
                continue

            for item in cast(list[object], results_value):
                if not isinstance(item, dict):
                    continue
                item_dict = cast(dict[str, object], item)
                term = item_dict.get("term")
                if not isinstance(term, str):
                    continue
                normalized = term.strip().title()
                if normalized and normalized.lower() not in seen_lower:
                    seen_lower.add(normalized.lower())
                    suggestions.append(normalized)

        return suggestions[:limit]

    def fetch_recalls(self, drug_name: str, limit: int = 5) -> list[dict[str, str]]:
        """Return recent recall/enforcement records mentioning this drug."""
        query = f'product_description:"{drug_name}"'
        data = self._get(
            self.ENFORCEMENT_URL,
            {"search": query, "limit": str(limit), "sort": "report_date:desc"},
        )
        results_value = data.get("results")
        if not isinstance(results_value, list):
            return []

        recalls: list[dict[str, str]] = []
        results_list: list[object] = cast(list[object], results_value)
        for item in results_list:
            if not isinstance(item, dict):
                continue
            item_dict = cast(dict[str, object], item)
            product_description = item_dict.get("product_description")
            reason_for_recall = item_dict.get("reason_for_recall")
            classification = item_dict.get("classification", "Unknown")
            status = item_dict.get("status", "Unknown")
            report_date = item_dict.get("report_date", "")
            recalling_firm = item_dict.get("recalling_firm", "")

            product_description_text = ""
            if isinstance(product_description, str):
                product_description_text = product_description
            elif isinstance(product_description, list):
                product_description_parts = cast(list[object], product_description)
                product_description_text = " ".join(
                    str(part) for part in product_description_parts if isinstance(part, str)
                )

            reason_for_recall_text = ""
            if isinstance(reason_for_recall, str):
                reason_for_recall_text = reason_for_recall
            elif isinstance(reason_for_recall, list):
                reason_for_recall_parts = cast(list[object], reason_for_recall)
                reason_for_recall_text = " ".join(
                    str(part) for part in reason_for_recall_parts if isinstance(part, str)
                )

            recalls.append(
                {
                    "product_description": Medication.clean_text(product_description_text),
                    "reason_for_recall": Medication.clean_text(reason_for_recall_text),
                    "classification": str(classification),
                    "status": str(status),
                    "report_date": str(report_date),
                    "recalling_firm": str(recalling_firm),
                }
            )
        return recalls


@lru_cache(maxsize=256)
def get_cached_suggestions(partial_name: str) -> tuple[str, ...]:
    """Look up "did you mean" name suggestions for a partial medication
    name, cached per unique prefix. Streamlit reruns the whole script on
    every widget interaction, so without this cache the same prefix (e.g.
    while the user is deciding whether to keep typing) would re-hit the
    openFDA count endpoint on every rerun. Suggestions are best-effort:
    any network problem here is swallowed rather than shown to the user,
    since a failed suggestion lookup should never block a normal search."""
    try:
        return tuple(FDAClient().suggest_names(partial_name))
    except FDANetworkError:
        return ()


def render_recall_banner(recalls: list[dict[str, str]]) -> None:
    if recalls:
        _ = cast(_StreamlitErrorAPI, cast(object, st)).error(
            f"⚠️ {len(recalls)} recall notice(s) found for this medication."
        )
        for r in recalls:
            title = (
                f"{r['recalling_firm'] or 'Unknown firm'} — {r['report_date']} "
                + f"(Class {r['classification']})"
            )
            with cast(_StreamlitExpanderFactoryAPI, cast(object, st)).expander(title):
                _ = cast(_StreamlitWriteAPI, cast(object, st)).write(
                    f"**Reason:** {r['reason_for_recall'] or 'Not specified'}"
                )
                _ = cast(_StreamlitWriteAPI, cast(object, st)).write(
                    f"**Status:** {r['status']}"
                )
                _ = cast(_StreamlitWriteAPI, cast(object, st)).write(
                    f"**Product:** {r['product_description']}"
                )
    else:
        _ = cast(_StreamlitSuccessAPI, cast(object, st)).success(
            "✅ No recent recalls found for this medication."
        )
