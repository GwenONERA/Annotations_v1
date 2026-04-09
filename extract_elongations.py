#!/usr/bin/env python3
"""
Extrait les allongements graphiques (étirements de lettres) dans les textes SMS
en comparant TEXT (brut) et full_transcription (corrigé) du fichier parquet.

Pipeline :
  1. Détection par alignement caractère/caractère (difflib.SequenceMatcher)
  2. Classification heuristique : expressif / probable_typo
  3. Filtrage par annotations LLM (JSONL dans outputs/) pour isoler les cas "sûrs"
  4. Push des cas ambigus vers Argilla pour supervision manuelle

Usage :
  python extract_elongations.py                    # détection seule
  python extract_elongations.py --push-argilla     # détection + push ambigus vers Argilla
"""

import argparse
import pandas as pd
import re
import json
import html as html_mod
from pathlib import Path
from difflib import SequenceMatcher
from collections import Counter, defaultdict

BASE_DIR = Path(__file__).parent
REPO_ROOT = BASE_DIR.parent
PARQUET_PATH = REPO_ROOT / "data" / "CyberBullyingExperiment.parquet"
OUTPUTS_DIR = REPO_ROOT / "outputs"


def find_elongations(text_raw: str, text_trans: str) -> list[dict]:
    """
    Compare raw SMS text vs its transcription to find letter elongations.
    
    Returns list of dicts with keys:
      - raw_word: the word in the raw text containing the elongation
      - char: the elongated character
      - total_repeated: how many times the char appears consecutively in raw
      - expected_count: how many times this char appears at this position in transcription
      - position: char position in raw text
    """
    if not text_raw or not text_trans:
        return []

    raw_lower = text_raw.lower()
    trans_lower = text_trans.lower()

    sm = SequenceMatcher(None, raw_lower, trans_lower)
    results = []
    seen_positions = set()

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'delete':
            deleted = raw_lower[i1:i2]
            # Check if deleted chars are all the same letter
            if len(deleted) >= 1 and len(set(deleted)) == 1:
                c = deleted[0]
                if c.isalpha():
                    # Verify adjacency: the char before or after in raw is the same
                    adjacent = False
                    if i1 > 0 and raw_lower[i1 - 1] == c:
                        adjacent = True
                    if i2 < len(raw_lower) and raw_lower[i2] == c:
                        adjacent = True
                    if not adjacent:
                        continue

                    # Find the full extent of the repeated char in raw
                    start = i1
                    while start > 0 and raw_lower[start - 1] == c:
                        start -= 1
                    end = i2
                    while end < len(raw_lower) and raw_lower[end] == c:
                        end += 1
                    total_in_raw = end - start

                    if start in seen_positions:
                        continue
                    seen_positions.add(start)

                    # How many of this char at this position in transcription?
                    # Find the corresponding position in transcription
                    # Count from the equal block before
                    expected = total_in_raw - len(deleted)

                    # Find word containing this position in raw
                    word_start = raw_lower.rfind(' ', 0, start) + 1
                    word_end = raw_lower.find(' ', end)
                    if word_end == -1:
                        word_end = len(raw_lower)
                    raw_word = text_raw[word_start:word_end]

                    # Find corresponding word in transcription
                    # Use the j1 position to find it
                    tw_start = trans_lower.rfind(' ', 0, j1) + 1
                    tw_end = trans_lower.find(' ', j1)
                    if tw_end == -1:
                        tw_end = len(trans_lower)
                    trans_word = text_trans[tw_start:tw_end]

                    results.append({
                        'raw_word': raw_word,
                        'trans_word': trans_word,
                        'char': c,
                        'total_repeated': total_in_raw,
                        'expected_count': expected,
                        'extra_chars': len(deleted),
                        'position': start,
                    })

        elif tag == 'replace':
            # Sometimes an elongation shows up as replace: e.g. "ooooh" → "oh"
            raw_seg = raw_lower[i1:i2]
            trans_seg = trans_lower[j1:j2]
            # Check if the raw segment is mostly one repeated char
            if len(raw_seg) >= 3:
                counter = Counter(raw_seg)
                most_common_char, most_common_count = counter.most_common(1)[0]
                if most_common_char.isalpha() and most_common_count >= len(raw_seg) * 0.6:
                    # Check if the transcription segment is shorter
                    trans_count = trans_seg.count(most_common_char)
                    if most_common_count > trans_count and most_common_count >= 3:
                        if i1 in seen_positions:
                            continue
                        seen_positions.add(i1)

                        word_start = raw_lower.rfind(' ', 0, i1) + 1
                        word_end = raw_lower.find(' ', i2)
                        if word_end == -1:
                            word_end = len(raw_lower)
                        raw_word = text_raw[word_start:word_end]

                        tw_start = trans_lower.rfind(' ', 0, j1) + 1
                        tw_end = trans_lower.find(' ', j2)
                        if tw_end == -1:
                            tw_end = len(trans_lower)
                        trans_word = text_trans[tw_start:tw_end]

                        results.append({
                            'raw_word': raw_word,
                            'trans_word': trans_word,
                            'char': most_common_char,
                            'total_repeated': most_common_count,
                            'expected_count': trans_count,
                            'extra_chars': most_common_count - trans_count,
                            'position': i1,
                        })

    return results


def classify_elongation(e: dict) -> str:
    """
    Classify an elongation as 'expressif' (intentional expressive stretching)
    or 'probable_typo' (likely a typo or misspelling, not expressive).
    
    Heuristics:
    - extra_chars >= 2 → almost certainly expressive
    - extra_chars == 1 AND total_repeated >= 3 → expressive (e.g. "ohhh" with 3 h's)
    - extra_chars == 1 AND total_repeated == 2 → likely typo (e.g. "salle"→"sale", "allors"→"alors")
    """
    if e['extra_chars'] >= 2:
        return 'expressif'
    if e['extra_chars'] == 1 and e['total_repeated'] >= 3:
        return 'expressif'
    return 'probable_typo'


def detect_all_elongations(df: pd.DataFrame) -> list[dict]:
    """Run elongation detection on every row of the DataFrame.

    Returns a list of elongation dicts enriched with row metadata
    (id, text_raw, full_transcription, name, role, classification).
    """
    all_elongations = []
    for _, row in df.iterrows():
        elongs = find_elongations(row['TEXT'], row['full_transcription'])
        for e in elongs:
            entry = {
                'id': row['ID'],
                'text_raw': row['TEXT'],
                'full_transcription': row['full_transcription'],
                'name': row['NAME'],
                'role': row['ROLE'],
                **e,
            }
            entry['classification'] = classify_elongation(entry)
            all_elongations.append(entry)
    return all_elongations


# ── LLM keyword extraction from JSONL outputs ─────────────────────────────────

