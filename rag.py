from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

import chromadb
import pdfplumber
from chromadb.utils import embedding_functions
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config

def _normaliser_texte(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", (texte or "").lower())
    texte = "".join(ch for ch in texte if not unicodedata.combining(ch))
    texte = texte.replace("–", " ").replace("—", " ").replace("/", " ")
    texte = re.sub(r"[^a-z0-9+#.\-\s]", " ", texte)
    texte = re.sub(r"\s+", " ", texte).strip()
    return texte

def _tokeniser(texte: str) -> list[str]:
    """Tous les tokens >= 3 chars, sans liste de stop words."""
    texte = _normaliser_texte(texte)
    return re.findall(r"[a-z0-9][a-z0-9+.#\-]{2,}", texte)

def _extraire_mots_cles(texte: str, limite: int = 25) -> list[str]:
    tokens = _tokeniser(texte)
    compteur = Counter(t for t in tokens if len(t) >= 4)
    return [mot for mot, _ in compteur.most_common(limite)]

def _extraire_phrases_competences(competences: list[str]) -> list[str]:
    return [
        c for c in (_normaliser_texte(comp) for comp in competences)
        if c and len(c) >= 2
    ]

def _ratio_presence_tokens(tokens_requis: list[str], tokens_doc: set[str]) -> float:
    if not tokens_requis:
        return 0.0
    return sum(1 for t in tokens_requis if t in tokens_doc) / len(set(tokens_requis))

def _ratio_presence_phrases(phrases_requises: list[str], doc_norm: str) -> float:
    if not phrases_requises:
        return 0.0
    return sum(1 for p in phrases_requises if p and p in doc_norm) / len(set(phrases_requises))

def _segmenter_description(description: str) -> list[str]:
    description = (description or "").strip()
    if not description:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max(300, config.DESCRIPTION_MAX_CHARS_REQUETE // max(1, config.NB_SEGMENTS_DESCRIPTION)),
        chunk_overlap=60,
        separators=[". ", "\n", ", ", " "],
    )
    segments = splitter.split_text(description[:config.DESCRIPTION_MAX_CHARS_REQUETE])
    return [s.strip() for s in segments if s.strip()][: config.NB_SEGMENTS_DESCRIPTION]

SECTIONS_CV = {
    "competences": [
        "competence", "competences", "skills", "skill", "techniques",
        "technologie", "technologies", "outils", "tools", "langages",
        "languages", "maitrise", "expertise", "savoir-faire",
    ],
    "experiences": [
        "experience", "experiences", "parcours", "professionnel",
        "emploi", "poste", "mission", "missions", "projet", "projets",
        "stage", "stages", "travail", "career", "work", "history",
    ],
    "formation": [
        "formation", "formations", "education", "diplome", "diplomes",
        "etude", "etudes", "scolarite", "universite", "ecole", "cursus",
        "bac", "master", "licence", "doctorat", "certification",
    ],
    "profil": [
        "profil", "resume", "summary", "objectif", "presentation",
        "about", "apropos", "introduction",
    ],
}

def _detecter_section(ligne: str) -> str | None:
    """Retourne le nom de la section si la ligne est un titre de section CV."""
    ligne_norm = _normaliser_texte(ligne).strip()
    if len(ligne_norm) > 60:
        return None
    for section, mots in SECTIONS_CV.items():
        for mot in mots:
            if mot in ligne_norm.split():
                return section
    return None

def _extraire_tableaux_page(page) -> str:
    """Extrait le contenu des tableaux d'une page PDF."""
    lignes_tableau = []
    try:
        tableaux = page.extract_tables()
        for tableau in (tableaux or []):
            for ligne in (tableau or []):
                cellules = [str(c).strip() for c in (ligne or []) if c and str(c).strip()]
                if cellules:
                    lignes_tableau.append(" | ".join(cellules))
    except Exception:
        pass
    return "\n".join(lignes_tableau)

def _extraire_texte_layout(page) -> str:
    """
    Extrait le texte en tenant compte des colonnes (CV deux colonnes très courant).
    Découpe la page en deux zones verticales et lit chaque zone séparément.
    """
    try:
        largeur = float(page.width)
        textes_colonnes = []
        for fraction_debut, fraction_fin in [(0, 0.52), (0.48, 1.0)]:
            x0 = largeur * fraction_debut
            x1 = largeur * fraction_fin
            zone = page.within_bbox((x0, 0, x1, page.height))
            texte_zone = zone.extract_text(x_tolerance=3, y_tolerance=3)
            if texte_zone and texte_zone.strip():
                textes_colonnes.append(texte_zone.strip())
        if textes_colonnes:
            return "\n".join(textes_colonnes)
    except Exception:
        pass
    try:
        return page.extract_text(x_tolerance=3, y_tolerance=3) or ""
    except Exception:
        return ""

def lire_pdf(chemin_pdf: Path) -> str:
    """
    Extraction maximale du PDF :
    1. Texte standard page par page
    2. Layout colonnes (CV deux colonnes)
    3. Tableaux (listes de compétences souvent en tableau)
    4. Extraction mot par mot via bounding boxes
    Fusion intelligente : on garde le contenu le plus riche
    et on n'ajoute un bloc supplémentaire que s'il apporte
    de nouveaux tokens.
    """
    blocs = []

    with pdfplumber.open(chemin_pdf) as pdf:
        nb_pages = len(pdf.pages)
        print(f"    → {nb_pages} page(s) détectée(s)")

        for page in pdf.pages:
            blocs_page = []

            try:
                texte_std = page.extract_text(x_tolerance=3, y_tolerance=3)
                if texte_std and texte_std.strip():
                    blocs_page.append(texte_std.strip())
            except Exception:
                pass

            texte_layout = _extraire_texte_layout(page)
            if texte_layout and texte_layout.strip():
                if not blocs_page or len(texte_layout) > len(blocs_page[0]) * 1.1:
                    blocs_page.append(texte_layout)

            texte_tableaux = _extraire_tableaux_page(page)
            if texte_tableaux.strip():
                blocs_page.append(texte_tableaux)

            try:
                mots = page.extract_words(
                    x_tolerance=5,
                    y_tolerance=5,
                    keep_blank_chars=False,
                    use_text_flow=True,
                )
                if mots:
                    texte_mots = " ".join(m["text"] for m in mots if m.get("text"))
                    if texte_mots.strip():
                        blocs_page.append(texte_mots.strip())
            except Exception:
                pass

            if blocs_page:

                blocs_page_tries = sorted(blocs_page, key=len, reverse=True)
                texte_fusion = blocs_page_tries[0]
                for bloc in blocs_page_tries[1:]:
                    mots_fusion = set(_tokeniser(texte_fusion))
                    mots_bloc = set(_tokeniser(bloc))
                    nouveaux = mots_bloc - mots_fusion
                    if len(nouveaux) >= 5:
                        texte_fusion += "\n" + bloc
                blocs.append(texte_fusion)

    return "\n\n".join(blocs)

def charger_cvs() -> dict:
    cvs = {}
    pdfs = list(config.DOSSIER_CVS.glob("*.pdf"))

    if not pdfs:
        print("  ERREUR : Aucun PDF dans le dossier 'cvs/'")
        print("  → Copiez vos PDF dans le dossier 'cvs/'")
        return {}

    print(f"\n[ÉTAPE 1] Lecture de {len(pdfs)} CV(s) PDF")
    print("-" * 45)

    for pdf in pdfs:
        print(f"  Lecture : {pdf.name}")
        texte = lire_pdf(pdf)
        cvs[pdf.stem] = texte
        nb_tokens = len(set(_tokeniser(texte)))
        print(f"    → {len(texte)} caractères extraits | ~{nb_tokens} tokens uniques")

    return cvs

def _detecter_blocs_sections(texte: str) -> dict[str, str]:
    """
    Découpe le texte CV en blocs par section détectée.
    Retourne { "experiences": "...", "competences": "...", ... }
    """
    lignes = texte.split("\n")
    blocs: dict[str, list[str]] = {"global": []}
    section_courante = "global"

    for ligne in lignes:
        section = _detecter_section(ligne)
        if section:
            section_courante = section
            if section not in blocs:
                blocs[section] = []
        blocs.setdefault(section_courante, []).append(ligne)

    return {
        section: "\n".join(lignes_section).strip()
        for section, lignes_section in blocs.items()
        if "\n".join(lignes_section).strip()
    }

def decouper_texte(texte: str, nom_cv: str) -> list:
    """
    Chunks généreux (500 chars, 120 overlap) pour maximiser la couverture.
    Chunks dédiés par section détectée (compétences, expériences, formation).
    Chunk résumé dense (début + fin du CV).
    """

    splitter_std = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=120,
        separators=["\n\n", "\n", ". ", ", ", " ", ""],
    )
    chunks_standard = splitter_std.create_documents(
        texts=[texte],
        metadatas=[{"source": nom_cv, "type": "standard", "index": i}
                   for i in range(9999)],
    )

    for i, c in enumerate(chunks_standard):
        c.metadata["index"] = i

    chunks_sections = []
    blocs = _detecter_blocs_sections(texte)
    splitter_sec = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=80,
        separators=["\n\n", "\n", ". ", ", ", " ", ""],
    )
    idx_sec = 0
    for section, contenu in blocs.items():
        if section == "global" or len(contenu) < 30:
            continue
        sous_chunks = splitter_sec.create_documents(
            texts=[contenu],
            metadatas=[{"source": nom_cv, "type": f"section_{section}", "index": idx_sec + j}
                       for j in range(9999)],
        )
        for j, c in enumerate(sous_chunks):
            c.metadata["index"] = idx_sec + j
        idx_sec += len(sous_chunks)
        chunks_sections.extend(sous_chunks)

    debut = texte[:1500].strip()
    fin = texte[-1500:].strip() if len(texte) > 3000 else ""
    resume_dense = (debut + ("\n\n" + fin if fin else "")).strip()
    chunks_resume = []
    if resume_dense:
        sous_chunks_r = splitter_std.create_documents(
            texts=[resume_dense],
            metadatas=[{"source": nom_cv, "type": "resume_dense", "index": idx_sec + j}
                       for j in range(9999)],
        )
        for j, c in enumerate(sous_chunks_r):
            c.metadata["index"] = idx_sec + j
        chunks_resume.extend(sous_chunks_r)

    tous = chunks_standard + chunks_sections + chunks_resume
    print(
        f"    → {len(chunks_standard)} standard + "
        f"{len(chunks_sections)} sections + "
        f"{len(chunks_resume)} résumé = "
        f"{len(tous)} vecteurs total"
    )
    return tous

