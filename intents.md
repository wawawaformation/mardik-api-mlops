# intents.md — intentions de la chaîne LLMOps

> Ce que je veux, et **pourquoi**. En amont du code, des workflows et des
> documents de conception d'implémentation.
>
> Ce fichier existe parce que le code peut être juste et malgré tout ne pas
> faire ce qui était voulu. Les docs de conception décrivent *comment* ;
> celui-ci fixe *ce qu'on cherche*. En cas de désaccord entre un workflow et
> ce fichier, c'est le workflow qui a tort.
>
> Posé le 2026-09-23, par mise à plat morceau par morceau.

---

## Deux principes directeurs

Tout le reste en découle. Si une décision de la chaîne paraît arbitraire,
c'est qu'on a perdu de vue l'un des deux.

### 1. Informer n'est pas prouver

Un même test peut jouer deux rôles radicalement différents :

- **Informer** : dire au développeur où il en est. Sans conséquence, sans
  trace, rejouable autant de fois qu'on veut.
- **Prouver** : établir un fait qui autorise l'étape suivante. Une preuve
  s'écrit, elle est attachée à un objet précis, et elle arrive dans un ordre.

Trois lots qui « font des tests » se ressemblent tous tant qu'on ne sépare
pas ces deux rôles. Une fois séparés, chaque pièce se range seule.

### 2. Attraper au plus tôt, au lot le moins cher

Chaque lot coûte plus cher que le précédent : le lot A coûte des secondes,
le lot B coûte de l'attention humaine, le lot C coûte de l'argent.

**Tout problème doit être détecté au lot le moins cher capable de le voir.**
Mobiliser un relecteur pour lui faire découvrir qu'un test unitaire casse,
c'est payer cher une information disponible gratuitement trente secondes
plus tôt.

---

## Les trois lots

| Lot | Contenu | Rôle | Coût |
| --- | --- | --- | --- |
| **A** | Lint + TU + TI (LLM mocké) | informer | secondes |
| **B** | Revue de code | **prouver** | attention humaine |
| **C** | Gate : tests mockés + évaluation réelle | **prouver** | appels LLM facturés |

---

## La chaîne

| # | Où | Déclencheur | Ce qui se passe | Résultat |
| --- | --- | --- | --- | --- |
| 1 | `feature/x` | push | **Lot A** | vert / rouge |
| 2 | PR `feature/x → dev` | approbation | **Lot B** | `revue-ok/<sha7>` |
| 3 | `dev` | manuel, quand on veut | **Lot C** | `eval-ok/<sha7>` |
| 4 | `dev → main` | manuel | fast-forward, rien d'autre | déploiement |

Le SHA est **le même sur les quatre lignes**. C'est ce qui fait tenir
l'ensemble.

---

## Les intentions

### I1 — `main` ne sert qu'au déploiement

Pas de TU, pas de TI, pas de TA sur `main`. Les tests appartiennent à `dev`.

Quand un commit arrive sur `main`, il est **déjà prouvé** : `main` ne
re-prouve rien, elle livre. Une `main` qui rejouerait les tests dirait « je
ne fais pas confiance au gel » — et dans ce cas les preuves ne serviraient à
rien.

Le seul contrôle admis sur `main` est la vérification que les preuves
existent. Ce n'est pas un test : il ne regarde pas le code, il regarde les
tags.

### I2 — Rien ne part sur `main` sans preuve : deux étapes

Puisque `main` ne vérifie plus rien par elle-même, il faut être certain que
ce qu'on déploie est propre. D'où **deux étapes obligatoires** avant la
fusion, dans cet ordre :

1. la **revue de code** (lot B),
2. le **gate** (lot C) — qui porte les tests mockés *et* l'évaluation réelle.

L'ordre est verrouillé : le lot C refuse de démarrer s'il n'y a pas de
`revue-ok` sur le SHA.

### I3 — Le relecteur doit savoir que le lot A passe

Au moment où la PR est demandée, le relecteur doit avoir la **certitude**
que le lot A est vert — pas seulement la possibilité d'aller voir.

Découlant du principe 2 : faire entrer un humain sur du code dont on sait
déjà qu'il est cassé, c'est dépenser la ressource la plus chère de la chaîne
pour rien.

### I4 — Entre le lot B et le lot C, le code n'a pas bougé

Une revue ne vaut que pour le code qui a été relu. Si quoi que ce soit
change entre l'approbation et le gate, la revue ne porte plus sur rien.

**C'est le hash qui donne cette certitude.** Le SHA d'un commit est calculé
sur l'arbre complet — chaque fichier, son contenu, son chemin. Un octet qui
change n'importe où, et c'est un autre SHA.

