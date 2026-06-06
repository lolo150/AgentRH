# Agent local de surveillance CV / offres d’emploi

Ce projet est un agent local qui surveille des offres d’emploi, les compare automatiquement avec un ou plusieurs CV, puis détecte les offres les plus pertinentes grâce à une combinaison de **RAG**, **ChromaDB**, **embeddings**, **LLM local via Ollama** et **dashboard Streamlit**.

L’objectif est simple : éviter de relire manuellement toutes les offres et faire ressortir automatiquement celles qui correspondent vraiment au profil du candidat.

---

## Fonctionnalités principales

- Récupération d’offres depuis l’API France Travail.
- Possibilité d’ajouter des offres manuellement dans le code pour les tester.
- Lecture de CV au format PDF depuis le dossier `cvs/`.
- Extraction avancée du contenu des CV, y compris texte, colonnes et tableaux.
- Découpage du CV en chunks exploitables pour la recherche sémantique.
- Indexation des CV dans ChromaDB avec le modèle d’embedding `all-MiniLM-L6-v2`.
- Recherche RAG entre une offre et les extraits de CV les plus proches.
- Analyse finale par un LLM local avec Ollama.
- Décision automatique :
  - `ACCEPTÉ`
  - `REFUSÉ`
  - `JE NE SAIS PAS`
- Calcul d’un score final combinant le score RAG et le score LLM.
- Sauvegarde des offres détectées dans des fichiers texte.
- Journal de notifications.
- Mémoire JSON pour éviter de réanalyser plusieurs fois la même offre.
- Dashboard Streamlit pour visualiser les notifications, les offres détectées et l’historique.

---

## Technologies utilisées

- Python
- Ollama
- LangChain
- LangGraph
- ChromaDB
- Sentence Transformers
- Streamlit
- pdfplumber
- API France Travail
- Requests

---

## Structure du projet

```text
.
├── agent_graph.py              # Graphe logique de l'agent : mémoire, RAG, LLM, score final
├── api_france_travail.py       # Récupération des offres via API France Travail ou offres manuelles
├── config.py                   # Paramètres globaux du projet
├── dashboard_offres.py         # Dashboard Streamlit de suivi des offres détectées
├── llm.py                      # Configuration Ollama, prompts, outils agent et analyse LLM
├── main.py                     # Point d'entrée principal de l'application
├── memoire.py                  # Gestion de la mémoire JSON des offres vues/détectées
├── rag.py                      # Lecture PDF, chunking, ChromaDB, recherche RAG
├── cvs/                        # Dossier à créer pour déposer les CV en PDF
├── chroma_db/                  # Base vectorielle locale générée automatiquement
├── memoire/
│   └── memoire.json            # Mémoire locale générée automatiquement
└── resultats/
    ├── offres_detectees/       # Détails des offres détectées
    ├── notes_agent/            # Notes générées par l'agent
    ├── offres_detectees.txt    # Index global des offres détectées
    └── notifications.log       # Journal des notifications
```

---

## Fonctionnement général

Le fonctionnement suit plusieurs étapes.

### 1. Chargement des CV

Les CV PDF sont placés dans le dossier `cvs/`.

Le module `rag.py` lit les PDF avec `pdfplumber`, extrait le texte, les colonnes et les tableaux, puis découpe le contenu en plusieurs chunks. Ces chunks sont ensuite indexés dans ChromaDB.

### 2. Récupération des offres

Le module `api_france_travail.py` récupère les offres depuis l’API France Travail si les identifiants sont configurés.

Il est aussi possible d’utiliser des offres manuelles dans `OFFRES_MANUELLES`, ce qui permet de tester le système sans dépendre directement de l’API.

### 3. Analyse RAG

Pour chaque offre, le système construit une requête à partir du titre, des compétences, du lieu, du contrat et de la description.

La recherche RAG récupère les extraits de CV les plus proches et calcule un score de similarité.

### 4. Analyse LLM

