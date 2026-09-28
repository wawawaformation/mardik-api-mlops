# Questions / Réponses — Chantier 2 (observabilité qui pilote la chaîne) — révisé

> Version révisée dans `mardik-api-mlops/docs/conception_revue/`, suite à la
> révision de `../pilotage/fenetre-glissante-seuils.md` (fenêtre temporelle,
> et non plus en nombre de requêtes). Document original :
> `conception/chantier2_observabilite/questions_reponses.md` (dépôt
> `mardik_nouvelle_version`, non modifié). Seules les questions Q9, Q10, Q12
> et Q14 sont modifiées ci-dessous ; le reste du document original est
> inchangé (non reproduit ici — voir l'original pour Q1-Q8, Q11, Q13, Q15-Q16).

## Q9 — Par rapport à quoi mesure-t-on la dérive du score de confiance ? (révisé)

La dérive se mesure sur la **fenêtre glissante de production** (les mesures
des `fenetre_s` dernières secondes de `metrics.jsonl`), pas sur la
distribution figée au moment de la sortie du pipeline. C'est un
**glissement observé en continu** : la proportion de scores faibles dépasse
un seuil → dérive.

→ Voir `../pilotage/fenetre-glissante-seuils.md` (révisé) et `drift-proxy.md`.

## Q10 — Combien de requêtes au minimum avant de conclure à une dérive ? (révisé)

**10 mesures** minimum dans la fenêtre avant de décider (valeur des tests
d'acceptance fournis et du stub `ops.deploy.surveiller`). En dessous,
l'échantillon est trop petit pour distinguer une vraie dérive du bruit
(anti-faux positifs). La fenêtre elle-même est **temporelle** : **120 s**
par défaut pour la surveillance de rollback (60 s dans les tests
d'acceptance), **300 s** pour le tableau de bord — et non plus un nombre de
requêtes fixe, contrairement à la décision initiale.

→ Voir `../pilotage/fenetre-glissante-seuils.md` (révisé).

## Q12 — Comment distinguer une vraie dérive du bruit ? (révisé)

Trois garde-fous :

- **fenêtre glissante temporelle** : on lit les mesures des `fenetre_s`
  dernières secondes (120 s pour le rollback, 300 s pour le tableau de
  bord), pas une seule ;
- **taille d'échantillon minimale** : 10 mesures avant toute décision ;
- **seuils avec marge** : seuils exprimés en proportion/quantile (P95, > 10 %,
  > 20 %), à calibrer sur les distributions observées pour éviter les faux
  positifs.

→ Voir `../pilotage/fenetre-glissante-seuils.md` (révisé).

## Q14 — Promotion canary : critères, durée, paliers, si critères non tenus ? (révisé)

- **Paliers** : 10 % → 50 % → 100 %.
- **Critères** (sur la fenêtre d'observation de 120 s) : respecter les
  contraintes client (P95 < 8 s, coût < 0,15 €, erreurs sous seuil) **et** ne
  jamais être moins bonne que la v1 sur latence/erreurs/coût **et** être
  strictement meilleure sur au moins un des trois.
- **Durée** : mesurée **en secondes** (`fenetre_s`, 120 s par défaut), et non
  plus en nombre de requêtes — interface imposée par le code fourni et ses
  tests d'acceptance (voir `../pilotage/fenetre-glissante-seuils.md`,
  révisé, pour la justification du changement).
- **Si critères non tenus** : la promotion **n'a pas lieu** (pas de passage au
  palier suivant), voire déclenche un rollback si un seuil critique est franchi.

→ Voir `../pilotage/canary.md` (révisé).
