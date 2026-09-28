"""Enrichissement du jeu d'évaluation — 3e boucle de rétroaction.

Capture les cas de production à faible confiance (score < ``SEUIL_CAPTURE``,
aligné sur ``SEUIL_SCORE_FAIBLE`` de ``ops/serveur_pilotage.py``), sous forme
pseudonymisée, pour un versement ultérieur dans ``eval/attendus.jsonl`` après
validation humaine (un juriste confirme/corrige les clauses attendues).

Voir ``../conception_figee/chantier2_observabilite/enrichissement-eval.md``
et ``../conception_figee/chantier1_llmops/anonymisation.md``.

Trois étapes, trois fonctions :

    capturer(texte, clauses, confiance_globale, version, dossier=None) -> str | None
        Sous le seuil : écrit ``<dossier>/<cas_id>.json`` et renvoie l'id.
    lister(dossier=None) -> list[dict]
        Les cas en attente de validation humaine.
    verser(cas_id, clauses_attendues, par, ...) -> str
        Versement définitif : ``eval/contrats/<id>.txt`` + une ligne dans
        ``eval/attendus.jsonl``, journalisé au registre, cas en attente
        supprimé.

Limite assumée (YAGNI) : ``pseudonymiser`` est une pseudonymisation par
regex minimale (montant, email, SIRET, téléphone) — pas de détection des
noms propres / adresses par zones (début/fin) décrite dans
``anonymisation.md``, ni de table de correspondance réversible.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ops.registry import Registry

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_CAPTURE_DEFAUT = RACINE / "eval" / "a_valider"
DOSSIER_CONTRATS_DEFAUT = RACINE / "eval" / "contrats"
CHEMIN_ATTENDUS_DEFAUT = RACINE / "eval" / "attendus.jsonl"

SEUIL_CAPTURE = 0.6
SEUIL_NOTE_DEFAUT = 0.75

# Ordre important : le motif SIRET (14 chiffres) doit être appliqué avant le
# motif téléphone (10 chiffres), sous peine de ne remplacer qu'une partie
# d'un SIRET et de laisser des chiffres épars.
_MOTIF_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_MOTIF_SIRET = re.compile(r"\b\d{3}\s?\d{3}\s?\d{3}\s?\d{5}\b")
_MOTIF_TELEPHONE = re.compile(r"\b0[1-9](?:[ .-]?\d{2}){4}\b")
_MOTIF_MONTANT = re.compile(r"\d[\d\s]*(?:,\d+)?\s?€")


class ErreurEnrichissement(RuntimeError):
    pass


def pseudonymiser(texte: str) -> str:
    """Remplace montants, emails, SIRET et téléphones par des placeholders
    neutres (``[MONTANT]``, ``[EMAIL]``, ``[SIRET]``, ``[TELEPHONE]``).

    Pseudonymisation par regex minimale (voir limite en tête de module) :
    ne détecte pas les noms propres ni les adresses.
    """
    texte = _MOTIF_EMAIL.sub("[EMAIL]", texte)
    texte = _MOTIF_SIRET.sub("[SIRET]", texte)
    texte = _MOTIF_TELEPHONE.sub("[TELEPHONE]", texte)
    texte = _MOTIF_MONTANT.sub("[MONTANT]", texte)
    return texte


def _dossier_capture(dossier: Path | str | None) -> Path:
    return Path(dossier or os.environ.get("CAPTURE_DIR") or DOSSIER_CAPTURE_DEFAUT)


def _dossier_contrats(contrats: Path | str | None) -> Path:
    return Path(contrats or os.environ.get("EVAL_CONTRATS_PATH") or DOSSIER_CONTRATS_DEFAUT)


def _chemin_attendus(attendus: Path | str | None) -> Path:
    return Path(attendus or os.environ.get("EVAL_ATTENDUS_PATH") or CHEMIN_ATTENDUS_DEFAUT)


def _nouveau_cas_id(texte: str) -> str:
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    court_hash = hashlib.sha256(f"{texte}{time.time_ns()}".encode()).hexdigest()[:8]
    return f"p-{horodatage}-{court_hash}"


def capturer(
    texte: str,
    clauses: list[str],
    confiance_globale: float,
    version: str,
    dossier: Path | str | None = None,
) -> str | None:
    """Capture un cas de production sous le seuil de confiance faible.

    Renvoie l'id du cas capturé, ou ``None`` si ``confiance_globale`` est au
    seuil ou au-dessus (rien n'est écrit).
    """
    if confiance_globale >= SEUIL_CAPTURE:
        return None
    dossier_cible = _dossier_capture(dossier)
    dossier_cible.mkdir(parents=True, exist_ok=True)
    cas_id = _nouveau_cas_id(texte)
    cas = {
        "texte": pseudonymiser(texte),
        "clauses": clauses,
        "confiance_globale": confiance_globale,
        "version": version,
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "production",
    }
    (dossier_cible / f"{cas_id}.json").write_text(
        json.dumps(cas, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return cas_id


def lister(dossier: Path | str | None = None) -> list[dict[str, Any]]:
    """Les cas en attente de validation humaine, triés par id (donc par date)."""
    dossier_cible = _dossier_capture(dossier)
    if not dossier_cible.exists():
        return []
    cas = []
    for fichier in sorted(dossier_cible.glob("p-*.json")):
        contenu = json.loads(fichier.read_text(encoding="utf-8"))
        cas.append({"cas_id": fichier.stem, **contenu})
    return cas


def _estimer_pages(texte: str) -> int:
    """Pas de pagination réelle disponible pour un cas capturé en
    production : estimation grossière (~3000 caractères/page, cohérente
    avec ``contexte_max_caracteres`` par défaut du bundle v2)."""
    return max(1, -(-len(texte) // 3000))


def verser(
    cas_id: str,
    clauses_attendues: list[str],
    par: str,
    dossier: Path | str | None = None,
    contrats: Path | str | None = None,
    attendus: Path | str | None = None,
    registry: Registry | None = None,
) -> str:
    """Versement définitif d'un cas validé par un humain dans le jeu d'éval.

    Écrit ``<contrats>/<cas_id>.txt`` et ajoute une ligne à ``attendus``,
    journalise l'événement au registre, puis supprime le cas en attente.
    Lève ``ErreurEnrichissement`` si le cas est inconnu ou si un contrat du
    même id existe déjà (ids non ré-utilisables, pas d'écrasement).
    """
    dossier_cible = _dossier_capture(dossier)
    fichier_cas = dossier_cible / f"{cas_id}.json"
    if not fichier_cas.exists():
        raise ErreurEnrichissement(f"cas d'enrichissement inconnu : {cas_id!r}")

    dossier_contrats = _dossier_contrats(contrats)
    chemin_contrat = dossier_contrats / f"{cas_id}.txt"
    if chemin_contrat.exists():
        raise ErreurEnrichissement(f"un contrat {cas_id!r} existe déjà (id non réutilisable)")

    cas = json.loads(fichier_cas.read_text(encoding="utf-8"))

    dossier_contrats.mkdir(parents=True, exist_ok=True)
    chemin_contrat.write_text(cas["texte"], encoding="utf-8")

    chemin_attendus = _chemin_attendus(attendus)
    chemin_attendus.parent.mkdir(parents=True, exist_ok=True)
    ligne = {
        "contrat_id": cas_id,
        "pages": _estimer_pages(cas["texte"]),
        "clauses_attendues": clauses_attendues,
        "seuil_note": SEUIL_NOTE_DEFAUT,
        "source": "production",
    }
    with chemin_attendus.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    reg = registry or Registry()
    reg.journaliser(
        "enrichissement",
        declencheur="humain",
        par=par,
        signal="score_faible",
        valeur=cas["confiance_globale"],
        contrat_id=cas_id,
    )

    fichier_cas.unlink()
    return cas_id