Le lot C ne demande donc pas « y a-t-il eu une revue quelque part ? » mais
« y a-t-il un `revue-ok` **sur ce SHA-ci** ? ». Si un commit est arrivé
entre-temps, la tête a bougé, le tag est resté en arrière, le gate refuse.
Aucune vérification supplémentaire à écrire : la propriété tombe toute
seule.

**Corollaire — les fusions sont fast-forward.** `feature → dev` puis
`dev → main`. Un squash ou un merge commit fabrique un nouveau SHA, que les
preuves ne suivent pas.

### I5 — Les preuves se stockent en tags

Le hash *identifie* le code, il n'*atteste* de rien. Il faut un endroit où
écrire le fait. Trois options existaient — tag git, commit status GitHub, ou
interrogation de l'API au moment du gate. **Choix retenu : le tag.**

Pourquoi :

- Il **vit dans le dépôt**. Un `git tag --points-at <sha>` le montre depuis
  un terminal, sans API, sans être connecté, sans GitHub. Si le projet part
  sur une autre forge, les tags suivent ; les commit statuses, non.
- Il est **lisible par un humain sans outil**. Un status vert est une case
  dans une interface ; `revue-ok/2f10905` est une phrase.

Conséquence assumée : il faut un jeton pour pousser les tags
(`CI_TAG_TOKEN`) et des règles de protection pour qu'ils soient immuables.

### I6 — Alerte évaluation dans le lot A, sans tag

Si un push touche quelque chose qui peut **influencer la note d'évaluation**
— prompt, modèle, pipeline, règles d'éval — le lot A joue l'évaluation en
plus des tests mockés. Condition exprimée dans le YAML, sur les chemins
modifiés.

Ce qui influence l'éval dans ce dépôt :

| Chemin | Pourquoi |
| --- | --- |
| `models/*/config.yaml` | prompt, modèle, paramètres, schéma de sortie, stratégie |
| `app/pipeline/**` | découpage en sections et consolidation — change ce qu'on envoie au modèle |
| `app/llm_client.py` | chargement du bundle et appel |
| `eval/**` | attendus, contrats, calcul de la note |

Le reste (`ops/`, `client_web/`, `docs/`, `bruno/`, les tests) ne peut pas
déplacer une note d'éval.

**Cette évaluation ne pose aucun tag.** C'est un signal au développeur :
« tu viens de toucher le prompt, voilà ce que ça donne sur les 12 contrats ».
Il en fait ce qu'il veut. La seule évaluation qui fait foi reste celle du
lot C, après la revue.

Si elle posait `eval-ok`, on pourrait obtenir la preuve sans jamais passer
par la revue — l'ordre du I2 s'effondrerait.

**Conséquence à assumer : le lot A cesse d'être gratuit.** Il le reste pour
la plupart des pushes, mais un commit qui touche le prompt déclenche de
vrais appels facturés sur une branche de travail. C'est l'objectif — savoir
tôt qu'on a cassé la qualité — mais ça se voit sur la facture.

---

## Points encore ouverts

- **Où placent-on les TA mockés** (`tests/acceptance/`, gratuits) ? Avec les
  TU et TI dans le lot A, ou en première marche du lot C ? Aujourd'hui ils
  tournent **deux fois** — la duplication n'est pas un accident (le gate ne
  peut pas supposer que le lot A a tourné sur *ce* SHA), mais elle n'a pas
  été tranchée intentionnellement.

---

## Écarts entre ces intentions et le code actuel (2026-09-23)

Constat, pas plan d'action.

| # | Écart | Intention concernée |
| --- | --- | --- |
| 1 | `revue.yml` exige `base.ref == 'main'` ; la revue doit se faire sur une PR `feature/x → dev` | chaîne, étape 2 |
| 2 | `revue.yml` pose `revue-ok` sans vérifier que le lot A est vert sur ce SHA — on peut approuver du code cassé | I3 |
| 3 | L'évaluation conditionnelle du lot A n'existe pas | I6 |
| 4 | Aucune protection de branche : `main` n'impose pas le fast-forward. Le 2026-09-23, la PR #1 a été fusionnée par un merge commit (`aec3112`) avant tout tag — `cd-main.yml` a correctement refusé de déployer | I4 |
| 5 | Aucune protection de tag sur `revue-ok/*`, `eval-ok/*`, `v*` | I5 |
| 6 | Le second compte GitHub (`connarddu16-design`) existe parce que GitHub interdit d'approuver sa propre PR — contrainte de plateforme, pas intention. La conception gelée assume l'auto-revue (`ci-feature-dev.drawio`, note 0c) | I2 |
