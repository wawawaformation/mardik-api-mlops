# Design — Chaîne LLMOps (chantier 1, point 3)

> Date : 2026-09-22. Statut : validé par l'utilisateur (brainstorming), en attente de plan.
> Couvre `eval/run_eval.py::evaluer`, `ops/deploy.py` (sauf `surveiller`) et les
> workflows GitHub Actions qui remplacent `.github/workflows/llmops.yml`
> (actuellement un `[TEMPLATE]` monolithique, antérieur à la décision à deux
> tags). Périmètre du point 3 tranché le 2026-09-22 (voir `TODO.md`, `MEMORY.md`).

## Besoin

Le brief exige une chaîne CI/CD qui : bloque toute fusion vers `main` tant que
la revue et le gate d'évaluation réel ne sont pas frais (`gel-eval-avant-fusion.md`,
décision actée le 2026-09-21) ; construit un artefact Docker versionné (SemVer)
une fois fusionné ; démarre un déploiement canary. Rien de tout cela n'existe
encore : `.github/workflows/llmops.yml` est un squelette d'apprentissage
(`[TEMPLATE]`) écrit avant cette décision — un seul pipeline linéaire sur push
`main`/PR/tags, sans les deux tags de preuve.

## Hors périmètre (chantier 2, non traité ici)

- `ops/deploy.py::surveiller` (détection de dérive, rollback automatique).
- `app/gateway.py` (routage réel du trafic canary).
- Progression automatique du canary (10→50→100 %) : elle dépend de `surveiller`.
- Conséquence assumée : `tests/acceptance/test_observabilite.py::test_promotion_canary_puis_totale`
  et `test_rollback_en_une_operation` resteront rouges après ce plan — ils
  appellent aussi `app/gateway.py` (`client.get("/gateway/etat")`,
  `from app.gateway import choisir_version`). Vérifié dans le code des tests :
  les assertions sur `ops.deploy.deployer_canary/promouvoir/rollback`
  elles-mêmes (effet sur `registry.index()` et `registry.journal()`) sont
  indépendantes de la gateway et seront couvertes.

## Décisions

| Sujet | Décision |
| --- | --- |
| Formule de la note (`eval/run_eval.py`) | **Rappel** par contrat, tel que documenté dans le stub — pas le micro-F1 scindé de la conception (écart, voir plus bas) |
| Effet de `deployer_canary`/`promouvoir`/`rollback` | **Métadonnée seule** dans `ops/registry/index.json` — aucun routage réel (confirmé par le code fourni `ops/registry/__init__.py`) |
| Automatisation du CD sur `main` | Jusqu'au **canary 10 %** (`publier` + `deployer_canary(10)`) ; promotion/rollback restent des commandes manuelles |
| Déclenchement du gate réel | **Tag `gate/<sha7>` poussé par le développeur** (mécanisme identique à `revue-ok`/`eval-ok`, pas de `workflow_dispatch`) |
| Preuve de revue (`revue-ok`) | **Second compte GitHub dédié** (ex. `mardik-relecteur`) qui approuve la PR — même pattern que QualiCheck, pas une simple déclaration |
| Bump SemVer major/minor | **Mot-clé dans le message du commit de tête** de `main` (`[minor]`/`[major]`) ; patch par défaut |
| `CANARY_PERCENT`/`MOCK` dans `.env` | Restent statiques (décision antérieure, 2026-09-22) |
| Structure des workflows | **4 fichiers séparés par rôle** (`ci.yml`, `revue.yml`, `gate.yml`, `cd-main.yml`), remplacent `llmops.yml` — pattern repris de `/projets/QualiCheck/.gitea/workflows/` (syntaxe GitHub Actions native, aucune adaptation de syntaxe nécessaire) |

### Écart de conception à documenter dans `docs/conception_revue/`

`conception_figee/chantier1_llmops/note-evaluation.md` avait décidé un
**micro-F1 scindé courts/longs** (9 courts ≥ 0,75, 3 longs ≥ 0,80). Le stub
fourni `eval/run_eval.py::evaluer` documente un **rappel simple** par contrat
(clauses attendues trouvées / clauses attendues), sans mention de micro-F1.
Aucun test ne verrouille l'une ou l'autre formule exacte — seul
`test_gate_evaluation_note_par_version` vérifie que `v2.note >= 0.75` (un
seuil global unique, pas deux notes séparées) et que chaque entrée de
`par_contrat` porte `note` + `seuil_note`. Décision : suivre le stub (le code
fourni fait foi sur un point non verrouillé par les tests). Le garde-fou visé
par la conception (« un contrat long faible ne doit pas être masqué par la
moyenne ») reste assuré autrement : `passe` exige qu'aucun contrat n'échoue
son propre `seuil_note` (déjà présent dans `eval/attendus.jsonl` : 0,75 pour
les 9 courts, 0,80 pour les 3 longs), donc un contrat long faible fait
toujours échouer le gate même si la moyenne globale est haute.

## `eval/run_eval.py::evaluer`

Pour chaque contrat de `eval/contrats/` (12 au total) :

1. charger le texte, l'analyser avec le moteur que dicte la stratégie du
   bundle (`analyser_v1` / `analyser_v2`), `n_essais` fois (défaut :
   `parametres.essais_eval` du bundle, sinon 1) ;
2. comparer les types de clauses trouvées à `clauses_attendues` (depuis
   `attendus.jsonl`) → note de rappel par essai, moyennée sur les essais ;
3. mesurer latence et coût de chaque appel.

Agrégation : `note` globale = moyenne des notes par contrat. `latence_p95_ms`
et `cout_moyen_eur` = P95/moyenne sur toutes les analyses. `passe` = `note >=
seuil` ET aucun contrat sous son `seuil_note` ET `latence_p95_ms <
latence_max_ms` ET `cout_moyen_eur < cout_max_eur`. Une ligne JSON est ajoutée
à `eval/history.jsonl` (sauf si `historique=None`, cf. signature du stub).

