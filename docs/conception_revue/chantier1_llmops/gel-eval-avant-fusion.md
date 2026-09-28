# Gel avant fusion — chaîne `feature → dev → main` (révisé)

> Version révisée dans `mardik-api-mlops/docs/conception_revue/`, suite à la
> mise à plat des intentions du 2026-09-23 (voir `intents.md` à la racine du
> dépôt). Documents d'origine :
> `conception_figee/chantier1_llmops/gel-eval-avant-fusion.md` et
> `conception_figee/chantier1_llmops/img/ci-feature-dev.drawio` (dépôt
> `mardik_nouvelle_version`, non modifiés). Statut : décision révisée.
>
> **L'essentiel de la conception d'origine est confirmé, pas remplacé** : les
> deux tags immuables, la fraîcheur par comparaison de SHA, la fusion
> fast-forward stricte, l'absence de gate rejoué sur `main`, le déclenchement
> manuel du gate et de la fusion. Ce document ne consigne que les écarts.

## Écart 1 — une branche de travail `feature/x` s'intercale avant `dev`

**Conception d'origine** : « La branche de travail est nommée `dev` ». L'étape
`0a` du diagramme est « Développement **sur dev** ». Il n'existe qu'une seule
PR possible, `dev → main`, et c'est sur elle que se fait la revue.

**Décision (2026-09-23)** : le développement se fait sur une branche
`feature/x`, et **la revue de code se fait sur une PR `feature/x → dev`**.

La chaîne devient :

| # | Où | Déclencheur | Ce qui se passe | Résultat |
| --- | --- | --- | --- | --- |
| 1 | `feature/x` | push | lot A — lint + TU + TI (mockés) | vert / rouge |
| 2 | PR `feature/x → dev` | approbation | lot B — revue de code | `revue-ok/<sha7>` |
| 3 | `dev` | manuel | lot C — gate (tests mockés + évaluation réelle) | `eval-ok/<sha7>` |
| 4 | `dev → main` | manuel | fast-forward, rien d'autre | déploiement |

**Pourquoi** : `dev` ne doit contenir que du code relu. Dans la topologie
d'origine, on code directement sur `dev` et la revue arrive après coup, au
moment de sortir vers `main` — la branche d'intégration accumule donc du code
non relu, et la seule barrière est à la toute fin.

**Conséquence sur la propriété de fraîcheur** : elle est inchangée, mais elle
exige maintenant **deux** fusions fast-forward au lieu d'une —
`feature/x → dev`, puis `dev → main`. Un squash ou un merge commit à l'une ou
l'autre étape fabrique un nouveau SHA, que les tags ne suivent pas. La
conception d'origine n'imposait le fast-forward que sur la seconde.

**Conséquence sur le code** : le garde de `.github/workflows/revue.yml`
compare aujourd'hui `github.event.pull_request.base.ref == 'main'`. Il doit
comparer à `'dev'`.

## Écart 2 — le rôle de la PR était sous-estimé

**Conception d'origine**, note `0c` du diagramme :

> « Le format PR n'améliore pas la revue en soi (un `git diff` ferait aussi
> bien) — il est nécessaire parce que `main` est protégé : la fusion ne peut
> se faire que via une PR, seul point d'ancrage des checks de gel. »

**Constat (2026-09-23)** : cette justification est fausse, et elle a coûté
deux jours de compréhension.

Un `git diff` **informe** : il montre le code. Il ne **prouve** rien — il ne
produit aucun événement, donc aucun tag, donc aucune preuve attachée à un
SHA. La PR n'est pas une contrainte administrative imposée par la protection
de `main` : c'est le **seul mécanisme qui transforme une relecture humaine en
fait vérifiable par un automate**. C'est la pièce centrale du gel, pas son
support.

Le raisonnement d'origine tenait par accident : il aboutissait à la bonne
conclusion (il faut une PR) pour une mauvaise raison (la protection de
branche). Dès que la topologie change — écart 1 — la mauvaise raison
s'évapore et la conclusion semble arbitraire. D'où la révision.

Rien à changer dans le code : seule la justification est corrigée.

## Écart 3 — alerte d'évaluation conditionnelle dans le lot A

