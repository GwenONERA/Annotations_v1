#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Génère un fichier HTML unique pour les 4 corpus XLSX avec la même structure UI
que /home/gwen/ExpressionEmotionnelle/scripts/html_annotations.py.
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
MODES = list(MODE_COLORS.keys())
EMOTION_LABELS = [
    "Colère", "Dégoût", "Joie", "Peur", "Surprise", "Tristesse",
    "Admiration", "Culpabilité", "Embarras", "Fierté", "Jalousie", "Autre",
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
    {"key": "homophobie", "label": "Homophobie", "path": "outputs/homophobie_annotations_gold_flat_updated.xlsx"},
    {"key": "obesite", "label": "Obésité", "path": "outputs/obésité_annotations_gold_flat_updated.xlsx"},
    {"key": "racisme", "label": "Racisme", "path": "outputs/racisme_annotations_gold_flat_updated.xlsx"},
    {"key": "religion", "label": "Religion", "path": "outputs/religion_annotations_gold_flat_updated.xlsx"},
]

HTML_HEADER = """\
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<style>
  body {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 13.5px; line-height: 1.5; margin: 20px; color: #222; background: #fafafa; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  .top-controls {{ margin: 16px 0 24px; display: flex; gap: 12px; flex-wrap: wrap; }}
  .btn {{ padding: 8px 14px; border: 1px solid #ccc; background: #fff; cursor: pointer; border-radius: 4px; font-size: 13px; font-weight: 500; transition: 0.2s; }}
  .btn:hover {{ background: #f0f0f0; }}
  .btn.active {{ background: #d0e0ff; border-color: #80a0e0; }}
  #stats-section {{ display: none; }}
  #stats-section.visible {{ display: block; }}
  .stats-grid {{ display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 20px; }}
  .stat-box {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; padding: 14px 20px; min-width: 250px; flex: 1; }}
  .stat-box h3 {{ margin: 0 0 12px; font-size: 14px; color: #444; }}
  .bar-row {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 12px; }}
  .bar-label {{ width: 110px; text-align: right; font-weight: 500; color: #555; }}
  .bar {{ height: 12px; border-radius: 2px; min-width: 2px; }}
  .legend {{ display: flex; gap: 16px; margin: 16px 0; font-size: 13px; align-items: center; flex-wrap: wrap; }}
  .legend-item {{ display: inline-flex; align-items: center; gap: 6px; font-weight: 500; }}
  .legend-swatch {{ display: inline-block; width: 16px; height: 16px; border-radius: 4px; }}
  #filter-container {{ background: #fff; border: 1px solid #bce8f1; padding: 16px 20px; border-radius: 6px; margin: 16px 0; display: flex; flex-direction: column; gap: 12px; }}
  .filter-row {{ display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }}
  .filter-row strong {{ font-size: 13px; min-width: 80px; color: #333; }}
  .filter-row label {{ font-size: 13px; cursor: pointer; display: flex; align-items: center; gap: 4px; user-select: none; }}
  .search-row {{ display: flex; justify-content: space-between; align-items: center; margin-top: 6px; border-top: 1px solid #eee; padding-top: 12px; }}
  #search-box {{ font-size: 13px; padding: 6px 12px; width: 350px; border: 1px solid #ccc; border-radius: 4px; }}
  .corpus-section {{ margin-bottom: 20px; }}
  .section-meta {{ font-size: 13px; color: #666; margin: -4px 0 12px; }}
  .doc-container {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 12px; padding: 12px 16px; }}
  .doc-header {{ margin-bottom: 8px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .doc-corpus-badge {{ display: none; background: #e0e0e0; color: #333; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
  body.show-corpus .doc-corpus-badge {{ display: inline-block; }}
  .doc-meta {{ background: #eef5ff; border: 1px solid #cce0ff; padding: 3px 8px; border-radius: 4px; color: #0044aa; font-size: 12px; font-weight: 600; }}
  .hl {{ border-radius: 2px; padding: 2px 0; }}
  .doc-text {{ white-space: pre-wrap; color: #111; line-height: 1.6; font-size: 14px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p style="font-size:13px;color:#666;">{subtitle}</p>
<div class="top-controls">
  <button id="btn-toggle-stats" class="btn">Afficher les statistiques</button>
  <button id="btn-toggle-corpus" class="btn">Afficher les noms de corpus</button>
</div>
"""

