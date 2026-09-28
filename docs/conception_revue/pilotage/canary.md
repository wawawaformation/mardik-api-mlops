# Déploiement canary — mécanique de promotion (révisé)

> Version révisée dans `mardik-api-mlops/docs/conception_revue/`, suite à la
> révision de `fenetre-glissante-seuils.md` (fenêtre temporelle, et non plus
> en nombre de requêtes). Document original : `conception/pilotage/canary.md`
> (dépôt `mardik_nouvelle_version`, non modifié). Statut : décisions
> provisoires, à calibrer au chantier 2.

## Principe

La v2 est déployée progressivement, pilotée par les métriques. La bascule est
réversible à tout instant (rollback). La v1 reste disponible en permanence.

## Paliers de trafic

```text
10 % → 50 % → 100 %
```

- **10 %** : palier initial, expose la v2 à un trafic limité pour détecter les
  problèmes sans risque majeur.
- **50 %** : palier intermédiaire, compare v1 et v2 sur un trafic significatif.
- **100 %** : généralisation, la v2 sert tout le trafic.

## Fenêtre d'observation — révisée

Mesurée **en secondes** (`fenetre_s`), et non plus en nombre de requêtes —
voir `fenetre-glissante-seuils.md` (dans ce même dossier) pour la
justification du changement : l'interface imposée par les tests
d'acceptance fournis (`ops.deploy.surveiller`, `ops.dashboard.resume`) est
temporelle, et ces tests ne sont pas modifiables.

**Valeur provisoire alignée sur `ops.deploy.surveiller`** : même fenêtre que
la surveillance de rollback — **120 s** par défaut (60 s dans les tests
d'acceptance), avec un minimum de **10 mesures** avant décision.

## Critères de promotion (v2 ≥ v1 + contraintes)

Pour passer au palier suivant, la v2 doit, sur la fenêtre d'observation,
comparée à la v1 sur les **trois mêmes signaux** (latence P95, taux d'erreur,
coût moyen) :

1. respecter les **contraintes client** : P95 < 8 s, coût moyen < 0,15 €,
   taux d'erreur sous le seuil ;
2. n'être **moins bonne sur aucun** des trois signaux (pas de dégradation du
   service par rapport à la v1) ;
3. être **strictement meilleure sur au moins un** des trois signaux — une v2
   simplement à égalité partout n'apporte aucune preuve d'amélioration
   mesurable, et ne suffit pas à justifier la promotion.

Si les critères ne sont pas tenus : la promotion **n'a pas lieu** (pas de
passage au palier suivant), voire déclenche un rollback si un seuil critique
est franchi.

## Décision : auto ou humain

- **Auto** : la promotion est déclenchée automatiquement par le serveur de
  pilotage quand la fenêtre d'observation se conclut et que les critères sont
  tenus.
- **Humain** : possible via l'écran « Actions » (bouton « Promouvoir »), pour
  l'override ou la démo.

Conformément au brief, les deux voies passent **par la chaîne** et sont tracées
au journal.

## Points ouverts

- La valeur exacte de la fenêtre (120 s) est provisoire, à calibrer au
  chantier 2, comme prévu pour les seuils.
- Écart à répercuter dans `conception/pilotage/canary.md` (dépôt
  `mardik_nouvelle_version`) si le dossier de conception d'origine est repris.