Si le score RAG est suffisant, les meilleurs extraits du CV sont envoyés au LLM local via Ollama.

Le LLM doit répondre uniquement au format JSON avec :

```json
{
  "points_forts": ["..."],
  "points_manquants": ["..."],
  "score": 0,
  "decision": "ACCEPTÉ",
  "explication": "..."
}
```

### 5. Score final

Le score final combine :

- 60 % du score RAG
- 40 % du score LLM

Une pondération supplémentaire est appliquée selon la décision du LLM.

### 6. Détection et sauvegarde

Une offre est considérée comme intéressante si :

- la décision est `ACCEPTÉ`
- le score final dépasse le seuil défini dans `config.py`
- l’offre n’a pas déjà été détectée

Les résultats sont ensuite sauvegardés dans `resultats/`.

### 7. Dashboard

Le dashboard Streamlit permet de suivre :

- les notifications
- les offres détectées
- les scores RAG, LLM et final
- la décision
- l’explication générée
- l’historique de la mémoire

---

## Installation

### 1. Cloner le projet

```bash
git clone https://github.com/lolo150/AgentRH
cd AgentRH
```

### 2. Créer un environnement virtuel

```bash
python -m venv .venv
```

Activer l’environnement :

```bash
# Windows
.venv\Scripts\activate
```

```bash
# macOS / Linux
source .venv/bin/activate
```

### 3. Installer les dépendances

Si vous avez un fichier `requirements.txt` :

```bash
pip install -r requirements.txt
```

Sinon, installer les dépendances principales :

```bash
pip install requests streamlit chromadb pdfplumber langchain langchain-ollama langgraph langchain-text-splitters sentence-transformers
```

### 4. Installer Ollama

Installer Ollama depuis le site officiel, puis télécharger le modèle utilisé par défaut :

```bash
ollama pull qwen2.5:1.5b
```

Vérifier qu’Ollama fonctionne :

```bash
ollama list
```

Le projet utilise par défaut :

```python
MODELE_LLM = "qwen2.5:1.5b"
URL_OLLAMA = "http://localhost:11434"
```

Ces valeurs sont modifiables dans `config.py`.

---

## Configuration

Les principaux paramètres se trouvent dans `config.py`.

### Modèle LLM

```python
MODELE_LLM = "qwen2.5:7b"
URL_OLLAMA = "http://localhost:11434"
```

### Embedding

```python
MODELE_EMBEDDING = "all-MiniLM-L6-v2"
```

### Seuils de détection

```python
SEUIL_SIMILARITE = 0.36
SEUIL_DETECTION = 0.52
```

### Pondération des scores

```python
PONDERATION_SCORE_RAG = 0.60
PONDERATION_SCORE_LLM = 0.40
```

### API France Travail

Dans `config.py`, renseigner les identifiants :

```python
FT_CLIENT_ID = "votre_client_id"
FT_CLIENT_SECRET = "votre_client_secret"
```

Ne mettez jamais vos vrais identifiants dans un dépôt public GitHub.

### Paramètres de recherche par défaut

```python
MOTS_CLES_DEFAUT = "data scientist"
DEPARTEMENT_DEFAUT = "69"
NB_OFFRES = 5
```

---

## Utilisation

### 1. Ajouter les CV

Créer un dossier `cvs/` à la racine du projet :

```bash
mkdir cvs
```

Ajouter un ou plusieurs CV au format PDF dans ce dossier.

Exemple :

```text
cvs/
└── mon_cv.pdf
```

### 2. Lancer l’agent

```bash
python main.py
```

Au démarrage, le programme :

1. vérifie qu’Ollama est disponible ;
2. charge les CV PDF ;
3. construit la base RAG ;
4. charge la mémoire ;
5. récupère les offres ;
6. analyse les nouvelles offres ;
7. surveille les nouvelles offres selon l’intervalle configuré.

### 3. Lancer le dashboard

Dans un autre terminal :

