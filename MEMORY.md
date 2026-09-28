# MEMORY — Contexte projet condensé (mardik-api-mlops)

> Continuité inter-sessions / inter-agents. À mettre à jour à chaque évolution
> significative. Lire ce fichier en premier.

## Projet

**Mardik v2** — outil d'analyse de contrats (lab phase 4, formation dev IA
agentique). Objectif : livrer la v2 (contrats longs sans troncature, score de
confiance) via une chaîne LLMOps automatisée, sans jamais casser la v1.
Contexte : un déploiement manuel raté a motivé la note du CTO « Plus jamais
ça ».

Ce dépôt (`mardik-api-mlops`) est le **code source de départ du brief**
(squelette + stubs + tests d'acceptance fournis), distinct du dossier de
conception qui a précédé son obtention.

## ⚠️ Le dossier de conception est gelé — ne jamais y écrire

`../conception_figee/` (dans le dépôt parent `mardik_nouvelle_version`) est
le dossier de conception produit **avant** d'avoir accès à ce code source. Il
a été présenté (dossier de conception soutenu), puis **gelé volontairement
par l'utilisateur le 2026-09-21** :

- renommé `conception/` → `conception_figee/` ;
- permissions **555** (lecture seule) ;
- le `.git` du dépôt parent `mardik_nouvelle_version` a été **supprimé
  intentionnellement** (pas de remote, donc pas d'historique à récupérer —
  assumé par l'utilisateur).

**Règle stricte : ne plus jamais créer ni modifier de fichier en dehors de
`mardik-api-mlops/`.** Toujours lire `conception_figee/` pour comprendre une
décision passée, jamais y écrire (de toute façon interdit par les
permissions). Un écart découvert entre une décision de conception et le code
réel se documente dans `docs/conception_revue/` (voir plus bas), jamais en
éditant `conception_figee/`.

## Documents de référence (ordre de lecture)

0. **`intents.md`** (racine) — **les intentions de l'utilisateur et leur
   *pourquoi*, en amont de tout le reste.** Posé le 2026-09-23. En cas de
   désaccord entre un workflow et ce fichier, c'est le workflow qui a tort.
   À lire avant de toucher à la chaîne LLMOps.
1. `README.md` — structure du dépôt, chantiers, commandes (`make ...`)
2. `docs/besoin_client.md` — expression de besoin (identique au brief connu)
3. `docs/schema_remediation.md` — ce que la remédiation a déjà instrumenté
   (télémétrie v1, à réutiliser tel quel)
4. `docs/analyse-coherence-conception.md` — confrontation entre les décisions
   de `conception_figee/` et le code réel fourni ici : ce qui est cohérent,
   ce qui a dû être révisé
5. `docs/conception_revue/` — versions **révisées** des documents de
   conception dont une décision a dû changer face au code réel (voir
   ci-dessous)
6. `docs/img/pipeline-v1_reel.drawio` / `.png` — pipeline `/v1/analyse` tel
   qu'implémenté (réel)
7. `docs/img/pipeline-v2.drawio` / `.png` — pipeline `/v2/analyse` **cible**
   (pas encore implémenté, tiré des docstrings des stubs)
8. `../conception_figee/` — dossier de conception d'origine, gelé, lecture
   seule, fait foi pour tout ce qui n'a pas été explicitement révisé

## Décisions acquises (héritées de `conception_figee/`, toujours valables)

- **V1 figée** : `/v1/analyse` intouchable (confirmé dans le code réel,
  `app/api_v1.py`), le client `scripts/client_v1.py` doit continuer de
  fonctionner à l'identique.
- **Cause du défaut v1** : troncature explicite à `contexte_max_caracteres`
  (16 000 car.) dans `models/v1/config.yaml`, appliquée **avant** l'appel LLM
  — confirmé dans `app/api_v1.py::analyser_v1`.
- **Contraintes client** : P95 < 8 s (même longs), coût < 0,15 €/analyse,
  ~400 contrats/mois (~13/jour), aucune interruption, rollback immédiat.
- **Jeu d'éval** : 12 contrats (9 courts + 3 longs), seuils 0,75 (courts) /
  0,80 (longs), note = micro-F1 (voir nuance ci-dessous).
- **Score de confiance** : confiance LLM × corroboration (stabilité
  inter-chunks), global = minimum des clauses.
- **Découpage v2** : structurel (articles), taille cible 6 000 car. —
  confirmé par `models/v2/config.yaml::contexte_max_caracteres`.
- **Versionnage** : SemVer, patch auto-incrémenté **au build validé**
  (gate d'éval passé), jamais à la fusion — confirmé par
  `ops/deploy.py::publier` (rejoue le gate, refuse si échec, étiquette
  ensuite).
- **Canary** : paliers 10→50→100 %, critères v2 jamais moins bonne sur
  latence/erreurs/coût + strictement meilleure sur au moins un des trois.
- **Gel avant fusion (chantier 1)** : branche `dev`, deux tags protégés
  auto-posés (`revue-ok/<sha>`, `eval-ok/<sha>`) accumulés sur le même SHA
  figé, fusion `dev → main` en fast-forward strict seulement si les deux
  tags sont présents. `main` ne rejoue aucun gate. Détail complet dans
  `conception_figee/chantier1_llmops/gel-eval-avant-fusion.md` — **pas
  encore traduit en `.github/workflows/llmops.yml` réel** (le fichier fourni
  est un `[TEMPLATE]` générique, à réécrire).

## Écart révisé — fenêtre glissante (comptage → temporelle)

`conception_figee/pilotage/fenetre-glissante-seuils.md` avait décidé une
fenêtre **en nombre de requêtes** (50, min 30). Les tests d'acceptance
**fournis et figés** (`tests/acceptance/test_observabilite.py`) imposent une
interface **temporelle** (`fenetre_s`) sur `ops.deploy.surveiller` et
`ops.dashboard.resume`. Décision (2026-09-21) : garder les tests tels quels,
réviser la conception plutôt que les tests. Détail complet et valeurs
retenues (120 s / 300 s / minimum 10) :
[`docs/conception_revue/pilotage/fenetre-glissante-seuils.md`](docs/conception_revue/pilotage/fenetre-glissante-seuils.md).
Répercussions déjà révisées : `canary.md`, `tableau-pilotage.md` (+ PDF),
`questions_reponses.md` (Q9/Q10/Q12/Q14) — tous dans
`docs/conception_revue/`.

## Points mineurs sans action (voir `docs/analyse-coherence-conception.md`)

- `eval/run_eval.py` (stub) décrit la note comme un « rappel » (recall), la
  conception avait décidé un micro-F1 scindé courts/longs — pas de test qui
  verrouille la formule exacte, le split reste implémentable via le champ
  `seuil_note` par contrat.
- `.github/workflows/llmops.yml` fourni n'est qu'un squelette `[TEMPLATE]`
  (push `main`/PR/tags, pas de branche `dev`) — à réécrire entièrement pour
  refléter le mécanisme à deux tags.
- `app/api_v2.py` (stub) ne documente que 422/503, pas de 413 pour un
  document trop long — ajoutable sans conflit avec les tests fournis.

## État de l'implémentation (2026-09-21)

**Chantier 1 point 2 (pipeline `/v2/analyse`) implémenté et testé**, via le
plan `docs/superpowers/plans/2026-09-21-api-v2-pipeline.md` exécuté en
subagent-driven development (7 tâches, revue par tâche + revue finale de
branche complète). `app/pipeline/decoupage.py::decouper`,
`app/pipeline/extraction.py::extraire`, `app/pipeline/consolidation.py::consolider`,
`app/pipeline/confiance.py::scorer` et `app/api_v2.py::analyser_v2` (+ route
`POST /v2/analyse`) sont tous fonctionnels, plus `models/v2/config.yaml`
(bundle, stratégie `map_reduce_clauses`). Couverture : 27 tests unitaires
(bundle + pipeline + orchestration) et les 2 tests d'acceptance ciblés
(`test_contrat_v2_long_analyse_sans_troncature`,
`test_erreurs_explicites_jamais_de_500`), tous verts.

Décisions actées pendant l'implémentation, non documentées ailleurs — détail
dans `CHANGELOG.md` (entrée du jour) :

- `seed: 0` fixé dans le bundle v2 (`models/v2/config.yaml`), pour un gate
  d'évaluation stable.
- `scorer()` a gagné un paramètre `nb_sections: int` (la formule de
  corroboration a besoin du nombre total de sections, que `texte` seul ne
  donne pas) ; `texte` est conservé dans la signature pour compatibilité mais
  inutilisé pour l'instant.
- `decoupage.py::decouper` implémente **trois niveaux** (structurel →
  regroupement des blocs consécutifs jusqu'à `taille_max` → repli taille
  fixe avec chevauchement) plutôt que les deux esquissés initialement dans le
  plan — le regroupement est ce qui tient le budget d'appels LLM.
- `LIMITE_CARACTERES = 250_000` pour le garde-fou 413, vérifié désormais
  **dans `analyser_v2` elle-même** (pas seulement dans la route HTTP), pour
  protéger aussi les appelants directs hors HTTP (futur `app/gateway.py`).

**Toujours non implémenté, hors périmètre de ce plan** : `app/gateway.py`,
`eval/run_eval.py::evaluer`, `ops/deploy.py::*`, `ops/dashboard.py::*` —
restent `[STUB]`, `NotImplementedError`. Seuls `app/api_v1.py`,
`app/llm_client.py`, `app/telemetry.py`, `ops/drift_proxy.py`,
`ops/registry/` étaient `[FOURNI]` et fonctionnels dès le départ ; s'y
ajoutent maintenant `app/api_v2.py` et tout `app/pipeline/*`.

Deux schémas documentent l'architecture (le second est maintenant à jour
avec le code réel, pas seulement la cible) :

- le pipeline `/v1/analyse` **réel** (`docs/img/pipeline-v1_reel.drawio`) :
  tout est dans `app/api_v1.py`, seul l'appel LLM est délégué à
  `app/llm_client.py`.
- le pipeline `/v2/analyse` (`docs/img/pipeline-v2.drawio`) :
  `decoupage → extraction (map, 1 appel LLM/section) → consolidation
  (reduce) → confiance`, orchestré par `app/api_v2.py` — désormais
  implémenté tel que schématisé.

### Points connus, non corrigés ici, hors périmètre de ce plan

- **Risque de latence P95 pour le gate d'éval (chantier 1 point 3)** —
  **corrigé le 2026-09-23** : les appels LLM par section dans
  `app/api_v2.py::analyser_v2` sont désormais parallélisés
  (`ThreadPoolExecutor`, `MAX_APPELS_LLM_PARALLELES = 8`), voir `CHANGELOG.md`
  (2026-09-23). Mesuré sur le corpus réel avant correctif : jusqu'à 20
  appels séquentiels pour le contrat le plus long (c12), invisible en mode
  `MOCK` (~0,2 ms/appel) donc aucun test ne le détectait, mais probablement
  bloquant contre le vrai modèle au gate (`latence_p95_ms < 8000`).
- **Note de calibration découpage/corroboration pour le chantier 2** : le
  chevauchement (~250 car.) du repli taille fixe peut faire compter une
  clause à cheval sur deux chunks adjacents comme corroborée par la
  géométrie du découpage, pas par une détection multiple réellement
  indépendante ; à l'inverse, le regroupement de `_regrouper` peut fusionner
  des occurrences d'articles distincts dans une seule section, plafonnant
  leur corroboration à n=1. Aucun des 12 contrats du corpus ne déclenche
  aujourd'hui le repli taille fixe, donc ce biais est latent, pas actif —
  mais à garder en tête pour la calibration du score au chantier 2, puisque
  le signal de corroboration dépend en partie de la géométrie du découpage,
  pas seulement d'une détection répétée réelle par le modèle. Fait mesuré à
  l'appui de cette calibration (pas une nouvelle anomalie — la formule est
  implémentée telle qu'actée) : **100 % des scores de clause individuels,
  sur les 12 contrats du corpus, valent actuellement exactement 0,0** (pas
  seulement le minimum global — chaque clause individuellement).

## Topologie — où en est-on de « un artefact, un rôle par container » (2026-09-21)

`docs/spec-v2.md` §4 vise un artefact Docker unique et un rôle par container
(v1, v2, gateway) derrière Caddy. **Partiellement en place** :

| Service compose | Port hôte → container | Rôle |
| --- | --- | --- |
| `app` | 8000 → 8000 | complet (v1 + v2 + gateway), confort de dev — inchangé |
| `v2` | 8001 → 8000 | `/v2/analyse` + `/health` (`create_app_v2`) |
| `serveur_pilotage` | 8002 → 8000 | squelette `/pilotage/*` (501) + `/health` |
| `proxy` | 8080 → 8080 | proxy de dérive |
| `dashboard` | 8501 → 8501 | tableau de bord (stub) — inchangé |
| `azure-adapter` | interne 9000 | adaptateur Azure |

Reste à faire : container v1 isolé, container gateway, Caddy en frontal.
Conception : `docs/superpowers/specs/2026-09-21-v2-pilotage-containers-design.md`.

- **Ce sont des ports différents qui étaient voulus, pas des IP fixes** (demande
  initiale ambiguë, précisée par l'utilisateur) : pas de réseau Docker
  personnalisé.
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
- **Les 3 routes d'écriture du serveur de pilotage valident leur corps** avec
  les modèles du contrat gelé : corps valide → 501, corps invalide → 422.
- **`GET /health` du serveur de pilotage est hors contrat gelé**, non
  normatif : il n'existe que pour le healthcheck du container.
- Healthchecks en Python (`urllib.request`) et non `curl` : l'image
  `python:3.11-slim` n'embarque pas `curl`.
- Le service `dashboard` (8501) et la route `GET /pilotage/dashboard` font
  double emploi : arbitrage renvoyé au chantier 2.
- Tests : `MOCK=on uv run pytest -q` → **54 passed, 7 failed** (les 7 rouges
  attendent `ops/deploy.py`, `eval/run_eval.py`, `ops/dashboard.py`).

## Décision — périmètre du chantier 1 point 3 (2026-09-22)

**Chantier 1, point 3 (chaîne `llmops.yml` : gates → build → artefact
étiqueté → déploiement canary)** : périmètre tranché par l'utilisateur.
Point 3 = `llmops.yml` + `ops/deploy.py::publier/deployer_canary/promouvoir/rollback`,
**sans** `surveiller()` (détection de dérive + rollback automatique, qui
reste chantier 2) et **sans** `app/gateway.py` (routage réel du trafic
canary, qui reste chantier 2 aussi). Conséquence assumée :
`test_promotion_canary_puis_totale` et `test_rollback_en_une_operation`
(tests d'acceptance fournis, dépendent de `gateway.py`) resteront rouges
tant que le chantier 2 n'est pas fait — attendu, pas un défaut du point 3.
Repères déjà en main pour la suite : `conception_figee/chantier1_llmops/gel-eval-avant-fusion.md`
(mécanisme à deux tags `revue-ok`/`eval-ok`, détaillé et acté) et
`ops/deploy.py` (stub fourni, signatures des 4 fonctions restantes déjà
figées par les tests d'acceptance fournis).

Deux autres points tranchés le même jour :

- **`CANARY_PERCENT`/`MOCK` dans `.env`** : restent des valeurs par défaut
  statiques. Le pilotage dynamique du pourcentage canary relève du
  chantier 2 (registre/serveur de pilotage), pas de l'environnement de base.
- **Doublon `ops/dashboard.py` (8501) vs `GET /pilotage/dashboard`** : pas de
  duplication à résoudre. `ops/dashboard.py::resume()` reste la fonction de
  calcul (imposée par le test d'acceptance fourni `test_dashboard_par_version`
  dans `tests/acceptance/test_observabilite.py`) ; `GET /pilotage/dashboard`
  (serveur de pilotage) réutilise cette même fonction en interne plutôt que
  de recalculer l'agrégation. Le service `dashboard` (8501, `--serve`) reste
  une vue texte/HTML autonome héritée de la remédiation, en plus de la route
  JSON contractuelle. La conception (ADR 0001, Q6 de
  `conception_figee/chantier2_observabilite/questions_reponses.md`) avait été
  écrite avant d'avoir accès au stub réel et ne tranchait pas ce doublon
  explicitement ; c'est le test d'acceptance gelé qui fixe la réponse.

## Chaîne LLMOps — plan exécuté et fusionné (2026-09-22)

Les 8 tâches du plan (`docs/superpowers/plans/2026-09-22-chaine-llmops.md`)
sont terminées et relues : `prochaine_version`, `evaluer` (gate d'évaluation),
`publier`/`deployer_canary`/`promouvoir`/`rollback`, les 4 workflows
(`ci.yml`, `revue.yml`, `gate.yml`, `cd-main.yml`) qui remplacent
`llmops.yml`. `surveiller()` et `app/gateway.py` restent hors périmètre
(chantier 2), conformément à la décision de périmètre ci-dessus.

La revue finale de branche (avant fusion vers `dev`) a trouvé plusieurs
problèmes, corrigés dans la même vague de correctifs : les 4 tests
d'acceptance hors périmètre bloquaient `tests` (donc `evaluation`, donc
`eval-ok`) — marqués `xfail(strict=False)` ; le commentaire d'en-tête de
`cd-main.yml` affirmait à tort qu'aucun gate n'était rejoué sur `main` alors
que `publier()` sans `--rapport` relance un vrai gate payant ; le push Docker
vers `ghcr.io` se faisait avant le gate (`publier`), risquant de publier une
image jamais validée ; la version ne progressait jamais d'un run CD à
l'autre car `ops/registry/v*` (sauf `v1.0.0`) est gitignored sur chaque
runner — un nouveau step commit désormais le répertoire de version
fraîchement créé, poussé avec `GITHUB_TOKEN` (jamais un PAT, pour éviter une
boucle de déclenchement infinie sur `push: main`) ; le prérequis fast-forward-only
sur `main` (nécessaire à la validité du mécanisme à deux tags) était
implicite, maintenant documenté ; `revue.yml` n'avait pas de bloc
`permissions:` explicite.

**Fusionné dans `dev`** (commit `2f1c53c`, fast-forward local, worktree et
branche `sdd/chaine-llmops` supprimés après fusion — tests vérifiés verts
sur le résultat fusionné : 68 passed, 4 xfailed, ruff clean). **Poussée vers
GitHub** (`origin/dev`, 2026-09-22) : le dépôt distant `wawawaformation/mardik-api-mlops`
n'avait jusque-là que `main` (squelette de départ, `protected: false`).

> **Mise à jour 2026-09-23** : le compte de revue et les 4 secrets Azure
> sont désormais en place — voir la section « Prérequis GitHub » en bas de
> ce fichier. Le paragraphe ci-dessous décrit l'état d'alors.

**La chaîne reste non exercée de bout en bout en conditions réelles** : les
prérequis hors code restent à faire par l'utilisateur avant le premier vrai
run — compte `mardik-relecteur` (inscription manuelle : `gh` ne peut pas
créer un compte GitHub), secret `CI_TAG_TOKEN` (PAT à générer depuis ce
compte), secrets Azure (`AZURE_LLM_MODEL`, `AZURE_AI_ENDPOINT`,
`AZURE_AI_API_KEY`, `AZURE_AI_API_VERSION`), règles de protection de tag
(`revue-ok/*`, `eval-ok/*`, `v*` — faisable via `gh api`, décision explicite
de l'utilisateur de reporter), protection de branche `main` (GitHub n'a pas
de bouton « fast-forward only » natif ; l'équivalent le plus proche est
« Require linear history », qui interdit les merge commits sans être
strictement identique — la fraîcheur des deux tags reste de toute façon
vérifiée par `cd-main.yml` lui-même, donc cette protection est un filet
supplémentaire, pas le mécanisme principal). Les workflows sont implémentés
et relus mais jamais exécutés sur un vrai dépôt GitHub — un premier run réel
(tag `gate/<sha7>` puis fusion `dev` → `main`)
reste à faire une fois ces prérequis en place, avec une vigilance
particulière sur le push du registre par le bot (`GITHUB_TOKEN`) si des
règles de protection de branche plus strictes que prévu bloquent les pushs
de bots sur `main` (point relevé, non testé, lors de la revue finale de
branche).

## Chantier 2 (Observabilité) — démarré (2026-09-23)

- **Parallélisation des appels LLM v2** (préalable, hors chantier 2 à
  proprement parler mais fait le même jour) : `app/api_v2.py::analyser_v2`
  résout le risque de latence P95 noté le 2026-09-21 — voir `CHANGELOG.md`.
- **`ops/dashboard.py::resume/rendre_texte/rendre_html` implémentés**
  (TDD, `tests/unit/test_dashboard.py`). Fenêtre temporelle, agrégats par
  version (trafic, p50/p95, taux d'erreur, score moyen, coût total),
  erreurs exclues des latences/scores. `test_dashboard_par_version`
  (acceptance) n'est plus `xfail`.
- **Fusion des journaux v1/v2** : `resume()` sans `metriques` explicite lit
  désormais `METRICS_PATH` (v1) **et** une nouvelle variable
  `METRICS_PATH_V2` (défaut `ops/metrics_v2.jsonl`), sinon le trafic du
  container `v2` (journal séparé, voir topologie plus haut) serait invisible
  du tableau de bord. `docker-compose.yml` (service `dashboard`) reçoit
  `METRICS_PATH_V2`. **`ops/deploy.py::surveiller` a le même besoin, pas
  encore traité** (reste `[STUB]`) — même mécanisme (`_stores_par_defaut`,
  `ops/dashboard.py`) réutilisable quand `surveiller()` sera écrit.
- Suite : 76 passed, 3 xfailed (restants : `test_promotion_canary_puis_totale`,
  `test_rollback_en_une_operation` — dépendent de `app/gateway.py` ;
  `test_journal_derive_et_rollback_automatique` — dépend de
  `ops/deploy.py::surveiller`).
- **`app/gateway.py` implémenté** (TDD, `tests/unit/test_gateway.py`) :
  `choisir_version`, `GET /gateway/etat`, `POST /analyse` — route vers
  `analyser_v1`/`analyser_v2` selon `bundle.strategie`, relit le registre à
  chaque requête, `CANARY_PERCENT` force le pourcentage si défini. Piège
  FastAPI rencontré : la route déclarée `-> dict` faisait inférer
  `response_model=dict` à FastAPI, qui rejetait alors les réponses
  (`ReponseAnalyseV1`/`V2`, pas des `dict` bruts) — corrigé avec
  `response_model=None` explicite. `test_promotion_canary_puis_totale` et
  `test_rollback_en_une_operation` ne sont plus `xfail`. Suite : 84 passed,
  1 xfailed (reste `test_journal_derive_et_rollback_automatique`, dépend de
  `ops/deploy.py::surveiller`).
- **`ops/deploy.py::surveiller` implémenté** (TDD, `tests/unit/test_deploy.py`) :
  surveille le canary s'il y en a un, sinon l'active ; dérive sur score
  moyen/taux d'erreur/latence P95, minimum de mesures requis, rollback
  automatique + journal si dérive. `percentile()` et
  `stores_metriques_par_defaut()` de `ops/dashboard.py` rendues publiques et
  réutilisées (même besoin de fusion v1/v2 des journaux de métriques,
  maintenant traité aux deux endroits qui en avaient besoin). Plus aucun
  test `xfail` dans `tests/acceptance/test_observabilite.py` : **93 passed**
  sur la suite complète, ruff clean. Le cœur logique du chantier 2
  (gateway, dashboard, surveiller) est posé ; restent le câblage HTTP du
  serveur de pilotage, le client web, et `docs/exploitation.md`.
- **`ops/serveur_pilotage.py` implémenté** (TDD, `tests/unit/test_serveur_pilotage.py`
  réécrit). **Conflit de conception tranché** : la conception voulait deux
  nouveaux fichiers (`ops/registre.json` par fingerprint,
  `ops/journal_pilotage.jsonl`) ; le serveur de pilotage réutilise
  `ops/registry/` existant à la place (une seule source de vérité, déjà
  branchée sur `app/gateway.py`/`ops/deploy.py`) — détail complet et
  conséquences (identité par SemVer pas fingerprint, v1/v2 = `v1.0.0` vs
  tout le reste, reshape du journal) dans
  `docs/conception_revue/pilotage/formats-ops.md` (nouveau). Seul vrai
  nouveau fichier : `ops/regles_pilotage.json` (les 4 seuils ajustables,
  qui n'avaient nulle part où vivre — `ops.deploy.surveiller` les prend en
  paramètres de fonction). `ops/deploy.py::deployer_canary/promouvoir/
  rollback` acceptent maintenant `**details` (déclencheur/signal) transmis
  au journal, rétrocompatible. `POST /pilotage/promotion` implémente le
  vrai critère « v2 ≥ v1 » de `canary.md` (contraintes client + jamais
  moins bonne + strictement meilleure sur ≥1 signal). **Correctif
  d'isolation** : `tests/conftest.py` isole maintenant aussi
  `METRICS_PATH_V2` (sans ça, les routes sans `metriques` explicite
  auraient lu le vrai `ops/metrics_v2.jsonl` du dépôt). Hors périmètre,
  documenté : régénération Caddyfile (pas de container Caddy encore), et
  bouclage des règles ajustables sur la décision automatique. Suite :
  **100 passed**, ruff clean.
- **`client_web/` câblé sur `ops/serveur_pilotage.py`** (2026-09-23) : les 4
  pages de la maquette figée recopiées et branchées (HTML/CSS/JS vanilla,
  `app.js` partagé). Écart documenté : la carte « distribution du score »
  de la maquette montrait un histogramme à 10 tranches, le contrat gelé
  n'expose qu'une proportion unique (`proportion_score_faible`) — remplacé
  par une seule barre plutôt que d'inventer des données. Paliers canary de
  `actions.html` limités à 50/100 % (10 % vient de la chaîne CD, pas de cet
  écran — cohérent avec `Promotion.cible_pct` du contrat gelé, `enum:
  [50, 100]`). CORS ouvert sur `ops/serveur_pilotage.py`
  (`allow_origins=["*"]`) car pas de Caddy en frontal pour unifier les
  origines. Service `client_web` (port 8503) ajouté à `docker-compose.yml`.
  Vérifié manuellement (pas de navigateur ici) : `node --check` sur tout le
  JS, formes JSON réelles de l'API conformes à ce que `app.js` consomme,
  en-tête CORS présent, 6 fichiers statiques en 200 — **pas de rendu visuel
  confirmé**. Chantier 2 : reste `docs/exploitation.md`.
- **`docs/exploitation.md` complété** (2026-09-23), les 7 sections du
  gabarit. Point notable, section 7 (preuve d'exécution) : transcript
  **réel**, exécuté en direct (`ops.deploy.deployer_canary` → trafic sain →
  dérive de score simulée → `surveiller()` détecte et déclenche
  `rollback()` → trace au journal), pas un exemple fabriqué — mais limité
  au mécanisme de décision `ops.deploy` (`MOCK=on`, sans Docker) : la démo
  HTTP bout en bout via la gateway + le vrai proxy de dérive
  (`scripts/traffic_sim.py`, `make traffic`) n'a pas été exécutée ici
  (nécessite `MOCK=off` pour que `DRIFT=` ait un effet — le client LLM
  court-circuite le proxy en `MOCK=on` — donc Ollama ou Azure réel, coût
  réel), commande fournie pour que l'utilisateur la rejoue. **Les 6 points
  du chantier 2 (`TODO.md`) sont maintenant tous cochés.**

## ⚠️ Incident (2026-09-23) : dépense LLM réelle non autorisée + bug SemVer découvert

En testant `scripts/demo.py` (juste écrit, pour vérifier qu'il échoue
proprement sans services disponibles), une exécution complète a eu lieu par
erreur contre la stack Docker de l'utilisateur, réellement démarrée avec
`MOCK=off`/`LLM_PROVIDER=azure` — **~0,15 € et 50 appels LLM facturés, sans
autorisation préalable**. Leçon retenue : ne jamais lancer un script qui
frappe des URL réseau par défaut (même pour un test de robustesse) sans
vérifier d'abord si des services répondent déjà, ou sans confirmation
explicite si `.env` n'est pas garanti `MOCK=on`.

En creusant l'état du registre pollué par cette exécution
(`ops/registry/v1.0.1/` contenait en réalité le bundle **v2**, pas un
patch de v1), un **vrai bug produit** a été découvert et corrigé :
`ops/deploy.py::prochaine_version` mélangeait les lignées v1/v2 — avec
seulement `v1.0.0` dans le registre (état initial normal), le premier vrai
déploiement v2 via `cd-main.yml` aurait été étiqueté `v1.0.1` au lieu de
`v2.0.0`. Corrigé (TDD, `bundle="v2"` filtre désormais par lignée via
`manifest.json::strategie`) — détail complet dans `CHANGELOG.md`.

**Nettoyage fait en fin de journée** : l'artefact `ops/registry/v1.0.1/`
(bundle v2 mal étiqueté) a été déplacé en
`ops/registry/_incident-2026-09-23-v1.0.1/` — nom hors motif SemVer, donc
ignoré par `Registry.versions()`, et réversible. Le registre repart propre
(`v1.0.0` active, aucun canary) et `prochaine_version` y produit bien
`v2.0.0`.

## Second bug trouvé le même jour : rollback pouvait mettre `active: null`

En diagnostiquant « la démo répond tronqué » (l'utilisateur croyait avoir
promu à 100 %), la lecture de `ops/registry/journal.jsonl` a montré qu'il
n'y avait eu **aucune promotion**, seulement trois rollbacks — « rollback »
signifie littéralement *v1 à 100 %*, donc v1 (qui tronque) servait bien
tout le trafic : comportement attendu, pas un bug. **Mais** le journal a
révélé un vrai défaut : le second rollback (sans canary ni `precedente`)
avait mis `active: null`, état dans lequel la gateway répond **500** sur
`/analyse` (`registry.bundle(None)` → `TypeError`). Le système est resté
ainsi 12 minutes en conditions réelles. Corrigé en TDD (2 tests rejouant la
séquence) : sans rien à annuler, `rollback()` garde l'active en place.

**Leçon de méthode confirmée deux fois dans la journée** : le journal de
pilotage et les fichiers d'état (`index.json`, `journal.jsonl`) racontent
précisément ce qui s'est passé — les lire *avant* de formuler une
hypothèse, plutôt que de deviner à partir du symptôme rapporté.

## Environnement technique

- Dépôt git propre à `mardik-api-mlops`, remote `origin` =
  `git@github.com:wawawaformation/mardik-api-mlops.git` (rien poussé pour
  l'instant).
- `uv` pour les dépendances Python, `make` pour les commandes courantes
  (`make test`, `make eval`, `make ci`, voir `README.md`).
- MOCK=on réservé à la CI (rejoue `eval/fixtures/`), `DRIFT=` pour simuler
  une dérive via `ops/drift_proxy.py`.
- **Fournisseur LLM = Azure AI Inference** (`LLM_PROVIDER=azure`,
  `LLM_MODEL=gpt-5.4-mini`), endpoint `.../openai/v1` (nouvelle API unifiée).
- **`ops/azure_adapter.py`** (nouveau, non fourni) : adaptateur entre
  `ops/drift_proxy.py` [FOURNI] et le vrai endpoint Azure. Nécessaire car ce
  fournisseur/endpoint rejette `?api-version=...` (toujours ajouté par le
  proxy fourni) et le modèle refuse `max_tokens` (attend
  `max_completion_tokens`). Câblé via le service docker `azure-adapter` ;
  `AZURE_AI_ENDPOINT` (vu par le proxy) pointe dessus, la vraie URL Azure est
  dans `AZURE_AI_REAL_ENDPOINT`. Décision explicite : ne jamais modifier
  `ops/drift_proxy.py` ni `app/llm_client.py` (fournis) pour ce problème.
  Détail : `CHANGELOG.md` (2026-09-21, « environnement Docker »).
- `/v1/analyse` vérifiée fonctionnelle avec cette config (curl, `client_v1.py`,
  `make test-integration`).

## Conventions de travail (utilisateur)

- Français pour les échanges, code en anglais commenté en français.
- Simple > flexible, YAGNI, modifications ciblées.
- Suivi dans ce dépôt : `CHANGELOG.md` (réalisé, ordre inverse), `TODO.md`
  (reste à faire), `MEMORY.md` (ce fichier). Écarts de conception documentés
  dans `docs/conception_revue/`, jamais dans `conception_figee/`.
- Pas de commit sans accord explicite de l'utilisateur.
- Un seul agent par défaut ; subagents exceptionnels, justifiés par un gain
  clair.
- L'utilisateur est développeur PHP confirmé, étudiant en dev IA agentique —
  pédagogie bienvenue.

## Prérequis GitHub — état au 2026-09-23 (fin de journée)

| Prérequis | État |
| --- | --- |
| Compte de revue dédié | ✅ `connarddu16-design`, collaborateur `write` |
| `revue.yml` pointé sur ce login | ✅ (gardait `mardik-relecteur`, jamais enregistré) |
| Secrets Azure (4) | ✅ poussés via `gh secret set` depuis `.env` |
| Secret `CI_TAG_TOKEN` | ✅ PAT classique du compte de revue (`push` sans `admin`) |
| Protections tags / branche `main` | ⬜ reportées (choix de l'utilisateur) |

Le vrai nom du compte de revue est **`connarddu16-design`**, pas
`mardik-relecteur` : ce dernier était un nom de travail de la conception,
jamais enregistré sur GitHub. Le garde de `revue.yml` le comparait
pourtant en dur — il n'aurait jamais matché, donc `revue-ok` jamais posé,
donc fusion vers `main` refusée sans message clair. Corrigé.

`AZURE_AI_API_VERSION` est poussée à `2024-05-01-preview` mais n'a aucun
effet : `ops/drift_proxy.py` [FOURNI] l'ajoute à l'URL amont,
`ops/azure_adapter.py` la retire, l'API `/openai/v1` la rejette. Elle
n'est donc pas dans `.env` en local, et c'est normal.

## ⚠️ Mise à plat des intentions (2026-09-23) — `intents.md` fait foi

Après l'incident de la PR #1 (fusionnée au lieu d'être approuvée), mise à
plat morceau par morceau de ce que l'utilisateur veut réellement de la
chaîne. Résultat : **`intents.md` à la racine du dépôt**, à lire avant
toute intervention sur la chaîne LLMOps.

**Le déclic, et la clé de lecture de tout le dispositif** : distinguer
**informer** de **prouver**. Un même test peut jouer deux rôles
incompatibles — informer le développeur (sans trace, sans conséquence,
rejouable) ou établir un fait qui autorise l'étape suivante (écrit,
attaché à un SHA, ordonné). Tant qu'on ne sépare pas les deux, les trois
lots se ressemblent et on ne comprend pas pourquoi il en faut trois.

Second principe : **attraper au plus tôt, au lot le moins cher** (lot A =
secondes, lot B = attention humaine, lot C = argent).

**Changement de topologie** : la revue se fait désormais sur une PR
**`feature/x → dev`**, plus `dev → main`. La conception gelée faisait
développer directement sur `dev`. Conséquence : **deux** fusions
fast-forward au lieu d'une.

**La conception gelée n'est pas désavouée.**
`conception_figee/chantier1_llmops/gel-eval-avant-fusion.md` est juste sur
presque tout (deux tags immuables, fraîcheur par SHA, fast-forward strict,
aucun gate rejoué sur main, déclenchements manuels). C'est son **diagramme**
qui a coûté deux jours de compréhension : la note 0c de
`img/ci-feature-dev.drawio` présente la PR comme un pis-aller administratif
(« un `git diff` ferait aussi bien — il est nécessaire parce que main est
protégé »). C'est faux : un `git diff` informe, la PR est le **seul
mécanisme qui transforme une relecture humaine en fait vérifiable par un
automate**. Pièce centrale, pas accessoire.

Cinq écarts consignés dans
`docs/conception_revue/chantier1_llmops/gel-eval-avant-fusion.md` :
topologie `feature/x`, rôle réel de la PR, alerte d'évaluation
conditionnelle dans le lot A (sans tag), garantie que le lot A est vert
avant la revue, et le second compte GitHub comme **contrainte de
plateforme** (GitHub interdit d'approuver sa propre PR) et non comme
intention — la conception assume l'auto-revue.

**Point resté ouvert** : les TA mockés (`tests/acceptance/`) — lot A avec
les TU/TI, ou première marche du lot C ? Ils tournent deux fois
aujourd'hui ; la duplication est volontaire (le gate ne peut pas supposer
que le lot A a tourné sur *ce* SHA) mais n'a jamais été tranchée.
**Tranché le 2026-09-23, voir ci-dessous.**

## Chaîne LLMOps alignée sur `intents.md` (2026-09-23)

Plan `docs/superpowers/plans/2026-09-23-chaine-llmops-intents.md` exécuté
sur `feature/chaine-llmops-intents`. Les quatre écarts ouverts sont fermés.
À retenir, dans l'ordre de ce qui coûte le plus cher à réapprendre :

**1. Ne jamais activer *require a pull request before merging*** sur `dev`
ni sur `main`. C'est le piège le plus coûteux de ce lot : cette règle
interdirait le `git push origin dev` de la fusion fast-forward — exactement
le geste que la chaîne impose, puisque **aucun des trois boutons de fusion
de GitHub ne fait de fast-forward** (merge commit, squash et rebase
fabriquent tous un nouveau SHA, que les tags de preuve ne suivent pas). Les
rulesets posés se limitent donc à : force-push et suppression bloqués,
*require linear history*, sur `dev` et `main` ; tags `revue-ok/*`,
`eval-ok/*`, `v*` immuables et non supprimables (`gate/*` reste libre, c'est
un déclencheur, pas une preuve). **L'interdit de fusionner sans preuve est
porté par les tags, pas par la plateforme** — c'est précisément ce que I5
cherchait en choisissant le tag.

**2. D4 tranché — option 1** : les TA mockés restent dans le lot A (`ci.yml`)
*et* dans le lot C (`gate.yml`). La duplication est **voulue** : au lot A ils
**informent** (gratuits, ils doivent voir une régression au push), au lot C
ils **prouvent** (le gate ne peut pas supposer que le lot A a tourné sur *ce*
SHA). Deux rôles du même test, pas un doublon. Justifié par écrit dans
`docs/exploitation.md` § 3 et en commentaire dans `gate.yml` pour qu'aucune
relecture future ne le « nettoie ».

**3. `alerte-eval.yml` rend le lot A payant sur quatre chemins** :
`models/*/config.yaml`, `app/pipeline/**`, `app/llm_client.py`, `eval/**`.
Un push sur `feature/**` qui les touche déclenche 12 contrats d'évaluation
réelle. Ce workflow **ne pose aucun tag et ne reçoit aucun jeton
d'écriture** : s'il posait `eval-ok`, on obtiendrait la preuve sans passer
par la revue et l'ordre revue → gate s'effondrerait (I2 + I6). Une alerte
rouge ne bloque rien — le garde de `revue.yml` ne regarde que `ci.yml`.

**4. Contrainte de plateforme à ne pas réessayer** : un workflow déclenché
par `pull_request_review` ne peut pas dépendre d'un job d'un autre
workflow — `needs:` ne relie que des jobs d'une même exécution, et
`workflow_run` ne va que dans l'autre sens. D'où le garde « lot A vert » de
`revue.yml` écrit comme un appel à l'API GitHub Actions sur
`workflows/ci.yml/runs?head_sha=…` (et non `gh pr checks`, qui attendrait
*tous* les checks du SHA, y compris l'alerte d'évaluation). Renommer
`ci.yml` casserait ce garde.

**Reste ouvert** : la vérification bout en bout sur une vraie PR
`feature/x → dev` approuvée par `connarddu16-design`. Le cas « CI rouge » du
garde n'a jamais pu être vérifié en réel — les 17 exécutions de `ci.yml` de
l'historique sont toutes vertes.

## Script de démo CI/CD (2026-09-24)

`docs/demo-ci.md` : déroulé Dire / Faire / Montrer de la chaîne complète
(`make ci` → `ci.yml` → `revue.yml` → ff `dev` → `gate.yml` → ff `main` →
`cd-main.yml`). Choix : changement anodin hors chemins sensibles (pas
d'alerte payante), refus du gate sans `revue-ok` montré en premier
(gratuit). Deux effets de bord de `cd-main.yml` à connaître : il pousse un
commit `chore(registry)` sur `main` (réaligner `dev` ensuite) et **ne
committe pas `ops/registry/index.json`** — l'état du canary posé en CI
n'arrive pas dans le dépôt (question ouverte dans `TODO.md`).

## Démo via Caddy — pièges connus (2026-09-25)

Caddy (port **8090**) est le point d'entrée de la démo, API et client web
compris (`client_web` en `API_BASE` relatif : ouvert sur 8503, ses appels
API partent vers 8503 et échouent en 404 « File not found »). Script :
`docs/demo-v1-v2-pilotage.md`, collection `bruno/demo-cto-caddy/` ;
`bruno/secours-ports-directs/` = repli sans Caddy.

Ce qui surprend en direct, tous vérifiés en répétition :

- **Tableau de bord = fenêtre glissante de 5 min** (`FENETRE_DASHBOARD_S`) :
  sans trafic récent, `0 %/0 %` — pas une panne.
- **Score de confiance v2 presque toujours à 0** : biais de la formule de
  corroboration, pas du modèle. Requêtes 3 (0,99) / 3b (0) le prouvent.
  Ne pas « corriger » à chaud en codant 1 en dur (fausse mesure, désactive
  la règle `score_faible`, casse les tests, relance l'éval payante).
- **Promotion : 409 attendu** (10 mesures par version sur 2 min) ; depuis
  le 2026-09-28 les refus sont journalisés (`promotion_refusee`), un
  rollback sans canary l'est aussi.
- **Le modèle varie** (`MOCK=off`) : une « durée » fantôme apparaît ou non
  sur le texte de remplissage. Ne promettre dans le script que ce qui a
  été rejoué.

Outillage : les `.bru` se vérifient avec le parseur officiel
(`@usebruno/lang`, `bruToJsonV2`) plutôt qu'en faisant retester dans
l'interface. Deux collections aux noms proches ont déjà été confondues
(« la requête a disparu ») : vérifier le dossier ouvert avant de chercher
un bug.
`ops/registry/journal.jsonl` et `ops/metrics*.jsonl` sont ignorés par git,
`ops/registry/index.json` est suivi (modifié par chaque test de pilotage).

## ▶ Reprendre ici — préparation du rendu (état au 2026-09-28)

**Plus d'oral : c'est un rendu écrit.** Tout écart au brief doit être
justifié par écrit, pas « défendu ». Les deux documents du rendu sont
**hors du dépôt**, à la racine de `mardik_nouvelle_version/livrables/`
(dossier créé à la demande explicite de l'utilisateur, exception au gel
de la racine) :

- `livrables/README.md` — note de rendu pour l'évaluateur : où est chaque
  livrable, comment lancer (`docker compose up`, client sur
  <http://localhost:8090>), choix justifiés (5 workflows au lieu de
  `llmops.yml`, rollback via `ops/deploy.py` et pas un workflow GitHub,
  frontend en lien local, validation humaine de l'enrichissement),
  limites connues ;
- `livrables/checklist.md` — brief critère par critère : tout est ✅, sauf
  2 écarts 📝 justifiés dans le README (rollback « via la chaîne »,
  lien local). Liste « Actions avant de livrer » = le reste à faire.

Fait le 2026-09-28 (commits sur `feature/demo-ci`, **non poussés**, 36
commits d'avance sur `origin/dev`) : 3e boucle enrichissement du jeu
d'éval (`7d0ce2c`), lint Markdown de tout le dépôt + `.markdownlint-cli2.jsonc`
(`811bdc6`), déclencheur/signal au journal + refus de promotion tracés
(`c02a0b9`), règles ajustables consommées par `surveiller()` + règle
`cout_moyen` + histogramme du score (`53da1ca`). 144 tests verts, ruff et
markdownlint propres.

Reste à faire (ordre) : voir `TODO.md` § « Rendu — reste à faire ».

Pièges : le score v2 biaisé vers 0 + la règle `score_faible` (> 20 % de
scores < 0,6) ⇒ `ops.deploy surveiller --boucle` rollbackera le canary v2
presque à coup sûr (non lancé par docker compose). Toujours non commités
volontairement : changements Bruno de l'utilisateur, sa modif de
`.github/workflows/alerte-eval.yml`, effets de bord `ops/registry/index.json`
et `ops/regles_pilotage.json`. Un push déclenche l'éval payante
(`alerte-eval.yml`, chemins `eval/**` touchés).
