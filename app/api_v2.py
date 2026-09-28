"""Contrat ``/v2`` — la nouvelle version.

Contrat (c'est celui que testent ``tests/acceptance/test_chaine.py``
et que consomme la gateway) :

    POST /v2/analyse   {"texte": "<contrat>", "contrat_id": "c07" (optionnel)}
    → 200 {
        "clauses": [{"type": "résiliation", "extrait": "...", "confiance": 0.91,
                     "sections": [3]}, ...],
        "confiance_globale": 0.87,
        "modele": "...", "version": "v2.0.0",
        "sections": 14,            # nombre de sections analysées
        "appels_llm": 14,
        "latence_ms": 5230.4,
        "cout_eur": 0.031
      }
    → 422 corps invalide (détail explicite)
    → 503 fournisseur LLM indisponible (détail explicite)
    Jamais de 500 brut : toute erreur est explicite et journalisée.

Règles :
* aucune troncature : le contrat passe par ``pipeline.decouper`` puis chaque
  section par ``pipeline.extraire`` (map), ``pipeline.consolider`` (reduce),
  et ``pipeline.scorer`` calcule les confiances ;
* la fonction ``analyser_v2(texte, client, telemetry)`` doit exister et être
  réutilisable hors HTTP (le gate d'évaluation l'appelle directement) ;
* chaque requête produit une ``Mesure`` (version, latence, score, coût,
  appels LLM, erreur) dans ``telemetry.metriques`` et des spans
  ``analyse.requete`` → ``llm.appel`` (un par section), comme la v1.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from opentelemetry import context as otel_context
from pydantic import BaseModel, Field

from app.llm_client import Bundle, ErreurLLM, LLMClient, ReponseLLM
from app.pipeline.confiance import Clause, scorer
from app.pipeline.consolidation import consolider
from app.pipeline.decoupage import Section, decouper
from app.pipeline.extraction import extraire
from app.telemetry import Mesure, Telemetry, build_default_telemetry
from ops.enrichissement import capturer

router = APIRouter(prefix="/v2", tags=["v2"])
VERSION_V2 = "v2"
LIMITE_CARACTERES = 250_000
MAX_APPELS_LLM_PARALLELES = 8


class DocumentTropLong(ValueError):
    """Levée par ``analyser_v2`` quand ``texte`` dépasse ``LIMITE_CARACTERES``."""

    def __init__(self, taille: int) -> None:
        self.taille = taille
        super().__init__(f"document trop long ({taille} caractères, max {LIMITE_CARACTERES})")


class RequeteAnalyseV2(BaseModel):
    texte: str = Field(..., min_length=20, description="Texte intégral du contrat")
    contrat_id: str | None = None


class ClauseV2(BaseModel):
    type: str
    extrait: str
    confiance: float
    sections: list[int]


class ReponseAnalyseV2(BaseModel):
    clauses: list[ClauseV2]
    confiance_globale: float
    modele: str
    version: str
    sections: int
    appels_llm: int
    latence_ms: float
    cout_eur: float


def get_bundle_v2() -> Bundle:
    return Bundle.charger(VERSION_V2)


def get_client_v2(bundle: Bundle = Depends(get_bundle_v2)) -> LLMClient:
    return LLMClient(bundle)


def get_telemetry() -> Telemetry:
    return build_default_telemetry()


def _extraire_avec_span(
    section: Section, client: LLMClient, telemetry: Telemetry, parent_ctx: otel_context.Context
) -> tuple[list[Clause], ReponseLLM]:
    """Exécute ``extraire`` dans un thread du pool en rattachant le span
    ``llm.appel`` au span parent ``analyse.requete`` (le contexte OpenTelemetry
    ne traverse pas les threads tout seul)."""
    token = otel_context.attach(parent_ctx)
    try:
        with telemetry.tracer.start_as_current_span("llm.appel") as span_llm:
            clauses, reponse = extraire(section, client)
            span_llm.set_attribute("llm.latence_ms", reponse.latence_ms)
            span_llm.set_attribute("llm.tokens", reponse.tokens)
            span_llm.set_attribute("llm.clauses", len(clauses))
        return clauses, reponse
    finally:
        otel_context.detach(token)


def analyser_v2(texte: str, client: LLMClient, telemetry: Telemetry) -> ReponseAnalyseV2:
    bundle = client.bundle
    if len(texte) > LIMITE_CARACTERES:
        telemetry.metriques.enregistrer(
            Mesure(ts=time.time(), version=bundle.version, route="/v2/analyse", latence_ms=0.0, erreur=True)
        )
        raise DocumentTropLong(len(texte))
    taille_max = int(bundle.parametres.get("contexte_max_caracteres", 6000))
    debut = time.perf_counter()
    with telemetry.tracer.start_as_current_span("analyse.requete") as span:
        span.set_attribute("mardik.version", bundle.version)
        sections = decouper(texte, taille_max)
        span.set_attribute("mardik.sections", len(sections))

        try:
            parent_ctx = otel_context.get_current()
            nb_ouvriers = max(1, min(len(sections), MAX_APPELS_LLM_PARALLELES))
            with ThreadPoolExecutor(max_workers=nb_ouvriers) as executor:
                resultats = list(
                    executor.map(
                        lambda section: _extraire_avec_span(section, client, telemetry, parent_ctx),
                        sections,
                    )
                )
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

        par_section = [clauses for clauses, _ in resultats]
        appels_llm = len(resultats)
        tokens_total = sum(reponse.tokens for _, reponse in resultats)
        cout_total = sum(client.cout_eur(reponse) for _, reponse in resultats)

        clauses_consolidees = consolider(par_section)
        clauses_notees, confiance_globale = scorer(clauses_consolidees, len(sections), texte)

        # Capture pour le jeu d'éval (3e boucle de rétroaction) : ne doit
        # jamais faire échouer une analyse, seul endroit où un except large
        # est justifié (voir docstring de ops.enrichissement).
        cas_id = None
        try:
            cas_id = capturer(
                texte,
                clauses=[c.type for c in clauses_notees],
                confiance_globale=confiance_globale,
                version=bundle.version,
            )
        except Exception as exc:  # noqa: BLE001
            telemetry.logger.warning("enrichissement.capture_echouee", cause=str(exc))

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
            **({"cas_id": cas_id} if cas_id else {}),
        )
    return ReponseAnalyseV2(
        clauses=[
            ClauseV2(type=c.type, extrait=c.extrait, confiance=round(c.confiance, 3), sections=c.sections)
            for c in clauses_notees
        ],
        confiance_globale=round(confiance_globale, 3),
        modele=bundle.modele,
        version=bundle.version,
        sections=len(sections),
        appels_llm=appels_llm,
        latence_ms=latence,
        cout_eur=cout_total,
    )


@router.post("/analyse", response_model=ReponseAnalyseV2)
def analyse(
    requete: RequeteAnalyseV2,
    client: LLMClient = Depends(get_client_v2),
    telemetry: Telemetry = Depends(get_telemetry),
) -> ReponseAnalyseV2:
    try:
        return analyser_v2(requete.texte, client, telemetry)
    except DocumentTropLong as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except ErreurLLM as exc:
        raise HTTPException(status_code=503, detail=f"fournisseur LLM indisponible : {exc}")