TARGET_RE = re.compile(
    r'TARGET:\s*\[.*?\]\s*\(role=[^)]*\)\s*\(time=[^)]*\)\s*"(.+)"\s*$',
    re.MULTILINE,
)

ELONG_KEYWORDS = {"répétition", "étirement", "allongement", "redoublement"}
TYPO_KEYWORDS = {"faute", "orthographe", "coquille"}


def _extract_target_text(prompt: str) -> str:
    m = TARGET_RE.search(prompt)
    return m.group(1).strip() if m else ""


def build_llm_keyword_index() -> dict[str, dict]:
    """Parse all JSONL in outputs/ and build a text→keyword-flags mapping.

    Returns dict keyed by stripped target_text:
        {
          text: {
            "has_elong_kw": bool,
            "has_typo_kw": bool,
            "span_elong_words": set[str],   # span_text whose justif mentions elong kw
            "span_typo_words": set[str],     # span_text whose justif mentions typo kw
            "justifications": [str, ...],
          }
        }
    Multiple JSONL rows for the same text are merged (union of flags).
    """
    index: dict[str, dict] = {}

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
                    target_text = _extract_target_text(row.get("prompt", ""))
                    if not target_text:
                        continue

                    entry = index.setdefault(target_text, {
                        "has_elong_kw": False,
                        "has_typo_kw": False,
                        "span_elong_words": set(),
                        "span_typo_words": set(),
                        "justifications": [],
                    })

                    for unit in parsed.get("sitemo_units", []):
                        justif = unit.get("justification", "")
                        if not justif:
                            continue
                        justif_lower = justif.lower()
                        span_text = unit.get("span_text", "").lower().strip()

                        has_elong = any(kw in justif_lower for kw in ELONG_KEYWORDS)
                        has_typo = any(kw in justif_lower for kw in TYPO_KEYWORDS)

                        if has_elong:
                            entry["has_elong_kw"] = True
                            if span_text:
                                entry["span_elong_words"].add(span_text)
                        if has_typo:
                            entry["has_typo_kw"] = True
                            if span_text:
                                entry["span_typo_words"].add(span_text)

                        entry["justifications"].append(justif)

    return index


# ── Matching parquet texts → LLM index ─────────────────────────────────────────

def match_elongations_to_llm(
    all_elongations: list[dict],
    llm_index: dict[str, dict],
) -> list[dict]:
    """Enrich each elongation entry with LLM keyword flags and confidence verdict.

    Adds to each entry:
      - llm_has_elong_kw: bool | None  (None = no LLM coverage)
      - llm_has_typo_kw: bool | None
      - llm_span_match_elong: bool  (span-level: raw_word matches a span with elong kw)
      - llm_span_match_typo: bool
      - llm_justifications: list[str]
      - confidence: "sure_elongation" | "sure_typo" | "ambiguous"
      - ambiguity_reason: str | None
    """
    for entry in all_elongations:
        text_key = entry["text_raw"].strip()
        llm = llm_index.get(text_key)

        if llm is None:
            entry["llm_has_elong_kw"] = None
            entry["llm_has_typo_kw"] = None
            entry["llm_span_match_elong"] = False
            entry["llm_span_match_typo"] = False
            entry["llm_justifications"] = []
        else:
            entry["llm_has_elong_kw"] = llm["has_elong_kw"]
            entry["llm_has_typo_kw"] = llm["has_typo_kw"]

            raw_word_lower = entry["raw_word"].lower().strip()
            entry["llm_span_match_elong"] = any(
                raw_word_lower in sw or sw in raw_word_lower
                for sw in llm["span_elong_words"]
            )
            entry["llm_span_match_typo"] = any(
                raw_word_lower in sw or sw in raw_word_lower
                for sw in llm["span_typo_words"]
            )
            entry["llm_justifications"] = llm["justifications"]

        # ── Confidence assignment ──
        heuristic = entry["classification"]
        has_e = entry["llm_has_elong_kw"]
        has_t = entry["llm_has_typo_kw"]
        span_e = entry["llm_span_match_elong"]
        span_t = entry["llm_span_match_typo"]

        if has_e is None:
            # No LLM coverage for this text
            entry["confidence"] = "ambiguous"
            entry["ambiguity_reason"] = "no_llm_coverage"
        elif has_e and not has_t and heuristic == "expressif":
            entry["confidence"] = "sure_elongation"
            entry["ambiguity_reason"] = None
        elif not has_e and has_t and heuristic == "probable_typo":
            entry["confidence"] = "sure_typo"
            entry["ambiguity_reason"] = None
        elif span_e and heuristic == "expressif":
            # Span-level match is strong evidence even if text-level has both kw
            entry["confidence"] = "sure_elongation"
            entry["ambiguity_reason"] = None
        elif span_t and heuristic == "probable_typo":
            entry["confidence"] = "sure_typo"
            entry["ambiguity_reason"] = None
        elif has_e and has_t:
            entry["confidence"] = "ambiguous"
            entry["ambiguity_reason"] = "conflicting_llm_keywords"
        elif has_e and not has_t and heuristic == "probable_typo":
            entry["confidence"] = "ambiguous"
            entry["ambiguity_reason"] = "heuristic_vs_llm_conflict"
        elif not has_e and has_t and heuristic == "expressif":
            entry["confidence"] = "ambiguous"
            entry["ambiguity_reason"] = "heuristic_vs_llm_conflict"
        elif not has_e and not has_t:
            entry["confidence"] = "ambiguous"
            entry["ambiguity_reason"] = "no_llm_signal"
        else:
            entry["confidence"] = "ambiguous"
            entry["ambiguity_reason"] = "unclassified"

    return all_elongations


# ── Argilla push ───────────────────────────────────────────────────────────────

ARGILLA_API_URL = "https://allezallezallez-argilla.hf.space"
ARGILLA_API_KEY = (
    "QxYhMT4sZAL3NHBgOv5jhoxt-NDhcVn87rfzblrmnW6GC-Wj_kfDM_pcaFeTfLFhhqE"
    "TG2BZ4dKYvHFN8mAfONITR3O_UjftLwX4Vha9QlI"
)
ARGILLA_DATASET_NAME = "elongation_supervision"


