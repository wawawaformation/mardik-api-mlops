# Containers `v2` et `serveur_pilotage` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire tourner la v2 et le squelette du serveur de pilotage chacun dans son propre container docker-compose, sur un port hôte dédié (8001 et 8002), sans jamais modifier `app/api_v1.py` ni changer le comportement du service `app` existant.

**Architecture:** Un seul artefact Docker, plusieurs rôles (`docs/spec-v2.md` §4). Le rôle est choisi par la **commande de lancement**, pas par une variable d'environnement : `app/main.py` gagne une fabrique `create_app_v2()` qui ne monte que le router `api_v2`, lancée par `uvicorn app.main:create_app_v2 --factory`. Le serveur de pilotage est un nouveau module FastAPI autonome, `ops/serveur_pilotage.py`, qui monte les 6 routes du contrat gelé `conception_figee/pilotage/openapi-pilotage.json` en squelette : corps de requête validés par des modèles Pydantic repris fidèlement du contrat, puis `NotImplementedError` traduit en 501 par le même handler que `app/main.py`.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, uvicorn, pytest, Docker Compose. Aucune dépendance nouvelle : `fastapi` et `uvicorn[standard]` sont déjà dans `pyproject.toml`, `ops/` est déjà copié dans l'image (`Dockerfile`) et déclaré comme package (`[tool.hatch.build.targets.wheel]`).

**Spec de référence :** `docs/superpowers/specs/2026-09-21-v2-pilotage-containers-design.md`

## Global Constraints

- **Ne jamais modifier `app/api_v1.py`** ni son contrat. Il n'est pas lu par ce plan.
- **Ne jamais écrire dans `conception_figee/`** — dossier gelé, lecture seule (`MEMORY.md` §« Le dossier de conception est gelé »). `openapi-pilotage.json` sert de source pour les modèles Pydantic, rien de plus.
- **Ne jamais modifier `tests/conftest.py`, `tests/acceptance/*.py`, `tests/integration/*.py`, `ops/drift_proxy.py`, `app/llm_client.py`, `app/telemetry.py`** — tous `[FOURNI]`.
- **Aucune variable d'environnement ne pilote le rôle.** Décision de la spec (§Décisions, ligne « Restriction de `v2` à `/v2` ») : une variable perdue dans un shell, dans la CI ou dans le `.env` partagé par tous les services pourrait retirer `/v1` au service `app`, ce qui violerait `docs/spec-v2.md` §3 (« v1 jamais interrompue »). Le rôle vient de la commande uvicorn.
- **`create_app()` garde sa signature (`() -> FastAPI`) et son comportement observable exact** : les trois routers `api_v1`, `api_v2`, `gateway`, `/health`, le handler `NotImplementedError` → 501, et `app = create_app()` en bas du module. Task 1 en factorise les internes dans un helper privé partagé avec `create_app_v2()` — c'est le seul changement autorisé dans `app/main.py`, et les 37 tests verts existants en sont la garantie de non-régression.
- **Isolation au niveau du routage, pas des imports** : `app/main.py` continue d'importer `api_v1`, `api_v2` et `gateway` au chargement du module. Conforme à « un seul artefact » — ne pas tenter de rendre les imports conditionnels.
- **Contrat gelé du pilotage** : les 6 chemins et méthodes sont exactement `GET /pilotage/dashboard`, `GET /pilotage/regles`, `PUT /pilotage/regles/{signal}`, `POST /pilotage/promotion`, `POST /pilotage/rollback`, `GET /pilotage/journal`. Aucun autre, aucun renommage. `GET /health` est une **extension hors contrat, non normative**, nécessaire au healthcheck du container.
- **Le squelette du pilotage ne lit ni n'écrit aucun fichier** : pas de `MetricsStore`, pas de `Registry`, pas de `METRICS_PATH`/`REGISTRY_PATH`. La logique est le chantier 2.
- **Ports** : 8000 (`app`), 8080 (`proxy`), 8501 (`dashboard`) sont pris ; `azure-adapter` écoute sur 9000 sans le publier. Les nouveaux services prennent **8001** (`v2`) et **8002** (`serveur_pilotage`), tous deux → 8000 dans le container.
- **Métriques séparées** : le service `v2` écrit dans `/app/ops/metrics_v2.jsonl`, pas dans `/app/ops/metrics.jsonl`. Conséquence assumée : `ops/dashboard.py` et `ops/deploy.py::surveiller` ne lisent pas encore ce fichier (chantier 2).
- **Lint** : `ruff`, `line-length = 100`, `target-version = "py311"`. `uv run ruff check .` doit rester vert.
- **Baseline de non-régression** : avant ce plan, `MOCK=on uv run pytest -q` affiche **`7 failed, 37 passed`**. Ce plan ajoute **17 tests unitaires** (5 en Task 1, 12 en Task 2) ; à la fin, la commande doit afficher **`7 failed, 54 passed`**. Les 7 rouges sont attendus tant que `ops/deploy.py`, `eval/run_eval.py` et `ops/dashboard.py` sont des stubs — ce plan n'y touche pas.
- **`.env.example` n'est pas modifié** : ce plan n'introduit aucune variable d'environnement nouvelle. `METRICS_PATH` et `REGISTRY_PATH` existent déjà et sont fixés par service dans `docker-compose.yml`, pas dans `.env`. Si une tâche finit par ajouter une variable, `.env.example` doit être mis à jour dans la même tâche.
- **Aucun commit automatique.** Les étapes « Commit » de chaque tâche préparent la commande mais **ne l'exécutent pas** : elles sont regroupées et soumises à l'utilisateur en Task 6. Convention du dépôt : titre de commit en anglais, corps en français.

## File Structure

