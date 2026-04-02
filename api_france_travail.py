import requests
import config

def _credentials_disponibles() -> bool:
    """Retourne True si les identifiants France Travail ont été renseignés."""
    return (
        config.FT_CLIENT_ID
        and config.FT_CLIENT_SECRET
        and config.FT_CLIENT_ID != "votre_client_id_ici"
        and config.FT_CLIENT_SECRET != "votre_client_secret_ici"
    )

def obtenir_token() -> str | None:
    """Récupère un token OAuth2 France Travail."""
    if not _credentials_disponibles():
        print("  API France Travail ignorée : client_id / client_secret non renseignés")
        return None

    payload = {
        "grant_type": "client_credentials",
        "client_id": config.FT_CLIENT_ID,
        "client_secret": config.FT_CLIENT_SECRET,
        "scope": "api_offresdemploiv2 o2dsoffre",
    }

    try:
        resp = requests.post(config.URL_TOKEN_FT, data=payload, timeout=10)
    except requests.exceptions.ConnectionError:
        print("  ERREUR : Pas de connexion internet")
        return None

    if resp.status_code != 200:
        print(f"  ERREUR authentification ({resp.status_code})")
        return None

    token = resp.json().get("access_token")
    print("  Token obtenu (valable ~1h)")
    return token

def recuperer_offres(mots_cles: str = None, departement: str = None, nb: int = None) -> list:
    """Récupère les offres depuis l'API France Travail."""
    mots_cles = mots_cles or config.MOTS_CLES_DEFAUT
    departement = departement or config.DEPARTEMENT_DEFAUT
    nb = nb or config.NB_OFFRES

    print("\n[API] Récupération des offres France Travail")
    print("-" * 45)
    print(f"  Mots-clés : '{mots_cles}'  |  Département : {departement}")
    token = obtenir_token()
    if not token:
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    params = {
        "motsCles": mots_cles,
        "departement": departement,
        "range": f"0-{nb - 1}",
        "sort": "1",
    }

    try:
        resp = requests.get(
            config.URL_OFFRES_FT,
            headers=headers,
            params=params,
            timeout=15,
        )
    except requests.exceptions.ConnectionError:
        print("  ERREUR : Pas de connexion internet")
        return []

    if resp.status_code != 200:
        print(f"  ERREUR récupération ({resp.status_code})")
        return []

    brutes = resp.json().get("resultats", [])
    offres = [_formater(o) for o in brutes]
    print(f"  {len(offres)} offre(s) récupérée(s) depuis l'API")
    return offres

