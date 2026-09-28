"""Tests unitaires — ``ops/enrichissement.py`` (3e boucle de rétroaction).

Capture des cas de production à faible confiance, pseudonymisation minimale,
versement dans le jeu d'évaluation après validation humaine.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ops.enrichissement import ErreurEnrichissement, capturer, lister, pseudonymiser, verser
from ops.registry import Registry


# ------------------------------------------------------------- pseudonymiser


def test_pseudonymiser_remplace_un_montant():
    texte = "Le montant de 50 000 € est dû à réception."
    assert "[MONTANT]" in pseudonymiser(texte)
    assert "50 000" not in pseudonymiser(texte)


def test_pseudonymiser_remplace_un_email():
    texte = "Contact : jean.dupont@example.com pour toute question."
    assert "[EMAIL]" in pseudonymiser(texte)
    assert "jean.dupont@example.com" not in pseudonymiser(texte)


def test_pseudonymiser_remplace_un_siret():
    texte = "SIRET 123 456 789 00012, immatriculée à Montpellier."
    resultat = pseudonymiser(texte)
    assert "[SIRET]" in resultat
    assert "123 456 789 00012" not in resultat


def test_pseudonymiser_remplace_un_telephone():
    texte = "Téléphone : 04 67 12 34 56."
    resultat = pseudonymiser(texte)
    assert "[TELEPHONE]" in resultat
    assert "04 67 12 34 56" not in resultat


def test_pseudonymiser_laisse_le_reste_intact():
    texte = "Article 3 — Durée du contrat : douze mois renouvelables."
    assert pseudonymiser(texte) == texte


# ------------------------------------------------------------------ capturer


def test_capturer_sous_le_seuil_ecrit_un_cas(tmp_path: Path):
    cas_id = capturer(
        "Le montant de 1 000 € est dû.",
        clauses=["prix et paiement"],
        confiance_globale=0.4,
        version="v2.0.0",
        dossier=tmp_path,
    )
    assert cas_id is not None
    assert cas_id.startswith("p-")
    fichier = tmp_path / f"{cas_id}.json"
    assert fichier.exists()
    contenu = json.loads(fichier.read_text(encoding="utf-8"))
    assert contenu["texte"] == "Le montant de [MONTANT] est dû."
    assert contenu["clauses"] == ["prix et paiement"]
    assert contenu["confiance_globale"] == 0.4
    assert contenu["version"] == "v2.0.0"
    assert contenu["source"] == "production"
    assert "date" in contenu


def test_capturer_au_dessus_du_seuil_ne_capture_pas(tmp_path: Path):
    cas_id = capturer(
        "texte quelconque",
        clauses=["durée"],
        confiance_globale=0.6,
        version="v2.0.0",
        dossier=tmp_path,
    )
    assert cas_id is None
    assert list(tmp_path.iterdir()) == []


def test_capturer_deux_cas_ont_des_ids_distincts(tmp_path: Path):
    id1 = capturer("texte A", clauses=[], confiance_globale=0.1, version="v2.0.0", dossier=tmp_path)
    id2 = capturer("texte B", clauses=[], confiance_globale=0.1, version="v2.0.0", dossier=tmp_path)
    assert id1 != id2


# -------------------------------------------------------------------- lister


def test_lister_renvoie_les_cas_en_attente(tmp_path: Path):
    capturer("texte A", clauses=[], confiance_globale=0.1, version="v2.0.0", dossier=tmp_path)
    capturer("texte B", clauses=[], confiance_globale=0.2, version="v2.0.0", dossier=tmp_path)
    cas = lister(dossier=tmp_path)
    assert len(cas) == 2
    assert {c["texte"] for c in cas} == {"texte A", "texte B"}


def test_lister_dossier_vide(tmp_path: Path):
    assert lister(dossier=tmp_path) == []


# -------------------------------------------------------------------- verser


def test_verser_ecrit_le_contrat_et_la_ligne_attendus(tmp_path: Path):
    dossier = tmp_path / "a_valider"
    contrats = tmp_path / "contrats"
    attendus = tmp_path / "attendus.jsonl"
    registry = Registry(tmp_path / "registry")

    cas_id = capturer(
        "Le contrat prévoit [MONTANT] à titre de prix.",
        clauses=["prix et paiement"],
        confiance_globale=0.3,
        version="v2.0.0",
        dossier=dossier,
    )
    contrat_id = verser(
        cas_id,
        clauses_attendues=["prix et paiement", "durée"],
        par="juriste@example.com",
        dossier=dossier,
        contrats=contrats,
        attendus=attendus,
        registry=registry,
    )

    assert contrat_id == cas_id
    assert (contrats / f"{contrat_id}.txt").read_text(encoding="utf-8") == (
        "Le contrat prévoit [MONTANT] à titre de prix."
    )
    lignes = attendus.read_text(encoding="utf-8").splitlines()
    assert len(lignes) == 1
    item = json.loads(lignes[0])
    assert item["contrat_id"] == contrat_id
    assert item["clauses_attendues"] == ["prix et paiement", "durée"]
    assert item["seuil_note"] == 0.75
    assert item["source"] == "production"
    assert "pages" in item

    # le cas en attente a été supprimé
    assert lister(dossier=dossier) == []

    # journalisé au registre
    entree = registry.journal()[-1]
    assert entree["evenement"] == "enrichissement"
    assert entree["declencheur"] == "humain"
    assert entree["par"] == "juriste@example.com"
    assert entree["signal"] == "score_faible"
    assert entree["valeur"] == 0.3
    assert entree["contrat_id"] == contrat_id


def test_verser_cas_inconnu_leve_une_erreur(tmp_path: Path):
    with pytest.raises(ErreurEnrichissement):
        verser(
            "p-inconnu",
            clauses_attendues=["durée"],
            par="juriste@example.com",
            dossier=tmp_path / "a_valider",
            contrats=tmp_path / "contrats",
            attendus=tmp_path / "attendus.jsonl",
            registry=Registry(tmp_path / "registry"),
        )


def test_verser_id_deja_present_leve_une_erreur(tmp_path: Path):
    dossier = tmp_path / "a_valider"
    contrats = tmp_path / "contrats"
    attendus = tmp_path / "attendus.jsonl"
    registry = Registry(tmp_path / "registry")
    contrats.mkdir(parents=True)
    (contrats / "p-deja-la.txt").write_text("déjà présent", encoding="utf-8")

    cas_id = capturer(
        "nouveau texte", clauses=[], confiance_globale=0.1, version="v2.0.0", dossier=dossier
    )
    # on force une collision d'id en renommant le cas capturé
    (dossier / f"{cas_id}.json").rename(dossier / "p-deja-la.json")

    with pytest.raises(ErreurEnrichissement):
        verser(
            "p-deja-la",
            clauses_attendues=["durée"],
            par="juriste@example.com",
            dossier=dossier,
            contrats=contrats,
            attendus=attendus,
            registry=registry,
        )
