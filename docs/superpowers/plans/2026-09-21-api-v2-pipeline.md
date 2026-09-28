# API v2 (pipeline map-reduce) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `POST /v2/analyse` end-to-end (bundle, pipeline découpage → extraction → consolidation → confiance, orchestration, erreurs explicites) so that contracts of any length are analysed without truncation, without ever touching `/v1`.

**Architecture:** Map-reduce per section. `decouper()` splits the contract into `Section`s by article headers (with a size-based fallback + overlap for oversized sections). `extraire()` makes one LLM call per section (JSON-constrained) producing per-section `Clause`s. `consolider()` merges same-type clauses across sections. `scorer()` computes the composite confidence (`confiance_llm × corroboration`) per clause and the global score (minimum). `api_v2.analyser_v2()` orchestrates the four steps and mirrors the telemetry/error pattern already used by `api_v1.analyser_v1` (untouched, read-only reference).

**Tech Stack:** Python 3.11, FastAPI, Pydantic, pytest, `app.llm_client.LLMClient` (fourni, `MOCK=on` in tests).

## Global Constraints

- Never modify `app/api_v1.py` or its contract — read-only reference for the telemetry/error pattern.
- Never modify `tests/acceptance/*.py`, `tests/conftest.py`, `ops/drift_proxy.py`, `app/llm_client.py`, `app/telemetry.py` — all `[FOURNI]`.
- Score de confiance (décision actée, `conception_figee/chantier1_llmops/score-confiance.md`) : `corroboration = 1.0` si le document ne compte qu'1 section au total, sinon `corroboration = min(1.0, (n-1)/2)` où `n` = nombre de sections où la clause a été vue. `score par clause = confiance_llm × corroboration`. `score global = min(scores des clauses)` (0.0 si aucune clause). **Biais connu, assumé (décision utilisateur, 2026-09-21)** : avec cette formule, une clause vue dans un seul article (le cas normal) obtient une corroboration de 0, donc un score de confiance de 0 — le score global (minimum) est quasi systématiquement 0.0 sur un contrat bien structuré. La formule est implémentée **telle quelle** dans ce plan, sans changement ; `score-confiance.md` prévoit explicitement une « calibration hors-ligne, chantier 2 » si les scores sont systématiquement biaisés — ce biais-là sera corrigé à ce moment, pas ici.
- Découpage cible ~6 000 caractères par section, chevauchement ~250 caractères sur le repli taille fixe (`conception_figee/chantier1_llmops/decoupage-chunking.md`). Trois niveaux implémentés : découpage structurel (articles/préambule/annexes) → **regroupement des blocs consécutifs jusqu'à `taille_max`** (tient le budget d'appels LLM — indispensable, pas un cas rare, voir Task 2) → repli taille fixe avec chevauchement pour un bloc qui dépasse `taille_max` à lui seul.
- Garde-fou document : 413 si `len(texte) > 250_000` (`MEMORY.md`, racine).
- Jamais de 500 brut : toute erreur fournisseur LLM devient un 503 avec `detail` explicite ; toute réponse LLM hors schéma est ignorée pour cette clause, jamais une exception qui remonte.
- Format du corps d'erreur : `{"detail": "..."}`, conforme à ce qu'exigent les tests d'acceptance fournis. **Écart connu et assumé, non traité par ce plan** : `conception_figee/chantier1_llmops/openapi.json` (gelé) décrit un schéma d'erreur `{code, message, request_id}` pour 413/422/503 — en conflit avec les tests fournis, qui font foi (même principe que la révision de la fenêtre glissante, `docs/conception_revue/pilotage/`). À documenter dans `docs/conception_revue/` séparément, hors scope de ce plan.
- TDD unitaire → acceptance : chaque module du pipeline a ses tests unitaires (purs, sans réseau) ; la validation finale passe par les deux tests d'acceptance fournis (`test_contrat_v2_long_analyse_sans_troncature`, `test_erreurs_explicites_jamais_de_500`) plus la suite complète (`make test`) pour vérifier l'absence de régression.

---

### Task 1: Bundle v2 (`models/v2/config.yaml`)

**Files:**

- Modify: `models/v2/config.yaml`
- Test: `tests/unit/test_bundle_v2.py`

**Interfaces:**

- Produces: un bundle chargeable par `Bundle.charger("v2")` avec `strategie == "map_reduce_clauses"`, `schema_sortie` non vide (dict), `parametres["contexte_max_caracteres"] == 6000`. Toutes les tâches suivantes en dépendent (le prompt système, le schéma JSON, la taille de section).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_bundle_v2.py
from __future__ import annotations

from app.llm_client import Bundle


def test_bundle_v2_strategie_map_reduce():
    bundle = Bundle.charger("v2")
    assert bundle.strategie == "map_reduce_clauses"


def test_bundle_v2_schema_sortie_defini():
    bundle = Bundle.charger("v2")
    assert bundle.schema_sortie
    assert "clauses" in bundle.schema_sortie["properties"]


