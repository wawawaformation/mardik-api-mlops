"""Serveur de pilotage : les 6 routes du contrat gelé
(`conception_figee/pilotage/openapi-pilotage.json`), réutilisant
`ops/registry/` existant (voir écart documenté dans
`docs/conception_revue/pilotage/formats-ops.md` et l'en-tête de
`ops/serveur_pilotage.py`).
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.llm_client import Bundle
from app.telemetry import Mesure, MetricsStore
from ops.registry import Registry


@pytest.fixture
def client(registry: Registry) -> TestClient:
    from ops.serveur_pilotage import creer_app_pilotage, get_registry

    app = creer_app_pilotage()
    app.dependency_overrides[get_registry] = lambda: registry
    return TestClient(app)


def _livrer_v2(registry: Registry, version: str = "v2.0.0") -> str:
    registry.etiqueter(version, Bundle.charger("v2"), commit="abc1234", note_eval=0.9)
    return version


def test_health_repond_200():
    from ops.serveur_pilotage import creer_app_pilotage

    r = TestClient(creer_app_pilotage()).get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_les_six_routes_du_contrat_sont_montees():
    from ops.serveur_pilotage import creer_app_pilotage

    chemins = {route.path for route in creer_app_pilotage().routes}
    assert {
        "/pilotage/dashboard",
        "/pilotage/regles",
        "/pilotage/regles/{signal}",
        "/pilotage/promotion",
        "/pilotage/rollback",
        "/pilotage/journal",
    } <= chemins


# ------------------------------------------------------------------ dashboard


def test_dashboard_agrege_le_trafic(client: TestClient, metriques: MetricsStore, registry: Registry):
    maintenant = time.time()
    for i in range(20):
        metriques.enregistrer(
            Mesure(ts=maintenant, version="v1.0.0", route="/analyse", latence_ms=800, score=None, cout_eur=0.001)
        )
    for i in range(10):
        metriques.enregistrer(
            Mesure(ts=maintenant, version="v2.0.0", route="/analyse", latence_ms=3000, score=0.5, cout_eur=0.02)
        )
    r = client.get("/pilotage/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert d["fenetre"]["requetes_observees"] == 30
    assert d["trafic"]["v1_pct"] == 66.7
    assert d["distribution_score"]["proportion_score_faible"] == 1.0  # tous les scores v2 à 0.5 < 0.6
    assert d["latence_p95_ms"] > 0


def test_dashboard_sans_trafic_ne_plante_pas(client: TestClient):
    r = client.get("/pilotage/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert d["fenetre"]["requetes_observees"] == 0
    assert d["trafic"] == {"v1_pct": 0.0, "v2_pct": 0.0}


# --------------------------------------------------------------------- règles


def test_regles_par_defaut(client: TestClient, monkeypatch, tmp_path):
    monkeypatch.setenv("REGLES_PILOTAGE_PATH", str(tmp_path / "regles.json"))
    r = client.get("/pilotage/regles")
    assert r.status_code == 200
    signaux = {regle["signal"] for regle in r.json()["regles"]}
    assert signaux == {"latence_p95", "taux_erreur", "score_faible", "canary"}


def test_ajuster_seuil_modifie_et_persiste(client: TestClient, monkeypatch, tmp_path, registry: Registry):
    monkeypatch.setenv("REGLES_PILOTAGE_PATH", str(tmp_path / "regles.json"))
    r = client.put("/pilotage/regles/latence_p95", json={"seuil": "> 9 s", "declencheur": "humain"})
    assert r.status_code == 200
    assert r.json()["seuil"] == "> 9 s"

    r2 = client.get("/pilotage/regles")
    regle = next(x for x in r2.json()["regles"] if x["signal"] == "latence_p95")
    assert regle["seuil"] == "> 9 s"

    entree = registry.journal()[-1]
    assert entree["evenement"] == "ajustement_seuil"
    assert entree["signal"] == "latence_p95" and entree["declencheur"] == "humain"


def test_ajuster_seuil_signal_inconnu_404(client: TestClient, monkeypatch, tmp_path):
    monkeypatch.setenv("REGLES_PILOTAGE_PATH", str(tmp_path / "regles.json"))
    r = client.put("/pilotage/regles/inconnu", json={"seuil": "> 1", "declencheur": "humain"})
    assert r.status_code == 404


def test_ajuster_seuil_declencheur_hors_enumeration_422(client: TestClient):
    r = client.put("/pilotage/regles/latence_p95", json={"seuil": "> 9 s", "declencheur": "robot"})
    assert r.status_code == 422


# ----------------------------------------------------------------- promotion


def test_promotion_palier_hors_enumeration_422(client: TestClient):
    r = client.post("/pilotage/promotion", json={"cible_pct": 75})
    assert r.status_code == 422


def test_promotion_sans_canary_409(client: TestClient):
    r = client.post("/pilotage/promotion", json={"cible_pct": 50})
    assert r.status_code == 409


def test_promotion_pas_assez_de_mesures_409(client: TestClient, registry: Registry):
    _livrer_v2(registry)
    from ops.deploy import deployer_canary

    deployer_canary("v2.0.0", pourcentage=10, registry=registry)
    r = client.post("/pilotage/promotion", json={"cible_pct": 50})
    assert r.status_code == 409


def test_promotion_criteres_non_tenus_409(client: TestClient, metriques: MetricsStore, registry: Registry):
    _livrer_v2(registry)
    from ops.deploy import deployer_canary

    deployer_canary("v2.0.0", pourcentage=10, registry=registry)
    maintenant = time.time()
    for _ in range(10):
        metriques.enregistrer(Mesure(ts=maintenant, version="v1.0.0", route="/analyse", latence_ms=800))
        metriques.enregistrer(
            Mesure(ts=maintenant, version="v2.0.0", route="/analyse", latence_ms=9000)  # > contrainte 8s
        )
    r = client.post("/pilotage/promotion", json={"cible_pct": 50})
    assert r.status_code == 409
    assert "latence" in r.json()["detail"]


def test_promotion_criteres_tenus_200(client: TestClient, metriques: MetricsStore, registry: Registry):
    _livrer_v2(registry)
    from ops.deploy import deployer_canary

    deployer_canary("v2.0.0", pourcentage=10, registry=registry)
    maintenant = time.time()
    for _ in range(10):
        metriques.enregistrer(Mesure(ts=maintenant, version="v1.0.0", route="/analyse", latence_ms=800, cout_eur=0.01))
        metriques.enregistrer(Mesure(ts=maintenant, version="v2.0.0", route="/analyse", latence_ms=600, cout_eur=0.01))
    r = client.post("/pilotage/promotion", json={"cible_pct": 50, "declencheur": "humain"})
    assert r.status_code == 200
    d = r.json()
    assert d["action"] == "promotion" and d["fingerprint_cible"] == "v2.0.0"
    assert registry.canary() == ("v2.0.0", 50)
    assert registry.journal()[-1]["declencheur"] == "humain"


def test_promotion_a_100_promeut_reellement(client: TestClient, metriques: MetricsStore, registry: Registry):
    _livrer_v2(registry)
    from ops.deploy import deployer_canary

    deployer_canary("v2.0.0", pourcentage=50, registry=registry)
    maintenant = time.time()
    for _ in range(10):
        metriques.enregistrer(Mesure(ts=maintenant, version="v1.0.0", route="/analyse", latence_ms=800, cout_eur=0.01))
        metriques.enregistrer(Mesure(ts=maintenant, version="v2.0.0", route="/analyse", latence_ms=600, cout_eur=0.01))
    r = client.post("/pilotage/promotion", json={"cible_pct": 100})
    assert r.status_code == 200
    assert registry.active() == "v2.0.0"
    assert registry.canary() == (None, 0)
    assert r.json()["nouvelle_repartition"] == {"v1_pct": 0, "v2_pct": 100}


# ----------------------------------------------------------------- rollback


def test_rollback_sans_declencheur_422(client: TestClient):
    r = client.post("/pilotage/rollback", json={"signal": "taux_erreur"})
    assert r.status_code == 422


def test_rollback_retire_le_canary(client: TestClient, registry: Registry):
    _livrer_v2(registry)
    from ops.deploy import deployer_canary

    deployer_canary("v2.0.0", pourcentage=20, registry=registry)
    r = client.post(
        "/pilotage/rollback", json={"declencheur": "auto", "signal": "taux_erreur", "valeur": "12 %"}
    )
    assert r.status_code == 200
    d = r.json()
    assert d["action"] == "rollback"
    assert registry.canary() == (None, 0)
    assert d["nouvelle_repartition"] == {"v1_pct": 100, "v2_pct": 0}

    entree = registry.journal()[-1]
    assert entree["evenement"] == "rollback" and entree["declencheur"] == "auto"


# ------------------------------------------------------------------- journal


def test_journal_accepte_les_parametres_du_contrat(client: TestClient):
    r = client.get("/pilotage/journal", params={"signal": "latence_p95", "limite": 10})
    assert r.status_code == 200
    assert r.json() == {"entrees": []}


def test_journal_reprend_les_decisions_du_registre(client: TestClient, registry: Registry):
    _livrer_v2(registry)
    from ops.deploy import deployer_canary

    deployer_canary("v2.0.0", pourcentage=20, registry=registry, declencheur="humain", signal="canary")
    r = client.get("/pilotage/journal")
    assert r.status_code == 200
    entrees = r.json()["entrees"]
    assert entrees[-1]["action"] == "canary"
    assert entrees[-1]["declencheur"] == "humain"
    assert entrees[-1]["fingerprint"] == "v2.0.0"


def test_journal_filtre_par_signal(client: TestClient, registry: Registry):
    registry.journaliser("ajustement_seuil", signal="latence_p95", seuil="> 9 s", declencheur="humain")
    registry.journaliser("ajustement_seuil", signal="taux_erreur", seuil="> 5 %", declencheur="humain")
    r = client.get("/pilotage/journal", params={"signal": "latence_p95"})
    entrees = r.json()["entrees"]
    assert len(entrees) == 1 and entrees[0]["signal"] == "latence_p95"


# ---------------------------------------------------------- enrichissement


def test_enrichissement_liste_les_cas_en_attente(client: TestClient):
    from ops.enrichissement import capturer

    capturer("texte A", clauses=[], confiance_globale=0.2, version="v2.0.0")
    r = client.get("/pilotage/enrichissement")
    assert r.status_code == 200
    cas = r.json()["cas"]
    assert len(cas) == 1
    assert cas[0]["texte"] == "texte A"


def test_enrichissement_liste_vide(client: TestClient):
    r = client.get("/pilotage/enrichissement")
    assert r.status_code == 200
    assert r.json() == {"cas": []}


def test_enrichissement_versement_201(client: TestClient, monkeypatch, tmp_path, registry: Registry):
    from ops.enrichissement import capturer

    monkeypatch.setenv("EVAL_CONTRATS_PATH", str(tmp_path / "contrats"))
    monkeypatch.setenv("EVAL_ATTENDUS_PATH", str(tmp_path / "attendus.jsonl"))
    cas_id = capturer("texte A", clauses=["durée"], confiance_globale=0.2, version="v2.0.0")

    r = client.post(
        f"/pilotage/enrichissement/{cas_id}",
        json={"clauses_attendues": ["durée", "prix et paiement"], "par": "juriste@example.com"},
    )
    assert r.status_code == 201
    assert r.json()["contrat_id"] == cas_id
    assert (tmp_path / "contrats" / f"{cas_id}.txt").exists()

    entree = registry.journal()[-1]
    assert entree["evenement"] == "enrichissement" and entree["par"] == "juriste@example.com"

    r2 = client.get("/pilotage/enrichissement")
    assert r2.json() == {"cas": []}


def test_enrichissement_versement_cas_inconnu_404(client: TestClient):
    r = client.post(
        "/pilotage/enrichissement/p-inconnu",
        json={"clauses_attendues": ["durée"], "par": "juriste@example.com"},
    )
    assert r.status_code == 404


def test_enrichissement_versement_id_deja_present_409(
    client: TestClient, monkeypatch, tmp_path
):
    from ops.enrichissement import capturer

    monkeypatch.setenv("EVAL_CONTRATS_PATH", str(tmp_path / "contrats"))
    monkeypatch.setenv("EVAL_ATTENDUS_PATH", str(tmp_path / "attendus.jsonl"))
    (tmp_path / "contrats").mkdir(parents=True)
    cas_id = capturer("texte A", clauses=[], confiance_globale=0.2, version="v2.0.0")
    (tmp_path / "contrats" / f"{cas_id}.txt").write_text("déjà là", encoding="utf-8")

    r = client.post(
        f"/pilotage/enrichissement/{cas_id}",
        json={"clauses_attendues": ["durée"], "par": "juriste@example.com"},
    )
    assert r.status_code == 409