**Conception d'origine** : « Sur `dev`, le développeur déclenche
**manuellement** le gate d'évaluation réel quand il le souhaite — jamais
automatiquement à chaque push. »

**Décision (2026-09-23)** : le lot A joue l'évaluation réelle, automatiquement,
**quand le push touche un chemin capable de déplacer la note** :

| Chemin | Pourquoi |
| --- | --- |
| `models/*/config.yaml` | prompt, modèle, paramètres, schéma de sortie, stratégie |
| `app/pipeline/**` | découpage en sections et consolidation |
| `app/llm_client.py` | chargement du bundle et appel |
| `eval/**` | attendus, contrats, calcul de la note |

**Ce n'est pas le gate, et la règle d'origine n'est pas violée.** Cette
évaluation **ne pose aucun tag**. Elle informe le développeur qu'il vient de
toucher quelque chose d'important ; elle ne prouve rien et n'autorise aucune
étape suivante. Le gate (lot C) reste déclenché manuellement, après la revue,
et reste seul à poser `eval-ok`.

Si elle posait `eval-ok`, on obtiendrait la preuve d'évaluation sans jamais
passer par la revue — l'ordre revue → gate s'effondrerait.

**Conséquence assumée** : le lot A cesse d'être gratuit sur ces chemins-là.
Un commit qui touche le prompt déclenche de vrais appels facturés sur une
branche de travail.

**Conséquence sur le code** : non implémenté à ce jour.

## Écart 4 — le relecteur doit avoir la certitude que le lot A passe

**Conception d'origine** : rien sur ce point. Le diagramme enchaîne
`0b. CI automatique` → `0c. Revue de code` sans lier l'un à l'autre.

**Décision (2026-09-23)** : au moment où la PR est ouverte, le lot A doit être
vert sur le SHA de tête — pas seulement consultable, **garanti**.

**Pourquoi** : chaque lot coûte plus cher que le précédent (secondes,
attention humaine, argent). Faire entrer un relecteur sur du code dont on
sait déjà qu'il est cassé dépense la ressource la plus chère de la chaîne
pour une information disponible gratuitement trente secondes plus tôt.

**Conséquence sur le code** : `revue.yml` pose aujourd'hui `revue-ok` sans
vérifier l'état du lot A sur ce SHA. On peut donc approuver du code cassé et
obtenir le tag. Ce n'est pas dangereux pour la production — le lot C rejoue
les tests mockés avant de payer l'évaluation — mais la détection arrive trop
tard dans la chaîne.

## Écart 5 — le second compte GitHub n'est pas une intention

**Conception d'origine**, note `0c` : « Seul sur ce projet : relecture du diff
avant fusion, **assumée comme auto-revue — pas une revue à deux**. Second
regard automatisé retiré pour l'instant. » La liste des prérequis mentionne
malgré tout un compte dédié `mardik-relecteur`.

**Constat (2026-09-23)** : le compte `connarddu16-design` existe uniquement
parce que **GitHub interdit d'approuver sa propre pull request**. C'est une
contrainte de plateforme, pas un choix de conception. Le mécanisme reste une
auto-revue ; le second compte n'apporte pas un second regard, il permet
seulement à l'événement d'approbation d'exister.

Cette nuance n'avait jamais été explicitée à l'utilisateur au moment de créer
le compte. Elle est consignée ici pour que la relecture du dispositif ne lui
prête pas une intention qu'il n'a pas.

## Incident associé (2026-09-23)

La PR #1 (`dev → main`) a été **fusionnée** au lieu d'être **approuvée** :
aucune revue soumise, donc aucun `revue-ok`, et un merge commit (`aec3112`)
créé sur `main` alors que la conception impose le fast-forward strict.

`cd-main.yml` a refusé de déployer :

```text
[refus] aucun revue-ok/* sur aec3112...
```

Le garde-fou des deux tags a donc fonctionné en conditions réelles, sur un
contournement non simulé. C'est à ce jour la seule exécution du mécanisme de
gel sur un vrai dépôt.

Les protections de branche et de tag prévues par la conception d'origine
(fast-forward seul sur `main`, tags `revue-ok/*`, `eval-ok/*`, `v*`
immuables) ne sont **pas encore configurées** — c'est ce qui a rendu la
fusion possible.