def push_ambiguous_to_argilla(
    all_elongations: list[dict],
    proxy: str | None = None,
    force: bool = False,
):
    """Push only ambiguous elongation entries to Argilla for manual annotation."""
    import argilla as rg

    ambiguous = [e for e in all_elongations if e["confidence"] == "ambiguous"]
    if not ambiguous:
        print("Aucun cas ambigu à pousser vers Argilla.")
        return

    print(f"\nConnexion à Argilla ({ARGILLA_API_URL})...")
    connect_kwargs = {}
    if proxy:
        connect_kwargs["proxy"] = proxy
    client = rg.Argilla(
        api_url=ARGILLA_API_URL, api_key=ARGILLA_API_KEY,
        timeout=120, **connect_kwargs,
    )

    # Check for existing dataset
    existing = client.datasets(name=ARGILLA_DATASET_NAME)
    if existing is not None:
        if force:
            print(f"  Suppression du dataset existant '{ARGILLA_DATASET_NAME}'...")
            existing.delete()
        else:
            print(
                f"  Le dataset '{ARGILLA_DATASET_NAME}' existe déjà. "
                f"Utilisez --force pour le recréer."
            )
            return

    settings = rg.Settings(
        fields=[
            rg.TextField(name="texte_brut", title="Texte brut (SMS original)", use_markdown=False),
            rg.TextField(name="transcription", title="Transcription corrigée", use_markdown=False),
            rg.TextField(name="detail_elongation", title="Détail de l'élongation détectée", use_markdown=True),
            rg.TextField(name="contexte_llm", title="Justifications LLM (si disponibles)", use_markdown=True, required=False),
        ],
        questions=[
            rg.LabelQuestion(
                name="verdict",
                title="Ce phénomène est-il une élongation intentionnelle ou une faute de frappe ?",
                labels=["elongation", "typo"],
                required=True,
            ),
            rg.TextQuestion(
                name="notes",
                title="Notes (optionnel)",
                required=False,
            ),
        ],
        metadata=[
            rg.TermsMetadataProperty(name="parquet_id", title="ID parquet"),
            rg.TermsMetadataProperty(name="heuristic_class", title="Heuristique"),
            rg.TermsMetadataProperty(name="char", title="Caractère allongé"),
            rg.IntegerMetadataProperty(name="extra_chars", title="Caractères en excès"),
            rg.TermsMetadataProperty(name="ambiguity_reason", title="Raison d'ambiguïté"),
        ],
    )

    print(f"  Création du dataset '{ARGILLA_DATASET_NAME}'...")
    dataset = rg.Dataset(
        name=ARGILLA_DATASET_NAME,
        settings=settings,
        client=client,
    )
    dataset.create()

    # Build records
    records = []
    seen_ids = set()
    for entry in ambiguous:
        record_id = f"{entry['id']}_{entry['position']}"
        # Ensure uniqueness (same text can have multiple elongations at same position)
        if record_id in seen_ids:
            suffix = 1
            while f"{record_id}_{suffix}" in seen_ids:
                suffix += 1
            record_id = f"{record_id}_{suffix}"
        seen_ids.add(record_id)
        detail_md = (
            f"**Mot brut** : `{entry['raw_word']}` → **Transcrit** : `{entry['trans_word']}`\n\n"
            f"**Caractère** : `{entry['char']}` — "
            f"répété **{entry['total_repeated']}×** dans le brut, "
            f"**{entry['expected_count']}×** attendu "
            f"(+{entry['extra_chars']} en excès)\n\n"
            f"**Heuristique** : `{entry['classification']}`"
        )

        justifs = entry.get("llm_justifications", [])
        if justifs:
            # Show at most 10 justifications to keep it readable
            justif_md = "\n".join(f"- {j}" for j in justifs[:10])
            if len(justifs) > 10:
                justif_md += f"\n- … et {len(justifs) - 10} autres"
            contexte_llm = justif_md
        else:
            contexte_llm = "*Aucune annotation LLM disponible pour ce texte.*"

        record = rg.Record(
            id=record_id,
            fields={
                "texte_brut": entry["text_raw"],
                "transcription": entry["full_transcription"],
                "detail_elongation": detail_md,
                "contexte_llm": contexte_llm,
            },
            metadata={
                "parquet_id": str(entry["id"]),
                "heuristic_class": entry["classification"],
                "char": entry["char"],
                "extra_chars": int(entry["extra_chars"]),
                "ambiguity_reason": entry.get("ambiguity_reason", "unknown"),
            },
        )
        records.append(record)

    print(f"  Push de {len(records)} records ambigus...")
    dataset.records.log(records)
    print(f"  ✓ {len(records)} records poussés vers {ARGILLA_API_URL}")

    # Breakdown by ambiguity reason
    reason_counts = Counter(e["ambiguity_reason"] for e in ambiguous)
    print("\n  Répartition par raison d'ambiguïté :")
    for reason, count in reason_counts.most_common():
        print(f"    {reason}: {count}")


# ── Argilla export ─────────────────────────────────────────────────────────────

def export_from_argilla(proxy: str | None = None) -> list[dict]:
    """Download annotated records from Argilla and return them as dicts.

    Returns a list of dicts with keys:
      - record_id, verdict, notes
      - fields: texte_brut, transcription, detail_elongation, contexte_llm
      - metadata: parquet_id, heuristic_class, char, extra_chars, ambiguity_reason
      - status (submitted / pending / discarded / draft)
    """
    import argilla as rg

    print(f"\nConnexion à Argilla ({ARGILLA_API_URL})...")
    connect_kwargs = {}
    if proxy:
        connect_kwargs["proxy"] = proxy
    client = rg.Argilla(
        api_url=ARGILLA_API_URL, api_key=ARGILLA_API_KEY,
        timeout=120, **connect_kwargs,
    )

    dataset = client.datasets(name=ARGILLA_DATASET_NAME)
    if dataset is None:
        print(f"⚠ Dataset '{ARGILLA_DATASET_NAME}' non trouvé.")
        return []

    print(f"  Téléchargement des records depuis '{ARGILLA_DATASET_NAME}'...")
    exported = []
    for record in dataset.records(with_responses=True):
        entry = {
            "record_id": record.id,
            "texte_brut": record.fields.get("texte_brut", ""),
            "transcription": record.fields.get("transcription", ""),
            "detail_elongation": record.fields.get("detail_elongation", ""),
            "contexte_llm": record.fields.get("contexte_llm", ""),
            "verdict": None,
            "notes": None,
            "status": str(record.status) if hasattr(record, "status") else "unknown",
        }

        # Extract metadata
        meta = record.metadata or {}
        entry["parquet_id"] = meta.get("parquet_id", "")
        entry["heuristic_class"] = meta.get("heuristic_class", "")
        entry["char"] = meta.get("char", "")
        entry["extra_chars"] = meta.get("extra_chars", 0)
        entry["ambiguity_reason"] = meta.get("ambiguity_reason", "")

        # Extract responses
        if record.responses:
            for resp in record.responses:
                if resp.question_name == "verdict":
                    entry["verdict"] = resp.value
                elif resp.question_name == "notes":
                    entry["notes"] = resp.value

        exported.append(entry)

    n_annotated = sum(1 for e in exported if e["verdict"] is not None)
    print(f"  → {len(exported)} records téléchargés ({n_annotated} annotés)")
    return exported


def save_export(exported: list[dict]) -> Path:
    """Save the exported annotations to JSONL."""
    out_path = BASE_DIR / "elongations_annotated.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for entry in exported:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"  Annotations sauvegardées : {out_path}")
    return out_path