def construire_rag(cvs: dict):
    print(f"\n[ÉTAPE 2] Construction du RAG (ChromaDB + Embeddings)")
    print("-" * 45)

    print(f"  Chargement du modèle d'embedding : {config.MODELE_EMBEDDING}")
    fn_embedding = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=config.MODELE_EMBEDDING
    )

    client = chromadb.PersistentClient(path=config.DOSSIER_CHROMA)

    try:
        client.delete_collection("cvs_collection")
        print("  Ancienne collection supprimée (nouveau départ propre)")
    except Exception:
        pass

    collection = client.create_collection(
        name="cvs_collection",
        embedding_function=fn_embedding,
        metadata={"hnsw:space": "cosine"},
    )

    total_chunks = 0
    for nom_cv, texte_cv in cvs.items():
        print(f"\n  Indexation : {nom_cv}")
        chunks = decouper_texte(texte_cv, nom_cv)

        textes = [chunk.page_content for chunk in chunks]

        ids = [
            f"{nom_cv}__{chunk.metadata.get('type','std')}__{chunk.metadata.get('index', i)}"
            for i, chunk in enumerate(chunks)
        ]
        metas = [chunk.metadata for chunk in chunks]

        taille_lot = 500
        for debut in range(0, len(textes), taille_lot):
            fin_lot = debut + taille_lot
            collection.add(
                documents=textes[debut:fin_lot],
                ids=ids[debut:fin_lot],
                metadatas=metas[debut:fin_lot],
            )

        total_chunks += len(chunks)
        print(f"    → {len(chunks)} vecteurs stockés dans ChromaDB")

    print(f"\n  RAG prêt : {total_chunks} vecteurs au total")
    return collection

