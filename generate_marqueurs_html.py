#!/usr/bin/env python3
"""
Analyse les fichiers JSONL dans outputs/ et génère marqueurs_syntaxiques.html
avec les correspondances de mots-clés linguistiques dans les justifications SitEmo.
"""

import json
import os
import re
import html
from pathlib import Path
from collections import defaultdict

# ── Configuration des familles de phénomènes ──────────────────────────────────

PHENOMENES = {
    "Ponctuation": [
        "ponctuation", "point d'exclamation", "point d'interrogation",
        "points de suspension", "double ponctuation", "absence de ponctuation"
    ],
    "Typographie & majuscules": [
        "typographique", "majuscule", "capitalisation"
    ],
    "Orthographe expressive": [
        "orthographe", "faute", "coquille"
    ],
    "Abréviations & registre": [
        "abréviation", "argot", "argotique", "familier", "registre", "vulgaire", "SMS"
    ],
    "Répétition & étirement graphique": [
        "répétition", "étirement", "allongement", "redoublement"
    ],
    "Émoticônes & emojis": [
        "émoticône", "emoticone", "emoji"
    ],
    "Structures syntaxiques": [
        "syntaxe", "syntaxique", "ellipse", "averbale", "accumulation", "réduction"
    ],
    "Figures discursives": [
        "question rhétorique", "interjection", "impératif", "injonction"
    ],
    "Intensité formelle": [
        "intensificateur", "charge affective", "marque formelle"
    ],
    "Insultes & injures": [
        "insulte", "insultes", "injure", "injures"
    ],
    "Ironie & sarcasme": [
        "ironie", "ironique", "sarcasme", "sarcastique",
        "moquerie", "moquer", "moqueur", "raillerie", "railler",
        "dérision", "cynisme", "cynique", "parodie",
        "antiphrase", "second degré", "ton décalé"
    ],
    "Mépris & haine": [
        "mépris", "méprisant", "haine", "haineux",
        "dégoût", "aversion", "hostilité", "hostile",
        "dédain", "dédaigneux", "répugnance", "répulsion",
        "animosité", "ressentiment", "rancœur", "rancune",
        "dénigrement", "dénigrer", "déshumanisation", "déshumaniser",
        "diabolisation", "diaboliser", "rejet"
    ],
}

# ── Collecte des données ──────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
OUTPUTS_DIR = BASE_DIR / "outputs"


TARGET_RE = re.compile(
    r'TARGET:\s*\[.*?\]\s*\(role=[^)]*\)\s*\(time=[^)]*\)\s*"(.+)"\s*$',
    re.MULTILINE,
)

def extract_target_text(prompt: str) -> str:
    """Extract the full TARGET message text from the prompt field."""
    m = TARGET_RE.search(prompt)
    return m.group(1) if m else ""

def collect_all_justifications():
    """Parse all JSONL files and extract justifications with metadata."""
    results = []
    for folder in OUTPUTS_DIR.iterdir():
        if not folder.is_dir():
            continue
        for jsonl_file in folder.glob("*.jsonl"):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    parsed = row.get("parsed_json")
                    if not parsed:
                        continue
                    # Extract full original message from prompt
                    prompt = row.get("prompt", "")
                    texte_original = extract_target_text(prompt)
                    units = parsed.get("sitemo_units", [])
                    idx = row.get("idx", "")
                    row_id = row.get("row_id", "")
                    for unit in units:
                        justification = unit.get("justification", "")
                        if not justification:
                            continue
                        results.append({
                            "fichier": jsonl_file.name,
                            "texte_original": texte_original,
                            "span_text": unit.get("span_text", ""),
                            "mode": unit.get("mode", ""),
                            "categorie": unit.get("categorie", ""),
                            "idx": idx,
                            "row_id": row_id,
                            "justification": justification,
                        })
    return results

# ── Recherche par mots-clés ───────────────────────────────────────────────────