HTML_FOOTER = """\
<script>
document.getElementById('btn-toggle-stats').addEventListener('click', function() {
  var sec = document.getElementById('stats-section');
  sec.classList.toggle('visible');
  this.classList.toggle('active');
  this.textContent = sec.classList.contains('visible') ? "Masquer les statistiques" : "Afficher les statistiques";
});

document.getElementById('btn-toggle-corpus').addEventListener('click', function() {
  document.body.classList.toggle('show-corpus');
  this.classList.toggle('active');
  this.textContent = document.body.classList.contains('show-corpus') ? "Masquer les noms de corpus" : "Afficher les noms de corpus";
});

function applyFilters() {
  var modeChecks = document.querySelectorAll('.mode-filter');
  var activeModes = [];
  modeChecks.forEach(function(cb) { if(cb.checked) activeModes.push(cb.value); });

  var emoChecks = document.querySelectorAll('.emo-filter');
  var activeEmos = [];
  emoChecks.forEach(function(cb) { if(cb.checked) activeEmos.push(cb.value); });

  var corpusChecks = document.querySelectorAll('.corpus-filter');
  var activeCorpora = [];
  corpusChecks.forEach(function(cb) { if(cb.checked) activeCorpora.push(cb.value); });

  var search = (document.getElementById('search-box') || {}).value || '';
  search = search.toLowerCase();

  var docs = document.querySelectorAll('.doc-container');
  var shown = 0;

  docs.forEach(function(doc) {
    var modes = (doc.dataset.modes || '').split(',').filter(Boolean);
    var emos = (doc.dataset.emos || '').split(',').filter(Boolean);
    var corpus = doc.dataset.corpus || '';

    var modeOk = activeModes.length === 0 || modes.some(function(m){ return activeModes.indexOf(m) >= 0; });
    var emoOk = activeEmos.length === 0 || emos.some(function(e){ return activeEmos.indexOf(e) >= 0; });
    var corpusOk = activeCorpora.length === 0 || activeCorpora.indexOf(corpus) >= 0;
    var textOk = !search || doc.textContent.toLowerCase().indexOf(search) >= 0;

    if (modeOk && emoOk && corpusOk && textOk) {
      doc.style.display = '';
      shown++;
    } else {
      doc.style.display = 'none';
    }
  });

  document.querySelectorAll('.corpus-section').forEach(function(section) {
    var key = section.dataset.corpus || '';
    var corpusVisible = activeCorpora.length === 0 || activeCorpora.indexOf(key) >= 0;
    var visibleDocs = section.querySelectorAll('.doc-container:not([style*="display: none"])').length;
    section.style.display = (corpusVisible && visibleDocs > 0) ? '' : 'none';
    var counter = section.querySelector('.section-shown-count');
    if (counter) counter.textContent = visibleDocs;
  });

  document.getElementById('shown-count').textContent = shown;
}

document.querySelectorAll('.mode-filter, .emo-filter, .corpus-filter').forEach(function(cb){ cb.addEventListener('change', applyFilters); });
var sb = document.getElementById('search-box');
if(sb) sb.addEventListener('input', applyFilters);
applyFilters();
</script>
</body>
</html>
"""


def normalise_record(row: dict) -> dict:
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

    intervals = []
    text_lower = text.lower()
    for span in spans:
        span_text = (span or {}).get("span_text", "")
        mode = (span or {}).get("mode", "")
        if not span_text or mode not in MODE_COLORS:
            continue
        idx = text_lower.find(str(span_text).lower())
        if idx >= 0:
            intervals.append((idx, idx + len(span_text), mode))

    if not intervals:
        return html.escape(text)

    char_modes = [set() for _ in range(len(text))]
    for start, end, mode in intervals:
        for pos in range(start, min(end, len(text))):
            char_modes[pos].add(mode)

    parts = []
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
            border = ""
            if len(sorted_modes) > 1:
                border = f"border-bottom:2px solid {MODE_COLORS_SOLID[sorted_modes[1]]};"
            title = html.escape(" + ".join(sorted_modes), quote=True)
            parts.append(f'<span class="hl" style="background:{bg};{border}" title="{title}">{chunk}</span>')
        else:
            parts.append(chunk)
        i = j
    return "".join(parts)


def bar_chart_html(counts: dict, color_map: dict | None = None, max_width: int = 220) -> str:
    if not counts:
        return ""
    max_val = max(counts.values(), default=0)
    if max_val == 0:
        return ""
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
            f'<span class="legend-item"><span class="legend-swatch" style="background:{color};"></span>{html.escape(mode)}</span>'
        )
    return '<div class="legend">' + ' '.join(items) + '</div>'



