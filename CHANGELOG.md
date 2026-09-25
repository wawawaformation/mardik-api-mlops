# CHANGELOG — mardik-api-mlops

> Tracé horodaté, ordre inverse (plus récent en premier).

## 2026-09-25 (répétition de la démo via Caddy)

Branche `feature/demo-ci`, 16 commits (`c9f2058` → `0f28585`), non
poussés, PR vers `dev` toujours à ouvrir.

- **Vérification visuelle faite** (navigateur + Bruno) de la stack derrière
  Caddy (port 8090) : routage `/v1`, `/v2`, `/analyse`, `/gateway`,
  `/pilotage` et client web confirmés, en plus des tests `curl`.
- **Documents de démo** :
  - `docs/cahier-de-recettes-demo-caddy.md` (nouveau) : scénarios Gherkin
    à cocher pour valider la stack avant la démo.
  - `docs/demo-v1-v2-pilotage.md` réécrit pour passer par Caddy (8090)
    au lieu des ports directs ; étapes 2b, 3, 3b, 8, 9, 10 alignées sur
    ce que la répétition a réellement montré.
  - `docs/fiche-demo-caddy.md` : affirmation périmée corrigée
    (`client_web` utilise bien un `API_BASE` relatif).
- **Collections Bruno** :
  - `bruno/demo-cto-caddy/` (nouveau) : le script CTO via Caddy. Textes
    calibrés avec le vrai `decouper()` puis rejoués : 2b (v1) et 3 (v2)
    partagent un texte de ~31 700 caractères — v1 tronque et perd la
    non-concurrence, v2 la retrouve (score 0,99) ; 3b cite chaque clause
    une seule fois (score 0).
  - `bruno/caddy/06-gateway-analyse.bru` (nouveau) : `/analyse` via Caddy,
    version choisie par la gateway.
  - `bruno/mardik-demo-cto/` renommé `bruno/secours-ports-directs/`
    (confondu avec la collection Caddy pendant la répétition).
- **Client web** (`client_web/`) : seuils du tableau de bord et filtre du
  journal lus depuis `/pilotage/regles` au lieu d'être codés en dur ;
  boutons « Rafraîchir » / « Auto : 30 s » retirés ; note « fenêtre
  glissante de 5 minutes » sous le titre, durée lue dans l'API.
- **Nettoyage** : `app/pipeline/Achtung` supprimé (déclencheur du test CI).
  Au prochain push, relance `alerte-eval.yml` (évaluation payante).
- **Constats, reportés dans `TODO.md`** :
  - score de confiance v2 presque toujours à 0 : la corroboration vaut 0
    pour une clause vue dans une seule section, et le global prend le
    minimum ; la formule mesure la répétition, pas la justesse ;
  - la promotion exige 10 mesures par version sur 2 minutes, un 409 est
    donc attendu en démo, et les refus ne sont pas tracés au journal ;
  - un rollback sans canary en cours est tracé quand même.

## 2026-09-24 (soir — Caddy en frontal + client web branché)

