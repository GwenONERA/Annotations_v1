"""Generate one HTML visualization file aggregating the 4 annotated corpora.

The output HTML contains:
- one global overview across all corpora
- one section per corpus
- mode / corpus / text filters shared across the whole page
- inline span highlighting for annotated expression modes

Only rows with Emo == 1 are kept.
"""

from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from pathlib import Path

import openpyxl


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
MODES = list(MODE_COLORS)
EMOTION_LABELS = [
    "Colère",
    "Dégoût",
    "Joie",
    "Peur",
    "Surprise",
    "Tristesse",
    "Admiration",
    "Culpabilité",
    "Embarras",
    "Fierté",
    "Jalousie",
    "Autre",
]

COL_RENAME = {
    "Designee": "Désignée",
    "Montree": "Montrée",
    "Suggeree": "Suggérée",
    "Colere": "Colère",
    "Degout": "Dégoût",
    "Culpabilite": "Culpabilité",
    "Fierte": "Fierté",
}

DATASETS = [
    {
        "key": "homophobie",
        "label": "Homophobie",
        "path": "outputs/homophobie_annotations_gold_flat_updated.xlsx",
    },
    {
        "key": "obesite",
        "label": "Obésité",
        "path": "outputs/obésité_annotations_gold_flat_updated.xlsx",
    },
    {
        "key": "racisme",
        "label": "Racisme",
        "path": "outputs/racisme_annotations_gold_flat_updated.xlsx",
    },
    {
        "key": "religion",
        "label": "Religion",
        "path": "outputs/religion_annotations_gold_flat_updated.xlsx",
    },
]


def normalise_record(row: dict) -> dict:
    """Rename legacy unaccented columns and normalize span payload."""
    out = {COL_RENAME.get(k, k): v for k, v in row.items()}
    if "spans_json" not in out and "_span_details" in out:
        out["spans_json"] = out["_span_details"]
    if "text" not in out and "TEXT" in out:
        out["text"] = out["TEXT"]
    return out


def read_xlsx(path: Path) -> tuple[list[str], list[tuple]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    rows = [tuple(cell.value for cell in row) for row in ws.iter_rows(min_row=2)]
    wb.close()
    return headers, rows


def rows_to_dicts(headers: list[str], rows: list[tuple]) -> list[dict]:
    return [normalise_record(dict(zip(headers, row))) for row in rows]


def as_int(value) -> int:
    if value in (None, "", False):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def get_active_modes(row: dict) -> list[str]:
    return [mode for mode in MODES if as_int(row.get(mode)) == 1]


def get_active_emotions(row: dict) -> list[str]:
    return [emotion for emotion in EMOTION_LABELS if as_int(row.get(emotion)) == 1]


def compute_stats(records: list[dict]) -> dict:
    mode_counts = Counter()
    emotion_counts = Counter()
    for row in records:
        mode_counts.update(get_active_modes(row))
        emotion_counts.update(get_active_emotions(row))
    return {
        "total": len(records),
        "mode_counts": {mode: mode_counts.get(mode, 0) for mode in MODES},
        "emo_counts": {emotion: emotion_counts.get(emotion, 0) for emotion in EMOTION_LABELS if emotion_counts.get(emotion, 0)},
    }


def highlight_text_with_spans(text: str, spans_json_str: str | None) -> str:
    """Return escaped HTML with highlighted spans. Overlaps are supported."""
    if not text:
        return ""
    if not spans_json_str or spans_json_str == "[]":
        return html.escape(text)

    try:
        spans = json.loads(spans_json_str)
    except (json.JSONDecodeError, TypeError):
        return html.escape(text)

    if not spans:
        return html.escape(text)

    intervals: list[tuple[int, int, str]] = []
    text_lower = text.lower()

    for span in spans:
        span_text = (span or {}).get("span_text", "")
        mode = (span or {}).get("mode", "")
        if not span_text or mode not in MODE_COLORS:
            continue

        idx = text_lower.find(span_text.lower())
        if idx >= 0:
            intervals.append((idx, idx + len(span_text), mode))

    if not intervals:
        return html.escape(text)

    char_modes = [set() for _ in range(len(text))]
    for start, end, mode in intervals:
        for pos in range(start, min(end, len(text))):
            char_modes[pos].add(mode)

    chunks: list[str] = []
    i = 0
    while i < len(text):
        modes = frozenset(char_modes[i])
        j = i + 1
        while j < len(text) and frozenset(char_modes[j]) == modes:
            j += 1

        chunk = html.escape(text[i:j])
        if modes:
            sorted_modes = sorted(modes)
            background = MODE_COLORS[sorted_modes[0]]
            border_bottom = ""
            if len(sorted_modes) > 1:
                border_bottom = f"border-bottom:2px solid {MODE_COLORS_SOLID[sorted_modes[1]]};"
            title = html.escape(" + ".join(sorted_modes), quote=True)
            chunks.append(
                f'<span class="hl" style="background:{background};{border_bottom}" title="{title}">{chunk}</span>'
            )
        else:
            chunks.append(chunk)
        i = j

    return "".join(chunks)


def bar_chart_html(counts: dict, color_map: dict | None = None, max_width: int = 220) -> str:
    if not counts:
        return '<div class="empty-note">Aucune donnée.</div>'

    max_val = max(counts.values(), default=0)
    if max_val == 0:
        return '<div class="empty-note">Aucune occurrence.</div>'

    parts = []
    for label, value in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        width = int(value / max_val * max_width) if max_val else 0
        color = (color_map or {}).get(label, "#888")
        parts.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{html.escape(label)}</span>'
            f'<div class="bar" style="width:{width}px;background:{color};"></div>'
            f'<span>{value}</span>'
            f'</div>'
        )
    return "\n".join(parts)


