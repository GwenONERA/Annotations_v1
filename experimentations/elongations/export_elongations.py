import json
import re
import difflib

# Chemins d'accès
INPUT_FILE = r"C:\Users\gtsang\Desktop\New\elongations\elongations_annotated.jsonl"
OUTPUT_FILE = "resultat_elongations.html"

def highlight_diff(raw, trans):
    """Compare deux mots et surligne la différence (jaune pour l'original, vert pour le transcrit)."""
    sm = difflib.SequenceMatcher(None, raw, trans)
    raw_hl, trans_hl = "", ""
    
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            raw_hl += raw[i1:i2]
            trans_hl += trans[j1:j2]
        elif tag == 'delete':
            raw_hl += f"<span style='background-color: yellow;'>{raw[i1:i2]}</span>"
        elif tag == 'insert':
            trans_hl += f"<span style='background-color: lightgreen;'>{trans[j1:j2]}</span>"
        elif tag == 'replace':
            raw_hl += f"<span style='background-color: yellow;'>{raw[i1:i2]}</span>"
            trans_hl += f"<span style='background-color: lightgreen;'>{trans[j1:j2]}</span>"
            
    return raw_hl, trans_hl

# Initialisation du HTML minimaliste
html_content = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<table border="1" style="border-collapse: collapse; width: 100%; text-align: left;">
    <tr>
        <th>Phrase</th>
        <th>Mot original &rarr; Mot transcris</th>
    </tr>
"""

with open(INPUT_FILE, 'r', encoding='utf-8') as f:
    for line in f:
        if not line.strip(): continue
        data = json.loads(line)
        
        # Filtrer pour ne garder QUE les élongations (selon l'annotation ou l'heuristique)
        if data.get("verdict") == "elongation" or data.get("heuristic_class") == "expressif":
            texte = data.get("texte_brut", "")
            detail = data.get("detail_elongation", "")
            
            # Extraction du mot brut et transcrit depuis le champ markdown
            m_raw = re.search(r"\*\*Mot brut\*\*\s*:\s*`([^`]*)`", detail)
            m_trans = re.search(r"\*\*Transcrit\*\*\s*:\s*`([^`]*)`", detail)
            
            raw_w = m_raw.group(1) if m_raw else ""
            trans_w = m_trans.group(1) if m_trans else ""
            
            if raw_w and trans_w:
                # Création des mots avec différences surlignées
                raw_diff, trans_diff = highlight_diff(raw_w, trans_w)
                
                # Ajout de la ligne au tableau HTML
                html_content += f"""
                <tr>
                    <td>{texte}</td>
                    <td>{raw_diff} &rarr; {trans_diff}</td>
                </tr>
                """

html_content += "</table></body></html>"

# Écriture du fichier final
with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
    out.write(html_content)

print(f"Terminé. Le fichier {OUTPUT_FILE} a été généré avec succès.")