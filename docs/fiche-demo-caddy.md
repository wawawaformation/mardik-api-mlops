# Fiche démo — Caddy en frontal + client de pilotage

> Aide-mémoire pour montrer la stack Docker complète : Caddy comme point
> d'entrée unique de l'API, et le client web de pilotage à côté.
> Détail de la topologie cible (non atteinte) : `docs/spec-v2.md` §4.

## 1. Démarrer la stack

```bash
docker compose up -d --build --wait
docker compose ps
```

## 2. Topologie actuelle

| Service | Port hôte | Rôle | Derrière Caddy ? |
|---|---|---|---|
| `caddy` | **8090** | point d'entrée unique de l'API (Caddyfile statique) | — |
| `app` | 8000 | `/v1`, `/v2`, `/analyse` (gateway) — accès direct toujours possible | oui (`/v1`, `/analyse`, `/gateway`) |
| `v2` | 8001 | `/v2/analyse` isolé | oui (`/v2`) |
| `serveur_pilotage` | 8002 | 6 routes `/pilotage/*` | oui (`/pilotage`) |
| `dashboard` | 8501 | tableau de bord (lecture `ops/metrics*.jsonl`) | non |
| `client_web` | 8503 | client HTML/JS de pilotage | non |
| `proxy` / `azure-adapter` | 8080 / interne | proxy de dérive + adaptateur Azure | non (pas exposé côté client) |

**Important** : `client_web` appelle `http://localhost:8002` en dur
(`client_web/app.js:5`), donc directement `serveur_pilotage` — **pas**
via Caddy. Caddy unifie l'accès à l'API, pas encore celui du client de
pilotage (hors périmètre de cette étape).

## 3. Montrer le routage Caddy (tout passe par le port 8090)

```bash
# /v1 -> app
curl -i -X POST http://localhost:8090/v1/analyse -H "Content-Type: application/json" -d '{}'

# /v2 -> v2 (isolé)
curl -i -X POST http://localhost:8090/v2/analyse -H "Content-Type: application/json" -d '{}'

# /analyse et /gateway/etat -> app (gateway, dispatch en process)
curl -i http://localhost:8090/gateway/etat

# /pilotage -> serveur_pilotage
curl -i http://localhost:8090/pilotage/journal
```

Attendu : `422` sur `/v1` et `/v2` (corps vide rejeté par la validation
Pydantic — preuve que la requête a bien atteint le bon container), `200`
sur `/gateway/etat` et `/pilotage/journal`.

Pour montrer que Caddy est bien le seul point de routage : couper `app`
(`docker compose stop app`) puis refaire l'appel `/v1` via `8090` → erreur
502 (Caddy ne trouve plus le backend), alors que `/v2` via `8090` continue
de répondre. Relancer avec `docker compose start app`.

## 4. Le client web de pilotage

Ouvrir `http://localhost:8503/index.html` dans le navigateur.

- Les 3 lectures (`dashboard`, `regles`, `journal`) répondent normalement.
- Les 3 écritures (`promotion`, `rollback`, `regles/{signal}`) répondent
  `501 Not Implemented` — c'est le contrat gelé, pas un bug (squelette du
  serveur de pilotage, chantier 2 pour la logique réelle).

## 5. Le dashboard

Ouvrir `http://localhost:8501` — fusionne `ops/metrics.jsonl` (app, v1+v2)
et `ops/metrics_v2.jsonl` (container v2 isolé). Voir la piste
« télémétrie » de `docs/img/pipeline-v2.png` pour l'origine exacte
(fichier:ligne) de chaque champ.

## 6. Limites à mentionner si la question vient

- Caddyfile **statique**, pas de régénération dynamique par
  `serveur_pilotage` (ça, c'est le chantier 2 : `docs/spec-v2.md` §4).
- `v1` n'est pas isolé dans son propre container : `app` sert encore
  `/v1` + `/v2` + gateway ensemble (confort de dev, cf. commentaire dans
  `docker-compose.yml`).
- Pas de container `gateway` séparé : le dispatch v1/v2 se fait **en
  process** dans `app`, conformément au contrat de `app/gateway.py`.
- `client_web` n'est pas (encore) derrière Caddy.

## 7. Arrêter proprement

```bash
docker compose down
```