| Fichier | Rôle | Action |
| --- | --- | --- |
| `app/main.py` | Fabriques d'application : `create_app()` (rôle complet) + `create_app_v2()` (rôle v2) | Modifier |
| `tests/unit/test_fabrique_app_v2.py` | Tests de la fabrique `create_app_v2` et de la non-régression de `create_app` | Créer |
| `ops/serveur_pilotage.py` | Squelette FastAPI du serveur de pilotage : 6 routes du contrat gelé + `/health` | Créer |
| `tests/unit/test_serveur_pilotage.py` | Tests du squelette : 501 sur corps valide, 422 sur corps invalide | Créer |
| `docker-compose.yml` | Ajout des services `v2` (8001) et `serveur_pilotage` (8002) avec healthchecks | Modifier |
| `.gitignore` | Ignorer `ops/metrics_v2.jsonl` | Modifier |
| `Makefile` | `make clean` supprime aussi `ops/metrics_v2.jsonl` | Modifier |
| `CHANGELOG.md`, `TODO.md`, `MEMORY.md`, `docs/spec-v2.md` | Traçabilité des décisions | Modifier |

---

### Task 1: Fabrique `create_app_v2()` (rôle v2)

**Files:**

- Modify: `app/main.py` (fichier entier, 45 lignes)
- Test: `tests/unit/test_fabrique_app_v2.py` (créer)

**Interfaces:**

- Consumes: `app.api_v1.router`, `app.api_v2.router`, `app.gateway.router`, `app.telemetry.build_default_telemetry` (tous existants, inchangés).
- Produces:
  - `app.main.create_app() -> FastAPI` — inchangé : `/v1/analyse`, `/v2/analyse`, `/analyse`, `/gateway/etat`, `/health`.
  - `app.main.create_app_v2() -> FastAPI` — **nouveau** : `/v2/analyse` et `/health` seulement ; c'est la cible de la commande uvicorn du service `v2` en Task 3.
  - `app.main.app` — inchangé, produit par `create_app()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_fabrique_app_v2.py
"""Fabrique de rôle : le container `v2` ne sert que /v2 (+ /health).

Le rôle vient de la commande uvicorn (`app.main:create_app_v2 --factory`),
jamais d'une variable d'environnement : une variable perdue dans le `.env`
partagé retirerait `/v1` au service `app` (docs/spec-v2.md §3, v1 jamais
interrompue).

Pas de fixture d'environnement ici : l'autouse `environnement` de
`tests/conftest.py` (MOCK=on, DRIFT=off, LLM_PROVIDER=ollama, LLM_MODEL,
METRICS_PATH et REGISTRY_PATH en tmp_path, OTEL_TRACES=off) s'applique déjà
à tout `tests/`, y compris `tests/unit/`.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import api_v2
from app.main import create_app, create_app_v2
from app.telemetry import build_telemetry


def _client_v2(tmp_path) -> TestClient:
    """App du rôle v2, télémétrie surchargée pour ne pas écrire dans le vrai
    `ops/metrics.jsonl` (même précaution que `tests/unit/test_api_v2_analyser.py`)."""
    app = create_app_v2()
    app.dependency_overrides[api_v2.get_telemetry] = lambda: build_telemetry(
        span_exporter=InMemorySpanExporter(), metrics_path=tmp_path / "metrics.jsonl", level="INFO"
    )
    return TestClient(app)


def test_create_app_v2_analyse_un_contrat(tmp_path):
    """La route /v2/analyse est bien montée et fonctionnelle dans le rôle v2."""
    texte = "Article 1 — Objet\n\n" + ("Texte du contrat. " * 20)
    r = _client_v2(tmp_path).post("/v2/analyse", json={"texte": texte})
    assert r.status_code == 200
    assert r.json()["version"]


def test_create_app_v2_sans_route_v1(tmp_path):
    """Le contrat v1 n'est pas servi par ce rôle : 404, pas 422 ni 200."""
    r = _client_v2(tmp_path).post("/v1/analyse", json={"texte": "x" * 40})
    assert r.status_code == 404


def test_create_app_v2_sans_route_gateway(tmp_path):
    client = _client_v2(tmp_path)
    assert client.post("/analyse", json={"texte": "x" * 40}).status_code == 404
    assert client.get("/gateway/etat").status_code == 404


def test_create_app_v2_expose_health(tmp_path):
    """Nécessaire au healthcheck du container `v2` (docker-compose.yml)."""
    r = _client_v2(tmp_path).get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_app_conserve_les_trois_routers():
    """Non-régression du service `app` : la fabrique historique est intacte."""
    chemins = {route.path for route in create_app().routes}
    assert {"/v1/analyse", "/v2/analyse", "/analyse", "/gateway/etat", "/health"} <= chemins
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `MOCK=on uv run pytest tests/unit/test_fabrique_app_v2.py -v`
Expected: collection error — `ImportError: cannot import name 'create_app_v2' from 'app.main'`. Les 5 tests sont en erreur, aucun ne passe.

- [ ] **Step 3: Rewrite `app/main.py`**

Remplacer **tout** le contenu de `app/main.py` par :

```python
"""Application FastAPI — [FOURNI], étendu (fabrique de rôle, 2026-09-21).

* ``/v1`` est branché et fonctionnel (le contrat historique) ;
* ``/v2`` et ``/analyse`` (gateway) sont branchés sur des stubs : tant qu'un
  module lève ``NotImplementedError``, la route répond **501** avec le nom du
  chantier restant — jamais un 500 muet.

Deux fabriques, un seul artefact (``docs/spec-v2.md`` §4) :

* ``create_app()`` — rôle complet, service ``app`` du compose (port 8000) ;
* ``create_app_v2()`` — rôle « v2 », service ``v2`` du compose (port 8001).

Le rôle est choisi par la **commande uvicorn**, jamais par une variable
d'environnement : le ``.env`` est partagé par tous les services du compose,
une variable de rôle qui s'y glisserait retirerait ``/v1`` au service ``app``.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from app import api_v1, api_v2, gateway
from app.telemetry import build_default_telemetry


def _creer(*, titre: str, routers: tuple[APIRouter, ...]) -> FastAPI:
    """Partie commune à tous les rôles : télémétrie, routers, /health, 501."""
    app = FastAPI(title=titre, version="2.0.0")
    build_default_telemetry()

    for router in routers:
        app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "provider": os.environ.get("LLM_PROVIDER", "ollama"),
            "mock": os.environ.get("MOCK", "off"),
        }

    @app.exception_handler(NotImplementedError)
    async def _non_implemente(request: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(
            status_code=501,
            content={"detail": f"à implémenter : {exc or 'module non implémenté'}"},
        )

    return app


def create_app() -> FastAPI:
    """Rôle complet : ``/v1``, ``/v2`` et la gateway (service ``app``)."""
    return _creer(
        titre="Mardik — analyse de contrats",
        routers=(api_v1.router, api_v2.router, gateway.router),
    )


def create_app_v2() -> FastAPI:
    """Rôle « v2 » : ``/v2`` seulement (service ``v2``, port hôte 8001)."""
    return _creer(
        titre="Mardik — analyse de contrats (rôle v2)",
        routers=(api_v2.router,),
    )


app = create_app()
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `MOCK=on uv run pytest tests/unit/test_fabrique_app_v2.py -v`
Expected: `5 passed`

- [ ] **Step 5: Run the whole suite to prove `create_app()` did not change**

Run: `MOCK=on uv run pytest -q`
Expected: `7 failed, 42 passed` (37 verts d'avant + les 5 nouveaux ; les 7 rouges sont inchangés : `test_etiquetage_version_apres_gate`, `test_gate_evaluation_note_par_version`, `test_rollback_en_une_operation`, `test_promotion_canary_puis_totale`, `test_evaluation_enrichie_latence_et_cout`, `test_dashboard_par_version`, `test_journal_derive_et_rollback_automatique`).
**Si un huitième test devient rouge, arrêter** : la factorisation de `create_app()` a changé un comportement.

- [ ] **Step 6: Lint**

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 7: Prepare the commit (do NOT run it)**

Noter la commande, sans l'exécuter (voir Task 6) :

```bash
git add app/main.py tests/unit/test_fabrique_app_v2.py
```

---

### Task 2: Squelette du serveur de pilotage (`ops/serveur_pilotage.py`)

**Files:**

- Create: `ops/serveur_pilotage.py`
- Test: `tests/unit/test_serveur_pilotage.py` (créer)
- Read-only reference: `conception_figee/pilotage/openapi-pilotage.json` (gelé — **ne jamais écrire dedans**)

**Interfaces:**

- Consumes: rien du projet (aucune dépendance à `app/` ni à `ops/registry`, `ops/dashboard`). FastAPI + Pydantic uniquement.
- Produces:
  - `ops.serveur_pilotage.creer_app_pilotage() -> FastAPI` — fabrique, pour les tests.
  - `ops.serveur_pilotage.app` — instance de module, cible de la commande uvicorn en Task 3.
  - Modèles de corps : `AjustementSeuil(seuil: str, declencheur: Literal["auto","humain"])`, `Promotion(cible_pct: Literal[50,100], declencheur: Literal["auto","humain"] | None)`, `Rollback(declencheur: Literal["auto","humain"], signal: str | None, valeur: str | None)`.

**Schémas repris du contrat gelé** (`openapi-pilotage.json`, `components.schemas`) — à reproduire fidèlement :

| Schéma | Champs requis | Champs optionnels | Énumérations |
| --- | --- | --- | --- |
| `AjustementSeuil` | `seuil` (string), `declencheur` (string) | — | `declencheur` ∈ {`auto`, `humain`} |
| `Promotion` | `cible_pct` (integer) | `declencheur` (string) | `cible_pct` ∈ {50, 100} ; `declencheur` ∈ {`auto`, `humain`} |
| `Rollback` | `declencheur` (string) | `signal` (string), `valeur` (string) | `declencheur` ∈ {`auto`, `humain`} |

Paramètres hors corps, repris du contrat : `PUT /pilotage/regles/{signal}` → `signal` en chemin, `type: string`, **sans énumération** (l'énumération des signaux vit dans le schéma `Regle`, pas sur ce paramètre — ne pas la restreindre ici). `GET /pilotage/journal` → `signal` (query, optionnel, string) et `limite` (query, optionnel, integer, **défaut 100**).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_serveur_pilotage.py
"""Squelette du serveur de pilotage : les 6 routes du contrat gelé
(`conception_figee/pilotage/openapi-pilotage.json`) répondent 501, et les 3
routes d'écriture valident leur corps AVANT de lever (corps invalide → 422).