## `ops/deploy.py`

- **`publier`** : appelle `evaluer()` sur le bundle en chantier — sauf si un
  `rapport` est fourni (le workflow `cd-main.yml` réutilisera le rapport déjà
  produit par `gate.yml`, pour ne pas repayer un second appel au vrai modèle).
  Refuse (`ErreurDeploiement`) si `rapport.passe` est faux. Sinon
  `Registry.etiqueter(...)` puis `journaliser("publication", ...)`. En
  pratique, la réutilisation de `rapport` n'est disponible que côté API
  Python : le CLI `python -m ops.deploy publier` n'expose pas de flag
  `--rapport`, donc l'invocation de `cd-main.yml` sur `main` rejoue toujours
  le vrai gate (second appel réel, payant, au modèle Azure).
- **`deployer_canary`** : `Registry.definir_canary(version, pourcentage)` +
  journal. Le pourcentage par défaut vient de `CANARY_PERCENT` (`.env`), sinon
  10.
- **`promouvoir`** : `Registry.definir_actif(version)`, vide le canary,
  conserve l'ancienne version active dans `index["precedente"]`, journal.
- **`rollback`** : si un canary est en cours, le retire ; sinon l'active
  redevient `precedente`. Journal avec le motif.

Ces quatre fonctions ne touchent que `ops/registry/index.json` et
`journal.jsonl` (fichiers locaux, `[FOURNI]`) — aucun appel réseau, aucun
effet sur le trafic réel.

## Workflows GitHub Actions

Remplacent `.github/workflows/llmops.yml` par 4 fichiers, chacun avec un
déclencheur et une responsabilité uniques (`make ci` reste l'équivalent local
du job rapide) :

### `ci.yml`

Push sur toute branche sauf `main`. `ruff check .` + `MOCK=on pytest -q
tests/unit tests/integration tests/acceptance`.

### `revue.yml`

Sur `pull_request_review` approuvée par le compte dédié (`mardik-relecteur`)
vers `main` : pose `revue-ok/<sha7>` sur le SHA de tête de la PR (idempotent —
ne replante pas si déjà posé). Jamais déclenché par le développeur.

### `gate.yml`

Sur push d'un tag `gate/<sha7>` :

1. refuse immédiatement si aucun `revue-ok/*` ne pointe sur ce SHA ;
2. job `tests` = équivalent de `ci.yml` (`MOCK=on`) ;
3. job `evaluation` (`needs: tests`, **dans la même exécution** — sans quoi
   rien n'empêche de poser `eval-ok` sur un commit dont les tests rapides ont
   échoué) : secrets Azure réels, `eval.run_eval.evaluer(version="v2",
   seuil=0.75)`, échec si `passe` est faux ;
4. pose `eval-ok/<sha7>` (idempotent).

### `cd-main.yml`

Push sur `main` (n'arrive qu'en fast-forward strict, après vérification des
deux tags à la fusion — mécanisme déjà décrit dans
`gel-eval-avant-fusion.md`, pas répété ici) :

1. garde bash : `revue-ok` et `eval-ok` doivent tous les deux pointer sur
   `github.sha` ;
2. calcule la prochaine version : patch auto-incrémenté depuis la dernière
   version de `ops/registry/`, sauf `[minor]`/`[major]` dans le message du
   commit de tête ;
3. `docker build` + push vers `ghcr.io` (image unique, rôle par commande
   `uvicorn`, cf. `docs/spec-v2.md` §4) ;
4. `ops.deploy.publier(version)` (registre local) ;
5. `ops.deploy.deployer_canary(version)` — pas de pourcentage explicite : la
   fonction retombe sur `CANARY_PERCENT` (`.env`, reste statique par décision
   antérieure), pas de valeur dupliquée dans le workflow.

Rien après l'étape 5 : pas de progression automatique, pas d'appel à
`surveiller`.

## Tests / vérification

- `evaluer()` : tests unitaires avec fixtures `MOCK` — rappel correct par
  contrat, `passe` faux si un contrat est sous son `seuil_note` même quand la
  moyenne globale dépasse le seuil global.
- `ops/deploy.py` : les tests d'acceptance fournis (`test_etiquetage_version_apres_gate`,
  `test_gate_evaluation_note_par_version`, et les assertions sur
  `registry.index()`/`registry.journal()` de `test_rollback_en_une_operation`
  / `test_promotion_canary_puis_totale`) couvrent déjà les quatre fonctions —
  pas de nouveau test d'acceptance à écrire, seulement des tests unitaires
  complémentaires si des cas limites ne sont pas couverts.
- Workflows : non testables unitairement ; vérifiés par une exécution réelle
  sur une branche de test après implémentation, hors du plan de code.

## Prérequis hors code (à faire par l'utilisateur, pas par l'implémentation)

- Créer le compte GitHub dédié `mardik-relecteur` (ou nom équivalent) et
  configurer ses droits d'approbation sur le dépôt.
- Configurer les règles de protection de tag sur GitHub pour `revue-ok/*`,
  `eval-ok/*` et `v*` (immuables, non supprimables) — pas exprimable dans un
  fichier de workflow.
- Générer/enregistrer les secrets GitHub nécessaires (Azure, `CI_TAG_TOKEN`
  ou équivalent pour que `revue.yml`/`gate.yml` puissent pousser des tags).
- Configurer la protection de branche `main` pour n'autoriser que les fusions
  fast-forward (pas de merge commit, pas de squash) — condition nécessaire
  pour que la comparaison de SHA du mécanisme à deux tags reste valide.
