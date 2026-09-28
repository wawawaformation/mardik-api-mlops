# Chaîne LLMOps (chantier 1, point 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `eval/run_eval.py::evaluer`, `ops/deploy.py` (`publier`, `deployer_canary`, `promouvoir`, `rollback`), and the four GitHub Actions workflows (`ci.yml`, `revue.yml`, `gate.yml`, `cd-main.yml`) that replace the monolithic `.github/workflows/llmops.yml` template, implementing the two-tag gate mechanism (`revue-ok`/`eval-ok`) decided in `conception_figee/chantier1_llmops/gel-eval-avant-fusion.md`.

**Architecture:** `evaluer()` runs the 12-contract eval corpus through the already-implemented `analyser_v1`/`analyser_v2` (chosen by `bundle.strategie`), scores recall per contract against `eval/attendus.jsonl`, and produces a `Rapport`. `ops/deploy.py`'s four functions manipulate only the local file-based registry (`ops/registry/index.json` + `journal.jsonl`) — no live traffic routing (that's `app/gateway.py`, chantier 2, out of scope). The four workflows split by trigger/responsibility: `ci.yml` (fast, mocked, every branch), `revue.yml` (posts `revue-ok/<sha>` on approval by a dedicated review account), `gate.yml` (posts `eval-ok/<sha>` after a real-model evaluation, triggered by a `gate/<sha7>` tag push), `cd-main.yml` (build image, publish, canary 10% — on push to `main`, which only happens fast-forward after both tags are verified).

**Tech Stack:** Python 3.11, `uv`, `pytest`, FastAPI (already in place), GitHub Actions, Docker/`ghcr.io`.

## Global Constraints

- Scope: `eval/run_eval.py::evaluer`, `ops/deploy.py::publier/deployer_canary/promouvoir/rollback`. Out of scope: `ops/deploy.py::surveiller`, `app/gateway.py` — do not implement either.
- Note formula: simple recall per contract (as documented in the `eval/run_eval.py` stub), **not** the micro-F1 split from `conception_figee/chantier1_llmops/note-evaluation.md`. The per-contract `seuil_note` (0.75 short / 0.80 long, already in `eval/attendus.jsonl`) is what prevents a high global average from masking a weak long contract.
- `ops/deploy.py::deployer_canary/promouvoir/rollback` touch only `ops/registry/index.json` and `journal.jsonl` — no network calls, no gateway.
- `CANARY_PERCENT`/`MOCK` stay static in `.env`; `deployer_canary` falls back to `CANARY_PERCENT` (default `10`) only when no explicit `pourcentage` is passed.
- `cd-main.yml` automates only up to the canary at `CANARY_PERCENT`; it never calls `promouvoir` or `rollback` automatically.
- Gate is triggered by a developer pushing a `gate/<sha7>` tag (not `workflow_dispatch`).
- `revue-ok/<sha>` is posted only when the dedicated GitHub account `mardik-relecteur` approves a PR into `main` — never by the developer.
- SemVer bump: patch auto-incremented by default; `[minor]`/`[major]` in the merge commit message on `main` forces that level.
- Follow the existing convention in every file touched by this plan: French docstrings/comments, French domain vocabulary for identifiers (`publier`, `deployer_canary`, `evaluer`, `contrat`, `attendus`...). Match the file you're editing — don't introduce English identifiers into `eval/run_eval.py` or `ops/deploy.py`.
- No test written in this plan may touch `app/gateway.py` or `ops/deploy.py::surveiller` — those stay `NotImplementedError`.
- Full reference: `docs/superpowers/specs/2026-09-22-chaine-llmops-design.md`.

---

## File Structure

- Modify `eval/run_eval.py` — implement `evaluer()` (Task 2). New imports only, no new file.
- Modify `ops/deploy.py` — implement `publier`, `deployer_canary`, `promouvoir`, `rollback`, add `prochaine_version` (Tasks 1, 3, 4).
- Create `tests/unit/test_deploy.py` — unit tests for `prochaine_version`, `deployer_canary`, `promouvoir`, `rollback` (Tasks 1, 4).
- Create `tests/unit/test_run_eval.py` — unit tests for `evaluer`'s per-contract safeguard and history logging (Task 2).
- Create `.github/workflows/ci.yml`, `.github/workflows/revue.yml`, `.github/workflows/gate.yml`, `.github/workflows/cd-main.yml` (Tasks 5-8).
- Delete `.github/workflows/llmops.yml` (Task 5) — replaced by the four files above.
- Modify `Makefile` — `ci:` target's stale reference to `llmops.yml` (Task 5).

---

### Task 1: `ops.deploy.prochaine_version`

**Files:**

- Modify: `ops/deploy.py` (add function after `_commit_courant`, add `import os` to the import block)
- Test: `tests/unit/test_deploy.py` (new file)

**Interfaces:**

- Produces: `prochaine_version(bump: str = "patch", registry: Registry | None = None) -> str` — reads `registry.versions()` (already SemVer-sorted by `Registry`), bumps the highest one. Raises `ValueError` on an unknown `bump`. Used by Task 8 (`cd-main.yml`).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_deploy.py`:

```python
"""Tests unitaires — ops/deploy.py (publier/canary/promotion/rollback,
sans app/gateway.py ni surveiller, hors périmètre du point 3)."""
from __future__ import annotations

import pytest


def test_prochaine_version_patch_par_defaut(registry):
    from ops.deploy import prochaine_version

    assert prochaine_version(registry=registry) == "v1.0.1"


def test_prochaine_version_minor(registry):
    from ops.deploy import prochaine_version

    assert prochaine_version("minor", registry=registry) == "v1.1.0"


def test_prochaine_version_major(registry):
    from ops.deploy import prochaine_version

    assert prochaine_version("major", registry=registry) == "v2.0.0"


