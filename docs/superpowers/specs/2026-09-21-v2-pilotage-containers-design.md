# Design — containers `v2` et `serveur_pilotage` (ports distincts)

> Date : 2026-09-21. Statut : validé par l'utilisateur (brainstorming), corrigé après
> relecture critique par Opus (2026-09-21), en attente de plan.
> Étape intermédiaire vers la topologie cible de `docs/spec-v2.md` §4
> (« un artefact, un rôle par container »). Ce document ne couvre que
> ce qui a été demandé : isoler la v2 et créer le squelette du serveur de pilotage,
> chacun dans son container, chacun sur son port.

## Besoin

- La **v2** tourne dans son propre container, sur un port dédié.
- Le **serveur de pilotage** tourne dans son propre container, sur un port dédié.
- Pour l'instant : rien de plus (pas de gateway, pas de container v1, pas de Caddy).

## Décisions

| Sujet | Décision |
| --- | --- |
| Distinction des services | **Ports hôte différents** (pas d'IP fixe, pas de réseau custom) |
| Service `app` existant | **Inchangé** (v1 + v2 + gateway, port 8000, confort de dev) |
| Contenu de `serveur_pilotage` | **Squelette** : `/health` + 6 routes `/pilotage/*` en 501 |
| Image | Même image que `app` (un artefact, un rôle par container — spec §4) |
| Restriction de `v2` à `/v2` | **Fabrique dédiée** `create_app_v2()`, pas de variable d'environnement |
| Corps des routes d'écriture du pilotage | **Modèles Pydantic du contrat gelé** (corps valide → 501, invalide → 422) |
| Métriques de `v2` | **`METRICS_PATH` distinct** (`ops/metrics_v2.jsonl`) |
| Service `dashboard` (8501) | **Inchangé** ; arbitrage `ops/dashboard.py` vs `/pilotage/dashboard` renvoyé au chantier 2 |

## Architecture

| Service compose | Port hôte → conteneur | Contenu servi |
| --- | --- | --- |
| `app` (existant) | 8000 → 8000 | `/v1`, `/v2`, gateway (inchangé) |
| `v2` (nouveau) | 8001 → 8000 | `/v2/analyse`, `/health` |
| `serveur_pilotage` (nouveau) | 8002 → 8000 | `/health`, `/pilotage/*` |

Ports déjà occupés à ne pas réutiliser : 8000 (`app`), 8080 (proxy de dérive), 8501
(`dashboard`). `azure-adapter` écoute sur 9000 sans le publier.

### Container `v2`

- Même `build: .` que `app` (le cache Docker évite tout coût réel), commande
  `uvicorn app.main:create_app_v2 --factory --host 0.0.0.0 --port 8000`.
- **Seul changement de code** : `app/main.py` gagne une fonction `create_app_v2()` qui ne monte
  que le router `api_v2` (+ `/health`, télémétrie et handler 501 réutilisés de `create_app`).
  `create_app()` et `app = create_app()` ne changent pas : `app`, `app.main:app` et les tests
  fournis restent intacts. **Aucune variable d'environnement ne pilote le rôle** (une variable
  perdue dans un shell, la CI ou le `.env` partagé pourrait sinon retirer `/v1` à `app`).
- Isolation **au niveau du routage, pas des imports** : `app/main.py` importe toujours
  `api_v1` et `gateway` au chargement (conforme à « un seul artefact »).
- Mêmes variables et volumes que `app` (`env_file: .env`, `LLM_PROXY_URL`, `REGISTRY_PATH`,
  volumes `./ops`, `./models`, `./eval`, `depends_on: proxy`), sauf
  **`METRICS_PATH=/app/ops/metrics_v2.jsonl`** : `app` et `v2` n'écrivent pas dans le même
  fichier, leurs mesures ne se mélangent donc pas. Conséquence assumée : `ops/dashboard.py`
  et `ops/deploy.py::surveiller` ne lisent pas encore ce fichier ; leur adaptation est du
  chantier 2. À vérifier au plan : `.gitignore` et `make clean` pour `ops/metrics_v2.jsonl`.
