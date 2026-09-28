"""Tests unitaires — ops/regles.py (fusion des règles, parsing des seuils)."""
from __future__ import annotations

import json

from ops.regles import (
    lire_regles,
    seuil_cout_moyen_eur,
    seuil_latence_p95_ms,
    seuil_score_faible,
    seuil_taux_erreur,
)


def test_lire_regles_sans_fichier_renvoie_les_defauts(monkeypatch, tmp_path):
    monkeypatch.setenv("REGLES_PILOTAGE_PATH", str(tmp_path / "regles.json"))
    signaux = {r["signal"] for r in lire_regles()}
    assert signaux == {"latence_p95", "taux_erreur", "score_faible", "cout_moyen", "canary"}


def test_lire_regles_fusionne_fichier_partiel_avec_defauts(monkeypatch, tmp_path):
    """Fichier sans la règle de coût (cas du fichier historique) : la fusion
    complète avec la valeur par défaut, sans écraser les autres règles
    présentes sur disque."""
    chemin = tmp_path / "regles.json"
    chemin.write_text(
        json.dumps(
            [
                {
                    "signal": "latence_p95",
                    "seuil": "> 5 s",
                    "retroaction": "rollback",
                    "declencheur": "humain",
                    "trace": "Journal (humain)",
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("REGLES_PILOTAGE_PATH", str(chemin))
    regles = {r["signal"]: r for r in lire_regles()}
    assert regles["latence_p95"]["seuil"] == "> 5 s"
    assert regles["cout_moyen"]["seuil"] == "> 0,15 €"  # valeur par défaut


def test_seuil_latence_p95_ms_parse_en_millisecondes():
    assert seuil_latence_p95_ms({"latence_p95": {"seuil": "> 8 s"}}) == 8000


def test_seuil_taux_erreur_parse_en_proportion():
    assert seuil_taux_erreur({"taux_erreur": {"seuil": "> 10 %"}}) == 0.10


def test_seuil_score_faible_parse_proportion_et_score():
    assert seuil_score_faible({"score_faible": {"seuil": "> 20 % de scores < 0,6"}}) == (0.20, 0.6)


def test_seuil_cout_moyen_eur_parse_en_euros():
    assert seuil_cout_moyen_eur({"cout_moyen": {"seuil": "> 0,15 €"}}) == 0.15


def test_seuil_illisible_retombe_sur_le_defaut(caplog):
    assert seuil_latence_p95_ms({"latence_p95": {"seuil": "une contrainte molle"}}) == 8000
    assert seuil_taux_erreur({"taux_erreur": {"seuil": "élevé"}}) == 0.10
    assert seuil_score_faible({"score_faible": {"seuil": "trop de scores bas"}}) == (0.20, 0.6)
    assert seuil_cout_moyen_eur({"cout_moyen": {"seuil": "cher"}}) == 0.15


def test_seuil_signal_absent_retombe_sur_le_defaut():
    assert seuil_latence_p95_ms({}) == 8000
    assert seuil_cout_moyen_eur({}, defaut=0.30) == 0.30