def test_prochaine_version_bump_invalide(registry):
    from ops.deploy import prochaine_version

    with pytest.raises(ValueError):
        prochaine_version("oups", registry=registry)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `MOCK=on uv run pytest -q tests/unit/test_deploy.py -v`
Expected: FAIL — `ImportError: cannot import name 'prochaine_version'`

- [ ] **Step 3: Implement `prochaine_version`**

In `ops/deploy.py`, add `import os` to the import block (currently `argparse, subprocess, sys, time, typing.Any`), then add this function right after `_commit_courant`:

```python
def prochaine_version(bump: str = "patch", registry: Registry | None = None) -> str:
    """Calcule la prochaine version SemVer à partir de la dernière du registre.

    ``bump`` : ``"patch"`` (défaut, auto-incrémenté à chaque build validé),
    ``"minor"`` ou ``"major"`` (montés manuellement, cf. versionnage.md).
    """
    reg = registry or Registry()
    versions = reg.versions()
    if not versions:
        return "v1.0.0"
    major, minor, patch = (int(x) for x in versions[-1].lstrip("v").split("."))
    if bump == "major":
        major, minor, patch = major + 1, 0, 0
    elif bump == "minor":
        minor, patch = minor + 1, 0
    elif bump == "patch":
        patch += 1
    else:
        raise ValueError(f"bump invalide : {bump!r} (attendu patch/minor/major)")
    return f"v{major}.{minor}.{patch}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `MOCK=on uv run pytest -q tests/unit/test_deploy.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ops/deploy.py tests/unit/test_deploy.py
git commit -m "feat(deploy): add prochaine_version for SemVer patch/minor/major bump"
```

---

### Task 2: `eval.run_eval.evaluer`

**Files:**

- Modify: `eval/run_eval.py` (implement `evaluer`, add imports)
- Test: `tests/unit/test_run_eval.py` (new file)
- Verify (not modify): `tests/acceptance/test_chaine.py::test_etiquetage_version_apres_gate`, `test_gate_evaluation_note_par_version`

**Interfaces:**

- Consumes: `app.api_v1.analyser_v1(texte: str, client: LLMClient, telemetry: Telemetry) -> ReponseAnalyseV1` (`.clauses: list[str]`); `app.api_v2.analyser_v2(texte: str, client: LLMClient, telemetry: Telemetry) -> ReponseAnalyseV2` (`.clauses: list[ClauseV2]`, each with `.type: str`); `app.llm_client.LLMClient(bundle)`, `LLMClient.cout_eur`; `app.telemetry.build_telemetry(span_exporter=..., metrics_path=...) -> Telemetry`, `Telemetry.metriques.lire() -> list[Mesure]` (`Mesure.cout_eur`); `charger_bundle`, `charger_attendus`, `_p95` (already defined in this file); `ops.registry.Registry`.
- Produces: `evaluer(version, *, n_essais=None, seuil=0.75, latence_max_ms=8000.0, cout_max_eur=0.15, contrats=DOSSIER_CONTRATS, attendus=CHEMIN_ATTENDUS, registry=None, telemetry=None, sous_ensemble=None, historique=CHEMIN_HISTORIQUE) -> Rapport`. Used by Task 3 (`ops.deploy.publier`) and by `gate.yml` (Task 7) via `python -m eval.run_eval`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_run_eval.py`:

```python
"""Tests unitaires — eval/run_eval.py::evaluer (formule de note = rappel,
garde-fou seuil_note par contrat). Les tests d'acceptance fournis
(tests/acceptance/test_chaine.py) couvrent déjà le chemin heureux sur les
12 contrats ; ces tests ciblent le comportement de garde-fou."""
from __future__ import annotations

import json


def test_passe_faux_si_un_contrat_sous_son_seuil(tmp_path, historique):
    from eval.run_eval import charger_attendus, evaluer

    item = dict(charger_attendus()["c01"])
    item["seuil_note"] = 0.99  # aucune réponse MOCK réaliste n'atteint 99 % de rappel
    chemin_attendus = tmp_path / "attendus.jsonl"
    chemin_attendus.write_text(json.dumps(item, ensure_ascii=False) + "\n", encoding="utf-8")

    rapport = evaluer(
        "v1", seuil=0.1, sous_ensemble=["c01"], attendus=chemin_attendus, historique=historique
    )

    assert rapport.par_contrat["c01"]["seuil_note"] == 0.99
    assert rapport.passe is False
    assert any("c01" in motif for motif in rapport.motifs)


def test_historique_recoit_une_ligne_par_appel(historique):
    from eval.run_eval import evaluer

    evaluer("v1", sous_ensemble=["c01"], historique=historique)
    evaluer("v1", sous_ensemble=["c01"], historique=historique)

    lignes = historique.read_text(encoding="utf-8").strip().splitlines()
    assert len(lignes) == 2
    assert json.loads(lignes[0])["version"] == "v1.0.0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `MOCK=on uv run pytest -q tests/unit/test_run_eval.py -v`
Expected: FAIL — `NotImplementedError: eval.run_eval.evaluer — le gate d'évaluation`

- [ ] **Step 3: Implement `evaluer`**

In `eval/run_eval.py`, extend the import block:

```python
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.api_v1 import analyser_v1
from app.api_v2 import analyser_v2
from app.llm_client import Bundle, LLMClient
from app.telemetry import NoopSpanExporter, Telemetry, build_telemetry
from ops.registry import MOTIF_VERSION, Registry
```

Add a private helper right before `evaluer` (a throwaway `Telemetry` so eval runs never write to the production `ops/metrics.jsonl` or spam the console with spans):

```python
def _telemetry_jetable() -> Telemetry:
    chemin = Path(tempfile.mkdtemp()) / "metrics.jsonl"
    return build_telemetry(span_exporter=NoopSpanExporter(), metrics_path=chemin)
```

Replace the body of `evaluer`:

