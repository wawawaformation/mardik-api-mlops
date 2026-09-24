#!/usr/bin/env bash
## NE PAS EXÉCUTER CE FICHIER TEL QUEL.
## Aide-mémoire pour copier-coller pendant la démo — détail et contexte
## complets dans docs/demo-ci.md. Certaines étapes sont manuelles
## (interface web GitHub), d'autres sont payantes (vrai modèle Azure),
## et il faut souvent attendre un run avant de continuer.

## ---------------------------------------------------------------------
## 1. Push sur feature/x — le lot A (ci.yml)
## Se déclenche sur tout push de branche sauf main. Gratuit (MOCK=on).
## ---------------------------------------------------------------------

git checkout dev && git pull
git checkout -b feature/demo-ci
echo "- démo CI du $(date +%F)" >> docs/demo-ci-trace.md
git add docs/demo-ci-trace.md
git commit -m "docs: trace the CI demo run"
git push -u origin feature/demo-ci

## Vérifier dans l'onglet Actions : le run "CI" doit passer au vert.

## ---------------------------------------------------------------------
## Variante — l'alerte d'évaluation (alerte-eval.yml)
## PAYANT. Se déclenche sur feature/** si le push touche un chemin
## sensible : models/*/config.yaml, app/pipeline/**, app/llm_client.py,
## eval/**. Signal seulement, ne pose aucun tag.
## ---------------------------------------------------------------------

echo "- démo alerte-eval du $(date +%F)" >> eval/README.md
git add eval/README.md
git commit -m "docs(eval): démo alerte-eval"
git push

## Vérifier l'onglet Summary du run "Alerte évaluation (lot A)".

## ---------------------------------------------------------------------
## 2. La PR et la revue (revue.yml)
## MANUEL, interface web. Dépôt forké : ne pas cliquer sur le bandeau
## vert "Compare & pull request" (il cible l'upstream par défaut).
##   - wawawaformation/mardik-api-mlops -> Pull requests -> New pull request
##   - vérifier : base repository = wawawaformation/mardik-api-mlops, base: dev
##                head repository = wawawaformation/mardik-api-mlops, compare: feature/demo-ci
##   - Create pull request
##   - connecté en connarddu16-design : Files changed -> Review changes -> Approve
## revue.yml attend que ci.yml soit vert sur ce SHA, puis pose revue-ok/<sha7>.
## ---------------------------------------------------------------------

git fetch --tags
git tag --points-at HEAD          # doit afficher revue-ok/<sha7>

## ---------------------------------------------------------------------
## 3. Fusion fast-forward vers dev
## Jamais les boutons de fusion GitHub (merge commit / squash / rebase) :
## ça fabrique un nouveau SHA que les tags ne suivent pas.
## ---------------------------------------------------------------------

git checkout dev
git merge --ff-only feature/demo-ci
git push origin dev

## ---------------------------------------------------------------------
## 4. Le gate (gate.yml) — démonstration du refus (gratuit)
## Poser un tag gate/ sur un commit SANS revue-ok pour voir le refus.
## ---------------------------------------------------------------------

git checkout -b demo-refus
git commit --allow-empty -m "chore: commit without review"
git tag "gate/$(git rev-parse --short=7 HEAD)"
git push origin "gate/$(git rev-parse --short=7 HEAD)"

## Attendu dans les logs : [refus] aucun tag revue-ok/* ne pointe sur <sha>

## Nettoyer la démo de refus :
git push origin --delete "gate/$(git rev-parse --short=7 HEAD)"
git tag -d "gate/$(git rev-parse --short=7 HEAD)"
git checkout dev && git branch -D demo-refus
git push origin --delete demo-refus 2>/dev/null   # si la branche a été poussée

## ---------------------------------------------------------------------
## 4bis. Le gate — cas nominal. PAYANT (vrai modèle Azure, ~1 min 30).
## Deux jobs enchaînés (needs:) : tests (revue-ok + lint/tests mockés)
## puis evaluation (proxy+adaptateur Azure, seuil 0.75, pose eval-ok).
## ---------------------------------------------------------------------

git checkout dev
SHA7=$(git rev-parse --short=7 HEAD)
git tag "gate/$SHA7"
git push origin "gate/$SHA7"

## Suivre le run dans l'onglet Actions, puis vérifier :
git fetch --tags
git tag --points-at HEAD          # revue-ok/<sha7>, gate/<sha7>, eval-ok/<sha7>

## ---------------------------------------------------------------------
## 5. Fusion vers main — le déploiement (cd-main.yml)
## PAYANT (rejoue l'évaluation réelle). Refuse s'il manque revue-ok OU
## eval-ok sur le SHA poussé. Build + push image ghcr.io + canary 10%.
## ---------------------------------------------------------------------

git checkout main
git merge --ff-only dev
git push origin main

## Suivre le run dans l'onglet Actions, puis vérifier :
git pull origin main
git log --oneline -2              # chore(registry): publish vX.Y.Z
ls ops/registry/                  # le dossier de la nouvelle version

## ops/registry/index.json n'est PAS committé par le workflow : l'état
## du canary vit sur le runner, pas dans le dépôt. Voir aussi l'onglet
## Packages du dépôt GitHub pour l'image taguée.

## ---------------------------------------------------------------------
## Après la démo
## ---------------------------------------------------------------------

## main a un commit de plus que dev (chore(registry): publish ...) :
## réaligner avant la prochaine fusion ff-only.
git checkout dev && git merge --ff-only origin/main && git push origin dev

## Supprimer la branche de démo, des deux côtés :
git push origin --delete feature/demo-ci && git branch -d feature/demo-ci
