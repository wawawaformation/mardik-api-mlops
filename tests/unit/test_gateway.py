"""Tests unitaires — app/gateway.py (routage canary)."""
from __future__ import annotations

from app.gateway import choisir_version


def test_choisir_version_sans_canary_renvoie_active():
    assert choisir_version("v1.0.0", None, 0, 50) == "v1.0.0"


def test_choisir_version_tirage_sous_le_pourcentage_renvoie_canary():
    assert choisir_version("v1.0.0", "v2.0.0", 30, 29) == "v2.0.0"


def test_choisir_version_tirage_au_dessus_du_pourcentage_renvoie_active():
    assert choisir_version("v1.0.0", "v2.0.0", 30, 30) == "v1.0.0"


def test_choisir_version_repartition_exacte_sur_100_tirages():
    tirages = [choisir_version("v1.0.0", "v2.0.0", 30, t) for t in range(100)]
    assert tirages.count("v2.0.0") == 30


def test_etat_reflete_le_registre(registry):
    from fastapi.testclient import TestClient

    from app.gateway import get_registry, router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_registry] = lambda: registry
    r = TestClient(app).get("/gateway/etat")
    assert r.json() == {"active": "v1.0.0", "canary": None, "canary_percent": 0}


def test_etat_reflete_un_canary_deploye(registry):
    from fastapi.testclient import TestClient

    from app.gateway import get_registry, router
    from app.llm_client import Bundle
    from fastapi import FastAPI

    registry.etiqueter("v2.0.0", Bundle.charger("v2"), commit="abc1234", note_eval=0.9)
    registry.definir_canary("v2.0.0", 0)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_registry] = lambda: registry
    r = TestClient(app).get("/gateway/etat")
    assert r.json()["canary"] == "v2.0.0"


def test_analyse_suit_le_pourcentage_du_registre_malgre_canary_percent(client, registry, monkeypatch):
    """CANARY_PERCENT est la valeur par défaut du déploiement, pas un forçage du routage."""
    from app.llm_client import Bundle

    registry.etiqueter("v2.0.0", Bundle.charger("v2"), commit="abc1234", note_eval=0.9)
    registry.definir_canary("v2.0.0", 100)
    monkeypatch.setenv("CANARY_PERCENT", "0")
    texte = "Le présent contrat est soumis au droit français."
    versions = {client.post("/analyse", json={"texte": texte}).headers["x-mardik-version"] for _ in range(5)}
    assert versions == {"v2.0.0"}
