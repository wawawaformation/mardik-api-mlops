"""Test d'acceptance — 3e boucle de rétroaction (enrichissement du jeu d'éval).

Étant donné un cas de production à faible confiance, quand il est capturé,
alors il apparaît dans le jeu d'évaluation et la chaîne le rejoue à la
fusion suivante.
"""
from __future__ import annotations

from pathlib import Path

from app.pipeline.confiance import scorer
from eval.run_eval import charger_attendus, evaluer
from ops.enrichissement import lister, verser


def test_cas_faible_confiance_capture_verse_puis_rejoue(
    client, contrat, tmp_path: Path, monkeypatch, registry
):
    # Force un score global bas : le mock LLM du dépôt ne le donne pas
    # naturellement sur un contrat court, donc on monkeypatche `scorer`
    # (déjà utilisé par `analyser_v2`) pour simuler un cas de faible confiance.
    def scorer_faible(clauses, nb_sections, texte=""):
        clauses_notees, _ = scorer(clauses, nb_sections, texte)
        return clauses_notees, 0.3

    monkeypatch.setattr("app.api_v2.scorer", scorer_faible)

    texte = contrat("c01")
    r = client.post("/v2/analyse", json={"texte": texte, "contrat_id": "c01"})
    assert r.status_code == 200
    assert r.json()["confiance_globale"] == 0.3

    # le cas apparaît en attente de validation humaine
    en_attente = lister()
    assert len(en_attente) == 1
    cas = en_attente[0]
    cas_id = cas["cas_id"]
    assert cas["confiance_globale"] == 0.3

    # validation humaine : un juriste confirme les clauses attendues
    contrats_dir = tmp_path / "contrats"
    attendus_path = tmp_path / "attendus.jsonl"
    contrat_id = verser(
        cas_id,
        clauses_attendues=["durée", "prix et paiement", "résiliation"],
        par="juriste@example.com",
        contrats=contrats_dir,
        attendus=attendus_path,
        registry=registry,
    )
    assert contrat_id == cas_id
    assert lister() == []  # le cas en attente a disparu

    # le contrat versé apparaît bien dans le jeu d'éval
    attendus = charger_attendus(attendus_path)
    assert contrat_id in attendus

    # et la chaîne le rejoue au prochain gate
    rapport = evaluer(
        "v2",
        contrats=contrats_dir,
        attendus=attendus_path,
        sous_ensemble=[contrat_id],
        historique=None,
    )
    assert contrat_id in rapport.par_contrat
