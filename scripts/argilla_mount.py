#!/usr/bin/env python3
"""
Script final pour pousser un XLSX vers Argilla avec gestion des erreurs Excel.
"""

import os
import sys
import argparse
import pandas as pd
import argilla as rg
from typing import List, Dict

# --- Constantes ---
EMOTIONS = [
    "Colère", "Dégoût", "Joie", "Peur", "Surprise", "Tristesse",
    "Admiration", "Culpabilité", "Embarras", "Fierté", "Jalousie", "Autre",
]

MODES = ["Désignée", "Comportementale", "Suggérée", "Montrée"]

# --- Connexion à Argilla ---
def connect_argilla(api_url: str, api_key: str) -> rg.Argilla:
    """Se connecter à Argilla."""
    return rg.Argilla(api_url=api_url, api_key=api_key)

# --- Préparation du dataset ---
def prepare_argilla_dataset(
    client: rg.Argilla,
    dataset_name: str,
    workspace: str = "argilla",
    force: bool = False,
) -> rg.Dataset:
    """Créer un dataset Argilla avec une question obligatoire."""
    settings = rg.Settings(
        guidelines=(
            "Annotatez **au moins une émotion** par message. "
            "Pour les spans, utilisez le format JSON fourni en exemple."
        ),
        fields=[
            rg.TextField(name="message", title="Message à annoter", use_markdown=True),
            rg.TextField(name="contexte", title="Contexte", use_markdown=True),
        ],
        questions=[
            rg.MultiLabelQuestion(
                name="emotions",
                title="Émotions présentes (obligatoire)",
                labels=EMOTIONS,
                required=True,  # Question obligatoire
            ),
            rg.TextQuestion(
                name="spans_json",
                title="Spans (format JSON)",
                description=(
                    "Exemple :\n```json\n[{\n"
                    '  "span_text": "je suis triste",\n'
                    '  "categorie": "Tristesse",\n'
                    '  "mode": "Désignée",\n'
                    '  "justification": "expression claire"\n'
                    "}]\n```"
                ),
                required=False,
            ),
            rg.TextQuestion(name="notes", title="Notes", required=False),
        ],
        metadata=[
            rg.IntegerMetadataProperty(name="idx", title="Index"),
            rg.TermsMetadataProperty(name="source", title="Fichier source"),
        ],
    )

    # Gestion du dataset existant
    try:
        existing = client.datasets(name=dataset_name, workspace=workspace)
        if force:
            print(f"Suppression du dataset existant '{dataset_name}'...")
            existing.delete()
        else:
            print(f"⚠ Le dataset '{dataset_name}' existe déjà. Utilisez --force pour le recréer.")
            sys.exit(1)
    except Exception:
        pass  # Dataset n'existe pas

    dataset = rg.Dataset(
        name=dataset_name,
        workspace=workspace,
        settings=settings,
        client=client,
    )
    dataset.create()
    print(f"✓ Dataset '{dataset_name}' créé.")
    return dataset

# --- Lecture du XLSX avec gestion des erreurs ---
def read_xlsx(xlsx_path: str) -> pd.DataFrame:
    """Lire un fichier XLSX avec gestion des erreurs de format."""
    try:
        # Utilisation explicite de openpyxl pour les fichiers .xlsx
        df = pd.read_excel(xlsx_path, engine="openpyxl")
        if "TEXT" not in df.columns:
            raise ValueError("La colonne 'TEXT' est manquante.")
        return df
    except Exception as e:
        print(f"⚠ Erreur de lecture du fichier XLSX : {str(e)}")
        print("   Vérifiez que :")
        print("   1. Le fichier est bien au format .xlsx (pas .xls)")
        print("   2. La colonne 'TEXT' existe")
        print("   3. Le fichier n'est pas corrompu")
        sys.exit(1)

# --- Préparation des records ---
def prepare_records_from_xlsx(xlsx_path: str) -> List[rg.Record]:
    """Préparer les records Argilla depuis un XLSX."""
    df = read_xlsx(xlsx_path)  # Utilise la fonction robuste
    records = []

    for _, row in df.iterrows():
        text = str(row.get("TEXT", ""))
        name = str(row.get("NAME", ""))
        role = str(row.get("ROLE", ""))
        idx = row.get("idx", len(records))

        message_md = f"> {text}" if text else "> *(vide)*"
        contexte_md = f"**Locuteur :** {name} | **Rôle :** {role}" if name or role else "*Aucun contexte*"

        records.append(
            rg.Record(
                id=f"msg_{idx}",
                fields={
                    "message": message_md,
                    "contexte": contexte_md,
                },
                metadata={
                    "idx": idx,
                    "source": os.path.basename(xlsx_path),
                },
            )
        )

    return records

# --- Push vers Argilla ---
def push_to_argilla(
    xlsx_path: str,
    api_url: str,
    api_key: str,
    dataset_name: str = "new",
    workspace: str = "argilla",
    force: bool = False,
) -> None:
    """Processus complet avec gestion des erreurs."""
    try:
        # 1. Connexion à Argilla
        client = connect_argilla(api_url, api_key)

        # 2. Création du dataset
        dataset = prepare_argilla_dataset(client, dataset_name, workspace, force)

        # 3. Lecture du XLSX (avec gestion d'erreur)
        records = prepare_records_from_xlsx(xlsx_path)

        if not records:
            print("⚠ Aucun message valide trouvé dans le XLSX.")
            return

        # 4. Push des records
        dataset.records.log(records)
        print(f"✓ {len(records)} messages poussés vers Argilla.")

        # 5. Ouverture du navigateur
        import webbrowser
        webbrowser.open(api_url)
        print(f"Interface : {api_url}")

    except Exception as e:
        print(f"⚠ Erreur critique : {str(e)}")
        sys.exit(1)

# --- Parsing des arguments ---
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pousser un XLSX vers Argilla pour annotation manuelle."
    )
    parser.add_argument("--xlsx", required=True, help="Chemin vers le fichier XLSX.")
    parser.add_argument("--api_url", required=True, help="URL de l'instance Argilla.")
    parser.add_argument("--api_key", required=True, help="Clé API Argilla.")
    parser.add_argument("--dataset", default="new", help="Nom du dataset.")
    parser.add_argument("--workspace", default="argilla", help="Workspace.")
    parser.add_argument("--force", action="store_true", help="Forcer la recréation.")
    return parser.parse_args()

# --- Main ---
if __name__ == "__main__":
    args = parse_args()
    push_to_argilla(
        args.xlsx,
        args.api_url,
        args.api_key,
        args.dataset,
        args.workspace,
        args.force,
    )
