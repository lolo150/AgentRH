from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from langchain.tools import tool
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

import config

SYSTEM_PROMPT = (
    "Tu es un agent expert en matching CV/offre d'emploi. "
    "Tu utilises les tools disponibles pour accomplir chaque tâche demandée. "
    "Quand on te demande d'enregistrer, notifier ou créer une note, tu appelles TOUJOURS les tools correspondants. "
    "Tu ne réponds jamais juste avec du texte quand un tool est disponible pour la tâche."
)

PROMPT_ANALYSE = """Évalue le matching entre ce CV et cette offre d'emploi.

EXTRAITS CV :
{extraits_cv}

OFFRE :
Titre : {titre}
Compétences requises : {competences}
Description : {description}

RÈGLES :
- Base-toi UNIQUEMENT sur les extraits CV fournis.
- N'invente aucune compétence absente du CV.
- decision = "ACCEPTÉ" si le CV correspond bien au poste.
- decision = "REFUSÉ" si le métier est sans rapport.
- decision = "JE NE SAIS PAS" si correspondance partielle ou incertaine.
- score = nombre entier entre 0 et 100 représentant la compatibilité.

Réponds UNIQUEMENT avec ce JSON (rien d'autre) :
{{"points_forts":["..."],"points_manquants":["..."],"score":0,"decision":"ACCEPTÉ","explication":"..."}}""".strip()


@tool
def ecrire_fichier_texte(path: str, contenu: str) -> str:
    """Crée ou remplace un fichier texte."""
    chemin = Path(path)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return f"Fichier écrit : {chemin}"


@tool
def ajouter_fichier_texte(path: str, contenu: str) -> str:
    """Ajoute du texte à la fin d’un fichier texte."""
    chemin = Path(path)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "a", encoding="utf-8") as f:
        f.write(contenu)
    return f"Fichier mis à jour : {chemin}"


@tool
def lire_fichier_texte(path: str) -> str:
    """Lit le contenu d’un fichier texte s’il existe."""
    chemin = Path(path)
    if not chemin.exists():
        return ""
    return chemin.read_text(encoding="utf-8")


@tool
def enregistrer_detection_offre(
    titre: str,
    entreprise: str,
    lieu: str,
    contrat: str,
    salaire: str,
    url: str,
    score_rag: float,
    score_llm: float,
    score_final: float,
    decision: str,
    explication: str,
    fichier_detail: str,
    fichier_index: str,
) -> str:
    """Enregistre une offre détectée dans les fichiers de sortie."""
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    contenu = (
        f"OFFRE DÉTECTÉE\n{'='*78}\n"
        f"Date détection : {horodatage}\n"
        f"Poste         : {titre}\n"
        f"Entreprise    : {entreprise}\n"
        f"Lieu          : {lieu}\n"
        f"Contrat       : {contrat}\n"
        f"Salaire       : {salaire}\n"
        f"URL           : {url}\n"
        f"Score RAG     : {float(score_rag):.3f}\n"
        f"Score LLM     : {float(score_llm):.3f}\n"
        f"Score final   : {float(score_final):.3f}\n"
        f"Décision      : {decision}\n"
        f"Explication   : {explication}\n"
    )
    Path(fichier_detail).parent.mkdir(parents=True, exist_ok=True)
    Path(fichier_detail).write_text(contenu, encoding="utf-8")
    resume = (
        f"[{horodatage}] Poste={titre} | Entreprise={entreprise} | "
        f"ScoreRAG={float(score_rag):.3f} | ScoreLLM={float(score_llm):.3f} | "
        f"ScoreFinal={float(score_final):.3f} | Décision={decision}\n"
    )
    Path(fichier_index).parent.mkdir(parents=True, exist_ok=True)
    with open(fichier_index, "a", encoding="utf-8") as f:
        f.write(resume)
    return f"Offre enregistrée : {fichier_detail}"


@tool
def envoyer_notification(titre: str, entreprise: str, score_final: float, decision: str, fichier_log: str) -> str:
    """Enregistre une notification dans le fichier log."""
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = (
        f"[{horodatage}] ALERTE | {titre} | {entreprise} | "
        f"score_final={float(score_final):.2f} | décision={decision}"
    )
    Path(fichier_log).parent.mkdir(parents=True, exist_ok=True)
    with open(fichier_log, "a", encoding="utf-8") as f:
        f.write(message + "\n")
    print("\n" + "!" * 78)
    print(f"  {message}")
    print("!" * 78)
    return "Notification envoyée"


