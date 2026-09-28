"""Règles de pilotage ajustables — chargement, fusion avec les défauts et
parsing des seuils numériques.

Partagé par ``ops/serveur_pilotage.py`` (routes ``GET/PUT /pilotage/regles``)
et ``ops/deploy.py`` (``surveiller`` consomme ces seuils pour décider du
rollback) — sans que ``ops/deploy.py`` importe le serveur FastAPI.

Le fichier sur disque (``REGLES_PILOTAGE_PATH``, défaut
``ops/regles_pilotage.json``) peut ne pas (encore) contenir tous les
signaux connus (ex. ``cout_moyen``, ajouté après coup) : la fusion se fait
par ``signal``, une règle absente du fichier retombe sur sa valeur par
défaut ci-dessous.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RACINE_OPS = Path(__file__).resolve().parent
CHEMIN_REGLES_DEFAUT = RACINE_OPS / "regles_pilotage.json"

REGLES_PAR_DEFAUT: list[dict[str, str]] = [
    {
        "signal": "latence_p95",
        "seuil": "> 8 s",
        "retroaction": "rollback",
        "declencheur": "auto",
        "trace": "Journal (auto)",
    },
    {
        "signal": "taux_erreur",
        "seuil": "> 10 %",
        "retroaction": "rollback",
        "declencheur": "auto",
        "trace": "Journal (auto)",
    },
    {
        "signal": "score_faible",
        "seuil": "> 20 % de scores < 0,6",
        "retroaction": "rollback + enrichissement du jeu d'éval",
        "declencheur": "auto",
        "trace": "Journal (auto)",
    },
    {
        "signal": "cout_moyen",
        "seuil": "> 0,15 €",
        "retroaction": "rollback",
        "declencheur": "auto",
        "trace": "Journal (auto)",
    },
    {
        "signal": "canary",
        "seuil": "contraintes tenues et v2 ≥ v1",
        "retroaction": "promotion 10 % → 50 % → 100 %",
        "declencheur": "auto_humain",
        "trace": "Journal (auto ou humain)",
    },
]


def chemin_regles() -> Path:
    return Path(os.environ.get("REGLES_PILOTAGE_PATH", CHEMIN_REGLES_DEFAUT))


def lire_regles() -> list[dict[str, str]]:
    """Règles sur disque fusionnées avec les défauts, par ``signal``."""
    chemin = chemin_regles()
    disque = json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else []
    par_signal_disque = {r["signal"]: r for r in disque}
    signaux_defaut = {r["signal"] for r in REGLES_PAR_DEFAUT}
    resultat = [par_signal_disque.get(d["signal"], dict(d)) for d in REGLES_PAR_DEFAUT]
    resultat += [r for r in disque if r["signal"] not in signaux_defaut]
    return resultat


def ecrire_regles(regles: list[dict[str, str]]) -> None:
    chemin = chemin_regles()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(regles, ensure_ascii=False, indent=2), encoding="utf-8")


def regles_par_signal() -> dict[str, dict[str, str]]:
    return {r["signal"]: r for r in lire_regles()}


# ------------------------------------------------------- parsing des seuils


_RE_NOMBRE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _nombres(texte: str) -> list[float]:
    return [float(n.replace(",", ".")) for n in _RE_NOMBRE.findall(texte)]


def seuil_latence_p95_ms(regles: dict[str, dict[str, Any]], defaut: float = 8000) -> float:
    regle = regles.get("latence_p95")
    nombres = _nombres(regle["seuil"]) if regle else []
    if not nombres:
        if regle:
            logger.warning("règle latence_p95 illisible (%r), valeur par défaut conservée", regle["seuil"])
        return defaut
    return nombres[0] * 1000


def seuil_taux_erreur(regles: dict[str, dict[str, Any]], defaut: float = 0.10) -> float:
    regle = regles.get("taux_erreur")
    nombres = _nombres(regle["seuil"]) if regle else []
    if not nombres:
        if regle:
            logger.warning("règle taux_erreur illisible (%r), valeur par défaut conservée", regle["seuil"])
        return defaut
    return nombres[0] / 100


def seuil_score_faible(
    regles: dict[str, dict[str, Any]], defaut_proportion: float = 0.20, defaut_score: float = 0.6
) -> tuple[float, float]:
    """Renvoie ``(proportion_max, score_bas)`` — dérive si la proportion de
    scores < ``score_bas`` dépasse ``proportion_max``."""
    regle = regles.get("score_faible")
    nombres = _nombres(regle["seuil"]) if regle else []
    if len(nombres) < 2:
        if regle:
            logger.warning("règle score_faible illisible (%r), valeur par défaut conservée", regle["seuil"])
        return defaut_proportion, defaut_score
    return nombres[0] / 100, nombres[1]


def seuil_cout_moyen_eur(regles: dict[str, dict[str, Any]], defaut: float = 0.15) -> float:
    regle = regles.get("cout_moyen")
    nombres = _nombres(regle["seuil"]) if regle else []
    if not nombres:
        if regle:
            logger.warning("règle cout_moyen illisible (%r), valeur par défaut conservée", regle["seuil"])
        return defaut
    return nombres[0]
