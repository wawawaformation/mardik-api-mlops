# TODO — mardik-api-mlops

## Analyse préalable (fait)

- [x] Lire le code source fourni et le confronter à `conception_figee/`
      (`docs/analyse-coherence-conception.md`)
- [x] Schéma du pipeline `/v1/analyse` réel (`docs/img/pipeline-v1_reel.drawio`)
- [x] Schéma du pipeline `/v2/analyse` cible (`docs/img/pipeline-v2.drawio`)
- [x] Trancher le conflit fenêtre glissante (comptage vs. temporelle) →
      temporelle retenue, révision dans `docs/conception_revue/pilotage/`
      (`fenetre-glissante-seuils.md`, `canary.md`, `tableau-pilotage.md` + PDF,
      `questions_reponses.md` Q9/Q10/Q12/Q14)

## Chantier 1 — Le bundle v2

- [x] `models/v2/config.yaml` : stratégie `map_reduce_clauses`, prompt par
      section (titre + texte, sortie JSON contrainte), `schema_sortie`,
      température/seed pour un gate stable

## Chantier 1 — Le pipeline v2

- [x] `app/pipeline/decoupage.py::decouper` — découpage par articles, taille
      cible 6 000 car., aucune perte de texte
- [x] `app/pipeline/extraction.py::extraire` — un appel LLM par section
      (json_mode), gestion des réponses hors schéma sans planter
- [x] `app/pipeline/consolidation.py::consolider` — fusion + dédoublonnage par
      type de clause
- [x] `app/pipeline/confiance.py::scorer` — score composite (≥ 2 signaux
      indépendants ; conception : confiance LLM × stabilité inter-chunks)
- [x] `app/api_v2.py::analyser_v2` + route `POST /v2/analyse` — orchestre les
      quatre étapes ci-dessus (voir `docs/img/pipeline-v2.drawio`)

## Chantier 1 — Le gate d'évaluation

- [x] `eval/run_eval.py::evaluer` — note par version (formule libre tant que
      les seuils/comparaisons testés passent ; conception : micro-F1 scindé
      courts/longs via `seuil_note` par contrat), latence P95, coût moyen

## Chantier 1 — La chaîne LLMOps

- [x] **Plan à 8 tâches exécuté et fusionné dans `dev`** (2026-09-22,
      commit `2f1c53c`) : `docs/superpowers/plans/2026-09-22-chaine-llmops.md`.
      Détail complet dans `MEMORY.md`.
- [x] Branche `dev` poussée vers GitHub (`origin/dev`) — le dépôt distant
      n'avait que `main` (squelette de départ) jusque-là.
- [x] **Compte de revue en place (2026-09-23)** : `connarddu16-design`
      (et non `mardik-relecteur`, nom de travail de la conception jamais
      enregistré), collaborateur `write` sur le dépôt. `revue.yml` pointé
      sur ce login — sans ça le garde n'aurait jamais matché et
      `revue-ok` n'aurait jamais été posé.
- [x] **Secrets Azure poussés (2026-09-23)** : `AZURE_LLM_MODEL`,
      `AZURE_AI_ENDPOINT`, `AZURE_AI_API_KEY` (depuis `.env`) et
      `AZURE_AI_API_VERSION` (valeur documentée `2024-05-01-preview` —
      sans effet réel : `drift_proxy` l'ajoute à l'URL, `azure_adapter`
      la retire, l'API `/openai/v1` n'en veut pas).
- [x] **Secret `CI_TAG_TOKEN` posé (2026-09-23)** : PAT classique émis
      depuis le compte de revue (`connarddu16-design`), vérifié avant pose
      (identité du token + `push: true` sans `admin` sur le dépôt).
      **Plus aucun prérequis bloquant** : la chaîne est exerçable de bout
      en bout (PR `dev → main`, approbation depuis le compte de revue, tag
      `gate/<sha7>`, fusion).
- [x] **Protections de tags et de branche posées (2026-09-23)** : rulesets
      GitHub `protection-dev-main` (`dev`/`main` — pas de suppression, pas
      de force-push, historique linéaire, **sans** « require a pull request
      before merging », qui interdirait la fusion fast-forward en ligne de
      commande) et `protection-tags-preuves` (`revue-ok/*`, `eval-ok/*`,
      `v*` — pas de suppression, pas de mise à jour ; `gate/*` reste libre).