# ── HTML visualization of annotations ──────────────────────────────────────────

def _parse_detail_md(detail_md: str) -> dict:
    """Extract structured info from the markdown detail field."""
    info = {"raw_word": "", "trans_word": "", "char": "", "total_repeated": "",
            "expected_count": "", "extra_chars": "", "heuristic": ""}
    m = re.search(r"\*\*Mot brut\*\*\s*:\s*`([^`]*)`", detail_md)
    if m:
        info["raw_word"] = m.group(1)
    m = re.search(r"\*\*Transcrit\*\*\s*:\s*`([^`]*)`", detail_md)
    if m:
        info["trans_word"] = m.group(1)
    m = re.search(r"\*\*Caractère\*\*\s*:\s*`([^`]*)`", detail_md)
    if m:
        info["char"] = m.group(1)
    m = re.search(r"répété\s*\*\*(\d+)×\*\*", detail_md)
    if m:
        info["total_repeated"] = m.group(1)
    m = re.search(r"\*\*(\d+)×\*\*\s*attendu", detail_md)
    if m:
        info["expected_count"] = m.group(1)
    m = re.search(r"\+(\d+)\s*en excès", detail_md)
    if m:
        info["extra_chars"] = m.group(1)
    m = re.search(r"\*\*Heuristique\*\*\s*:\s*`([^`]*)`", detail_md)
    if m:
        info["heuristic"] = m.group(1)
    return info


def generate_annotation_html(exported: list[dict], all_elongations: list[dict] | None = None):
    """Generate an HTML dashboard showing the Argilla annotation results
    merged with the full pipeline (sure + ambiguous)."""

    # ── Separate annotated from unannotated ──
    annotated = [e for e in exported if e["verdict"] is not None]
    pending = [e for e in exported if e["verdict"] is None]

    verdict_counts = Counter(e["verdict"] for e in annotated)
    n_elong = verdict_counts.get("elongation", 0)
    n_typo = verdict_counts.get("typo", 0)

    # ── Compute final counts merging sure + annotated ──
    n_sure_elong = 0
    n_sure_typo = 0
    if all_elongations:
        n_sure_elong = sum(1 for e in all_elongations if e.get("confidence") == "sure_elongation")
        n_sure_typo = sum(1 for e in all_elongations if e.get("confidence") == "sure_typo")

    total_elong = n_sure_elong + n_elong
    total_typo = n_sure_typo + n_typo
    total_all = (len(all_elongations) if all_elongations else len(exported))

    # ── Build table rows ──
    rows_html = []
    for e in exported:
        info = _parse_detail_md(e["detail_elongation"])

        verdict = e["verdict"] or "—"
        verdict_cls = ""
        if e["verdict"] == "elongation":
            verdict_cls = "v-elong"
        elif e["verdict"] == "typo":
            verdict_cls = "v-typo"
        else:
            verdict_cls = "v-pending"

        # Highlight the elongated word in raw text
        raw_esc = html_mod.escape(e["texte_brut"])
        rw_esc = html_mod.escape(info["raw_word"])
        if rw_esc:
            raw_esc = raw_esc.replace(
                rw_esc,
                f'<mark class="elong-hl">{rw_esc}</mark>',
                1,
            )

        trans_esc = html_mod.escape(e["transcription"])
        tw_esc = html_mod.escape(info["trans_word"])
        if tw_esc:
            trans_esc = trans_esc.replace(
                tw_esc,
                f'<span class="trans-hl">{tw_esc}</span>',
                1,
            )

        notes_esc = html_mod.escape(e["notes"] or "")
        heuristic_cls = "h-expr" if info["heuristic"] == "expressif" else "h-typo"

        rows_html.append(f"""<tr data-verdict="{html_mod.escape(e['verdict'] or 'pending')}" \
data-heuristic="{html_mod.escape(info['heuristic'])}" \
data-char="{html_mod.escape(info['char'])}">
  <td>{html_mod.escape(str(e.get('parquet_id', '')))}</td>
  <td class="text-cell">{raw_esc}</td>
  <td class="text-cell">{trans_esc}</td>
  <td><strong>{html_mod.escape(info['raw_word'])}</strong> → {html_mod.escape(info['trans_word'])}</td>
  <td class="char-cell">{html_mod.escape(info['char'])}</td>
  <td>+{html_mod.escape(info['extra_chars'])}</td>
  <td class="{heuristic_cls}">{html_mod.escape(info['heuristic'])}</td>
  <td class="{verdict_cls}">{html_mod.escape(verdict)}</td>
  <td class="notes-cell">{notes_esc}</td>
</tr>""")

    # ── Sure cases rows (from pipeline) ──
    sure_rows_html = []
    if all_elongations:
        for e in all_elongations:
            if e.get("confidence") not in ("sure_elongation", "sure_typo"):
                continue
            label = "elongation" if e["confidence"] == "sure_elongation" else "typo"
            verdict_cls = "v-elong" if label == "elongation" else "v-typo"
            raw_esc = html_mod.escape(e["text_raw"])
            rw_esc = html_mod.escape(e["raw_word"])
            if rw_esc:
                raw_esc = raw_esc.replace(rw_esc, f'<mark class="elong-hl">{rw_esc}</mark>', 1)
            trans_esc = html_mod.escape(e["full_transcription"])
            tw_esc = html_mod.escape(e["trans_word"])
            if tw_esc:
                trans_esc = trans_esc.replace(tw_esc, f'<span class="trans-hl">{tw_esc}</span>', 1)

            sure_rows_html.append(f"""<tr data-verdict="{label}" data-heuristic="{html_mod.escape(e['classification'])}" data-char="{html_mod.escape(e['char'])}">
  <td>{html_mod.escape(str(e['id']))}</td>
  <td class="text-cell">{raw_esc}</td>
  <td class="text-cell">{trans_esc}</td>
  <td><strong>{html_mod.escape(e['raw_word'])}</strong> → {html_mod.escape(e['trans_word'])}</td>
  <td class="char-cell">{html_mod.escape(e['char'])}</td>
  <td>+{e['extra_chars']}</td>
  <td class="h-expr" style="opacity:0.7">auto-LLM</td>
  <td class="{verdict_cls}">{html_mod.escape(label)}</td>
  <td class="notes-cell" style="color:#999">filtré automatiquement (LLM)</td>
</tr>""")

    # ── Character distribution for final verdicts ──
    char_elong = Counter()
    char_typo = Counter()
    for e in annotated:
        info = _parse_detail_md(e["detail_elongation"])
        c = info["char"]
        if e["verdict"] == "elongation":
            char_elong[c] += 1
        else:
            char_typo[c] += 1
    if all_elongations:
        for e in all_elongations:
            if e.get("confidence") == "sure_elongation":
                char_elong[e["char"]] += 1
            elif e.get("confidence") == "sure_typo":
                char_typo[e["char"]] += 1

    char_badges_elong = " ".join(
        f'<span class="cb cb-elong">\'{html_mod.escape(c)}\': <strong>{n}</strong></span>'
        for c, n in char_elong.most_common()
    )
    char_badges_typo = " ".join(
        f'<span class="cb cb-typo">\'{html_mod.escape(c)}\': <strong>{n}</strong></span>'
        for c, n in char_typo.most_common()
    )

    # ── Ambiguity reason breakdown ──
    reason_counts = Counter(e.get("ambiguity_reason", "") for e in exported)
    reason_badges = " ".join(
        f'<span class="reason-badge">{html_mod.escape(r or "?")} : <strong>{n}</strong></span>'
        for r, n in reason_counts.most_common()
    )

    # ── Agreement heuristic vs human ──
    agree = sum(1 for e in annotated
                if (e["heuristic_class"] == "expressif" and e["verdict"] == "elongation")
                or (e["heuristic_class"] == "probable_typo" and e["verdict"] == "typo"))
    disagree = len(annotated) - agree
    agree_pct = f"{agree / len(annotated) * 100:.1f}" if annotated else "—"

    page = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Supervision des élongations — Résultats annotations Argilla</title>