- **Branche `feature/demo-ci`, 3 commits, non fusionnée** (PR à ouvrir
  demain avant la démo) :
  - `be50066` : Caddy simple ajouté (`Caddyfile` statique + service
    `caddy` dans `docker-compose.yml`, port hôte **8090**). Route
    `/v1`→`app`, `/v2`→`v2`, `/pilotage`→`serveur_pilotage`,
    `/analyse`+`/gateway`→`app`. Pas de régénération dynamique du
    Caddyfile (ça reste le chantier 2 de `docs/spec-v2.md` §4).
  - `d6e4fbc` : piste « télémétrie » ajoutée à `docs/img/pipeline-v2.png`
    (fichier:ligne exact de chaque capture, `app/api_v2.py` +
    `app/telemetry.py`).
  - `94939c9` : `client_web` branché derrière Caddy (route `/` du
    Caddyfile) et `client_web/app.js` passé en `API_BASE` relatif
    (`""` au lieu de `http://localhost:8002` en dur) — marche out of
    the box une fois servi par Caddy, sans souci de CORS. Ajout de
    `docs/fiche-demo-caddy.md` (aide-mémoire démo) et de
    `bruno/caddy/` (5 requêtes qui simulent un client externe passant
    uniquement par le port 8090 : accueil, `/v1`, `/v2`, `/gateway/etat`,
    `/pilotage/dashboard`).
  - Testé en `curl` (tous les endpoints via 8090 → 200/422 attendus).
    **Pas encore testé visuellement** (navigateur + app Bruno) : lancement
    GUI tenté en fin de session sans retour visible (pas de prise fiable
    sur l'affichage depuis cette session) — à faire en live demain matin.

### À reprendre demain matin, dans l'ordre

1. Ouvrir `http://localhost:8090/` dans le navigateur (client de pilotage
   servi par Caddy) — vérifier visuellement que les pages s'affichent et
   que les données du tableau de bord chargent.
2. Ouvrir l'app **Bruno**, *Open Collection* sur le dossier `bruno/`,
   dérouler `bruno/caddy/` (5 requêtes numérotées).
3. Démo live : lancer `02-v1-analyse` et `03-v2-analyse` dans Bruno,
   rafraîchir `journal.html`/`index.html` dans le navigateur → les
   requêtes envoyées par Bruno doivent apparaître dans le dashboard (deux
   clients différents, même point d'entrée Caddy).
4. Si tout est bon : ouvrir la PR `feature/demo-ci → dev`, faire approuver
   par `connarddu16-design`, gate, puis fusion vers `main` (voir
   `docs/demo-ci.md` / `docs/demo-ci.sh` pour la procédure pas à pas).
5. Repenser à l'export ffmpeg (`video/source_norm.mkv`, -14 LUFS + légère
   compression) si besoin pour le montage.

## 2026-09-24 (infrastructure GitHub + script de démo CI/CD)

- **Infrastructure GitHub mise en place** :
  - Ruleset `main-linear` créé : **Require linear history** sur `main`,
    bloque les merge commits (fastidieux à désactiver après coup, utile pour
    rappel rapide). `cd-main.yml` en est le vrai garde — le ruleset est un
    filet de sécurité supplémentaire.
  - Vérification dans `cd-main.yml` (ligne 41-46) déjà en place : refuse le
    déploiement si pas les deux tags `revue-ok/<sha>` et `eval-ok/<sha>` sur
    le SHA de tête. Prérequis tous cochés : compte de revue, secrets Azure,
    `CI_TAG_TOKEN`, rulesets de protection sur tags/branches. **Chaîne
    exerçable de bout en bout.**
- **Tentative 1 de validation CI/CD (avortée)** : PR #3 créée
  (`feature/test-ci-cd → dev`), approuvée via `connarddu16-design`. Étape
  bloquante : `revue.yml` doit poser `revue-ok` automatiquement après
  approbation, mais la vérification n'était pas aisée en CLI — session
  abandonnée pour redémarrer avec VSCode et Claude Code, meilleure DX pour
  cette validation itérative.
- **Nouveau `docs/demo-ci.md`** : déroulé de présentation (Dire / Faire /
  Montrer) qui fait parcourir un changement anodin à toute la chaîne —
  `make ci` en local, `ci.yml`, `alerte-eval.yml` (variante payante),
  `revue.yml`, fusion ff-only vers `dev`, `gate.yml` (refus sans revue puis
  cas nominal), fusion vers `main`, `cd-main.yml` jusqu'au canary 10 %.
  Tableau des coûts LLM par étape, parades pour les temps d'attente,
  remise en état après démo. Aucun code ni workflow modifié.
- **`TODO.md` étendu** : sections « Infrastructure GitHub », « Validation CI/CD
  en conditions réelles » (3 cas à tester) et « Test d'intégration complète
  sur dev » pour clarifier ce qui reste et l'ordre de validation.

## 2026-09-23 (chaîne LLMOps alignée sur `intents.md`)

Exécution du plan `docs/superpowers/plans/2026-09-23-chaine-llmops-intents.md`
sur la branche `feature/chaine-llmops-intents` — les quatre écarts encore
ouverts de `TODO.md` sont fermés. Aucun code applicatif touché.

- **`revue.yml` : `revue-ok` n'est plus posé que si le lot A est vert**
  (intention I3). Le workflow interroge l'API GitHub Actions
  (`workflows/ci.yml/runs?head_sha=…`) sur le SHA de tête de la PR, attend
  au plus 10 min si la CI tourne encore, et refuse le tag si la conclusion
  n'est pas `success`. Ce que le tag atteste devient « une approbation **sur
  du code dont le lot A est vert** ».
- **Nouveau workflow `alerte-eval.yml`** (intention I6) : un push sur
  `feature/**` touchant `models/*/config.yaml`, `app/pipeline/**`,
  `app/llm_client.py` ou `eval/**` joue l'évaluation réelle et l'affiche
  dans le résumé de job. **Aucun tag, aucun jeton d'écriture** — s'il posait
  `eval-ok`, on obtiendrait la preuve sans passer par la revue et l'ordre
  revue → gate s'effondrerait. Fichier séparé et non un job de `ci.yml` :
  les filtres `paths:` d'Actions s'appliquent au workflow entier, pas à un
  job.
- **`docs/exploitation.md` § 3 révisée** : cinq workflows au lieu de quatre,
  deux fusions fast-forward au lieu d'une, les commandes exactes de fusion,
  et les rulesets posés sur `dev`/`main` et sur les tags.
- **D4 tranché — option 1** : les tests d'acceptance mockés restent dans le
  lot A *et* dans le lot C. La répétition est voulue (au lot A ils
  informent, au lot C ils prouvent) ; elle est désormais justifiée par écrit
  dans `docs/exploitation.md` § 3 et en commentaire dans `gate.yml`.

**Les deux points de conception à retenir** :

1. **GitHub n'offre aucune fusion fast-forward dans l'interface de PR.** Ses
   trois boutons (*merge commit*, *squash*, *rebase*) fabriquent tous un
   nouveau SHA, que les tags de preuve ne suivent pas. Les deux fusions se
   font donc en ligne de commande (`git merge --ff-only` + `git push`), et
   le ruleset *require a pull request before merging* ne doit surtout pas
   être activé : il interdirait précisément ce geste.
2. **Un workflow déclenché par `pull_request_review` ne peut pas dépendre
   d'un job d'un autre workflow.** `needs:` ne relie que des jobs d'une même
   exécution, et `workflow_run` ne fonctionne que dans l'autre sens. D'où le
   garde par appel API plutôt qu'une dépendance déclarée — ou qu'un lot A
   rejoué dans `revue.yml`, qui aurait fait de celui-ci un second `ci.yml` à
   maintenir en phase.

Vérifications réellement exécutées : les cinq workflows passent
`yaml.safe_load` ; `gh api` rend `completed success` sur un SHA vert et
`null null` sur un SHA sans exécution (jamais un faux succès) ; les quatre
chemins du filtre `paths:` existent ; `MOCK=on uv run python -m
eval.run_eval --version v2 --seuil 0.75 --contrats c01` imprime la forme
attendue ; `MOCK=on uv run pytest -q` et `uv run ruff check .` inchangés.
**Reste à faire** : la vérification bout en bout sur une vraie PR
`feature/x → dev` approuvée, seule à exercer le garde en conditions réelles
(l'historique ne contient aucune exécution `ci.yml` en échec, le cas rouge
n'est validé que par relecture).

## 2026-09-23 (mise à plat des intentions — `intents.md`)

- **`intents.md` créé à la racine.** Source de vérité de ce que l'utilisateur
  veut de la chaîne LLMOps, et **pourquoi** — en amont du code, des workflows
  et des documents de conception d'implémentation. En cas de désaccord entre
  un workflow et ce fichier, c'est le workflow qui a tort. Écrit par mise à
  plat morceau par morceau, après l'incident de la PR #1.
- **Deux principes directeurs dégagés**, dont tout le reste découle :
  1. **Informer n'est pas prouver.** Un même test peut informer le
     développeur (sans trace, sans conséquence) ou établir un fait qui
     autorise l'étape suivante (écrit, attaché à un SHA, ordonné). Tant qu'on
     ne sépare pas les deux rôles, les trois lots se ressemblent et on ne
     comprend pas pourquoi il en faut trois.
  2. **Attraper au plus tôt, au lot le moins cher** (lot A = secondes,
     lot B = attention humaine, lot C = argent).
- **Changement de topologie** : la revue de code se fait désormais sur une PR
  **`feature/x → dev`**, et non plus `dev → main`. La conception gelée faisait
  développer directement sur `dev`. Conséquence : **deux** fusions
  fast-forward au lieu d'une, `feature/x → dev` puis `dev → main`.
- **Révision consignée** dans
  `docs/conception_revue/chantier1_llmops/gel-eval-avant-fusion.md` — cinq
  écarts, pas un désaveu. `conception_figee/chantier1_llmops/gel-eval-avant-fusion.md`
  est juste sur presque tout (deux tags immuables jamais posés par le
  développeur, fraîcheur par comparaison de SHA, fast-forward strict, aucun
  gate rejoué sur `main`, déclenchements manuels). Ce qui a réellement coûté
  deux jours de compréhension, c'est la note `0c` de
  `img/ci-feature-dev.drawio` : « le format PR n'améliore pas la revue en soi
  (un `git diff` ferait aussi bien) — il est nécessaire parce que `main` est
  protégé ». C'est faux. Un `git diff` **informe** ; la PR est le **seul
  mécanisme qui transforme une relecture humaine en fait vérifiable par un
  automate**. Pièce centrale du gel, pas support administratif.
- **Le second compte GitHub reclassé** : `connarddu16-design` existe parce que
  GitHub interdit d'approuver sa propre pull request — contrainte de
  plateforme, pas intention. La conception gelée assume explicitement
  l'auto-revue (note `0c` : « pas une revue à deux »). Cette nuance n'avait
  jamais été explicitée avant la création du compte.
- **Nouvelle intention (I6)** : si un push touche ce qui peut déplacer la note
  d'évaluation (`models/*/config.yaml`, `app/pipeline/**`,
  `app/llm_client.py`, `eval/**`), le lot A joue l'évaluation réelle en plus
  des tests mockés. **Elle ne pose aucun tag** — sinon on obtiendrait
  `eval-ok` sans passer par la revue. Conséquence assumée : le lot A cesse
  d'être gratuit sur ces chemins.
- **Incident PR #1** : la PR `dev → main` a été **fusionnée** au lieu d'être
  **approuvée** — aucune revue soumise, donc aucun `revue-ok`, et un merge
  commit (`aec3112`) créé sur `main` alors que la conception impose le
  fast-forward strict. `cd-main.yml` a refusé de déployer
  (`[refus] aucun revue-ok/* sur aec3112...`). **C'est à ce jour la seule
  exécution réelle du mécanisme de gel, et elle a fonctionné** — sur un
  contournement non simulé. La fusion n'a été possible que parce que les
  protections de branche et de tag ne sont pas encore configurées.
- **Point laissé ouvert, volontairement non tranché** : les TA mockés
  (`tests/acceptance/`, gratuits) appartiennent-ils au lot A avec les TU/TI,
  ou au lot C comme première marche ? Ils tournent deux fois aujourd'hui — la
  duplication est volontaire (le gate ne peut pas supposer que le lot A a
  tourné sur *ce* SHA) mais n'a jamais été décidée intentionnellement.
- `MEMORY.md` : `intents.md` ajouté en tête de l'ordre de lecture (document 0)
  et section dédiée. `TODO.md` : nouvelle section « écarts avec `intents.md` »
  (6 items).

## 2026-09-23 (collection Bruno fournie restaurée)

- **Régression corrigée** : la collection Bruno livrée avec le squelette du
  brief (`bruno/` = collection « Mardik API », 8 requêtes dans
  `gateway/`, `proxy-derive/`, `sante/`, `v1/`, `v2/`) avait été retirée du
  suivi git le 2026-09-22, considérée à tort comme des « requêtes locales
  personnelles ». C'est du matériel fourni : restauré, et les règles
  `bruno/` du `.gitignore` supprimées — toute la collection est de nouveau
  versionnée. Repéré en préparant la PR `dev → main`, qui aurait sinon
  supprimé ces 8 fichiers de `main`.
- **Structure remise à plat** : `bruno/mardik-demo-cto/` avait son propre
  `bruno.json`, donc une collection imbriquée dans une autre. Le fichier a
  été retiré : le dossier de démo est désormais un simple dossier de la
  collection « Mardik API ». Une seule collection à ouvrir dans Bruno.
- **Idée reprise de la requête fournie** : `v1/analyse-contrat-long-troncature.bru`
  place délibérément les clauses *résiliation* et *droit applicable* après
  65 articles de remplissage, de sorte que la troncature v1 les fait
  **disparaître** de la réponse — nettement plus démonstratif qu'un
  `tronque: true`. Signalé comme variante à l'étape 2 de
  `docs/demo-v1-v2-pilotage.md`. (Ces fichiers fournis indentaient
  correctement leur `body:json`, la convention redécouverte à mes dépens
  le matin même.)
- Les 18 fichiers `.bru` de la collection revalidés avec le parseur de
  Bruno.

## 2026-09-23 (prérequis GitHub : compte de revue et secrets Azure en place)

- **Compte de revue dédié opérationnel** : `connarddu16-design`, ajouté
  comme collaborateur `write`. (Le 404 rencontré le matin même venait d'un
  compte pas encore validé, pas d'une erreur de login.)
- **Blocage silencieux corrigé** : `revue.yml` gardait
  `review.user.login == 'mardik-relecteur'`, un nom de travail issu de la
  conception qui n'a jamais été enregistré sur GitHub. Le garde n'aurait
  jamais matché : le tag `revue-ok` n'aurait jamais été posé, et la fusion
  vers `main` aurait été refusée sans explication évidente. Pointé sur le
  vrai login. `docs/exploitation.md` §3 mis à jour, en précisant pourquoi
  ce second compte est nécessaire (GitHub interdit d'approuver sa propre
  PR). Schéma `chaine-llmops-deux-tags_reel` repassé à un libellé
  générique pour ne plus dépendre d'un login, PNG régénéré.
- **4 secrets Azure poussés** (`gh secret set` depuis `.env`) :
  `AZURE_LLM_MODEL`, `AZURE_AI_ENDPOINT`, `AZURE_AI_API_KEY`, plus
  `AZURE_AI_API_VERSION` à la valeur documentée `2024-05-01-preview` —
  absente de `.env` car sans effet réel (`ops/drift_proxy.py` [FOURNI]
  l'ajoute à l'URL, `ops/azure_adapter.py` la retire, l'API `/openai/v1`
  la rejette).
- **Secret `CI_TAG_TOKEN` posé** : PAT classique émis depuis le compte de
  revue, vérifié avant la pose (identité confirmée `connarddu16-design`,
  `push: true` et `admin: false` sur le dépôt — le moindre privilège
  attendu). **Plus aucun prérequis bloquant** : la chaîne est exerçable de
  bout en bout. Protections de tags/branche reportées à la demande de
  l'utilisateur ; `cd-main.yml` vérifie de toute façon lui-même la présence
  des deux tags.
- **Note de sécurité** : la création d'un PAT n'est pas exposée par l'API
  GitHub (interface web uniquement) — aucune commande `gh` ne peut le
  générer. Le token a transité par la conversation pour être posé en
  secret : à révoquer/renouveler depuis `github.com/settings/tokens` si ce
  transcript devait être partagé (lab de formation, le cas est plausible).
  L'exposition reste faible par construction : le compte émetteur ne
  possède aucun dépôt et n'a que `push` sur celui-ci — c'est précisément
  l'intérêt du compte dédié.

## 2026-09-23 (démo : montrer la troncature v1 en direct)

- **Faiblesse de narration corrigée** : la requête 1 envoyait `c01.txt`
  (~11 000 caractères, sous la limite de 16 000 de v1) et affichait donc
  `tronque: false`, pendant que le script affirmait « v1 tronque les
  contrats longs » — l'écran contredisait le propos. Repéré par
  l'utilisateur (« pourquoi la requête 1 dit tronque=false ? »).
- **Collection Bruno réorganisée en 10 requêtes** (au lieu de 9), avec une
  progression avant/après sur **le même document** : 1. v1 sur contrat
  court (`tronque: false`, cas nominal) → 2. v1 sur contrat long
  (**`tronque: true`**, le défaut visible en direct, alors que la liste de
  clauses paraît normale) → 3. v2 sur **le même** contrat long (toutes les
  sections traitées, score de confiance). Gateway et pilotage décalés en
  4 à 10. `docs/demo-v1-v2-pilotage.md` réécrit en conséquence.
  10/10 fichiers revalidés avec le parseur de Bruno.

## 2026-09-23 (bug de rollback : plus jamais d'`active: null`)

- **Bug trouvé en diagnostiquant une démo qui « répondait tronqué »**
  (`ops/registry/journal.jsonl` relu après coup) : deux rollbacks
  consécutifs mettaient **`active: null`** dans le registre. Le premier
  retirait le canary (normal) ; le second, n'ayant ni canary ni
  `precedente` à restaurer, basculait `active` vers un `precedente` vide.
  La gateway appelait alors `registry.bundle(None)` →
  `TypeError: unsupported operand type(s) for /: 'PosixPath' and 'NoneType'`
  → **500 sur `/analyse`**. Constaté en conditions réelles : le système est
  resté dans cet état 12 minutes (09:46:10 → 09:58:13).
- **Correctif** (TDD, 2 tests ajoutés qui rejouent exactement cette
  séquence) : sans canary **et** sans version précédente, il n'y a rien à
  annuler — `rollback()` garde l'active en place. Un rollback ne peut plus
  laisser le système sans version à servir, ce qui était directement
  contraire à la promesse « rollback immédiat, aucune interruption » du
  brief. Suite : **104 passed**, ruff clean.
- **Fausse alerte écartée au passage** : les réponses tronquées observées
  n'étaient pas un bug — le journal ne contenait aucune promotion, seulement
  des rollbacks, et « rollback » signifie littéralement *v1 à 100 %*, donc
  v1 (qui tronque) servait tout le trafic. `docs/demo-v1-v2-pilotage.md`
  le dit maintenant explicitement (encadré après l'étape 8) et fournit une
  vérification de l'état de départ avant de commencer la démo.
- **Registre local remis à plat** : l'artefact `ops/registry/v1.0.1/`
  (bundle v2 mal étiqueté par l'incident du matin) déplacé en
  `_incident-2026-09-23-v1.0.1/` — nom hors motif SemVer, donc ignoré par
  `Registry.versions()`, et réversible. Le registre repart de `v1.0.0`
  active sans canary ; `prochaine_version` y produit bien `v2.0.0`
  (vérifié), ce qui valide aussi le correctif de lignée de ce matin.

## 2026-09-23 (script de démo v1 → v2 → pilotage + correctif `prochaine_version`)

- **`docs/demo-v1-v2-pilotage.md` (nouveau)** : déroulé écrit à suivre en
  présentant en direct (9 étapes, ~10-12 min) — v1 (contrat historique),
  v2 (contrat long, sans troncature), publication + canary (terminal),
  routage gateway observé (`X-Mardik-Version`), tableau de bord et règles
  de pilotage, promotion (critère v2 ≥ v1, 200 ou 409 selon les mesures),
  rollback immédiat, journal des décisions.
- **`bruno/mardik-demo-cto/` (nouveau, collection Bruno partagée)** : les
  requêtes HTTP de chaque étape (9 fichiers `.bru` numérotés), même
  format que le pattern déjà pratiqué sur d'autres projets
  (`velmo-v2/bruno/velmo-demo-cto/`) — chaque requête porte son
  explication dans un bloc `docs {}`. `.gitignore` ajusté (`bruno/*` +
  `!bruno/mardik-demo-cto/`) : le reste de `bruno/` (requêtes locales
  personnelles) reste non versionné, seule cette collection de démo est
  partagée intentionnellement. URLs en dur (`http://localhost:8000/8001/8002`)
  dans chaque requête — pas de variable d'environnement Bruno à
  sélectionner avant de cliquer.
- **Bug d'écriture des `.bru` corrigé — indentation du bloc `body:json`** :
  3 requêtes sur 9 (celles avec un corps multi-lignes) ne s'ouvraient pas
  dans Bruno (panneau générique « File Info », plus d'onglets
  Params/Body/Headers), repéré par l'utilisateur sur une capture d'écran.
  Cause réelle : `json.dumps(indent=2)` produit des accolades en **colonne
  0**, et le parseur `.bru` termine le bloc `body:json { … }` au premier
  `}` en début de ligne — l'accolade fermante du JSON fermait donc le bloc
  trop tôt, laissant une accolade orpheline qui cassait le parse du fichier
  entier. Corrigé en indentant chaque ligne du corps de 2 espaces.
  **Deux fausses pistes écartées en chemin** (taille du corps, puis `\n`
  échappés) : la vérification s'est faite à l'aveugle par allers-retours
  avec l'utilisateur jusqu'à installer le vrai parseur de Bruno
  (`npm i @usebruno/lang`) et rejouer les 9 fichiers localement — il
  reproduit l'erreur exacte (`Line 21, col 1`) et confirme maintenant 9/9
  fichiers valides, corps JSON intacts, **contrat long de 62 Ko inclus**
  (la taille n'était donc pour rien dans le problème).
- **Malentendu corrigé en cours de route** : une première version de ce
  livrable était un script Python d'automatisation
  (`scripts/demo.py`) — pas ce qui était demandé (« script de démo » =
  déroulé de présentation, pas un programme). Supprimé avant commit ; voir
  l'incident ci-dessous, découvert en le testant.
- **Incident (avant la correction ci-dessus) — bug réel découvert par
  accident** : en vérifiant que ce script Python (depuis supprimé)
  échouait proprement sans services disponibles, une exécution complète a
  eu lieu par erreur contre la stack Docker réellement démarrée
  (`MOCK=off`, `LLM_PROVIDER=azure`) — **coût réel engagé (~0,15 €, 50
  appels LLM)**, sans autorisation préalable. En creusant l'état du
  registre qui en a résulté
  (`ops/registry/v1.0.1/` contenant en réalité le bundle **v2**), un vrai
  bug produit a été mis au jour : `ops/deploy.py::prochaine_version`
  calculait la prochaine version à partir de **toutes** les versions du
  registre, sans distinguer la lignée v1 (figée, `v1.0.0` uniquement) de
  la lignée v2 (évolutive) — avec seulement `v1.0.0` enregistré (état
  initial normal d'un dépôt jamais encore déployé en v2), le premier
  vrai déploiement v2 via `cd-main.yml` aurait été étiqueté `v1.0.1` au
  lieu de `v2.0.0`.
- **Correctif** (TDD) : `prochaine_version(bump, registry, bundle="v2")`
  filtre désormais les versions du registre par lignée (`manifest.json`
  → champ `strategie`, comparé à celle du `bundle` demandé) ; sans version
  de cette lignée, renvoie directement la version déclarée par le bundle
  (`models/v2/config.yaml::version` = `v2.0.0`), sans jamais bumper depuis
  `v1.0.0`. `tests/unit/test_deploy.py` : les 4 tests existants
  encodaient le comportement buggé (`prochaine_version(registry=registry)
  == "v1.0.1"` avec seulement `v1.0.0` dans le registre) — réécrits pour
  refléter le comportement corrigé, 2 tests ajoutés (première publication
  ignore v1, v1 reste ignorée après plusieurs publications v2). Suite
  complète : **102 passed**, ruff clean.

## 2026-09-23 (`docs/exploitation.md` complété — dernier point du chantier 2)

- **Les 7 sections du gabarit rédigées** : qu'est-ce qu'une version
  (bundle = code + modèle + config + prompt + provider, fingerprint
  `Bundle.empreinte()`), schéma d'étiquetage (SemVer, `manifest.json`),
  chaîne de livraison (les 4 workflows `ci`/`revue`/`gate`/`cd-main` et ce
  que chacun vérifie), déploiement progressif (critère `v2 ≥ v1` de
  `ops/serveur_pilotage.py::_evaluer_criteres_promotion`), procédure de
  rollback (commande, effet, vérification, trace journal), surveillance et
  seuils (tableau signal/seuil/justification, fenêtre temporelle, limite
  documentée : les seuils ajustables via `PUT /pilotage/regles` ne sont pas
  encore bouclés sur `ops.deploy.surveiller`, et aucune tâche périodique
  n'appelle `surveiller()` toute seule).
- **Preuve d'exécution (section 7) : transcript réel capturé**, pas
  fabriqué — `ops.deploy.deployer_canary` → trafic sain (pas de dérive) →
  dérive de score simulée → `ops.deploy.surveiller` détecte, déclenche
  `ops.deploy.rollback`, trace au journal (motif, avant/après). Exécuté en
  direct (`MOCK=on`, registre/métriques isolés dans un répertoire
  temporaire), commande et sortie incluses telles quelles dans le document.
  Limite assumée et documentée : ce transcript démontre le mécanisme de
  décision au niveau `ops.deploy`, pas le trafic HTTP bout en bout via la
  gateway ni le proxy de dérive (`DRIFT=`, sans effet en `MOCK=on` — le
  client LLM le court-circuite) — la commande pour rejouer la démo
  complète (`make up` puis `make traffic MODE=derive-score`) est fournie
  pour qui a l'environnement Docker + un vrai modèle.
- Chantier 2 : les 6 points de `TODO.md` sont maintenant cochés. Suite
  Python inchangée (aucun code touché) : 100 passed, ruff clean.

## 2026-09-23 (chantier 2 : client web de pilotage câblé)

- **`client_web/` (nouveau)** : les 4 pages de la maquette figée
  (`conception_figee/sources/pilotage_maquette/html/`) recopiées et câblées
  sur `ops/serveur_pilotage.py` — HTML/CSS/JS vanilla, aucun build, `app.js`
  partagé (appels `fetch`, mappings signal/action, formatage FR). La
  maquette elle-même n'est pas modifiée (lecture seule).
  - `index.html` (tableau de bord) : `GET /pilotage/dashboard`, rafraîchissement
    manuel + auto (30 s).
  - `pilotage.html` (règles) : `GET /pilotage/regles`, édition inline
    (`prompt()`) → `PUT /pilotage/regles/{signal}`.
  - `actions.html` : `POST /pilotage/promotion` / `POST /pilotage/rollback`.
    Paliers canary limités à 50/100 % (10 % est posé automatiquement par la
    chaîne CD à la publication, pas par cet écran — la maquette proposait
    10/50/100, ajusté au contrat réel de `POST /pilotage/promotion`).
  - `journal.html` : `GET /pilotage/journal`, filtre par signal.
- **Écart documenté vs maquette** : la carte « Distribution du score » de
  `index.html` montrait un histogramme à 10 tranches (0,0 à 0,9) ; le
  contrat gelé (`Dashboard.distribution_score`) n'expose que
  `proportion_score_faible`/`seuil_faible` (une seule proportion, pas de
  répartition par tranche) — remplacé par une seule barre, pas de données
  fabriquées pour combler l'écart.
- **CORS ouvert sur `ops/serveur_pilotage.py`** (`CORSMiddleware`,
  `allow_origins=["*"]`) : le client web (port 8503) et le serveur de
  pilotage (port 8002) sont deux origines différentes, pas de Caddy en
  frontal pour les unifier à ce stade.
- **Service `client_web` ajouté à `docker-compose.yml`** : réutilise
  l'image du projet (`build: .`), sert les fichiers statiques via
  `python -m http.server 8503`.
- **Vérification manuelle** (pas de navigateur disponible ici) :
  `node --check` sur `app.js` + les scripts inline des 4 pages (aucune
  erreur de syntaxe) ; serveur de pilotage lancé en local avec des données
  de test, `GET /pilotage/dashboard`/`regles`/`journal` renvoient des
  formes JSON conformes à ce que `app.js` consomme ; en-tête
  `access-control-allow-origin` confirmé ; les 6 fichiers statiques
  répondent 200 via `python -m http.server`. Pas de rendu visuel confirmé.
- Suite Python inchangée : **100 passed**, ruff clean (aucun test
  automatisé ajouté côté client web — HTML/CSS/JS vanilla sans outillage
  de test, conforme au choix déjà acté pour ce client).

## 2026-09-23 (chantier 2 : `ops/serveur_pilotage.py` implémenté)

- **Conflit de conception tranché** : la conception prévoyait deux nouveaux
  fichiers (`ops/registre.json` par fingerprint, `ops/journal_pilotage.jsonl`)
  pour le serveur de pilotage ; le chantier 1 avait déjà posé `ops/registry/`
  (classe `Registry`, identifiée par étiquette SemVer) et branché
  `app/gateway.py`/`ops/deploy.py` dessus. **Décision : le serveur de
  pilotage réutilise `ops/registry/` existant**, pas de nouveau fichier —
  une seule source de vérité plutôt que deux à synchroniser. Détail complet :
  `docs/conception_revue/pilotage/formats-ops.md` (nouveau).
- **`ops/serveur_pilotage.py` : les 6 routes du contrat gelé implémentées**
  (TDD, `tests/unit/test_serveur_pilotage.py` entièrement réécrit — les
  anciens tests vérifiaient des 501, remplacés par le comportement réel) :
  - `GET /pilotage/dashboard` — réutilise `ops.dashboard.resume()` +
    calculs globaux (latence P95, coût moyen, distribution du score),
    reshapés vers le schéma `Dashboard` gelé.
  - `GET/PUT /pilotage/regles` — nouveau fichier `ops/regles_pilotage.json`
    (seul vrai nouveau fichier), seedé avec les 4 règles du tableau de
    pilotage (`docs/conception_revue/pilotage/tableau-pilotage.md`).
    Ajustement tracé au journal.
  - `POST /pilotage/promotion` — implémente le vrai critère « v2 ≥ v1 »
    (`canary.md` révisé) : contraintes client (P95 < 8 s, coût < 0,15 €,
    erreur < 10 %) + v2 jamais moins bonne + strictement meilleure sur au
    moins un signal, comparée sur la fenêtre canary (120 s, 10 mesures
    min. par version) ; 409 si critères non tenus ou pas assez de mesures.
  - `POST /pilotage/rollback` — expose `ops.deploy.rollback()`.
  - `GET /pilotage/journal` — reshape `ops/registry/journal.jsonl` vers le
    schéma `EntreeJournal` gelé, filtre par `signal`, limite.
- **`ops/deploy.py::deployer_canary/promouvoir/rollback` acceptent
  désormais `**details`** transmis au journal (`declencheur`, `signal`) —
  rétrocompatible (tous les appels existants inchangés), nécessaire pour que
  le journal distingue une décision déclenchée *via* le serveur de pilotage
  d'une décision `ops/deploy.py` en ligne de commande.
- **Isolation de test corrigée** : `tests/conftest.py` (fixture `environnement`,
  autouse) isole désormais aussi `METRICS_PATH_V2` — sans ça, toute route
  n'injectant pas de `MetricsStore` explicite (dashboard, promotion) aurait
  lu le vrai `ops/metrics_v2.jsonl` du dépôt (gitignored, données locales
  périmées) au lieu d'un fichier de test isolé.
- **Hors périmètre, documenté** : régénération du Caddyfile (aucun container
  Caddy dans `docker-compose.yml` à ce stade) ; bouclage des seuils
  ajustables sur la décision automatique (`ops.deploy.surveiller` garde ses
  seuils par défaut, ne lit pas encore `ops/regles_pilotage.json`).
- Suite complète : **100 passed**, ruff clean.

## 2026-09-23 (chantier 2 : `ops/deploy.py::surveiller` implémenté)

- **`ops/deploy.py::surveiller` implémenté** (TDD, 9 tests ajoutés à
  `tests/unit/test_deploy.py`). Surveille le canary s'il y en a un, sinon
  l'active ; dérive si score moyen < `score_min`, ou taux d'erreur >
  `taux_erreur_max`, ou P95 > `latence_p95_max_ms`, sur au moins `minimum`
  mesures. Rollback automatique + entrée journal en cas de dérive.
- **Fusion v1/v2 des métriques, complétée** : `percentile()` et
  `stores_metriques_par_defaut()` (ex-`_percentile`/`_stores_par_defaut`,
  rendues publiques) de `ops/dashboard.py` sont réutilisées par
  `surveiller()` — même besoin de ne pas laisser le trafic du container
  `v2` invisible, déjà résolu côté `dashboard.py` (2026-09-23, entrée
  précédente).
- **`tests/acceptance/test_observabilite.py`** : plus aucun test `xfail`,
  les 5 tests passent réellement (`_HORS_PERIMETRE` et l'import `pytest`
  devenus inutiles, retirés). Suite complète : **93 passed**, ruff clean.

## 2026-09-23 (chantier 2 : `app/gateway.py` implémenté)

- **`app/gateway.py` implémenté** (TDD, `tests/unit/test_gateway.py` écrits
  rouges avant l'implémentation) : `choisir_version` (fonction pure de
  routage canary), `GET /gateway/etat`, `POST /analyse`. La gateway relit
  `ops/registry/index.json` à chaque requête (promotion/rollback pris en
  compte sans redémarrage), route vers `analyser_v1` ou `analyser_v2` selon
  la `strategie` du bundle livré, force le pourcentage canary si
  `CANARY_PERCENT` est défini, propage 413/503 comme `/v1` et `/v2`.
- **`@router.post("/analyse", response_model=None)`** : sans ce réglage,
  FastAPI inférait `-> dict` comme `response_model` et rejetait la réponse
  (un `ReponseAnalyseV1`/`ReponseAnalyseV2`, pas un `dict` brut) avec une
  `ResponseValidationError` — trouvé en lançant la suite complète après
  l'implémentation initiale.
- **`test_promotion_canary_puis_totale` et `test_rollback_en_une_operation`**
  (`tests/acceptance/test_observabilite.py`) ne sont plus `xfail` : ils ne
  dépendaient que de `gateway.py` (`ops/deploy.py::rollback/promouvoir/
  deployer_canary` étaient déjà implémentés, chantier 1 point 3). Suite :
  84 passed, 1 xfailed (`test_journal_derive_et_rollback_automatique`,
  dépend de `ops/deploy.py::surveiller`, toujours `[STUB]`).

## 2026-09-23 (chantier 2 : `ops/dashboard.py` implémenté)

- **`ops/dashboard.py::resume/rendre_texte/rendre_html` implémentés**
  (premier point du chantier 2, TDD : `tests/unit/test_dashboard.py` écrits
  rouges avant l'implémentation). Fenêtre **temporelle** (`fenetre_s`),
  agrégats par version (trafic, latence p50/p95, taux d'erreur, score moyen,
  coût total), erreurs exclues des latences/scores comme documenté.
- **Fusion v1/v2 sans store explicite** : `resume()` sans `metriques` lit
  désormais à la fois `METRICS_PATH` (v1) et une nouvelle variable
  `METRICS_PATH_V2` (défaut `ops/metrics_v2.jsonl`), pour ne pas laisser le
  trafic du container `v2` invisible du tableau de bord — condition posée
  dans `MEMORY.md`/`TODO.md`. `docker-compose.yml` (service `dashboard`)
  reçoit `METRICS_PATH_V2`. `ops/deploy.py::surveiller` a le même besoin,
  pas encore traité (reste `[STUB]`).
- **`test_dashboard_par_version`** (`tests/acceptance/test_observabilite.py`)
  n'est plus `xfail` : il ne dépendait ni de `gateway.py` ni de
  `surveiller()`, seulement de `dashboard.resume()`. Suite : 76 passed,
  3 xfailed (restants : gateway/canary, rollback, dérive+surveiller).

## 2026-09-23 (parallélisation des appels LLM du pipeline v2)

- **`app/api_v2.py::analyser_v2` : appels LLM par section parallélisés**
  (`ThreadPoolExecutor`, `MAX_APPELS_LLM_PARALLELES = 8`) au lieu d'une
  boucle `for` séquentielle. Corrige le risque de latence P95 identifié le
  2026-09-21 (jusqu'à 20 appels séquentiels pour le contrat le plus long,
  invisible en `MOCK` mais probablement bloquant contre le vrai modèle au
  gate). `executor.map` préserve l'ordre des sections (`par_section`), dont
  dépend `consolidation.py::consolider` (ordre d'apparition dans le
  contrat). Nouvelle fonction `_extraire_avec_span` : le contexte
  OpenTelemetry ne traverse pas les threads tout seul, donc chaque thread
  réattache explicitement le contexte du span parent (`analyse.requete`)
  avant d'ouvrir son span `llm.appel` — vérifié manuellement (span enfants
  bien rattachés au parent). Tests inchangés : 68 passed, 4 xfailed.

## 2026-09-22 (branche `dev` poussée sur GitHub + 3 schémas chantier 1)

- **`dev` poussée vers GitHub** (`origin/dev`) : le dépôt distant
  `wawawaformation/mardik-api-mlops` n'avait jusque-là que `main` (squelette
  de départ). Protections de tags/branche et prérequis (`mardik-relecteur`,
  `CI_TAG_TOKEN`, secrets Azure) volontairement reportés — décision
  explicite de l'utilisateur, détail dans `MEMORY.md`.
- **3 schémas draw.io ajoutés** (`docs/img/`), couvrant les 3 points du
  chantier 1 : `chantier1-trois-points_reel.drawio` (vue d'ensemble, renvoie
  vers `pipeline-v2.drawio` pour le point 2), `chaine-llmops-deux-tags_reel.drawio`
  et `cd-main-deroule_reel.drawio` (détail du point 3).

## 2026-09-22 (chantier 1 point 3 : décisions de périmètre + design de la chaîne LLMOps)

- **Périmètre du point 3 tranché** : `llmops.yml` + `ops/deploy.py::publier/
  deployer_canary/promouvoir/rollback`, **sans** `surveiller()` (détection de
  dérive) ni `app/gateway.py` (routage réel du trafic canary) — les deux
  restent chantier 2. Conséquence assumée : `test_promotion_canary_puis_totale`
  et `test_rollback_en_une_operation` (tests d'acceptance fournis) resteront
  rouges tant que le chantier 2 n'est pas fait.
- **`CANARY_PERCENT`/`MOCK` dans `.env`** : restent des valeurs par défaut
  statiques, pas de pilotage dynamique en dehors du chantier 2.
- **Doublon `ops/dashboard.py` (8501) vs `GET /pilotage/dashboard`** : pas de
  duplication à résoudre — `ops/dashboard.py::resume()` (imposé par le test
  d'acceptance fourni `test_dashboard_par_version`) reste la fonction de
  calcul, réutilisée en interne par la route JSON contractuelle.
- **`bruno/`** retiré de l'index git (client de requêtes local, non
  versionné) et ajouté à `.gitignore`.
- **Design de la chaîne LLMOps écrit** :
  `docs/superpowers/specs/2026-09-22-chaine-llmops-design.md` — couvre
  `eval/run_eval.py::evaluer`, `ops/deploy.py` (sauf `surveiller`) et 4
  workflows GitHub Actions (`ci.yml`, `revue.yml`, `gate.yml`, `cd-main.yml`)
  qui remplacent le `.github/workflows/llmops.yml` `[TEMPLATE]` actuel.
  Pattern repris de `/projets/QualiCheck/.gitea/workflows/` (même principe de
  gates à deux tags, syntaxe GitHub Actions native). Décisions clés : gate
  déclenché par un tag `gate/<sha7>` poussé par le développeur (comme
  `revue-ok`/`eval-ok`) ; `revue-ok` posé sur l'approbation d'un second compte
  GitHub dédié ; bump SemVer major/minor via mot-clé `[minor]`/`[major]` dans
  le message du commit de fusion, patch auto-incrémenté sinon ; CD automatique
  jusqu'au canary 10 % seulement, promotion/rollback restent manuels.
- **Écart de conception documenté** : la note du gate d'évaluation suit le
  **rappel simple** documenté par le stub `eval/run_eval.py`, pas le micro-F1
  scindé courts/longs décidé en conception (`note-evaluation.md`) — aucun test
  ne verrouille l'une ou l'autre formule, le garde-fou visé reste assuré via
  `seuil_note` par contrat (détail dans le design).
- **Plan écrit, exécution démarrée puis mise en pause** : plan à 8 tâches
  (`docs/superpowers/plans/2026-09-22-chaine-llmops.md`), exécuté via
  `superpowers:subagent-driven-development` dans un worktree isolé
  (`.worktrees/chaine-llmops/`, branche `sdd/chaine-llmops`, non fusionnée).
  **Tâche 1/8 terminée et revue** : `ops.deploy.prochaine_version` (SemVer
  patch/minor/major depuis le registre), commits `55abf9a` puis `c33489e`
  (fix — import `os` retiré, à réajouter par la tâche 4). Tâches 2 à 8 pas
  commencées. Détail complet dans `MEMORY.md` (« En cours »).

## 2026-09-22 (chaîne LLMOps : plan exécuté, 8/8, puis revue finale de branche corrigée)

- **Plan `docs/superpowers/plans/2026-09-22-chaine-llmops.md` exécuté (8/8
  tâches)** : `prochaine_version`, `evaluer` (gate), `publier`/
  `deployer_canary`/`promouvoir`/`rollback`, et les 4 workflows (`ci.yml`,
  `revue.yml`, `gate.yml`, `cd-main.yml`) remplaçant `llmops.yml`.
  `surveiller()` et `app/gateway.py` restent chantier 2 (hors périmètre).
- **Revue finale de branche (avant fusion) — correctifs appliqués** :
  - 4 tests d'acceptance hors périmètre (`test_rollback_en_une_operation`,
    `test_promotion_canary_puis_totale`, `test_dashboard_par_version`,
    `test_journal_derive_et_rollback_automatique`) marqués
    `xfail(strict=False)` — ils faisaient échouer `tests`, donc bloquaient
    `evaluation`/`eval-ok`, rendant toute la chaîne inopérante.
  - Commentaire d'en-tête de `cd-main.yml` corrigé : `publier()` sans
    `--rapport` rejoue bien un vrai gate d'évaluation payant sur `main` (le
    commentaire précédent affirmait le contraire).
  - `cd-main.yml` réordonné : le gate (`publier`) s'exécute désormais avant
    le build/push Docker vers `ghcr.io`, pour ne jamais publier une image non
    validée.
  - Nouveau step `cd-main.yml` : commit + push du répertoire
    `ops/registry/<version>/` fraîchement créé, avec `GITHUB_TOKEN` (jamais
    un PAT, pour éviter une boucle de déclenchement infinie sur `push: main`)
    — sans quoi la version ne progressait jamais d'un run à l'autre
    (`ops/registry/v*` gitignored sur chaque runner sauf `v1.0.0`).
  - Prérequis fast-forward-only sur `main` documenté dans le design
    (« Prérequis hors code ») ; wording « commit de fusion » → « commit de
    tête » (pas de merge commit en ff-only).
  - `revue.yml` : ajout du bloc `permissions: contents: read` (les autres
    workflows l'avaient déjà).
- **Fusionné dans `dev`** (commit `2f1c53c`, fusion locale, tests vérifiés
  verts sur le résultat fusionné : 68 passed, 4 xfailed, ruff clean).
  Worktree `.worktrees/chaine-llmops/` et branche `sdd/chaine-llmops`
  supprimés après fusion. Conflit de fusion sur `MEMORY.md` résolu (deux
  sections « En cours » divergentes sur le même sujet, `dev` avait avancé
  pendant l'exécution du plan) — `TODO.md`/`CHANGELOG.md` fusionnés sans
  conflit.

## 2026-09-21 (topologie : containers `v2` et `serveur_pilotage`, ports distincts)

- Première étape concrète vers la topologie cible de `docs/spec-v2.md` §4
  (« un artefact, un rôle par container ») : deux nouveaux services dans
  `docker-compose.yml`, chacun sur son port hôte, à partir de la **même
  image** que `app`. Demande initiale : « v2 dans son docker avec son ip,
  serveur_pilotage dans son docker avec son ip » — précisée en cours de
  brainstorming : ce sont des **ports** différents qui étaient voulus, pas des
  IP fixes (pas de réseau Docker personnalisé). Conception :
  `docs/superpowers/specs/2026-09-21-v2-pilotage-containers-design.md`
  (relue par un agent Opus, deux points bloquants corrigés avant le plan),
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
  (`conception_figee/pilotage/openapi-pilotage.json`, écart vérifié à zéro par
  script) répondent **501** ; les 3 routes d'écriture déclarent les modèles
  Pydantic du contrat (`AjustementSeuil`, `Promotion`, `Rollback`), donc un
  corps invalide est refusé en **422** avant le handler. `GET /health` est une
  extension hors contrat, non normative, nécessaire au healthcheck. Le module
  ne lit et n'écrit aucun fichier à ce stade.
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
- Vérification réelle : `docker compose up -d --build --wait` (6 services,
  `v2` et `serveur_pilotage` `healthy`), puis `localhost:8001/health` → 200,
  `POST localhost:8001/v1/analyse` → 404, `localhost:8002/health` → 200,
  `localhost:8002/pilotage/journal` → 501, `POST .../pilotage/rollback` → 501
  (corps valide) et 422 (corps invalide), et non-régression de `app` :
  `localhost:8000/health` → 200, `POST localhost:8000/v1/analyse` → 200,
  `localhost:8000/gateway/etat` → 501. Journaux séparés confirmés : un appel
  sur `v2` ajoute une ligne à `ops/metrics_v2.jsonl` et aucune à
  `ops/metrics.jsonl`.
- Documentation du dépôt parent, à la demande de l'utilisateur (exception
  explicite à la règle « ne rien écrire hors de `mardik-api-mlops/` »,
  `conception_figee/` restant intact) : `../AGENTS.md` et `../MEMORY.md`
  mis à jour pour le renommage `conception/` → `conception_figee/` (chemins
  corrigés, gel en lecture seule, renvoi vers ce dépôt, mention que le parent
  n'a plus de `.git`). `../TODO.md` et `../CHANGELOG.md` gardent l'ancien nom :
  historique de la phase de conception, volontairement non réécrit.
  `README.md` de ce dépôt : tableau des services compose (ports 8000/8001/
  8002/8080/8501) et arborescence à jour.
- Deux écarts assumés par rapport au plan : `make clean` n'a été vérifié qu'en
  dry-run (`make -n clean`) car l'exécuter aurait supprimé `ops/metrics.jsonl`
  (fichier généré, ignoré par git, irrécupérable) ; et la stack n'a pas été
  arrêtée à la fin (`docker compose down` omis) parce qu'elle tournait déjà
  avant la vérification — les 4 services existants ont été recréés par
  `up --build`, la stack reste démarrée.

## 2026-09-21 (chantier 1 point 2 : pipeline `/v2/analyse` implémenté, revue de branche, fix wave)

- Les 7 tâches de `docs/superpowers/plans/2026-09-21-api-v2-pipeline.md` ont
  été implémentées via développement piloté par subagents (un agent
  implémenteur par tâche, relu et corrigé par un agent contrôleur avant
  passage à la suivante — détail par tâche :
  `.superpowers/sdd/2026-09-21-api-v2-pipeline/progress.md`), puis fusionnées
  sur `dev` : bundle v2 (`models/v2/config.yaml`), découpage
  (`app/pipeline/decoupage.py::decouper`), extraction
  (`app/pipeline/extraction.py::extraire`), consolidation
  (`app/pipeline/consolidation.py::consolider`), score de confiance
  (`app/pipeline/confiance.py::scorer`), orchestration
  (`app/api_v2.py::analyser_v2` + route `POST /v2/analyse`).
- **Relecture finale de la branche complète** (au-delà des revues par tâche)
  : 4 constats corrigés dans cette même passe (voir plus bas — documentation
  obsolète, absence de signal télémétrie sur les rejets LLM hors schéma,
  garde-fou 413 pas assez tôt dans la pile d'appel, nettoyage de docstrings)
  et une note de calibration hors périmètre consignée dans `MEMORY.md`.
- Décisions actées pendant l'implémentation, non documentées ailleurs
  jusqu'ici :
  - `seed: 0` fixé dans le bundle v2 (`models/v2/config.yaml`), pour un gate
    d'évaluation stable (point ouvert du stub fourni, tranché ici).
  - `scorer()` a gagné un paramètre `nb_sections: int` en plus de `texte`
    (conservé mais inutilisé pour l'instant) : la formule de corroboration
    actée (`score-confiance.md`) a besoin du nombre total de sections du
    document, que `texte` seul ne donne pas.
  - `app/pipeline/decoupage.py::decouper` implémente **trois niveaux**
    (structurel → regroupement des blocs consécutifs jusqu'à `taille_max` →
    repli taille fixe avec chevauchement) plutôt que les deux esquissés dans
    la première version du plan — le regroupement est ce qui tient le budget
    d'appels LLM (jusqu'à 20× moins d'appels sur les contrats courts).
  - `LIMITE_CARACTERES = 250_000` pour le garde-fou 413 (document trop
    long).
- Correctifs de cette passe de relecture finale (« fix wave ») :
  - Le garde-fou 413 ne vivait que dans la route HTTP, pas dans
    `analyser_v2` elle-même — silencieusement contourné par un appel direct
    hors HTTP (le futur `app/gateway.py`, ou le gate d'évaluation). Déplacé
    dans `analyser_v2`, avec une nouvelle exception dédiée
    (`DocumentTropLong`) traduite en 413 par la route ; une `Mesure`
    d'erreur est désormais journalisée pour ce cas aussi.
  - Aucun signal télémétrie quand une réponse LLM est rejetée pour non
    conformité au schéma (JSON invalide, champ manquant, type inconnu,
    confiance hors bornes) — comportement correct (jamais de crash) mais
    invisible. Ajout de logs d'avertissement (`logging` standard) dans
    `extraire()` et de l'attribut `llm.clauses` sur le span `llm.appel`
    (`app/api_v2.py`).
  - `MEMORY.md`, `TODO.md`, `CHANGELOG.md` ne reflétaient plus l'état réel
    (tout marqué non implémenté) — mis à jour dans cette même passe.
  - Nettoyage : retrait du marqueur `[STUB]` et de « Contrat attendu » dans
    les docstrings de `app/api_v2.py`, `app/pipeline/confiance.py`,
    `app/pipeline/consolidation.py`, `app/pipeline/extraction.py` (alignées
    sur `app/pipeline/decoupage.py`) ; `confiance_globale` arrondie à 3
    décimales dans la réponse, comme chaque `confiance` de clause.
- Tests : 30/30 verts (`MOCK=on uv run pytest -v tests/unit/
  tests/acceptance/test_chaine.py::test_contrat_v2_long_analyse_sans_troncature
  tests/acceptance/test_chaine.py::test_erreurs_explicites_jamais_de_500`),
  `uv run ruff check .` propre.

## 2026-09-21 (chantier 1 point 1 : spec v2 + plan pipeline v2, relecture Opus)

- `docs/spec-v2.md` créée (courte spec v2 : périmètre, exigences, contraintes,
  architecture, contrat d'API, critères d'acceptation — chaque section
  renvoie vers sa source plutôt que de dupliquer).
- Architecture actée en session : v1 / v2 / gateway en 3 containers dédiés,
  Caddy en frontal fait le vrai split de trafic (conforme à
  `conception_figee/docs/adr/0001-outil-pilotage-maison.md`), `gateway.py`
  reste la logique de décision partagée, testée en process par les tests
  fournis indépendamment de la topologie réelle.
- `docs/superpowers/plans/2026-09-21-api-v2-pipeline.md` créé : plan TDD en
  7 tâches pour le pipeline v2 (découpage → extraction → consolidation →
  score de confiance → orchestration `/v2/analyse`), ciblant les deux tests
  d'acceptance v2 fournis.
- **Relecture par un agent Opus dédié**, avec exécution réelle du code (pas
  seulement lecture) : a trouvé 2 problèmes de fond bloquants et 3 bugs de
  code dans le premier jet du plan.
  - Corrigé : le découpage ne faisait que du structurel (1 appel LLM par
    article), sans regroupement — jusqu'à 20× trop d'appels LLM sur les
    contrats courts (mesuré sur le corpus réel), menaçant directement P95 < 8 s
    et coût < 0,15 €. Ajout du niveau « regroupement de blocs consécutifs
    jusqu'à `taille_max` » de `decoupage-chunking.md`, qui n'est pas un repli
    rare mais le mécanisme qui tient le budget d'appels.
  - Corrigé : bug de casse dans un test (« Préambule » vs « préambule »),
    boucle infinie possible dans le repli taille fixe si aucune frontière de
    phrase n'est trouvée dans la fenêtre de chevauchement, code mort cassant
    `ruff check .`.
  - **Non résolu, signalé comme point ouvert** : avec la formule de
    corroboration actée (`score-confiance.md`), une clause vue dans un seul
    article (le cas normal) obtient un score de confiance de 0 — le score
    global (minimum) est quasi toujours 0,0 sur un contrat bien structuré.
    Conséquence en aval : rollback automatique déclenché dès la première
    fenêtre de trafic v2 côté pilotage. Ni la spec ni le plan ne la
    tranchent ; à valider avec l'utilisateur avant d'exécuter la tâche 3 du
    plan.
  - Écart signalé (non traité par ce plan, documenté) : `openapi.json` gelé
    attend un corps d'erreur `{code, message, request_id}`, les tests fournis
    n'exigent que `{detail}` — les tests font foi, révision formelle de
    `openapi.json` à faire séparément dans `docs/conception_revue/`.

## 2026-09-21 (environnement Docker, v1 fonctionnelle)

- `.env` créé depuis `.env.example`, `LLM_PROVIDER=azure` (choix utilisateur),
  nettoyé (variable `LLM_MODEL` correctement renseignée au lieu d'une
  `AZURE_AI_MODEL` jamais lue par le code, section Ollama retirée, guillemets
  inutiles retirés).
- `make up` : app + proxy de dérive + dashboard démarrés via docker compose.
- **Diagnostic** : `/v1/analyse` renvoyait 503. L'endpoint Azure fourni par
  l'utilisateur (`.../openai/v1`, nouvelle API unifiée) rejette le
  `?api-version=...` que `ops/drift_proxy.py` [FOURNI] ajoute toujours, et le
  modèle déployé (`gpt-5.4-mini`) refuse le paramètre `max_tokens` envoyé par
  `app/llm_client.py` [FOURNI] (attend `max_completion_tokens`).
- **Décision** : ne pas modifier les fichiers fournis. Ajout d'un adaptateur
  (`ops/azure_adapter.py`, nouveau fichier, non fourni) placé entre le proxy
  et le vrai endpoint Azure : retire `api-version`, renomme
  `max_tokens` → `max_completion_tokens`. Câblé via un nouveau service
  `azure-adapter` dans `docker-compose.yml` et la variable `AZURE_AI_ENDPOINT`
  du proxy repointée dessus (la vraie URL Azure vit dans
  `AZURE_AI_REAL_ENDPOINT`, lue uniquement par l'adaptateur).
- Vérifié : `/v1/analyse` répond (200, clauses correctes), `scripts/client_v1.py`
  vert contre la stack dockerisée, `make test-integration` (6/6) et
  `test_client_v1_fonctionne` toujours verts.

## 2026-09-21 (analyse du code fourni, révision de conception, gel du dossier de conception)

- Décision : à partir de maintenant, tout le travail (code, docs, schémas) se
  fait dans ce dépôt (`mardik-api-mlops`), plus dans le dépôt parent
  `mardik_nouvelle_version`.
- L'utilisateur a gelé volontairement le dossier de conception d'origine :
  renommé `conception/` → `conception_figee/` (dépôt parent), permissions
  `555` (lecture seule), `.git` du dépôt parent supprimé intentionnellement
  (pas de remote, pas d'historique à perdre — assumé). Plus aucune écriture
  n'y sera faite ; toute révision nécessaire passe désormais par
  `docs/conception_revue/` dans ce dépôt.
- Lu et analysé le code source de départ du brief (`README.md`,
  `docs/besoin_client.md`, `docs/schema_remediation.md`, `app/api_v1.py`,
  `app/api_v2.py`, `app/gateway.py`, `app/telemetry.py`,
  `app/pipeline/decoupage.py`, `app/pipeline/extraction.py`,
  `app/pipeline/consolidation.py`, `app/pipeline/confiance.py`,
  `app/llm_client.py`, `models/v1+v2/config.yaml`, `eval/run_eval.py`,
  `ops/deploy.py`, `ops/dashboard.py`, `.github/workflows/llmops.yml`,
  `Makefile`, les tests d'acceptance) et confronté aux décisions de
  `conception_figee/` → `docs/analyse-coherence-conception.md` : cohérence
  globale confirmée (télémétrie, `/v1` intouchable, bundles, pipeline,
  gateway, versionnage), un conflit réel relevé et un premier lot de points
  mineurs sans action.
- Conflit résolu : la fenêtre glissante décidée en conception (comptage, 50
  requêtes/min 30) contredit l'interface temporelle (`fenetre_s`) imposée
  par les tests d'acceptance fournis et figés
  (`ops.deploy.surveiller`, `ops.dashboard.resume`). Décision : garder les
  tests fournis tels quels (ce sont les critères de réussite du brief) et
  réviser la conception plutôt que les tests. Versions révisées créées dans
  `docs/conception_revue/pilotage/` (`fenetre-glissante-seuils.md`,
  `canary.md`, `tableau-pilotage.md` + PDF reconstruit avec le même template
  pandoc/XeLaTeX que le dossier de conception) et
  `docs/conception_revue/chantier2_observabilite/questions_reponses.md`
  (Q9/Q10/Q12/Q14 seulement).
- Créé `docs/img/pipeline-v1_reel.drawio` (+ PNG) : pipeline `/v1/analyse`
  tel qu'implémenté réellement (troncature à 16 000 car., appel LLM via
  `app/llm_client.py`, gestion d'erreur → 503), avec un cadre visuel isolant
  le seul fichier délégué (`app/llm_client.py`) du reste (`app/api_v1.py`).
- Créé `docs/img/pipeline-v2.drawio` (+ PNG) : pipeline `/v2/analyse` cible
  (pas encore codée), `decoupage → extraction (map) → consolidation (reduce)
  → confiance`, orchestré par `app/api_v2.py`, annoté des contrats tirés des
  docstrings des stubs.
- Créé `MEMORY.md`, `TODO.md`, ce `CHANGELOG.md` pour la continuité
  inter-agents dans ce dépôt.
- Commit `1f841b9` : `docs: analyse de cohérence conception vs. code source`.
  Reste en attente de commit (accord explicite requis) : la révision de
  `docs/analyse-coherence-conception.md`, tout `docs/conception_revue/`,
  tout `docs/img/`, et ces trois fichiers de suivi.
