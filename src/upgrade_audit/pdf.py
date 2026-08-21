# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Fleet PDF builder. PhD register. No decorative em dashes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .constants import ERROR_CLASS_TITLES, PDF_CONFIRMED_CAP, SEVERITY_RANK
from .findings import body_and_overflow, confirmed_findings, count_by_severity

INK = colors.HexColor("#1a2430")
MUTED = colors.HexColor("#4a5563")
HDR_BG = colors.HexColor("#e4ebe7")
GRID = colors.HexColor("#c5d0c8")
BOX_FILL = colors.HexColor("#eef5f1")


def _esc(text: Any) -> str:
    # $ is a reportlab Paragraph escape; leave it as a character entity.
    return escape("" if text is None else str(text)).replace("$", "&#36;")


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "UATitle",
            parent=base["Title"],
            fontName="Times-Bold",
            fontSize=16,
            leading=20,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "UAH1",
            parent=base["Heading1"],
            fontName="Times-Bold",
            fontSize=13,
            leading=16,
            textColor=INK,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "UAH2",
            parent=base["Heading2"],
            fontName="Times-Bold",
            fontSize=11,
            leading=14,
            textColor=INK,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "UABody",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=10,
            leading=13,
            textColor=INK,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "UABullet",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=9.5,
            leading=12,
            textColor=INK,
            spaceAfter=2,
        ),
        "meta": ParagraphStyle(
            "UAMeta",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=9,
            leading=12,
            textColor=MUTED,
            spaceAfter=4,
        ),
        "cell": ParagraphStyle(
            "UACell",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=8,
            leading=10,
            textColor=INK,
        ),
        "cellb": ParagraphStyle(
            "UACellB",
            parent=base["Normal"],
            fontName="Times-Bold",
            fontSize=8,
            leading=10,
            textColor=INK,
        ),
    }


def _header_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(MUTED)
    canvas.setFont("Times-Roman", 8)
    canvas.drawString(0.75 * inch, 0.45 * inch, "Martial Systems LLC. All rights reserved.")
    canvas.drawRightString(letter[0] - 0.75 * inch, 0.45 * inch, "page {0}".format(doc.page))
    canvas.restoreState()


def _bullets(items: Sequence[str], style: ParagraphStyle) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(item, style), leftIndent=8) for item in items],
        bulletType="bullet",
        start="•",
        leftIndent=14,
        bulletFontName="Times-Roman",
        bulletFontSize=9,
    )


def _table(rows: List[List[Paragraph]], col_widths: Sequence[float]) -> Table:
    tbl = Table(rows, colWidths=list(col_widths), repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HDR_BG),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return tbl


def _load_run(run_dir: Path) -> Dict[str, Any]:
    manifest = {}
    man_path = run_dir / "manifest.json"
    if man_path.is_file():
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
    reports = []
    repos = run_dir / "repos"
    if repos.is_dir():
        for path in sorted(repos.glob("*.json")):
            if path.name.endswith(".unverified.json"):
                continue
            reports.append(json.loads(path.read_text(encoding="utf-8")))
    inventory = {}
    inv_path = run_dir / "inventory.json"
    if inv_path.is_file():
        inventory = json.loads(inv_path.read_text(encoding="utf-8"))
    catalog_excluded = []
    cat_path = run_dir / "excluded.json"
    if cat_path.is_file():
        catalog_excluded = json.loads(cat_path.read_text(encoding="utf-8"))
    ledger = {}
    led_path = run_dir / "ledger.json"
    if led_path.is_file():
        ledger = json.loads(led_path.read_text(encoding="utf-8"))
    skipped = []
    walk_path = run_dir / "walk.json"
    if walk_path.is_file():
        walk = json.loads(walk_path.read_text(encoding="utf-8"))
        if isinstance(walk, dict):
            skipped = list(walk.get("skipped") or [])
    return {
        "manifest": manifest,
        "reports": reports,
        "inventory": inventory,
        "excluded": catalog_excluded,
        "ledger": ledger,
        "skipped": skipped,
    }


def _short_sha(sha: str) -> str:
    sha = sha or ""
    return sha[:12] if len(sha) > 12 else sha


def _highest_class(findings: Sequence[Mapping[str, Any]]) -> str:
    if not findings:
        return "none"
    best = sorted(findings, key=lambda f: SEVERITY_RANK.get(f.get("severity"), 9))[0]
    return ERROR_CLASS_TITLES.get(best.get("error_class"), best.get("error_class") or "none")


