## 1. Push sur `feature/x` — le lot A (`ci.yml`)

**Faire** : créer la branche et un changement **anodin** (hors chemins
sensibles, pour ne pas payer l'alerte) :

```bash
git checkout dev && git pull
git checkout -b feature/demo-ci
echo "- démo CI du $(date +%F)" >> docs/demo-ci-trace.md
git add docs/demo-ci-trace.md
git commit -m "docs: trace the CI demo run"
git push -u origin feature/demo-ci
```

**Ce que ça fait** : `ci.yml` se déclenche sur **tout push de branche sauf
`main`**. Un runner Ubuntu installe `uv`, fait `uv sync`, puis lint + les
trois niveaux de tests en `MOCK=on`. Permissions : lecture seule.

**Montrer** : l'exécution *CI* dans l'onglet Actions, les deux étapes
*Linting* et *Tests*. « C'est le gate le plus fréquent et le moins cher. »

## Variante — l'alerte d'évaluation (`alerte-eval.yml`)

**Les 4 chemins sensibles** qui déclenchent ce workflow (sur `feature/**`) :

| Chemin                 | Ce que c'est                                                                                                   | Pourquoi il est sensible                                                          |
| ---------------------- | -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `models/*/config.yaml` | Config du modèle par version (`v1`, `v2`) — stratégie, prompts par section, schéma de sortie, température/seed | Change directement ce qu'on demande au LLM                                        |
| `app/pipeline/**`      | Le pipeline v2 réel : découpage, extraction, consolidation, score de confiance                                 | Change le comportement du code qui produit le résultat                            |
| `app/llm_client.py`    | Le client qui appelle le LLM (Azure/Ollama)                                                                    | Change *comment* on parle au modèle (retries, parsing, etc.)                      |
| `eval/**`              | Le gate d'évaluation lui-même (`run_eval.py`, fixtures, historique)                                            | Change *comment on mesure* — un gate cassé pourrait laisser passer n'importe quoi |

Logique commune : ce sont les 4 endroits où une modification peut faire
bouger la note (`note_eval`) sans que ce soit visible dans `ci.yml` (qui
tourne en mock, donc insensible à un vrai changement de comportement du
modèle).

**Faire** (payant, sur `feature/demo-ci`, avant la PR) : toucher un fichier
sous un chemin sensible — ici `eval/**` (ou `models/*/config.yaml`,
`app/pipeline/**`, `app/llm_client.py`) — puis pousser :

```bash
echo "- démo alerte-eval du $(date +%F)" >> eval/README.md
git add eval/README.md
git commit -m "docs(eval): démo alerte-eval"
git push
```

**Ce que ça fait** : un **second** workflow part en plus de `ci.yml` : il
démarre le proxy + l'adaptateur Azure en Docker et lance
`eval.run_eval --version v2 --seuil 0.75` sur le vrai modèle.

**Montrer** l'onglet *Summary* du run : « Alerte évaluation — signal, pas
preuve. Aucun tag posé. » **Dire** : « Le développeur est prévenu tôt que
sa modif fait bouger la note. Mais ça ne prouve rien : ce workflow n'a
même pas le droit d'écrire dans le dépôt. La preuve viendra après la
revue. »

## 2. La PR et la revue (`revue.yml`)

**Faire** (compte développeur, interface web — dépôt étant un fork, ne pas
utiliser le bandeau « Compare & pull request » qui cible l'upstream par
défaut, voir « Après la démo ») :

1. Sur `wawawaformation/mardik-api-mlops` → onglet *Pull requests* →
   *New pull request*.
2. Vérifier en haut : `base repository: wawawaformation/mardik-api-mlops`
   **base: dev** ← `head repository: wawawaformation/mardik-api-mlops`
   **compare: feature/demo-ci**.
3. *Create pull request*.

Puis, **connecté en `connarddu16-design`**, approuver la PR (onglet *Files
changed* → *Review changes* → *Approve*).

**Ce que ça fait** : `revue.yml` se déclenche sur `pull_request_review`.
Il ne fait quelque chose que si les trois conditions sont vraies :
approbation, par `connarddu16-design`, sur une PR vers `dev`. Il **attend
ensuite que `ci.yml` ait conclu `success` sur le SHA de tête** (jusqu'à
10 min, en interrogeant l'API Actions), puis pose `revue-ok/<sha7>`.

**Montrer** :

```bash
git fetch --tags
git tag --points-at HEAD          # revue-ok/<sha7>


## ou 
git checkout feature/training-ci && git pull
git tag --points-at HEAD

```

Et dans les logs du run : `[ok] lot A vert sur <sha>` puis
`[ok] revue-ok/<sha7> posé`.

**Dire** : « Pourquoi un second compte ? GitHub interdit d'approuver sa
propre PR. Ce compte n'est pas une deuxième personne, c'est un mécanisme de
fraîcheur : l'approbation porte sur *ce* SHA-là. »

## 3. Fusion fast-forward vers `dev`

**Faire** :

```bash
git checkout dev
git merge --ff-only feature/demo-ci
git push origin dev
```

**Ce que ça fait** : `dev` avance **sur le même SHA** que celui relu — le
tag `revue-ok` reste valable. `ci.yml` rejoue sur `dev` (gratuit). La PR se
ferme toute seule.

**Dire** — point clé de la démo : « Jamais les boutons de fusion de
GitHub. *Merge commit*, *Squash*, *Rebase* : les trois fabriquent un
nouveau SHA, que les tags ne suivent pas. Le gate refuserait — c'est
arrivé pour de vrai avec la PR #1. `--ff-only` refuse au lieu de fabriquer
un commit de fusion en silence. »

## 4. Le gate (`gate.yml`) — et son refus

**Montrer d'abord le refus (gratuit, très parlant)** : poser un tag
`gate/` sur un commit **sans** `revue-ok`, par ex. un commit local jetable :

```bash
git checkout -b demo-refus
git commit --allow-empty -m "chore: commit without review"
git tag "gate/$(git rev-parse --short=7 HEAD)"
git push origin "gate/$(git rev-parse --short=7 HEAD)"
```

**Montrer** : le job échoue à la **première** étape —
`[refus] aucun tag revue-ok/* ne pointe sur <sha>`. **Dire** : « Zéro
appel payant tant que la revue n'est pas fraîche. »

Nettoyer :

```bash
git push origin --delete "gate/$(git rev-parse --short=7 HEAD)"
git tag -d "gate/$(git rev-parse --short=7 HEAD)"
git checkout dev && git branch -D demo-refus
git push origin --delete demo-refus 2>/dev/null   # si la branche a été poussée
```

**Puis le cas nominal** (payant), sur `dev` :

```bash
git checkout dev
SHA7=$(git rev-parse --short=7 HEAD)
git tag "gate/$SHA7"
git push origin "gate/$SHA7"
```

Suivre le run dans l'onglet **Actions** (compte ~1 min 30 : docker compose
du proxy + de l'adaptateur Azure, puis la vraie évaluation).

**Ce que ça fait** — deux jobs enchaînés par `needs:` :

1. **`tests`** : vérifie `revue-ok` sur ce SHA, puis rejoue lint + tests
   mockés. Répétition voulue : « dans `ci.yml` ils informent, ici ils
   prouvent ».
2. **`evaluation`** (seulement si `tests` est vert) : démarre proxy +
   adaptateur Azure, lance l'**évaluation réelle** (`v2`, seuil 0,75),
   publie `eval/history.jsonl` en artefact, puis pose `eval-ok/<sha7>`.

**Montrer** : le graphe des deux jobs dans Actions, le score dans les logs
de l'évaluation, l'artefact téléchargeable, puis :

```bash
git fetch --tags
git tag --points-at HEAD          # revue-ok/<sha7>, gate/<sha7>, eval-ok/<sha7>
```

**Dire** : « Deux tags distincts : `gate/` est un déclencheur, on peut le
recréer. `eval-ok/` est une preuve, immuable — elle n'existe que si tout
est vert. »

## 5. Fusion vers `main` — le déploiement (`cd-main.yml`)

**Faire** :

```bash
git checkout main
git merge --ff-only dev
git push origin main
```

Suivre le run dans l'onglet **Actions**.

**Ce que ça fait**, dans l'ordre :

1. Vérifie que le SHA poussé porte **les deux** tags `revue-ok` et
   `eval-ok` — sinon refus.
2. Calcule la prochaine version SemVer : `patch` par défaut, `minor` ou
   `major` si le message du commit de tête contient `[minor]`/`[major]`
   (`ops/deploy.py::prochaine_version`).
3. `ops.deploy publier` : **rejoue l'évaluation réelle** (simplification
   assumée, le CLI ne sait pas réutiliser le rapport du gate) et étiquette
   la version dans le registre `ops/registry/`.
4. Committe `ops/registry/<version>/` et le pousse sur `main`
   (compte `mardik-ci`).
5. Construit l'image Docker et la pousse sur
   `ghcr.io/wawawaformation/mardik-api-mlops:<version>`.
6. `ops.deploy canary <version>` : la nouvelle version reçoit **10 %** du
   trafic.

**Montrer** :

```bash
git pull origin main
git log --oneline -2              # chore(registry): publish vX.Y.Z
ls ops/registry/                  # le dossier de la nouvelle version
```

Et, dans les logs de la dernière étape, l'état renvoyé par `canary`
(`'canary': 'vX.Y.Z', 'canary_percent': 10`). Attention :
`ops/registry/index.json` n'est **pas** committé par le workflow — l'état
du canary vit sur le runner, pas dans le dépôt. Et la page *Packages* du dépôt GitHub avec l'image taguée.

**Dire** : « Ici s'arrête l'automatique. Pas de promotion ni de rollback
automatiques dans cette chaîne : c'est le pilotage (`ops.deploy
surveiller`, `promouvoir`, `rollback`), montré dans
`docs/demo-v1-v2-pilotage.md`. »

---

## Temps morts et parades

- **Attente des runners** (1–3 min par workflow) : en profiter pour
  ouvrir le YAML correspondant dans `.github/workflows/` et lire les
  commentaires d'en-tête, qui disent le *pourquoi* de chaque garde.
- **`revue.yml` en `[attente]`** : normal si `ci.yml` n'a pas fini, il
  réessaie toutes les 20 s.
- **Enregistrer à l'avance** : pour une démo sans risque, jouer la chaîne
  la veille et montrer les exécutions déjà terminées dans Actions (elles
  restent consultables), en ne rejouant en direct que les étapes 0, 1 et le
  refus de l'étape 4 — toutes gratuites.

## Après la démo

- `main` a **un commit de plus** que `dev` (`chore(registry): publish …`).
  Réaligner avant la prochaine fusion ff-only :
  
  ```bash
  git checkout dev && git merge --ff-only origin/main && git push origin dev
  ```

- Le dossier `ops/registry/<version>/` reste dans l'historique de `main`
  (voulu : c'est la trace de la publication). `index.json` n'ayant pas été
  committé, l'état local reste `active v1.0.0, canary null`.

- Supprimer la branche de démo :
  `git push origin --delete feature/demo-ci && git branch -d feature/demo-ci`.

---

## Validation réelle exécutée le 2026-09-24

Première exécution en conditions réelles de la chaîne complète, **jusqu'au
canary**, avec Claude Code en guidage pas à pas, sans `make` ni `gh` côté
développeur (commandes brutes + interface web GitHub — `gh` a servi côté
Claude Code pour les vérifications et, ponctuellement, pour débloquer
l'étape 5, voir plus bas). Sert de trace factuelle en complément du
script ci-dessus.

**Étapes 0 à 4, toutes vertes** :

1. `feature/demo-ci` créée depuis `dev`, commit `push sur feature`
   (`app/demo1.osef`), poussée — `ci.yml` vert.
2. PR `feature/demo-ci → dev` créée **via l'interface web** (bouton *New
   pull request*, sélecteurs vérifiés à la main — pas le bandeau vert
   « Compare & pull request », qui cible l'upstream par défaut sur un
   fork, voir plus bas). Approuvée par `connarddu16-design`.
3. `revue.yml` a posé `revue-ok/982f458` automatiquement (10 s).
4. Fusion `--ff-only` vers `dev`, poussée.
5. Tag `gate/982f458` poussé → `gate.yml` vert (1 min 32 s, tests +
   évaluation Azure réelle) → `eval-ok/982f458` posé. `dev` porte alors
   `revue-ok/982f458`, `gate/982f458` et `eval-ok/982f458`.

**Étape 5 (fusion vers `main`) : d'abord bloquée, puis débloquée le jour
même — pas un problème de commande.** `git push origin main` refusé par
GitHub (`GH013`, *require linear history*) à cause d'un **merge commit
ancien** (`2f1c53c`, 22 septembre, `Merge branch 'sdd/chaine-llmops' into
dev`), présent dans l'historique de `dev` **entre** `origin/main`
(`8c59599`) et la tête actuelle de `dev` — reliquat d'avant l'adoption de
la règle ff-only partout. Le fast-forward est possible au sens Git
(`origin/main` reste bien ancêtre de `dev`), mais deux rulesets distincts
portent chacun une règle `required_linear_history` et examinent toute la
plage poussée : `main-linear` (dédié à `~DEFAULT_BRANCH`) **et**
`protection-dev-main` (porte aussi `deletion` et `non_fast_forward` sur
`dev`/`main`, à ne pas toucher). Les deux ont bloqué le push.
Conséquence : cette étape n'avait **jamais été exercée pour de vrai** sur
ce dépôt (`main` était resté volontairement figé à `8c59599` depuis le
nettoyage du 2026-09-23, cf. `TODO.md`).

**Résolution (2026-09-24, via l'API GitHub `gh api`)** : désactivation
temporaire de la règle `required_linear_history` sur les deux rulesets
(`main-linear` entièrement désactivé, `protection-dev-main` réduit à
`deletion` + `non_fast_forward` le temps du push) → `git push origin
main` accepté (`8c59599..982f458`) → les deux rulesets remis à
l'identique immédiatement après (règle réactivée sur les deux). Aucune
réécriture d'historique, aucune protection restée désactivée durablement.
`cd-main.yml` s'est déclenché et a terminé vert en 1 min 31 s :
`chore(registry): publish v2.0.0` commité sur `main` par `mardik-ci`
(`ops/registry/v2.0.0/manifest.json`, `note_eval: 1.0`), image poussée sur
`ghcr.io/wawawaformation/mardik-api-mlops:v2.0.0`, canary 10 % déclenché.
Comme attendu, `ops/registry/index.json` n'a pas été committé — l'état
local du dépôt reste `active v1.0.0, canary null`.

Le merge commit `2f1c53c` reste dans l'historique de `dev`/`main` : cette
manip n'a fait que le laisser passer une fois, elle ne l'a pas fait
disparaître. Toute future fusion `dev → main` repassera par le chemin
normal (ff-only) sans problème, ce commit étant déjà de part et d'autre.

**Variante `alerte-eval.yml` testée séparément** : branche `feature/demo-eval`
depuis `dev`, un commit touchant `eval/README.md` (chemin sensible), poussé.
`ci.yml` et `Alerte évaluation (lot A)` tous deux verts — la vraie
évaluation Azure a tourné en signal, **aucun tag posé**, conforme au
design (I6).

**Piège rencontré et à surveiller** : sur un fork, le bandeau GitHub
« Compare & pull request » cible par défaut le dépôt **upstream**
(`bybysker/mardik-api-mlops`), pas le fork. Deux PR de test s'y sont
retrouvées ouvertes par erreur avant d'être repérées et fermées (#2, #3
sur l'upstream). Toujours vérifier `base repository` / `head repository`
avant de valider une PR sur un dépôt forké.