Aucune logique métier ici : lecture de `metrics.jsonl`, décisions, écriture
du registre et du journal sont le chantier 2.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from ops.serveur_pilotage import creer_app_pilotage

client = TestClient(creer_app_pilotage())


def test_health_repond_200():
    """Extension hors contrat gelé, nécessaire au healthcheck du container."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_les_six_routes_du_contrat_sont_montees():
    """Garde-fou contre une faute de frappe sur un chemin du contrat gelé."""
    chemins = {route.path for route in creer_app_pilotage().routes}
    assert {
        "/pilotage/dashboard",
        "/pilotage/regles",
        "/pilotage/regles/{signal}",
        "/pilotage/promotion",
        "/pilotage/rollback",
        "/pilotage/journal",
    } <= chemins


def test_dashboard_501():
    r = client.get("/pilotage/dashboard")
    assert r.status_code == 501
    assert "detail" in r.json()


def test_regles_501():
    r = client.get("/pilotage/regles")
    assert r.status_code == 501
    assert "detail" in r.json()


def test_journal_501():
    r = client.get("/pilotage/journal")
    assert r.status_code == 501
    assert "detail" in r.json()


def test_journal_accepte_les_parametres_du_contrat():
    """`signal` et `limite` sont optionnels (limite: défaut 100)."""
    r = client.get("/pilotage/journal", params={"signal": "latence_p95", "limite": 10})
    assert r.status_code == 501


def test_ajuster_seuil_corps_valide_501():
    r = client.put(
        "/pilotage/regles/latence_p95",
        json={"seuil": "> 9 s", "declencheur": "humain"},
    )
    assert r.status_code == 501
    assert "detail" in r.json()


def test_ajuster_seuil_declencheur_hors_enumeration_422():
    r = client.put(
        "/pilotage/regles/latence_p95",
        json={"seuil": "> 9 s", "declencheur": "robot"},
    )
    assert r.status_code == 422


def test_promotion_corps_valide_501():
    r = client.post("/pilotage/promotion", json={"cible_pct": 50, "declencheur": "humain"})
    assert r.status_code == 501
    assert "detail" in r.json()


def test_promotion_palier_hors_enumeration_422():
    """Le contrat gelé n'autorise que les paliers 50 et 100."""
    r = client.post("/pilotage/promotion", json={"cible_pct": 75})
    assert r.status_code == 422


