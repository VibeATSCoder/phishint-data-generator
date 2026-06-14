from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, TYPE_CHECKING


_TECH_LOGGER = logging.getLogger("phishgen.tech")

_ctx_entry_id: ContextVar[str] = ContextVar("phishgen_entry_id", default="-")
_ctx_run_id: ContextVar[str] = ContextVar("phishgen_run_id", default="-")


def set_log_context(*, entry_id: str | None = None, run_id: str | None = None):
    """Push context for the duration of a `with` block. Returns a contextlib-
    compatible reset function. Callers typically use:
        with set_log_context(entry_id="microsoft_login"): ...
    """
    tokens = []
    if entry_id is not None:
        tokens.append(_ctx_entry_id.set(entry_id))
    if run_id is not None:
        tokens.append(_ctx_run_id.set(run_id))

    class _Ctx:
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            for t in reversed(tokens):
                try:
                    if t is None:
                        continue
                    if t is tokens[0] and entry_id is not None:
                        _ctx_entry_id.reset(t)
                    else:
                        _ctx_run_id.reset(t)
                except Exception:
                    pass
    return _Ctx()


def _logfmt(fields: dict[str, Any]) -> str:
    """Render a dict to logfmt: `key=val key2="val with spaces"`.
    Strings without spaces/quotes are emitted bare; everything else is quoted.
    """
    parts: list[str] = []
    for k, v in fields.items():
        if v is None:
            continue
        s = str(v)
        if any(c in s for c in (" ", '"', "=", "\n")):
            s = '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
        parts.append(f"{k}={s}")
    return " ".join(parts)


class TechniqueGroup(str, Enum):
    URL_MANIPULATION = "url_manipulation"
    VISUAL_MIMICRY = "visual_mimicry"
    HTML_DOM_JS = "html_dom_js"
    ANTIBOT_CLOAKING = "antibot_cloaking"
    MULTISTAGE_DELIVERY = "multistage_delivery"
    MFA_AUTH_BYPASS = "mfa_auth_bypass"
    ADVANCED_AI = "advanced_ai"


class Category(str, Enum):
    """Attacker-intent label attached to each technique. Multi-label."""
    CREDENTIAL_THEFT = "credential_theft"
    BRAND_IMPERSONATION = "brand_impersonation"
    MALWARE_DISTRIBUTION = "malware_distribution"
    PERSONAL_INFO_HARVESTING = "personal_info_harvesting"


class Requirement(str, Enum):
    ALWAYS = "always"
    HAS_URL = "has_url"
    HAS_HTML = "has_html"
    HAS_INPUT_FIELDS = "has_input_fields"
    HAS_IMAGES = "has_images"
    REQUIRES_AI = "requires_ai"


@dataclass
class OptionSpec:
    """Describes one configurable option for a technique."""
    name: str
    description: str
    type: type
    default: Any
    min_value: Any = None
    max_value: Any = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type.__name__,
            "default": self.default,
            "min_value": self.min_value,
            "max_value": self.max_value,
        }


@dataclass
class ChangeEntry:
    """Records a single mutation made by a technique.

    `details` is the structured-data slot. Techniques drop machine-readable
    extras here (counts, selector results, sizes) without bloating the
    human-readable `description` / `before` / `after` strings.
    """
    technique_id: int
    technique_name: str
    change_type: str
    description: str
    before: str | None = None
    after: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "technique_id": self.technique_id,
            "technique_name": self.technique_name,
            "change_type": self.change_type,
            "description": self.description,
            "before": self.before[:120] if self.before else None,
            "after": self.after[:120] if self.after else None,
        }
        if self.details:
            d["details"] = self.details
        return d


@dataclass
class ApplyResult:
    """Returned by every technique's apply() method."""
    modified_html: str | None
    modified_url: str | None
    extra_files: dict[str, bytes] = field(default_factory=dict)
    change_log: list[ChangeEntry] = field(default_factory=list)


@dataclass
class EvaluationResult:
    """Quality check result returned by every technique's evaluate() method.

    Fields
    ------
    passed : bool
        True when all critical signals are present — the technique artifact
        is verifiably embedded in the output.
    score : float
        0.0–1.0.  signals / (signals + issues).  Allows partial credit when
        some but not all signals are present.
    signals : list[str]
        Each string names a concrete evidence item that was confirmed
        (e.g. "Cyrillic homoglyph chars found in domain").
    issues : list[str]
        Each string names something that was expected but missing or wrong
        (e.g. "form action still points to original URL").
    details : dict
        Technique-specific numeric / structured metrics suitable for CSV
        export (e.g. {"glyph_count": 3, "chars_replaced": 2}).
    """
    passed: bool
    score: float
    signals: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": round(self.score, 3),
            "signals": self.signals,
            "issues": self.issues,
            "details": self.details,
        }


