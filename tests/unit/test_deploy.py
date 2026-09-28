"""Tests unitaires — ops/deploy.py (publier/canary/promotion/rollback/surveiller)."""
from __future__ import annotations

import json
import time

import pytest

from app.llm_client import Bundle
from app.telemetry import Mesure, MetricsStore


def _livrer_v2(registry, version="v2.0.0"):
    registry.etiqueter(version, Bundle.charger("v2"), commit="abc1234", note_eval=0.9)
    return version


def _ecrire_regles(monkeypatch, tmp_path, **seuils):
    """Pose un fichier de règles isolé (``REGLES_PILOTAGE_PATH``) ne portant
    que les signaux passés en kwargs (``latence_p95="> 2 s"``, etc.)."""
    chemin = tmp_path / "regles.json"
    chemin.write_text(
        json.dumps(
            [
                {"signal": signal, "seuil": seuil, "retroaction": "rollback",
                 "declencheur": "auto", "trace": "Journal (auto)"}
                for signal, seuil in seuils.items()
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("REGLES_PILOTAGE_PATH", str(chemin))


def test_prochaine_version_premiere_publication_v2_ignore_v1(registry):
    """Seul v1.0.0 (code figé, jamais réétiqueté) est dans le registre : la
    première publication v2 doit prendre la version déclarée par le bundle
    (`models/v2/config.yaml::version`), pas un bump de v1.0.0. Bug corrigé
    le 2026-09-23 : `prochaine_version` mélangeait les deux lignées et
    renvoyait `v1.0.1` pour ce qui était en réalité un premier build v2."""
    from ops.deploy import prochaine_version

    assert prochaine_version(registry=registry) == "v2.0.0"
    assert prochaine_version("major", registry=registry) == "v2.0.0"
    assert prochaine_version("minor", registry=registry) == "v2.0.0"


def test_prochaine_version_patch_par_defaut(registry):
    from ops.deploy import prochaine_version

    _livrer_v2(registry)
    assert prochaine_version(registry=registry) == "v2.0.1"


def test_prochaine_version_minor(registry):
    from ops.deploy import prochaine_version

    _livrer_v2(registry)
    assert prochaine_version("minor", registry=registry) == "v2.1.0"


def test_prochaine_version_major(registry):
    from ops.deploy import prochaine_version

    _livrer_v2(registry)
    assert prochaine_version("major", registry=registry) == "v3.0.0"


def test_prochaine_version_ignore_toujours_v1_apres_plusieurs_publications_v2(registry):
    from ops.deploy import prochaine_version

    _livrer_v2(registry, "v2.0.0")
    _livrer_v2(registry, "v2.0.1")
    assert prochaine_version(registry=registry) == "v2.0.2"


def test_prochaine_version_bump_invalide(registry):
    from ops.deploy import prochaine_version

    with pytest.raises(ValueError):
        prochaine_version("oups", registry=registry)


def test_deployer_canary_pourcentage_par_defaut(registry):
    from ops.deploy import deployer_canary

    _livrer_v2(registry)
    index = deployer_canary("v2.0.0", registry=registry)

    assert index["canary"] == "v2.0.0"
    assert index["canary_percent"] == 10  # CANARY_PERCENT non défini dans les tests -> défaut 10
    assert index["active"] == "v1.0.0"
    assert registry.journal()[-1] == {
        **registry.journal()[-1],
        "evenement": "canary",
        "version": "v2.0.0",
        "pourcentage": 10,
    }


def test_deployer_canary_pourcentage_explicite(registry):
    from ops.deploy import deployer_canary

    _livrer_v2(registry)
    index = deployer_canary("v2.0.0", pourcentage=30, registry=registry)

    assert index["canary"] == "v2.0.0" and index["canary_percent"] == 30


def test_cli_canary_declencheur_et_signal_transmis(registry, monkeypatch):
    from ops.deploy import main

    _livrer_v2(registry)
    monkeypatch.setattr("ops.deploy.Registry", lambda: registry)
    main(["canary", "v2.0.0", "--declencheur", "auto", "--signal", "eval-ok"])

    entree = registry.journal()[-1]
    assert entree["evenement"] == "canary"
    assert entree["declencheur"] == "auto"
    assert entree["signal"] == "eval-ok"


def test_cli_canary_declencheur_par_defaut_humain_sans_signal(registry, monkeypatch):
    from ops.deploy import main

    _livrer_v2(registry)
    monkeypatch.setattr("ops.deploy.Registry", lambda: registry)
    main(["canary", "v2.0.0"])

    entree = registry.journal()[-1]
    assert entree["evenement"] == "canary"
    assert entree["declencheur"] == "humain"
    assert "signal" not in entree


def test_promouvoir(registry):
    from ops.deploy import promouvoir

    _livrer_v2(registry)
    index = promouvoir("v2.0.0", registry=registry)

    assert index["active"] == "v2.0.0"
    assert index["precedente"] == "v1.0.0"
    assert index["canary"] is None and index["canary_percent"] == 0
    assert registry.journal()[-1]["evenement"] == "promotion"


def test_rollback_sans_canary_en_cours(registry):
    from ops.deploy import promouvoir, rollback

    _livrer_v2(registry)
    promouvoir("v2.0.0", registry=registry)

    index = rollback(registry=registry, motif="test")

    assert index["active"] == "v1.0.0"
    assert index["precedente"] == "v2.0.0"
    assert index["canary"] is None
    assert registry.journal()[-1]["evenement"] == "rollback"
    assert registry.journal()[-1]["motif"] == "test"


def test_rollback_avec_canary_en_cours(registry):
    from ops.deploy import deployer_canary, rollback

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)

    index = rollback(registry=registry)

    assert index["active"] == "v1.0.0"  # inchangé : aucune promotion n'a eu lieu
    assert index["canary"] is None and index["canary_percent"] == 0


def test_rollback_sans_rien_a_annuler_garde_lactive(registry):
    """Aucun canary, aucune version précédente : il n'y a rien à annuler.
    Le rollback doit garder la version active en place — jamais `None`, qui
    laisserait la gateway sans version à servir (TypeError → 500)."""
    from ops.deploy import rollback

    index = rollback(registry=registry)

    assert index["active"] == "v1.0.0"
    assert index["canary"] is None


def test_rollback_deux_fois_de_suite_ne_casse_pas_letat(registry):
    """Séquence observée en production le 2026-09-23 : un rollback retire le
    canary, un second rollback (6 s plus tard, sans rien à annuler) mettait
    `active: null` — la gateway plantait alors sur chaque requête."""
    from ops.deploy import deployer_canary, rollback

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)

    rollback(registry=registry)
    index = rollback(registry=registry)

    assert index["active"] == "v1.0.0"
    assert registry.active() is not None


def test_surveiller_sans_derive(metriques: MetricsStore, registry):
    from ops.deploy import deployer_canary, surveiller

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)

    maintenant = time.time()
    for _ in range(12):
        metriques.enregistrer(
            Mesure(ts=maintenant, version="v2.0.0", route="/analyse", latence_ms=2500, score=0.88)
        )
    res = surveiller(registry, metriques, fenetre_s=60, score_min=0.7, minimum=10)
    assert res == {"version": "v2.0.0", "mesures": 12, "derive": False, "motif": "", "rollback": False}
    assert registry.canary()[0] == "v2.0.0"