def test_rollback_corps_valide_501():
    r = client.post(
        "/pilotage/rollback",
        json={"declencheur": "auto", "signal": "taux_erreur", "valeur": "12 %"},
    )
    assert r.status_code == 501
    assert "detail" in r.json()


def test_rollback_sans_declencheur_422():
    """`declencheur` est le seul champ requis du schéma gelé `Rollback`."""
    r = client.post("/pilotage/rollback", json={"signal": "taux_erreur"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `MOCK=on uv run pytest tests/unit/test_serveur_pilotage.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'ops.serveur_pilotage'`. Les 12 tests sont en erreur.

- [ ] **Step 3: Create `ops/serveur_pilotage.py`**

```python
"""Serveur de pilotage — SQUELETTE (chantier 2).

Contrat gelé : ``conception_figee/pilotage/openapi-pilotage.json``. Ce module
monte les 6 routes du contrat et **rien d'autre** ; chaque route valide son
entrée (modèles Pydantic repris du contrat) puis lève ``NotImplementedError``,
traduit en 501 par le handler — jamais un 500 muet, même mécanisme que
``app/main.py``.

Un corps de requête invalide est donc refusé en **422** avant d'atteindre le
handler ; un corps valide obtient **501**. C'est volontaire : le contrat est
respecté dès le squelette.

À ce stade le module **ne lit ni n'écrit aucun fichier** : la lecture de
``ops/metrics.jsonl``, les décisions, l'écriture du registre et du journal de
pilotage, la régénération du Caddyfile sont le chantier 2.

Lancement : ``uvicorn ops.serveur_pilotage:app --host 0.0.0.0 --port 8000``
(service ``serveur_pilotage`` du docker-compose, port hôte 8002).
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/pilotage", tags=["pilotage"])


class AjustementSeuil(BaseModel):
    """Corps de ``PUT /pilotage/regles/{signal}`` — schéma gelé ``AjustementSeuil``."""

    seuil: str
    declencheur: Literal["auto", "humain"]


class Promotion(BaseModel):
    """Corps de ``POST /pilotage/promotion`` — schéma gelé ``Promotion``.

    ``cible_pct`` est le palier canary suivant : 10 → 50 → 100 %, donc seuls
    50 et 100 sont demandables."""

    cible_pct: Literal[50, 100]
    declencheur: Literal["auto", "humain"] | None = None


class Rollback(BaseModel):
    """Corps de ``POST /pilotage/rollback`` — schéma gelé ``Rollback``.

    ``signal`` et ``valeur`` documentent la cause quand le rollback est
    automatique ; le contrat ne les rend pas obligatoires."""

    declencheur: Literal["auto", "humain"]
    signal: str | None = None
    valeur: str | None = None


@router.get("/dashboard")
def lire_dashboard() -> dict[str, Any]:
    raise NotImplementedError("pilotage.lire_dashboard — GET /pilotage/dashboard")


@router.get("/regles")
def lire_regles() -> dict[str, Any]:
    raise NotImplementedError("pilotage.lire_regles — GET /pilotage/regles")


@router.put("/regles/{signal}")
def ajuster_seuil(signal: str, ajustement: AjustementSeuil) -> dict[str, Any]:
    raise NotImplementedError("pilotage.ajuster_seuil — PUT /pilotage/regles/{signal}")


@router.post("/promotion")
def promouvoir(promotion: Promotion) -> dict[str, Any]:
    raise NotImplementedError("pilotage.promouvoir — POST /pilotage/promotion")


@router.post("/rollback")
def rollback(demande: Rollback) -> dict[str, Any]:
    raise NotImplementedError("pilotage.rollback — POST /pilotage/rollback")


@router.get("/journal")
def lire_journal(signal: str | None = None, limite: int = 100) -> dict[str, Any]:
    raise NotImplementedError("pilotage.lire_journal — GET /pilotage/journal")


def creer_app_pilotage() -> FastAPI:
    app = FastAPI(title="Mardik — serveur de pilotage", version="1.0.0")
    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Hors contrat gelé, non normative : sert le healthcheck du container."""
        return {"status": "ok", "role": "pilotage"}

    @app.exception_handler(NotImplementedError)
    async def _non_implemente(request: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(
            status_code=501,
            content={"detail": f"à implémenter : {exc or 'module non implémenté'}"},
        )

    return app


app = creer_app_pilotage()
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `MOCK=on uv run pytest tests/unit/test_serveur_pilotage.py -v`
Expected: `12 passed`

- [ ] **Step 5: Check the routes against the frozen contract (read-only)**

Run:

```bash
uv run python -c "
import json
from ops.serveur_pilotage import creer_app_pilotage
gele = json.load(open('../conception_figee/pilotage/openapi-pilotage.json'))
attendu = {(m.upper(), p) for p, ops in gele['paths'].items() for m in ops}
obtenu = {(m, r.path) for r in creer_app_pilotage().routes
          if r.path.startswith('/pilotage') for m in r.methods}
print('manquant :', sorted(attendu - obtenu))
print('en trop  :', sorted(obtenu - attendu))
"
```

Expected: `manquant : []` et `en trop  : []`.
Le chemin `../conception_figee/...` suppose que la commande est lancée depuis la racine du dépôt `mardik-api-mlops/` — `conception_figee/` est le dossier voisin, en **lecture seule**.

- [ ] **Step 6: Run the whole suite and lint**

Run: `MOCK=on uv run pytest -q && uv run ruff check .`
Expected: `7 failed, 54 passed` puis `All checks passed!`

- [ ] **Step 7: Prepare the commit (do NOT run it)**

```bash
git add ops/serveur_pilotage.py tests/unit/test_serveur_pilotage.py
```

---

### Task 3: Services `v2` et `serveur_pilotage` dans le docker-compose

**Files:**

- Modify: `docker-compose.yml` (ajout de deux services ; **aucun service existant n'est touché**)

**Interfaces:**

- Consumes: `app.main:create_app_v2` (Task 1) et `ops.serveur_pilotage:app` (Task 2).
- Produces: deux services healthy, `v2` sur `localhost:8001` et `serveur_pilotage` sur `localhost:8002`, consommés par la vérification réelle de Task 4.

- [ ] **Step 1: Add the `v2` service**

Insérer ce bloc **après** le service `app` (juste avant le commentaire `# Le proxy de dérive...`), sans rien modifier au-dessus :

```yaml
  # La v2 seule, dans son propre container (rôle « v2 » — docs/spec-v2.md §4).
  # Même image que `app` : un artefact, un rôle par container. Le rôle vient de
  # la commande (--factory), jamais d'une variable d'environnement.
  v2:
    build: .
    command: uvicorn app.main:create_app_v2 --factory --host 0.0.0.0 --port 8000
    ports:
      - "8001:8000"
    env_file: .env
    environment:
      LLM_PROXY_URL: http://proxy:8080
      METRICS_PATH: /app/ops/metrics_v2.jsonl   # journal distinct de celui d'`app`
      REGISTRY_PATH: /app/ops/registry
    volumes:
      - ./ops:/app/ops
      - ./models:/app/models
      - ./eval:/app/eval
    depends_on:
      - proxy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]
      interval: 5s
      timeout: 3s
      retries: 12
      start_period: 5s
```

Deux points à ne pas « corriger » par mimétisme avec le service `app` :

- **pas de `extra_hosts`** : tous les appels LLM passent par le proxy (`LLM_PROXY_URL`, voir `app/llm_client.py`, attribut `proxy_url`), et c'est le service `proxy` qui porte `host.docker.internal`. Inutile ici.
- **`METRICS_PATH` différent** : c'est la décision de la spec (§Décisions, « Métriques de `v2` »), pas une faute de copie.

- [ ] **Step 2: Add the `serveur_pilotage` service**

Insérer ce bloc **à la fin du fichier**, après le service `dashboard` (qui reste inchangé — l'arbitrage `ops/dashboard.py` vs `/pilotage/dashboard` est renvoyé au chantier 2) :

```yaml
  # Le serveur de pilotage — SQUELETTE (ops/serveur_pilotage.py) : les 6 routes
  # du contrat gelé répondent 501, la logique est le chantier 2. Ni env_file ni
  # METRICS_PATH : à ce stade le module ne lit et n'écrit aucun fichier.
  serveur_pilotage:
    build: .
    command: uvicorn ops.serveur_pilotage:app --host 0.0.0.0 --port 8000
    ports:
      - "8002:8000"
    volumes:
      - ./ops:/app/ops
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]
      interval: 5s
      timeout: 3s
      retries: 12
      start_period: 5s
```

Le healthcheck passe par Python et non `curl` : l'image `python:3.11-slim` (`Dockerfile`) n'embarque pas `curl`. `urlopen` lève `HTTPError` sur tout statut non-2xx, donc un code de sortie non nul — c'est exactement ce qu'attend Docker.

- [ ] **Step 3: Validate the compose file without starting anything**

Run: `docker compose config --quiet && docker compose config --services`
Expected: aucune erreur, et la liste `app`, `proxy`, `azure-adapter`, `dashboard`, `v2`, `serveur_pilotage`.

- [ ] **Step 4: Check there is no host port collision**

Run: `docker compose config | grep -E "published|target"`
Expected: 8000, 8080, 8501 (existants) + 8001 et 8002 (nouveaux), chacun une seule fois. 9000 (`azure-adapter`) n'apparaît pas : il n'est pas publié.

- [ ] **Step 5: Prepare the commit (do NOT run it)**

```bash
git add docker-compose.yml
```

---

### Task 4: `ops/metrics_v2.jsonl` — `.gitignore` et `make clean`

**Files:**

- Modify: `.gitignore` (section « Généré à l'exécution », après la ligne `ops/metrics.jsonl`)
- Modify: `Makefile` (cible `clean`)

**Interfaces:**

- Consumes: le chemin `ops/metrics_v2.jsonl` introduit par le service `v2` en Task 3.
- Produces: rien qu'une autre tâche consomme.

- [ ] **Step 1: Ignore the new metrics file**

Dans `.gitignore`, section `# Généré à l'exécution`, ajouter la ligne juste après `ops/metrics.jsonl` :

```gitignore
ops/metrics.jsonl
ops/metrics_v2.jsonl
ops/registry/journal.jsonl
```

- [ ] **Step 2: Clean it too**

Dans le `Makefile`, remplacer la première ligne de la cible `clean` :

```makefile
clean:
	rm -rf .pytest_cache .ruff_cache ops/metrics.jsonl ops/metrics_v2.jsonl eval/history.jsonl eval/.metrics_eval.jsonl
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
```

- [ ] **Step 3: Verify the ignore rule actually matches**

Run: `git check-ignore -v ops/metrics_v2.jsonl`
Expected: une ligne de la forme `.gitignore:32:ops/metrics_v2.jsonl	ops/metrics_v2.jsonl` (le numéro de ligne exact dépend de l'insertion).

- [ ] **Step 4: Verify `make clean` does not break**

Run: `make clean && MOCK=on uv run pytest -q`
Expected: `make clean` sans erreur (le fichier peut ne pas exister, `rm -rf` ne s'en plaint pas), puis `7 failed, 54 passed`.

- [ ] **Step 5: Prepare the commit (do NOT run it)**

```bash
git add .gitignore Makefile
```

---

### Task 5: Vérification réelle sur les containers

**Files:** aucun fichier modifié — cette tâche exécute et constate.

**Interfaces:**

- Consumes: les services de Task 3.
- Produces: la preuve que le critère §Vérification 4 de la spec est tenu.

**Pré-requis :** le fournisseur LLM configuré dans `.env` doit être joignable — `MEMORY.md` §Environnement technique indique `LLM_PROVIDER=azure` via `ops/azure_adapter.py`. Le seul appel de cette tâche qui sollicite le LLM est `POST localhost:8000/v1/analyse`. Si le fournisseur est indisponible, il répond **503** (erreur explicite, jamais 500) : noter le 503, ne pas conclure à une régression, et rejouer l'étape quand le fournisseur est revenu. Tous les autres contrôles sont hors LLM.

- [ ] **Step 1: Build and start the stack, waiting for the healthchecks**

Run: `docker compose up -d --build --wait`
Expected: la commande rend la main sans erreur ; `v2` et `serveur_pilotage` sont `healthy`. En cas d'échec de `--wait`, lire les logs avant toute modification : `docker compose logs v2 serveur_pilotage --tail 50`.

- [ ] **Step 2: Check the container states**

Run: `docker compose ps`
Expected: 6 services `running`, dont `v2` et `serveur_pilotage` en `(healthy)`, avec les mappings `0.0.0.0:8001->8000/tcp` et `0.0.0.0:8002->8000/tcp`.

- [ ] **Step 3: Verify the `v2` container (port 8001)**

Run:

```bash
curl -s -o /dev/null -w "health=%{http_code}\n" localhost:8001/health
curl -s -o /dev/null -w "v1=%{http_code}\n" -X POST localhost:8001/v1/analyse \
  -H 'Content-Type: application/json' -d '{"texte":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}'
```

Expected:

```text
health=200
v1=404
```

- [ ] **Step 4: Verify the `serveur_pilotage` container (port 8002)**

Run:

```bash
curl -s -o /dev/null -w "health=%{http_code}\n" localhost:8002/health
curl -s -o /dev/null -w "journal=%{http_code}\n" localhost:8002/pilotage/journal
curl -s -o /dev/null -w "rollback_valide=%{http_code}\n" -X POST localhost:8002/pilotage/rollback \
  -H 'Content-Type: application/json' -d '{"declencheur":"humain"}'
curl -s -o /dev/null -w "rollback_invalide=%{http_code}\n" -X POST localhost:8002/pilotage/rollback \
  -H 'Content-Type: application/json' -d '{"signal":"taux_erreur"}'
```

Expected:

```text
health=200
journal=501
rollback_valide=501
rollback_invalide=422
```

- [ ] **Step 5: Verify the `app` service did not regress (port 8000)**

Run:

```bash
curl -s -o /dev/null -w "health=%{http_code}\n" localhost:8000/health
curl -s -o /dev/null -w "v1=%{http_code}\n" -X POST localhost:8000/v1/analyse \
  -H 'Content-Type: application/json' \
  -d '{"texte":"Article 1 — Objet. Le present contrat definit les obligations des parties."}'
curl -s -o /dev/null -w "gateway=%{http_code}\n" localhost:8000/gateway/etat
```

Expected:

```text
health=200
v1=200
gateway=501
```

C'est le contrôle le plus important du plan : il prouve que la contrainte « v1 jamais interrompue » (`docs/spec-v2.md` §3) tient après la modification de `app/main.py`. (`v1=503` = fournisseur LLM injoignable, voir le pré-requis — ce n'est pas une régression, mais l'étape doit être rejouée avant de clore le plan.)

- [ ] **Step 6: Check that the two metrics journals are really separate**

Run:

```bash
ls -l ops/metrics.jsonl ops/metrics_v2.jsonl 2>&1
curl -s -o /dev/null -X POST localhost:8001/v2/analyse -H 'Content-Type: application/json' \
  -d '{"texte":"Article 1 — Objet. Le present contrat definit les obligations des parties."}'
wc -l ops/metrics_v2.jsonl
```

Expected: après l'appel sur 8001, `ops/metrics_v2.jsonl` existe et a gagné une ligne, tandis que `ops/metrics.jsonl` n'a pas bougé. (Si le fournisseur LLM est injoignable, la route répond 503 et une `Mesure` d'erreur est tout de même écrite dans `metrics_v2.jsonl` : le contrôle de séparation reste valable.)

- [ ] **Step 7: Stop the stack**

Run: `docker compose down`
Expected: les 6 containers sont arrêtés et supprimés.

- [ ] **Step 8: Nothing to commit**

Cette tâche ne modifie aucun fichier suivi par git. Si l'un des contrôles a révélé un défaut, le corriger dans la tâche concernée (1, 2 ou 3) et rejouer cette tâche entièrement.

---

### Task 6: Documentation et demande d'accord pour committer

**Files:**

- Modify: `CHANGELOG.md` (nouvelle entrée en tête)
- Modify: `TODO.md` (sections « Chantier 2 — Pilotage » et « Environnement »)
- Modify: `MEMORY.md` (section « État de l'implémentation » ou une nouvelle section dédiée)
- Modify: `docs/spec-v2.md` (§4, avant le paragraphe `Source : ...` de la ligne 84)

**Interfaces:** aucune — tâche de traçabilité, conforme à `CLAUDE.md` (« Décisions de conception : toujours les consigner dans les docs dédiés + `MEMORY.md` + `CHANGELOG.md`, jamais seulement dans la discussion »).

- [ ] **Step 1: Add the CHANGELOG entry**

Insérer juste après la ligne `> Tracé horodaté, ordre inverse (plus récent en premier).` et sa ligne vide, **avant** l'entrée `## 2026-09-21 (chantier 1 point 2 ...)` :

```markdown
## 2026-09-21 (topologie : containers `v2` et `serveur_pilotage`, ports distincts)

- Première étape concrète vers la topologie cible de `docs/spec-v2.md` §4
  (« un artefact, un rôle par container ») : deux nouveaux services dans
  `docker-compose.yml`, chacun sur son port hôte, à partir de la **même
  image** que `app`. Conception :
  `docs/superpowers/specs/2026-09-21-v2-pilotage-containers-design.md`,
  plan : `docs/superpowers/plans/2026-09-21-v2-pilotage-containers.md`.
- **`app/main.py`** gagne une fabrique `create_app_v2()` qui ne monte que le
  router `api_v2` (+ `/health`, télémétrie et handler 501, factorisés dans un
  helper privé `_creer` partagé avec `create_app`). `create_app()`, son
  comportement et `app = create_app()` sont inchangés — les 37 tests verts
  préexistants le vérifient. `app/api_v1.py` n'a pas été touché.
- **Décision : le rôle vient de la commande uvicorn, pas d'une variable
  d'environnement.** Une variable `ROLE` avait été envisagée puis écartée en
  relecture critique : `.env` est partagé par tous les services du compose et
  `tests/conftest.py` [FOURNI] ne la neutralise pas, donc une variable perdue
  dans un shell, dans la CI ou dans `.env` aurait pu retirer `/v1` au service
  `app` — en contradiction avec `docs/spec-v2.md` §3 (« v1 jamais
  interrompue »). `--factory` supprime le problème à la racine.
- **`ops/serveur_pilotage.py`** (nouveau) : squelette FastAPI du serveur de
  pilotage. Les 6 routes du contrat gelé
  (`conception_figee/pilotage/openapi-pilotage.json`) répondent **501** ; les
  3 routes d'écriture déclarent les modèles Pydantic du contrat
  (`AjustementSeuil`, `Promotion`, `Rollback`), donc un corps invalide est
  refusé en **422** avant le handler. `GET /health` est une extension hors
  contrat, non normative, nécessaire au healthcheck. Le module ne lit et
  n'écrit aucun fichier à ce stade.
- **Décision : `METRICS_PATH=/app/ops/metrics_v2.jsonl` pour le service
  `v2`.** `app` et `v2` servent tous deux `/v2/analyse` et la dataclasse
  `Mesure` (`app/telemetry.py` [FOURNI]) n'a aucun champ identifiant le
  container : sans journaux distincts, les mesures des deux instances
  seraient indiscernables pour `ops/dashboard.py::resume` et
  `ops/deploy.py::surveiller`. Conséquence assumée : ces deux modules ne
  lisent pas encore `metrics_v2.jsonl` — leur adaptation est le chantier 2.
  `.gitignore` et `make clean` couvrent le nouveau fichier.
- Healthchecks Python (`urllib.request`) sur `/health` pour les deux nouveaux
  services : l'image `python:3.11-slim` n'embarque pas `curl`, et
  `docker compose up -d --build --wait` ne doit rendre la main qu'une fois
  les services prêts.
- Le service `dashboard` (8501) reste **inchangé** : l'arbitrage entre
  `ops/dashboard.py` et la route `/pilotage/dashboard` du contrat gelé est
  explicitement renvoyé au chantier 2.
- Tests : 17 tests unitaires ajoutés (`tests/unit/test_fabrique_app_v2.py`,
  5 ; `tests/unit/test_serveur_pilotage.py`, 12).
  `MOCK=on uv run pytest -q` → **54 passed, 7 failed** (contre 37/7 avant ;
  les 7 rouges sont inchangés, ils attendent `ops/deploy.py`,
  `eval/run_eval.py` et `ops/dashboard.py`). `uv run ruff check .` vert.
- Vérification réelle : `docker compose up -d --build --wait` puis
  `localhost:8001/health` → 200, `POST localhost:8001/v1/analyse` → 404,
  `localhost:8002/health` → 200, `localhost:8002/pilotage/journal` → 501,
  et non-régression de `app` : `localhost:8000/health` → 200,
  `POST localhost:8000/v1/analyse` → 200, `localhost:8000/gateway/etat` → 501.
```

- [ ] **Step 2: Update `TODO.md`**

Dans la section `## Chantier 2 — Pilotage`, ajouter en tête de liste :

```markdown
- [x] Squelette `ops/serveur_pilotage.py` : 6 routes du contrat gelé en 501,
      corps validés par les modèles Pydantic du contrat, `/health` pour le
      healthcheck (service compose `serveur_pilotage`, port hôte 8002)
- [ ] Logique du serveur de pilotage : lecture de `ops/metrics.jsonl`,
      décisions (fenêtre 120 s / 300 s, minimum 10 mesures — voir
      `docs/conception_revue/pilotage/fenetre-glissante-seuils.md`), écriture
      du registre et de `ops/journal_pilotage.jsonl`, régénération du Caddyfile
- [ ] Arbitrage `ops/dashboard.py` (service `dashboard`, 8501) vs la route
      `GET /pilotage/dashboard` du contrat gelé — deux tableaux de bord
      coexistent depuis l'ajout du service `serveur_pilotage`
- [ ] Faire lire `ops/metrics_v2.jsonl` (service `v2`) par `ops/dashboard.py`
      et `ops/deploy.py::surveiller`, qui ne connaissent que
      `ops/metrics.jsonl` — condition pour que le trafic du container `v2`
      soit visible dans la surveillance
```

Dans la section `## Environnement`, ajouter :

```markdown
- [x] Containers `v2` (8001) et `serveur_pilotage` (8002) ajoutés au
      `docker-compose.yml`, healthchecks Python sur `/health`, vérifiés avec
      `docker compose up -d --build --wait`
- [ ] Topologie cible complète de `docs/spec-v2.md` §4 : container v1 isolé,
      container gateway, Caddy en frontal — non entamée
```

- [ ] **Step 3: Update `MEMORY.md`**

Ajouter une section juste avant `## En cours / point ouvert (2026-09-21)` :

```markdown
## Topologie — où en est-on de « un artefact, un rôle par container » (2026-09-21)

`docs/spec-v2.md` §4 vise un artefact Docker unique et un rôle par container
(v1, v2, gateway) derrière Caddy. **Partiellement en place** :

| Service compose | Port hôte → container | Rôle |
|---|---|---|
| `app` | 8000 → 8000 | complet (v1 + v2 + gateway), confort de dev — inchangé |
| `v2` | 8001 → 8000 | `/v2/analyse` + `/health` (`create_app_v2`) |
| `serveur_pilotage` | 8002 → 8000 | squelette `/pilotage/*` (501) + `/health` |
| `proxy` | 8080 → 8080 | proxy de dérive |
| `dashboard` | 8501 → 8501 | tableau de bord (stub) — inchangé |
| `azure-adapter` | interne 9000 | adaptateur Azure |

Reste à faire : container v1 isolé, container gateway, Caddy en frontal.

- **Le rôle vient de la commande uvicorn, jamais d'une variable
  d'environnement** (`--factory` sur `app.main:create_app_v2`). Raison : le
  `.env` est partagé par tous les services et `tests/conftest.py` [FOURNI] ne
  neutralise aucune variable de rôle ; une variable perdue aurait pu retirer
  `/v1` au service `app`. À ne pas ré-introduire.
- **`app` et `v2` ont des journaux de métriques distincts** :
  `ops/metrics.jsonl` et `ops/metrics_v2.jsonl`. `Mesure` [FOURNI] n'a pas de
  champ identifiant le container, deux journaux étaient le seul moyen de ne
  pas mélanger les mesures. `ops/dashboard.py` et `ops/deploy.py::surveiller`
  ne lisent encore que `ops/metrics.jsonl` (chantier 2).
- **`GET /health` du serveur de pilotage est hors contrat gelé**, non
  normatif : il n'existe que pour le healthcheck du container.
- Healthchecks en Python (`urllib.request`) et non `curl` : l'image
  `python:3.11-slim` n'embarque pas `curl`.
```

- [ ] **Step 4: Update `docs/spec-v2.md` §4**

Insérer, après la ligne 82 (`n'est pas l'architecture de déploiement canary cible décrite ci-dessus.`) et avant la ligne vide qui précède `Source : ...`, la puce suivante :

```markdown
- **État de mise en œuvre (2026-09-21, partiel)** : les containers `v2`
  (port hôte 8001, `uvicorn app.main:create_app_v2 --factory`) et
  `serveur_pilotage` (port hôte 8002, squelette `ops/serveur_pilotage.py`)
  existent dans le `docker-compose.yml`, à partir de la même image que `app`.
  Le rôle est porté par la commande uvicorn, pas par une variable
  d'environnement. Restent à faire : container v1 isolé, container gateway et
  Caddy en frontal. Détail :
  `docs/superpowers/specs/2026-09-21-v2-pilotage-containers-design.md`.
```

- [ ] **Step 5: Final verification before asking for the commit**

Run: `MOCK=on uv run pytest -q && uv run ruff check . && docker compose config --quiet && git status --short`
Expected :

- `7 failed, 54 passed`
- `All checks passed!`
- aucune sortie de `docker compose config --quiet`
- `git status --short` liste exactement : `M .gitignore`, `M CHANGELOG.md`, `M MEMORY.md`, `M Makefile`, `M TODO.md`, `M app/main.py`, `M docker-compose.yml`, `M docs/spec-v2.md`, `?? docs/superpowers/plans/2026-09-21-v2-pilotage-containers.md`, `?? docs/superpowers/specs/2026-09-21-v2-pilotage-containers-design.md`, `?? ops/serveur_pilotage.py`, `?? tests/unit/test_fabrique_app_v2.py`, `?? tests/unit/test_serveur_pilotage.py` (plus les fichiers déjà en attente de commit avant ce plan, voir `TODO.md` §« En attente de décision utilisateur »).
**`ops/metrics_v2.jsonl` ne doit PAS apparaître** — si c'est le cas, la Task 4 a échoué.

- [ ] **Step 6: Ask the user for permission to commit — DO NOT COMMIT**

**Ne rien exécuter.** Présenter à l'utilisateur la commande et le message ci-dessous, et **attendre son accord explicite** (convention du dépôt : « Aucun commit sans accord explicite de l'utilisateur », `CLAUDE.md` et §Documentation de la spec).

```bash
git add app/main.py ops/serveur_pilotage.py \
        tests/unit/test_fabrique_app_v2.py tests/unit/test_serveur_pilotage.py \
        docker-compose.yml .gitignore Makefile \
        CHANGELOG.md TODO.md MEMORY.md docs/spec-v2.md \
        docs/superpowers/specs/2026-09-21-v2-pilotage-containers-design.md \
        docs/superpowers/plans/2026-09-21-v2-pilotage-containers.md

git commit -F- <<'EOF'
feat(topology): run v2 and the pilot server as their own containers

Première étape vers la topologie cible de docs/spec-v2.md §4 (« un artefact,
un rôle par container ») : deux services de plus dans le docker-compose, à
partir de la même image que `app`, chacun sur son port hôte.

- `v2` (8001 → 8000) : nouvelle fabrique `app/main.py::create_app_v2()`, qui
  ne monte que le router `api_v2` (+ `/health`). Le rôle est porté par la
  commande uvicorn (`--factory`), jamais par une variable d'environnement :
  le `.env` est partagé par tous les services et `tests/conftest.py` [FOURNI]
  ne neutraliserait pas une telle variable, qui aurait pu retirer `/v1` au
  service `app`. `create_app()` et `app = create_app()` sont inchangés,
  `app/api_v1.py` n'a pas été touché.
- `serveur_pilotage` (8002 → 8000) : nouveau module `ops/serveur_pilotage.py`,
  squelette des 6 routes du contrat gelé conception_figee/pilotage/
  openapi-pilotage.json. Corps validés par les modèles Pydantic du contrat,
  donc 501 sur un corps valide et 422 sur un corps invalide. `/health` est une
  extension hors contrat, nécessaire au healthcheck.
- `METRICS_PATH=/app/ops/metrics_v2.jsonl` pour `v2` : sans journal distinct,
  les mesures de `app` et de `v2` seraient indiscernables (`Mesure` n'a pas de
  champ container). `.gitignore` et `make clean` couvrent ce fichier.
- Healthchecks Python sur `/health` (l'image slim n'a pas `curl`), pour que
  `docker compose up -d --build --wait` attende que les services soient prêts.

Tests : 17 tests unitaires ajoutés ; `MOCK=on uv run pytest -q` passe de
37 verts / 7 rouges à 54 verts / 7 rouges (les 7 rouges sont inchangés et
attendent `ops/deploy.py`, `eval/run_eval.py` et `ops/dashboard.py`).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

Si l'utilisateur refuse ou demande des changements, ne rien committer et appliquer ses retours.

---

## Récapitulatif d'exécution

| Tâche | Livrable | Vérification |
| --- | --- | --- |
| 1 | `create_app_v2()` + 5 tests | `5 passed`, puis `7 failed, 42 passed` |
| 2 | `ops/serveur_pilotage.py` + 12 tests | `12 passed`, puis `7 failed, 54 passed` |
| 3 | 2 services compose | `docker compose config --quiet` muet, ports 8001/8002 |
| 4 | `.gitignore` + `make clean` | `git check-ignore -v ops/metrics_v2.jsonl` |
| 5 | Vérification réelle | les 10 codes HTTP attendus, dont `v1=200` sur 8000 |
| 6 | Documentation + demande d'accord | `7 failed, 54 passed`, `git status --short` propre |