def test_bundle_v2_taille_section():
    bundle = Bundle.charger("v2")
    assert bundle.parametres["contexte_max_caracteres"] == 6000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `MOCK=on uv run pytest tests/unit/test_bundle_v2.py -v`
Expected: 2 of 3 FAIL (`test_bundle_v2_strategie_map_reduce` et `test_bundle_v2_schema_sortie_defini` — `strategie` vaut encore `monolithique`, `schema_sortie` est `None`). `test_bundle_v2_taille_section` PASSE déjà : `contexte_max_caracteres: 6000` est présent dans le stub fourni.

- [ ] **Step 3: Write the bundle**

```yaml
# models/v2/config.yaml — Bundle v2, chantier 1 point 2.
#
# Stratégie map-reduce : un appel LLM par section (découpée par
# app.pipeline.decoupage), sortie JSON contrainte au schéma ci-dessous.

version: v2.0.0
modele: ${LLM_MODEL}
strategie: map_reduce_clauses

prompt: |
  Tu es un assistant juridique. On te donne le titre et le texte d'UNE
  section d'un contrat commercial (pas le contrat entier).

  Identifie les clauses présentes dans cette seule section, parmi
  exactement ces libellés : résiliation, pénalité de retard, confidentialité,
  propriété intellectuelle, limitation de responsabilité, force majeure,
  durée, prix et paiement, non-concurrence, garantie, données personnelles,
  droit applicable, exclusivité, reconduction tacite.

  Pour chaque clause trouvée, cite l'extrait exact du texte qui la justifie
  (pas de paraphrase) et donne ta confiance entre 0 et 1. N'invente jamais un
  extrait absent du texte fourni. Si aucune clause n'est présente dans cette
  section, réponds avec une liste vide.

parametres:
  temperature: 0.2
  max_tokens: 500
  seed: 0                        # fixe, pour un gate stable (point ouvert du stub tranché ici)
  contexte_max_caracteres: 6000
  essais_eval: 1

schema_sortie:
  type: object
  properties:
    clauses:
      type: array
      items:
        type: object
        properties:
          type: {type: string}
          extrait: {type: string}
          confiance: {type: number, minimum: 0, maximum: 1}
        required: [type, extrait, confiance]
  required: [clauses]

cout_par_1k_tokens: 0.002
```

- [ ] **Step 4: Run test to verify it passes**

Run: `MOCK=on uv run pytest tests/unit/test_bundle_v2.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add models/v2/config.yaml tests/unit/test_bundle_v2.py
git commit -m "feat(v2): define the v2 bundle (map-reduce strategy, JSON schema)"
```

---

### Task 2: Découpage (`app/pipeline/decoupage.py`)

**Files:**

- Create: `tests/unit/__init__.py` (vide)
- Create: `tests/unit/pipeline/__init__.py` (vide)
- Modify: `app/pipeline/decoupage.py`
- Test: `tests/unit/pipeline/test_decoupage.py`

**Interfaces:**

