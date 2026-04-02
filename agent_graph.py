from __future__ import annotations

from typing import Optional, TypedDict

import config
import llm as llm_module
import memoire as mem_module
import rag as rag_module

class EtatAgent(TypedDict):
    offre: dict
    collection: object
    llm: object
    memoire: dict

    deja_vue: bool
    resultats_rag: Optional[dict]
    score_rag: float
    score_llm: float
    score_final: float

    decision: str
    explication: str
    reponse_llm: str

def noeud_verifier_memoire(etat: EtatAgent) -> EtatAgent:
    id_offre = etat["offre"]["id"]
    deja_vue = mem_module.est_deja_vue(etat["memoire"], id_offre)

    if deja_vue:
        print("  [Mémoire] Offre déjà vue → passage à la suivante")
        return {
            **etat,
            "deja_vue": True,
            "decision": "DÉJÀ ANALYSÉE",
            "explication": "",
            "reponse_llm": "",
            "score_rag": 0.0,
            "score_llm": 0.0,
            "score_final": 0.0,
            "resultats_rag": None,
        }

    print("  [Mémoire] Nouvelle offre → analyse lancée")
    return {**etat, "deja_vue": False}

def noeud_interroger_rag(etat: EtatAgent) -> EtatAgent:
    offre = etat["offre"]

    print("  [RAG] Recherche hybride dans ChromaDB...")
    resultats = rag_module.rechercher_cv(etat["collection"], offre)

    score = float(resultats["score"])
    print(f"  [RAG] Score hybride : {score:.2f}/1.00")
    mots_cles = resultats.get("mots_cles", [])[:8]
    if mots_cles:
        print(f"  [RAG] Mots-clés extraits : {', '.join(mots_cles)}")

    preuves = resultats.get("preuves", {})
    if preuves:
        print(
            "  [RAG] Preuves | "
            f"titre={preuves.get('couverture_titre', 0.0):.2f} | "
            f"compétences={preuves.get('couverture_competences', 0.0):.2f} | "
            f"domaine={preuves.get('couverture_domaine', 0.0):.2f} | "
            f"support_chunks={preuves.get('support_chunks', 0.0):.2f}"
        )

    return {**etat, "resultats_rag": resultats, "score_rag": score}

def noeud_evaluer_score(etat: EtatAgent) -> EtatAgent:
    score = float(etat["score_rag"] or 0.0)
    preuves = (etat.get("resultats_rag") or {}).get("preuves", {})

    preuves_fortes = (
        preuves.get("couverture_competences", 0.0) >= config.SEUIL_COUVERTURE_COMPETENCES
        or preuves.get("couverture_titre", 0.0) >= config.SEUIL_COUVERTURE_TITRE
        or preuves.get("role_family_match", False)
    )

    if score < config.SEUIL_SIMILARITE and not preuves_fortes:
        print(f"  [Score] {score:.2f} < {config.SEUIL_SIMILARITE} → JE NE SAIS PAS (RAG)")
        explication = (
            f"Score RAG trop bas ({score:.2f}) et preuves lexicales insuffisantes. "
            "Le CV ne contient pas assez d'éléments réellement proches de cette offre."
        )
        return {
            **etat,
            "decision": config.DECISION_NSP,
            "explication": explication,
            "reponse_llm": explication,
            "score_llm": 0.0,
            "score_final": score,
        }

    print(f"  [Score] {score:.2f} → analyse LLM")
    return etat

def noeud_appeler_llm(etat: EtatAgent) -> EtatAgent:
    chunks = (etat["resultats_rag"] or {}).get("chunks", [])
    resultat_llm = llm_module.analyser_offre(etat["llm"], chunks, etat["offre"])

    return {
        **etat,
        "decision": resultat_llm["decision"],
        "explication": resultat_llm["explication"],
        "reponse_llm": resultat_llm["reponse_complete"],
        "score_llm": resultat_llm["score_llm"],
    }

def noeud_calculer_score_final(etat: EtatAgent) -> EtatAgent:
    score_rag = float(etat.get("score_rag", 0.0) or 0.0)
    score_llm = float(etat.get("score_llm", 0.0) or 0.0)
    decision = etat.get("decision", config.DECISION_NSP)

    multiplicateur_decision = {
        config.DECISION_ACCEPTE: 1.00,
        config.DECISION_NSP: 0.90,
        config.DECISION_REFUSE: 0.72,
    }.get(decision, 0.90)

    score_final = (
        config.PONDERATION_SCORE_RAG * score_rag
        + config.PONDERATION_SCORE_LLM * score_llm
    ) * multiplicateur_decision

    score_final = max(0.0, min(1.0, score_final))
    print(
        f"  [Score final] RAG={score_rag:.2f} | LLM={score_llm:.2f} | "
        f"Décision={decision} | Final={score_final:.2f}"
    )

    return {**etat, "score_final": score_final}

def router_apres_memoire(etat: EtatAgent) -> str:
    if etat.get("deja_vue", False):
        return "fin"
    return "continuer"

def router_apres_score(etat: EtatAgent) -> str:
    if etat.get("decision") == config.DECISION_NSP and float(etat.get("score_llm", 0.0) or 0.0) == 0.0:
        return "nsp_direct"
    return "appeler_llm"

class GrapheCompatible:
    def __init__(self):
        self.nodes = {
            "verifier_memoire": noeud_verifier_memoire,
            "interroger_rag": noeud_interroger_rag,
            "evaluer_score": noeud_evaluer_score,
            "appeler_llm": noeud_appeler_llm,
            "calculer_score_final": noeud_calculer_score_final,
        }

    def invoke(self, etat_initial: EtatAgent) -> EtatAgent:
        etat = noeud_verifier_memoire(etat_initial)
        if router_apres_memoire(etat) == "fin":
            return etat

        etat = noeud_interroger_rag(etat)
        etat = noeud_evaluer_score(etat)

        if router_apres_score(etat) == "appeler_llm":
            etat = noeud_appeler_llm(etat)

        etat = noeud_calculer_score_final(etat)
        return etat

def construire_graphe():
    print("  [INIT] Graphe compatible chargé (sans import LangGraph)")
    return GrapheCompatible()

def analyser_une_offre(graphe, offre: dict, collection, llm, memoire: dict) -> dict:
    etat_initial: EtatAgent = {
        "offre": offre,
        "collection": collection,
        "llm": llm,
        "memoire": memoire,
        "deja_vue": False,
        "resultats_rag": None,
        "score_rag": 0.0,
        "score_llm": 0.0,
        "score_final": 0.0,
        "decision": "",
        "explication": "",
        "reponse_llm": "",
    }
    return graphe.invoke(etat_initial)