```python
def evaluer(
    version: str,
    *,
    n_essais: int | None = None,
    seuil: float = 0.75,
    latence_max_ms: float = 8000.0,
    cout_max_eur: float = 0.15,
    contrats: Path = DOSSIER_CONTRATS,
    attendus: Path = CHEMIN_ATTENDUS,
    registry: Registry | None = None,
    telemetry: Telemetry | None = None,
    sous_ensemble: list[str] | None = None,
    historique: Path | None = CHEMIN_HISTORIQUE,
) -> Rapport:
    bundle = charger_bundle(version, registry)
    client = LLMClient(bundle)
    tel = telemetry or _telemetry_jetable()
    essais = n_essais or int(bundle.parametres.get("essais_eval", 1))
    attendus_par_contrat = charger_attendus(attendus)
    ids = sous_ensemble or sorted(attendus_par_contrat)

    par_contrat: dict[str, dict[str, Any]] = {}
    toutes_latences: list[float] = []
    tous_couts: list[float] = []

    for cid in ids:
        item = attendus_par_contrat[cid]
        texte = (contrats / f"{cid}.txt").read_text(encoding="utf-8")
        attendues = set(item["clauses_attendues"])
        notes_essais: list[float] = []
        trouvees_dernier: list[str] = []
        latence_dernier = 0.0
        cout_dernier = 0.0
        for _ in range(essais):
            debut = time.perf_counter()
            if bundle.strategie == "monolithique":
                trouvees_dernier = analyser_v1(texte, client, tel).clauses
            else:
                trouvees_dernier = [c.type for c in analyser_v2(texte, client, tel).clauses]
            latence_dernier = (time.perf_counter() - debut) * 1000
            mesures = tel.metriques.lire()
            cout_dernier = mesures[-1].cout_eur if mesures else 0.0
            trouvees_pertinentes = set(trouvees_dernier) & attendues
            notes_essais.append(len(trouvees_pertinentes) / len(attendues) if attendues else 1.0)

        note_contrat = sum(notes_essais) / len(notes_essais)
        seuil_note = float(item.get("seuil_note", seuil))
        par_contrat[cid] = {
            "note": note_contrat,
            "seuil_note": seuil_note,
            "passe": note_contrat >= seuil_note,
            "trouvees": trouvees_dernier,
            "manquantes": sorted(attendues - set(trouvees_dernier)),
            "latence_ms": latence_dernier,
            "cout_eur": cout_dernier,
        }
        toutes_latences.append(latence_dernier)
        tous_couts.append(cout_dernier)

    note_globale = sum(c["note"] for c in par_contrat.values()) / len(par_contrat)
    latence_p95 = _p95(toutes_latences)
    cout_moyen = sum(tous_couts) / len(tous_couts) if tous_couts else 0.0

    motifs: list[str] = []
    if note_globale < seuil:
        motifs.append(f"note globale {note_globale:.3f} < seuil {seuil}")
    for cid, c in par_contrat.items():
        if not c["passe"]:
            motifs.append(f"{cid} note {c['note']:.3f} < seuil {c['seuil_note']}")
    if latence_p95 >= latence_max_ms:
        motifs.append(f"latence P95 {latence_p95:.0f} ms >= {latence_max_ms} ms")
    if cout_moyen >= cout_max_eur:
        motifs.append(f"coût moyen {cout_moyen:.4f} € >= {cout_max_eur} €")

    rapport = Rapport(
        version=bundle.version,
        date=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        essais=essais,
        note=note_globale,
        par_contrat=par_contrat,
        latence_p95_ms=latence_p95,
        cout_moyen_eur=cout_moyen,
        passe=not motifs,
        motifs=motifs,
        seuil=seuil,
    )
    if historique is not None:
        historique.parent.mkdir(parents=True, exist_ok=True)
        with historique.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rapport.to_dict(), ensure_ascii=False) + "\n")
    return rapport
```

- [ ] **Step 4: Run the new unit tests**

Run: `MOCK=on uv run pytest -q tests/unit/test_run_eval.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the existing acceptance tests this unblocks**

Run: `MOCK=on uv run pytest -q tests/acceptance/test_chaine.py::test_gate_evaluation_note_par_version tests/acceptance/test_chaine.py::test_etiquetage_version_apres_gate -v`
Expected: `test_gate_evaluation_note_par_version` PASSES. `test_etiquetage_version_apres_gate` still FAILS at this point — it also calls `ops.deploy.publier`, not implemented until Task 3. Confirm the failure is now inside `publier` (`NotImplementedError`), not inside `evaluer`.

- [ ] **Step 6: Full unit + integration regression check**

Run: `MOCK=on uv run pytest -q tests/unit tests/integration`
Expected: all pass (no regression on v1/v2 pipeline or bundle tests).

- [ ] **Step 7: Commit**

```bash
git add eval/run_eval.py tests/unit/test_run_eval.py
git commit -m "feat(eval): implement the evaluation gate (recall per contract)"
```

---

### Task 3: `ops.deploy.publier`

**Files:**

- Modify: `ops/deploy.py` (implement `publier`)
- Verify (not modify): `tests/acceptance/test_chaine.py::test_etiquetage_version_apres_gate`

**Interfaces:**

- Consumes: `eval.run_eval.evaluer` (Task 2), `ops.registry.Registry.etiqueter/journaliser`, `app.llm_client.Bundle.charger`.
- Produces: `publier(version: str, *, bundle: str = "v2", commit: str | None = None, registry: Registry | None = None, seuil: float = 0.75, rapport: Any | None = None) -> dict[str, Any]` (the manifest). Raises `ErreurDeploiement` if the gate fails. Used by Task 8 (`cd-main.yml`).

- [ ] **Step 1: Run the existing acceptance test to confirm the starting failure**

Run: `MOCK=on uv run pytest -q tests/acceptance/test_chaine.py::test_etiquetage_version_apres_gate -v`
Expected: FAIL — `NotImplementedError: deploy.publier — gate puis étiquetage dans le registre`

- [ ] **Step 2: Implement `publier`**

In `ops/deploy.py`, replace the body of `publier`:

```python
def publier(
    version: str,
    *,
    bundle: str = "v2",
    commit: str | None = None,
    registry: Registry | None = None,
    seuil: float = 0.75,
    rapport: Any | None = None,
) -> dict[str, Any]:
    reg = registry or Registry()
    commit = commit or _commit_courant()
    if rapport is None:
        from eval.run_eval import evaluer

        rapport = evaluer(bundle, seuil=seuil)
    if not rapport.passe:
        raise ErreurDeploiement(
            "gate d'évaluation en échec : " + "; ".join(rapport.motifs)
        )
    manifest = reg.etiqueter(
        version, Bundle.charger(bundle), commit=commit, note_eval=rapport.note
    )
    reg.journaliser("publication", version=version, commit=commit, note_eval=rapport.note)
    return manifest