def test_surveiller_pas_assez_de_mesures_ne_declenche_rien(metriques: MetricsStore, registry):
    from ops.deploy import deployer_canary, surveiller

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)

    for _ in range(5):
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=2500, score=0.1)
        )
    res = surveiller(registry, metriques, fenetre_s=60, score_min=0.7, minimum=10)
    assert res["derive"] is False and res["rollback"] is False and res["mesures"] == 5


def test_surveiller_derive_taux_erreur(metriques: MetricsStore, registry):
    from ops.deploy import deployer_canary, surveiller

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)

    for i in range(10):
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=2500,
                   erreur=(i < 3), score=0.9)
        )
    res = surveiller(registry, metriques, fenetre_s=60, taux_erreur_max=0.10, minimum=10)
    assert res["derive"] is True and "erreur" in res["motif"]
    assert registry.canary() == (None, 0)


def test_surveiller_derive_latence(metriques: MetricsStore, registry):
    from ops.deploy import deployer_canary, surveiller

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)

    for _ in range(10):
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=9000, score=0.9)
        )
    res = surveiller(registry, metriques, fenetre_s=60, latence_p95_max_ms=8000, minimum=10)
    assert res["derive"] is True and "latence" in res["motif"]


def test_surveiller_surveille_le_canary_pas_lactive(metriques: MetricsStore, registry):
    """Un canary en cours est ce qui est surveillé, pas la version active :
    l'active peut avoir une dérive sans provoquer de rollback tant que le
    canary est sain."""
    from ops.deploy import deployer_canary, surveiller

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)

    for _ in range(10):
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v1.0.0", route="/analyse", latence_ms=2500, score=0.1)
        )
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=2500, score=0.9)
        )
    res = surveiller(registry, metriques, fenetre_s=60, score_min=0.7, minimum=10)
    assert res["version"] == "v2.0.0"
    assert res["derive"] is False and res["rollback"] is False


def test_surveiller_sans_canary_surveille_lactive(metriques: MetricsStore, registry):
    from ops.deploy import surveiller

    for _ in range(10):
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v1.0.0", route="/analyse", latence_ms=2500)
        )
    res = surveiller(registry, metriques, fenetre_s=60, minimum=10)
    assert res["version"] == "v1.0.0"


def test_surveiller_journalise_le_rollback(metriques: MetricsStore, registry):
    from ops.deploy import deployer_canary, surveiller

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)

    for _ in range(10):
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=2500, score=0.1)
        )
    surveiller(registry, metriques, fenetre_s=60, score_min=0.7, minimum=10)

    entree = registry.journal()[-1]
    assert entree["evenement"] == "rollback"
    assert entree["avant"]["canary"] == "v2.0.0" and entree["apres"]["canary"] is None


