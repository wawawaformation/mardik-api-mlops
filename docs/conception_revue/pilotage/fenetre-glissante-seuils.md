# Fenêtre glissante et seuils de décision (révisé)

> Version révisée dans `mardik-api-mlops/docs/conception_revue/`, à la suite
> de la découverte que le code source fourni (tests d'acceptance figés,
> `ops/deploy.py::surveiller`, `ops/dashboard.py::resume`) impose une fenêtre
> **temporelle**, pas un comptage de requêtes. Document original :
> `conception/pilotage/fenetre-glissante-seuils.md` (dépôt
> `mardik_nouvelle_version`, non modifié). Statut : décision révisée
> (2026-09-21) ; valeurs par défaut provisoires, à calibrer au chantier 2.

## Principe

Inchangé. La fenêtre glissante n'est pas une mémoire ajoutée : c'est la façon
de lire `ops/metrics.jsonl` (déjà produit par la v1) pour décider de façon
fiable. On lit les mesures **récentes**, pas une seule (bruit) ni tout
l'historique (passé résolu).

## Décision de type — révisée

**Fenêtre en secondes** (`fenetre_s`), et non plus en nombre de requêtes.

### Décision initiale (abandonnée)

La première version de cette décision retenait une fenêtre **en nombre de
requêtes** (50 dernières, minimum 30 avant décision), en écartant
volontairement une fenêtre temporelle : *« le volume est faible (~400
contrats/mois ≈ 13/jour) ; une fenêtre temporelle contiendrait très peu de
requêtes et serait trop sensible au hasard »*. Ce raisonnement reste valable
en théorie pour le trafic réel de production (voir « Limite assumée »
ci-dessous).

### Pourquoi on y revient

Le code source fourni (`mardik-api-mlops`) impose une interface différente,
et ses tests d'acceptance sont **figés** — ce sont les critères de réussite
du brief, pas un détail d'implémentation à ajuster à notre convenance :

```python
# tests/acceptance/test_observabilite.py
ops.deploy.surveiller(registry, metriques, fenetre_s=60, score_min=0.7, minimum=10)
ops.dashboard.resume(metriques, fenetre_s=60, registry=registry)
```

Le paramètre est `fenetre_s` (secondes), pas un nombre de requêtes. Plutôt
que de modifier ces tests fournis pour les plier à la décision de conception
initiale, on aligne la décision de conception sur l'interface imposée par le
code : la fenêtre est **temporelle**. `minimum` (nombre de mesures) reste le
garde-fou anti-bruit déjà prévu — il ne disparaît pas, il se combine à la
fenêtre temporelle au lieu de la remplacer.

## Valeurs provisoires — révisées

| Paramètre | Valeur provisoire | Justification |
| --- | --- | --- |
| Fenêtre de surveillance (rollback, `ops.deploy.surveiller`) | **120 s** (valeur par défaut du stub) | Détection rapide ; les tests d'acceptance appellent explicitement `fenetre_s=60` pour leurs scénarios simulés. |
| Fenêtre du tableau de bord (`ops.dashboard.resume`) | **300 s** (valeur par défaut du stub) | Vue un peu plus large que le rollback, pour lisser l'affichage. |
| Nombre minimal de mesures avant décision | **10** (valeur par défaut du stub et des tests) | En dessous, l'échantillon est trop petit pour distinguer dérive et bruit (anti-faux positifs) — même logique qu'avant, seuil abaissé car la fenêtre est courte. |
| Seuil taux d'erreur (rollback) | **> 10 %** | Inchangé — indépendant du type de fenêtre. |
| Seuil latence P95 (rollback) | **> 8 s** | Inchangé — contrainte client. |
| Seuil distribution du score (rollback) | **proportion de score < 0,6 > 20 %** | Inchangé — aligné sur la dérive simulée (`DRIFT=score` → chute vers 0,5). |

> Le seuil de score reste à recaler, comme prévu initialement. Les valeurs de
> fenêtre (120 s / 300 s) sont celles des stubs fournis ; elles restent
> provisoires et calibrables au chantier 2, comme les seuils eux-mêmes.

## Limite assumée

Avec un volume réel de ~13 contrats/jour, une fenêtre de 120 s ou 300 s ne
contiendra quasiment jamais de trafic réel en dehors d'une démo ou d'un test
de charge délibéré (`make traffic`). C'est exactement le raisonnement qui
avait motivé le choix initial en nombre de requêtes — il reste valable pour
le trafic réel de production. Cette fenêtre temporelle est donc surtout
pertinente pour la démonstration (trafic simulé sur une courte durée,
`make traffic --rps ...`) et pour les tests. Point à surveiller au
chantier 2.

## Ce qui dépend encore du type de décision

- **Rollback** : détection rapide, fenêtre courte (120 s par défaut, 60 s
  dans les tests), seuils ci-dessus.
- **Promotion canary** : observation plus longue, à traiter séparément (voir
  `canary.md` révisé dans ce même dossier) — la v2 doit accumuler
  suffisamment de trafic sur son faible % avant d'être promue.

## Points ouverts

- Les valeurs exactes de chaque seuil (erreur, latence, score) et de chaque
  fenêtre (120 s, 300 s) seront calibrées au chantier 2 sur les distributions
  observées, comme le prévoit le brief.
- Écart à répercuter dans le dossier de conception d'origine
  (`conception/pilotage/fenetre-glissante-seuils.md`, dépôt
  `mardik_nouvelle_version`) si celui-ci est repris.
