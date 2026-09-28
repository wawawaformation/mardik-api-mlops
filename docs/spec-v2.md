# Spec v2 — chantier 1, point 1

> Synthèse figée du périmètre v2 pour le développement (exigences, contraintes,
> critères d'acceptation). Ce document ne réintroduit aucune décision nouvelle :
> chaque section renvoie vers le document qui fait foi. Pour le détail des
> décisions de conception (découpage, score, versionnage, anonymisation...),
> voir `MEMORY.md`.

## 1. Périmètre

MVP v2 (Must) :

| Élément |
| --- |
| Traiter les contrats longs sans perdre les clauses en fin de document |
| Produire un score de confiance par clause |
| Produire un score de confiance global |
| Maintenir `client_v1` sans modification |
| Respecter P95 < 8 s |
| Respecter un coût moyen < 0,15 € / analyse |
| Maintenir la disponibilité de la v1 |
| Permettre un retour immédiat à une version précédente |
| Comparer v1 et v2 avant généralisation |
| Observer latence, erreurs et confiance en production |

Hors périmètre (Could, explicitement écarté si risque sur les Must) :
traduction anglaise, chatbot sur le contrat.

Source : `conception_figee/intrants/analyse_intrants.md` (MoSCoW provisoire).

## 2. Exigences

- **Contrats longs** : aucune perte de clause en fin de document. La v1 tronque
  à 16 000 caractères (`contexte_max_caracteres`) ; la v2 lève cette limite via
  un découpage structurel + map-reduce. Garde-fou indépendant du LLM : documents
  > 250 000 caractères refusés (413, à ajouter — voir §5).
- **Score de confiance** : par clause (confiance LLM × corroboration entre
  chunks), score global = minimum des clauses.

Source : `MEMORY.md` (racine et `mardik-api-mlops`), décisions actées
2026-09-17/18.

## 3. Contraintes

- P95 < 8 s, y compris sur les contrats longs.
- Coût moyen < 0,15 € / analyse, ~400 contrats/mois (~13/jour).
- v1 jamais interrompue, code jamais modifié ni redéployé.
- Rollback immédiat, une seule opération.

Source : `docs/besoin_client.md`, `MEMORY.md`.

## 4. Architecture

- **Un seul artefact partagé** (image Docker versionnée, contient
  `app/api_v1.py`, `app/api_v2.py`, `app/gateway.py`), **trois containers**
  qui en font tourner chacun une instance avec un rôle différent :
  - **v1** — sert `/v1/analyse` uniquement. Touché le moins possible : le
    code et le contrat de `app/api_v1.py` sont intouchables, mais
    l'exécuter dans son propre container (rôle isolé) n'est pas une
    modification de ce code.
  - **v2** — sert `/v2/analyse` uniquement. Champ libre.
  - **Gateway** — sert `/analyse` et `/gateway/etat`. Appelle
    `analyser_v1`/`analyser_v2` **en process** (appel de fonction Python,
    pas réseau), exactement comme `app/gateway.py` [FOURNI] le décrit : la
    stratégie du bundle actif (`registry.bundle(version).strategie`) décide
    du moteur — `monolithique` → `analyser_v1`, `map_reduce_clauses` →
    `analyser_v2`. Rien à changer dans `gateway.py` pour cette topologie.
  - Chaque container ne démarre que le(s) router(s) correspondant à son
    rôle (v1 seul, v2 seul, ou gateway) à partir du même code source —
    pas trois images différentes à maintenir.
  - Image versionnée : SemVer, artefact Docker immuable poussé sur
    `ghcr.io`, patch auto-incrémenté au build validé — jamais à la fusion.
- **Caddy** — en frontal, seul composant qui route réellement le trafic
  client. Caddyfile régénéré par le serveur de pilotage (chantier 2) à chaque
  changement du registre, `caddy reload` sans coupure.
- C'est le gateway (en process) qu'exercent les tests fournis
  (`test_promotion_canary_puis_totale`, `test_rollback_en_une_operation`) via
  `TestClient` sur `app.main:app` — indépendamment de la topologie de
  déploiement réelle décrite ici.
- Le `docker-compose.yml` actuel (un seul service `app` montant les trois
  routers v1/v2/gateway ensemble) reste un confort de dev/test local ; ce
  n'est pas l'architecture de déploiement canary cible décrite ci-dessus.
- **État de mise en œuvre (2026-09-21, partiel)** : les containers `v2`
  (port hôte 8001, `uvicorn app.main:create_app_v2 --factory`) et
  `serveur_pilotage` (port hôte 8002, squelette `ops/serveur_pilotage.py`)
  existent dans le `docker-compose.yml`, à partir de la même image que `app`.
  Le rôle est porté par la commande uvicorn, pas par une variable
  d'environnement. Restent à faire : container v1 isolé, container gateway et
  Caddy en frontal. Détail :
  `docs/superpowers/specs/2026-09-21-v2-pilotage-containers-design.md`.

Source : `conception_figee/docs/adr/0001-outil-pilotage-maison.md`,
`conception_figee/chantier1_llmops/img/chaine-llmops.png`. Topologie
« un artefact, trois rôles/containers » + rôle de Caddy actée en session
(2026-09-21), adaptée de l'ADR pour respecter la contrainte v1 intouchable
et le contrat de `app/gateway.py` [FOURNI] (dispatch en process, pas HTTP).

## 5. Contrat d'API

- **`/v1/analyse` [FIGÉ]** — `{texte}` → `{clauses: [str], modele, version,
  tronque}` ; 422 (corps invalide), 503 (LLM indisponible).
- **`/v2/analyse` [NOUVEAU]** — `{texte, contrat_id?}` → `{clauses:
  [{type, extrait, confiance, sections}], confiance_globale, modele, version,
  sections, appels_llm, latence_ms, cout_eur}` ; 422, 503. Le 413 (document
  > 250 000 caractères) n'est pas encore dans le stub — à ajouter, sans
  conflit avec les tests fournis (`docs/analyse-coherence-conception.md`).
- **`/analyse` [GATEWAY]** — `{texte, contrat_id?}` → réponse de la version
  tirée par `choisir_version`, en-tête `X-Mardik-Version`.

Détail champ à champ : `conception_figee/chantier1_llmops/openapi.json`,
et les sources de vérité pour le code : `app/api_v1.py`, `app/api_v2.py`,
`app/gateway.py`.

**Écart connu, non résolu** : `openapi.json` (gelé) décrit un corps d'erreur
`{code, message, request_id}` pour 413/422/503. Les tests d'acceptance
fournis (`tests/acceptance/test_chaine.py::test_erreurs_explicites_jamais_de_500`)
exigent seulement `{"detail": "..."}`. Comme pour la fenêtre glissante
(`docs/conception_revue/pilotage/`), les tests fournis font foi ; la révision
formelle de `openapi.json` reste à faire dans `docs/conception_revue/`.

## 6. Critères d'acceptation

Les 10 tests fournis (`tests/acceptance/`, Gherkin français, figés) font foi —
pas de duplication ici, juste le renvoi et un résumé d'une ligne :

**`test_chaine.py`**

| Test | Couvre |
| --- | --- |
| `test_contrat_v2_long_analyse_sans_troncature` | v2 sur contrat long : contrat respecté, clauses de fin trouvées (là où v1 tronque) |
| `test_erreurs_explicites_jamais_de_500` | v2 : erreurs toujours explicites (4xx/5xx + detail), jamais de 500 brut |
| `test_client_v1_fonctionne` | client historique inchangé, avant/pendant/après livraison v2 |
| `test_etiquetage_version_apres_gate` | publication : version étiquetée + manifeste si gate vert, refusée si gate rouge |
| `test_gate_evaluation_note_par_version` | gate d'éval sur les 12 contrats : note par contrat + globale, v2 meilleure que v1 sur les longs |

**`test_observabilite.py`**

| Test | Couvre |
| --- | --- |
| `test_rollback_en_une_operation` | rollback v2→v1 en une opération, sans redémarrage, client v1 continue de fonctionner |
| `test_promotion_canary_puis_totale` | canary 30 % (mélange v1/v2, en-tête `X-Mardik-Version`) puis promotion 100 %, chaque étape journalisée |
| `test_evaluation_enrichie_latence_et_cout` | gate d'éval : rapport inclut P95 et coût moyen, échoue si contrainte non tenue |
| `test_dashboard_par_version` | tableau de bord : trafic, latence P50/P95, taux d'erreur, score moyen, par version |
| `test_journal_derive_et_rollback_automatique` | dérive détectée → rollback automatique → entrée journal datée avec motif et versions avant/après |