```

`Bundle` is not yet imported in `ops/deploy.py` (current imports: `argparse`, `subprocess`, `sys`, `time`, `typing.Any`, `app.telemetry.MetricsStore`, `ops.registry.Registry`). Add `from app.llm_client import Bundle` to the import block.

- [ ] **Step 3: Run the acceptance test to verify it passes**

Run: `MOCK=on uv run pytest -q tests/acceptance/test_chaine.py::test_etiquetage_version_apres_gate -v`
Expected: PASS

- [ ] **Step 4: Full unit + acceptance regression check**

Run: `MOCK=on uv run pytest -q tests/unit tests/integration tests/acceptance`
Expected: same pass/fail set as before this task, plus `test_etiquetage_version_apres_gate` now green. `test_promotion_canary_puis_totale` and `test_rollback_en_une_operation` still fail (Task 4 territory, and permanently blocked on `app/gateway.py` regardless).

- [ ] **Step 5: Commit**

```bash
git add ops/deploy.py
git commit -m "feat(deploy): implement publier (gate then registry tag)"
```

---

### Task 4: `ops.deploy.deployer_canary`, `promouvoir`, `rollback`

**Files:**

- Modify: `ops/deploy.py` (implement the three functions, add `import os`)
- Modify: `tests/unit/test_deploy.py` (add tests, created in Task 1)
- Verify (not modify): the registry-only assertions inside `tests/acceptance/test_observabilite.py::test_promotion_canary_puis_totale` and `test_rollback_en_une_operation` (these tests stay red overall — they also exercise `app/gateway.py`, out of scope — but the `ops.deploy` calls inside them must not raise `NotImplementedError` any more)

**Interfaces:**

- Consumes: `ops.registry.Registry.definir_canary/ecrire_index/index/manifest/journaliser`.
- Produces: `deployer_canary(version: str, pourcentage: int | None = None, registry: Registry | None = None) -> dict[str, Any]`; `promouvoir(version: str, registry: Registry | None = None) -> dict[str, Any]`; `rollback(registry: Registry | None = None, motif: str = "manuel") -> dict[str, Any]`. All return `registry.index()`. Not consumed elsewhere in this plan (chantier 2's `app/gateway.py` and `ops/deploy.py::surveiller` will consume them later, out of scope here).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_deploy.py`:

```python
from app.llm_client import Bundle


def _livrer_v2(registry, version="v2.0.0"):
    registry.etiqueter(version, Bundle.charger("v2"), commit="abc1234", note_eval=0.9)
    return version


def test_deployer_canary_pourcentage_par_defaut(registry):
    from ops.deploy import deployer_canary

    _livrer_v2(registry)
    index = deployer_canary("v2.0.0", registry=registry)

    assert index["canary"] == "v2.0.0"
    assert index["canary_percent"] == 10  # CANARY_PERCENT non défini dans les tests -> défaut 10
    assert index["active"] == "v1.0.0"
    assert registry.journal()[-1] == {
        **registry.journal()[-1],
        "evenement": "canary",
        "version": "v2.0.0",
        "pourcentage": 10,
    }


def test_deployer_canary_pourcentage_explicite(registry):
    from ops.deploy import deployer_canary

    _livrer_v2(registry)
    index = deployer_canary("v2.0.0", pourcentage=30, registry=registry)

    assert index["canary"] == "v2.0.0" and index["canary_percent"] == 30


def test_promouvoir(registry):
    from ops.deploy import promouvoir

    _livrer_v2(registry)
    index = promouvoir("v2.0.0", registry=registry)

    assert index["active"] == "v2.0.0"
    assert index["precedente"] == "v1.0.0"
    assert index["canary"] is None and index["canary_percent"] == 0
    assert registry.journal()[-1]["evenement"] == "promotion"


def test_rollback_sans_canary_en_cours(registry):
    from ops.deploy import promouvoir, rollback

    _livrer_v2(registry)
    promouvoir("v2.0.0", registry=registry)

    index = rollback(registry=registry, motif="test")

    assert index["active"] == "v1.0.0"
    assert index["precedente"] == "v2.0.0"
    assert index["canary"] is None
    assert registry.journal()[-1]["evenement"] == "rollback"
    assert registry.journal()[-1]["motif"] == "test"


def test_rollback_avec_canary_en_cours(registry):
    from ops.deploy import deployer_canary, rollback

    _livrer_v2(registry)
    deployer_canary("v2.0.0", pourcentage=20, registry=registry)

    index = rollback(registry=registry)

    assert index["active"] == "v1.0.0"  # inchangé : aucune promotion n'a eu lieu
    assert index["canary"] is None and index["canary_percent"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `MOCK=on uv run pytest -q tests/unit/test_deploy.py -v`
Expected: `test_deployer_canary_*`, `test_promouvoir`, `test_rollback_*` FAIL with `NotImplementedError`. The 4 `prochaine_version` tests from Task 1 still PASS.

- [ ] **Step 3: Implement the three functions**

In `ops/deploy.py`, ensure `import os` is present (added in Task 1), then replace the bodies:

```python
def deployer_canary(
    version: str, pourcentage: int | None = None, registry: Registry | None = None
) -> dict[str, Any]:
    reg = registry or Registry()
    pct = pourcentage if pourcentage is not None else int(os.environ.get("CANARY_PERCENT", "10"))
    reg.definir_canary(version, pct)
    reg.journaliser("canary", version=version, pourcentage=pct)
    return reg.index()