def construire_requete_offre(offre: dict | str) -> dict:
    if isinstance(offre, str):
        offre = {"titre": "", "description": offre, "competences": []}

    titre = (offre.get("titre") or "").strip()
    entreprise = (offre.get("entreprise") or "").strip()
    lieu = (offre.get("lieu") or "").strip()
    contrat = (offre.get("contrat") or "").strip()
    description = (offre.get("description") or "").strip()
    competences = [str(c).strip() for c in (offre.get("competences") or []) if str(c).strip()]

    description_longue = description[: config.DESCRIPTION_MAX_CHARS_REQUETE]
    mots_cles = _extraire_mots_cles(description_longue)
    segments_description = _segmenter_description(description_longue)

    partie_competences = ", ".join(competences)
    partie_mots_cles = ", ".join(mots_cles)

    requete_titre = f"{titre}. {titre}".strip()
    requete_competences = (
        f"{titre}. Compétences requises : {partie_competences}. "
        f"Mots-clés : {partie_mots_cles}."
    ).strip()
    requete_complete = (
        f"Titre poste : {titre}. "
        f"Entreprise : {entreprise}. Lieu : {lieu}. Contrat : {contrat}. "
        f"Compétences requises : {partie_competences}. "
        f"Description : {description_longue}"
    ).strip()

    requete_experiences = (
        f"Expérience professionnelle pour le poste : {titre}. "
        f"Missions : {description_longue[:600]}"
    ).strip()

    titre_tokens = [t for t in _tokeniser(titre) if len(t) >= 3]
    competence_tokens = [t for comp in competences for t in _tokeniser(comp)]
    competence_phrases = _extraire_phrases_competences(competences)
    mots_cles_tokens = [t for t in mots_cles if len(t) >= 3]

    termes_critiques = []
    for comp in competences[:12]:
        termes_critiques.extend(_tokeniser(comp))
    termes_critiques.extend(titre_tokens[:6])
    termes_critiques = list(dict.fromkeys([t for t in termes_critiques if len(t) >= 3]))

    termes_domaine = _extraire_mots_cles(
        " ".join([titre, partie_competences, description_longue[:800]]),
        limite=30,
    )

    return {
        "titre": requete_titre or description_longue,
        "competences": requete_competences or requete_complete,
        "complete": requete_complete or requete_competences or description_longue,
        "experiences": requete_experiences,
        "segments": segments_description,
        "description_longue": description_longue,
        "mots_cles": mots_cles,
        "titre_tokens": titre_tokens,
        "competence_tokens": competence_tokens,
        "competence_phrases": competence_phrases,
        "mots_cles_tokens": mots_cles_tokens,
        "termes_critiques": termes_critiques,
        "termes_domaine": termes_domaine,
    }