def filter_html(total: int) -> str:
    corpus_checks = []
    for dataset in DATASETS:
        corpus_checks.append(
            f'<label><input type="checkbox" class="corpus-filter" value="{dataset["key"]}" checked> {html.escape(dataset["label"])}</label>'
        )

    mode_checks = []
    for mode in MODES:
        mode_checks.append(
            f'<label style="color:{MODE_COLORS_SOLID[mode]};font-weight:600;">'
            f'<input type="checkbox" class="mode-filter" value="{html.escape(mode, quote=True)}" checked> {html.escape(mode)}</label>'
        )

    emo_checks = []
    for emo in EMOTION_LABELS:
        emo_checks.append(
            f'<label><input type="checkbox" class="emo-filter" value="{html.escape(emo, quote=True)}" checked> {html.escape(emo)}</label>'
        )

    return (
        f'<div id="filter-container">'
        f'  <div class="filter-row"><strong>Corpus :</strong> {"".join(corpus_checks)}</div>'
        f'  <div class="filter-row"><strong>Modes :</strong> {"".join(mode_checks)}</div>'
        f'  <div class="filter-row"><strong>Émotions :</strong> {"".join(emo_checks)}</div>'
        f'  <div class="search-row">'
        f'    <input type="text" id="search-box" placeholder="Rechercher un mot dans les textes…">'
        f'    <span style="font-size:13px;color:#666;font-weight:500;">Textes affichés : <span id="shown-count">{total}</span> / {total}</span>'
        f'  </div>'
        f'</div>'
    )


def render_record(dataset: dict, row: dict) -> str:
    text = str(row.get("text") or row.get("TEXT") or "")
    highlighted = highlight_text_with_spans(text, row.get("spans_json"))
    active_modes = get_active_modes(row)
    active_emotions = get_active_emotions(row)
    name = html.escape(str(row.get("NAME") or ""))
    role = html.escape(str(row.get("ROLE") or ""))

    meta_parts = []
    if name:
        meta_parts.append(name)
    if role:
        meta_parts.append(f'[{role}]')
    if active_emotions:
        meta_parts.append(', '.join(active_emotions))

    meta_html = ''.join(f'<span class="doc-meta">{html.escape(part)}</span>' for part in meta_parts)

    return (
        f'<div class="doc-container" data-corpus="{dataset["key"]}" data-modes="{html.escape(",".join(active_modes), quote=True)}" data-emos="{html.escape(",".join(active_emotions), quote=True)}">'
        '<div class="doc-header">'
        f'<span class="doc-corpus-badge">{html.escape(dataset["label"])} </span>'
        f'{meta_html}'
        '</div>'
        f'<div class="doc-text">{highlighted}</div>'
        '</div>'
    )


def render_dataset_section(dataset: dict) -> str:
    stats = dataset["stats"]
    parts = [
        f'<section class="corpus-section" data-corpus="{dataset["key"]}">',
        f'<div class="section-meta">Affichés: <span class="section-shown-count">{stats["total"]}</span> / {stats["total"]} textes avec au moins une émotion annotée</div>',
    ]
    for record in dataset["records"]:
        parts.append(render_record(dataset, record))
    parts.append('</section>')
    return '\n'.join(parts)


def generate_combined_html(datasets: list[dict], out_path: Path) -> None:
    all_records = [record for dataset in datasets for record in dataset["records"]]
    overall_stats = compute_stats(all_records)
    parts = [
        HTML_HEADER.format(
            title="Visualisation unifiée des annotations",
            subtitle="Un seul fichier HTML regroupant les 4 corpus annotés (Homophobie, Obésité, Racisme, Religion).",
        ),
        '<div id="stats-section">',
        '<div class="stats-grid">',
        '<div class="stat-box"><h3>Distribution globale des modes</h3>',
        bar_chart_html(overall_stats["mode_counts"], MODE_COLORS_SOLID),
        '</div>',
        '<div class="stat-box"><h3>Distribution globale des émotions</h3>',
        bar_chart_html(overall_stats["emo_counts"]),
        '</div>',
        '</div>',
        '</div>',
        legend_html(),
        filter_html(overall_stats["total"]),
    ]
    for dataset in datasets:
        parts.append(render_dataset_section(dataset))
    parts.append(HTML_FOOTER)
    out_path.write_text('\n'.join(parts), encoding='utf-8')


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
    parser.add_argument("--output", type=Path, default=Path("outputs/viz_all_corpora_unified_v2.html"), help="Output HTML path, relative to /home/gwen/Annotations_v1 unless absolute.")
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
