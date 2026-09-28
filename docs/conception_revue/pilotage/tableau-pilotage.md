---
title: Tableau de pilotage — Mardik v2 (révisé)
author: David LEGRAND
date: 2026-09-21
lang: fr-FR
toc: false
numbersections: false
---

> Version révisée dans `mardik-api-mlops/docs/conception_revue/`, suite à la
> révision de `fenetre-glissante-seuils.md` (fenêtre temporelle, et non plus
> en nombre de requêtes). Document original :
> `conception/pilotage/tableau-pilotage.md` (dépôt `mardik_nouvelle_version`,
> livrable n°2 fusionné dans `1_pilotage.pdf`, non modifié). **Le PDF
> `conception/livrables/1_pilotage.pdf` est donc lui aussi obsolète sur ce
> point** (il affiche encore la fenêtre en nombre de requêtes) — non
> reconstruit ici, car il vit dans le dépôt `mardik_nouvelle_version`.

À quel seuil chaque signal déclenche quelle rétroaction, et où la décision est
tracée. Les trois boucles de rétroaction du brief (rollback sur signal,
promotion canary, enrichissement du jeu d'évaluation) s'y lisent en une table.

| Signal | Seuil | Rétroaction | Trace |
| --- | --- | --- | --- |
| Latence P95 | > 8 s | Rollback | Journal (auto) |
| Taux d'erreur | > 10 % | Rollback | Journal (auto) |
| Score de confiance | > 20 % de scores < 0,6 | Rollback + enrichissement du jeu d'éval | Journal (auto) |
| Canary conforme | contraintes tenues et v2 ≥ v1 | Promotion 10 % → 50 % → 100 % | Journal (auto ou humain) |

## Fenêtre d'observation — révisée

Les seuils ci-dessus se lisent sur une **fenêtre glissante temporelle**
(`fenetre_s`), pas sur un nombre de requêtes : **120 s** pour la surveillance
de rollback (60 s dans les tests d'acceptance fournis), **300 s** pour le
tableau de bord, avec un minimum de **10 mesures** avant toute décision — en
dessous, l'échantillon est trop petit pour distinguer une dérive réelle du
bruit.

Ce choix découle de l'interface imposée par le code source fourni
(`ops.deploy.surveiller`, `ops.dashboard.resume`) et ses tests d'acceptance
figés — voir `fenetre-glissante-seuils.md` (dans ce même dossier) pour le
détail de cette révision. La décision initiale (fenêtre en nombre de
requêtes, justifiée par le faible volume réel ~13 contrats/jour) reste
pertinente pour le trafic de production réel ; la fenêtre temporelle est
surtout mobilisée pour la démonstration et les tests.

## Détail par rétroaction

**Rollback** (latence, erreur, score). Détection rapide sur la fenêtre de
120 s (60 s en test). Dès qu'un seuil est franchi, retour immédiat à la
version saine (v1 à 100 %), sans attendre une confirmation humaine.

**Promotion canary**. La v2 passe au palier suivant (10 → 50 → 100 %) quand,
sur sa fenêtre d'observation, elle respecte les contraintes client (P95 < 8 s,
coût < 0,15 €, taux d'erreur sous seuil) **et** reste au moins aussi bonne que
la v1 sur les mêmes signaux. Si ces critères ne sont pas tenus, la promotion
n'a pas lieu — voire un rollback se déclenche si un seuil critique est franchi.
Déclenchement automatique par défaut ; possible manuellement depuis l'écran
« Actions », pour l'override ou la démo.

**Enrichissement du jeu d'évaluation**. Quand le score de confiance d'une
analyse passe sous 0,6, son texte pseudonymisé est capturé et proposé au
versement dans le jeu d'évaluation. Un juriste valide ou corrige les clauses
attendues avant tout versement — un cas capturé automatiquement n'a pas de
vérité terrain fiable tant qu'il n'a pas été relu. Une fois versé, le cas est
rejoué au gate d'évaluation de la prochaine fusion.

## Auto vs humain

- **auto** : déclenché automatiquement par le serveur de pilotage, dès que la
  fenêtre se conclut et que le critère est atteint.
- **humain** : nécessite un clic dans l'écran « Actions » (override ou démo).

Dans les deux cas, la décision passe par la même chaîne et est tracée au
journal — signal déclencheur, valeur observée, seuil applicable, action prise,
déclencheur, horodatage.

## Points ouverts

Les valeurs de seuil et de fenêtre ci-dessus sont provisoires, à calibrer au
chantier 2 sur les distributions réellement observées (comme le prévoit le
brief). Le détail exact de la comparaison « v2 ≥ v1 » — sur quels signaux,
avec quelle marge — reste également à préciser. Écart à répercuter dans
`conception/pilotage/tableau-pilotage.md` (dépôt `mardik_nouvelle_version`)
si le dossier de conception d'origine est repris.