def promouvoir(version: str, registry: Registry | None = None) -> dict[str, Any]:
    reg = registry or Registry()
    reg.manifest(version)  # lève ErreurRegistre si version inconnue
    idx = reg.index()
    precedente = idx.get("active")
    reg.ecrire_index(
        {**idx, "active": version, "precedente": precedente, "canary": None, "canary_percent": 0}
    )
    reg.journaliser("promotion", version=version, precedente=precedente)
    return reg.index()


def rollback(registry: Registry | None = None, motif: str = "manuel") -> dict[str, Any]:
    reg = registry or Registry()
    idx = reg.index()
    avant = {"active": idx.get("active"), "canary": idx.get("canary")}
    if idx.get("canary"):
        idx = {**idx, "canary": None, "canary_percent": 0}
    else:
        idx = {**idx, "active": idx.get("precedente"), "precedente": idx.get("active")}
    reg.ecrire_index(idx)
    apres = {"active": idx.get("active"), "canary": idx.get("canary")}
    reg.journaliser("rollback", motif=motif, avant=avant, apres=apres)
    return reg.index()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `MOCK=on uv run pytest -q tests/unit/test_deploy.py -v`
Expected: all pass (8 tests: 4 from Task 1 + 4 new groups above, count may vary slightly by how pytest enumerates — verify 0 failures).

- [ ] **Step 5: Verify the acceptance tests fail at the expected point (gateway, not deploy)**

Run: `MOCK=on uv run pytest -q tests/acceptance/test_observabilite.py::test_promotion_canary_puis_totale tests/acceptance/test_observabilite.py::test_rollback_en_une_operation -v`
Expected: both still FAIL, but the traceback must now point into `app/gateway.py` (`NotImplementedError: gateway.etat` / `gateway.choisir_version` / `gateway.analyse`), never into `ops/deploy.py`. If a failure still originates in `ops/deploy.py`, that is a regression — fix before moving on.

- [ ] **Step 6: Full regression check**

Run: `MOCK=on uv run pytest -q tests/unit tests/integration tests/acceptance`
Expected: `tests/unit` and `tests/integration` fully green; `tests/acceptance` green except `test_promotion_canary_puis_totale`, `test_rollback_en_une_operation`, `test_journal_derive_et_rollback_automatique` (needs `surveiller`, out of scope) — all three failing inside `app/gateway.py` or `ops/deploy.py::surveiller`, never inside code this plan touches.

- [ ] **Step 7: Commit**

```bash
git add ops/deploy.py tests/unit/test_deploy.py
git commit -m "feat(deploy): implement deployer_canary, promouvoir, rollback (registry only)"
```

---

### Task 5: `.github/workflows/ci.yml` + retire the old template

**Files:**

