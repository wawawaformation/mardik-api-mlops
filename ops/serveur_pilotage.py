"""Serveur de pilotage — 6 routes du contrat gelé
(``conception_figee/pilotage/openapi-pilotage.json``).

Écart de conception documenté dans
``docs/conception_revue/pilotage/formats-ops.md`` : la conception prévoyait
deux nouveaux fichiers (``ops/registre.json``, ``ops/journal_pilotage.jsonl``,
identifiés par fingerprint). Le code du chantier 1 avait déjà posé
``ops/registry/`` (classe ``Registry`` : ``index.json`` + ``journal.jsonl``,
identifiés par étiquette SemVer) et branché dessus ``app/gateway.py`` /
``ops/deploy.py``. Plutôt que deux sources de vérité à synchroniser, le
serveur de pilotage réutilise ``ops/registry/`` tel quel ; les réponses HTTP
respectent la forme du contrat gelé (mêmes noms de champs), mais les valeurs
en dessous viennent du registre existant.

Hors périmètre de ce module (voir ``TODO.md``) : la régénération du
Caddyfile (aucun container Caddy dans ``docker-compose.yml`` à ce stade) et
le bouclage automatique des seuils ajustables (``PUT /pilotage/regles``) sur
la boucle de décision (``ops.deploy.surveiller`` garde ses propres seuils par
défaut) — les règles sont lues/écrites/tracées, pas encore consommées par la
boucle.

Lancement : ``uvicorn ops.serveur_pilotage:app --host 0.0.0.0 --port 8000``
(service ``serveur_pilotage`` du docker-compose, port hôte 8002).

Extension du contrat (3e boucle de rétroaction, hors contrat gelé) :
``GET /pilotage/enrichissement`` (cas capturés en attente de validation
humaine) et ``POST /pilotage/enrichissement/{cas_id}`` (versement dans le
jeu d'éval après validation par un juriste) — voir ``ops/enrichissement.py``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ops.dashboard import percentile, resume, stores_metriques_par_defaut
from ops.deploy import deployer_canary, promouvoir as deploy_promouvoir, rollback as deploy_rollback
from ops.enrichissement import ErreurEnrichissement, lister as lister_enrichissement, verser as verser_enrichissement
from ops.registry import Registry

router = APIRouter(prefix="/pilotage", tags=["pilotage"])

RACINE_OPS = Path(__file__).resolve().parent
CHEMIN_REGLES_DEFAUT = RACINE_OPS / "regles_pilotage.json"

REGLES_PAR_DEFAUT: list[dict[str, str]] = [
    {
        "signal": "latence_p95",
        "seuil": "> 8 s",
        "retroaction": "rollback",
        "declencheur": "auto",
        "trace": "Journal (auto)",
    },
    {
        "signal": "taux_erreur",
        "seuil": "> 10 %",
        "retroaction": "rollback",
        "declencheur": "auto",
        "trace": "Journal (auto)",
    },
    {
        "signal": "score_faible",
        "seuil": "> 20 % de scores < 0,6",
        "retroaction": "rollback + enrichissement du jeu d'éval",
        "declencheur": "auto",
        "trace": "Journal (auto)",
    },
    {
        "signal": "canary",
        "seuil": "contraintes tenues et v2 ≥ v1",
        "retroaction": "promotion 10 % → 50 % → 100 %",
        "declencheur": "auto_humain",
        "trace": "Journal (auto ou humain)",
    },
]

SEUIL_SCORE_FAIBLE = 0.6
FENETRE_DASHBOARD_S = 300
FENETRE_CANARY_S = 120
MINIMUM_MESURES_CANARY = 10
CONTRAINTE_LATENCE_P95_MS = 8000
CONTRAINTE_COUT_EUR = 0.15
CONTRAINTE_TAUX_ERREUR = 0.10


class AjustementSeuil(BaseModel):
    """Corps de ``PUT /pilotage/regles/{signal}`` — schéma gelé ``AjustementSeuil``."""

    seuil: str
    declencheur: Literal["auto", "humain"]


class Promotion(BaseModel):
    """Corps de ``POST /pilotage/promotion`` — schéma gelé ``Promotion``.

    ``cible_pct`` est le palier canary suivant : 10 → 50 → 100 %, donc seuls
    50 et 100 sont demandables."""

    cible_pct: Literal[50, 100]
    declencheur: Literal["auto", "humain"] | None = None


class VersementEnrichissement(BaseModel):
    """Corps de ``POST /pilotage/enrichissement/{cas_id}`` — extension du
    contrat (voir en-tête du module)."""

    clauses_attendues: list[str]
    par: str


class Rollback(BaseModel):
    """Corps de ``POST /pilotage/rollback`` — schéma gelé ``Rollback``.

    ``signal`` et ``valeur`` documentent la cause quand le rollback est
    automatique ; le contrat ne les rend pas obligatoires."""

    declencheur: Literal["auto", "humain"]
    signal: str | None = None
    valeur: str | None = None


def get_registry() -> Registry:
    return Registry()


# --------------------------------------------------------------- règles


def _chemin_regles() -> Path:
    return Path(os.environ.get("REGLES_PILOTAGE_PATH", CHEMIN_REGLES_DEFAUT))


def _lire_regles() -> list[dict[str, str]]:
    chemin = _chemin_regles()
    if not chemin.exists():
        return [dict(r) for r in REGLES_PAR_DEFAUT]
    return json.loads(chemin.read_text(encoding="utf-8"))


def _ecrire_regles(regles: list[dict[str, str]]) -> None:
    chemin = _chemin_regles()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(regles, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------- répartition


def _repartition(index: dict[str, Any]) -> dict[str, float]:
    """v1/v2 au sens du contrat pilotage : ``v1.0.0`` (code figé) vs tout le
    reste (bundle v2, quel que soit son étiquette SemVer)."""
    if index.get("active") == "v1.0.0":
        canary_pct = index.get("canary_percent") or 0 if index.get("canary") else 0
        return {"v1_pct": 100 - canary_pct, "v2_pct": canary_pct}
    return {"v1_pct": 0, "v2_pct": 100}


# ------------------------------------------------------------------ journal


def _entree_journal(e: dict[str, Any]) -> dict[str, Any]:
    """Reshape une entrée de ``ops/registry/journal.jsonl`` (forme
    ``registry.journaliser``) vers le schéma gelé ``EntreeJournal``."""
    return {
        "id": e.get("id", str(e.get("ts"))),
        "ts": e.get("date", ""),
        "signal": e.get("signal"),
        "valeur": e.get("valeur"),
        "seuil": e.get("seuil"),
        "action": e.get("evenement"),
        "declencheur": e.get("declencheur", "auto"),
        "fingerprint": e.get("version") or e.get("fingerprint"),
    }


# ------------------------------------------------------------------ dashboard


@router.get("/dashboard")
def lire_dashboard(registry: Registry = Depends(get_registry)) -> dict[str, Any]:
    r = resume(fenetre_s=FENETRE_DASHBOARD_S, registry=registry)
    stores = stores_metriques_par_defaut()
    mesures = [m for store in stores for m in store.lire(depuis_s=FENETRE_DASHBOARD_S)]
    sans_erreur = [m for m in mesures if not m.erreur]
    latences = sorted(m.latence_ms for m in sans_erreur)
    couts = [m.cout_eur for m in sans_erreur]
    scores = [m.score for m in sans_erreur if m.score is not None]

    v1_pct = r["par_version"].get("v1.0.0", {}).get("trafic_pct", 0.0)
    v2_pct = round(
        sum(v["trafic_pct"] for k, v in r["par_version"].items() if k != "v1.0.0"), 1
    )

    return {
        "fenetre": {
            # révisé : fenêtre temporelle (fenetre_s), pas un nombre de
            # requêtes — voir docs/conception_revue/pilotage/fenetre-glissante-seuils.md
            "taille_requetes": FENETRE_DASHBOARD_S,
            "requetes_observees": r["total"],
        },
        "latence_p95_ms": percentile(latences, 95) if latences else 0.0,
        "cout_moyen_eur": round(sum(couts) / len(couts), 6) if couts else 0.0,
        "taux_erreur": (
            round((len(mesures) - len(sans_erreur)) / len(mesures), 4) if mesures else 0.0
        ),
        "trafic": {"v1_pct": v1_pct, "v2_pct": v2_pct},
        "distribution_score": {
            "proportion_score_faible": (
                round(sum(1 for s in scores if s < SEUIL_SCORE_FAIBLE) / len(scores), 4)
                if scores
                else 0.0
            ),
            "seuil_faible": SEUIL_SCORE_FAIBLE,
        },
        "evenements_recents": [
            {
                "ts": e.get("date", ""),
                "type": e.get("evenement", ""),
                "message": ", ".join(
                    f"{k}={v}" for k, v in e.items() if k not in {"ts", "date", "evenement"}
                ),
            }
            for e in registry.journal()[-5:]
        ],
    }


# --------------------------------------------------------------------- règles


@router.get("/regles")
def lire_regles() -> dict[str, Any]:
    return {"regles": _lire_regles()}


@router.put("/regles/{signal}")
def ajuster_seuil(
    signal: str, ajustement: AjustementSeuil, registry: Registry = Depends(get_registry)
) -> dict[str, Any]:
    regles = _lire_regles()
    regle = next((r for r in regles if r["signal"] == signal), None)
    if regle is None:
        raise HTTPException(status_code=404, detail=f"signal inconnu : {signal!r}")
    regle["seuil"] = ajustement.seuil
    _ecrire_regles(regles)
    registry.journaliser(
        "ajustement_seuil", signal=signal, seuil=ajustement.seuil, declencheur=ajustement.declencheur
    )
    return regle


# ----------------------------------------------------------------- promotion


def _stats_fenetre(version: str, fenetre_s: float) -> dict[str, Any] | None:
    r = resume(fenetre_s=fenetre_s)
    v = r["par_version"].get(version)
    if v is None or v["requetes"] < MINIMUM_MESURES_CANARY:
        return None
    return {
        "latence_p95_ms": v["latence_p95_ms"],
        "cout_moyen_eur": (v["cout_total_eur"] / v["requetes"]) if v["requetes"] else 0.0,
        "taux_erreur": v["taux_erreur"],
    }


def _evaluer_criteres_promotion(v1: dict[str, Any], v2: dict[str, Any]) -> list[str]:
    """``canary.md`` révisé : contraintes client + v2 jamais moins bonne +
    strictement meilleure sur au moins un signal. Renvoie les motifs de
    refus (liste vide = critères tenus)."""
    motifs: list[str] = []
    if v2["latence_p95_ms"] >= CONTRAINTE_LATENCE_P95_MS:
        motifs.append(f"latence P95 v2 {v2['latence_p95_ms']:.0f}ms ≥ contrainte {CONTRAINTE_LATENCE_P95_MS}ms")
    if v2["cout_moyen_eur"] >= CONTRAINTE_COUT_EUR:
        motifs.append(f"coût moyen v2 {v2['cout_moyen_eur']:.3f}€ ≥ contrainte {CONTRAINTE_COUT_EUR}€")
    if v2["taux_erreur"] >= CONTRAINTE_TAUX_ERREUR:
        motifs.append(f"taux d'erreur v2 {v2['taux_erreur']:.1%} ≥ contrainte {CONTRAINTE_TAUX_ERREUR:.0%}")

    signaux = ("latence_p95_ms", "cout_moyen_eur", "taux_erreur")
    if any(v2[s] > v1[s] for s in signaux):
        pires = [s for s in signaux if v2[s] > v1[s]]
        motifs.append(f"v2 moins bonne que v1 sur : {', '.join(pires)}")
    elif not any(v2[s] < v1[s] for s in signaux):
        motifs.append("v2 n'est strictement meilleure que v1 sur aucun signal")
    return motifs


@router.post("/promotion")
def promouvoir(
    promotion: Promotion, registry: Registry = Depends(get_registry)
) -> dict[str, Any]:
    canary_version, _ = registry.canary()
    if canary_version is None:
        # Rien à décider : pas de canary en cours, donc pas d'entrée au journal.
        raise HTTPException(status_code=409, detail="aucun canary en cours")

    declencheur_refus = promotion.declencheur or "auto"
    v1 = _stats_fenetre("v1.0.0", FENETRE_CANARY_S)
    v2 = _stats_fenetre(canary_version, FENETRE_CANARY_S)
    if v1 is None or v2 is None:
        detail = f"pas assez de mesures sur la fenêtre ({MINIMUM_MESURES_CANARY} min. par version)"
        registry.journaliser(
            "promotion_refusee",
            version=canary_version,
            cible_pct=promotion.cible_pct,
            motif=detail,
            declencheur=declencheur_refus,
            signal="canary",
        )
        raise HTTPException(status_code=409, detail=detail)
    motifs = _evaluer_criteres_promotion(v1, v2)
    if motifs:
        detail = "; ".join(motifs)
        registry.journaliser(
            "promotion_refusee",
            version=canary_version,
            cible_pct=promotion.cible_pct,
            motif=detail,
            declencheur=declencheur_refus,
            signal="canary",
        )
        raise HTTPException(status_code=409, detail=detail)

    declencheur = promotion.declencheur or "auto"
    if promotion.cible_pct == 100:
        index = deploy_promouvoir(canary_version, registry=registry, declencheur=declencheur, signal="canary")
    else:
        index = deployer_canary(
            canary_version, pourcentage=promotion.cible_pct, registry=registry,
            declencheur=declencheur, signal="canary",
        )

    derniere = registry.journal()[-1]
    return {
        "action": "promotion",
        "fingerprint_cible": canary_version,
        "nouvelle_repartition": _repartition(index),
        "ts": derniere.get("date", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        "journal_id": str(derniere.get("ts")),
    }


# ----------------------------------------------------------------- rollback


@router.post("/rollback")
def rollback(demande: Rollback, registry: Registry = Depends(get_registry)) -> dict[str, Any]:
    index = deploy_rollback(
        registry=registry,
        motif=demande.signal or "manuel",
        declencheur=demande.declencheur,
        signal=demande.signal,
        valeur=demande.valeur,
    )
    derniere = registry.journal()[-1]
    return {
        "action": "rollback",
        "fingerprint_cible": index.get("active"),
        "nouvelle_repartition": _repartition(index),
        "ts": derniere.get("date", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        "journal_id": str(derniere.get("ts")),
    }


# ------------------------------------------------------------------- journal


@router.get("/journal")
def lire_journal(
    signal: str | None = None, limite: int = 100, registry: Registry = Depends(get_registry)
) -> dict[str, Any]:
    entrees = [_entree_journal(e) for e in registry.journal()]
    if signal is not None:
        entrees = [e for e in entrees if e["signal"] == signal]
    return {"entrees": entrees[-limite:]}


# ------------------------------------------------------------ enrichissement


@router.get("/enrichissement")
def lire_enrichissement() -> dict[str, Any]:
    return {"cas": lister_enrichissement()}


@router.post("/enrichissement/{cas_id}", status_code=201)
def verser(
    cas_id: str, versement: VersementEnrichissement, registry: Registry = Depends(get_registry)
) -> dict[str, Any]:
    try:
        contrat_id = verser_enrichissement(
            cas_id,
            clauses_attendues=versement.clauses_attendues,
            par=versement.par,
            registry=registry,
        )
    except ErreurEnrichissement as exc:
        message = str(exc)
        statut = 404 if "inconnu" in message else 409
        raise HTTPException(status_code=statut, detail=message)
    return {"contrat_id": contrat_id}


def creer_app_pilotage() -> FastAPI:
    app = FastAPI(title="Mardik — serveur de pilotage", version="1.0.0")
    app.include_router(router)

    # Le client web (client_web/, servi sur son propre port) appelle cette
    # API depuis une autre origine — pas de Caddy en frontal à ce stade pour
    # unifier les origines (voir docs/conception_revue/pilotage/formats-ops.md).
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "PUT", "POST"], allow_headers=["*"]
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        """Hors contrat gelé, non normative : sert le healthcheck du container."""
        return {"status": "ok", "role": "pilotage"}

    @app.exception_handler(NotImplementedError)
    async def _non_implemente(request: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(
            status_code=501,
            content={"detail": f"à implémenter : {exc or 'module non implémenté'}"},
        )

    return app


app = creer_app_pilotage()