def search_keywords(all_justifications):
    """
    Pour chaque justification, cherche les mots-clés (case-insensitive, partiel).
    Retourne un dict: famille -> mot_clé -> [list of matches avec metadata]
    """
    matches = defaultdict(lambda: defaultdict(list))
    total_matches = 0

    for entry in all_justifications:
        justif_lower = entry["justification"].lower()
        for famille, keywords in PHENOMENES.items():
            for kw in keywords:
                if kw.lower() in justif_lower:
                    matches[famille][kw].append(entry)
                    total_matches += 1

    return matches, total_matches

# ── Analyse des chevauchements ─────────────────────────────────────────────────

def compute_overlaps(all_justifications):
    """
    Calcule les chevauchements entre familles.
    Une entrée (justification) est identifiée par son index dans la liste.
    Retourne :
      - entry_families : dict index -> set de familles matchées
      - multi_family_entries : liste de (entry, set de familles) pour les entrées dans ≥2 familles
      - pairwise_counts : dict (fam_a, fam_b) -> nombre d'entrées en commun (triangulaire sup.)
    """
    # Pour chaque entrée, trouver les familles qui matchent
    entry_families = {}
    for i, entry in enumerate(all_justifications):
        justif_lower = entry["justification"].lower()
        fams = set()
        for famille, keywords in PHENOMENES.items():
            for kw in keywords:
                if kw.lower() in justif_lower:
                    fams.add(famille)
                    break  # une seule correspondance suffit pour la famille
        if fams:
            entry_families[i] = fams

    # Entrées dans ≥ 2 familles
    multi_family_entries = []
    for i, fams in entry_families.items():
        if len(fams) >= 2:
            multi_family_entries.append((all_justifications[i], fams))

    # Compter les intersections par paire de familles
    from itertools import combinations
    famille_names = list(PHENOMENES.keys())
    pairwise_counts = {}
    for fa, fb in combinations(famille_names, 2):
        count = sum(1 for fams in entry_families.values() if fa in fams and fb in fams)
        if count > 0:
            pairwise_counts[(fa, fb)] = count

    return entry_families, multi_family_entries, pairwise_counts

# ── Surlignage ────────────────────────────────────────────────────────────────

def highlight_keyword_in_text(text: str, keyword: str) -> str:
    """Surligne toutes les occurrences (case-insensitive) du mot-clé en jaune."""
    escaped_text = html.escape(text)
    escaped_kw = html.escape(keyword)
    pattern = re.compile(re.escape(escaped_kw), re.IGNORECASE)
    return pattern.sub(
        lambda m: f'<mark style="background:#ffe066;padding:1px 3px;border-radius:3px">{m.group()}</mark>',
        escaped_text,
    )

# ── Génération HTML ───────────────────────────────────────────────────────────

