# Design — Chaîne LLMOps, alignement sur `intents.md` (2026-09-23)

> Date : 2026-09-23. Statut : **en attente de validation** — un point reste
> ouvert (D4). Fait suite à la mise à plat des intentions consignée dans
> `intents.md` (racine du dépôt) et à sa traduction en écarts de conception
> dans `docs/conception_revue/chantier1_llmops/gel-eval-avant-fusion.md`.
>
> Complète — ne remplace pas —
> `docs/superpowers/specs/2026-09-22-chaine-llmops-design.md` : le mécanisme à
> deux tags, la fraîcheur par comparaison de SHA, le déclenchement manuel du
> gate et le rôle de `cd-main.yml` sont confirmés tels quels. Cette spec ne
> traite que les écarts encore ouverts de `TODO.md`
> (« Chaîne LLMOps — écarts avec `intents.md` (2026-09-23) »).

## Problème adressé

`intents.md` pose deux principes directeurs :

> **1. Informer n'est pas prouver.** Un même test peut *informer* (dire au
> développeur où il en est, sans conséquence, sans trace) ou *prouver*
> (établir un fait qui autorise l'étape suivante — une preuve s'écrit, elle
> est attachée à un objet précis, et elle arrive dans un ordre).
>
> **2. Attraper au plus tôt, au lot le moins cher.** Le lot A coûte des
> secondes, le lot B de l'attention humaine, le lot C de l'argent. « Tout
> problème doit être détecté au lot le moins cher capable de le voir. »

La chaîne visée (`intents.md`, § « La chaîne ») :

| # | Où | Déclencheur | Ce qui se passe | Résultat |
| --- | --- | --- | --- | --- |
| 1 | `feature/x` | push | **Lot A** — lint + TU + TI mockés | vert / rouge |
| 2 | PR `feature/x → dev` | approbation | **Lot B** — revue | `revue-ok/<sha7>` |
| 3 | `dev` | manuel | **Lot C** — gate (mocké + éval réelle) | `eval-ok/<sha7>` |
| 4 | `dev → main` | manuel | fast-forward, rien d'autre | déploiement |

Quatre écarts entre cette chaîne et le code actuel restent à trancher ou à
implémenter. Ils sont indépendants les uns des autres et traités séparément
ci-dessous (D1 à D4).

### Acquis, hors périmètre de cette spec

