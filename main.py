import importlib
import sys
import time
import traceback
import webbrowser
from datetime import datetime

import agent_graph
import config
import llm as llm_module
import memoire as mem_module
import rag as rag_module

def afficher_banniere():
    print("\n" + "=" * 70)
    print("  AGENT LOCAL — SURVEILLANCE CV / OFFRES D'EMPLOI")
    print(f"  LLM : {config.MODELE_LLM} via Ollama (local)")
    print(f"  RAG : ChromaDB + {config.MODELE_EMBEDDING}")
    print(f"  Seuil final de détection : {config.SEUIL_DETECTION:.2f}")
    print(f"  Seuil minimal avant LLM  : {config.SEUIL_SIMILARITE:.2f}")
    print(f"  Intervalle de veille     : {config.INTERVALLE_SURVEILLANCE} sec")
    print("  Arrêt manuel : Ctrl + C")
    print("=" * 70)

def titre_safe(texte: str, limite: int = 50) -> str:
    propre = "".join(c for c in texte if c.isalnum() or c in "-_ ").strip()
    propre = propre.replace(" ", "_")
    return (propre or "offre")[:limite]

def envoyer_signal_sonore():
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.Beep(1200, 500)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass

def enregistrer_notification(message: str):
    config.DOSSIER_RESULTATS.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(config.FICHIER_NOTIFICATIONS, "a", encoding="utf-8") as f:
        f.write(f"[{horodatage}] {message}\n")

def notifier_detection(offre: dict, score_rag: float, score_final: float, decision: str):
    message = (
        f"ALERTE | {offre['titre']} | {offre['entreprise']} | "
        f"score_rag={score_rag:.2f} | score_final={score_final:.2f} | décision={decision}"
    )
    print("\n" + "!" * 78)
    print(f"  {message}")
    print("!" * 78)
    envoyer_signal_sonore()
    enregistrer_notification(message)

    if config.OUVRIR_URL_AUTOMATIQUEMENT and offre.get("url"):
        try:
            webbrowser.open(offre["url"])
        except Exception:
            pass

def sauvegarder_offre_detectee(
    offre: dict,
    score_rag: float,
    score_llm: float,
    score_final: float,
    decision: str,
    explication: str,
    reponse_llm: str,
):
    config.DOSSIER_RESULTATS.mkdir(parents=True, exist_ok=True)
    config.DOSSIER_OFFRES_DETECTEES.mkdir(parents=True, exist_ok=True)
    config.DOSSIER_NOTES_AGENT.mkdir(parents=True, exist_ok=True)

    maintenant = datetime.now()
    horodatage = maintenant.strftime("%Y-%m-%d %H:%M:%S")
    nom_fichier = (
        f"{offre.get('id', 'sans_id')}_{maintenant.strftime('%Y%m%d_%H%M%S')}_"
        f"{titre_safe(offre.get('titre', 'offre'))}.txt"
    )
    fichier_detail = config.DOSSIER_OFFRES_DETECTEES / nom_fichier
    fichier_note_agent = config.DOSSIER_NOTES_AGENT / f"note_agent_{nom_fichier}"

    contenu = (
        "OFFRE DÉTECTÉE\n"
        + f"{'='*78}\n"
        + f"Date détection : {horodatage}\n"
        + f"ID            : {offre.get('id', '')}\n"
        + f"Poste         : {offre.get('titre', '')}\n"
        + f"Entreprise    : {offre.get('entreprise', '')}\n"
        + f"Lieu          : {offre.get('lieu', '')}\n"
        + f"Contrat       : {offre.get('contrat', '')}\n"
        + f"Salaire       : {offre.get('salaire', '')}\n"
        + f"URL           : {offre.get('url', '')}\n"
        + f"Score RAG     : {score_rag:.3f}\n"
        + f"Score LLM     : {score_llm:.3f}\n"
        + f"Score final   : {score_final:.3f}\n"
        + f"Décision      : {decision}\n"
        + f"Explication   : {explication}\n\n"
        + f"COMPÉTENCES : {', '.join(offre.get('competences', []))}\n\n"
        + f"DESCRIPTION :\n{offre.get('description', '')}\n\n"
        + f"ANALYSE LLM :\n{reponse_llm}\n"
    )

    with open(fichier_detail, "w", encoding="utf-8") as f:
        f.write(contenu)

    resume = (
        f"[{horodatage}] ID={offre.get('id', '')} | Poste={offre.get('titre', '')} | "
        f"Entreprise={offre.get('entreprise', '')} | ScoreRAG={score_rag:.3f} | "
        f"ScoreLLM={score_llm:.3f} | ScoreFinal={score_final:.3f} | "
        f"Décision={decision} | Fichier={fichier_detail.name}\n"
    )
    with open(config.FICHIER_OFFRES_DETECTEES, "a", encoding="utf-8") as f:
        f.write(resume)

    print(f"  Offre stockée dans : {fichier_detail}")
    print(f"  Index global mis à jour : {config.FICHIER_OFFRES_DETECTEES}")

    try:
        llm_module.creer_note_detection_via_agent(
            offre=offre,
            score_rag=score_rag,
            score_final=score_final,
            decision=decision,
            explication=explication,
            fichier_sortie=str(fichier_note_agent),
        )
        print(f"  Note agent créée via tools : {fichier_note_agent}")
    except Exception as exc:
        print(f"  Note agent non créée (non bloquant) : {exc}")