def _build_overlap_section(multi_family_entries, pairwise_counts):
    """Construit la section HTML des chevauchements entre familles."""

    # ── Tableau des intersections par paire (triées par taille décroissante) ──
    sorted_pairs = sorted(pairwise_counts.items(), key=lambda x: x[1], reverse=True)
    pair_rows = []
    for (fa, fb), count in sorted_pairs:
        pair_rows.append(
            f"<tr><td>{html.escape(fa)}</td><td>{html.escape(fb)}</td>"
            f"<td><strong>{count}</strong></td></tr>"
        )
    pair_table = ""
    if pair_rows:
        pair_table = f"""<h3>Intersections par paire de familles</h3>
<p class="overlap-note">Nombre d'entrées (justifications) partagées entre deux familles. Trié par taille décroissante.</p>
<table class="data-table overlap-table">
  <thead><tr><th>Famille A</th><th>Famille B</th><th>Entrées communes</th></tr></thead>
  <tbody>{"".join(pair_rows)}</tbody>
</table>"""
    else:
        pair_table = "<p class='empty-note'>Aucune intersection entre familles.</p>"

    # ── Tableau des entrées multi-familles ──
    # Trier par nombre de familles décroissant
    sorted_entries = sorted(multi_family_entries, key=lambda x: len(x[1]), reverse=True)
    entry_rows = []
    for entry, fams in sorted_entries[:200]:  # limiter à 200 pour la lisibilité
        fams_sorted = sorted(fams)
        fams_html = ", ".join(
            f'<span class="kw-badge">{html.escape(f)}</span>' for f in fams_sorted
        )
        orig = html.escape(entry.get("texte_original", ""))
        span_text = entry.get("span_text", "")
        if span_text:
            span_esc = re.escape(html.escape(span_text))
            orig = re.sub(
                f'({span_esc})',
                r'<span class="span-hl">\1</span>',
                orig, count=1, flags=re.IGNORECASE,
            )
        entry_rows.append(f"""<tr>
  <td><strong>{len(fams)}</strong></td>
  <td>{fams_html}</td>
  <td>{html.escape(entry.get('mode', ''))}</td>
  <td class="text-cell">{orig}</td>
  <td class="justif-cell">{html.escape(entry.get('justification', ''))}</td>
</tr>""")

    entry_table = ""
    if entry_rows:
        truncated_note = ""
        if len(sorted_entries) > 200:
            truncated_note = f"<p class='overlap-note'>(Affichage limité à 200 / {len(sorted_entries)} entrées)</p>"
        entry_table = f"""<h3>Entrées présentes dans plusieurs familles</h3>
<p class="overlap-note">{len(multi_family_entries)} justifications apparaissent dans au moins 2 familles.</p>
{truncated_note}
<table class="data-table overlap-table">
  <thead><tr>
    <th>Nb familles</th><th>Familles</th><th>Mode</th><th>Texte original</th><th>Justification</th>
  </tr></thead>
  <tbody>{"".join(entry_rows)}</tbody>
</table>"""
    else:
        entry_table = "<p class='empty-note'>Aucune entrée n'apparaît dans plusieurs familles.</p>"

    return f"""
<section id="chevauchements">
  <h2>Chevauchements entre familles <span class="section-count">({len(multi_family_entries)} entrées multi-familles)</span></h2>
  {pair_table}
  <br>
  {entry_table}
</section>
"""


def generate_html(all_justifications, matches, total_matches, multi_family_entries, pairwise_counts):
    famille_counts = {}
    for famille in PHENOMENES:
        count = sum(len(v) for v in matches.get(famille, {}).values())
        famille_counts[famille] = count

    # Build TOC
    toc_items = []
    for i, (famille, count) in enumerate(famille_counts.items(), 1):
        anchor = f"famille-{i}"
        toc_items.append(
            f'<li><a href="#{anchor}">{html.escape(famille)}</a> '
            f'<span class="badge">{count}</span></li>'
        )
    toc_html = "\n".join(toc_items)
    # Add overlap section to TOC
    toc_items.append(
        f'<li><a href="#chevauchements">Chevauchements entre familles</a> '
        f'<span class="badge">{len(multi_family_entries)}</span></li>'
    )
    toc_html = "\n".join(toc_items)
    sections_html = []
    for i, (famille, keywords) in enumerate(PHENOMENES.items(), 1):
        anchor = f"famille-{i}"
        fam_matches = matches.get(famille, {})
        fam_total = famille_counts[famille]

        # Keyword counts
        kw_counts_html = []
        for kw in keywords:
            c = len(fam_matches.get(kw, []))
            if c > 0:
                kw_counts_html.append(
                    f'<span class="kw-badge">{html.escape(kw)}: <strong>{c}</strong></span>'
                )
            else:
                kw_counts_html.append(
                    f'<span class="kw-badge kw-zero">{html.escape(kw)}: 0</span>'
                )

        # Rows
        rows_html = []
        for kw in keywords:
            for entry in fam_matches.get(kw, []):
                highlighted_justif = highlight_keyword_in_text(entry["justification"], kw)
                # Highlight span_text within the original text
                orig = html.escape(entry['texte_original'])
                span_esc = re.escape(html.escape(entry['span_text']))
                if span_esc:
                    orig = re.sub(
                        f'({span_esc})',
                        r'<span class="span-hl">\1</span>',
                        orig,
                        count=1,
                        flags=re.IGNORECASE,
                    )
                rows_html.append(f"""<tr>
  <td>{html.escape(kw)}</td>
  <td>{html.escape(entry['mode'])}</td>
  <td>{html.escape(entry['categorie'])}</td>
  <td class="text-cell">{orig}</td>
  <td class="justif-cell">{highlighted_justif}</td>
</tr>""")

        section = f"""
<section id="{anchor}">
  <h2>{html.escape(famille)} <span class="section-count">({fam_total} occurrences)</span></h2>
  <div class="kw-summary">{"  ".join(kw_counts_html)}</div>
  {"<p class='empty-note'>Aucune correspondance trouvée pour cette famille.</p>" if not rows_html else ""}
  {"" if not rows_html else f'''<table class="data-table">
    <thead>
      <tr>
        <th>Mot-clé</th>
        <th>Mode</th>
        <th>Catégorie émotion</th>
        <th>Texte original</th>
        <th>Justification</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>'''}
</section>
"""
        sections_html.append(section)

    # ── Section chevauchements ──
    overlap_section = _build_overlap_section(multi_family_entries, pairwise_counts)
    sections_html.append(overlap_section)

    total_justifications = len(all_justifications)

    page = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Marqueurs syntaxiques — Analyse des justifications SitEmo</title>