- **Cible de la revue** (écart 1 de `intents.md`) : le garde de
  `.github/workflows/revue.yml` compare désormais
  `github.event.pull_request.base.ref == 'dev'`. Déjà corrigé dans le fichier
  de travail (non committé au moment d'écrire ces lignes). Rien à décider.
- **Nettoyage de `main`** : `origin/main` est revenu à `8c59599` et est de
  nouveau un ancêtre de `dev` — le merge commit `aec3112` de l'incident du
  2026-09-23 a disparu, la fusion fast-forward `dev → main` est donc à nouveau
  possible. Vérifié : `git merge-base --is-ancestor origin/main dev` répond
  vrai.

---

## D1 — Deux fusions fast-forward : ce que cela implique réellement

**Décision** : les deux fusions (`feature/x → dev` puis `dev → main`) se font
**en ligne de commande, en `--ff-only`, jamais avec le bouton « Merge » de
GitHub**. Les protections de branche sont posées pour *préserver* les SHA, pas
pour *policer* le circuit — c'est le mécanisme des tags qui police.

### Pourquoi la ligne de commande

C'est le point le moins évident de cette spec, et il conditionne tout le
reste. `intents.md` I4 exige que le SHA relu soit exactement celui qui arrive
sur `main` : « un squash ou un merge commit fabrique un nouveau SHA, que les
preuves ne suivent pas ».

Or **GitHub n'offre aucune option de fusion fast-forward dans l'interface de
PR**. Les trois boutons disponibles sont :

| Bouton GitHub | Effet sur le SHA | Verdict |
| --- | --- | --- |
| *Create a merge commit* | crée un commit de fusion (nouveau SHA de tête) | interdit |
| *Squash and merge* | écrase l'historique en un commit neuf | interdit |
| *Rebase and merge* | réécrit chaque commit (nouveaux SHA) | interdit |

Les trois cassent la propriété de fraîcheur. La fusion doit donc se faire
ainsi, depuis un terminal :

```bash
# 1. feature/x -> dev, après l'approbation (donc après revue-ok/<sha7>)
git checkout dev
git merge --ff-only feature/x
git push origin dev          # la PR se ferme toute seule : GitHub voit ses
                             # commits arrivés sur dev

# 2. dev -> main, après le gate (donc après eval-ok/<sha7>)
git checkout main
git merge --ff-only dev
git push origin main         # déclenche cd-main.yml
```

`--ff-only` est la garantie active : si la fusion ne peut pas être un
fast-forward (parce que `dev` a divergé), la commande refuse au lieu de
fabriquer un merge commit silencieusement.

### Protections de branche à poser (prérequis hors code, voir plus bas)

Sur `dev` et sur `main`, via les *rulesets* GitHub :

| Règle | Pourquoi |
| --- | --- |
| Bloquer les force-push | un SHA déjà prouvé ne doit pas pouvoir être réécrit |
| Bloquer la suppression de branche | idem |
| *Require linear history* | interdit les merge commits poussés à la main |

**Règle à ne surtout pas activer : *Require a pull request before merging*.**
Elle interdirait le `git push origin dev` de la fusion fast-forward — c'est-à-dire
exactement le geste que cette conception impose. Rien ne force alors
techniquement à passer par une PR ; c'est assumé : sans PR il n'y a pas
d'approbation, donc pas de `revue-ok`, donc `gate.yml` refuse de démarrer.
**L'interdit est porté par les tags, pas par la plateforme** — c'est la
propriété que `intents.md` I5 cherchait en choisissant le tag (« il vit dans
le dépôt », portable si le projet change de forge).

Noter que *Require linear history* seule ne suffit pas : un squash ou un
rebase produit aussi un historique linéaire. La garantie réelle reste la
comparaison de SHA faite par `gate.yml` et `cd-main.yml` — elle a déjà refusé
un contournement en conditions réelles le 2026-09-23.

### Révision de `docs/exploitation.md`

Vérifié : le document décrit encore la topologie d'origine. Trois passages de
la § 3 « Chaîne de livraison » sont à réviser :

1. la phrase d'introduction « De la fusion sur `dev` vers `main` … » — il y a
   maintenant **deux** fusions, `feature/x → dev` puis `dev → main` ;
2. le point 2 (`revue.yml`) dit « approuve une PR vers `main` » — c'est une PR
   `feature/x → dev` ;
3. rien n'indique que les deux fusions se font en ligne de commande en
   `--ff-only` : c'est le geste opérationnel le plus facile à rater, il doit
   être écrit noir sur blanc avec les commandes.

S'y ajoutent, selon les décisions ci-dessous : le nouveau workflow
`alerte-eval.yml` (D3, la liste « quatre workflows » devient cinq) et le
garde « lot A vert » de `revue.yml` (D2).

*Constat hors périmètre, à ne pas traiter ici* : la § 3 parle encore de
« micro-F1 sur les 12 contrats » alors que la formule retenue le 2026-09-22
est le **rappel** par contrat (voir la spec du 2026-09-22, § « Écart de
conception »). Signalé, pas corrigé.

---

## D2 — `revue-ok` n'est posé que si le lot A est vert sur ce SHA

**Décision** : `revue.yml` interroge l'API GitHub Actions pour le résultat de
`ci.yml` **sur `pull_request.head.sha`**, attend sa fin si elle est encore en
cours (10 min max), et refuse de poser le tag si la conclusion n'est pas
`success`.

### Pourquoi pas un `needs:` ni un `workflow_run`

Étudié, et impossible : `needs:` ne relie que des jobs d'une **même
exécution**, et `revue.yml` est déclenché par un événement
`pull_request_review` — il ne peut pas dépendre d'un job de `ci.yml`, qui
appartient à une exécution distincte déclenchée par un `push`. Le trigger
`workflow_run` ne fonctionne que dans l'autre sens (un workflow qui réagit à
la fin d'un autre), ce qui est inutilisable ici : c'est l'approbation, pas la
CI, qui doit déclencher la pose du tag.

Il ne reste donc que deux mécanismes praticables :

| Mécanisme | Coût | Retenu ? |
| --- | --- | --- |
| Interroger l'API sur le SHA | 1 appel API, 0 s de calcul | **oui** |
| Rejouer le lot A dans `revue.yml` | ~1 min de runner, dupliqué | non |

Le second fonctionnerait, mais il ferait de `revue.yml` un second lot A :
deux fichiers à maintenir en phase, et un workflow qui cesse d'avoir une seule
responsabilité. L'information existe déjà, il suffit de la lire.

### Le garde, concrètement

À insérer dans `revue.yml` **avant** l'étape qui pose le tag :

```yaml
      - name: Vérifier que le lot A est vert sur ce SHA
        env:
          GH_TOKEN: ${{ secrets.CI_TAG_TOKEN }}
          SHA: ${{ github.event.pull_request.head.sha }}
        run: |
          # I3 : le tag de revue n'est posé que si le lot A est vert sur CE
          # SHA. Pas de needs: possible ici (autre exécution, autre
          # événement) — on lit le résultat via l'API.
          for i in $(seq 1 30); do
            ETAT=$(gh api \
              "repos/${{ github.repository }}/actions/workflows/ci.yml/runs?head_sha=$SHA&per_page=1" \
              --jq '.workflow_runs[0] | "\(.status) \(.conclusion)"' || echo "absent")
            case "$ETAT" in
              "completed success") echo "[ok] lot A vert sur $SHA"; exit 0 ;;
              "completed "*)       echo "[refus] lot A en échec sur $SHA ($ETAT)"; exit 1 ;;
              *)                   echo "[attente] lot A : $ETAT ($i/30)"; sleep 20 ;;
            esac
          done
          echo "[refus] le lot A n'a pas conclu en 10 min sur $SHA"
          exit 1
```

Points de conception :

- **On interroge `ci.yml` nommément**, pas l'ensemble des check-runs du SHA.
  `gh pr checks --watch` aurait été plus court, mais il attendrait *tous* les
  checks du commit — y compris l'alerte d'évaluation de D3, qui doit rester
  un signal sans conséquence. Viser `workflows/ci.yml/runs` est explicite :
  seul le lot A conditionne la preuve de revue.
- **`head_sha` est le bon filtre** : les branches `feature/x` vivent dans le
  dépôt, donc l'exécution de `ci.yml` déclenchée par le `push` porte
  exactement le SHA de tête de la PR. (Ce ne serait pas vrai pour une PR
  venant d'un fork.)
- **L'attente bornée** couvre le cas normal : approuver une PR pendant que la
  CI tourne encore. Sans elle, le garde refuserait un code parfaitement sain
  pour une question de quelques secondes.
- **En cas de refus, il n'y a rien à réparer côté chaîne** : le développeur
  corrige, pousse, la CI repasse — et le nouveau SHA devra de toute façon être
  réapprouvé (I4).
- Permission nécessaire : lecture des exécutions de workflow. `CI_TAG_TOKEN`
  (déjà en place, PAT) la porte ; avec le `GITHUB_TOKEN` par défaut il
  faudrait ajouter `permissions: actions: read`.

`gate.yml` continue de rejouer les tests mockés : ce n'est pas une
duplication à supprimer, c'est la différence entre informer et prouver (voir
D4).

---

## D3 — Alerte d'évaluation conditionnelle dans le lot A

**Décision** : un **nouveau workflow** `.github/workflows/alerte-eval.yml`,
déclenché par un push sur `feature/**` touchant l'un des chemins capables de
déplacer la note, joue l'évaluation réelle et n'écrit **aucun tag**. Le
résultat est publié dans le résumé de job GitHub (`$GITHUB_STEP_SUMMARY`).

### Pourquoi un fichier séparé plutôt qu'un job dans `ci.yml`

Les filtres `paths:` de GitHub Actions s'appliquent **au niveau du workflow**
(`on.push.paths`), pas au niveau d'un job. Mettre l'évaluation dans `ci.yml`
obligerait donc soit à filtrer le workflow entier (le lint et les TU ne
tourneraient plus que sur ces chemins : inacceptable), soit à ajouter une
dépendance à une action tierce type `dorny/paths-filter` pour conditionner le
job. Les workflows actuels n'utilisent que `actions/checkout`,
`astral-sh/setup-uv` et `actions/upload-artifact` — pas de filtre tiers, et
`intents.md` parle de « condition exprimée dans le YAML, sur les chemins
modifiés ». Un fichier séparé exprime cela nativement et garde `ci.yml`
gratuit et lisible. Il prolonge aussi la structure décidée le 2026-09-22 :
un fichier par déclencheur et par responsabilité.

### Le workflow

```yaml
name: Alerte évaluation (lot A)

# I6 — signal, pas preuve. Un push sur une branche de travail qui touche un
# chemin capable de déplacer la note d'évaluation joue l'évaluation réelle
# (payante) et l'affiche. Aucun tag n'est posé : la seule évaluation qui
# fait foi reste celle du lot C, après la revue (gate.yml). Si celle-ci
# posait eval-ok, on obtiendrait la preuve sans passer par la revue et
# l'ordre revue -> gate s'effondrerait (intents.md, I2 et I6).

on:
  push:
    branches:
      - "feature/**"
    paths:
      - "models/*/config.yaml"
      - "app/pipeline/**"
      - "app/llm_client.py"
      - "eval/**"

permissions:
  contents: read

jobs:
  alerte-eval:
    runs-on: ubuntu-latest
    steps:
      # … checkout, .env Azure, docker compose up proxy azure-adapter,
      # attente du proxy, setup-uv, uv sync : identique à gate.yml,
      # job `evaluation` (sans le token CI_TAG_TOKEN — ce workflow
      # n'écrit rien dans le dépôt).

      - name: Évaluation réelle (signal, aucun tag)
        id: eval
        shell: bash            # -eo pipefail : sans quoi le `tee` masque le
                               # code de retour de run_eval
        env:
          LLM_PROVIDER: azure
          LLM_PROXY_URL: http://localhost:8080
          MOCK: "off"
        run: uv run python -m eval.run_eval --version v2 --seuil 0.75 | tee /tmp/eval.txt

      - name: Résumé lisible dans l'onglet Summary
        if: always()
        run: |
          {
            echo "## Alerte évaluation — signal, pas preuve"
            echo
            echo "Push touchant un chemin sensible à la note. **Aucun tag posé.**"
            echo "La preuve d'évaluation reste celle du lot C (\`gate.yml\`)."
            echo
            echo '```'
            cat /tmp/eval.txt
            echo '```'
          } >> "$GITHUB_STEP_SUMMARY"