def _distance_vers_similarite(distance: float) -> float:
    """
    ChromaDB espace cosine : distance ∈ [0, 2], 0 = identique.
    sim = 1 - distance (approximation de la similarité cosinus normalisée).
    """
    try:
        sim = 1.0 - float(distance)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, sim))

def _score_moyen_top3(distances: list[float]) -> float:
    if not distances:
        return 0.0
    sims = sorted((_distance_vers_similarite(d) for d in distances), reverse=True)
    top = sims[:3]
    return sum(top) / len(top)

def _score_meilleur_chunk(distances: list[float]) -> float:
    if not distances:
        return 0.0
    return max(_distance_vers_similarite(d) for d in distances)

def _score_median(distances: list[float]) -> float:
    if not distances:
        return 0.0
    sims = sorted([_distance_vers_similarite(d) for d in distances])
    return sims[len(sims) // 2]

def _query_collection(collection, texte: str, n_results: int):
    texte = str(texte or "").strip()
    if not texte:
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
    try:
        return collection.query(
            query_texts=[texte],
            n_results=n_results,
            include=["documents", "distances", "metadatas"],
        )
    except Exception:
        try:
            return collection.query(
                query_texts=[texte],
                n_results=max(1, n_results // 2),
                include=["documents", "distances", "metadatas"],
            )
        except Exception:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

def _fusionner_resultats(*resultats):
    documents, metadatas, distances = [], [], []
    deja_vus = set()

    for resultat in resultats:
        if not resultat:
            continue
        docs  = (resultat.get("documents")  or [[]])[0]
        metas = (resultat.get("metadatas")  or [[]])[0]
        dists = (resultat.get("distances")  or [[]])[0]

        for doc, meta, dist in zip(docs, metas, dists):
            meta = meta or {}
            cle = (meta.get("source_cv"), meta.get("type"), meta.get("index"))
            if cle in deja_vus:
                continue
            deja_vus.add(cle)
            documents.append(doc)
            metadatas.append(meta)
            distances.append(dist)

    triplets = sorted(
        zip(documents, metadatas, distances),
        key=lambda x: _distance_vers_similarite(x[2]),
        reverse=True,
    )
    n = config.NB_CHUNKS_RAG
    return (
        [t[0] for t in triplets[:n]],
        [t[1] for t in triplets[:n]],
        [t[2] for t in triplets[:n]],
    )

def _calculer_preuves_lexicales(documents: list[str], requetes: dict) -> dict:
    """Couverture lexicale brute entre chunks CV et tokens de l'offre."""
    titre_tokens      = requetes["titre_tokens"]
    competence_tokens = requetes["competence_tokens"]
    competence_phrases = requetes["competence_phrases"]
    mots_cles_tokens  = requetes["mots_cles_tokens"]
    termes_critiques  = requetes["termes_critiques"]
    termes_domaine    = requetes["termes_domaine"]

    couverture_titre        = 0.0
    couverture_competences  = 0.0
    couverture_mots_cles    = 0.0
    couverture_domaine      = 0.0
    couverture_termes_critiques = 0.0
    support_chunks = 0

    for doc in documents:
        doc_norm   = _normaliser_texte(doc)
        tokens_doc = set(_tokeniser(doc))

        titre_cov = _ratio_presence_tokens(titre_tokens, tokens_doc)
        comp_cov  = max(
            _ratio_presence_tokens(competence_tokens, tokens_doc),
            _ratio_presence_phrases(competence_phrases, doc_norm),
        )
        mots_cov     = _ratio_presence_tokens(mots_cles_tokens, tokens_doc)
        domaine_cov  = _ratio_presence_tokens(termes_domaine, tokens_doc)
        critiques_cov = _ratio_presence_tokens(termes_critiques, tokens_doc)

        preuve_locale = max(comp_cov, titre_cov, domaine_cov, critiques_cov)
        if preuve_locale >= 0.15:
            support_chunks += 1

        couverture_titre       = max(couverture_titre,       titre_cov)
        couverture_competences = max(couverture_competences, comp_cov)
        couverture_mots_cles   = max(couverture_mots_cles,   mots_cov)
        couverture_domaine     = max(couverture_domaine,     domaine_cov)
        couverture_termes_critiques = max(couverture_termes_critiques, critiques_cov)

    nb_docs = max(1, len(documents))
    support_chunks_ratio = support_chunks / nb_docs

    score_lexical = (
        0.20 * couverture_titre
        + 0.40 * couverture_competences
        + 0.15 * couverture_mots_cles
        + 0.15 * couverture_domaine
        + 0.10 * support_chunks_ratio
    )

    aucune_preuve_forte = (
        couverture_competences < config.SEUIL_COUVERTURE_COMPETENCES
        and couverture_domaine  < config.SEUIL_COUVERTURE_DOMAINE
        and couverture_titre    < config.SEUIL_COUVERTURE_TITRE
    )
    aucun_terme_critique = bool(termes_critiques) and couverture_termes_critiques == 0.0

    return {
        "couverture_titre":        couverture_titre,
        "couverture_competences":  couverture_competences,
        "couverture_mots_cles":    couverture_mots_cles,
        "couverture_domaine":      couverture_domaine,
        "couverture_termes_critiques": couverture_termes_critiques,
        "support_chunks":          support_chunks_ratio,
        "score_lexical":           max(0.0, min(1.0, score_lexical)),
        "aucune_preuve_forte":     aucune_preuve_forte,
        "aucun_terme_critique":    aucun_terme_critique,
        "role_family_match":       False,
    }

def rechercher_cv(collection, offre: dict | str) -> dict:
    requetes = construire_requete_offre(offre)
    nb = config.NB_CHUNKS_RAG

    r_titre   = _query_collection(collection, requetes["titre"],       nb)
    r_comp    = _query_collection(collection, requetes["competences"], nb)
    r_complet = _query_collection(collection, requetes["complete"],    nb)
    r_exp     = _query_collection(collection, requetes["experiences"], nb)

    resultats_segments = [
        _query_collection(collection, seg, max(4, nb - 1))
        for seg in requetes["segments"]
    ]

    d_titre   = (r_titre.get("distances")   or [[]])[0]
    d_comp    = (r_comp.get("distances")    or [[]])[0]
    d_complet = (r_complet.get("distances") or [[]])[0]
    d_exp     = (r_exp.get("distances")     or [[]])[0]
    d_segments = []
    for res in resultats_segments:
        d_segments.extend((res.get("distances") or [[]])[0])

    toutes_distances = d_titre + d_comp + d_complet + d_exp + d_segments

    score_titre   = _score_moyen_top3(d_titre)
    score_comp    = _score_moyen_top3(d_comp)
    score_complet = _score_moyen_top3(d_complet)
    score_exp     = _score_moyen_top3(d_exp)
    score_seg     = _score_moyen_top3(d_segments)
    score_best    = _score_meilleur_chunk(toutes_distances)
    score_median  = _score_median(toutes_distances)

    score_semantique = (
        0.15 * score_titre
        + 0.28 * score_comp
        + 0.22 * score_complet
        + 0.15 * score_exp
        + 0.10 * score_seg
        + 0.07 * score_best
        + 0.03 * score_median
    )

    documents, metadatas, distances = _fusionner_resultats(
        r_titre, r_comp, r_complet, r_exp, *resultats_segments
    )

    preuves = _calculer_preuves_lexicales(documents, requetes)
    score_lexical = preuves["score_lexical"]

    score_final = (
        0.55 * score_semantique
        + 0.30 * score_lexical
        + 0.15 * preuves["support_chunks"]
    )

    if preuves["aucune_preuve_forte"]:
        score_final *= 0.45

    if preuves["aucun_terme_critique"]:
        score_final *= 0.55

    if score_semantique >= 0.50 and score_lexical < 0.10:
        score_final = min(score_final, 0.30)

    if preuves["couverture_competences"] < 0.12 and preuves["couverture_titre"] < 0.10:
        score_final *= 0.70

    score_final = max(0.0, min(1.0, score_final))

    print(
        f"  [RAG détail] cosinus={score_semantique:.3f} | "
        f"lexical={score_lexical:.3f} | "
        f"support={preuves['support_chunks']:.2f} | "
        f"final={score_final:.3f}"
    )

    return {
        "chunks":         documents[: config.NB_CHUNKS_ANALYSE_LLM],
        "distances":      distances[: config.NB_CHUNKS_ANALYSE_LLM],
        "metadatas":      metadatas[: config.NB_CHUNKS_ANALYSE_LLM],
        "score":          score_final,
        "score_semantique": score_semantique,
        "score_lexical":  score_lexical,
        "mots_cles":      requetes["mots_cles"],
        "preuves":        preuves,
        "requetes": {
            "titre":       requetes["titre"],
            "competences": requetes["competences"],
            "complete":    requetes["complete"],
            "experiences": requetes["experiences"],
            "segments":    requetes["segments"],
        },
    }