def legend_html() -> str:
    items = []
    for mode, color in MODE_COLORS_SOLID.items():
        items.append(
            f'<span class="legend-item">'
            f'<span class="legend-swatch" style="background:{color};"></span>'
            f'{html.escape(mode)}'
            f'</span>'
        )
    return '<div class="legend">' + " ".join(items) + "</div>"


def render_toc(datasets: list[dict]) -> str:
    links = []
    for dataset in datasets:
        links.append(
            f'<a class="toc-link" href="#section-{dataset["key"]}">'
            f'{html.escape(dataset["label"])}'
            f'<span class="section-counter">{dataset["stats"]["total"]}</span>'
            f'</a>'
        )
    return (
        '<nav class="toc">'
        '<h3>Navigation rapide</h3>'
        '<div class="toc-links">'
        + ''.join(links)
        + '</div>'
        '</nav>'
    )


def filter_bar_html(total: int) -> str:
    mode_checks = []
    for mode in MODES:
        mode_checks.append(
            f'<label style="color:{MODE_COLORS_SOLID[mode]};font-weight:600;">'
            f'<input type="checkbox" class="mode-filter" value="{html.escape(mode, quote=True)}" checked> {html.escape(mode)}'
            f'</label>'
        )

    corpus_checks = []
    for dataset in DATASETS:
        corpus_checks.append(
            f'<label class="corpus-filter-label">'
            f'<input type="checkbox" class="corpus-filter" value="{dataset["key"]}" checked> {html.escape(dataset["label"])}'
            f'</label>'
        )

    return (
        '<div id="filter-bar">'
        '<div class="filter-group"><strong>Corpus</strong>' + "".join(corpus_checks) + '</div>'
        '<div class="filter-group"><strong>Modes</strong>' + "".join(mode_checks) + '</div>'
        '<div class="filter-group filter-group-tools">'
        '<button id="toggle-names" class="toggle-btn" title="Masquer/afficher les noms">Noms</button>'
        '<button id="toggle-roles" class="toggle-btn" title="Masquer/afficher les rôles">Rôles</button>'
        f'<input type="text" id="search-box" placeholder="Rechercher dans les textes…">'
        f'<span class="filter-counter">Affichés: <span id="shown-count">{total}</span> / {total}</span>'
        '</div>'
        '</div>'
    )