<style>
  :root {{
    --primary: #2c3e50; --accent: #3498db; --elong-color: #27ae60;
    --typo-color: #e67e22; --bg: #f8f9fa; --card-bg: #fff;
    --border: #dee2e6; --text: #212529; --text-muted: #6c757d;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
    padding: 2rem; max-width: 1800px; margin: 0 auto;
  }}
  h1 {{ color: var(--primary); font-size: 1.8rem; margin-bottom: 0.3rem; }}
  .subtitle {{ color: var(--text-muted); margin-bottom: 1.5rem; font-size: 0.95rem; }}

  /* ── Stats cards ── */
  .stats-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem; margin-bottom: 1.5rem;
  }}
  .stat-card {{
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 1rem 1.2rem; text-align: center;
  }}
  .stat-card .val {{ font-size: 2rem; font-weight: 700; }}
  .stat-card .lbl {{ font-size: 0.85rem; color: var(--text-muted); }}
  .val-elong {{ color: var(--elong-color); }}
  .val-typo {{ color: var(--typo-color); }}
  .val-pending {{ color: #95a5a6; }}
  .val-total {{ color: var(--primary); }}

  /* ── Sections ── */
  .section {{
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 1.2rem 1.5rem; margin-bottom: 1.5rem;
  }}
  .section h2 {{ font-size: 1.15rem; color: var(--primary); margin-bottom: 0.8rem;
    border-bottom: 2px solid var(--accent); padding-bottom: 0.3rem; }}

  /* ── Badges ── */
  .cb {{ border-radius: 4px; padding: 2px 8px; font-size: 0.85rem; font-family: monospace;
    display: inline-block; margin-bottom: 4px; }}
  .cb-elong {{ background: #d5f5e3; border: 1px solid #82e0aa; }}
  .cb-typo {{ background: #fdebd0; border: 1px solid #f0b27a; }}
  .reason-badge {{ background: #eaf2f8; border: 1px solid #aed6f1; border-radius: 4px;
    padding: 2px 8px; font-size: 0.85rem; display: inline-block; margin-bottom: 4px; }}

  /* ── Agreement bar ── */
  .agree-bar {{
    height: 28px; border-radius: 14px; overflow: hidden;
    display: flex; margin: 0.5rem 0 0.3rem;
  }}
  .agree-bar .seg {{ display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem; font-weight: 600; color: #fff; }}
  .seg-agree {{ background: var(--elong-color); }}
  .seg-disagree {{ background: var(--typo-color); }}

  /* ── Filter bar ── */
  .filter-box {{
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 0.8rem 1.2rem; margin-bottom: 1.5rem;
    display: flex; gap: 1rem; flex-wrap: wrap; align-items: center;
  }}
  .filter-box label {{ font-weight: 600; color: var(--primary); font-size: 0.9rem; }}
  .filter-box select, .filter-box input[type="text"] {{
    padding: 0.35rem 0.7rem; border: 1px solid var(--border); border-radius: 4px; font-size: 0.9rem;
  }}
  .filter-box input[type="text"] {{ min-width: 220px; }}

  /* ── Table ── */
  table {{ width: 100%; border-collapse: collapse; font-size: 0.84rem; table-layout: auto; }}
  th {{
    background: var(--primary); color: #fff; padding: 0.55rem 0.7rem;
    text-align: left; position: sticky; top: 0; z-index: 2; white-space: nowrap;
  }}
  td {{ padding: 0.45rem 0.7rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
  tbody tr:nth-child(even) {{ background: #f8f9fa; }}
  tbody tr:hover {{ background: #eaf5fb; }}
  .text-cell {{ max-width: 380px; word-break: break-word; }}
  .notes-cell {{ max-width: 200px; word-break: break-word; font-size: 0.82rem; color: #555; }}
  .char-cell {{ font-family: monospace; font-size: 1.05rem; text-align: center; }}

  .elong-hl {{
    background: #d5f5e3; border: 1px solid #82e0aa; border-radius: 3px;
    padding: 0 3px; font-weight: 600;
  }}
  .trans-hl {{
    background: #eaf2f8; border: 1px solid #aed6f1; border-radius: 3px; padding: 0 2px;
  }}

  .v-elong {{
    background: var(--elong-color); color: #fff; padding: 2px 10px; border-radius: 10px;
    font-size: 0.8rem; font-weight: 600; text-align: center; white-space: nowrap;
  }}
  .v-typo {{
    background: var(--typo-color); color: #fff; padding: 2px 10px; border-radius: 10px;
    font-size: 0.8rem; font-weight: 600; text-align: center; white-space: nowrap;
  }}
  .v-pending {{
    background: #bdc3c7; color: #fff; padding: 2px 10px; border-radius: 10px;
    font-size: 0.8rem; font-weight: 600; text-align: center; white-space: nowrap;
  }}
  .h-expr {{ color: #c0392b; font-weight: 600; font-size: 0.82rem; }}
  .h-typo {{ color: #d35400; font-weight: 600; font-size: 0.82rem; }}

  .tab-bar {{
    display: flex; gap: 0; margin-bottom: -1px; position: relative; z-index: 1;
  }}
  .tab-btn {{
    padding: 0.5rem 1.2rem; border: 1px solid var(--border); border-bottom: none;
    background: #eee; cursor: pointer; font-size: 0.9rem; border-radius: 6px 6px 0 0;
    margin-right: 2px;
  }}
  .tab-btn.active {{ background: var(--card-bg); font-weight: 600; border-bottom: 1px solid var(--card-bg); }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}
</style>
</head>
<body>

<h1>Supervision des élongations — Résultats Argilla</h1>
<p class="subtitle">Annotations manuelles fusionnées avec le filtrage automatique LLM.
Dataset : <code>{ARGILLA_DATASET_NAME}</code></p>

<!-- ── Stats ── -->
<div class="stats-grid">
  <div class="stat-card">
    <div class="val val-total">{total_all}</div>
    <div class="lbl">Élongations détectées (total)</div>
  </div>
  <div class="stat-card">
    <div class="val val-elong">{total_elong}</div>
    <div class="lbl">Élongations confirmées<br><small>({n_sure_elong} auto + {n_elong} manuelles)</small></div>
  </div>
  <div class="stat-card">
    <div class="val val-typo">{total_typo}</div>
    <div class="lbl">Typos confirmées<br><small>({n_sure_typo} auto + {n_typo} manuelles)</small></div>
  </div>
  <div class="stat-card">
    <div class="val val-pending">{len(pending)}</div>
    <div class="lbl">Non annotées</div>
  </div>
  <div class="stat-card">
    <div class="val" style="color:var(--accent)">{agree_pct}%</div>
    <div class="lbl">Accord heuristique↔humain<br><small>({agree} / {len(annotated)})</small></div>
  </div>
</div>

<!-- ── Character distributions ── -->
<div class="section">
  <h2>Distribution par caractère allongé</h2>
  <p style="margin-bottom:0.5rem"><strong>Élongations</strong> : {char_badges_elong or "<em>aucune</em>"}</p>
  <p><strong>Typos</strong> : {char_badges_typo or "<em>aucune</em>"}</p>
</div>

<!-- ── Agreement bar ── -->
<div class="section">
  <h2>Accord heuristique ↔ annotation humaine</h2>
  <p style="font-size:0.9rem;margin-bottom:0.3rem">
    Sur les {len(annotated)} cas annotés, l'heuristique automatique est en accord avec
    l'annotateur humain dans <strong>{agree}</strong> cas ({agree_pct}%)
    et en désaccord dans <strong>{disagree}</strong> cas.
  </p>
  <div class="agree-bar">
    <div class="seg seg-agree" style="width:{agree / max(len(annotated),1) * 100:.1f}%">
      {agree} accord{"s" if agree > 1 else ""}
    </div>
    <div class="seg seg-disagree" style="width:{disagree / max(len(annotated),1) * 100:.1f}%">
      {disagree} désaccord{"s" if disagree > 1 else ""}
    </div>
  </div>
</div>

<!-- ── Ambiguity reasons ── -->
<div class="section">
  <h2>Raisons d'ambiguïté (pré-annotation)</h2>
  <div>{reason_badges}</div>
</div>

<!-- ── Filters ── -->
<div class="filter-box">
  <label for="f-text">Recherche :</label>
  <input type="text" id="f-text" placeholder="Filtrer par texte…" oninput="applyF()">
  <label for="f-verdict">Verdict :</label>
  <select id="f-verdict" onchange="applyF()">
    <option value="">Tous</option>
    <option value="elongation">Élongation ({n_elong})</option>
    <option value="typo">Typo ({n_typo})</option>
    <option value="pending">Non annoté ({len(pending)})</option>
  </select>
  <label for="f-char">Caractère :</label>
  <select id="f-char" onchange="applyF()">
    <option value="">Tous</option>
    {"".join(f'<option value="{html_mod.escape(c)}">{html_mod.escape(c)} ({n})</option>'
             for c, n in (char_elong + char_typo).most_common())}
  </select>
</div>

<!-- ── Tabs ── -->
<div class="tab-bar">
  <div class="tab-btn active" onclick="switchTab('annotated')">Cas annotés manuellement ({len(annotated)})</div>
  <div class="tab-btn" onclick="switchTab('sure')">Cas filtrés automatiquement ({n_sure_elong + n_sure_typo})</div>
  <div class="tab-btn" onclick="switchTab('pending')">Non annotés ({len(pending)})</div>
</div>

<!-- Tab: annotated -->
<div id="tab-annotated" class="tab-content active">
<table>
  <thead><tr>
    <th>ID</th><th>Texte brut</th><th>Transcription</th><th>Mot brut → transcrit</th>
    <th>Lettre</th><th>Extra</th><th>Heuristique</th><th>Verdict humain</th><th>Notes</th>
  </tr></thead>
  <tbody class="filterable">
    {"".join(r for r, e in zip(rows_html, exported) if e['verdict'] is not None)}
  </tbody>
</table>
</div>

<!-- Tab: sure -->
<div id="tab-sure" class="tab-content">
<table>
  <thead><tr>
    <th>ID</th><th>Texte brut</th><th>Transcription</th><th>Mot brut → transcrit</th>
    <th>Lettre</th><th>Extra</th><th>Source</th><th>Verdict</th><th>Notes</th>
  </tr></thead>
  <tbody class="filterable">
    {"".join(sure_rows_html)}
  </tbody>
</table>
</div>

<!-- Tab: pending -->
<div id="tab-pending" class="tab-content">
<table>
  <thead><tr>
    <th>ID</th><th>Texte brut</th><th>Transcription</th><th>Mot brut → transcrit</th>
    <th>Lettre</th><th>Extra</th><th>Heuristique</th><th>Verdict</th><th>Notes</th>
  </tr></thead>
  <tbody class="filterable">
    {"".join(r for r, e in zip(rows_html, exported) if e['verdict'] is None)}
  </tbody>
</table>
</div>

<script>
function applyF() {{
  const text = document.getElementById('f-text').value.toLowerCase();
  const vf = document.getElementById('f-verdict').value;
  const cf = document.getElementById('f-char').value;
  document.querySelectorAll('.filterable tr').forEach(function(row) {{
    const rt = row.textContent.toLowerCase();
    const rv = row.getAttribute('data-verdict');
    const rc = row.getAttribute('data-char');
    const tm = !text || rt.indexOf(text) !== -1;
    const vm = !vf || rv === vf;
    const cm = !cf || rc === cf;
    row.style.display = (tm && vm && cm) ? '' : 'none';
  }});
}}
function switchTab(name) {{
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
}}
</script>
</body>
</html>"""

    output_path = BASE_DIR / "supervision_elongations.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"\nRapport HTML généré : {output_path}")
    return output_path


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extraction des allongements graphiques + supervision Argilla"
    )
    parser.add_argument(
        "--push-argilla", action="store_true",
        help="Pousser les cas ambigus vers Argilla pour annotation manuelle",
    )
    parser.add_argument(
        "--export-argilla", action="store_true",
        help="Télécharger les annotations depuis Argilla et générer la visualisation HTML",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Recréer le dataset Argilla s'il existe déjà",
    )
    parser.add_argument(
        "--proxy", default=None,
        help="Proxy HTTP (ex: http://proxy.onera:80)",
    )
    args = parser.parse_args()

    # ── 1. Chargement du parquet ──
    print(f"Lecture de {PARQUET_PATH}...")
    df = pd.read_parquet(PARQUET_PATH)
    print(f"  → {len(df)} lignes")

    df = df[(df['TEXT'].str.len() > 0) & (df['full_transcription'].str.len() > 0)].copy()
    print(f"  → {len(df)} lignes avec TEXT et full_transcription non vides")

    # ── 2. Détection des élongations ──
    print("\nDétection des allongements graphiques...")
    all_elongations = detect_all_elongations(df)
    texts_with = len({e['id'] for e in all_elongations})

    expressifs = [e for e in all_elongations if e['classification'] == 'expressif']
    typos = [e for e in all_elongations if e['classification'] == 'probable_typo']

    print(f"\n=== Détection heuristique ===")
    print(f"Textes avec allongements : {texts_with}")
    print(f"Allongements détectés    : {len(all_elongations)}")
    print(f"  → Expressifs : {len(expressifs)}")
    print(f"  → Probables typos : {len(typos)}")

    # ── 3. Enrichissement LLM ──
    print("\nConstruction de l'index LLM depuis outputs/...")
    llm_index = build_llm_keyword_index()
    print(f"  → {len(llm_index)} textes distincts avec annotations LLM")

    match_elongations_to_llm(all_elongations, llm_index)

    # Stats
    sure_elong = [e for e in all_elongations if e['confidence'] == 'sure_elongation']
    sure_typo = [e for e in all_elongations if e['confidence'] == 'sure_typo']
    ambiguous = [e for e in all_elongations if e['confidence'] == 'ambiguous']

    matched_count = sum(1 for e in all_elongations if e['llm_has_elong_kw'] is not None)

    print(f"\n=== Filtrage par annotations LLM ===")
    print(f"Élongations avec couverture LLM : {matched_count}/{len(all_elongations)}")
    print(f"  → Sûrs élongation   : {len(sure_elong)}")
    print(f"  → Sûrs typo         : {len(sure_typo)}")
    print(f"  → Ambigus (→ Argilla) : {len(ambiguous)}")

    reason_counts = Counter(e.get('ambiguity_reason') for e in ambiguous)
    if reason_counts:
        print(f"\n  Détail des cas ambigus :")
        for reason, count in reason_counts.most_common():
            print(f"    {reason}: {count}")

    # ── 4. Sauvegarde JSONL enrichi ──
    output_path = BASE_DIR / "elongations_with_confidence.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for e in all_elongations:
            # Convert sets to lists for JSON serialization
            row = {k: (list(v) if isinstance(v, set) else v) for k, v in e.items()}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nRésultats enrichis sauvegardés : {output_path}")

    # Backward compat: save original format too
    output_path_orig = BASE_DIR / "elongations_detected.jsonl"
    with open(output_path_orig, "w", encoding="utf-8") as f:
        for e in all_elongations:
            row = {k: v for k, v in e.items()
                   if k not in ('llm_has_elong_kw', 'llm_has_typo_kw',
                                'llm_span_match_elong', 'llm_span_match_typo',
                                'llm_justifications', 'confidence', 'ambiguity_reason')}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # ── 5. Rapport HTML ──
    generate_html_report(all_elongations, texts_with, len(df))

    # ── 6. Push Argilla (optionnel) ──
    if args.push_argilla:
        push_ambiguous_to_argilla(all_elongations, proxy=args.proxy, force=args.force)

    # ── 7. Export Argilla + visualisation HTML ──
    if args.export_argilla:
        exported = export_from_argilla(proxy=args.proxy)
        if exported:
            save_export(exported)
            generate_annotation_html(exported, all_elongations)


def generate_html_report(all_elongations, texts_with_elongations, total_texts):
    """Generate an HTML visualization of detected elongations."""
    expressifs = [e for e in all_elongations if e['classification'] == 'expressif']
    typos = [e for e in all_elongations if e['classification'] == 'probable_typo']
    
    char_counts_expr = Counter(e['char'] for e in expressifs)
    char_counts_all = Counter(e['char'] for e in all_elongations)

    rows_html = []
    for e in all_elongations:
        # Highlight the elongated word in the raw text
        raw_escaped = html_mod.escape(e['text_raw'])
        raw_word_escaped = html_mod.escape(e['raw_word'])
        if raw_word_escaped:
            raw_escaped = raw_escaped.replace(
                raw_word_escaped,
                f'<mark class="elong-hl">{raw_word_escaped}</mark>',
                1,
            )

        trans_escaped = html_mod.escape(e['full_transcription'])
        trans_word_escaped = html_mod.escape(e['trans_word'])
        if trans_word_escaped:
            trans_escaped = trans_escaped.replace(
                trans_word_escaped,
                f'<span class="trans-hl">{trans_word_escaped}</span>',
                1,
            )

        cls_label = "expressif" if e['classification'] == 'expressif' else "typo"
        cls_class = "cls-expr" if e['classification'] == 'expressif' else "cls-typo"

        rows_html.append(f"""<tr data-cls="{e['classification']}" data-char="{html_mod.escape(e['char'])}">
  <td>{html_mod.escape(str(e['id']))}</td>
  <td>{html_mod.escape(e['name'])}</td>
  <td class="text-cell">{raw_escaped}</td>
  <td class="text-cell">{trans_escaped}</td>
  <td><strong>{html_mod.escape(e['raw_word'])}</strong> → {html_mod.escape(e['trans_word'])}</td>
  <td class="char-cell">'{html_mod.escape(e['char'])}'</td>
  <td>{e['total_repeated']}</td>
  <td>{e['expected_count']}</td>
  <td>+{e['extra_chars']}</td>
  <td class="{cls_class}">{cls_label}</td>
</tr>""")

    # Character distribution
    char_badges = []
    for c, cnt in char_counts_expr.most_common():
        char_badges.append(
            f'<span class="char-badge">\'{html_mod.escape(c)}\': <strong>{cnt}</strong></span>'
        )

    page = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Allongements graphiques — Extraction par comparaison TEXT / Transcription</title>
<style>
  :root {{
    --primary: #2c3e50;
    --accent: #e74c3c;
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
    max-width: 1800px;
    margin: 0 auto;
  }}
  h1 {{ color: var(--primary); font-size: 1.8rem; margin-bottom: 0.5rem; }}
  .subtitle {{ color: var(--text-muted); margin-bottom: 1.5rem; }}
  .stats {{
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 1rem 1.5rem; margin-bottom: 1.5rem;
    display: flex; gap: 2rem; flex-wrap: wrap; align-items: center;
  }}
  .stats .stat {{ font-size: 1.1rem; }}
  .stats .stat strong {{ color: var(--accent); font-size: 1.3rem; }}
  .char-dist {{
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 1rem 1.5rem; margin-bottom: 1.5rem;
  }}
  .char-dist h2 {{ font-size: 1.1rem; color: var(--primary); margin-bottom: 0.5rem; }}
  .char-badges {{ display: flex; flex-wrap: wrap; gap: 0.5rem; }}
  .char-badge {{
    background: #fde8e8; border: 1px solid #f5b7b7; border-radius: 4px;
    padding: 3px 10px; font-size: 0.9rem; font-family: monospace;
  }}
  .filter-box {{
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 1rem 1.5rem; margin-bottom: 1.5rem;
    display: flex; gap: 1rem; flex-wrap: wrap; align-items: center;
  }}
  .filter-box label {{ font-weight: 600; color: var(--primary); }}
  .filter-box input, .filter-box select {{
    padding: 0.4rem 0.8rem; border: 1px solid var(--border); border-radius: 4px; font-size: 0.95rem;
  }}
  .filter-box input[type="text"] {{ min-width: 250px; }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 0.85rem; table-layout: auto;
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
  }}
  th {{
    background: var(--primary); color: white; padding: 0.6rem 0.8rem;
    text-align: left; position: sticky; top: 0; z-index: 1; white-space: nowrap;
  }}
  td {{ padding: 0.5rem 0.8rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
  tbody tr:nth-child(even) {{ background: #f8f9fa; }}
  tbody tr:hover {{ background: #fce4e4; }}
  .text-cell {{ max-width: 400px; word-break: break-word; }}
  .char-cell {{ font-family: monospace; font-size: 1.1rem; text-align: center; }}
  .elong-hl {{
    background: #ffcccc; border: 1px solid #e74c3c; border-radius: 3px; padding: 0 3px;
    font-weight: 600;
  }}
  .trans-hl {{
    background: #d4edda; border: 1px solid #a3d9a5; border-radius: 3px; padding: 0 2px;
  }}
  .cls-expr {{
    background: #e74c3c; color: white; padding: 2px 8px; border-radius: 10px;
    font-size: 0.8rem; font-weight: 600; text-align: center; white-space: nowrap;
  }}
  .cls-typo {{
    background: #f39c12; color: white; padding: 2px 8px; border-radius: 10px;
    font-size: 0.8rem; font-weight: 600; text-align: center; white-space: nowrap;
  }}
  .method-box {{
    background: #fffde7; border: 1px solid #fff176; border-radius: 8px;
    padding: 1rem 1.5rem; margin-bottom: 1.5rem;
  }}
  .method-box h2 {{ font-size: 1.1rem; color: #f57f17; margin-bottom: 0.5rem; }}
  .method-box ol {{ padding-left: 1.5rem; }}
  .method-box li {{ margin-bottom: 0.3rem; }}
</style>
</head>
<body>

<h1>Allongements graphiques — Extraction par diff TEXT / Transcription</h1>
<p class="subtitle">Détection automatique des étirements de lettres en comparant le texte SMS brut
à sa transcription corrigée (full_transcription) dans le corpus CyberBullyingExperiment.</p>

<div class="method-box">
  <h2>Méthode utilisée</h2>
  <ol>
    <li>Alignement caractère par caractère du TEXT brut et de la full_transcription via <code>difflib.SequenceMatcher</code></li>
    <li>Détection des opérations <em>delete</em> : caractères présents dans le brut mais absents de la transcription</li>
    <li>Filtrage : ne garder que les suppressions de lettres alphabétiques identiques et adjacentes à la même lettre</li>
    <li>Détection des opérations <em>replace</em> : segments où un caractère domine (≥60%) et apparaît plus souvent que dans la transcription</li>
    <li>Reconstruction du mot brut et du mot transcrit correspondant</li>
    <li><strong>Classification</strong> : <span class="cls-expr">expressif</span> si extra ≥ 2 ou total ≥ 3 ;
        <span class="cls-typo">typo</span> si extra = 1 et total = 2 (probable doublement accidentel)</li>
  </ol>
</div>

<div class="stats">
  <div class="stat">Textes analysés : <strong>{total_texts}</strong></div>
  <div class="stat">Textes avec allongements : <strong>{texts_with_elongations}</strong></div>
  <div class="stat">Total détectés : <strong>{len(all_elongations)}</strong></div>
  <div class="stat">Expressifs : <strong style="color:#e74c3c">{len(expressifs)}</strong></div>
  <div class="stat">Probables typos : <strong style="color:#f39c12">{len(typos)}</strong></div>
</div>

<div class="char-dist">
  <h2>Distribution par caractère allongé (expressifs uniquement)</h2>
  <div class="char-badges">{"  ".join(char_badges)}</div>
</div>

<div class="filter-box">
  <label for="filter-text">Recherche :</label>
  <input type="text" id="filter-text" placeholder="Filtrer par texte…" oninput="applyFilters()">
  <label for="filter-char">Caractère :</label>
  <select id="filter-char" onchange="applyFilters()">
    <option value="">Tous</option>
    {"".join(f'<option value="{html_mod.escape(c)}">{html_mod.escape(c)} ({cnt})</option>' for c, cnt in char_counts_all.most_common())}
  </select>
  <label for="filter-cls">Classification :</label>
  <select id="filter-cls" onchange="applyFilters()">
    <option value="">Tous</option>
    <option value="expressif" selected>Expressifs ({len(expressifs)})</option>
    <option value="probable_typo">Probables typos ({len(typos)})</option>
  </select>
</div>

<table>
  <thead>
    <tr>
      <th>ID</th>
      <th>Auteur</th>
      <th>Texte brut (TEXT)</th>
      <th>Transcription</th>
      <th>Mot brut → transcrit</th>
      <th>Lettre</th>
      <th>Répété</th>
      <th>Attendu</th>
      <th>Extra</th>
      <th>Type</th>
    </tr>
  </thead>
  <tbody>
    {"".join(rows_html)}
  </tbody>
</table>

<script>
function applyFilters() {{
  const text = document.getElementById('filter-text').value.toLowerCase();
  const charFilter = document.getElementById('filter-char').value;
  const clsFilter = document.getElementById('filter-cls').value;
  document.querySelectorAll('tbody tr').forEach(function(row) {{
    const rowText = row.textContent.toLowerCase();
    const rowChar = row.getAttribute('data-char');
    const rowCls = row.getAttribute('data-cls');
    const textMatch = !text || rowText.indexOf(text) !== -1;
    const charMatch = !charFilter || rowChar === charFilter;
    const clsMatch = !clsFilter || rowCls === clsFilter;
    row.style.display = (textMatch && charMatch && clsMatch) ? '' : 'none';
  }});
}}
// Apply default filter on load (show expressifs only)
document.addEventListener('DOMContentLoaded', applyFilters);
</script>

</body>
</html>"""

    output_path = BASE_DIR / "allongements_graphiques.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Rapport HTML généré : {output_path}")


if __name__ == "__main__":
    main()
