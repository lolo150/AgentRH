from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import streamlit as st
from streamlit.components.v1 import html

BASE_DIR = Path(__file__).resolve().parent

try:
    import config as project_config
except Exception:
    project_config = None


def _resolve_path(name: str, default: Path) -> Path:
    if project_config is None:
        return default
    value = getattr(project_config, name, default)
    try:
        return Path(value)
    except Exception:
        return default


DOSSIER_RESULTATS = _resolve_path("DOSSIER_RESULTATS", BASE_DIR / "resultats")
DOSSIER_OFFRES_DETECTEES = _resolve_path("DOSSIER_OFFRES_DETECTEES", DOSSIER_RESULTATS / "offres_detectees")
DOSSIER_NOTES_AGENT = _resolve_path("DOSSIER_NOTES_AGENT", DOSSIER_RESULTATS / "notes_agent")
FICHIER_OFFRES_DETECTEES = _resolve_path("FICHIER_OFFRES_DETECTEES", DOSSIER_RESULTATS / "offres_detectees.txt")
FICHIER_NOTIFICATIONS = _resolve_path("FICHIER_NOTIFICATIONS", DOSSIER_RESULTATS / "notifications.log")
FICHIER_MEMOIRE = _resolve_path("FICHIER_MEMOIRE", BASE_DIR / "memoire" / "memoire.json")


st.set_page_config(page_title="Dashboard Offres", page_icon="🔔", layout="wide")