- Create: `.github/workflows/ci.yml`
- Delete: `.github/workflows/llmops.yml`
- Modify: `Makefile:52` (the `ci:` target's stale echo line)

**Interfaces:**

- Consumes: `uv run ruff check .`, `uv run pytest -q tests/unit tests/integration tests/acceptance` (identical to the current `make ci` steps).
- Produces: nothing consumed by other tasks in this plan — `gate.yml` (Task 7) duplicates the same steps in its own `tests` job rather than calling this workflow, per the design (each workflow is self-contained, matching the QualiCheck reference).

- [ ] **Step 1: Delete the obsolete template**

```bash
git rm .github/workflows/llmops.yml
```

- [ ] **Step 2: Create `.github/workflows/ci.yml`**

```yaml
name: CI

# Lint + tests unitaires/intégration/acceptance, LLM mocké, à chaque push de
# branche. main en est exclue : on n'y pousse jamais directement (fusion
# fast-forward de ce qui a déjà été testé ici et gelé par les deux tags —
# voir conception_figee/chantier1_llmops/gel-eval-avant-fusion.md). Un push
# de tag seul ne déclenche pas ce workflow. Voir gate.yml pour l'évaluation
# réelle et cd-main.yml pour le déploiement.
#
# Équivalent local : `make ci`.

on:
  push:
    branches-ignore:
      - main

permissions:
  contents: read

jobs:
  ci:
    runs-on: ubuntu-latest
    env:
      MOCK: "on"
      DRIFT: "off"
      LLM_PROVIDER: ollama
      LLM_MODEL: modele-ci
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Installer uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.11"

      - name: Installer les dépendances
        run: uv sync

      - name: Linting (ruff)
        run: uv run ruff check .

      - name: Tests unitaires, intégration, acceptance (MOCK=on)
        run: uv run pytest -q tests/unit tests/integration tests/acceptance
```

- [ ] **Step 3: Fix the stale Makefile reference**

In `Makefile`, the `ci:` target currently ends with:

```makefile
	@echo "TODO gate d'évaluation / publication / canary : voir .github/workflows/llmops.yml"
```

Replace that line with:

```makefile
	@echo "Gate d'évaluation / publication / canary : voir .github/workflows/gate.yml et cd-main.yml"
```

- [ ] **Step 4: Validate YAML syntax**

Run: `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text())"`
Expected: no output, exit code 0 (valid YAML — this does not validate GitHub Actions semantics, only syntax).

- [ ] **Step 5: Run the equivalent local command to confirm parity**

Run: `MOCK=on uv run ruff check . && MOCK=on uv run pytest -q tests/unit tests/integration tests/acceptance`
Expected: same pass/fail set as the end of Task 4 (ruff clean; acceptance green except the three gateway/surveiller-dependent tests).

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml Makefile
git commit -m "ci: replace llmops.yml template with a dedicated ci.yml workflow"
```

---

### Task 6: `.github/workflows/revue.yml`

**Files:**

- Create: `.github/workflows/revue.yml`

**Interfaces:**

- Consumes: nothing from earlier tasks (pure git/GitHub tag automation).
- Produces: the `revue-ok/<sha7>` tag on approval — consumed by Task 7's guard step and Task 8's guard step.

- [ ] **Step 1: Create `.github/workflows/revue.yml`**

```yaml
name: Revue — preuve d'approbation

# Pose revue-ok/<sha7> quand mardik-relecteur (compte GitHub dédié à la
# revue, jamais le développeur) approuve une PR vers main, sur le SHA de
# tête de la PR. Auto-revue assumée : le second compte est un mécanisme de
# fraîcheur (le SHA approuvé doit être celui de tête), pas une deuxième
# personne — même principe que le pipeline QualiCheck
# (/projets/QualiCheck/.gitea/workflows/revue.yml), adapté à la vraie
# payload GitHub (review.state == 'approved', review.user.login — sur
# Gitea ces deux champs ont un nom différent, cf. le commentaire de leur
# fichier ; ici on utilise les champs GitHub natifs). Voir
# docs/superpowers/specs/2026-09-22-chaine-llmops-design.md.

on:
  pull_request_review:
    types: [submitted]

jobs:
  revue-ok:
    if: >-
      github.event.review.state == 'approved'
      && github.event.review.user.login == 'mardik-relecteur'
      && github.event.pull_request.base.ref == 'main'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout au SHA relu
        uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
          token: ${{ secrets.CI_TAG_TOKEN }}

      - name: Poser revue-ok sur le SHA relu
        run: |
          SHA="${{ github.event.pull_request.head.sha }}"
          SHA7=$(git rev-parse --short=7 "$SHA")
          if git tag --points-at "$SHA" | grep -q '^revue-ok/'; then
            echo "[ok] revue-ok déjà posé sur $SHA (nouvelle approbation sur le même SHA)"
            exit 0
          fi
          git config user.name "mardik-ci"
          git config user.email "mardik-ci@users.noreply.github.com"
          git tag "revue-ok/$SHA7" "$SHA"
          git push origin "revue-ok/$SHA7"
          echo "[ok] revue-ok/$SHA7 posé sur $SHA"
```

- [ ] **Step 2: Validate YAML syntax**

Run: `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/revue.yml').read_text())"`
Expected: no output, exit code 0.

- [ ] **Step 3: Self-review checklist (no automated test possible for a `pull_request_review`-triggered workflow without a real PR)**

Confirm each item by reading the file back:

- [ ] Trigger is `pull_request_review` / `types: [submitted]`, not `pull_request`.
- [ ] The `if:` guard checks `review.state == 'approved'` (GitHub's actual field — not Gitea's `pull_request_review_approved`), the approver is `mardik-relecteur`, and the PR base branch is `main`.
- [ ] The tag push step is idempotent (checks `git tag --points-at` before creating).
- [ ] `token: ${{ secrets.CI_TAG_TOKEN }}` is used for checkout (needed to push a tag — the default `GITHUB_TOKEN` cannot push if tag protection rules apply, and per the spec this secret is a user-created prerequisite, not something this plan can create).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/revue.yml
git commit -m "ci: add revue.yml to post revue-ok/<sha> on PR approval"
```

---

### Task 7: `.github/workflows/gate.yml`

**Files:**

- Create: `.github/workflows/gate.yml`

**Interfaces:**

- Consumes: `revue-ok/<sha>` tag (Task 6); `eval.run_eval.evaluer` via `python -m eval.run_eval` (Task 2); the `proxy`/`azure-adapter` docker-compose services (already `[FOURNI]`, see `docker-compose.yml:49-71`).
- Produces: the `eval-ok/<sha7>` tag — consumed by Task 8's guard step. Also produces `eval/history.jsonl`, uploaded as a build artifact for inspection.

- [ ] **Step 1: Create `.github/workflows/gate.yml`**

```yaml
name: Gate — tests complets et évaluation réelle

# Déclenché par le push d'un tag gate/<sha7> (par le développeur, quand il
# veut — jamais automatique). 1. refus immédiat si aucun revue-ok/* ne
# pointe sur ce SHA (0 appel LLM payant avant d'être sûr que la revue est
# fraîche) ; 2. lint + tests unitaires/intégration/acceptance mockés
# (needs: dans la même exécution — sans quoi rien n'empêche de poser
# eval-ok sur un commit dont 0b a échoué, cf. le design) ; 3. évaluation
# réelle (vrai modèle Azure, payante) ; 4. pose eval-ok/<sha7>. Tag de
# déclenchement (gate/*) et tag de preuve (eval-ok/*) distincts : la preuve
# n'existe que si tout est vert. Voir
# docs/superpowers/specs/2026-09-22-chaine-llmops-design.md.

on:
  push:
    tags:
      - "gate/*"

permissions:
  contents: read

jobs:
  tests:
    runs-on: ubuntu-latest
    env:
      MOCK: "on"
      DRIFT: "off"
      LLM_PROVIDER: ollama
      LLM_MODEL: modele-ci
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Vérifier la revue (revue-ok sur ce SHA)
        run: |
          if ! git tag --points-at "${{ github.sha }}" | grep -q '^revue-ok/'; then
            echo "[refus] aucun tag revue-ok/* ne pointe sur ${{ github.sha }} : faire approuver la PR avant le gate."
            exit 1
          fi
          echo "[ok] revue-ok présent sur ${{ github.sha }}"

      - name: Installer uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.11"

      - name: Installer les dépendances
        run: uv sync

      - name: Linting (ruff)
        run: uv run ruff check .

      - name: Tests unitaires, intégration, acceptance (MOCK=on)
        run: uv run pytest -q tests/unit tests/integration tests/acceptance

  evaluation:
    needs: tests
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.CI_TAG_TOKEN }}

      - name: Écrire le .env pour le fournisseur Azure réel
        run: |
          cat > .env <<ENVEOF
          LLM_PROVIDER=azure
          LLM_MODEL=${{ secrets.AZURE_LLM_MODEL }}
          AZURE_AI_ENDPOINT=${{ secrets.AZURE_AI_ENDPOINT }}
          AZURE_AI_API_KEY=${{ secrets.AZURE_AI_API_KEY }}
          AZURE_AI_API_VERSION=${{ secrets.AZURE_AI_API_VERSION }}
          LLM_PROXY_URL=http://localhost:8080
          DRIFT=off
          MOCK=off
          CANARY_PERCENT=10
          ENVEOF

      - name: Démarrer le proxy de dérive et l'adaptateur Azure
        run: docker compose up -d --build proxy azure-adapter

      - name: Attendre que le proxy soit prêt
        run: |
          for i in $(seq 1 30); do
            curl -sf http://localhost:8080/_drift && exit 0
            sleep 1
          done
          echo "le proxy n'a pas démarré à temps :"
          docker compose logs proxy azure-adapter
          exit 1

      - name: Installer uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.11"

      - name: Installer les dépendances
        run: uv sync

      - name: Gate d'évaluation (vrai modèle, v2, seuil 0.75)
        env:
          LLM_PROVIDER: azure
          LLM_PROXY_URL: http://localhost:8080
          MOCK: "off"
        run: uv run python -m eval.run_eval --version v2 --seuil 0.75

      - name: Publier eval/history.jsonl en artefact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: eval-history-${{ github.sha }}
          path: eval/history.jsonl

      - name: Poser eval-ok sur ce SHA
        run: |
          SHA7=$(git rev-parse --short=7 "${{ github.sha }}")
          if git tag --points-at "${{ github.sha }}" | grep -q '^eval-ok/'; then
            echo "[ok] eval-ok déjà posé sur ${{ github.sha }} (gate relancé après un succès)"
            exit 0
          fi
          git config user.name "mardik-ci"
          git config user.email "mardik-ci@users.noreply.github.com"
          git tag "eval-ok/$SHA7" "${{ github.sha }}"
          git push origin "eval-ok/$SHA7"
          echo "[ok] eval-ok/$SHA7 posé sur ${{ github.sha }}"