- Consumes: rien (fonction pure, pas de dépendance sur les autres tâches).
- Produces: `decouper(texte: str, taille_max: int = 6000) -> list[Section]` où `Section(indice: int, titre: str, texte: str)`. Consommé par Task 5 (orchestration).
- **Trois niveaux implémentés** (contrairement à la v1 du plan qui n'en avait que deux) : découpage structurel (articles/préambule/annexes) → **regroupement des blocs consécutifs jusqu'à `taille_max`** (repli « paragraphes » de `decoupage-chunking.md` : c'est lui qui tient le budget d'appels LLM, pas un cas limite) → repli taille fixe avec chevauchement pour un bloc qui dépasse `taille_max` à lui seul.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/pipeline/test_decoupage.py
from __future__ import annotations

from app.pipeline.decoupage import decouper


def test_regroupe_articles_courts_pour_limiter_les_appels():
    """Plusieurs articles courts tiennent dans une seule section groupée."""
    texte = (
        "Article 1 — Objet\n\nTexte court.\n\n"
        "Article 2 — Durée\n\nTexte court aussi.\n\n"
        "Article 3 — Prix\n\nEncore un texte court.\n"
    )
    sections = decouper(texte, taille_max=6000)
    assert len(sections) == 1
    assert "Article 1 — Objet" in sections[0].titre
    assert "Article 3 — Prix" in sections[0].titre
    assert "Texte court aussi" in sections[0].texte


def test_decoupe_par_article_sans_regroupement_si_gros():
    """Chaque article, seul, tient sous taille_max (pas de repli taille fixe
    déclenché) mais deux articles combinés le dépassent (pas de regroupement
    entre eux). Tailles vérifiées : ~450-480 car. par bloc, taille_max=800 —
    marge large dans les deux sens (bloc seul < 800, deux blocs > 800)."""
    texte = (
        "Préambule\n\n" + ("Contexte du contrat détaillé. " * 15) + "\n\n"
        "Article 1 — Objet\n\n" + ("Objet du contrat détaillé. " * 15) + "\n\n"
        "Article 2 — Durée\n\n" + ("Durée du contrat détaillée. " * 15) + "\n"
    )
    sections = decouper(texte, taille_max=800)
    titres = [s.titre for s in sections]
    assert titres == ["préambule", "Article 1 — Objet", "Article 2 — Durée"]


def test_couvre_tout_le_texte_sans_perte():
    remplissage = "Remplissage. " * 2000
    texte = (
        f"Article 1 — Objet\n\nPremière phrase. {remplissage}\n\n"
        "Article 2 — Fin\n\nDernière phrase avec résiliation.\n"
    )
    sections = decouper(texte, taille_max=6000)
    reconstitue = "".join(s.texte for s in sections)
    assert "Première phrase" in reconstitue
    assert "résiliation" in reconstitue
    assert len(sections) > 1  # le remplissage dépasse largement taille_max


def test_section_trop_longue_est_redecoupee_avec_chevauchement():
    long_texte = "Article 1 — Long\n\n" + "".join(f"Phrase numéro {i}. " for i in range(1000))
    sections = decouper(long_texte, taille_max=1000)
    morceaux_article_1 = [s for s in sections if s.titre == "Article 1 — Long"]
    assert len(morceaux_article_1) > 1
    for s in morceaux_article_1:
        assert len(s.texte) <= 1000 + 260  # taille_max + marge de chevauchement
    # chevauchement réel : la fin du 1er morceau réapparaît au début du 2e
    fin_premier = morceaux_article_1[0].texte[-100:]
    assert any(fin_premier[-30:] in m.texte for m in morceaux_article_1[1:])


def test_indices_croissants():
    texte = "Article 1 — A\n\ntexte a.\n\nArticle 2 — B\n\ntexte b.\n"
    sections = decouper(texte)
    assert [s.indice for s in sections] == list(range(len(sections)))


def test_pas_de_titre_devient_preambule():
    texte = "Juste un paragraphe sans titre d'article, assez court."
    sections = decouper(texte)
    assert len(sections) == 1
    assert sections[0].titre == "préambule"


def test_preambule_explicite_normalise_en_minuscule():
    """Un en-tête « Préambule » (majuscule) explicite est normalisé, comme le cas implicite."""
    texte = "Préambule\n\nLe client souhaite un service.\n"
    sections = decouper(texte)
    assert sections[0].titre == "préambule"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `MOCK=on uv run pytest tests/unit/pipeline/test_decoupage.py -v`
Expected: FAIL with `NotImplementedError`

- [ ] **Step 3: Write the minimal implementation**

```python
# app/pipeline/decoupage.py — remplace le corps du fichier après la docstring
from __future__ import annotations

import re
from dataclasses import dataclass

MOTIF_TITRE = re.compile(
    r"^(Article\s+\d+\s*[—:-].*|Pr[ée]ambule\s*$|Annexe\s+\d+.*|Chapitre\s+.*|"
    r"Titre\s+[IVXLCDM]+.*)$",
    re.IGNORECASE | re.MULTILINE,
)
CHEVAUCHEMENT = 250


@dataclass
class Section:
    indice: int
    titre: str
    texte: str


def decouper(texte: str, taille_max: int = 6000) -> list[Section]:
    limites: list[tuple[int, str]] = []
    for m in MOTIF_TITRE.finditer(texte):
        titre = m.group(0).strip()
        if titre.lower() == "préambule":
            titre = "préambule"  # normalisé, quelle que soit la casse source
        limites.append((m.start(), titre))

    blocs: list[tuple[str, str]] = []
    debut_premier = limites[0][0] if limites else len(texte)
    preambule = texte[:debut_premier].strip()
    if preambule:
        blocs.append(("préambule", preambule))

    for i, (pos, titre) in enumerate(limites):
        fin = limites[i + 1][0] if i + 1 < len(limites) else len(texte)
        corps = texte[pos:fin].strip()
        if corps:
            blocs.append((titre, corps))

    groupes = _regrouper(blocs, taille_max)

    resultat: list[Section] = []
    indice = 0
    for titres, corps in groupes:
        for morceau in _decouper_taille(corps, taille_max):
            resultat.append(Section(indice=indice, titre=" ; ".join(titres), texte=morceau))
            indice += 1
    return resultat


def _regrouper(blocs: list[tuple[str, str]], taille_max: int) -> list[tuple[list[str], str]]:
    """Accumule les blocs consécutifs jusqu'à ~taille_max (repli « paragraphes »
    de decoupage-chunking.md : limite le nombre d'appels LLM, pas un cas rare)."""
    groupes: list[tuple[list[str], str]] = []
    titres_courants: list[str] = []
    texte_courant = ""
    for titre, corps in blocs:
        candidat = f"{texte_courant}\n\n{corps}".strip() if texte_courant else corps
        if texte_courant and len(candidat) > taille_max:
            groupes.append((titres_courants, texte_courant))
            titres_courants = [titre]
            texte_courant = corps
        else:
            titres_courants.append(titre)
            texte_courant = candidat
    if texte_courant:
        groupes.append((titres_courants, texte_courant))
    return groupes


def _decouper_taille(texte: str, taille_max: int) -> list[str]:
    if len(texte) <= taille_max:
        return [texte]
    morceaux: list[str] = []
    debut = 0
    while debut < len(texte):
        fin = min(debut + taille_max, len(texte))
        if fin < len(texte):
            fin_phrase = texte.rfind(". ", debut, fin)
            if fin_phrase > debut:
                fin = fin_phrase + 1
        morceau = texte[debut:fin].strip()
        if morceau:
            morceaux.append(morceau)
        if fin >= len(texte):
            break
        debut = max(debut + 1, fin - CHEVAUCHEMENT)  # garantit une progression (pas de boucle infinie)
    return morceaux
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `MOCK=on uv run pytest tests/unit/pipeline/test_decoupage.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/unit/__init__.py tests/unit/pipeline/__init__.py app/pipeline/decoupage.py tests/unit/pipeline/test_decoupage.py
git commit -m "feat(v2): implement structural + grouped + size-based decoupage with overlap"
```

---

### Task 3: Score de confiance (`app/pipeline/confiance.py`)

**Files:**

- Modify: `app/pipeline/confiance.py`
- Test: `tests/unit/pipeline/test_confiance.py`

**Interfaces:**

- Consumes: `Clause` dataclass déjà définie dans `app/pipeline/confiance.py` (inchangée : `type`, `extrait`, `confiance_llm`, `sections`, `confiance`).
- Produces: `scorer(clauses: list[Clause], nb_sections: int, texte: str = "") -> tuple[list[Clause], float]`. **Écart assumé par rapport à la signature du stub** (`scorer(clauses, texte)`) : la formule actée (`score-confiance.md`) a besoin du nombre total de sections du document, que `texte` seul ne donne pas — `nb_sections` est ajouté. `texte` est **conservé mais inutilisé** : la formule est implémentée telle quelle (décision utilisateur, pas de second signal de corroboration ajouté maintenant — le biais connu de cette formule sur les contrats bien structurés est assumé et sera traité en calibration au chantier 2, pas ici). Aucun test fourni n'appelle `scorer` directement (seul `app/api_v2.py`, notre propre code, l'appelle) : changement sûr. Consommé par Task 6.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/pipeline/test_confiance.py
from __future__ import annotations

from app.pipeline.confiance import Clause, scorer


def test_corroboration_une_seule_section_document_multi_sections():
    clause = Clause(type="résiliation", extrait="...", confiance_llm=0.9, sections=[0])
    clauses, _ = scorer([clause], nb_sections=3)
    assert clauses[0].confiance == 0.0  # n=1, doc multi-sections → corroboration 0


def test_corroboration_deux_sections():
    clause = Clause(type="résiliation", extrait="...", confiance_llm=0.8, sections=[0, 2])
    clauses, _ = scorer([clause], nb_sections=3)
    assert clauses[0].confiance == 0.4  # 0.8 * 0.5


def test_corroboration_trois_sections_ou_plus():
    clause = Clause(type="résiliation", extrait="...", confiance_llm=0.7, sections=[0, 1, 2])
    clauses, _ = scorer([clause], nb_sections=3)
    assert clauses[0].confiance == 0.7  # 0.7 * 1.0


def test_document_une_seule_section_ne_penalise_pas():
    clause = Clause(type="résiliation", extrait="...", confiance_llm=0.9, sections=[0])
    clauses, _ = scorer([clause], nb_sections=1)
    assert clauses[0].confiance == 0.9  # corroboration = 1 (rien à corroborer)


def test_score_global_est_le_minimum():
    a = Clause(type="a", extrait="x", confiance_llm=0.9, sections=[0, 1, 2])
    b = Clause(type="b", extrait="y", confiance_llm=0.9, sections=[0])
    _, score_global = scorer([a, b], nb_sections=3)
    assert score_global == 0.0  # b : 0.9 * 0 = 0, minimum des deux


def test_score_global_zero_sans_clause():
    _, score_global = scorer([], nb_sections=3)
    assert score_global == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `MOCK=on uv run pytest tests/unit/pipeline/test_confiance.py -v`
Expected: FAIL with `NotImplementedError` (et `TypeError` tant que la signature n'a pas changé)

- [ ] **Step 3: Write the minimal implementation**

```python
# app/pipeline/confiance.py — remplace la fonction scorer, garde le dataclass Clause
def scorer(clauses: list[Clause], nb_sections: int, texte: str = "") -> tuple[list[Clause], float]:
    # `texte` conservé pour compatibilité de signature avec le stub fourni,
    # volontairement inutilisé : la formule (score-confiance.md) ne s'appuie
    # que sur nb_sections. Biais connu (score souvent nul sur un contrat bien
    # structuré) assumé, calibration prévue au chantier 2.
    del texte
    for clause in clauses:
        n = len(clause.sections)
        corroboration = 1.0 if nb_sections <= 1 else min(1.0, (n - 1) / 2)
        clause.confiance = clause.confiance_llm * corroboration
    score_global = min((c.confiance for c in clauses), default=0.0)
    return clauses, score_global
```

Also update the function's signature line (`def scorer(clauses: list[Clause], texte: str)`) and the module docstring's contract line to `scorer(clauses: list[Clause], nb_sections: int, texte: str = "") -> tuple[list[Clause], float]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `MOCK=on uv run pytest tests/unit/pipeline/test_confiance.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/confiance.py tests/unit/pipeline/test_confiance.py
git commit -m "feat(v2): implement composite confidence score (llm x corroboration)"
```

---

### Task 4: Consolidation (`app/pipeline/consolidation.py`)

**Files:**

- Modify: `app/pipeline/consolidation.py`
- Test: `tests/unit/pipeline/test_consolidation.py`

**Interfaces:**

- Consumes: `Clause` (Task 3, `app/pipeline/confiance.py`).
- Produces: `consolider(par_section: list[list[Clause]]) -> list[Clause]`. Consommé par Task 5.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/pipeline/test_consolidation.py
from __future__ import annotations

from app.pipeline.confiance import Clause
from app.pipeline.consolidation import consolider


def test_fusionne_meme_type_plusieurs_sections():
    par_section = [
        [Clause(type="résiliation", extrait="courte", confiance_llm=0.7, sections=[0])],
        [Clause(type="résiliation", extrait="un extrait plus long et complet", confiance_llm=0.9, sections=[1])],
    ]
    resultat = consolider(par_section)
    assert len(resultat) == 1
    assert resultat[0].extrait == "un extrait plus long et complet"
    assert resultat[0].confiance_llm == 0.9
    assert resultat[0].sections == [0, 1]


def test_aucun_doublon_de_type():
    par_section = [
        [Clause(type="durée", extrait="a", confiance_llm=0.5, sections=[0])],
        [Clause(type="durée", extrait="b", confiance_llm=0.6, sections=[1])],
        [Clause(type="durée", extrait="c", confiance_llm=0.4, sections=[2])],
    ]
    resultat = consolider(par_section)
    types = [c.type for c in resultat]
    assert len(types) == len(set(types))


def test_ordre_premiere_apparition():
    par_section = [
        [Clause(type="prix et paiement", extrait="a", confiance_llm=0.5, sections=[0])],
        [Clause(type="résiliation", extrait="b", confiance_llm=0.5, sections=[1])],
    ]
    resultat = consolider(par_section)
    assert [c.type for c in resultat] == ["prix et paiement", "résiliation"]


def test_sections_vides_ne_cassent_rien():
    assert consolider([[], []]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `MOCK=on uv run pytest tests/unit/pipeline/test_consolidation.py -v`
Expected: FAIL with `NotImplementedError`

- [ ] **Step 3: Write the minimal implementation**

```python
# app/pipeline/consolidation.py — remplace la fonction consolider
# (Clause est déjà importé au niveau module par le stub : `from app.pipeline.confiance import Clause`)
def consolider(par_section: list[list[Clause]]) -> list[Clause]:
    par_type: dict[str, Clause] = {}
    ordre: list[str] = []
    for clauses_section in par_section:
        for clause in clauses_section:
            existante = par_type.get(clause.type)
            if existante is None:
                par_type[clause.type] = Clause(
                    type=clause.type,
                    extrait=clause.extrait,
                    confiance_llm=clause.confiance_llm,
                    sections=list(clause.sections),
                )
                ordre.append(clause.type)
            else:
                if len(clause.extrait) > len(existante.extrait):
                    existante.extrait = clause.extrait
                existante.confiance_llm = max(existante.confiance_llm, clause.confiance_llm)
                for idx in clause.sections:
                    if idx not in existante.sections:
                        existante.sections.append(idx)
    return [par_type[t] for t in ordre]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `MOCK=on uv run pytest tests/unit/pipeline/test_consolidation.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/consolidation.py tests/unit/pipeline/test_consolidation.py
git commit -m "feat(v2): implement cross-section clause deduplication"
```

---

### Task 5: Extraction (`app/pipeline/extraction.py`)

**Files:**

- Modify: `app/pipeline/extraction.py`
- Test: `tests/unit/pipeline/test_extraction.py`

**Interfaces:**

- Consumes: `Section` (Task 2), `Clause` (Task 3), `LLMClient`/`ReponseLLM`/`ErreurLLM`/`TYPES_CLAUSES` (`app/llm_client.py`, fourni).
- Produces: `extraire(section: Section, client: LLMClient) -> tuple[list[Clause], ReponseLLM]`. Consommé par Task 6.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/pipeline/test_extraction.py
from __future__ import annotations

import pytest

from app.llm_client import Bundle, LLMClient
from app.pipeline.decoupage import Section
from app.pipeline.extraction import extraire


@pytest.fixture
def client_v2(monkeypatch: pytest.MonkeyPatch, tmp_path) -> LLMClient:
    monkeypatch.setenv("MOCK", "on")
    # dossier de fixtures vide et isolé : le test dépend du repli par mots-clés
    # (reponse_de_repli), jamais d'une vraie fixture enregistrée par `make fixtures`
    return LLMClient(Bundle.charger("v2"), fixtures=tmp_path / "fixtures_vides")


def test_extrait_une_clause_via_mots_cles(client_v2: LLMClient):
    section = Section(
        indice=0,
        titre="Article 1 — Résiliation",
        texte="En cas de résiliation anticipée, un préavis de deux mois est requis.",
    )
    clauses, reponse = extraire(section, client_v2)
    assert any(c.type == "résiliation" for c in clauses)
    assert all(c.sections == [0] for c in clauses)
    assert reponse.mock is True


def test_section_sans_clause_renvoie_liste_vide(client_v2: LLMClient):
    section = Section(indice=1, titre="Article 2", texte="Texte neutre sans mot-clé connu.")
    clauses, _ = extraire(section, client_v2)
    assert clauses == []


def test_confiance_hors_bornes_est_ignoree(client_v2: LLMClient, monkeypatch: pytest.MonkeyPatch):
    from app.llm_client import ReponseLLM

    def fausse_reponse(*_args, **_kwargs):
        return ReponseLLM(
            texte='{"clauses": [{"type": "résiliation", "extrait": "x", "confiance": 1.7}]}',
            latence_ms=1.0,
            mock=True,
        )

    monkeypatch.setattr(client_v2, "completer", fausse_reponse)
    section = Section(indice=0, titre="A", texte="peu importe")
    clauses, _ = extraire(section, client_v2)
    assert clauses == []


def test_json_invalide_ne_plante_pas(client_v2: LLMClient, monkeypatch: pytest.MonkeyPatch):
    from app.llm_client import ReponseLLM

    def fausse_reponse(*_args, **_kwargs):
        return ReponseLLM(texte="pas du json", latence_ms=1.0, mock=True)

    monkeypatch.setattr(client_v2, "completer", fausse_reponse)
    section = Section(indice=0, titre="A", texte="peu importe")
    clauses, reponse = extraire(section, client_v2)
    assert clauses == []
    assert reponse.texte == "pas du json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `MOCK=on uv run pytest tests/unit/pipeline/test_extraction.py -v`
Expected: FAIL with `NotImplementedError`

- [ ] **Step 3: Write the minimal implementation**

```python
# app/pipeline/extraction.py — remplace la fonction extraire
def extraire(section: Section, client: LLMClient) -> tuple[list[Clause], ReponseLLM]:
    from app.llm_client import ErreurLLM, TYPES_CLAUSES

    prompt_utilisateur = f"{section.titre}\n\n{section.texte}"
    reponse = client.completer(prompt_utilisateur, json_mode=True)

    clauses: list[Clause] = []
    try:
        data = reponse.json()
    except ErreurLLM:
        return clauses, reponse

    brutes = data.get("clauses", []) if isinstance(data, dict) else []
    types_connus = set(TYPES_CLAUSES)
    for item in brutes:
        if not isinstance(item, dict):
            continue
        type_ = item.get("type")
        extrait = item.get("extrait")
        confiance = item.get("confiance")
        if type_ not in types_connus:
            continue
        if not isinstance(extrait, str) or not extrait.strip():
            continue
        if not isinstance(confiance, (int, float)) or not (0.0 <= confiance <= 1.0):
            continue
        clauses.append(
            Clause(type=type_, extrait=extrait.strip(), confiance_llm=float(confiance), sections=[section.indice])
        )
    return clauses, reponse
```

Move the `from app.llm_client import ErreurLLM, TYPES_CLAUSES` to the top-level imports of the file instead of inline (shown inline above only to make the diff obvious; the committed file should import at module level alongside the existing `from app.llm_client import LLMClient, ReponseLLM`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `MOCK=on uv run pytest tests/unit/pipeline/test_extraction.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/extraction.py tests/unit/pipeline/test_extraction.py
git commit -m "feat(v2): implement per-section LLM extraction with JSON validation"
```

---

### Task 6: Orchestration (`app/api_v2.py`)

**Files:**

- Modify: `app/api_v2.py`
- Test: `tests/unit/test_api_v2_analyser.py`

**Interfaces:**

- Consumes: `decouper` (Task 2), `scorer` (Task 3), `consolider` (Task 4), `extraire` (Task 5), `Mesure`/`Telemetry` (`app/telemetry.py`, fourni), `ErreurLLM` (`app/llm_client.py`, fourni).
- Produces: `analyser_v2(texte: str, client: LLMClient, telemetry: Telemetry) -> ReponseAnalyseV2` (déjà déclarée dans le stub, signature inchangée) et la route `POST /v2/analyse` avec le 413.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_api_v2_analyser.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import api_v2
from app.api_v2 import analyser_v2
from app.llm_client import Bundle, LLMClient
from app.main import create_app
from app.telemetry import Telemetry, build_telemetry
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# Pas de fixture d'environnement ici : l'autouse `environnement` de
# `tests/conftest.py` (MOCK=on, DRIFT=off, LLM_PROVIDER=ollama, LLM_MODEL,
# OTEL_TRACES=off) s'applique déjà à tout `tests/`, y compris `tests/unit/`.


@pytest.fixture
def telemetry(tmp_path) -> Telemetry:
    return build_telemetry(
        span_exporter=InMemorySpanExporter(), metrics_path=tmp_path / "metrics.jsonl", level="INFO"
    )


def test_analyser_v2_sur_contrat_multi_articles(telemetry: Telemetry, tmp_path):
    """Chaque article est assez long pour ne pas tenir dans une seule section
    groupée (taille_max=6000 du bundle v2) : vérifie le multi-appels + la
    consolidation, sans dépendre du nombre exact de sections produites par le
    regroupement (Task 2) — seulement qu'il y en a plus d'une."""
    client = LLMClient(Bundle.charger("v2"), fixtures=tmp_path / "fixtures_vides")
    remplissage = "Contexte additionnel du contrat. " * 150  # ~5 000 car.
    texte = (
        f"Préambule\n\n{remplissage}\n\n"
        f"Article 1 — Confidentialité\n\nLes parties respectent la confidentialité "
        f"des informations. {remplissage}\n\n"
        f"Article 2 — Résiliation\n\nLe contrat peut être résilié moyennant préavis. {remplissage}\n"
    )
    resultat = analyser_v2(texte, client, telemetry)
    assert resultat.sections >= 2
    assert resultat.appels_llm == resultat.sections
    types = {c.type for c in resultat.clauses}
    assert {"confidentialité", "résiliation"} <= types
    assert 0.0 <= resultat.confiance_globale <= 1.0
    assert len(resultat.clauses) == len({c.type for c in resultat.clauses})


def test_route_v2_document_trop_long_413():
    app = create_app()
    client_http = TestClient(app)
    texte_trop_long = "x" * 250_001
    r = client_http.post("/v2/analyse", json={"texte": texte_trop_long})
    assert r.status_code == 413
    assert "detail" in r.json()


def test_route_v2_document_sous_la_limite_ne_declenche_pas_413(tmp_path):
    app = create_app()
    app.dependency_overrides[api_v2.get_telemetry] = lambda: build_telemetry(
        span_exporter=InMemorySpanExporter(), metrics_path=tmp_path / "metrics.jsonl", level="INFO"
    )
    client_http = TestClient(app)
    texte = "Article 1 — Objet\n\n" + ("Texte du contrat. " * 20)
    r = client_http.post("/v2/analyse", json={"texte": texte})
    assert r.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `MOCK=on uv run pytest tests/unit/test_api_v2_analyser.py -v`
Expected: FAIL — `test_analyser_v2_sur_contrat_multi_articles` avec `NotImplementedError` ; `test_route_v2_document_trop_long_413` avec un 501 (le handler `app.main`'s `@app.exception_handler(NotImplementedError)` répond 501, pas 500, mais toujours pas le 413 attendu) ; `test_route_v2_document_sous_la_limite_ne_declenche_pas_413` avec un 501 également

- [ ] **Step 3: Write the minimal implementation**

```python
# app/api_v2.py — imports supplémentaires en haut du fichier
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.llm_client import Bundle, ErreurLLM, LLMClient
from app.pipeline.confiance import Clause, scorer
from app.pipeline.consolidation import consolider
from app.pipeline.decoupage import decouper
from app.pipeline.extraction import extraire
from app.telemetry import Mesure, Telemetry, build_default_telemetry

LIMITE_CARACTERES = 250_000
```

```python
# app/api_v2.py — remplace analyser_v2
def analyser_v2(texte: str, client: LLMClient, telemetry: Telemetry) -> ReponseAnalyseV2:
    bundle = client.bundle
    taille_max = int(bundle.parametres.get("contexte_max_caracteres", 6000))
    debut = time.perf_counter()
    with telemetry.tracer.start_as_current_span("analyse.requete") as span:
        span.set_attribute("mardik.version", bundle.version)
        sections = decouper(texte, taille_max)
        span.set_attribute("mardik.sections", len(sections))

        par_section: list[list[Clause]] = []
        appels_llm = 0
        tokens_total = 0
        cout_total = 0.0
        try:
            for section in sections:
                with telemetry.tracer.start_as_current_span("llm.appel") as span_llm:
                    clauses, reponse = extraire(section, client)
                    span_llm.set_attribute("llm.latence_ms", reponse.latence_ms)
                    span_llm.set_attribute("llm.tokens", reponse.tokens)
                par_section.append(clauses)
                appels_llm += 1
                tokens_total += reponse.tokens
                cout_total += client.cout_eur(reponse)
        except ErreurLLM as exc:
            telemetry.metriques.enregistrer(
                Mesure(
                    ts=time.time(),
                    version=bundle.version,
                    route="/v2/analyse",
                    latence_ms=(time.perf_counter() - debut) * 1000,
                    erreur=True,
                )
            )
            telemetry.logger.error("analyse.echec", version=bundle.version, cause=str(exc))
            raise

        clauses_consolidees = consolider(par_section)
        clauses_notees, confiance_globale = scorer(clauses_consolidees, len(sections), texte)
        latence = (time.perf_counter() - debut) * 1000
        telemetry.metriques.enregistrer(
            Mesure(
                ts=time.time(),
                version=bundle.version,
                route="/v2/analyse",
                latence_ms=latence,
                score=confiance_globale,
                cout_eur=cout_total,
                appels_llm=appels_llm,
                tokens=tokens_total,
                tronque=False,
            )
        )
        telemetry.logger.info(
            "analyse.terminee",
            version=bundle.version,
            latence_ms=round(latence, 1),
            clauses=len(clauses_notees),
            sections=len(sections),
        )
    return ReponseAnalyseV2(
        clauses=[
            ClauseV2(type=c.type, extrait=c.extrait, confiance=round(c.confiance, 3), sections=c.sections)
            for c in clauses_notees
        ],
        confiance_globale=confiance_globale,
        modele=bundle.modele,
        version=bundle.version,
        sections=len(sections),
        appels_llm=appels_llm,
        latence_ms=latence,
        cout_eur=cout_total,
    )
```

```python
# app/api_v2.py — remplace la route
@router.post("/analyse", response_model=ReponseAnalyseV2)
def analyse(
    requete: RequeteAnalyseV2,
    client: LLMClient = Depends(get_client_v2),
    telemetry: Telemetry = Depends(get_telemetry),
) -> ReponseAnalyseV2:
    if len(requete.texte) > LIMITE_CARACTERES:
        raise HTTPException(
            status_code=413,
            detail=f"document trop long ({len(requete.texte)} caractères, max {LIMITE_CARACTERES})",
        )
    try:
        return analyser_v2(requete.texte, client, telemetry)
    except ErreurLLM as exc:
        raise HTTPException(status_code=503, detail=f"fournisseur LLM indisponible : {exc}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `MOCK=on uv run pytest tests/unit/test_api_v2_analyser.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/api_v2.py tests/unit/test_api_v2_analyser.py
git commit -m "feat(v2): orchestrate the map-reduce pipeline behind POST /v2/analyse"
```

---

### Task 7: Full validation (acceptance + no regression)

**Files:**

- Modify: `Makefile` (`ci:` target — add `tests/unit`, currently only runs `tests/integration` + `tests/acceptance`; `testpaths = ["tests"]` in `pyproject.toml` already makes plain `make test` pick up `tests/unit` automatically, `make ci` does not).

**Interfaces:** none.

- [ ] **Step 1: Add `tests/unit` to the local CI target**

```makefile
ci:                 ## l'équivalent local du workflow GitHub (MOCK=on)
	uv run ruff check .
	MOCK=on uv run pytest -q tests/unit
	MOCK=on uv run pytest -q tests/integration
	MOCK=on uv run pytest -q tests/acceptance
	@echo "TODO gate d'évaluation / publication / canary : voir .github/workflows/llmops.yml"
```

- [ ] **Step 2: Run the two acceptance tests this plan targets**

Run: `MOCK=on uv run pytest -v tests/acceptance/test_chaine.py::test_contrat_v2_long_analyse_sans_troncature tests/acceptance/test_chaine.py::test_erreurs_explicites_jamais_de_500`
Expected: 2 passed

- [ ] **Step 3: Run the full test suite (unit + integration + acceptance) to check for regressions**

Run: `MOCK=on uv run pytest -v`
Expected: `test_client_v1_fonctionne` still passes (v1 untouched), all new unit tests pass (Tasks 1-6, 27 tests: 3+7+6+4+4+3), the two v2 acceptance tests pass. Other acceptance tests (gateway/observabilité, gate d'évaluation) stay red — out of scope for this plan.

- [ ] **Step 4: Run `make ci` (lint + unit + integration + acceptance, `MOCK=on`)**

Run: `make ci`
Expected: `ruff check .` clean, `tests/unit` green, `tests/integration` green, `tests/acceptance` shows the 2 new v2 tests green plus the pre-existing `test_client_v1_fonctionne`.

- [ ] **Step 5: Commit the Makefile change**

```bash
git add Makefile
git commit -m "chore: run tests/unit as part of make ci"
```

- [ ] **Step 6: Manual smoke test against the real LLM (optional but recommended)**

Run: `make eval VERSION=v2 ARGS="--essais 1"` is out of scope (gate d'évaluation, point 3) — instead, smoke-test the endpoint directly with `make up` (or the already-running stack) and the Bruno request `v2/Analyse v2 - exemple`, then the `v1/Analyse v1 - demo troncature (texte genere)` body against `/v2/analyse` to eyeball a real long-document response. With a vrai modèle, vérifier en particulier le **nombre d'appels LLM réellement fait** (`appels_llm` dans la réponse) contre l'estimation de `decoupage-chunking.md` (~1 appel / 6 000 car.) — c'est le test de non-régression de B1 en conditions réelles.

- [ ] **Step 7: Commit (if step 6 prompted any fix)**

Only if step 6 revealed a bug — commit the fix with a description of what broke and why. If no fix was needed, no commit for this task.