def build_pdf(
    run_dir: Path,
    dest: Path,
    from_ver: str,
    to_ver: str,
    day: Optional[str] = None,
    revisions: Optional[Sequence[str]] = None,
) -> Path:
    data = _load_run(run_dir)
    manifest = data["manifest"]
    reports: List[dict] = data["reports"]
    order = list(manifest.get("repos") or [])
    if order:
        rank = {name: i for i, name in enumerate(order)}
        reports = sorted(reports, key=lambda r: rank.get(r.get("repo"), 10**6))
    day = day or manifest.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    styles = _styles()
    dest.parent.mkdir(parents=True, exist_ok=True)

    story: List[Any] = []
    story.append(
        Paragraph(
            "Model-upgrade logic audit: Grok {0} to {1} ({2})".format(
                _esc(from_ver), _esc(to_ver), _esc(day)
            ),
            styles["title"],
        )
    )
    story.append(
        Paragraph(
            "Martial Systems LLC. Read-only. No fixes applied. Generated {0}.".format(
                _esc(generated)
            ),
            styles["meta"],
        )
    )
    story.append(Paragraph("Revisions ({0})".format(_esc(day)), styles["h1"]))
    rev_items = list(revisions or [])
    if not rev_items:
        rev_items = [
            "{0}: first {1} to {2} fleet PDF from this runner.".format(day, from_ver, to_ver)
        ]
    story.append(_bullets([_esc(x) for x in rev_items], styles["bullet"]))

    story.append(Paragraph("1. Method ({0})".format(_esc(day)), styles["h1"]))
    story.append(
        Paragraph(
            "This document is a model-upgrade logic audit. A later Grok generation "
            "reads the shipped default-branch commit of each owned product repository "
            "and records specific errors. It does not restyle code and it does not "
            "apply patches. Findings enter the main list only after a second read-only "
            "pass fails to refute the cited evidence. Unverified or rejected items stay "
            "in Appendix B.",
            styles["body"],
        )
    )
    story.append(
        _bullets(
            [
                "Catalog: <font face='Courier'>catalog/repos.yaml</font> is the scope list. "
                "A new owned non-fork that is on GitHub and not in the catalog halts the run.",
                "Commit: the audited object is the audit remote's default-branch HEAD, "
                "not the dirty working tree.",
                "Dirty trees: recorded as residual risk. Never discarded, reset, or stashed away.",
                "Empty findings: valid only when the auditor names the files it read.",
                "Cap: at most {0} confirmed findings per repo in the chapter body; overflow is titled only.".format(
                    PDF_CONFIRMED_CAP
                ),
                "Not done: no live play-through of games, no Kalshi order, no public-site deploy, "
                "no Chrome Web Store walk.",
            ],
            styles["bullet"],
        )
    )

    story.append(Paragraph("2. Fleet summary ({0})".format(_esc(day)), styles["h1"]))
    if not reports:
        story.append(
            Paragraph(
                "No per-repo reports were present in this run directory. "
                "The fleet has not been audited.",
                styles["body"],
            )
        )
    else:
        s = styles
        header = [
            Paragraph("<b>Repo</b>", s["cellb"]),
            Paragraph("<b>SHA</b>", s["cellb"]),
            Paragraph("<b>Dirty</b>", s["cellb"]),
            Paragraph("<b>C</b>", s["cellb"]),
            Paragraph("<b>M</b>", s["cellb"]),
            Paragraph("<b>N</b>", s["cellb"]),
            Paragraph("<b>Highest class</b>", s["cellb"]),
        ]
        rows = [header]
        for report in reports:
            confirmed = confirmed_findings(report)
            counts = count_by_severity(confirmed)
            rows.append(
                [
                    Paragraph(_esc(report.get("repo")), s["cell"]),
                    Paragraph(_esc(_short_sha(report.get("audited_sha") or "")), s["cell"]),
                    Paragraph("yes" if report.get("dirty") else "no", s["cell"]),
                    Paragraph(str(counts["critical"]), s["cell"]),
                    Paragraph(str(counts["major"]), s["cell"]),
                    Paragraph(str(counts["minor"]), s["cell"]),
                    Paragraph(_esc(_highest_class(confirmed)), s["cell"]),
                ]
            )
        story.append(
            _table(rows, [1.55 * inch, 1.05 * inch, 0.5 * inch, 0.35 * inch, 0.35 * inch, 0.35 * inch, 2.35 * inch])
        )
        story.append(
            Paragraph(
                "Columns C / M / N: confirmed critical, major, and minor. "
                "Dirty means the local working tree had uncommitted paths; those paths were not audited.",
                styles["meta"],
            )
        )

    skipped = list(data.get("skipped") or [])
    if skipped:
        story.append(
            Paragraph(
                "Skipped repos are not clean. They have no confirmed-empty report.",
                styles["body"],
            )
        )
        story.append(
            _bullets(
                [
                    "{0}: {1}".format(_esc(row.get("repo")), _esc(row.get("reason")))
                    for row in skipped
                    if isinstance(row, dict)
                ],
                styles["bullet"],
            )
        )

    story.append(Paragraph("3. Per-repo chapters ({0})".format(_esc(day)), styles["h1"]))
    if not reports:
        story.append(Paragraph("None. See section 2.", styles["body"]))
    for report in reports:
        story.append(Paragraph(_esc(report.get("repo")), styles["h2"]))
        story.append(
            Paragraph(
                "GitHub: {0}. Audited: {1} at {2}. Dirty: {3}.".format(
                    _esc(report.get("github")),
                    _esc(report.get("audited_ref")),
                    _esc(_short_sha(report.get("audited_sha") or "")),
                    "yes" if report.get("dirty") else "no",
                ),
                styles["meta"],
            )
        )
        note = report.get("sync_note") or ""
        if note:
            story.append(Paragraph(_esc(note), styles["meta"]))
        body, overflow = body_and_overflow(report)
        if not body:
            story.append(
                Paragraph(
                    "No confirmed findings. This is not a play-through certification.",
                    styles["body"],
                )
            )
        for i, finding in enumerate(body, start=1):
            title = ERROR_CLASS_TITLES.get(finding.get("error_class"), finding.get("error_class"))
            story.append(
                Paragraph(
                    "{0}. [{1}] {2} ({3}:{4})".format(
                        i,
                        _esc(finding.get("severity")),
                        _esc(title),
                        _esc(finding.get("file")),
                        _esc(finding.get("line")),
                    ),
                    styles["h2"],
                )
            )
            story.append(
                _bullets(
                    [
                        "Claim: {0}".format(_esc(finding.get("claim"))),
                        "Evidence: {0}".format(_esc(finding.get("evidence"))),
                        "Proposed change (not applied): {0}".format(_esc(finding.get("proposed_fix"))),
                        "Verifier: {0}".format(_esc(finding.get("verifier_evidence"))),
                    ],
                    styles["bullet"],
                )
            )
        if overflow:
            story.append(Paragraph("Overflow (titles only)", styles["h2"]))
            story.append(
                _bullets(
                    [
                        "[{0}] {1}: {2}".format(
                            _esc(f.get("severity")),
                            _esc(f.get("file")),
                            _esc(f.get("claim")),
                        )
                        for f in overflow
                    ],
                    styles["bullet"],
                )
            )

    story.append(PageBreak())
    story.append(Paragraph("Appendix A. Excluded repositories ({0})".format(_esc(day)), styles["h1"]))
    excluded = data["excluded"]
    if not excluded:
        inv = data["inventory"]
        excluded = [{"github": g, "reason": "catalog exclusion"} for g in inv.get("excluded") or []]
    if not excluded:
        story.append(Paragraph("No exclusion list was written into this run directory.", styles["body"]))
    else:
        s = styles
        rows = [
            [
                Paragraph("<b>GitHub</b>", s["cellb"]),
                Paragraph("<b>Reason</b>", s["cellb"]),
            ]
        ]
        for row in excluded:
            if isinstance(row, str):
                gh, reason = row, ""
            else:
                gh = row.get("github") or row.get("name") or ""
                reason = row.get("reason") or ""
            rows.append([Paragraph(_esc(gh), s["cell"]), Paragraph(_esc(reason), s["cell"])])
        story.append(_table(rows, [3.2 * inch, 3.8 * inch]))

    story.append(Paragraph("Appendix B. Unverified or rejected ({0})".format(_esc(day)), styles["h1"]))
    extras = []
    for report in reports:
        for finding in report.get("findings") or []:
            if finding.get("status") in ("unverified", "rejected"):
                extras.append(finding)
    if not extras:
        story.append(Paragraph("None recorded.", styles["body"]))
    else:
        story.append(
            _bullets(
                [
                    "[{0} / {1}] {2} {3}:{4}: {5}".format(
                        _esc(f.get("status")),
                        _esc(f.get("severity")),
                        _esc(f.get("repo")),
                        _esc(f.get("file")),
                        _esc(f.get("line")),
                        _esc(f.get("claim")),
                    )
                    for f in extras
                ],
                styles["bullet"],
            )
        )

    story.append(Paragraph("Appendix C. Prior-run ledger ({0})".format(_esc(day)), styles["h1"]))
    ledger = data["ledger"]
    if not ledger or not ledger.get("prior"):
        story.append(
            Paragraph(
                "No prior run. First pass of this from/to pair has an empty ledger.",
                styles["body"],
            )
        )
    else:
        counts = ledger.get("counts") or {}
        story.append(
            Paragraph(
                "Still open: {0}. New: {1}. Gone: {2}.".format(
                    counts.get("still_open", 0),
                    counts.get("new", 0),
                    counts.get("gone", 0),
                ),
                styles["body"],
            )
        )
        for label, key in (("Still open", "still_open"), ("New", "new"), ("Gone", "gone")):
            rows = ledger.get(key) or []
            if not rows:
                continue
            story.append(Paragraph(label, styles["h2"]))
            story.append(
                _bullets(
                    [
                        "{0} {1}: {2}".format(
                            _esc(f.get("repo")),
                            _esc(f.get("file")),
                            _esc(f.get("claim")),
                        )
                        for f in rows
                    ],
                    styles["bullet"],
                )
            )

    doc = SimpleDocTemplate(
        str(dest),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="Model-upgrade logic audit: Grok {0} to {1}".format(from_ver, to_ver),
        author="Martial Systems LLC",
    )
    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return dest
