import json
from datetime import datetime

import config

STRUCTURE_VIDE = {
    "offres_vues": [],
    "offres_signalees": [],
    "offres_detectees": [],
    "historique": [],
}

def _normaliser_structure(memoire: dict) -> dict:
    for cle, valeur in STRUCTURE_VIDE.items():
        if cle not in memoire:
            memoire[cle] = valeur.copy() if isinstance(valeur, list) else valeur
    return memoire

def charger() -> dict:
    if config.FICHIER_MEMOIRE.exists():
        with open(config.FICHIER_MEMOIRE, "r", encoding="utf-8") as f:
            memoire = json.load(f)
        memoire = _normaliser_structure(memoire)
        print(
            "  Mémoire chargée : "
            f"{len(memoire['offres_vues'])} vue(s), "
            f"{len(memoire['offres_detectees'])} détectée(s), "
            f"{len(memoire['offres_signalees'])} signalée(s)"
        )
        return memoire

    print("  Première utilisation — mémoire vide créée")
    return STRUCTURE_VIDE.copy()

def sauvegarder(memoire: dict):
    config.FICHIER_MEMOIRE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.FICHIER_MEMOIRE, "w", encoding="utf-8") as f:
        json.dump(memoire, f, ensure_ascii=False, indent=2)

def est_deja_vue(memoire: dict, id_offre: str) -> bool:
    return id_offre in memoire["offres_vues"]

def est_signalée(memoire: dict, id_offre: str) -> bool:
    return id_offre in memoire["offres_signalees"]

def est_detectee(memoire: dict, id_offre: str) -> bool:
    return id_offre in memoire["offres_detectees"]

def enregistrer_detection(memoire: dict, offre: dict, score_rag: float, decision: str, score_final: float | None = None):
    id_offre = offre["id"]

    if id_offre not in memoire["offres_detectees"]:
        memoire["offres_detectees"].append(id_offre)

    memoire["historique"].append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "DETECTION",
        "offre_id": id_offre,
        "titre": offre["titre"],
        "entreprise": offre["entreprise"],
        "decision": decision,
        "score_rag": round(score_rag, 3),
        "score_final": round(score_final if score_final is not None else score_rag, 3),
    })
    sauvegarder(memoire)

def enregistrer(memoire: dict, offre: dict, decision: str, score_rag: float, score_final: float | None = None):
    id_offre = offre["id"]

    if id_offre not in memoire["offres_vues"]:
        memoire["offres_vues"].append(id_offre)

    if decision == config.DECISION_ACCEPTE and id_offre not in memoire["offres_signalees"]:
        memoire["offres_signalees"].append(id_offre)

    memoire["historique"].append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "ANALYSE",
        "offre_id": id_offre,
        "titre": offre["titre"],
        "entreprise": offre["entreprise"],
        "decision": decision,
        "score_rag": round(score_rag, 3),
        "score_final": round(score_final if score_final is not None else score_rag, 3),
    })

    sauvegarder(memoire)

def afficher_resume(memoire: dict):
    print(f"\n{'='*60}")
    print("  RÉSUMÉ DE LA MÉMOIRE")
    print(f"{'='*60}")
    print(f"  Offres analysées              : {len(memoire['offres_vues'])}")
    print(f"  Offres détectées (score seuil): {len(memoire['offres_detectees'])}")
    print(f"  Offres signalées (ACCEPTÉES)  : {len(memoire['offres_signalees'])}")

    if memoire["historique"]:
        print("\n  Dernières traces :")
        for entree in memoire["historique"][-8:]:
            symbole = {"ACCEPTÉ": "✓", "REFUSÉ": "✗", "JE NE SAIS PAS": "?"}.get(entree["decision"], "•")
            type_evt = entree.get("type", "LOG")
            print(
                f"    {symbole} [{entree['date']}] {type_evt:<9} "
                f"{entree['titre'][:36]:<36} — score_rag: {entree['score_rag']:.2f} "
                f"| final: {entree.get('score_final', entree['score_rag']):.2f}"
            )
    print()