- [x] **Tranché (2026-09-22)** : `CANARY_PERCENT` et `MOCK` restent des
      valeurs par défaut statiques dans `.env`. Le pilotage dynamique du
      pourcentage canary relève du chantier 2 (registre/serveur de
      pilotage), pas de l'environnement de base.
- [x] `ops/deploy.py::publier/deployer_canary/promouvoir/rollback` (point 3 ;
      `surveiller` reste chantier 2 (hors périmètre, avec `app/gateway.py`),
      voir décision périmètre ci-dessus)
- [x] `ops/dashboard.py::resume/rendre_texte/rendre_html` — fenêtre
      **temporelle** (`fenetre_s`) — voir détail sous « Chantier 2 — Pilotage »
- [x] `.github/workflows/llmops.yml` — remplacé par 4 workflows séparés par
      rôle (`ci.yml`, `revue.yml`, `gate.yml`, `cd-main.yml`), mécanisme à
      deux tags (`revue-ok/<sha>`, `eval-ok/<sha>`) décrit dans
      `conception_figee/chantier1_llmops/gel-eval-avant-fusion.md`. **Exemple
      suivi (tranché 2026-09-22)** : même principe de gates que
      `/projets/QualiCheck/.gitea/workflows/` (`ci.yml`, `revue.yml`,
      `gate.yml`, `cd-staging.yml` — syntaxe GitHub Actions, transposable
      telle quelle) — garde bash
      `git tag --points-at "$SHA" | grep -q '^revue-ok/'`, pose de tag
      idempotente (skip si déjà posé), compte technique dédié + token
      restreint pour poser les tags (jamais le développeur),
      `fetch-depth: 0` sur tout job qui lit des tags. Déclenchement manuel
      du gate = tag `gate/<sha7>` poussé par le développeur (pas de
      `workflow_dispatch`), même logique que `revue-ok`/`eval-ok`. Revue finale
      de branche (2026-09-22) : corrections appliquées (xfail des 4 tests
      hors périmètre, réordonnancement gate-avant-push-image, commit du
      registre après publication, permissions `revue.yml`) — voir
      `MEMORY.md` et `CHANGELOG.md`. `ops/deploy.py::surveiller` et
      `app/gateway.py` restent hors périmètre (chantier 2).
