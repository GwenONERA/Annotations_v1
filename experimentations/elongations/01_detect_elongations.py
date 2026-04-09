#!/usr/bin/env python3
import pandas as pd
import json
from pathlib import Path
from difflib import SequenceMatcher
from collections import Counter

# Logique de détection
def find_elongations(text_raw: str, text_trans: str) -> list[dict]:
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
            if len(deleted) >= 1 and len(set(deleted)) == 1:
                c = deleted[0]
                if c.isalpha():
                    adjacent = False
                    if i1 > 0 and raw_lower[i1 - 1] == c: adjacent = True
                    if i2 < len(raw_lower) and raw_lower[i2] == c: adjacent = True
                    if not adjacent: continue

                    start = i1
                    while start > 0 and raw_lower[start - 1] == c: start -= 1
                    end = i2
                    while end < len(raw_lower) and raw_lower[end] == c: end += 1
                    total_in_raw = end - start

                    if start in seen_positions: continue
                    seen_positions.add(start)

                    expected = total_in_raw - len(deleted)

                    word_start = raw_lower.rfind(' ', 0, start) + 1
                    word_end = raw_lower.find(' ', end)
                    if word_end == -1: word_end = len(raw_lower)
                    raw_word = text_raw[word_start:word_end]

                    tw_start = trans_lower.rfind(' ', 0, j1) + 1
                    tw_end = trans_lower.find(' ', j1)
                    if tw_end == -1: tw_end = len(trans_lower)
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
            raw_seg = raw_lower[i1:i2]
            trans_seg = trans_lower[j1:j2]
            if len(raw_seg) >= 3:
                counter = Counter(raw_seg)
                most_common_char, most_common_count = counter.most_common(1)[0]
                if most_common_char.isalpha() and most_common_count >= len(raw_seg) * 0.6:
                    trans_count = trans_seg.count(most_common_char)
                    if most_common_count > trans_count and most_common_count >= 3:
                        if i1 in seen_positions: continue
                        seen_positions.add(i1)

                        word_start = raw_lower.rfind(' ', 0, i1) + 1
                        word_end = raw_lower.find(' ', i2)
                        if word_end == -1: word_end = len(raw_lower)
                        raw_word = text_raw[word_start:word_end]

                        tw_start = trans_lower.rfind(' ', 0, j1) + 1
                        tw_end = trans_lower.find(' ', j2)
                        if tw_end == -1: tw_end = len(trans_lower)
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
    if e['extra_chars'] >= 2:
        return 'expressif'
    if e['extra_chars'] == 1 and e['total_repeated'] >= 3:
        return 'expressif'
    return 'probable_typo'

# -- Fin de la logique ciblée --

def main():
    base_dir = Path(__file__).parent
    parquet_path = base_dir / 'data' / 'CyberBullyingExperiment.parquet'
    excel_path = base_dir / 'outputs' / 'religion' / 'religion_annotations_gold_flat.xlsx'
    
    print("Chargement des données...")
    try:
        pq_df = pd.read_parquet(parquet_path)
    except Exception as e:
        print(f"Erreur à la lecture du parquet : {e}")
        print("Assurez-vous que pyarrow est installé (`pip install pyarrow`).")
        return
        
    ex_df = pd.read_excel(excel_path)
    
    # Cast en string pour éviter l'erreur de type int64 / string lors du merge
    ex_df['ID'] = ex_df['ID'].astype(str)
    pq_df['ID'] = pq_df['ID'].astype(str)
    
    # On fait un merge pour récupérer la full_transcription (qui est dans pq_df) sur la clef 'ID'
    merged = ex_df.merge(pq_df[['ID', 'full_transcription']], on='ID', how='left', suffixes=('', '_pq'))
    
    ambiguous = []
    
    for row_idx, row in merged.iterrows():
        text_raw = str(row.get('TEXT', ''))
        text_trans = str(row.get('full_transcription', ''))
        r_id = row['ID']
        idx = row['idx']
        
        if not text_raw or not text_trans or text_raw == 'nan':
            continue
            
        elongs = find_elongations(text_raw, text_trans)
        
        if not elongs:
            continue
            
        for e in elongs:
            classification = classify_elongation(e)
            entry = {
                'idx': idx,
                'id': r_id,
                'text_raw': text_raw,
                'full_transcription': text_trans,
                'classification': classification,
                'raw_word': e['raw_word'],
                'trans_word': e['trans_word'],
                'char': e['char'],
                'position': e['position']
            }
            ambiguous.append(entry)

    out_file = base_dir / 'outputs' / 'religion' / 'to_review.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(ambiguous, f, ensure_ascii=False, indent=2)
    
    print(f"Extraction terminée. {len(ambiguous)} phénomènes détectés et sauvegardés dans {out_file}.")
    print("Passez à l'étape 2 : lancez 02_supervise.py")

if __name__ == '__main__':
    main()
