"""
st_compat.py — Shared infrastructure (not owned by one presenter)
==================================================================

This module holds the plumbing every other file needs but that isn't
really "anyone's feature": the Streamlit/requests import shims and the
typing Protocol classes used for strict static typing against Streamlit
(whose own type stubs are loose).

Every other module in this package does:
    from st_compat import st, requests, RequestException, <protocols you need>

If asked in the defense "who owns this file" — it's shared scaffolding,
same as a project's `utils.py` or `types.py`. Whoever presents `app.py`
(Person 8 / app orchestration) is the natural person to explain *why*
it exists, since main() is what ties everything together.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Protocol, cast


class _HTTPResponse(Protocol):
    status_code: int
    ok: bool
    text: str

    def json(self) -> object:
        ...


class _RequestsExceptions(Protocol):
    RequestException: type[Exception]


class _RequestsModule(Protocol):
    exceptions: _RequestsExceptions


class _StreamlitErrorAPI(Protocol):
    def error(self, message: str) -> object:
        ...


class _StreamlitWarningAPI(Protocol):
    def warning(self, message: str) -> object:
        ...


class _StreamlitSuccessAPI(Protocol):
    def success(self, message: str) -> object:
        ...


class _StreamlitWriteAPI(Protocol):
    def write(self, message: str) -> object:
        ...


class _StreamlitExpanderAPI(Protocol):
    def __enter__(self) -> "_StreamlitExpanderAPI":
        ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        ...


class _StreamlitExpanderFactoryAPI(Protocol):
    def expander(self, label: str) -> _StreamlitExpanderAPI:
        ...


class _StreamlitSpinnerAPI(Protocol):
    def __enter__(self) -> "_StreamlitSpinnerAPI":
        ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        ...


class _StreamlitSpinnerFactoryAPI(Protocol):
    def spinner(self, text: str) -> _StreamlitSpinnerAPI:
        ...


class _StreamlitPageConfigAPI(Protocol):
    def set_page_config(
        self, *, page_title: str, page_icon: str, layout: str
    ) -> object:
        ...


class _StreamlitSidebarAPI(Protocol):
    def __enter__(self) -> "_StreamlitSidebarAPI":
        ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        ...

    def header(self, body: str) -> object:
        ...

    def text_input(
        self, label: str, *, value: str, type: str, help: str
    ) -> str:
        ...

    def divider(self) -> object:
        ...

    def write(self, body: str) -> object:
        ...

    def button(self, label: str) -> bool:
        ...


class _StreamlitFormAPI(Protocol):
    def __enter__(self) -> "_StreamlitFormAPI":
        ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        ...


class _StreamlitFormFactoryAPI(Protocol):
    def form(self, key: str, *, clear_on_submit: bool = ...) -> _StreamlitFormAPI:
        ...


class _StreamlitTabAPI(Protocol):
    def __enter__(self) -> "_StreamlitTabAPI":
        ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        ...


class _StreamlitTabsFactoryAPI(Protocol):
    def tabs(self, labels: list[str]) -> list[_StreamlitTabAPI]:
        ...


requests: ModuleType = importlib.import_module("requests")
RequestException = cast(_RequestsModule, cast(object, requests)).exceptions.RequestException

try:
    st: ModuleType = importlib.import_module("streamlit")
except ModuleNotFoundError:
    class _StreamlitFallback:
        def __call__(self, *args: object, **kwargs: object) -> None:
            return None

        def __getattr__(self, name: str) -> "_StreamlitFallback":
            return self

        def __enter__(self) -> "_StreamlitFallback":
            return self

        def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
            return False

    st = cast(ModuleType, cast(object, _StreamlitFallback()))