def test_surveiller_sans_metriques_explicites_fusionne_v1_et_v2(monkeypatch, tmp_path, registry):
    from ops.deploy import surveiller

    chemin_v1 = tmp_path / "metrics.jsonl"
    chemin_v2 = tmp_path / "metrics_v2.jsonl"
    monkeypatch.setenv("METRICS_PATH", str(chemin_v1))
    monkeypatch.setenv("METRICS_PATH_V2", str(chemin_v2))

    for _ in range(10):
        MetricsStore(chemin_v2).enregistrer(
            Mesure(ts=time.time(), version="v1.0.0", route="/analyse", latence_ms=100)
        )
    res = surveiller(registry, fenetre_s=60, minimum=10)
    assert res["mesures"] == 10


# --------------------------------------------- surveiller() suit les règles


def test_surveiller_seuil_latence_ajuste_par_les_regles(metriques, registry, monkeypatch, tmp_path):
    """Un seuil de latence abaissé via /pilotage/regles doit changer la
    décision de rollback : sans surcharge explicite, `surveiller` doit
    utiliser le seuil de la règle, pas un seuil codé en dur."""
    from ops.deploy import deployer_canary, surveiller

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)
    _ecrire_regles(monkeypatch, tmp_path, latence_p95="> 2 s")

    for _ in range(10):
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=2500, score=0.9)
        )
    res = surveiller(registry, metriques, fenetre_s=60, minimum=10)
    assert res["derive"] is True and "latence" in res["motif"] and res["rollback"] is True


def test_surveiller_critere_proportion_scores_faibles(metriques, registry, monkeypatch, tmp_path):
    """Sans `score_min` explicite, le critère par défaut est la proportion
    de scores < 0,6 (règle `score_faible`), pas la moyenne."""
    from ops.deploy import deployer_canary, surveiller

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)
    _ecrire_regles(monkeypatch, tmp_path, score_faible="> 20 % de scores < 0,6")

    # 3 scores sur 10 (30 %) sous 0,6 : au-dessus du seuil de 20 %.
    for i in range(10):
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=2500,
                   score=(0.2 if i < 3 else 0.9))
        )
    res = surveiller(registry, metriques, fenetre_s=60, minimum=10)
    assert res["derive"] is True and "score" in res["motif"]


def test_surveiller_critere_proportion_scores_faibles_sous_le_seuil_pas_de_derive(
    metriques, registry, monkeypatch, tmp_path
):
    from ops.deploy import deployer_canary, surveiller

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)
    _ecrire_regles(monkeypatch, tmp_path, score_faible="> 20 % de scores < 0,6")

    # 1 score sur 10 (10 %) sous 0,6 : en dessous du seuil de 20 %.
    for i in range(10):
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=2500,
                   score=(0.2 if i < 1 else 0.9))
        )
    res = surveiller(registry, metriques, fenetre_s=60, minimum=10)
    assert res["derive"] is False


def test_surveiller_critere_cout(metriques, registry, monkeypatch, tmp_path):
    from ops.deploy import deployer_canary, surveiller

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)
    _ecrire_regles(monkeypatch, tmp_path, cout_moyen="> 0,15 €")

    for _ in range(10):
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=2500,
                   score=0.9, cout_eur=0.20)
        )
    res = surveiller(registry, metriques, fenetre_s=60, minimum=10)
    assert res["derive"] is True and "coût" in res["motif"]


def test_surveiller_score_min_explicite_prioritaire_sur_la_regle(metriques, registry, monkeypatch, tmp_path):
    """`score_min` fourni explicitement doit primer sur la règle
    `score_faible` (compatibilité des appelants existants)."""
    from ops.deploy import deployer_canary, surveiller

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)
    # La règle seule déclencherait une dérive (30 % de scores bas > 20 %) ;
    # `score_min` explicite change le critère et n'est pas franchi ici.
    _ecrire_regles(monkeypatch, tmp_path, score_faible="> 20 % de scores < 0,6")

    for i in range(10):
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=2500,
                   score=(0.2 if i < 3 else 0.9))
        )
    res = surveiller(registry, metriques, fenetre_s=60, minimum=10, score_min=0.4)
    assert res["derive"] is False


def test_surveiller_cout_max_explicite_prioritaire_sur_la_regle(metriques, registry, monkeypatch, tmp_path):
    from ops.deploy import deployer_canary, surveiller

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)
    _ecrire_regles(monkeypatch, tmp_path, cout_moyen="> 0,05 €")  # la règle seule déclencherait

    for _ in range(10):
        metriques.enregistrer(
            Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=2500,
                   score=0.9, cout_eur=0.10)
        )
    res = surveiller(registry, metriques, fenetre_s=60, minimum=10, cout_moyen_max_eur=0.20)
    assert res["derive"] is False