<style>
  :root {{
    --primary: #2c3e50;
    --accent: #3498db;
    --bg: #f8f9fa;
    --card-bg: #ffffff;
    --border: #dee2e6;
    --text: #212529;
    --text-muted: #6c757d;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 2rem;
    max-width: 1600px;
    margin: 0 auto;
  }}
  h1 {{
    color: var(--primary);
    font-size: 1.8rem;
    margin-bottom: 0.5rem;
  }}
  .global-stats {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem 1.5rem;
    margin-bottom: 1.5rem;
    display: flex;
    gap: 2rem;
    flex-wrap: wrap;
    align-items: center;
  }}
  .global-stats .stat {{
    font-size: 1.1rem;
  }}
  .global-stats .stat strong {{
    color: var(--accent);
    font-size: 1.3rem;
  }}
  .filter-box {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem 1.5rem;
    margin-bottom: 1.5rem;
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    align-items: center;
  }}
  .filter-box label {{
    font-weight: 600;
    color: var(--primary);
  }}
  .filter-box select, .filter-box input[type="text"] {{
    padding: 0.4rem 0.8rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 0.95rem;
  }}
  .filter-box input[type="text"] {{
    min-width: 250px;
  }}
  nav.toc {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem 1.5rem;
    margin-bottom: 2rem;
  }}
  nav.toc h2 {{
    font-size: 1.2rem;
    color: var(--primary);
    margin-bottom: 0.5rem;
  }}
  nav.toc ol {{
    list-style: decimal;
    padding-left: 1.5rem;
  }}
  nav.toc li {{
    margin-bottom: 0.3rem;
  }}
  nav.toc a {{
    color: var(--accent);
    text-decoration: none;
    font-weight: 500;
  }}
  nav.toc a:hover {{
    text-decoration: underline;
  }}
  .badge {{
    background: var(--accent);
    color: white;
    font-size: 0.8rem;
    padding: 2px 8px;
    border-radius: 12px;
    font-weight: 600;
  }}
  section {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
  }}
  section h2 {{
    color: var(--primary);
    font-size: 1.3rem;
    margin-bottom: 0.8rem;
    border-bottom: 2px solid var(--accent);
    padding-bottom: 0.4rem;
  }}
  .section-count {{
    color: var(--text-muted);
    font-size: 0.95rem;
    font-weight: 400;
  }}
  .kw-summary {{
    margin-bottom: 1rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }}
  .kw-badge {{
    background: #e8f4fd;
    border: 1px solid #b8daf5;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.85rem;
    white-space: nowrap;
  }}
  .kw-badge.kw-zero {{
    background: #f5f5f5;
    border-color: #ddd;
    color: #999;
  }}
  .empty-note {{
    color: var(--text-muted);
    font-style: italic;
  }}
  .data-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
    table-layout: auto;
  }}
  .data-table th {{
    background: var(--primary);
    color: white;
    padding: 0.6rem 0.8rem;
    text-align: left;
    position: sticky;
    top: 0;
    z-index: 1;
    white-space: nowrap;
  }}
  .data-table td {{
    padding: 0.5rem 0.8rem;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}
  .data-table tbody tr:nth-child(even) {{
    background: #f8f9fa;
  }}
  .data-table tbody tr:hover {{
    background: #e2edf7;
  }}
  .text-cell {{
    max-width: 400px;
    word-break: break-word;
  }}
  .text-cell .span-hl {{
    background: #d4edda;
    border: 1px solid #a3d9a5;
    border-radius: 3px;
    padding: 0 2px;
  }}
  .justif-cell {{
    max-width: 450px;
    word-break: break-word;
  }}
  @media (max-width: 1000px) {{
    body {{ padding: 0.8rem; }}
    .data-table {{ font-size: 0.8rem; }}
    .data-table th, .data-table td {{ padding: 0.3rem 0.5rem; }}
  }}
</style>
</head>
<body>

<h1>Marqueurs syntaxiques — Analyse des justifications SitEmo</h1>

<div class="global-stats">
  <div class="stat">Justifications analysées : <strong>{total_justifications}</strong></div>
  <div class="stat">Correspondances trouvées : <strong>{total_matches}</strong></div>
  <div class="stat">Familles de phénomènes : <strong>{len(PHENOMENES)}</strong></div>
</div>

<div class="filter-box">
  <label for="filter-text">Recherche libre :</label>
  <input type="text" id="filter-text" placeholder="Filtrer par texte…" oninput="applyFilters()">
</div>

<nav class="toc">
  <h2>Sommaire</h2>
  <ol>
    {toc_html}
  </ol>
</nav>

{"".join(sections_html)}

<script>
function applyFilters() {{
  const text = document.getElementById('filter-text').value.toLowerCase();

  document.querySelectorAll('.data-table tbody tr').forEach(function(row) {{
    const rowText = row.textContent.toLowerCase();
    row.style.display = (!text || rowText.indexOf(text) !== -1) ? '' : 'none';
  }});
}}
</script>

</body>
</html>"""
    return page


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Collecte des justifications depuis outputs/...")
    all_justifications = collect_all_justifications()
    print(f"  → {len(all_justifications)} justifications extraites")

    print("Recherche des mots-clés par famille de phénomènes...")
    matches, total_matches = search_keywords(all_justifications)
    print(f"  → {total_matches} correspondances trouvées")

    for famille in PHENOMENES:
        fam_total = sum(len(v) for v in matches.get(famille, {}).values())
        if fam_total > 0:
            print(f"    {famille}: {fam_total}")

    print("Analyse des chevauchements entre familles...")
    entry_families, multi_family_entries, pairwise_counts = compute_overlaps(all_justifications)
    print(f"  → {len(multi_family_entries)} entrées dans ≥ 2 familles")
    if pairwise_counts:
        top_pairs = sorted(pairwise_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        for (fa, fb), count in top_pairs:
            print(f"    {fa} ∩ {fb}: {count}")

    print("Génération du fichier HTML...")
    html_content = generate_html(all_justifications, matches, total_matches,
                                 multi_family_entries, pairwise_counts)

    output_path = BASE_DIR / "marqueurs_syntaxiques.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Fichier généré : {output_path}")
