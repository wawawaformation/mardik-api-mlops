# Chaîne LLMOps — alignement sur `intents.md` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four remaining gaps listed in `TODO.md` § « Chaîne LLMOps — écarts avec `intents.md` (2026-09-23) » : guard `revue-ok` behind a green lot A (D2), add the conditional evaluation alert to lot A (D3), document the two fast-forward merges and their branch protections (D1), and record the decision about the mocked acceptance tests (D4).

**Architecture:** No application code is touched. Two workflow-level changes (`.github/workflows/revue.yml` gets an API-based guard; a new `.github/workflows/alerte-eval.yml` runs a real, tag-less evaluation on eval-sensitive paths) and one documentation revision (`docs/exploitation.md` § 3, still describing the pre-`intents.md` topology). Full reference: `docs/superpowers/specs/2026-09-23-chaine-llmops-intents.md`.

**Tech Stack:** GitHub Actions, `gh` CLI (2.45, installed locally), bash, Python 3.11 / `uv` (only as invoked by the workflows).

## Global Constraints

- **Ne rien implémenter avant que la Tâche 0 soit close.** La spec laisse D4 ouvert ; les tâches 4 et 5 en dépendent directement.
- Aucun fichier de `conception_figee/` n'est modifié (lecture seule, 555). Les révisions de conception vont dans `docs/conception_revue/`.
- `.github/workflows/revue.yml` porte déjà une modification non committée (garde `base.ref == 'dev'`, écart 1). Elle fait partie du même sujet : la committer avec la tâche 1 plutôt que séparément.
- Le nouveau workflow ne pose **aucun tag** et ne reçoit **pas** `CI_TAG_TOKEN` : c'est le point de conception central de I6, une erreur ici ferait s'effondrer l'ordre revue → gate.
- Français pour les commentaires et les messages de log des workflows, anglais pour les titres de commit — convention en place dans les quatre workflows existants.
- Les workflows ne sont pas testables par `pytest`. Chaque tâche se vérifie par : validation YAML + une commande réellement exécutable quand il y en a une + une liste de relecture.
- Les vérifications bout en bout (vraie PR, vrai gate) restent hors plan : elles supposent les rulesets de la tâche 0 et une branche `feature/x` qui n'existe pas encore.

---

## File Structure

- Modify `.github/workflows/revue.yml` — add the « lot A vert » guard (Task 1).
- Create `.github/workflows/alerte-eval.yml` — conditional real evaluation, no tag (Task 2).
- Modify `docs/exploitation.md` — § 3 « Chaîne de livraison » (Tasks 3 and 4).
- Modify `.github/workflows/gate.yml` — one comment only, on the intentional duplication (Task 4, blocked).
- Modify `TODO.md`, `CHANGELOG.md`, `MEMORY.md` (Task 5).

---

### Task 0: Débloquer — décision D4 et prérequis GitHub