@tool
def creer_note_agent(
    titre: str,
    entreprise: str,
    score_rag: float,
    score_final: float,
    decision: str,
    explication: str,
    url: str,
    fichier_sortie: str,
) -> str:
    """Crée une note agent pour l’offre détectée."""
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    contenu = (
        f"NOTE DE VEILLE AGENT\n{'='*60}\n"
        f"Date       : {horodatage}\n"
        f"Poste      : {titre}\n"
        f"Entreprise : {entreprise}\n"
        f"Score RAG  : {float(score_rag):.3f}\n"
        f"Score final: {float(score_final):.3f}\n"
        f"Décision   : {decision}\n"
        f"Explication: {explication}\n"
        f"URL        : {url}\n"
    )
    Path(fichier_sortie).parent.mkdir(parents=True, exist_ok=True)
    Path(fichier_sortie).write_text(contenu, encoding="utf-8")
    return f"Note agent créée : {fichier_sortie}"


def verifier_ollama() -> bool:
    url = f"{config.URL_OLLAMA.rstrip('/')}/api/tags"
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        modeles = [m.get("name") for m in data.get("models", []) if m.get("name")]
        if not modeles:
            print("  ERREUR : Ollama n'a retourné aucun modèle")
            return False
        print("  Ollama OK — modèles détectés :")
        for modele in modeles[:5]:
            print(f"    - {modele}")
        print(f"  Modèle utilisé : {config.MODELE_LLM}")
        return True
    except Exception:
        print("  ERREUR : Ollama n'est pas disponible")
        return False


def creer_llm_analyse() -> ChatOllama:
    return ChatOllama(
        model=config.MODELE_LLM,
        base_url=config.URL_OLLAMA.rstrip("/"),
        temperature=0.1,
        num_predict=1200,
        format="json",
    )


def creer_llm_agent() -> ChatOllama:
    return ChatOllama(
        model=config.MODELE_LLM,
        base_url=config.URL_OLLAMA.rstrip("/"),
        temperature=0.1,
        num_predict=1200,
    )


def creer_llm() -> ChatOllama:
    return creer_llm_analyse()


def creer_agent_llm():
    llm_agent = creer_llm_agent()
    tools = [
        ecrire_fichier_texte,
        ajouter_fichier_texte,
        lire_fichier_texte,
        enregistrer_detection_offre,
        envoyer_notification,
        creer_note_agent,
    ]
    return create_react_agent(model=llm_agent, tools=tools, prompt=SYSTEM_PROMPT)


def _reparer_json_tronque(texte: str) -> str:
    texte = texte.rstrip()
    nb_guillemets = texte.count('"') - texte.count('\\"')
    if nb_guillemets % 2 != 0:
        texte += '"'
    pile = []
    in_string = False
    i = 0
    while i < len(texte):
        c = texte[i]
        if c == '\\' and in_string:
            i += 2
            continue
        if c == '"':
            in_string = not in_string
        elif not in_string:
            if c in '{[':
                pile.append('}' if c == '{' else ']')
            elif c in '}]':
                if pile and pile[-1] == c:
                    pile.pop()
        i += 1
    texte += "".join(reversed(pile))
    return texte


