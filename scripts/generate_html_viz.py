"""
Generate a single HTML visualization for the four annotated datasets.
Highlights emotion expression mode spans with 4 colours:
  - Désignée   : rgb(40, 80, 160)   - Blue
  - Comportementale : rgb(0, 130, 100) - Teal
  - Suggérée   : rgb(180, 100, 20)  - Amber
  - Montrée    : rgb(120, 50, 140)  - Violet
Filters out texts with no annotated emotion (Emo == 0).
"""

import html
import json
from collections import Counter
from pathlib import Path

import openpyxl

# ── colour map ──────────────────────────────────────────────────────
MODE_COLORS = {
    "Désignée": "rgba(40, 80, 160, 0.30)",
    "Comportementale": "rgba(0, 130, 100, 0.30)",
    "Suggérée": "rgba(180, 100, 20, 0.30)",
    "Montrée": "rgba(120, 50, 140, 0.30)",
}
MODE_COLORS_SOLID = {
    "Désignée": "rgb(40, 80, 160)",
    "Comportementale": "rgb(0, 130, 100)",
    "Suggérée": "rgb(180, 100, 20)",
    "Montrée": "rgb(120, 50, 140)",
}

MODES = list(MODE_COLORS.keys())
EMOTION_LABELS = [
    "Colère", "Dégoût", "Joie", "Peur", "Surprise", "Tristesse",
    "Admiration", "Culpabilité", "Embarras", "Fierté", "Jalousie", "Autre",
]

# ── column renaming (legacy aggregate.py outputs used unaccented names) ─
COL_RENAME = {
    "Designee": "Désignée",
    "Montree": "Montrée",
    "Suggeree": "Suggérée",
    "Colere": "Colère",
    "Degout": "Dégoût",
    "Culpabilite": "Culpabilité",
    "Fierte": "Fierté",
}


def normalise_record(row: dict) -> dict:
    """Rename legacy unaccented columns to accented names (no-op if already accented).
    Also promote _span_details -> spans_json when spans_json is absent."""
    out = {}
    for k, v in row.items():
        out[COL_RENAME.get(k, k)] = v
    if "spans_json" not in out and "_span_details" in out:
        out["spans_json"] = out["_span_details"]
    return out


# ── helpers ─────────────────────────────────────────────────────────