def charger_offres_depuis_fichier(mode_test: bool = False) -> list[dict]:
    """
    Recharge api_france_travail.py et retourne TOUTES les offres
    (déduplication par ID incluse). Le filtrage "déjà analysé" est
    fait en amont par _filtrer_nouvelles_offres.
    """
    import api_france_travail
    module_api = importlib.reload(api_france_travail)
    return module_api.recuperer_toutes_les_offres(mode_test=mode_test)

def _filtrer_nouvelles_offres(offres: list[dict], ids_deja_traites: set[str]) -> list[dict]:
    """
    Retourne uniquement les offres dont l'ID n'a JAMAIS été traité
    durant ce run (ni dans les cycles précédents du run, ni en mémoire JSON).
    """
    return [o for o in offres if o.get("id") and o["id"] not in ids_deja_traites]

def _ids_depuis_fichier(mode_test: bool = False) -> set[str]:
    """
    Lit le fichier api_france_travail.py (via reload) et retourne
    l'ensemble des IDs actuellement présents — sans analyser.
    Utilisé pendant la veille pour détecter un nouvel ajout.
    """
    try:
        import api_france_travail
        module_api = importlib.reload(api_france_travail)
        offres = module_api.recuperer_toutes_les_offres(mode_test=mode_test)
        return {o["id"] for o in offres if o.get("id")}
    except Exception:
        return set()

def initialiser_agent():
    print("\n[INIT] Vérification d'Ollama...")
    if not llm_module.verifier_ollama():
        raise RuntimeError("Ollama non disponible.")

    cvs = rag_module.charger_cvs()
    if not cvs:
        raise RuntimeError("Aucun CV PDF trouvé dans le dossier cvs/.")

    collection = rag_module.construire_rag(cvs)
    llm = llm_module.creer_llm()
    memoire = mem_module.charger()
    graphe = agent_graph.construire_graphe()

    print(f"\n[INIT] Graphe compilé ({len(graphe.nodes)} nœuds)")
    return collection, llm, memoire, graphe

def traiter_nouvelles_offres(
    offres_nouvelles: list[dict],
    collection,
    llm,
    memoire: dict,
    graphe,
    ids_deja_traites: set[str],
) -> tuple[int, int]:
    """
    Analyse uniquement les offres de la liste (déjà filtrées).
    Met à jour ids_deja_traites en place.
    Retourne (nb_analyses, nb_detections).
    """
    analyses = 0
    detections = 0

    for index, offre in enumerate(offres_nouvelles, start=1):
        id_offre = offre.get("id", "")
        print(f"\n→ Nouvelle offre {index}/{len(offres_nouvelles)} : {offre['titre']}")

        etat_final = agent_graph.analyser_une_offre(
            graphe, offre, collection, llm, memoire
        )

        ids_deja_traites.add(id_offre)

        if etat_final.get("deja_vue"):

            continue

        analyses += 1
        score_rag   = etat_final["score_rag"]
        score_llm   = etat_final["score_llm"]
        score_final = etat_final["score_final"]
        decision    = etat_final["decision"]
        explication = etat_final["explication"]
        reponse_llm = etat_final["reponse_llm"]

        print(
            f"  Score RAG : {score_rag:.2f} | Score LLM : {score_llm:.2f} | "
            f"Score final : {score_final:.2f}"
        )
        print(f"  Décision    : {decision}")
        print(f"  Explication : {explication}")

        detection_valide = (
            decision == config.DECISION_ACCEPTE
            and score_final >= config.SEUIL_DETECTION
            and not mem_module.est_detectee(memoire, id_offre)
        )

        if detection_valide:
            detections += 1
            sauvegarder_offre_detectee(
                offre=offre,
                score_rag=score_rag,
                score_llm=score_llm,
                score_final=score_final,
                decision=decision,
                explication=explication,
                reponse_llm=reponse_llm,
            )
            notifier_detection(offre, score_rag, score_final, decision)
            mem_module.enregistrer_detection(
                memoire,
                offre,
                score_rag=score_rag,
                score_final=score_final,
                decision=decision,
            )

        mem_module.enregistrer(
            memoire,
            offre,
            decision=decision,
            score_rag=score_rag,
            score_final=score_final,
        )

    return analyses, detections