st.markdown(
    """
    <style>
    .appview-container, .main {
        background: linear-gradient(180deg, #0b1020 0%, #11182e 100%);
    }
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 1.2rem;
        max-width: 1400px;
    }
    .hero {
        padding: 20px 24px;
        border-radius: 22px;
        background: linear-gradient(135deg, rgba(124,58,237,0.28), rgba(59,130,246,0.18));
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 18px 40px rgba(0,0,0,0.18);
        margin-bottom: 16px;
    }
    .hero-title {
        font-size: 1.7rem;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 4px;
    }
    .hero-subtitle {
        color: #cbd5e1;
        font-size: 0.98rem;
    }
    .metric-card {
        padding: 14px 16px;
        border-radius: 18px;
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 10px 24px rgba(0,0,0,0.15);
    }
    .metric-label {
        color: #cbd5e1;
        font-size: 0.88rem;
        margin-bottom: 6px;
    }
    .metric-value {
        color: #f8fafc;
        font-size: 1.55rem;
        font-weight: 700;
    }
    .notification-card {
        padding: 14px 16px;
        border-radius: 18px;
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.06);
        box-shadow: 0 12px 24px rgba(0,0,0,0.14);
        margin-bottom: 10px;
    }
    .card-accept {
        border-left: 5px solid #22c55e;
    }
    .card-refuse {
        border-left: 5px solid #ef4444;
    }
    .card-nsp {
        border-left: 5px solid #f59e0b;
    }
    .notif-date {
        color: #93c5fd;
        font-size: 0.82rem;
        margin-bottom: 6px;
    }
    .notif-title {
        color: #f8fafc;
        font-size: 1.0rem;
        font-weight: 700;
        margin-bottom: 6px;
    }
    .notif-company {
        color: #cbd5e1;
        font-size: 0.92rem;
        margin-bottom: 10px;
    }
    .badge-wrap {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 4px;
    }
    .badge {
        display: inline-block;
        border-radius: 999px;
        padding: 4px 10px;
        font-size: 0.76rem;
        font-weight: 700;
    }
    .badge-green { background: rgba(34,197,94,0.18); color: #86efac; }
    .badge-red { background: rgba(239,68,68,0.18); color: #fca5a5; }
    .badge-yellow { background: rgba(245,158,11,0.18); color: #fcd34d; }
    .badge-blue { background: rgba(59,130,246,0.18); color: #93c5fd; }
    .detail-card {
        padding: 18px 20px;
        border-radius: 20px;
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 14px 28px rgba(0,0,0,0.16);
    }
    .section-title {
        color: #e2e8f0;
        font-size: 1.03rem;
        font-weight: 700;
        margin-bottom: 10px;
        margin-top: 8px;
    }
    .small-muted {
        color: #94a3b8;
        font-size: 0.84rem;
    }
    .empty-box {
        padding: 20px;
        border-radius: 18px;
        background: rgba(255,255,255,0.03);
        border: 1px dashed rgba(255,255,255,0.12);
        color: #cbd5e1;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _safe_read(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return ""


@st.cache_data(ttl=2)
def load_notifications(path: str) -> list[dict]:
    file_path = Path(path)
    text = _safe_read(file_path)
    entries: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        date_match = re.match(r"^\[(?P<date>[^\]]+)\]\s*(?P<body>.*)$", line)
        if not date_match:
            continue
        date_str = date_match.group("date")
        body = date_match.group("body")
        parts = [p.strip() for p in body.split("|")]
        titre = ""
        entreprise = ""
        score_final = None
        decision = ""
        for part in parts:
            lower = part.lower()
            if lower == "alerte":
                continue
            if lower.startswith("score_final="):
                try:
                    score_final = float(part.split("=", 1)[1].strip())
                except Exception:
                    score_final = None
            elif lower.startswith("décision=") or lower.startswith("decision="):
                decision = part.split("=", 1)[1].strip()
            elif not titre:
                titre = part
            elif not entreprise:
                entreprise = part
        entries.append(
            {
                "date": date_str,
                "titre": titre,
                "entreprise": entreprise,
                "score_final": score_final,
                "decision": decision or "JE NE SAIS PAS",
                "raw": line,
            }
        )
    entries.sort(key=lambda x: x["date"], reverse=True)
    return entries


@st.cache_data(ttl=2)
def load_memoire(path: str) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        return {
            "offres_vues": [],
            "offres_signalees": [],
            "offres_detectees": [],
            "historique": [],
        }
    try:
        return json.loads(_safe_read(file_path) or "{}")
    except Exception:
        return {
            "offres_vues": [],
            "offres_signalees": [],
            "offres_detectees": [],
            "historique": [],
        }


@st.cache_data(ttl=2)
def load_index(path: str, details_dir: str, notes_dir: str) -> list[dict]:
    file_path = Path(path)
    details_path = Path(details_dir)
    notes_path = Path(notes_dir)
    text = _safe_read(file_path)
    entries: list[dict] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        date_match = re.match(r"^\[(?P<date>[^\]]+)\]\s*(?P<body>.*)$", raw)
        if not date_match:
            continue
        date_str = date_match.group("date")
        body = date_match.group("body")
        chunks = [p.strip() for p in body.split("|") if p.strip()]
        data: dict[str, str] = {"date": date_str, "raw": raw}
        for chunk in chunks:
            if "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            data[key.strip()] = value.strip()
        file_name = data.get("Fichier", "")
        detail_file = details_path / file_name if file_name else None
        note_file = notes_path / f"note_agent_{file_name}" if file_name else None
        entries.append(
            {
                "id": data.get("ID", ""),
                "date": date_str,
                "titre": data.get("Poste", "Sans titre"),
                "entreprise": data.get("Entreprise", ""),
                "score_rag": _to_float(data.get("ScoreRAG")),
                "score_llm": _to_float(data.get("ScoreLLM")),
                "score_final": _to_float(data.get("ScoreFinal")),
                "decision": data.get("Décision") or data.get("Decision") or "",
                "detail_file": detail_file,
                "note_file": note_file,
                "raw": raw,
            }
        )
    entries.sort(key=lambda x: x["date"], reverse=True)
    return entries


def _to_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return None


@st.cache_data(ttl=2)
def read_detail_file(path: str) -> dict:
    file_path = Path(path)
    text = _safe_read(file_path)
    if not text:
        return {"raw": ""}
    description = ""
    analyse_llm = ""
    if "DESCRIPTION :" in text:
        after_desc = text.split("DESCRIPTION :", 1)[1]
        if "ANALYSE LLM :" in after_desc:
            description, analyse_llm = after_desc.split("ANALYSE LLM :", 1)
        else:
            description = after_desc
    fields = {}
    for label in [
        "Date détection",
        "ID",
        "Poste",
        "Entreprise",
        "Lieu",
        "Contrat",
        "Salaire",
        "URL",
        "Score RAG",
        "Score LLM",
        "Score final",
        "Décision",
        "Explication",
        "COMPÉTENCES",
    ]:
        pattern = rf"{re.escape(label)}\s*:\s*(.*)"
        match = re.search(pattern, text)
        if match:
            fields[label] = match.group(1).strip()
    fields["DESCRIPTION"] = description.strip()
    fields["ANALYSE_LLM"] = analyse_llm.strip()
    fields["raw"] = text
    return fields


@st.cache_data(ttl=2)
def read_note_file(path: str) -> str:
    return _safe_read(Path(path))


@st.cache_data(ttl=2)
def build_offer_lookup(index_entries: list[dict]) -> dict:
    lookup: dict[str, dict] = {}
    for item in index_entries:
        k1 = f"{item.get('titre','').strip().lower()}||{item.get('entreprise','').strip().lower()}"
        if k1 and k1 not in lookup:
            lookup[k1] = item
        k2 = item.get("id", "").strip().lower()
        if k2 and k2 not in lookup:
            lookup[k2] = item
    return lookup


notifications = load_notifications(str(FICHIER_NOTIFICATIONS))
index_entries = load_index(str(FICHIER_OFFRES_DETECTEES), str(DOSSIER_OFFRES_DETECTEES), str(DOSSIER_NOTES_AGENT))
memoire = load_memoire(str(FICHIER_MEMOIRE))
lookup = build_offer_lookup(index_entries)

if "selected_offer_key" not in st.session_state:
    st.session_state.selected_offer_key = ""

if "last_notification_count" not in st.session_state:
    st.session_state.last_notification_count = len(notifications)

st.markdown(
    f"""
    <div class='hero'>
        <div class='hero-title'>🔔 Dashboard des offres détectées</div>
        <div class='hero-subtitle'>Suivi en direct des notifications, accès au détail d'une offre, et lecture du résultat complet d'analyse.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Paramètres")
    auto_refresh = st.toggle("Rafraîchissement automatique", value=True)
    refresh_seconds = st.slider("Intervalle (secondes)", 3, 60, 8)
    if st.button("Actualiser maintenant", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption("Fichiers surveillés")
    st.code(str(FICHIER_NOTIFICATIONS), language=None)
    st.code(str(FICHIER_OFFRES_DETECTEES), language=None)
    st.code(str(FICHIER_MEMOIRE), language=None)

if auto_refresh:
    html(
        f"""
        <script>
        setTimeout(function() {{
            const topWindow = window.parent;
            if (topWindow && topWindow.location) {{
                topWindow.location.reload();
            }} else {{
                window.location.reload();
            }}
        }}, {refresh_seconds * 1000});
        </script>
        """,
        height=0,
    )

if len(notifications) > st.session_state.last_notification_count and hasattr(st, "toast"):
    new_count = len(notifications) - st.session_state.last_notification_count
    for notif in reversed(notifications[:new_count]):
        titre = notif.get("titre") or "Nouvelle offre"
        entreprise = notif.get("entreprise") or "Entreprise inconnue"
        st.toast(f"Nouvelle offre détectée : {titre} — {entreprise}", icon="🔔")
    st.session_state.last_notification_count = len(notifications)
elif len(notifications) < st.session_state.last_notification_count:
    st.session_state.last_notification_count = len(notifications)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Notifications</div><div class='metric-value'>{len(notifications)}</div></div>",
        unsafe_allow_html=True,
    )
with col2:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Offres détectées</div><div class='metric-value'>{len(index_entries)}</div></div>",
        unsafe_allow_html=True,
    )