**Files:** aucun (décisions et actions hors code, par l'utilisateur).

- [ ] **Step 1: Faire trancher D4**

Présenter la recommandation de la spec (§ D4) : garder les TA mockés **dans le lot A et dans le lot C**, et écrire pourquoi. Les deux principes de `intents.md` convergent, mais c'est un point ouvert de `TODO.md` — il appartient à l'utilisateur.

Sortie attendue : « option 1 » (recommandée) ou « option 2 ». Noter la réponse dans `MEMORY.md` à la tâche 5.

- [ ] **Step 2: Poser les protections GitHub (utilisateur)**

Rulesets sur `dev` **et** `main` : bloquer les force-push, bloquer la suppression, *require linear history*. **Ne pas** activer *require a pull request before merging* — elle interdirait le `git push` de la fusion fast-forward (spec, § D1). Protection des tags `revue-ok/*`, `eval-ok/*`, `v*` (immuables) ; `gate/*` reste libre.

- [ ] **Step 3: Vérifier**

Non automatisable. Contrôle manuel : tenter un `git push --force` sur une branche de test protégée doit être refusé. À défaut, relire les rulesets dans l'interface GitHub.

---

### Task 1: Garde « lot A vert » dans `revue.yml` (D2)

**Files:**

- Modify: `.github/workflows/revue.yml` (nouvelle étape avant la pose du tag ; embarque aussi la correction non committée `base.ref == 'dev'`)

**Interfaces:**

- Consomme : l'API GitHub `repos/{owner}/{repo}/actions/workflows/ci.yml/runs?head_sha=…` (donc le nom de fichier `ci.yml` — le renommer casserait ce garde).
- Produit : un `revue-ok/<sha7>` qui n'existe que si le lot A a conclu `success` sur ce SHA. Consommé par le garde de `gate.yml` (inchangé).

- [ ] **Step 1: Vérifier le mécanisme en réel, avant d'écrire le YAML**

C'est l'équivalent du test qui échoue : on prouve que la requête API dit la vérité avant de la câbler.

```bash
gh run list --workflow=ci.yml --limit 10 \
  --json headSha,status,conclusion,headBranch
```

Relever un SHA dont la conclusion est `success` et, s'il en existe un, un SHA `failure`. Puis, pour chacun :

```bash
gh api "repos/wawawaformation/mardik-api-mlops/actions/workflows/ci.yml/runs?head_sha=<SHA>&per_page=1" \
  --jq '.workflow_runs[0] | "\(.status) \(.conclusion)"'
```

Attendu : `completed success` pour le premier, `completed failure` pour le second. Vérifier aussi le cas « aucune exécution » sur un SHA quelconque (ex. un commit de `main`) : la sortie doit être vide ou `null null`, jamais un faux `success`.

Si aucune exécution `failure` n'existe dans l'historique, le noter : seul le cas vert aura été vérifié en réel, le cas rouge reposera sur la relecture du `case`.

- [ ] **Step 2: Ajouter le garde dans `revue.yml`**

Insérer l'étape **entre** « Checkout au SHA relu » et « Poser revue-ok sur le SHA relu » (le garde doit précéder l'écriture du tag, jamais l'inverse) :

```yaml
      - name: Vérifier que le lot A est vert sur ce SHA
        env:
          GH_TOKEN: ${{ secrets.CI_TAG_TOKEN }}
          SHA: ${{ github.event.pull_request.head.sha }}
        run: |
          # I3 — le relecteur doit avoir la certitude que le lot A passe, pas
          # seulement la possibilité d'aller voir. Pas de needs: possible :
          # ci.yml appartient à une autre exécution, déclenchée par un push.
          # On vise ci.yml nommément, pas tous les check-runs du SHA :
          # l'alerte d'évaluation (alerte-eval.yml) est un signal et ne doit
          # rien conditionner.
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

Compléter le commentaire d'en-tête du fichier : le workflow ne fait plus qu'attester une approbation, il atteste « approbation **sur du code dont le lot A est vert** ».

- [ ] **Step 3: Valider la syntaxe YAML**

Run: `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/revue.yml').read_text())"`
Expected: aucune sortie, code 0.

- [ ] **Step 4: Liste de relecture**

- [ ] Le garde est **avant** l'étape qui pose le tag.
- [ ] `GH_TOKEN` est `secrets.CI_TAG_TOKEN` (le `GITHUB_TOKEN` par défaut exigerait `permissions: actions: read`, absent du fichier).
- [ ] La requête vise `workflows/ci.yml/runs`, pas `check-runs` ni `gh pr checks`.
- [ ] Le `case` distingue trois issues : vert → `exit 0`, conclu-non-vert → `exit 1`, pas encore conclu → attente. Aucune branche ne laisse passer un état inconnu.
- [ ] Le garde `if:` du job compare toujours `base.ref == 'dev'` (correction de l'écart 1, déjà présente dans le fichier de travail — la conserver).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/revue.yml
git commit -m "ci(revue): target dev and require a green lot A before tagging revue-ok"
```

Corps du message (français) : rappeler l'écart 1 (cible `dev`) et I3 (garde lot A), et pourquoi un `needs:` était impossible.

---

### Task 2: Workflow `alerte-eval.yml` (D3)

**Files:**

- Create: `.github/workflows/alerte-eval.yml`

**Interfaces:**

- Consomme : `python -m eval.run_eval --version v2 --seuil 0.75` (CLI déjà en place, `eval/run_eval.py::main`) ; les services `proxy` et `azure-adapter` de `docker-compose.yml` ; les secrets Azure déjà enregistrés.
- Produit : **rien de consommable** — aucun tag, aucun artefact attendu par une autre tâche. C'est le point : un signal, pas une preuve.

- [ ] **Step 1: Créer le fichier**

Reprendre la structure du job `evaluation` de `gate.yml` **sans** `token: ${{ secrets.CI_TAG_TOKEN }}` au checkout et **sans** l'étape de pose de tag :

```yaml
name: Alerte évaluation (lot A)

# I6 — signal, pas preuve. Un push sur une branche de travail qui touche un
# chemin capable de déplacer la note joue l'évaluation réelle (payante) et
# l'affiche. Aucun tag n'est posé : la seule évaluation qui fait foi reste
# celle du lot C, après la revue (gate.yml). Si celle-ci posait eval-ok, on
# obtiendrait la preuve sans passer par la revue et l'ordre revue -> gate
# s'effondrerait (intents.md, I2 et I6). Voir
# docs/superpowers/specs/2026-09-23-chaine-llmops-intents.md.

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
      - name: Checkout
        uses: actions/checkout@v4

      # .env Azure, docker compose up -d --build proxy azure-adapter,
      # attente du proxy, setup-uv, uv sync : recopier à l'identique le job
      # `evaluation` de gate.yml (chaque workflow reste autonome, décision
      # du 2026-09-22).

      - name: Évaluation réelle (signal, aucun tag)
        shell: bash
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

- [ ] **Step 2: Valider la syntaxe YAML**

Run: `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/alerte-eval.yml').read_text())"`
Expected: aucune sortie, code 0.

- [ ] **Step 3: Vérifier que les filtres `paths:` désignent des fichiers réels**

```bash
ls models/*/config.yaml app/llm_client.py && ls -d app/pipeline eval
```

Expected: les quatre chemins existent. Un filtre `paths:` pointant à côté ne déclencherait jamais rien — et l'échec serait silencieux.

- [ ] **Step 4: Vérifier la commande d'évaluation hors CI, en mocké**

Run: `MOCK=on uv run python -m eval.run_eval --version v2 --seuil 0.75 --contrats c01`
Expected: le CLI s'exécute et imprime `note globale = … | P95 = … | coût moyen = …` puis `GATE : …`. On vérifie la forme de la sortie qui alimentera le résumé, pas la note (mockée, non significative). Aucun appel payant.

- [ ] **Step 5: Liste de relecture**

- [ ] Aucune étape ne pousse de tag, aucun `CI_TAG_TOKEN` dans le fichier, `permissions: contents: read` seulement.
- [ ] `on.push.branches` vaut `feature/**` (ni `dev`, ni `branches-ignore`) — sans quoi le fast-forward vers `dev` repaierait la même évaluation.
- [ ] L'étape d'évaluation porte `shell: bash` (pipefail) : sans lui, `| tee` masquerait un échec de `run_eval`.
- [ ] Le résumé est écrit avec `if: always()`, sinon il disparaît précisément quand la note est mauvaise.
- [ ] Le bloc `.env` reprend exactement les noms de variables de `.env.example`, comme dans `gate.yml`.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/alerte-eval.yml
git commit -m "ci: add alerte-eval.yml — real evaluation as a lot A signal, no tag"
```

---

### Task 3: Réviser `docs/exploitation.md` § 3 — topologie et fusions (D1)

**Files:**

- Modify: `docs/exploitation.md` (§ 3 « Chaîne de livraison »)

**Interfaces:** aucune. Documentation d'exploitation, lue par l'utilisateur au moment de livrer.

- [ ] **Step 1: Relire l'existant et relever les passages faux**

Run: `grep -n "fusion\|main\|revue.yml\|quatre workflows" docs/exploitation.md | sed -n '1,40p'`

Les trois points identifiés par la spec (§ D1) : la phrase d'introduction « De la fusion sur `dev` vers `main` … », le point 2 qui parle d'« une PR vers `main` », et l'absence de toute mention du geste de fusion.

- [ ] **Step 2: Réviser la section**

Contenu à obtenir :

1. Introduction : la chaîne va de `feature/x` à `main` par **deux** fusions fast-forward, `feature/x → dev` puis `dev → main`.
2. Point 2 (`revue.yml`) : la PR est `feature/x → dev` ; le tag n'est posé que si le lot A est vert sur le SHA approuvé (tâche 1).
3. Nouveau point : `alerte-eval.yml` — la liste « quatre workflows » devient **cinq** ; préciser « aucun tag, signal seulement, payant sur les chemins sensibles » (tâche 2).
4. Nouveau paragraphe « Comment fusionner » avec les commandes exactes :

```bash
git checkout dev  && git merge --ff-only feature/x && git push origin dev
git checkout main && git merge --ff-only dev       && git push origin main
```

   et la raison : **les trois boutons de fusion de GitHub (merge commit, squash, rebase) fabriquent tous un nouveau SHA**, que les tags ne suivent pas. La PR se ferme d'elle-même une fois ses commits sur `dev`.
5. Une ligne sur les rulesets posés à la tâche 0, dont le piège *require a pull request before merging* (à ne pas activer).

Ne pas toucher au reste du fichier (§ 1, 2, 4 à 7). Le « micro-F1 » de la § 3 est un écart réel mais antérieur et hors sujet ici : le signaler à l'utilisateur, ne pas le corriger dans cette tâche.

- [ ] **Step 3: Vérifier**

Relecture croisée : chaque affirmation de la § 3 doit être vraie au regard de `.github/workflows/` (cinq fichiers après la tâche 2) et de la table « La chaîne » de `intents.md`. Vérifier en particulier qu'aucune phrase ne dit plus que la revue porte sur une PR vers `main`.

Run: `grep -n "PR vers .main\|quatre workflows" docs/exploitation.md`
Expected: aucune ligne.

- [ ] **Step 4: Commit**

```bash
git add docs/exploitation.md
git commit -m "docs(exploitation): describe the feature/dev/main chain and its two fast-forward merges"
```

---

### Task 4: Inscrire la décision sur les TA mockés (D4) — **bloquée par la Tâche 0**

**Files:**

- Modify: `docs/exploitation.md` (§ 3)
- Modify: `.github/workflows/gate.yml` (commentaire uniquement)
- Modify (option 2 seulement): `.github/workflows/ci.yml`

**Interfaces:** aucune en option 1 (état actuel conservé). En option 2, `ci.yml` cesse de couvrir `tests/acceptance` — à répercuter sur `make ci`, dont c'est l'équivalent local.

- [ ] **Step 1: Ne rien faire tant que la Tâche 0, Step 1 n'a pas de réponse écrite**

- [ ] **Step 2 (option 1, recommandée) : écrire que la répétition est voulue**

Dans `docs/exploitation.md` § 3, quelques lignes : les TA mockés tournent au lot A *et* au lot C ; au lot A ils **informent** (détection au lot le moins cher), au lot C ils **prouvent** (le gate ne peut pas supposer que le lot A a tourné sur ce SHA). Ce n'est pas un doublon à nettoyer.

Dans `.github/workflows/gate.yml`, ajouter la même remarque en une ligne au-dessus de l'étape « Tests unitaires, intégration, acceptance (MOCK=on) » du job `tests`, pour qu'elle soit lue par qui édite le fichier.

- [ ] **Step 2 bis (option 2, si l'utilisateur la choisit) : retirer les TA du lot A**

Dans `.github/workflows/ci.yml`, la commande devient `uv run pytest -q tests/unit tests/integration`. Aligner la cible `ci:` du `Makefile` (équivalent local revendiqué par l'en-tête du workflow) et inscrire la raison dans `docs/exploitation.md`.

- [ ] **Step 3: Vérifier**

Option 1 : `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/gate.yml').read_text())"` — code 0 (le commentaire n'a rien cassé).
Option 2 : en plus, `MOCK=on uv run pytest -q tests/unit tests/integration` doit passer, et `make ci` ne doit plus prétendre couvrir l'acceptance.

- [ ] **Step 4: Commit**

Option 1 : `docs: record that mocked acceptance tests run in both lot A and lot C on purpose`
Option 2 : `ci: move mocked acceptance tests to the gate only`

---

### Task 5: Mettre à jour `TODO.md`, `CHANGELOG.md`, `MEMORY.md`

**Files:**

- Modify: `TODO.md`, `CHANGELOG.md`, `MEMORY.md`

- [ ] **Step 1: `TODO.md`**

Cocher les cinq entrées de la section « Chaîne LLMOps — écarts avec `intents.md` (2026-09-23) » traitées : cible de la revue (acquis, tâche 1), deux fusions fast-forward (tâche 3), lot A vert avant `revue-ok` (tâche 1), alerte d'évaluation (tâche 2), TA mockés (tâche 4), nettoyage de `main` (acquis). Ajouter une entrée non cochée pour ce qui reste vraiment ouvert : **la vérification bout en bout sur une vraie PR `feature/x → dev`**, impossible tant qu'aucune branche `feature/…` n'existe.

- [ ] **Step 2: `CHANGELOG.md`**

Entrée datée 2026-09-23, en tête, en français : ce qui a été aligné sur `intents.md`, et les deux points de conception à retenir — GitHub n'offre pas de fusion fast-forward dans l'interface de PR (d'où la fusion en ligne de commande), et un workflow déclenché par `pull_request_review` ne peut pas dépendre d'un job d'un autre workflow (d'où le garde par API).

- [ ] **Step 3: `MEMORY.md`**

Consigner : la décision D4 telle que tranchée à la tâche 0, la règle *require a pull request before merging* à ne pas activer (elle bloquerait la fusion fast-forward — le piège le plus coûteux de ce lot), et le fait que `alerte-eval.yml` rend le lot A payant sur quatre chemins.

- [ ] **Step 4: Commit**

```bash
git add TODO.md CHANGELOG.md MEMORY.md
git commit -m "docs: track the intents.md alignment of the LLMOps chain"
```

---

## Final Verification (après les 5 tâches)

- [ ] `.github/workflows/` contient exactement cinq fichiers : `ci.yml`, `revue.yml`, `gate.yml`, `cd-main.yml`, `alerte-eval.yml`.
- [ ] Les cinq passent `yaml.safe_load`.
- [ ] `grep -rn "CI_TAG_TOKEN" .github/workflows/alerte-eval.yml` ne renvoie **rien** (l'alerte ne peut pas poser de tag).
- [ ] `MOCK=on uv run pytest -q` : inchangé par rapport à avant ce plan (aucun code applicatif touché).
- [ ] `uv run ruff check .` : propre.
- [ ] Chaque affirmation de `docs/exploitation.md` § 3 est vraie au regard de `intents.md` et des cinq workflows.
- [ ] Reste à faire hors plan, à noter dans le rapport final : une vraie PR `feature/x → dev` approuvée par `connarddu16-design`, une fois les rulesets de la tâche 0 posés — c'est la seule vérification qui exerce le garde de la tâche 1 en conditions réelles, dans ses deux issues (CI verte, CI rouge).