- `app/api_v1.py` n'est pas touché.

### Container `serveur_pilotage`

- Nouveau module **`ops/serveur_pilotage.py`** (FastAPI). `ops/` est déjà copié dans
  l'image et déclaré dans `pyproject.toml` : ni `Dockerfile` ni `pyproject.toml` à modifier.
- Les 6 routes de `conception_figee/pilotage/openapi-pilotage.json` : `GET /pilotage/dashboard`,
  `GET /pilotage/regles`, `PUT /pilotage/regles/{signal}`, `POST /pilotage/promotion`,
  `POST /pilotage/rollback`, `GET /pilotage/journal` (paramètres `signal` et `limite`).
  Les 3 routes d'écriture déclarent les **modèles Pydantic du contrat** : un corps valide
  atteint le handler et lève `NotImplementedError`, traduit en **501** par un handler (même
  mécanisme que `app/main.py`) ; un corps invalide est refusé en **422** avant le handler.
- `GET /health` → 200 : **extension hors contrat gelé, non normative**, nécessaire au
  `healthcheck` du container.
- Commande `uvicorn ops.serveur_pilotage:app --host 0.0.0.0 --port 8000`, volume `./ops`.
  Le squelette **ne lit ni écrit aucun fichier** : pas de `METRICS_PATH`/`REGISTRY_PATH` à
  ce stade (ils seront explicités quand la logique arrivera, chantier 2).

### Healthcheck des deux nouveaux services

- `healthcheck` sur `GET /health`, via Python (l'image `python:3.11-slim` n'a pas `curl`),
  pour que `docker compose up -d --build --wait` ne rende la main qu'une fois les services prêts.

## Hors périmètre (explicite)

- Logique du serveur de pilotage (lecture de `metrics.jsonl`, décisions, écriture
  registre/journal, régénération du Caddyfile) — chantier 2.
- Container v1 isolé, container gateway, Caddy — topologie complète de `docs/spec-v2.md` §4.
- Adaptation de `ops/dashboard.py` et `surveiller` à `metrics_v2.jsonl`, arbitrage du service
  `dashboard` — chantier 2.
- IP fixes / réseau Docker personnalisé (envisagés puis écartés : c'étaient les ports demandés).

## Vérification (TDD)

1. **Unitaire — fabrique** : `create_app_v2()` route `POST /v2/analyse` et répond 404 sur
   `POST /v1/analyse` et `POST /analyse` ; `create_app()` garde les trois routers.
2. **Unitaire — pilotage** : `GET /health` → 200 ; les 3 GET → 501 ; les 3 routes d'écriture
   → 501 avec un corps valide, 422 avec un corps invalide.
3. **Non-régression** : `MOCK=on uv run pytest -q` → **37 passed, 7 failed** (les 7 rouges
   attendus, tant que `deploy.py`, `run_eval.py` et `dashboard.py` restent des stubs) et
   `uv run ruff check .` vert (line-length 100).
4. **Réel** : `docker compose up -d --build --wait`, puis :
   - `curl localhost:8001/health` → 200 ; `POST localhost:8001/v1/analyse` → 404 ;
   - `curl localhost:8002/health` → 200 ; `curl localhost:8002/pilotage/journal` → 501 ;
   - non-régression de `app` : `curl localhost:8000/health` → 200,
     `POST localhost:8000/v1/analyse` → 200, `GET localhost:8000/gateway/etat` → 501.

## Documentation à mettre à jour

`CHANGELOG.md`, `TODO.md`, `MEMORY.md`, `docs/spec-v2.md` §4 (topologie partiellement
en place), `.env.example` seulement si une variable y est ajoutée (aucune prévue).
Aucun commit sans accord explicite de l'utilisateur.