def main(mode_test: bool = False):
    afficher_banniere()
    collection, llm, memoire, graphe = initialiser_agent()

    ids_deja_traites: set[str] = set(memoire.get("offres_vues", []))

    print("\n" + "─" * 78)
    print(f"[DÉMARRAGE] {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("─" * 78)

    try:
        offres_initiales = charger_offres_depuis_fichier(mode_test=mode_test)
        nouvelles = _filtrer_nouvelles_offres(offres_initiales, ids_deja_traites)

        if nouvelles:
            print(f"  {len(nouvelles)} offre(s) à analyser au démarrage.")
            nb_analyses, nb_detections = traiter_nouvelles_offres(
                nouvelles, collection, llm, memoire, graphe, ids_deja_traites
            )
            print(
                f"\n[DÉMARRAGE] Terminé | analyses : {nb_analyses} | "
                f"détections : {nb_detections}"
            )
        else:
            print("  Aucune nouvelle offre à analyser au démarrage.")

    except Exception as exc:
        print(f"\n[ERREUR DÉMARRAGE] {exc}")
        traceback.print_exc()
        enregistrer_notification(f"ERREUR DÉMARRAGE: {exc}")

    print("\n" + "=" * 78)
    print(f"  EN ÉCOUTE — surveillance de api_france_travail.py toutes les "
          f"{config.INTERVALLE_SURVEILLANCE}s")
    print(f"  Ajoutez une offre dans OFFRES_MANUELLES pour la faire analyser.")
    print(f"  Arrêt : Ctrl + C")
    print("=" * 78)

    ids_connus_dans_fichier = {o.get("id") for o in offres_initiales if o.get("id")}

    cycle = 1
    try:
        while config.SURVEILLANCE_ACTIVE:
            time.sleep(config.INTERVALLE_SURVEILLANCE)

            try:

                ids_fichier_maintenant = _ids_depuis_fichier(mode_test=mode_test)

                ids_vraiment_nouveaux = ids_fichier_maintenant - ids_connus_dans_fichier

                if not ids_vraiment_nouveaux:

                    heure = datetime.now().strftime("%H:%M:%S")
                    print(f"  [{heure}] En écoute... (aucune nouvelle offre détectée)", end="\r")
                    continue

                ids_connus_dans_fichier = ids_fichier_maintenant

                offres_toutes = charger_offres_depuis_fichier(mode_test=mode_test)
                offres_nouvelles = [
                    o for o in offres_toutes
                    if o.get("id") in ids_vraiment_nouveaux
                    and o.get("id") not in ids_deja_traites
                ]

                if not offres_nouvelles:
                    continue

                print()
                print("\n" + "─" * 78)
                print(
                    f"[CYCLE {cycle}] {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} — "
                    f"{len(offres_nouvelles)} nouvelle(s) offre(s) détectée(s)"
                )
                print("─" * 78)

                nb_analyses, nb_detections = traiter_nouvelles_offres(
                    offres_nouvelles, collection, llm, memoire, graphe, ids_deja_traites
                )

                print(
                    f"\n[CYCLE {cycle}] Fin | analyses : {nb_analyses} | "
                    f"détections : {nb_detections}"
                )
                print("=" * 78)
                print(f"  EN ÉCOUTE — en attente de nouvelles offres...")
                print("=" * 78)

                cycle += 1

            except Exception as exc:
                print(f"\n[ERREUR VEILLE] {exc}")
                traceback.print_exc()
                enregistrer_notification(f"ERREUR VEILLE cycle {cycle}: {exc}")

    except KeyboardInterrupt:
        print("\n\nArrêt manuel détecté.")
        mem_module.afficher_resume(memoire)

if __name__ == "__main__":
    main(mode_test=False)
