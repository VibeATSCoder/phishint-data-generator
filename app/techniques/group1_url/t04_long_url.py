from __future__ import annotations

from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.url_utils import add_query_params, random_hash_like, random_string


class LongUrlTechnique(BaseTechnique):
    """
    T4 — Very long URL + random/hash-like parameters.

    Appends many random query parameters to confuse length/entropy-based
    ML detectors and make the URL visually overwhelming.
    """

    TECHNIQUE_ID: ClassVar[int] = 4
    TECHNIQUE_NAME: ClassVar[str] = "Long URL + Random Hash Parameters"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.URL_MANIPULATION
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_URL]
    DESCRIPTION: ClassVar[str] = (
        "Appends many random/hash-like query parameters to the URL, "
        "increasing its length and character entropy to confuse "
        "statistical ML-based detectors."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="param_count",
            description="Number of random query parameters to append",
            type=int,
            default=8,
            min_value=1,
            max_value=50,
        ),
        OptionSpec(
            name="param_length",
            description="Length of each random parameter value",
            type=int,
            default=32,
            min_value=8,
            max_value=128,
        ),
        OptionSpec(
            name="hash_algorithm",
            description="Style of random value: 'random', 'md5_like', 'sha_like'",
            type=str,
            default="random",
        ),
    ]

    _MAX_TOTAL_URL_LEN = 8192

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        from app.utils.url_utils import parse_url
        param_count: int = int(options.get("param_count", 8))
        param_length: int = int(options.get("param_length", 32))
        hash_algo: str = options.get("hash_algorithm", "random")

        parsed, _ = parse_url(url)
        existing_params = parsed.query.count("=") if parsed.query else 0

        params = {
            random_string(6): random_hash_like(hash_algo, param_length)
            for _ in range(param_count)
        }
        new_url = add_query_params(url, params)

        if len(new_url) > self._MAX_TOTAL_URL_LEN:
            self.log("warning", "long_url_clamped",
                     orig_len=len(new_url), cap=self._MAX_TOTAL_URL_LEN)
            keys = list(params.keys())
            while len(new_url) > self._MAX_TOTAL_URL_LEN and keys:
                params.pop(keys.pop(), None)
                new_url = add_query_params(url, params)

        params_added = len(params)
        self.log("info", "long_url_applied",
                 params_added=params_added, final_len=len(new_url))

        return ApplyResult(
            modified_html=None,
            modified_url=new_url,
            extra_files={},
            change_log=[
                self._make_change(
                    "url_long_params",
                    f"Appended {params_added} random query params "
                    f"(style={hash_algo}, len={param_length})",
                    before=url,
                    after=new_url,
                    details={
                        "params_added": params_added,
                        "params_kept": existing_params,
                        "final_url_len": len(new_url),
                        "hash_algorithm": hash_algo,
                        "fragment_preserved": bool(parsed.fragment),
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        from urllib.parse import urlparse, parse_qs
        import math
        signals, issues = [], []

        parsed = urlparse(url if "://" in url else "https://" + url)
        url_len = len(url)
        params = parse_qs(parsed.query)
        param_count = len(params)

        if url_len >= 200:
            signals.append(f"URL length {url_len} chars (≥ 200 threshold)")
        else:
            issues.append(f"URL length {url_len} is short — long-URL evasion may not trigger")

        if param_count >= 5:
            signals.append(f"Has {param_count} query parameters (≥ 5)")
        else:
            issues.append(f"Only {param_count} query parameter(s) — expected ≥ 5 for ML evasion")

        values = [v[0] for v in params.values() if v]
        if values:
            avg_len = sum(len(v) for v in values) / len(values)
            joined = "".join(values)
            freq = {c: joined.count(c) / len(joined) for c in set(joined)}
            entropy = -sum(p * math.log2(p) for p in freq.values() if p > 0)
            if entropy >= 4.0:
                signals.append(f"Parameter value entropy {entropy:.2f} bits (≥ 4.0 — random-looking)")
            else:
                issues.append(f"Parameter entropy {entropy:.2f} bits — values may not look random enough")

        added = next(
            (e.details.get("params_added", 0) for e in change_log
             if e.change_type == "url_long_params"), 0
        )
        if added >= 5:
            signals.append(f"change_log: {added} params added")
        else:
            issues.append(f"change_log shows only {added} params added")

        passed = url_len >= 200 and param_count >= 5
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"url_len": url_len, "param_count": param_count, "params_added": added},
        )
