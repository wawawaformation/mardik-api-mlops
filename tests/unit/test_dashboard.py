"""Tests unitaires — ops/dashboard.py (resume/rendre_texte/rendre_html)."""
from __future__ import annotations

import time

from app.telemetry import Mesure, MetricsStore


def test_resume_agrege_par_version(metriques: MetricsStore, registry):
    from ops.dashboard import resume

    maintenant = time.time()
    for i in range(20):
        metriques.enregistrer(
            Mesure(ts=maintenant, version="v1.0.0", route="/analyse", latence_ms=800 + i * 10,
                   erreur=(i == 0), score=None, cout_eur=0.001)
        )
    for i in range(10):
        metriques.enregistrer(
            Mesure(ts=maintenant, version="v2.0.0", route="/analyse", latence_ms=3000 + i * 100,
                   erreur=False, score=0.8 + i * 0.01, cout_eur=0.02)
        )
    r = resume(metriques, fenetre_s=60, registry=registry)
    assert r["total"] == 30
    assert set(r["par_version"]) == {"v1.0.0", "v2.0.0"}
    assert r["par_version"]["v1.0.0"]["cout_total_eur"] == 0.019  # 19 requêtes sans erreur * 0.001, arrondi


def test_resume_fenetre_exclut_les_mesures_anciennes(metriques: MetricsStore, registry):
    from ops.dashboard import resume

    metriques.enregistrer(Mesure(ts=time.time() - 3600, version="v1.0.0", route="/analyse", latence_ms=100))
    r = resume(metriques, fenetre_s=60, registry=registry)
    assert r["total"] == 0
    assert r["par_version"] == {}


def test_resume_sans_trafic_ne_plante_pas(metriques: MetricsStore, registry):
    from ops.dashboard import resume

    r = resume(metriques, fenetre_s=60, registry=registry)
    assert r == {"fenetre_s": 60, "total": 0, "par_version": {}, "journal": []}


def test_resume_inclut_les_derniers_evenements_du_journal(metriques: MetricsStore, registry):
    from ops.dashboard import resume

    registry.journaliser("canary", version="v2.0.0", pourcentage=10)
    r = resume(metriques, fenetre_s=60, registry=registry)
    assert r["journal"][-1]["evenement"] == "canary"


def test_resume_sans_metriques_explicites_fusionne_v1_et_v2(monkeypatch, tmp_path, registry):
    """Sans ``metriques`` explicite, ``resume`` doit lire à la fois
    ``METRICS_PATH`` (v1) et ``METRICS_PATH_V2`` (v2) : le trafic du
    container ``v2`` ne doit pas être invisible du tableau de bord."""
    from ops.dashboard import resume

    chemin_v1 = tmp_path / "metrics.jsonl"
    chemin_v2 = tmp_path / "metrics_v2.jsonl"
    monkeypatch.setenv("METRICS_PATH", str(chemin_v1))
    monkeypatch.setenv("METRICS_PATH_V2", str(chemin_v2))

    MetricsStore(chemin_v1).enregistrer(
        Mesure(ts=time.time(), version="v1.0.0", route="/analyse", latence_ms=100)
    )
    MetricsStore(chemin_v2).enregistrer(
        Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=200)
    )

    r = resume(fenetre_s=60, registry=registry)
    assert r["total"] == 2
    assert set(r["par_version"]) == {"v1.0.0", "v2.0.0"}


def test_resume_distribution_score_par_version(metriques: MetricsStore, registry):
    """5 tranches de 0,2 par version, avec le nombre de mesures dans
    chacune — pas seulement la proportion sous le seuil."""
    from ops.dashboard import resume

    maintenant = time.time()
    for score in (0.1, 0.3, 0.3, 0.55, 0.7, 0.95, 1.0):
        metriques.enregistrer(
            Mesure(ts=maintenant, version="v2.0.0", route="/analyse", latence_ms=100, score=score)
        )
    r = resume(metriques, fenetre_s=60, registry=registry)
    tranches = r["par_version"]["v2.0.0"]["distribution_score"]
    assert [t["n"] for t in tranches] == [1, 2, 1, 1, 2]
    assert tranches[0]["borne_min"] == 0.0 and tranches[0]["borne_max"] == 0.2
    assert tranches[-1]["borne_min"] == 0.8 and tranches[-1]["borne_max"] == 1.0


def test_resume_distribution_score_sans_scores_est_a_zero(metriques: MetricsStore, registry):
    from ops.dashboard import resume

    metriques.enregistrer(
        Mesure(ts=time.time(), version="v1.0.0", route="/analyse", latence_ms=100, score=None)
    )
    r = resume(metriques, fenetre_s=60, registry=registry)
    assert [t["n"] for t in r["par_version"]["v1.0.0"]["distribution_score"]] == [0, 0, 0, 0, 0]


def test_rendre_texte_contient_les_versions():
    from ops.dashboard import rendre_texte

    r = {
        "fenetre_s": 60,
        "total": 1,
        "par_version": {
            "v2.0.0": {
                "requetes": 1, "trafic_pct": 100.0, "latence_p50_ms": 100.0,
                "latence_p95_ms": 100.0, "taux_erreur": 0.0, "score_moyen": 0.9,
                "cout_total_eur": 0.01,
            }
        },
        "journal": [],
    }
    texte = rendre_texte(r)
    assert "v2.0.0" in texte
    assert "100" in texte


def test_rendre_html_est_auto_rafraichie():
    from ops.dashboard import rendre_html

    html = rendre_html({"fenetre_s": 60, "total": 0, "par_version": {}, "journal": []})
    assert "<meta http-equiv=\"refresh\"" in html
    assert "<html" in html