```

- [ ] **Step 2: Validate YAML syntax**

Run: `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/gate.yml').read_text())"`
Expected: no output, exit code 0.

- [ ] **Step 3: Self-review checklist**

- [ ] `evaluation` has `needs: tests` and both jobs run against the exact same `github.sha` (implicit — same workflow run).
- [ ] The `tests` job's guard step fails the whole run (`exit 1`) before any Azure secret is touched if `revue-ok` is missing.
- [ ] `.env` is written from GitHub secrets only, matching the exact variable names in `.env.example` (`AZURE_AI_ENDPOINT`, `AZURE_AI_API_KEY`, `AZURE_AI_API_VERSION`, `LLM_MODEL`) plus `LLM_PROXY_URL=http://localhost:8080` (the published port of the `proxy` service in `docker-compose.yml:49-61`).
- [ ] The `eval-ok` tag push is idempotent, mirrors `revue.yml`'s pattern exactly.
- [ ] `--seuil 0.75` matches the conception decision for the global note threshold (per-contract 0.75/0.80 split lives in `eval/attendus.jsonl`, read automatically by `evaluer`).

- [ ] **Step 4: Note the manual verification this task cannot complete**

This workflow cannot be exercised end-to-end without the prerequisites listed in the spec's "Prérequis hors code" section (the `mardik-relecteur` account, `CI_TAG_TOKEN`, `AZURE_*`/`AZURE_LLM_MODEL` repo secrets, tag protection rules). Record in the plan's final report that a real run against a pushed `gate/<sha7>` tag is still needed once those exist — this is expected, not a defect of this task.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/gate.yml
git commit -m "ci: add gate.yml — real-model evaluation gated by revue-ok, posts eval-ok"
```

---

### Task 8: `.github/workflows/cd-main.yml`

**Files:**

- Create: `.github/workflows/cd-main.yml`

**Interfaces:**

- Consumes: `revue-ok`/`eval-ok` tags (Tasks 6, 7); `ops.deploy.prochaine_version` (Task 1); `ops.deploy.publier`, `ops.deploy.deployer_canary` (Tasks 3, 4); `Dockerfile` (already `[FOURNI]`, builds the single shared image).
- Produces: a `ghcr.io` image tag, a new entry in `ops/registry/`, and an updated `ops/registry/index.json` with a 10% canary — nothing else in this plan consumes these; they're the deliverable of chantier 1 point 3.

- [ ] **Step 1: Create `.github/workflows/cd-main.yml`**

```yaml
name: CD — main

# Se déclenche sur push vers main, qui n'arrive qu'en fast-forward strict
# une fois que le SHA de tête porte revue-ok/<sha> et eval-ok/<sha> (cf.
# conception_figee/chantier1_llmops/gel-eval-avant-fusion.md — la garantie
# vient de la comparaison de SHA ci-dessous, pas d'un réglage GitHub).
# main ne rejoue aucun gate : build -> publication -> canary 10 % seulement.
# Pas de promotion ni de rollback automatiques (chantier 2, surveiller()
# hors périmètre). Voir
# docs/superpowers/specs/2026-09-22-chaine-llmops-design.md.

on:
  push:
    branches: [main]

concurrency:
  group: main-deploy
  cancel-in-progress: false