def _extraire_champ_regex(texte: str, champ: str) -> str | None:
    m = re.search(rf'"{champ}"\s*:\s*"([^"]*)"', texte, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(rf'"{champ}"\s*:\s*([0-9]+(?:\.[0-9]+)?)', texte, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _extraire_liste_regex(texte: str, champ: str) -> list[str]:
    m = re.search(rf'"{champ}"\s*:\s*\[([^\]]*)\]', texte, re.DOTALL)
    if not m:
        return []
    return re.findall(r'"([^"]+)"', m.group(1))


def _extraire_json(texte: str) -> dict[str, Any]:
    texte = (texte or "").strip()
    if not texte:
        return {}
    try:
        return json.loads(texte)
    except Exception:
        pass
    match = re.search(r"\{.*\}", texte, flags=re.DOTALL)
    if match:
        bloc = match.group(0)
        try:
            return json.loads(bloc)
        except Exception:
            try:
                return json.loads(_reparer_json_tronque(bloc))
            except Exception:
                pass
            resultat = {}
            for champ in ["score", "decision", "explication"]:
                val = _extraire_champ_regex(bloc, champ)
                if val is not None:
                    resultat[champ] = val
            resultat["points_forts"] = _extraire_liste_regex(bloc, "points_forts")
            resultat["points_manquants"] = _extraire_liste_regex(bloc, "points_manquants")
            if resultat:
                return resultat
    print(f"  [LLM] WARN : réponse non parsable ({len(texte)} chars) : {texte[:200]!r}")
    return {}


def _normaliser_decision(decision: str) -> str:
    decision = (decision or "").upper().strip()
    if "ACCEPT" in decision:
        return config.DECISION_ACCEPTE
    if "REFUS" in decision:
        return config.DECISION_REFUSE
    return config.DECISION_NSP


def _inferer_decision_depuis_score(score: float) -> str:
    if score >= 65:
        return config.DECISION_ACCEPTE
    if score <= 30:
        return config.DECISION_REFUSE
    return config.DECISION_NSP


def analyser_offre(llm: ChatOllama, extraits_cv: list[str], offre: dict) -> dict[str, Any]:
    extraits_cv = [str(x).strip() for x in (extraits_cv or []) if str(x).strip()]
    extraits_courts = [x[:300] for x in extraits_cv[:3]]
    extraits_formates = "\n---\n".join(extraits_courts) if extraits_courts else "Aucun extrait CV disponible."
    competences_str = ", ".join(offre.get("competences", [])) or "Non précisées"
    description_courte = (offre.get("description") or "")[:600]

    prompt = PROMPT_ANALYSE.format(
        extraits_cv=extraits_formates,
        titre=offre.get("titre", ""),
        competences=competences_str,
        description=description_courte,
    )

    print(f"  Appel au LLM via Ollama ({config.MODELE_LLM})...")
    reponse = llm.invoke(prompt)
    contenu = reponse.content if hasattr(reponse, "content") else str(reponse)
    donnees = _extraire_json(contenu)

    score_raw = donnees.get("score", None)
    score = 0.0
    if score_raw is not None:
        try:
            score = float(score_raw)
        except Exception:
            score = 0.0
    score = max(0.0, min(100.0, score))

    decision_brute = donnees.get("decision", "")
    decision = _normaliser_decision(decision_brute)

    if not donnees or (decision == config.DECISION_NSP and score_raw is None):
        print("  [LLM] WARN : JSON vide — score_llm forcé à 0")
        score = 0.0
    elif decision == config.DECISION_NSP and score > 0 and not decision_brute.strip():
        decision = _inferer_decision_depuis_score(score)
        print(f"  [LLM] Decision inférée depuis score ({score:.0f}) → {decision}")

    explication = (donnees.get("explication") or "").strip() or "Analyse sans explication exploitable."
    points_forts = donnees.get("points_forts", [])
    if not isinstance(points_forts, list):
        points_forts = []
    points_manquants = donnees.get("points_manquants", [])
    if not isinstance(points_manquants, list):
        points_manquants = []

    texte_analyse = " ".join(extraits_cv).lower()
    offre_texte = " ".join([
        offre.get("titre", ""),
        " ".join(offre.get("competences", []) or []),
        offre.get("description", ""),
    ]).lower()

    famille_foot = any(x in offre_texte for x in ["football", "footballeur", "attaquant", "match"])
    famille_data = any(x in texte_analyse for x in ["python", "sql", "machine learning", "data", "pandas", "scikit"])
    if famille_foot and famille_data and decision == config.DECISION_ACCEPTE:
        decision = config.DECISION_REFUSE
        score = min(score, 20.0)
        explication = "Le CV est data/informatique, l'offre est sportive. Similarité trompeuse."

    print(f"  [LLM] score={score:.0f}/100 | decision={decision} | forts={len(points_forts)} | manquants={len(points_manquants)}")

    return {
        "reponse_complete": contenu,
        "decision": decision,
        "explication": explication,
        "score_llm": score / 100.0,
        "points_forts": points_forts,
        "points_manquants": points_manquants,
    }


def _taille_fichier(path: str) -> int:
    chemin = Path(path)
    if not chemin.exists():
        return -1
    try:
        return chemin.stat().st_size
    except Exception:
        return -1


def _executer_detection_directe(
    offre: dict,
    score_rag: float,
    score_llm: float,
    score_final: float,
    decision: str,
    explication: str,
    fichier_detail: str,
    fichier_index: str,
    fichier_note: str,
    fichier_log: str,
    avant_index: int,
    avant_log: int,
) -> list[str]:
    actions: list[str] = []

    detail_manquant = not Path(fichier_detail).exists() or Path(fichier_detail).stat().st_size == 0
    index_non_mis_a_jour = _taille_fichier(fichier_index) <= avant_index

    if detail_manquant or index_non_mis_a_jour:
        enregistrer_detection_offre.invoke({
            "titre": offre.get("titre", ""),
            "entreprise": offre.get("entreprise", ""),
            "lieu": offre.get("lieu", ""),
            "contrat": offre.get("contrat", ""),
            "salaire": offre.get("salaire", ""),
            "url": offre.get("url", ""),
            "score_rag": float(score_rag),
            "score_llm": float(score_llm),
            "score_final": float(score_final),
            "decision": decision,
            "explication": explication,
            "fichier_detail": fichier_detail,
            "fichier_index": fichier_index,
        })
        actions.append("enregistrer_detection_offre")

    if _taille_fichier(fichier_log) <= avant_log:
        envoyer_notification.invoke({
            "titre": offre.get("titre", ""),
            "entreprise": offre.get("entreprise", ""),
            "score_final": float(score_final),
            "decision": decision,
            "fichier_log": fichier_log,
        })
        actions.append("envoyer_notification")

    note_manquante = not Path(fichier_note).exists() or Path(fichier_note).stat().st_size == 0
    if note_manquante:
        creer_note_agent.invoke({
            "titre": offre.get("titre", ""),
            "entreprise": offre.get("entreprise", ""),
            "score_rag": float(score_rag),
            "score_final": float(score_final),
            "decision": decision,
            "explication": explication,
            "url": offre.get("url", ""),
            "fichier_sortie": fichier_note,
        })
        actions.append("creer_note_agent")

    return actions


def traiter_detection_via_agent(
    agent,
    offre: dict,
    score_rag: float,
    score_llm: float,
    score_final: float,
    decision: str,
    explication: str,
    fichier_detail: str,
    fichier_index: str,
    fichier_note: str,
    fichier_log: str,
) -> str:
    demande = (
        f"Une offre d'emploi a été détectée. Tu dois appeler ces 3 tools dans l'ordre :\n\n"
        f"1. Appelle enregistrer_detection_offre avec :\n"
        f"   titre=\"{offre.get('titre', '')}\"\n"
        f"   entreprise=\"{offre.get('entreprise', '')}\"\n"
        f"   lieu=\"{offre.get('lieu', '')}\"\n"
        f"   contrat=\"{offre.get('contrat', '')}\"\n"
        f"   salaire=\"{offre.get('salaire', '')}\"\n"
        f"   url=\"{offre.get('url', '')}\"\n"
        f"   score_rag={score_rag}\n"
        f"   score_llm={score_llm}\n"
        f"   score_final={score_final}\n"
        f"   decision=\"{decision}\"\n"
        f"   explication=\"{explication}\"\n"
        f"   fichier_detail=\"{fichier_detail}\"\n"
        f"   fichier_index=\"{fichier_index}\"\n\n"
        f"2. Appelle envoyer_notification avec :\n"
        f"   titre=\"{offre.get('titre', '')}\"\n"
        f"   entreprise=\"{offre.get('entreprise', '')}\"\n"
        f"   score_final={score_final}\n"
        f"   decision=\"{decision}\"\n"
        f"   fichier_log=\"{fichier_log}\"\n\n"
        f"3. Appelle creer_note_agent avec :\n"
        f"   titre=\"{offre.get('titre', '')}\"\n"
        f"   entreprise=\"{offre.get('entreprise', '')}\"\n"
        f"   score_rag={score_rag}\n"
        f"   score_final={score_final}\n"
        f"   decision=\"{decision}\"\n"
        f"   explication=\"{explication}\"\n"
        f"   url=\"{offre.get('url', '')}\"\n"
        f"   fichier_sortie=\"{fichier_note}\"\n"
        f"Ne réponds qu'après avoir exécuté les trois tools."
    )

    avant_index = _taille_fichier(fichier_index)
    avant_log = _taille_fichier(fichier_log)
    contenu = ""

    try:
        resultat = agent.invoke({"messages": [{"role": "user", "content": demande}]})
        messages = resultat.get("messages", []) if isinstance(resultat, dict) else []
        if messages:
            dernier = messages[-1]
            brut = getattr(dernier, "content", str(dernier))
            contenu = brut if isinstance(brut, str) else str(brut)
    except Exception as exc:
        contenu = f"Erreur agent: {exc}"

    actions = _executer_detection_directe(
        offre=offre,
        score_rag=score_rag,
        score_llm=score_llm,
        score_final=score_final,
        decision=decision,
        explication=explication,
        fichier_detail=fichier_detail,
        fichier_index=fichier_index,
        fichier_note=fichier_note,
        fichier_log=fichier_log,
        avant_index=avant_index,
        avant_log=avant_log,
    )

    if actions:
        print(f"  [Agent] Fallback écriture directe : {', '.join(actions)}")

    return contenu or "Détection traitée"