```

Points de conception :

- **Où s'affiche le résultat** : le log du job (brut) *et* le résumé de job
  (`$GITHUB_STEP_SUMMARY`), qui apparaît en haut de la page de l'exécution
  sans avoir à déplier des étapes. `eval/run_eval.py::afficher` imprime déjà
  la note globale, le P95, le coût moyen et les motifs d'échec : il n'y a rien
  à écrire de plus, seulement à le remonter.
- **`shell: bash`** est nécessaire : le shell par défaut de GitHub Actions est
  `bash -e`, sans `pipefail` — un `| tee` avalerait le code de sortie non nul
  de `run_eval`. `shell: bash` force `-eo pipefail`.
- **Le job échoue si l'évaluation échoue.** Une croix rouge se voit ; un
  résumé vert qu'il faut ouvrir pour y lire une mauvaise note, non. Cette
  croix ne bloque rien : le garde de D2 ne regarde que `ci.yml`, donc
  `revue-ok` peut être posé malgré une alerte rouge. C'est exactement
  l'intention I6 — « il en fait ce qu'il veut ».
- **Restreint à `feature/**`**, pas à toutes les branches sauf `main`. Un push
  sur `dev` est un fast-forward de commits déjà évalués sur la branche de
  travail : l'étendre à `dev` ferait repayer la même évaluation sans rien
  apprendre. Conséquence assumée : une branche de travail qui ne s'appelle pas
  `feature/…` n'a pas d'alerte (le gate, lui, la rattrape toujours).
- **Coût** : `intents.md` l'assume explicitement — « le lot A cesse d'être
  gratuit […] ça se voit sur la facture ». Un push touchant le prompt déclenche
  12 contrats d'évaluation réelle.

---

## D4 — Où vont les TA mockés ? *(point ouvert, à valider avant implémentation)*

**État actuel** : `tests/acceptance/` tourne **deux fois** — dans `ci.yml`
(lot A) et dans le job `tests` de `gate.yml` (lot C). Gratuit à chaque fois
(`MOCK=on`), mais jamais tranché intentionnellement.

### Les deux options

| | Option 1 — TA dans le lot A **et** le lot C (état actuel) | Option 2 — TA dans le lot C seul |
| --- | --- | --- |
| Détection d'une régression d'acceptance | à chaque push, en secondes | seulement au gate, après la revue |
| Duplication | oui, une ligne de commande dans deux fichiers | non |
| Durée du lot A | + quelques secondes | inchangée |
| Coût monétaire | nul dans les deux cas (`MOCK=on`) | nul |

### Recommandation : garder l'état actuel (option 1), et l'écrire

Les deux principes directeurs de `intents.md` pointent dans la même
direction — ce point n'est donc pas un arbitrage équilibré :

- **Attraper au lot le moins cher** : les TA mockés sont gratuits et rapides.
  S'ils peuvent voir une régression, ils doivent la voir au lot A. Les
  retirer, c'est choisir de découvrir au lot C (après avoir mobilisé un
  relecteur) une information disponible gratuitement au push.
- **Informer n'est pas prouver** : le lot C ne peut pas *supposer* que le lot A
  a tourné sur ce SHA — une preuve s'établit dans son propre périmètre. Il doit
  donc rejouer les TA de toute façon. La duplication n'est pas un doublon à
  éliminer : ce sont **deux rôles différents joués par le même test**, ce que
  le principe 1 décrit précisément.

Ce qui manque n'est donc pas une décision technique mais une **justification
écrite** : quelques lignes dans `docs/exploitation.md` § 3 et un commentaire
dans `gate.yml` disant que la répétition est voulue, pour qu'aucune relecture
future ne la « nettoie ».

**Reste à valider par l'utilisateur** avant d'exécuter les tâches du plan qui
en dépendent — c'est son point ouvert, la spec ne le ferme pas d'autorité.
Si l'option 2 était retenue, il faudrait retirer `tests/acceptance` de la
commande `pytest` de `ci.yml` (une ligne) et l'inscrire de même.

---

## Tests / vérification

Aucun de ces quatre points n'est du code applicatif : rien n'est testable par
`pytest`. Les vérifications disponibles, par ordre de force :

1. **Syntaxe YAML** de chaque workflow créé ou modifié :
   `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/<f>.yml').read_text())"`.
   Valide la syntaxe, pas la sémantique GitHub Actions.
2. **Le garde de D2, en dur, hors CI** : la commande `gh api` peut être jouée
   localement (`gh` 2.45 installé, `origin` =
   `git@github.com:wawawaformation/mardik-api-mlops.git`) contre un SHA réel
   déjà passé en CI. C'est la seule vérification *réelle* possible avant une
   PR : elle prouve que le chemin d'API, le filtre `head_sha` et l'expression
   `--jq` sont exacts.
3. **Revue de lecture** des points non exécutables (les `if:`, les chemins
   `paths:`), sous forme de liste à cocher dans le plan.
4. **Vérification bout en bout** : une vraie PR `feature/x → dev`, approuvée
   par `connarddu16-design`, avec CI verte puis CI rouge. Hors plan de code,
   à faire par l'utilisateur une fois les protections posées.

## Prérequis hors code (à faire par l'utilisateur)

Les prérequis de la spec du 2026-09-22 (compte relecteur, `CI_TAG_TOKEN`,
secrets Azure) sont en place. S'ajoutent :

- **Ruleset sur `dev`** : bloquer les force-push, bloquer la suppression,
  *require linear history*. **Ne pas** activer *require a pull request before
  merging* (elle interdirait le `git push` de la fusion fast-forward).
- **Ruleset sur `main`** : les mêmes règles. (La conception du 2026-09-22
  demandait déjà « fusions fast-forward seules sur `main` » ; la nouveauté est
  que `dev` est soumise à la même exigence.)
- **Protection des tags** `revue-ok/*`, `eval-ok/*`, `v*` : immuables, non
  supprimables (déjà listé le 2026-09-22, toujours à faire). Les tags `gate/*`
  ne sont pas protégés : ce sont des déclencheurs poussés par le développeur,
  pas des preuves.
- **Créer la première branche `feature/x`** : le dépôt n'en a aucune
  aujourd'hui, le travail se fait encore directement sur `dev`. Sans branche
  de travail, ni le lot B (il n'y a pas de PR à approuver) ni D3 (le filtre
  `branches: feature/**`) n'ont d'objet.