permissions:
  contents: read
  packages: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      LLM_PROVIDER: azure
      LLM_PROXY_URL: http://localhost:8080
      DRIFT: "off"
      CANARY_PERCENT: "10"
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Vérifier les preuves de revue et de gate
        run: |
          TAGS=$(git tag --points-at "${{ github.sha }}")
          echo "$TAGS" | grep -q '^revue-ok/' || { echo "[refus] aucun revue-ok/* sur ${{ github.sha }}"; exit 1; }
          echo "$TAGS" | grep -q '^eval-ok/'  || { echo "[refus] aucun eval-ok/* sur ${{ github.sha }}"; exit 1; }
          echo "[ok] revue-ok et eval-ok présents sur ${{ github.sha }}"

      - name: Installer uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.11"

      - name: Installer les dépendances
        run: uv sync

      - name: Écrire le .env pour le fournisseur Azure réel
        run: |
          cat > .env <<ENVEOF
          LLM_PROVIDER=azure
          LLM_MODEL=${{ secrets.AZURE_LLM_MODEL }}
          AZURE_AI_ENDPOINT=${{ secrets.AZURE_AI_ENDPOINT }}
          AZURE_AI_API_KEY=${{ secrets.AZURE_AI_API_KEY }}
          AZURE_AI_API_VERSION=${{ secrets.AZURE_AI_API_VERSION }}
          LLM_PROXY_URL=http://localhost:8080
          DRIFT=off
          CANARY_PERCENT=10
          ENVEOF

      - name: Démarrer le proxy de dérive et l'adaptateur Azure
        run: docker compose up -d --build proxy azure-adapter

      - name: Attendre que le proxy soit prêt
        run: |
          for i in $(seq 1 30); do
            curl -sf http://localhost:8080/_drift && exit 0
            sleep 1
          done
          echo "le proxy n'a pas démarré à temps :"
          docker compose logs proxy azure-adapter
          exit 1

      - name: Calculer la prochaine version
        id: version
        run: |
          BUMP=patch
          MESSAGE=$(git log -1 --pretty=%B "${{ github.sha }}")
          if echo "$MESSAGE" | grep -q '\[major\]'; then BUMP=major; fi
          if echo "$MESSAGE" | grep -q '\[minor\]'; then BUMP=minor; fi
          VERSION=$(uv run python -c "from ops.deploy import prochaine_version; print(prochaine_version('$BUMP'))")
          echo "version=$VERSION" >> "$GITHUB_OUTPUT"
          echo "[ok] prochaine version : $VERSION (bump=$BUMP)"

      - name: Connexion au registre GitHub (ghcr.io)
        run: echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u "${{ github.actor }}" --password-stdin

      - name: Construire l'image
        run: docker build -t "ghcr.io/${{ github.repository }}:${{ steps.version.outputs.version }}" .

      - name: Pousser l'image
        run: docker push "ghcr.io/${{ github.repository }}:${{ steps.version.outputs.version }}"

      - name: Publier la version (gate + étiquetage dans le registre)
        run: uv run python -m ops.deploy publier "${{ steps.version.outputs.version }}" --bundle v2 --seuil 0.75

      - name: Déployer en canary
        run: uv run python -m ops.deploy canary "${{ steps.version.outputs.version }}"
```

- [ ] **Step 2: Validate YAML syntax**

Run: `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/cd-main.yml').read_text())"`
Expected: no output, exit code 0.

- [ ] **Step 3: Self-review checklist**

- [ ] The guard step checks **both** `revue-ok` and `eval-ok` on `github.sha` before anything else runs, before any secret is touched.
- [ ] The `proxy`/`azure-adapter` services are brought up (same pattern as `gate.yml`) before "Publier la version" runs — `publier()`'s internal `evaluer()` call needs the real Azure path, since no `--rapport` is passed on this CLI invocation (the `rapport=` reuse-optimization from the design is a Python-level option on `publier()`, not exposed by `ops/deploy.py::main`'s CLI — running the real gate a second time here is an accepted simplification, not a defect).
- [ ] `docker build`/`docker push` use `ghcr.io/${{ github.repository }}` — the real repository name (`wawawaformation/mardik-api-mlops`) is already all-lowercase, so no lowercase-conversion step is needed (Docker tags reject uppercase; note this as a latent assumption if the repository is ever renamed).
- [ ] No step calls `promouvoir` or `rollback` — confirms the "canary 10% only, no auto-promotion" constraint.

- [ ] **Step 4: Note the manual verification this task cannot complete**

Same as `gate.yml` (Task 7, Step 4): this workflow cannot run end-to-end without the repo secrets and a real push to `main` carrying both tags. Record this as pending manual verification once the prerequisites exist.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/cd-main.yml
git commit -m "ci: add cd-main.yml — build, publish, canary 10% on push to main"
```

---

## Final Verification (after all 8 tasks)

- [ ] Run: `MOCK=on uv run pytest -q` (full suite)
  Expected: `tests/unit` and `tests/integration` fully green. `tests/acceptance` green except `test_promotion_canary_puis_totale`, `test_rollback_en_une_operation`, `test_journal_derive_et_rollback_automatique` — all three failing strictly inside `app/gateway.py` or `ops/deploy.py::surveiller`.
- [ ] Run: `uv run ruff check .`
  Expected: clean.
- [ ] Confirm `.github/workflows/` contains exactly `ci.yml`, `revue.yml`, `gate.yml`, `cd-main.yml` — `llmops.yml` is gone.
- [ ] Update `TODO.md`: mark `eval/run_eval.py::evaluer`, the four `ops/deploy.py` functions, and `.github/workflows/llmops.yml` (now split) as done; note the three still-red acceptance tests as expected (chantier 2, not a regression).
- [ ] Update `MEMORY.md`: record that chantier 1 point 3 is code-complete except `app/gateway.py`/`surveiller` (chantier 2), and that the workflows are unverified end-to-end pending the manual GitHub prerequisites (bot account, secrets, tag protection).
- [ ] Update `CHANGELOG.md` with a dated entry summarizing what was implemented.