def read_xlsx(path: str) -> tuple[list[str], list[tuple]]:
    """Return (headers, rows) from first sheet."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    rows = [tuple(c.value for c in row) for row in ws.iter_rows(min_row=2)]
    wb.close()
    return headers, rows


def rows_to_dicts(headers, rows):
    return [normalise_record(dict(zip(headers, r))) for r in rows]


def is_active_flag(value) -> bool:
    if value is None or value == "":
        return False
    try:
        return int(value) == 1
    except (TypeError, ValueError):
        return str(value).strip() == "1"



def highlight_text_with_spans(text: str, spans_json_str: str) -> str:
    """Return HTML with highlighted spans. Handles overlapping spans."""
    text = "" if text is None else str(text)
    if not spans_json_str or spans_json_str == "[]":
        return html.escape(text)

    try:
        spans = json.loads(spans_json_str)
    except (json.JSONDecodeError, TypeError):
        return html.escape(text)

    if not spans:
        return html.escape(text)

    intervals = []
    st_lower = text.lower()
    for sp in spans:
        span_text = sp.get("span_text", "")
        mode = sp.get("mode", "")
        if not span_text or mode not in MODE_COLORS:
            continue
        idx = st_lower.find(str(span_text).lower())
        if idx != -1:
            intervals.append((idx, idx + len(span_text), mode))

    if not intervals:
        return html.escape(text)

    char_modes = [set() for _ in range(len(text))]
    for start, end, mode in intervals:
        for i in range(start, min(end, len(text))):
            char_modes[i].add(mode)

    result = []
    i = 0
    while i < len(text):
        modes = frozenset(char_modes[i])
        j = i + 1
        while j < len(text) and frozenset(char_modes[j]) == modes:
            j += 1
        chunk = html.escape(text[i:j])
        if modes:
            sorted_modes = sorted(modes)
            bg = MODE_COLORS[sorted_modes[0]]
            border_bottom = ""
            if len(sorted_modes) > 1:
                border_bottom = f"border-bottom:2px solid {MODE_COLORS_SOLID[sorted_modes[1]]};"
            title = " + ".join(sorted_modes)
            result.append(
                f'<span class="hl" style="background:{bg};{border_bottom}" title="{title}">{chunk}</span>'
            )
        else:
            result.append(chunk)
        i = j

    return "".join(result)



def compute_stats(records: list[dict]) -> dict:
    total = len(records)
    mode_counts = {m: 0 for m in MODES}
    emo_counts = Counter()
    corpus_counts = Counter()

    for r in records:
        corpus_counts[r["corpus_label"]] += 1
        for m in MODES:
            if is_active_flag(r.get(m)):
                mode_counts[m] += 1
        for e in EMOTION_LABELS:
            if is_active_flag(r.get(e)):
                emo_counts[e] += 1

    return {
        "total": total,
        "mode_counts": mode_counts,
        "emo_counts": dict(emo_counts),
        "corpus_counts": dict(corpus_counts),
    }



def get_active_modes(row: dict) -> list[str]:
    return [m for m in MODES if is_active_flag(row.get(m))]



def get_active_emotions(row: dict) -> list[str]:
    return [e for e in EMOTION_LABELS if is_active_flag(row.get(e))]


# ── HTML template ───────────────────────────────────────────────────

HTML_HEADER = """\
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<style>
  body {{
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 11px;
    line-height: 1.25;
    margin: 20px;
    color: #222;
  }}
  h1 {{ font-size: 18px; margin-bottom: 4px; }}
  h2 {{ font-size: 14px; margin: 18px 0 6px; }}
  h3 {{ font-size: 12px; margin: 0 0 6px; }}
  .stats-grid {{
    display: flex; gap: 24px; flex-wrap: wrap;
    margin-bottom: 12px;
  }}
  .stat-box {{
    background: #f5f5f5; border-radius: 6px; padding: 8px 14px;
  }}
  .bar-row {{
    display: flex; align-items: center; gap: 4px;
    margin: 1px 0; font-size: 10px;
  }}
  .bar-label {{ width: 120px; text-align: right; }}
  .bar {{
    height: 12px; border-radius: 2px; min-width: 2px;
  }}
  .legend {{
    display: flex; gap: 14px; margin: 8px 0 10px;
    font-size: 11px; align-items: center; flex-wrap: wrap;
  }}
  .legend-item {{
    display: inline-flex; align-items: center; gap: 3px;
  }}
  .legend-swatch {{
    display: inline-block; width: 14px; height: 14px;
    border-radius: 2px;
  }}
  .text-row {{
    padding: 4px 0;
    border-bottom: 1px solid #eee;
  }}
  .text-idx {{
    color: #999; font-size: 9px; margin-right: 6px;
    display: inline-block; width: 36px; text-align: right;
  }}
  .hl {{
    border-radius: 2px;
    padding: 0 1px;
  }}
  .meta {{
    color: #777; font-size: 9px; margin-left: 6px;
  }}
  #filter-bar {{
    margin: 8px 0 14px;
    display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
    position: sticky; top: 0; background: #fff; padding: 8px 0;
    border-bottom: 1px solid #eee;
  }}
  #filter-bar label {{
    font-size: 11px; cursor: pointer;
  }}
  #filter-bar input[type=checkbox] {{ margin-right: 2px; }}
  #search-box {{
    font-size: 11px; padding: 2px 6px; width: 260px;
  }}
  .char-name {{ font-size: 10px; font-weight: bold; }}
  .char-role {{ color: #777; font-size: 9px; margin-left: 6px; }}
  .corpus-section {{ margin-top: 20px; }}
  .corpus-summary {{ color: #666; font-size: 10px; margin-bottom: 8px; }}
  .corpus-tag {{
    display: inline-block; font-size: 9px; font-weight: 700;
    color: #fff; background: #444; border-radius: 10px;
    padding: 1px 7px; margin-right: 8px;
    vertical-align: middle;
  }}
  .hide-names .char-name {{ display: none; }}
  .hide-roles .char-role {{ display: none; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p style="font-size:11px;color:#666;">{subtitle}</p>
"""

HTML_FOOTER = """\
<script>
function applyFilters() {
  var modeChecks = document.querySelectorAll('.mode-filter');
  var corpusChecks = document.querySelectorAll('.corpus-filter');
  var activeModes = [];
  var activeCorpora = [];
  modeChecks.forEach(function(cb) { if (cb.checked) activeModes.push(cb.value); });
  corpusChecks.forEach(function(cb) { if (cb.checked) activeCorpora.push(cb.value); });
  var search = (document.getElementById('search-box') || {}).value || '';
  search = search.toLowerCase();
  var rows = document.querySelectorAll('.text-row');
  var shown = 0;
  rows.forEach(function(row) {
    var modes = (row.dataset.modes || '').split(',').filter(Boolean);
    var corpus = row.dataset.corpus || '';
    var modeOk = activeModes.length === 0 || activeModes.some(function(m) { return modes.indexOf(m) >= 0; });
    var corpusOk = activeCorpora.length === 0 || activeCorpora.indexOf(corpus) >= 0;
    var textOk = !search || row.textContent.toLowerCase().indexOf(search) >= 0;
    if (modeOk && corpusOk && textOk) {
      row.style.display = '';
      shown++;
    } else {
      row.style.display = 'none';
    }
  });

  document.querySelectorAll('.corpus-section').forEach(function(section) {
    var visibleRows = section.querySelectorAll('.text-row:not([style*="display: none"])').length;
    section.style.display = visibleRows ? '' : 'none';
  });

  document.getElementById('shown-count').textContent = shown;
}
document.querySelectorAll('.mode-filter, .corpus-filter').forEach(function(cb) { cb.addEventListener('change', applyFilters); });
var sb = document.getElementById('search-box');
if (sb) sb.addEventListener('input', applyFilters);
var btnName = document.getElementById('toggle-names');
var btnRole = document.getElementById('toggle-roles');
if (btnName) btnName.addEventListener('click', function() {
  document.body.classList.toggle('hide-names');
  this.classList.toggle('active');
});
if (btnRole) btnRole.addEventListener('click', function() {
  document.body.classList.toggle('hide-roles');
  this.classList.toggle('active');
});
applyFilters();
</script>
</body>
</html>
"""



def bar_chart_html(counts: dict, color_map: dict | None = None, max_width: int = 220) -> str:
    if not counts:
        return ""
    max_val = max(counts.values()) if counts.values() else 1
    lines = []
    for label, val in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        w = int(val / max_val * max_width) if max_val else 0
        c = (color_map or {}).get(label, "#888")
        lines.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{html.escape(label)}</span>'
            f'<div class="bar" style="width:{w}px;background:{c};"></div>'
            f'<span>{val}</span></div>'
        )
    return "\n".join(lines)



def legend_html() -> str:
    parts = []
    for mode, color in MODE_COLORS_SOLID.items():
        parts.append(
            f'<span class="legend-item">'
            f'<span class="legend-swatch" style="background:{color};"></span>'
            f'{mode}</span>'
        )
    return '<div class="legend">' + " ".join(parts) + '</div>'



def filter_bar_html(total: int, corpus_labels: list[str]) -> str:
    mode_checks = []
    for mode in MODES:
        c = MODE_COLORS_SOLID[mode]
        mode_checks.append(
            f'<label style="color:{c};font-weight:600;">'
            f'<input type="checkbox" class="mode-filter" value="{mode}" checked> {mode}</label>'
        )

    corpus_checks = []
    for corpus in corpus_labels:
        corpus_checks.append(
            f'<label style="font-weight:600;">'
            f'<input type="checkbox" class="corpus-filter" value="{html.escape(corpus)}" checked> {html.escape(corpus)}</label>'
        )

    return (
        '<div id="filter-bar">'
        + ''.join(mode_checks)
        + '<span style="width:1px;height:18px;background:#ddd;display:inline-block;"></span>'
        + ''.join(corpus_checks)
        + '<button id="toggle-names" class="toggle-btn" title="Masquer/afficher les noms">Noms</button>'
        + '<button id="toggle-roles" class="toggle-btn" title="Masquer/afficher les rôles">Rôles</button>'
        + '<input type="text" id="search-box" placeholder="Rechercher dans les textes…">'
        + f'<span style="font-size:10px;color:#999;">Affichés: <span id="shown-count">{total}</span> / {total}</span>'
        + '</div>'
    )



def render_record(record: dict, index_within_corpus: int) -> str:
    highlighted = highlight_text_with_spans(record.get("text") or "", record.get("spans_json") or "")
    active_modes = get_active_modes(record)
    active_emotions = get_active_emotions(record)
    modes_str = ",".join(active_modes)
    emo_str = ", ".join(active_emotions)
    name = html.escape(str(record.get("NAME") or ""))
    role = html.escape(str(record.get("ROLE") or ""))
    corpus_label = html.escape(record["corpus_label"])

    return (
        f'<div class="text-row" data-modes="{html.escape(modes_str)}" data-corpus="{corpus_label}">'
        f'<span class="text-idx">{index_within_corpus}</span>'
        f'<span class="corpus-tag">{corpus_label}</span>'
        f'<span class="char-name">{name}</span> '
        f'<span class="char-role">[{role}]</span> '
        f'{highlighted}'
        f'<span class="meta">[{html.escape(emo_str)}]</span>'
        '</div>'
    )



def generate_combined_html(corpus_records: list[tuple[str, list[dict]]], out_path: Path):
    all_records = [record for _, records in corpus_records for record in records]
    stats = compute_stats(all_records)
    title = "Visualisation unifiée des modes d'expression"
    subtitle = (
        f"{stats['total']} textes avec au moins une émotion annotée, "
        f"issus de 4 corpus XLSX réunis dans un seul fichier HTML"
    )

    parts = [HTML_HEADER.format(title=title, subtitle=subtitle)]
    parts.append('<div class="stats-grid">')
    parts.append('<div class="stat-box"><h3>Distribution des corpus</h3>')
    parts.append(bar_chart_html(stats["corpus_counts"], max_width=180))
    parts.append('</div>')
    parts.append('<div class="stat-box"><h3>Distribution des modes</h3>')
    parts.append(bar_chart_html(stats["mode_counts"], MODE_COLORS_SOLID))
    parts.append('</div>')
    parts.append('<div class="stat-box"><h3>Distribution des émotions</h3>')
    parts.append(bar_chart_html(stats["emo_counts"]))
    parts.append('</div></div>')

    parts.append(legend_html())
    parts.append(filter_bar_html(stats["total"], [label for label, _ in corpus_records]))

    for corpus_label, records in corpus_records:
        parts.append(f'<section class="corpus-section" data-corpus="{html.escape(corpus_label)}">')
        parts.append(f'<h2>{html.escape(corpus_label)}</h2>')
        parts.append(f'<div class="corpus-summary">{len(records)} textes</div>')
        for idx, record in enumerate(records, start=1):
            parts.append(render_record(record, idx))
        parts.append('</section>')

    parts.append(HTML_FOOTER)
    out_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"  -> {out_path}  ({stats['total']} texts, {len(corpus_records)} corpora)")


# ── main ────────────────────────────────────────────────────────────

def main():
    base = Path("/home/gwen/Annotations_v1")
    outputs_dir = base / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    datasets = [
        ("Homophobie", outputs_dir / "homophobie_annotations_gold_flat_updated.xlsx"),
        ("Obésité", outputs_dir / "obésité_annotations_gold_flat_updated.xlsx"),
        ("Racisme", outputs_dir / "racisme_annotations_gold_flat_updated.xlsx"),
        ("Religion", outputs_dir / "religion_annotations_gold_flat_updated.xlsx"),
    ]

    corpus_records = []
    for label, path in datasets:
        if not path.exists():
            print(f"⚠ Fichier introuvable pour {label} : {path}")
            continue

        print(f"Processing {label}…")
        headers, rows = read_xlsx(path)
        records = rows_to_dicts(headers, rows)
        records = [r for r in records if is_active_flag(r.get("Emo"))]
        for record in records:
            record["corpus_label"] = label
        corpus_records.append((label, records))

    if not corpus_records:
        raise SystemExit("Aucun corpus charge, aucun HTML genere.")

    out = outputs_dir / "viz_all_corpora.html"
    generate_combined_html(corpus_records, out)
    print("Done.")


if __name__ == "__main__":
    main()