class BaseTechnique(ABC):
    """
    Abstract base for all 25 phishing techniques.

    Subclasses must declare these ClassVars:
        TECHNIQUE_ID, TECHNIQUE_NAME, GROUP, CATEGORIES,
        REQUIREMENTS, DESCRIPTION, OPTION_SPECS
    """

    TECHNIQUE_ID: ClassVar[int]
    TECHNIQUE_NAME: ClassVar[str]
    GROUP: ClassVar[TechniqueGroup]
    CATEGORIES: ClassVar[list[Category]]
    REQUIREMENTS: ClassVar[list[Requirement]]
    DESCRIPTION: ClassVar[str]
    OPTION_SPECS: ClassVar[list[OptionSpec]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "__abstractmethods__", None):
            return
        required_attrs = (
            "TECHNIQUE_ID", "TECHNIQUE_NAME", "GROUP", "CATEGORIES",
            "REQUIREMENTS", "DESCRIPTION", "OPTION_SPECS",
        )
        for attr in required_attrs:
            if not hasattr(cls, attr):
                raise TypeError(
                    f"{cls.__name__} must define ClassVar '{attr}'"
                )
        if not cls.CATEGORIES:
            raise TypeError(
                f"{cls.__name__}.CATEGORIES must contain at least one Category"
            )
        from app.core.registry import TechniqueRegistry
        TechniqueRegistry.register(cls)

    @abstractmethod
    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        """
        Apply this technique to the given HTML/URL.

        Parameters
        ----------
        html : str
            Current HTML string (may be empty for URL-only techniques).
        url : str
            Current URL string.
        options : dict[str, Any]
            User options already merged with defaults.
        screenshot_bytes : bytes | None
            Raw bytes of uploaded screenshot image, if any.

        Returns
        -------
        ApplyResult
            modified_html=None means HTML is unchanged.
            modified_url=None means URL is unchanged.
        """
        ...

    @classmethod
    def get_default_options(cls) -> dict[str, Any]:
        return {spec.name: spec.default for spec in cls.OPTION_SPECS}

    def _detect_lang(self, html: str, url: str = "") -> str:
        """Detect target page language (ISO 639-1) for choosing injected
        popup/form/page strings. Delegates to `app.utils.i18n` and defaults
        to Persian (`fa`). Imported lazily to keep base.py free of cycles.

        When `url` is supplied, the TLD is checked first: `.ir` domains are
        always served as Persian regardless of the HTML `lang` attribute,
        because many Iranian academic/government sites set `lang="en"` but
        are operated in Persian.
        """
        from app.utils.i18n import detect_language
        return detect_language(html or "", url)

    def log(self, level: str, event: str, **fields: Any) -> None:
        """Emit a structured log line tagged with technique + entry context.

        Usage inside `apply()`:
            self.log("info", "logo_picked", picker="rel=apple-touch-icon", scanned=12)
            self.log("warning", "no_logo_found", reason="no_img_tags")

        Output is logfmt:
            tid=7 entry=microsoft_login event=logo_picked picker=rel=apple-touch-icon scanned=12

        Cheap when the logger is disabled (early return on `isEnabledFor`).
        """
        lvl = logging.getLevelName(level.upper())
        if not isinstance(lvl, int):
            lvl = logging.INFO
        if not _TECH_LOGGER.isEnabledFor(lvl):
            return
        base_fields = {
            "tid": getattr(self, "TECHNIQUE_ID", "?"),
            "entry": _ctx_entry_id.get(),
            "event": event,
        }
        run_id = _ctx_run_id.get()
        if run_id and run_id != "-":
            base_fields["run"] = run_id
        base_fields.update(fields)
        _TECH_LOGGER.log(lvl, _logfmt(base_fields))

    @classmethod
    def to_info_dict(cls) -> dict[str, Any]:
        return {
            "id": cls.TECHNIQUE_ID,
            "name": cls.TECHNIQUE_NAME,
            "group": cls.GROUP.value,
            "categories": [c.value for c in cls.CATEGORIES],
            "description": cls.DESCRIPTION,
            "requirements": [r.value for r in cls.REQUIREMENTS],
            "options": [spec.to_dict() for spec in cls.OPTION_SPECS],
        }

    def evaluate(
        self,
        html: str,
        url: str,
        change_log: "list[ChangeEntry]",
        extra_files: "dict[str, bytes]",
    ) -> "EvaluationResult":
        """Quality-check the technique output. Override in each subclass.

        Parameters
        ----------
        html : str
            The generated (phishing) HTML as a string.
        url : str
            The phishing URL string.
        change_log : list[ChangeEntry]
            The change_log returned by apply().
        extra_files : dict[str, bytes]
            Any extra files returned by apply().

        Returns
        -------
        EvaluationResult
            passed=True when all critical signals are present.
        """
        return EvaluationResult(
            passed=False,
            score=0.0,
            signals=[],
            issues=["evaluate() not implemented for this technique"],
        )

    def _eval_score(self, signals: list, issues: list) -> float:
        total = len(signals) + len(issues)
        return round(len(signals) / total, 3) if total else 0.0

    def _make_change(
        self,
        change_type: str,
        description: str,
        before: str | None = None,
        after: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> ChangeEntry:
        return ChangeEntry(
            technique_id=self.TECHNIQUE_ID,
            technique_name=self.TECHNIQUE_NAME,
            change_type=change_type,
            description=description,
            before=before,
            after=after,
            details=dict(details) if details else {},
        )