HTML_HEADER = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<style>
  :root {{
    --border: #dfdfdf;
    --muted: #707070;
    --bg-soft: #f7f7f8;
    --accent-soft: #f0f4ff;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 12px;
    line-height: 1.35;
    margin: 24px;
    color: #222;
    background: #fff;
  }}
  h1 {{ font-size: 24px; margin: 0 0 6px; }}
  h2 {{ font-size: 18px; margin: 0; }}
  h3 {{ font-size: 13px; margin: 0 0 8px; }}
  p.subtitle {{ margin: 0 0 18px; color: var(--muted); max-width: 1100px; }}
  .overview-grid, .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
  }}
  .overview-grid {{ margin-bottom: 18px; }}
  .stat-box, .overview-card, .dataset-section {{
    border: 1px solid var(--border);
    border-radius: 10px;
    background: #fff;
  }}
  .overview-card, .stat-box {{ padding: 14px 16px; }}
  .overview-card strong {{ display: block; font-size: 22px; margin-top: 4px; }}
  .toc {{
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--bg-soft);
    padding: 12px 14px;
    margin: 10px 0 14px;
  }}
  .toc h3 {{ margin-bottom: 10px; }}
  .toc-links {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .toc-link {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 1px solid #cfd6e6;
    border-radius: 999px;
    background: #fff;
    color: #28457d;
    text-decoration: none;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 600;
  }}
  .toc-link:hover {{ background: #eef3ff; }}
  .dataset-section {{ margin-top: 20px; overflow: hidden; scroll-margin-top: 96px; }}
  .dataset-header {{
    padding: 14px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-soft);
  }}
  .dataset-header-top {{
    display: flex;
    gap: 12px;
    justify-content: space-between;
    align-items: baseline;
    flex-wrap: wrap;
    margin-bottom: 8px;
  }}
  .dataset-meta {{ color: var(--muted); font-size: 11px; }}
  .section-body {{ padding: 14px 16px 18px; }}
  .legend {{
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    margin: 14px 0 12px;
    font-size: 11px;
    align-items: center;
  }}
  .legend-item {{ display: inline-flex; align-items: center; gap: 5px; }}
  .legend-swatch {{ width: 14px; height: 14px; border-radius: 3px; display: inline-block; }}
  #filter-bar {{
    position: sticky;
    top: 0;
    z-index: 5;
    background: rgba(255, 255, 255, 0.96);
    backdrop-filter: blur(4px);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px 14px;
    margin: 14px 0 18px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }}
  .filter-group {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
  .filter-group label {{ font-size: 11px; cursor: pointer; }}
  .corpus-filter-label {{ color: #333; font-weight: 600; }}
  .filter-group-tools {{ justify-content: space-between; }}
  .filter-group-tools input {{ margin-left: auto; }}
  #search-box {{ font-size: 11px; padding: 5px 8px; width: 280px; max-width: 100%; }}
  .toggle-btn {{
    font-size: 11px;
    padding: 4px 10px;
    border: 1px solid #b9b9b9;
    border-radius: 6px;
    cursor: pointer;
    background: #fff;
    color: #444;
  }}
  .toggle-btn.active {{ background: #ececec; border-color: #999; }}
  .filter-counter {{ font-size: 11px; color: var(--muted); }}
  .bar-row {{ display: flex; align-items: center; gap: 6px; margin: 2px 0; font-size: 11px; }}
  .bar-label {{ width: 110px; text-align: right; color: #444; }}
  .bar {{ height: 12px; border-radius: 3px; min-width: 2px; }}
  .empty-note {{ color: var(--muted); font-style: italic; }}
  .text-list {{ margin-top: 14px; }}
  .text-row {{
    padding: 8px 0;
    border-bottom: 1px solid #ececec;
  }}
  .text-row:last-child {{ border-bottom: 0; }}
  .text-head {{
    display: flex;
    gap: 8px;
    align-items: baseline;
    flex-wrap: wrap;
    margin-bottom: 3px;
  }}
  .text-idx {{ color: #999; font-size: 10px; min-width: 34px; }}
  .corpus-badge {{
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    background: var(--accent-soft);
    color: #28457d;
    padding: 2px 7px;
    border-radius: 999px;
  }}
  .char-name {{ font-size: 11px; font-weight: 700; }}
  .char-role {{ color: var(--muted); font-size: 10px; }}
  .text-content {{ font-size: 12px; }}
  .hl {{ border-radius: 3px; padding: 0 1px; }}
  .meta {{ color: var(--muted); font-size: 10px; margin-left: 6px; }}
  .hide-names .char-name {{ display: none; }}
  .hide-roles .char-role {{ display: none; }}
  .section-counter {{ font-size: 11px; color: var(--muted); }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="subtitle">{subtitle}</p>
"""

HTML_FOOTER = """<script>
function applyFilters() {
  const activeModes = Array.from(document.querySelectorAll('.mode-filter:checked')).map(cb => cb.value);
  const activeCorpora = Array.from(document.querySelectorAll('.corpus-filter:checked')).map(cb => cb.value);
  const search = (document.getElementById('search-box')?.value || '').toLowerCase();

  let shown = 0;
  document.querySelectorAll('.dataset-section').forEach(section => {
    let sectionShown = 0;
    section.querySelectorAll('.text-row').forEach(row => {
      const rowModes = (row.dataset.modes || '').split(',').filter(Boolean);
      const rowCorpus = row.dataset.corpus || '';
      const modeOk = activeModes.length === 0 || activeModes.some(mode => rowModes.includes(mode));
      const corpusOk = activeCorpora.length === 0 || activeCorpora.includes(rowCorpus);
      const textOk = !search || row.textContent.toLowerCase().includes(search);
      const visible = modeOk && corpusOk && textOk;

      row.style.display = visible ? '' : 'none';
      if (visible) {
        shown += 1;
        sectionShown += 1;
      }
    });

    section.style.display = sectionShown ? '' : 'none';
    const counter = section.querySelector('.dataset-shown-count');
    if (counter) counter.textContent = sectionShown;
  });

  const globalCounter = document.getElementById('shown-count');
  if (globalCounter) globalCounter.textContent = shown;
}

document.querySelectorAll('.mode-filter, .corpus-filter').forEach(cb => cb.addEventListener('change', applyFilters));
document.getElementById('search-box')?.addEventListener('input', applyFilters);
document.getElementById('toggle-names')?.addEventListener('click', function() {
  document.body.classList.toggle('hide-names');
  this.classList.toggle('active');
});
document.getElementById('toggle-roles')?.addEventListener('click', function() {
  document.body.classList.toggle('hide-roles');
  this.classList.toggle('active');
});
applyFilters();
</script>
</body>
</html>
"""


def render_record_row(dataset: dict, row: dict, index: int) -> str:
    text = str(row.get("text") or row.get("TEXT") or "")
    highlighted = highlight_text_with_spans(text, row.get("spans_json"))
    active_modes = get_active_modes(row)
    active_emotions = get_active_emotions(row)
    name = html.escape(str(row.get("NAME") or ""))
    role = html.escape(str(row.get("ROLE") or ""))
    emotion_text = html.escape(", ".join(active_emotions))

    meta_parts = [f'<span class="corpus-badge">{html.escape(dataset["label"])} </span>']
    if name:
        meta_parts.append(f'<span class="char-name">{name}</span>')
    if role:
        meta_parts.append(f'<span class="char-role">[{role}]</span>')

    return (
        f'<div class="text-row" data-corpus="{dataset["key"]}" data-modes="{html.escape(",".join(active_modes), quote=True)}">'
        f'<div class="text-head">'
        f'<span class="text-idx">{index}</span>'
        f'{" ".join(meta_parts)}'
        f'<span class="meta">[{emotion_text}]</span>'
        f'</div>'
        f'<div class="text-content">{highlighted}</div>'
        f'</div>'
    )


def render_dataset_section(dataset: dict) -> str:
    stats = dataset["stats"]
    parts = [
        f'<section class="dataset-section" id="section-{dataset["key"]}">',
        '<div class="dataset-header">',
        '<div class="dataset-header-top">',
        f'<h2>{html.escape(dataset["label"])} </h2>',
        (
            f'<div class="section-counter">Affichés: '
            f'<span class="dataset-shown-count">{stats["total"]}</span> / {stats["total"]}</div>'
        ),
        '</div>',
        f'<div class="dataset-meta">{stats["total"]} textes avec au moins une émotion annotée</div>',
        '</div>',
        '<div class="section-body">',
        '<div class="stats-grid">',
        '<div class="stat-box"><h3>Distribution des modes</h3>',
        bar_chart_html(stats["mode_counts"], MODE_COLORS_SOLID),
        '</div>',
        '<div class="stat-box"><h3>Distribution des émotions</h3>',
        bar_chart_html(stats["emo_counts"]),
        '</div>',
        '</div>',
        '<div class="text-list">',
    ]

    for index, record in enumerate(dataset["records"], start=1):
        parts.append(render_record_row(dataset, record, index))

    parts.extend(['</div>', '</div>', '</section>'])
    return "\n".join(parts)


def generate_combined_html(datasets: list[dict], out_path: Path) -> None:
    all_records = [record for dataset in datasets for record in dataset["records"]]
    overall_stats = compute_stats(all_records)

    parts = [
        HTML_HEADER.format(
            title="Visualisation unifiée des annotations",
            subtitle=(
                "Un seul fichier HTML regroupant les 4 corpus annotés "
                "(Homophobie, Obésité, Racisme, Religion)."
            ),
        ),
        '<div class="overview-grid">',
        '<div class="overview-card"><span>Textes annotés</span>'
        f'<strong>{overall_stats["total"]}</strong></div>',
        '<div class="overview-card"><span>Corpus inclus</span>'
        f'<strong>{len(datasets)}</strong></div>',
        '<div class="overview-card"><span>Fichier de sortie</span>'
        f'<strong>{html.escape(out_path.name)}</strong></div>',
        '</div>',
        render_toc(datasets),
        '<div class="stats-grid">',
        '<div class="stat-box"><h3>Distribution globale des modes</h3>',
        bar_chart_html(overall_stats["mode_counts"], MODE_COLORS_SOLID),
        '</div>',
        '<div class="stat-box"><h3>Distribution globale des émotions</h3>',
        bar_chart_html(overall_stats["emo_counts"]),
        '</div>',
        '</div>',
        legend_html(),
        filter_bar_html(overall_stats["total"]),
    ]

    for dataset in datasets:
        parts.append(render_dataset_section(dataset))

    parts.append(HTML_FOOTER)
    out_path.write_text("\n".join(parts), encoding="utf-8")


def load_dataset(base_dir: Path, spec: dict) -> dict:
    path = base_dir / spec["path"]
    headers, rows = read_xlsx(path)
    records = rows_to_dicts(headers, rows)
    filtered_records = [row for row in records if as_int(row.get("Emo")) == 1]
    return {
        "key": spec["key"],
        "label": spec["label"],
        "path": path,
        "records": filtered_records,
        "stats": compute_stats(filtered_records),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one HTML visualization file for the 4 annotated corpora.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/viz_all_corpora.html"),
        help="Output HTML path, relative to /home/gwen/Annotations_v1 unless absolute.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_dir = Path("/home/gwen/Annotations_v1")
    output_path = args.output if args.output.is_absolute() else base_dir / args.output

    datasets = []
    missing_files = []
    for spec in DATASETS:
        path = base_dir / spec["path"]
        if path.exists():
            print(f"Processing {spec['label']}…")
            datasets.append(load_dataset(base_dir, spec))
        else:
            missing_files.append(path)

    if missing_files:
        missing = "\n".join(f"- {path}" for path in missing_files)
        raise FileNotFoundError(f"Missing input files:\n{missing}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    generate_combined_html(datasets, output_path)

    total_records = sum(dataset["stats"]["total"] for dataset in datasets)
    print(f"Generated {output_path} ({total_records} texts across {len(datasets)} corpora).")


if __name__ == "__main__":
    main()
