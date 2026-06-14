from __future__ import annotations

from app.core.engine import RunResult, TechniqueRunResult


def _trunc(s: str, n: int = 120) -> str:
    return s[:n] + "…" if len(s) > n else s


def _url_line(label: str, url: str) -> str:
    """Format a URL field, noting when it contains Unicode homoglyphs."""
    try:
        url.encode("ascii")
        return f"  - {label}: `{_trunc(url)}`"
    except UnicodeEncodeError:
        ascii_approx = url.encode("ascii", errors="replace").decode()
        return (
            f"  - {label}: `{_trunc(url)}`"
            f"  _(⚠ contains Unicode homoglyphs — visually identical to `{_trunc(ascii_approx)}`)_"
        )


class ReportBuilder:
    """Builds a human-readable Markdown change report from a RunResult."""

    @staticmethod
    def build(result: RunResult) -> str:
        successful = [r for r in result.technique_results if r.success]
        failed = [r for r in result.technique_results if not r.success]
        all_changes = [c for r in successful for c in r.changes]

        lines = [
            "# Phishing Generation Report",
            "",
            f"**Run ID:** `{result.run_id}`",
            f"**Original URL:** `{result.original_url}`",
            f"**Final URL:** `{result.final_url}`",
            f"**Techniques applied:** {len(successful)} / {len(result.technique_results)}",
            f"**Total mutations:** {len(all_changes)}",
            "",
            "---",
            "",
            "## Technique Results",
            "",
        ]

        for r in result.technique_results:
            status_icon = "✅" if r.success else "❌"
            lines.append(f"### {status_icon} T{r.technique_id} — {r.technique_name}")

            if not r.success:
                lines.append(f"- **Skipped / Error:** {r.error}")
            else:
                if r.modified_url:
                    try:
                        r.modified_url.encode("ascii")
                        lines.append(f"- **Modified URL:** `{_trunc(r.modified_url)}`")
                    except UnicodeEncodeError:
                        ascii_approx = r.modified_url.encode("ascii", errors="replace").decode()
                        lines.append(
                            f"- **Modified URL:** `{_trunc(r.modified_url)}`"
                            f"  _(⚠ Unicode homoglyphs — looks like `{_trunc(ascii_approx)}`)_"
                        )
                if r.extra_file_names:
                    lines.append(f"- **Extra files:** {', '.join(r.extra_file_names)}")
                for change in r.changes:
                    lines.append(f"- **[{change.change_type}]** {change.description}")
                    if change.before:
                        lines.append(_url_line("Before", change.before))
                    if change.after:
                        after_line = _url_line("After ", change.after)
                        if (
                            change.before
                            and change.before == change.after
                            and change.before is not change.after
                        ):
                            after_line += "  _(unchanged — no eligible characters found)_"
                        lines.append(after_line)
                    if change.details:
                        for k, v in change.details.items():
                            if isinstance(v, (list, tuple)):
                                shown = ", ".join(str(x) for x in list(v)[:8])
                                if len(v) > 8:
                                    shown += f"  _(+{len(v) - 8} more)_"
                            elif isinstance(v, dict):
                                shown = ", ".join(f"{kk}={vv}" for kk, vv in list(v.items())[:8])
                            else:
                                shown = _trunc(str(v), 200)
                            lines.append(f"  - _{k}_: `{shown}`")

            lines.append("")

        lines += [
            "---",
            "",
            "## HTML Size",
            f"- Original: {len(result.original_html):,} bytes",
            f"- Final:    {len(result.final_html):,} bytes",
            f"- Delta:    {len(result.final_html) - len(result.original_html):+,} bytes",
            "",
            "## Extra Files",
        ]
        if result.extra_files:
            for name, data in result.extra_files.items():
                lines.append(f"- `{name}` ({len(data):,} bytes)")
        else:
            lines.append("- *(none)*")

        return "\n".join(lines)