- [x] **Conciliation architecture avant CI/CD (point 3)** : pas besoin de la
      rouvrir, l'architecture actée pour l'API (`docs/spec-v2.md` §4 — un seul
      artefact Docker partagé, 3 containers/rôles v1/v2/gateway, Caddy en
      frontal) sert aussi de cible pour le déploiement canary du point 3
      (confirmé par l'utilisateur, 2026-09-21).
- [x] **Périmètre exact du point 3, tranché (2026-09-22)** : point 3 =
      `llmops.yml` + `deploy.py::publier/deployer_canary/promouvoir/rollback`,
      **sans** `surveiller()`. `surveiller` (détection de dérive + rollback
      automatique) et `app/gateway.py` (routage réel du trafic canary)
      restent chantier 2. Conséquence : `test_promotion_canary_puis_totale`
      et `test_rollback_en_une_operation` (qui dépendent de `gateway.py`)
      resteront rouges tant que le chantier 2 n'est pas fait — attendu, pas
      un défaut du point 3.

## Chaîne LLMOps — écarts avec `intents.md` (2026-09-23)

Issus de la mise à plat des intentions. Référence : `intents.md` (racine) et
`docs/conception_revue/chantier1_llmops/gel-eval-avant-fusion.md`.

Plan exécuté le 2026-09-23 sur `feature/chaine-llmops-intents` :
`docs/superpowers/plans/2026-09-23-chaine-llmops-intents.md` (spec :
`docs/superpowers/specs/2026-09-23-chaine-llmops-intents.md`).

- [x] **Changer la cible de la revue** : `revue.yml` garde désormais
      `base.ref == 'dev'`. La revue se fait sur une PR `feature/x → dev`.
      (Écart 1 — topologie ; commit `eeb55b2`.)
- [x] **Deux fusions fast-forward au lieu d'une** : `feature/x → dev` puis
      `dev → main`. Un squash ou un merge commit à l'une des deux étapes
      fabrique un nouveau SHA, que les tags ne suivent pas. Rulesets posés
      sur `dev` et `main` (force-push et suppression bloqués, historique
      linéaire) et sur les tags `revue-ok/*`, `eval-ok/*`, `v*` (immuables) ;
      les commandes exactes de fusion sont écrites dans
      `docs/exploitation.md` § 3.
- [x] **Garantir que le lot A est vert avant la revue** (intention I3) :
      `revue.yml` interroge l'API GitHub Actions sur `ci.yml` pour le SHA de
      tête de la PR, attend au plus 10 min si la CI tourne encore, et refuse
      de poser `revue-ok` si la conclusion n'est pas `success`.
- [x] **Alerte d'évaluation conditionnelle dans le lot A** (intention I6) :
      `.github/workflows/alerte-eval.yml`, déclenché par un push sur
      `feature/**` touchant `models/*/config.yaml`, `app/pipeline/**`,
      `app/llm_client.py` ou `eval/**`. **Ne pose aucun tag** et ne reçoit
      aucun jeton d'écriture — c'est un signal au développeur, pas une
      preuve. Conséquence assumée : le lot A cesse d'être gratuit sur ces
      chemins.
- [x] **Trancher : où vont les TA mockés ?** → **option 1** (2026-09-23) :
      ils restent dans le lot A *et* dans le lot C. La répétition est
      voulue — au lot A ils informent, au lot C ils prouvent. Justification
      écrite dans `docs/exploitation.md` § 3 et en commentaire dans
      `gate.yml`, pour qu'aucune relecture future ne la « nettoie ».
- [x] **Nettoyer `main`** : `origin/main` est revenu à `8c59599` et est de
      nouveau un ancêtre de `dev` — le merge commit `aec3112` de la PR #1 a
      disparu, la fusion fast-forward `dev → main` est donc à nouveau
      possible.
- [x] **Cas CI verte vérifié en conditions réelles (2026-09-23)** : PR #2
      (`feature/chaine-llmops-intents → dev`), approuvée par
      `connarddu16-design` — `revue-ok/6373259` posé après vérification du
      lot A, puis `gate/6373259` déclenché à la main → `eval-ok/6373259`
      posé (vraie évaluation Azure, gate passé) → fast-forward `feature →
      dev` poussé, PR fermée d'elle-même. `dev` est désormais à `6373259`,
      gelé (`revue-ok` + `eval-ok` sur le même SHA). `main` reste
      volontairement à `8c59599` : la fusion vers `main` est une décision de
      déploiement séparée, pas encore prise.
- [ ] **Cas CI rouge non vérifié** : le garde de `revue.yml` (lot A vert
      avant `revue-ok`) n'a été exercé que côté succès. L'historique du
      dépôt ne contient aucune exécution `ci.yml` en échec — le refus n'a
      donc été validé que par relecture du `case` dans le YAML, jamais en
      conditions réelles.

## Chantier 2 — Pilotage

- [x] Squelette `ops/serveur_pilotage.py` : 6 routes du contrat gelé en 501,
      corps validés par les modèles Pydantic du contrat, `/health` pour le
      healthcheck (service compose `serveur_pilotage`, port hôte 8002)
- [x] Logique du serveur de pilotage implémentée (2026-09-23, TDD,
      `tests/unit/test_serveur_pilotage.py` réécrit) : les 6 routes lisent
      les métriques (via `ops/dashboard.py`), décident (dashboard, critère
      de promotion `canary.md`), écrivent le registre et journalisent —
      **en réutilisant `ops/registry/` existant**, pas de nouveau
      `ops/registre.json`/`ops/journal_pilotage.jsonl` (conflit de
      conception tranché, détail dans
      `docs/conception_revue/pilotage/formats-ops.md`, nouveau). Nouveau
      fichier `ops/regles_pilotage.json` pour les 4 seuils ajustables (`PUT
      /pilotage/regles/{signal}`, tracé au journal). Restent hors
      périmètre, documentés dans ce même fichier : régénération du
      Caddyfile (pas de container Caddy encore) et bouclage des règles
      ajustables sur la décision automatique de `ops.deploy.surveiller`.
- [x] Client web de pilotage câblé sur l'API (2026-09-23) : les 4 pages de
      la maquette figée (`conception_figee/sources/pilotage_maquette/html/`)
      recopiées et branchées dans `client_web/` (HTML/CSS/JS vanilla, aucun
      build). Service `client_web` (port 8503) dans `docker-compose.yml`,
      CORS ouvert sur `ops/serveur_pilotage.py`. Écarts documentés dans
      `CHANGELOG.md`/`MEMORY.md` (histogramme de score simplifié en une
      proportion, paliers canary limités à 50/100 %). Vérifié
      mécaniquement (formes JSON, CORS, fichiers statiques servis) mais pas
      dans un vrai navigateur.
- [x] **Arbitrage tranché (2026-09-22)** : pas de duplication à résoudre.
      `ops/dashboard.py::resume()` reste la fonction de calcul (imposée par
      le test d'acceptance fourni `test_dashboard_par_version`) ;
      `GET /pilotage/dashboard` (serveur de pilotage) réutilise cette même
      fonction en interne plutôt que de recalculer l'agrégation. Le service
      `dashboard` (8501, `--serve`) reste une vue texte/HTML autonome héritée
      de la remédiation, en plus de la route JSON contractuelle.
- [x] `ops/dashboard.py::resume/rendre_texte/rendre_html` implémentés
      (2026-09-23), fenêtre **temporelle** (`fenetre_s`, voir
      `docs/conception_revue/pilotage/fenetre-glissante-seuils.md`). Sans
      `metriques` explicite, `resume()` fusionne `METRICS_PATH` (v1) et
      `METRICS_PATH_V2` (v2, nouvelle variable, `docker-compose.yml` service
      `dashboard`) — condition pour que le trafic du container `v2` ne soit
      pas invisible du tableau de bord.
- [x] `app/gateway.py::choisir_version/etat/analyse` — routage canary
      (2026-09-23, TDD). `test_promotion_canary_puis_totale` et
      `test_rollback_en_une_operation` ne sont plus xfail.
- [x] `ops/deploy.py::surveiller` implémenté (2026-09-23, TDD) : dérive sur
      score/taux d'erreur/latence P95 (minimum de mesures requis), rollback
      automatique + journal. Fusion `ops/metrics.jsonl` +
      `ops/metrics_v2.jsonl` via `ops/dashboard.py::stores_metriques_par_defaut`
      (rendue publique, réutilisée). `test_journal_derive_et_rollback_automatique`
      n'est plus xfail — plus aucun test xfail dans
      `tests/acceptance/test_observabilite.py` (93 passed sur la suite
      complète).
- [x] `docs/exploitation.md` complété (2026-09-23), 7 sections : version/
      fingerprint, étiquetage SemVer + manifest.json, chaîne de livraison
      (4 workflows), déploiement progressif (critère v2≥v1), rollback,
      surveillance/seuils (+ limite : règles ajustables pas encore
      bouclées sur `surveiller()`, boucle périodique non implémentée),
      preuve d'exécution (transcript réel capturé au niveau `ops.deploy`,
      pas de démo HTTP bout en bout complète — nécessite Docker + un vrai
      modèle, commande fournie pour que l'utilisateur la rejoue).

## Divers

- [x] `scripts/demo.py` : démo guidée v1 → v2 → pilotage pour présentation
      (2026-09-23), bandeau `MOCK=...` avant toute étape.
- [x] **Bug corrigé (2026-09-23)** : `ops/deploy.py::prochaine_version`
      mélangeait les lignées v1/v2 — le premier vrai déploiement v2 via
      `cd-main.yml` aurait été étiqueté `v1.0.1` au lieu de `v2.0.0`.
      Détail : `CHANGELOG.md`/`MEMORY.md` (section incident).
- [x] **Registre local remis à plat (2026-09-23)** : l'artefact `v1.0.1`
      (bundle v2 mal étiqueté par l'incident du matin) déplacé en
      `ops/registry/_incident-2026-09-23-v1.0.1/` — ignoré par
      `Registry.versions()` (nom hors motif SemVer), réversible. État de
      départ propre : `v1.0.0` active, aucun canary, et
      `prochaine_version` y produit bien `v2.0.0`.
- [x] **Bug de rollback corrigé (2026-09-23, TDD)** : deux rollbacks
      consécutifs mettaient `active: null` (ni canary ni `precedente` à
      restaurer) → la gateway répondait 500 sur `/analyse`. Constaté en
      conditions réelles pendant 12 min. `rollback()` garde désormais
      l'active en place quand il n'y a rien à annuler.
- [x] `docs/demo-ci.md` (2026-09-24) : script de démo de la chaîne CI/CD,
      de `make ci` au canary 10 % (commandes, workflow déclenché, coût LLM,
      ce qu'il faut montrer). **Rédigé, pas encore joué.**
- [ ] Jouer `docs/demo-ci.md` une fois en répétition — ce serait aussi
      l'occasion de fermer « Cas CI rouge non vérifié » (pousser un commit
      au lint cassé, approuver, constater le `[refus]` de `revue.yml`).
- [ ] Décider si `cd-main.yml` doit committer `ops/registry/index.json` :
      aujourd'hui l'état du canary posé en CI vit sur le runner seulement.
- [x] `docs/demo-v1-v2-pilotage.md` + `bruno/mardik-demo-cto/` (2026-09-23) :
      déroulé de présentation v1 → v2 → pilotage et les 10 requêtes HTTP
      correspondantes. **Règle à retenir pour tout `.bru`** : le corps d'un
      bloc `body:json { … }` doit être indenté (2 espaces) — une accolade
      en colonne 0 ferme le bloc prématurément et casse le parse du fichier
      entier (Bruno n'affiche alors que « File Info »). Vérifiable sans
      ouvrir Bruno : `npm i @usebruno/lang` puis `bruToJsonV2()` sur chaque
      fichier.

## Environnement

- [x] Environnement Docker démarré (`make up`), fournisseur Azure configuré
      (`.env`) — voir `ops/azure_adapter.py` pour l'adaptation nécessaire
      (api-version, max_tokens → max_completion_tokens)
- [x] Containers `v2` (8001) et `serveur_pilotage` (8002) ajoutés au
      `docker-compose.yml`, healthchecks Python sur `/health`, vérifiés avec
      `docker compose up -d --build --wait`
- [ ] Topologie cible complète de `docs/spec-v2.md` §4 : container v1 isolé,
      container gateway — **après validation CI/CD**
- [x] Caddy simple en frontal (2026-09-24, branche `feature/demo-ci`, pas
      encore fusionnée) : `Caddyfile` statique (port hôte 8090), route
      `/v1`, `/v2`, `/pilotage`, `/analyse`+`/gateway`, et `/` vers
      `client_web` (branché derrière Caddy, `API_BASE` relatif). Testé en
      `curl`, puis vérifié visuellement navigateur + Bruno le 2026-09-25
      (voir `CHANGELOG.md`). Reste hors périmètre : régénération dynamique
      du Caddyfile par `serveur_pilotage` (chantier 2).
- [x] Vérifier que les tests d'intégration v1 restent verts (`make test-integration`)
- [ ] `make test-acceptance` : 9 rouges / 1 vert au départ (`test_client_v1_fonctionne`),
      objectif = tout vert

## Constats de la répétition de démo (2026-09-25)

- [x] **3e boucle de rétroaction — enrichissement du jeu d'éval livrée
      (2026-09-28, TDD)** : `ops/enrichissement.py` (capture, pseudonymisation
      regex minimale, versement), branché dans `app/api_v2.py::analyser_v2`,
      2 routes dans `ops/serveur_pilotage.py`. Détail :
      `CHANGELOG.md` (2026-09-28).
- [ ] **UI client web pour l'enrichissement** : pas de page dans
      `client_web/` pour lister/valider les cas en attente — le juriste
      passe par l'API (`GET`/`POST /pilotage/enrichissement`) ou Bruno.
- [ ] **Pseudonymisation regex minimale** : `ops/enrichissement.py::pseudonymiser`
      ne couvre que montant/email/SIRET/téléphone — pas la détection de
      noms propres/adresses par zones (début/fin) décrite dans
      `anonymisation.md`. À enrichir si des cas réels laissent passer des
      données personnelles.
- [ ] **Cas en attente à commiter par un humain** : `eval/a_valider/*.json`
      et les fichiers versés (`eval/contrats/p-*.txt`, ligne dans
      `eval/attendus.jsonl`) ne partent en PR que si quelqu'un les commit —
      aucune automatisation de ce commit aujourd'hui.
- [ ] **Calibrer le score de confiance v2** (`app/pipeline/confiance.py`) :
      la corroboration `min(1, (n - 1) / 2)` vaut 0 pour une clause vue
      dans une seule section (cas normal d'un contrat), et le global prend
      le minimum → score presque toujours nul. Preuve : requêtes 3 (0,99)
      et 3b (0) de `bruno/demo-cto-caddy/`, mêmes clauses, seule la
      répétition change. Piste : vérifier que l'extrait figure dans le
      contrat (paramètre `texte` déjà transmis, inutilisé), revoir
      l'agrégation `min`. Mettre à jour `tests/unit/pipeline/test_confiance.py`
      et les tests qui en dépendent ; toucher `app/pipeline/` relance
      `alerte-eval.yml` (payant). Impacte la règle de rollback `score_faible`.
- [x] **Tracer les refus de promotion** au journal : fait le 2026-09-28 —
      `promotion_refusee` journalisé pour les 2 cas décisionnels (mesures
      insuffisantes, critères non tenus) avant la 409 ; « aucun canary »
      reste non tracé (rien à décider).
- [x] **Déclencheur/signal sur l'événement `canary` posé par la CLI** : fait
      le 2026-09-28 — `ops.deploy` CLI (`canary`/`promouvoir`/`rollback`)
      accepte `--declencheur`/`--signal` ; `cd-main.yml` passe
      `--declencheur auto --signal eval-ok`.
- [ ] **Rollback sans canary en cours** : aujourd'hui tracé quand même
      (lignes identiques avant/après au journal) — refuser (409) ou ne pas
      tracer.
- [ ] **Événements récents du tableau de bord** : `message` construit par
      `", ".join(f"{k}={v}")` (`ops/serveur_pilotage.py:208-217`) → dicts
      Python bruts à l'écran (`{'active': 'v1.0.0', 'canary': None}`).
- [x] **Seuil de coût** (0,15 €) absent de `/pilotage/regles`, donc encore
      codé en dur dans `client_web/index.html` — fait le 2026-09-28 : règle
      `cout_moyen` ajoutée aux règles par défaut, lue depuis `/pilotage/regles`
      côté client.
- [ ] `scripts/traffic_sim.py` vise `http://localhost:8000` par défaut
      (port direct) : passer `--url http://localhost:8090` pour passer par
      Caddy.

## À régler plus tard — notes rapides

- [ ] **Régler Git Graph** (demande du 2026-09-25, problème à préciser).
      État relevé ce jour-là : `dev`, `main` et leurs `origin/` alignés
      (0 d'écart) ; seule `feature/demo-ci` est en avance de 31 commits non
      poussés sur `origin/feature/demo-ci`.

## Release — pour plus tard (note du 2026-09-25)

**Constat** : chaque run de `cd-main.yml` crée bien une version SemVer
(`prochaine_version()` : patch automatique, `[minor]` / `[major]` via le
message du commit), l'enregistre dans `ops/registry/vX.Y.Z/` (commit
`chore(registry)` sur `main`) et pousse l'image `ghcr.io/…:vX.Y.Z` — déjà
v2.0.0 à v2.0.4. Mais il n'existe **aucune release au sens git / GitHub** :
ni tag git `vX.Y.Z`, ni GitHub Release, ni notes de version. Le ruleset
`protection-tags-preuves` protège pourtant déjà les tags `v*`… que rien ne
crée. Aujourd'hui, retrouver le commit d'une version impose d'ouvrir son
manifeste (`code_commit`) dans `ops/registry/vX.Y.Z/`.

- [ ] **Poser le tag git `vX.Y.Z`** dans `cd-main.yml`, après le push de
      l'image. À trancher : sur le SHA qui porte `revue-ok` / `eval-ok`
      (celui qui a été relu et évalué) ou sur le commit `chore(registry)`
      qui le suit ? Le premier semble plus juste. Sans risque de boucle :
      un push de tag `v*` ne déclenche aucun workflow (`ci.yml` ignore les
      tags, `gate.yml` n'écoute que `gate/*`, `cd-main.yml` que la branche
      `main`). `GITHUB_TOKEN` et `contents: write` suffisent, déjà en place.
- [ ] **Créer une GitHub Release** (`gh release create vX.Y.Z`) avec : note
      d'évaluation, fingerprint du manifeste, référence de l'image `ghcr.io`,
      pourcentage canary. Notes générées (`--generate-notes`) ou tirées du
      `CHANGELOG.md` ?
- [ ] **Trancher le moment de la release** : `versionnage.md` dit que chaque
      `vX.Y.Z` pointe vers une image déployable, pas qu'elle est en
      production. Piste : release **pré-publiée** (`--prerelease`) au
      déploiement canary 10 %, passée en release finale à la promotion à
      100 % (depuis `serveur_pilotage`, donc hors `cd-main.yml`).
- [ ] **Cas particuliers** : `v1.0.0` (lignée v1 figée, antérieure à la
      chaîne) sans tag ni release — la rattraper à la main ou l'assumer ;
      le tag étant immuable (ruleset), un run relancé sur la même version
      doit détecter le tag existant au lieu d'échouer (même garde que pour
      `revue-ok` / `eval-ok`).

Références : `conception_figee/chantier1_llmops/versionnage.md` (règles
SemVer et fingerprint), `ops/deploy.py::prochaine_version`,
`.github/workflows/cd-main.yml` (étapes « Calculer la prochaine version » à
« Pousser l'image »).

## Infrastructure GitHub — Prérequis pour la chaîne

- [x] Ruleset `main-linear` créé : **Require linear history** sur `main` (2026-09-24)
- [x] `cd-main.yml` vérifie les deux tags `revue-ok/<sha>` + `eval-ok/<sha>` avant
      déploiement (ligne 41-46) — refuse si absent
- [x] Tous les autres prérequis en place : compte de revue, secrets Azure,
      `CI_TAG_TOKEN`, rulesets de protection (2026-09-23)

## Validation CI/CD en conditions réelles

- [ ] **Cas 1 : CI rouge** → pousser un commit avec lint cassé sur `feature/x`,
      ouvrir PR vers `dev`, vérifier le `[refus]` de `revue.yml` (lot A doit être
      vert avant `revue-ok`) — **jamais testé, seul cas non validé**
- [ ] **Cas 2 : chaîne complète** → PR `feature/y → dev`, approuvée par
      `connarddu16-design` (compte de revue), déclencher gate via tag `gate/<sha7>`,
      vérifier `eval-ok` posé, puis fusion fast-forward `dev → main` :
      ```bash
      git push origin dev --force-with-lease  # ff seulement (localement d'abord : git merge --ff-only)
      ```
      Vérifier que `cd-main.yml` roule, image publiée sur `ghcr.io`, canary 10 %
      activé.
- [ ] **Cas 3 : vérifier le cas CI rouge n'est pas bloqué par un détail technique**
      (impossible avant d'avoir repoussé un commit cassé, mais documenter la
      procédure pour plus tard)

## Test d'intégration complète sur dev

- [ ] **Après validation de la CI/CD** : tester toute la solution sur ta machine
      - Stack Docker complète (`make up`)
      - Appel v1 + v2 + vérifier les métriques
      - Simuler une dérive (`DRIFT=score_moyen`) → vérifier rollback auto via
        `ops/deploy.surveiller` (faire tourner `make traffic` en parallèle)
      - Vérifier le journal de pilotage + accès au client web (port 8090, via Caddy)
      - Documenter le résultat dans un transcript (comme dans `docs/exploitation.md` § 7)
- [ ] **Topologie Docker complète (optionnel, après le reste)** : container Caddy
      en frontal, v1 isolé, container gateway, régénération Caddyfile dynamique
      (points ouverts depuis chantier 2)