```bash
streamlit run dashboard_offres.py
```

Le dashboard affiche les notifications, les offres détectées et l’historique des analyses.

---

## Ajouter une offre manuellement

Pour tester le système sans API, ajouter une offre dans `OFFRES_MANUELLES` dans `api_france_travail.py`.

Exemple :

```python
OFFRES_MANUELLES = [
    {
        "id": "TEST_001",
        "titre": "Data Scientist Junior",
        "entreprise": "DataLab",
        "lieu": "Lyon",
        "contrat": "CDI",
        "salaire": "40 000 EUR/an",
        "description": "Python, SQL, Machine Learning, NLP...",
        "competences": ["Python", "SQL", "Machine Learning"],
        "date": "2026-03-27",
        "url": "https://exemple.com"
    }
]
```

---

## Résultats générés

Les fichiers générés automatiquement sont stockés dans `resultats/`.

### Détail d’une offre détectée

```text
resultats/offres_detectees/
```

Chaque fichier contient :

- le poste ;
- l’entreprise ;
- le lieu ;
- le contrat ;
- le salaire ;
- l’URL ;
- le score RAG ;
- le score LLM ;
- le score final ;
- la décision ;
- l’explication ;
- la description de l’offre ;
- l’analyse LLM.

### Index global

```text
resultats/offres_detectees.txt
```

Ce fichier garde une ligne de résumé par offre détectée.

### Notifications

```text
resultats/notifications.log
```

Ce fichier contient les alertes créées lorsqu’une offre pertinente est détectée.

### Mémoire

```text
memoire/memoire.json
```

Ce fichier évite de retraiter plusieurs fois les mêmes offres.

---

## Exemple de logique de décision

Une offre peut être refusée même si elle contient quelques mots-clés techniques, si le métier est sans rapport avec le CV.

Exemple :

- offre Data Scientist avec Python, SQL, Machine Learning → probablement `ACCEPTÉ`
- offre médecin, avocat ou footballeur → probablement `REFUSÉ`
- offre partiellement liée mais pas assez claire → `JE NE SAIS PAS`

Cette logique permet d’éviter les faux positifs.

---

## Commandes utiles

Lancer l’agent :

```bash
python main.py
```

Lancer le dashboard :

```bash
streamlit run dashboard_offres.py
```

Télécharger le modèle Ollama :

```bash
ollama pull qwen2.5:1.5b
```

Changer le modèle Ollama dans `config.py` :

```python
MODELE_LLM = "nom_du_modele"
```

---

## Conseils avant publication sur GitHub

Avant de publier le projet :

1. Ne pas publier vos vrais CV.
2. Ne pas publier vos vrais identifiants France Travail.
3. Ajouter `cvs/`, `chroma_db/`, `memoire/` et `resultats/` dans `.gitignore`.
4. Ajouter un fichier `requirements.txt`.
5. Ajouter éventuellement un fichier `.env.example` si vous améliorez la gestion des variables sensibles.

Exemple de `.gitignore` conseillé :

```gitignore
.venv/
__pycache__/
*.pyc

cvs/
chroma_db/
memoire/
resultats/

.env
```

---

## Améliorations possibles

- Déplacer les identifiants API dans un fichier `.env`.
- Ajouter une interface pour modifier les seuils sans toucher au code.
- Ajouter un export CSV des offres détectées.
- Ajouter un système d’envoi d’email automatique.
- Ajouter une meilleure gestion des erreurs API.
- Ajouter des tests unitaires.
- Ajouter un mode Docker.
- Ajouter une page de configuration dans Streamlit.

---

## Remarque

Ce projet fonctionne localement. Les CV, la base vectorielle, les résultats et les logs restent sur la machine de l’utilisateur, sauf si le dépôt GitHub est publié avec ces fichiers. Il faut donc faire attention à ne pas versionner les données personnelles.

---

## Auteur

Projet développé dans le cadre d’un agent local de matching entre CV et offres d’emploi.