with col3:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Offres analysées</div><div class='metric-value'>{len(memoire.get('offres_vues', []))}</div></div>",
        unsafe_allow_html=True,
    )
with col4:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Offres signalées</div><div class='metric-value'>{len(memoire.get('offres_signalees', []))}</div></div>",
        unsafe_allow_html=True,
    )

notification_tab, detected_tab, history_tab = st.tabs(["Notifications", "Offres détectées", "Historique mémoire"])


def decision_class(decision: str) -> tuple[str, str]:
    dec = (decision or "").upper().strip()
    if "ACCEPT" in dec:
        return "card-accept", "badge-green"
    if "REFUS" in dec:
        return "card-refuse", "badge-red"
    return "card-nsp", "badge-yellow"


with notification_tab:
    left, right = st.columns([1.08, 1.35], gap="large")
    with left:
        st.markdown("<div class='section-title'>Flux des notifications</div>", unsafe_allow_html=True)
        if not notifications:
            st.markdown("<div class='empty-box'>Aucune notification pour le moment.</div>", unsafe_allow_html=True)
        else:
            for i, notif in enumerate(notifications):
                css_class, badge_class = decision_class(notif.get("decision", ""))
                score_final = notif.get("score_final")
                score_text = f"{score_final:.2f}" if isinstance(score_final, float) else "—"
                st.markdown(
                    f"""
                    <div class='notification-card {css_class}'>
                        <div class='notif-date'>{notif.get('date', '')}</div>
                        <div class='notif-title'>{notif.get('titre', 'Sans titre')}</div>
                        <div class='notif-company'>{notif.get('entreprise', '')}</div>
                        <div class='badge-wrap'>
                            <span class='badge {badge_class}'>{notif.get('decision', '—')}</span>
                            <span class='badge badge-blue'>Score final {score_text}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                key = f"{notif.get('titre','').strip().lower()}||{notif.get('entreprise','').strip().lower()}"
                target = lookup.get(key)
                if target:
                    if st.button("Voir le résultat", key=f"notif_btn_{i}", use_container_width=True):
                        st.session_state.selected_offer_key = target.get("detail_file", Path()).as_posix()
                        st.rerun()
                else:
                    st.caption("Résultat détaillé introuvable pour cette notification.")
    with right:
        st.markdown("<div class='section-title'>Résultat sélectionné</div>", unsafe_allow_html=True)
        selected_path = st.session_state.selected_offer_key
        if selected_path:
            selected_entry = next((x for x in index_entries if x.get("detail_file") and x["detail_file"].as_posix() == selected_path), None)
        else:
            selected_entry = index_entries[0] if index_entries else None
        if not selected_entry:
            st.markdown("<div class='empty-box'>Clique sur une notification pour afficher le détail complet.</div>", unsafe_allow_html=True)
        else:
            detail = read_detail_file(str(selected_entry["detail_file"])) if selected_entry.get("detail_file") else {"raw": ""}
            note = read_note_file(str(selected_entry["note_file"])) if selected_entry.get("note_file") and selected_entry["note_file"].exists() else ""
            css_class, badge_class = decision_class(selected_entry.get("decision", ""))
            st.markdown(
                f"""
                <div class='detail-card {css_class}'>
                    <div class='notif-date'>{selected_entry.get('date', '')}</div>
                    <div class='notif-title'>{selected_entry.get('titre', 'Sans titre')}</div>
                    <div class='notif-company'>{selected_entry.get('entreprise', '')}</div>
                    <div class='badge-wrap'>
                        <span class='badge {badge_class}'>{selected_entry.get('decision', '—')}</span>
                        <span class='badge badge-blue'>Score RAG {selected_entry.get('score_rag') if selected_entry.get('score_rag') is not None else '—'}</span>
                        <span class='badge badge-blue'>Score LLM {selected_entry.get('score_llm') if selected_entry.get('score_llm') is not None else '—'}</span>
                        <span class='badge badge-blue'>Score final {selected_entry.get('score_final') if selected_entry.get('score_final') is not None else '—'}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            with c1:
                st.text_input("Entreprise", value=detail.get("Entreprise", selected_entry.get("entreprise", "")), disabled=True)
                st.text_input("Lieu", value=detail.get("Lieu", ""), disabled=True)
                st.text_input("Contrat", value=detail.get("Contrat", ""), disabled=True)
                st.text_input("Salaire", value=detail.get("Salaire", ""), disabled=True)
            with c2:
                st.text_input("ID", value=detail.get("ID", selected_entry.get("id", "")), disabled=True)
                st.text_input("Date", value=detail.get("Date détection", selected_entry.get("date", "")), disabled=True)
                st.text_input("URL", value=detail.get("URL", ""), disabled=True)
                st.text_input("Explication", value=detail.get("Explication", ""), disabled=True)
            st.markdown("<div class='section-title'>Compétences</div>", unsafe_allow_html=True)
            st.write(detail.get("COMPÉTENCES", ""))
            st.markdown("<div class='section-title'>Description du poste</div>", unsafe_allow_html=True)
            st.text_area("Description", value=detail.get("DESCRIPTION", ""), height=220, label_visibility="collapsed")
            st.markdown("<div class='section-title'>Analyse LLM</div>", unsafe_allow_html=True)
            st.text_area("Analyse LLM", value=detail.get("ANALYSE_LLM", ""), height=240, label_visibility="collapsed")
            if note:
                st.markdown("<div class='section-title'>Note agent</div>", unsafe_allow_html=True)
                st.text_area("Note agent", value=note, height=200, label_visibility="collapsed")
            with st.expander("Afficher le fichier brut"):
                st.code(detail.get("raw", ""), language=None)

with detected_tab:
    st.markdown("<div class='section-title'>Toutes les offres détectées</div>", unsafe_allow_html=True)
    if not index_entries:
        st.markdown("<div class='empty-box'>Aucune offre détectée pour le moment.</div>", unsafe_allow_html=True)
    else:
        for i, item in enumerate(index_entries):
            css_class, badge_class = decision_class(item.get("decision", ""))
            st.markdown(
                f"""
                <div class='notification-card {css_class}'>
                    <div class='notif-date'>{item.get('date', '')}</div>
                    <div class='notif-title'>{item.get('titre', 'Sans titre')}</div>
                    <div class='notif-company'>{item.get('entreprise', '')}</div>
                    <div class='badge-wrap'>
                        <span class='badge {badge_class}'>{item.get('decision', '—')}</span>
                        <span class='badge badge-blue'>RAG {item.get('score_rag') if item.get('score_rag') is not None else '—'}</span>
                        <span class='badge badge-blue'>LLM {item.get('score_llm') if item.get('score_llm') is not None else '—'}</span>
                        <span class='badge badge-blue'>Final {item.get('score_final') if item.get('score_final') is not None else '—'}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Ouvrir cette offre", key=f"offer_btn_{i}", use_container_width=True):
                if item.get("detail_file"):
                    st.session_state.selected_offer_key = item["detail_file"].as_posix()
                    st.rerun()

with history_tab:
    st.markdown("<div class='section-title'>Historique de la mémoire</div>", unsafe_allow_html=True)
    historique = list(reversed(memoire.get("historique", [])))
    if not historique:
        st.markdown("<div class='empty-box'>Aucun historique enregistré dans la mémoire.</div>", unsafe_allow_html=True)
    else:
        for i, item in enumerate(historique[:80]):
            decision = item.get("decision", "")
            css_class, badge_class = decision_class(decision)
            score = item.get("score_final", item.get("score_rag", "—"))
            st.markdown(
                f"""
                <div class='notification-card {css_class}'>
                    <div class='notif-date'>{item.get('date', '')} — {item.get('type', 'LOG')}</div>
                    <div class='notif-title'>{item.get('titre', 'Sans titre')}</div>
                    <div class='notif-company'>{item.get('entreprise', '')}</div>
                    <div class='badge-wrap'>
                        <span class='badge {badge_class}'>{decision or '—'}</span>
                        <span class='badge badge-blue'>Score {score}</span>
                        <span class='badge badge-blue'>ID {item.get('offre_id', '')}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.caption(
    f"Dernière lecture : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | "
    f"notifications.log = {'OK' if FICHIER_NOTIFICATIONS.exists() else 'absent'} | "
    f"offres_detectees.txt = {'OK' if FICHIER_OFFRES_DETECTEES.exists() else 'absent'}"
)