OFFRES_TEST = [
    {
        "id": "TEST_001",
        "titre": "Data Scientist — Python & Machine Learning",
        "entreprise": "DataLab Lyon",
        "lieu": "Lyon 3ème (69)",
        "contrat": "CDI",
        "salaire": "42 000 - 52 000 EUR/an",
        "description": (
            "Nous cherchons un Data Scientist maîtrisant Python, "
            "scikit-learn, pandas, et les techniques de Machine Learning "
            "supervisé et non supervisé. Expérience avec les LLMs et "
            "NLP appréciée. Formation Bac+5 Data Science ou équivalent. "
            "Bonne connaissance de SQL et des bases de données."
        ),
        "competences": ["Python", "Machine Learning", "scikit-learn", "SQL", "NLP"],
        "date": "2026-03-27",
        "url": "https://francetravail.fr",
    },
    {
       "id": "TEST_004",
        "titre": "Medecin",
        "entreprise": "RetailData",
        "lieu": "Lyon 2ème (69)",
        "contrat": "CDI",
        "salaire": "30 000 - 36 000 EUR/an",
        "description": (
            "Profil junior accepté (0-2 ans). Missions : operation , "
            "pediatre "
            ""
        ),
        "competences": ["Kubernetes"],
        "date": "2026-03-27",
        "url": "https://francetravail.fr",
    },
    {
        "id": "TEST_003",
        "titre": "Analyste Data Junior — BI & Reporting",
        "entreprise": "RetailData",
        "lieu": "Lyon 2ème (69)",
        "contrat": "CDI",
        "salaire": "30 000 - 36 000 EUR/an",
        "description": (
            "Profil junior accepté (0-2 ans). Missions : extraction SQL, "
            "création de tableaux de bord Power BI, analyse de données retail. "
            "Maîtrise Excel avancé. Formation Master Data ou Statistiques."
        ),
        "competences": ["SQL", "Power BI", "Excel", "Python débutant"],
        "date": "2026-03-27",
        "url": "https://francetravail.fr",
    },
      {
        "id": "TEST_004",
        "titre": "Medecin",
        "entreprise": "RetailData",
        "lieu": "Lyon 2ème (69)",
        "contrat": "CDI",
        "salaire": "30 000 - 36 000 EUR/an",
        "description": (
            "Profil junior accepté (0-2 ans). Missions : operation , "
            "pediatre "
            ""
        ),
        "competences": ["Excel"],
        "date": "2026-03-27",
        "url": "https://francetravail.fr",
    },{
        "id": "TEST_005",
        "titre": "footbaleur",
        "entreprise": "OM",
        "lieu": "Marseille 2ème (13)",
        "contrat": "CDI",
        "salaire": "30 000 - 36 000 EUR/an",
        "description": (
            "Profil expert. Missions : jouer , "
            "attaquant "
            ""
        ),
        "competences": ["Excel"],
        "date": "2026-03-27",
        "url": "https://francetravail.fr",
    },  {
        "id": "TEST_006",
        "titre": "Avocat",
        "entreprise": "barrot",
        "lieu": "Marseille 2ème (13)",
        "contrat": "CDI",
        "salaire": "30 000 - 36 000 EUR/an",
        "description": (
            "Profil expert. Missions : victime , "
            "arnaque "
            ""
        ),
        "competences": ["Anglais"],
        "date": "2026-03-31",
        "url": "https://francetravail.fr",
    }

]

OFFRES_MANUELLES = OFFRES_TEST

def recuperer_offres_manuelles() -> list:
    """Retourne les offres écrites manuellement dans ce fichier."""
    offres = []
    for offre in OFFRES_MANUELLES:
        if _offre_deja_formatee(offre):
            offres.append(offre)
        else:
            offres.append(_formater(offre))

    if offres:
        print(f"  {len(offres)} offre(s) manuelle(s) détectée(s) dans api_france_travail.py")
    return offres

def recuperer_toutes_les_offres(mode_test: bool = False) -> list:
    """
    Retourne les offres à surveiller pour un cycle.

    - mode_test=True  -> seulement les offres manuelles / de test
    - mode_test=False -> API France Travail + offres manuelles
    """
    offres = []

    if not mode_test:
        offres.extend(recuperer_offres())

    if mode_test or config.INCLURE_OFFRES_MANUELLES:
        offres.extend(recuperer_offres_manuelles())

    uniques = {}
    for offre in offres:
        id_offre = offre.get("id") or f"SANS_ID_{len(uniques)+1}"
        uniques[id_offre] = offre

    resultat = list(uniques.values())
    print(f"  Total cycle : {len(resultat)} offre(s) unique(s) à analyser")
    return resultat

def _offre_deja_formatee(offre: dict) -> bool:
    return {"id", "titre", "entreprise", "lieu", "contrat", "salaire", "description", "competences", "date", "url"}.issubset(offre.keys())

def _formater(offre_brute: dict) -> dict:
    """Extrait les champs utiles d'une offre brute API."""
    return {
        "id": offre_brute.get("id", ""),
        "titre": offre_brute.get("intitule", "Sans titre"),
        "entreprise": offre_brute.get("entreprise", {}).get("nom", "Non précisé"),
        "lieu": offre_brute.get("lieuTravail", {}).get("libelle", "Non précisé"),
        "contrat": offre_brute.get("typeContrat", "Non précisé"),
        "salaire": offre_brute.get("salaire", {}).get("libelle", "Non précisé"),
        "description": offre_brute.get("description", ""),
        "competences": [c.get("libelle", "") for c in offre_brute.get("competences", [])],
        "date": offre_brute.get("dateCreation", ""),
        "url": offre_brute.get("origineOffre", {}).get("urlOrigine", ""),
    }
