# Cahier de recettes — Démo Caddy + client de pilotage + Bruno

> Déroulé de validation avant la démo (branche `feature/demo-ci`, non
> fusionnée). Complète `docs/fiche-demo-caddy.md` (aide-mémoire) avec des
> scénarios à cocher un par un. Contexte technique : `docs/spec-v2.md` §4.

## Pré-requis

- [ ] Se placer sur `feature/demo-ci` (`git status` propre)
- [ ] Aucun autre service n'écoute sur les ports **8090** (Caddy) et
      **8503** (`client_web`) — vérifier avec `ss -ltnp | grep -E ":8090|:8503"`
- [ ] Stack démarrée :

  ```bash
  docker compose up -d --build
  docker compose ps
  ```

  Attendu : tous les containers `Up`, `serveur_pilotage` et `v2` en
  `(healthy)`.

---

## Scénario 1 — Point d'entrée unique (navigateur)

**Étant donné** la stack démarrée,
**quand** j'ouvre `http://localhost:8090/` dans le navigateur,
**alors** la page d'accueil du client de pilotage s'affiche correctement
(styles chargés, pas d'erreur console réseau vers `localhost:8002`).

- [ ] Page chargée sans erreur
- [ ] Naviguer vers les 3 autres pages du client (`journal.html`,
      `regles.html`, `promotion.html` ou équivalents dans
      `client_web/`) — même vérification

> Point d'attention : `client_web/app.js` utilise `API_BASE = ""` (relatif),
> donc tous les appels API du client passent par Caddy (port 8090), pas par
> `localhost:8002` en direct (`docs/fiche-demo-caddy.md` corrigé en
> conséquence).

---

## Scénario 2 — Routage `/v1` (API v1 via Caddy)

**Étant donné** Bruno ouvert sur la collection `bruno/`, dossier `demo-cto-caddy/caddy/`,
**quand** j'exécute `02-v1-analyse.bru`,
**alors** la réponse est **200** avec les clauses détectées
(`durée`, `reconduction tacite`, `résiliation`, `pénalité de retard`,
`prix et paiement`, `confidentialité`, `droit applicable`) et
`"version":"v1.0.0"`.

- [ ] Statut 200
- [ ] `version` = `v1.0.0`
- [ ] Clauses cohérentes avec le texte du contrat envoyé

---

## Scénario 3 — Routage `/v2` (API v2 isolée via Caddy)

**Étant donné** la même collection Bruno,
**quand** j'exécute `03-v2-analyse.bru`,
**alors** la réponse est **200**, `"version":"v2.0.0"`, avec un
`confiance_globale` et un `cout_eur` renseignés.

- [ ] Statut 200
- [ ] `version` = `v2.0.0`
- [ ] `confiance_globale` et `cout_eur` présents (preuve que c'est bien le
      container `v2` isolé qui répond, pas `app`)

---

## Scénario 4 — Gateway (dispatch v1/v2)

**Étant donné** la même collection Bruno,
**quand** j'exécute `04-gateway-etat.bru`,
**alors** la réponse est **200** avec l'état courant du dispatch
(`active`, `canary`, `canary_percent`).

- [ ] Statut 200
- [ ] Champ `active` cohérent avec l'état attendu (`v1.0.0` sauf canary en
      cours)

---

## Scénario 5 — Pilotage (lecture du tableau de bord)

**Étant donné** la même collection Bruno,
**quand** j'exécute `05-pilotage-dashboard.bru`,
**alors** la réponse est **200** avec les données de pilotage
(règles, historique).

- [ ] Statut 200

---

## Scénario 6 — Deux clients, un seul point d'entrée (démo live)

**Étant donné** le navigateur ouvert sur `http://localhost:8090/journal.html`
(ou `index.html`) et Bruno ouvert sur `bruno/demo-cto-caddy/caddy/`,
**quand** j'exécute `02-v1-analyse` puis `03-v2-analyse` dans Bruno,
**alors** un rafraîchissement de la page dans le navigateur fait apparaître
ces nouvelles requêtes dans le journal / tableau de bord — preuve que
Bruno (client externe simulé) et le client web passent par le **même**
point d'entrée Caddy (port 8090).

- [ ] Nouvelle entrée visible après rafraîchissement

> Attention : `index.html` et `actions.html` affichent le trafic v1/v2 sur
> une **fenêtre glissante de 5 minutes** (`FENETRE_DASHBOARD_S = 300`,
> `ops/serveur_pilotage.py:79`), pas un historique complet. Si plus de
> 5 minutes se sont écoulées depuis la dernière requête `/v1` ou `/v2`,
> l'écran affiche `v1 à 0 %, v2 à 0 %` — ce n'est pas un bug. Toujours
> rejouer les requêtes Bruno juste avant de montrer cette page.

---

## Scénario 7 — Panne d'un backend (option, si le temps le permet)

**Étant donné** la stack qui tourne,
**quand** je fais `docker compose stop app` puis je rejoue
`02-v1-analyse.bru` (ou `04-gateway-etat.bru`) via Caddy,
**alors** j'obtiens une erreur **502** (Caddy ne trouve plus le backend),
**tandis que** `03-v2-analyse.bru` continue de répondre **200**
(container `v2` indépendant).

- [ ] 502 sur `/v1` et `/gateway`
- [ ] 200 toujours sur `/v2`
- [ ] Relancer ensuite : `docker compose start app`

---

## Si tout est vert → enchaîner

1. Ouvrir la PR `feature/demo-ci → dev`
2. Revue par `connarddu16-design`
3. Gate puis fusion vers `main`
   (procédure détaillée : `docs/demo-ci.md` / `docs/demo-ci.sh`)

## Remise en état après démo

```bash
docker compose down
```
