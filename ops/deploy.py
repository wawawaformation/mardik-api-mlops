"""Déploiement : publication, canary, promotion, rollback, surveillance.

Contrat attendu (le registre — ``ops/registry`` — enregistre ; ce module décide) :

    publier(version, *, bundle="v2", commit="local", registry=None, seuil=0.75,
            rapport=None) -> manifest
        Étiquette une version : joue le gate d'évaluation (``eval.run_eval.evaluer``)
        sur le bundle en chantier — sauf si un ``rapport`` est fourni — et
        REFUSE (``ErreurDeploiement``) si le gate échoue. Sinon dépose le bundle
        dans le registre avec commit + note d'éval, et journalise ``publication``.

    deployer_canary(version, pourcentage=None, registry=None) -> index
        Route ``pourcentage`` % du trafic vers ``version`` (défaut : CANARY_PERCENT
        de ``.env``, sinon 10). Journalise ``canary``.

    promouvoir(version, registry=None) -> index
        La version devient active pour 100 % du trafic ; l'ancienne active est
        conservée dans ``index["precedente"]`` ; le canary est retiré. Journalise
        ``promotion``.

    rollback(registry=None, motif="manuel") -> index
        Retour arrière en une opération : si un canary est en cours, il est
        retiré ; sinon l'active redevient ``precedente``. Journalise ``rollback``
        avec le motif et les versions avant/après.

    surveiller(registry=None, metriques=None, *, fenetre_s=120, score_min=None,
               taux_erreur_max=None, latence_p95_max_ms=None,
               cout_moyen_max_eur=None, minimum=10) -> dict
        Lit les mesures récentes (``MetricsStore``) de la version sous
        surveillance (le canary s'il y en a un, sinon l'active). Les seuils
        non fournis explicitement viennent des règles ajustables
        (``ops/regles.py`` — ``GET``/``PUT /pilotage/regles``) ; un seuil
        fourni explicitement garde la priorité (compatibilité des appelants
        existants). Dérive si taux d'erreur > seuil, ou P95 > seuil, ou coût
        moyen > seuil, ou (score_min explicite) score moyen < score_min,
        ou (sinon) proportion de scores < seuil bas de la règle
        ``score_faible`` supérieure au seuil de cette règle — sur au moins
        ``minimum`` mesures. En cas de dérive : rollback automatique +
        entrée au journal. Renvoie {"version", "mesures", "derive", "motif",
        "rollback"}.

Ligne de commande : ``python -m ops.deploy publier v2.0.0 | canary v2.0.0 --pourcentage 10
| promouvoir v2.0.0 | rollback | surveiller [--boucle]``.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from typing import Any

from app.llm_client import Bundle
from app.telemetry import Mesure, MetricsStore
from ops.dashboard import percentile, stores_metriques_par_defaut
from ops.registry import Registry
from ops.regles import (
    regles_par_signal,
    seuil_cout_moyen_eur,
    seuil_latence_p95_ms,
    seuil_score_faible,
    seuil_taux_erreur,
)


class ErreurDeploiement(RuntimeError):
    pass


def _commit_courant() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "local"


def prochaine_version(
    bump: str = "patch", registry: Registry | None = None, bundle: str = "v2"
) -> str:
    """Calcule la prochaine version SemVer, dans la lignée du ``bundle``
    donné (``"v2"`` par défaut — la seule lignée qui évolue : v1 est figée,
    jamais réétiquetée, voir AGENTS.md).

    ``bump`` : ``"patch"`` (défaut, auto-incrémenté à chaque build validé),
    ``"minor"`` ou ``"major"`` (montés manuellement, cf. versionnage.md).

    Ignore toute version d'une autre lignée (identifiée par la ``strategie``
    du manifeste, ex. ``v1.0.0`` en ``monolithique``) : un bug corrigé le
    2026-09-23 mélangeait les deux lignées dès lors que seule ``v1.0.0``
    était enregistrée, produisant ``v1.0.1`` pour ce qui était en réalité
    une première publication v2. Sans version de cette lignée dans le
    registre (première publication), renvoie directement la version
    déclarée par le bundle (``models/<bundle>/config.yaml::version``).
    """
    if bump not in {"patch", "minor", "major"}:
        raise ValueError(f"bump invalide : {bump!r} (attendu patch/minor/major)")
    reg = registry or Registry()
    strategie_cible = Bundle.charger(bundle).strategie
    versions_lignee = [
        v for v in reg.versions() if reg.manifest(v).get("strategie") == strategie_cible
    ]
    if not versions_lignee:
        return Bundle.charger(bundle).version
    major, minor, patch = (int(x) for x in versions_lignee[-1].lstrip("v").split("."))
    if bump == "major":
        major, minor, patch = major + 1, 0, 0
    elif bump == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"v{major}.{minor}.{patch}"


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


def deployer_canary(
    version: str, pourcentage: int | None = None, registry: Registry | None = None, **details: Any
) -> dict[str, Any]:
    reg = registry or Registry()
    pct = pourcentage if pourcentage is not None else int(os.environ.get("CANARY_PERCENT", "10"))
    reg.definir_canary(version, pct)
    reg.journaliser("canary", version=version, pourcentage=pct, **details)
    return reg.index()


def promouvoir(version: str, registry: Registry | None = None, **details: Any) -> dict[str, Any]:
    reg = registry or Registry()
    reg.manifest(version)  # lève ErreurRegistre si version inconnue
    idx = reg.index()
    precedente = idx.get("active")
    reg.ecrire_index(
        {**idx, "active": version, "precedente": precedente, "canary": None, "canary_percent": 0}
    )
    reg.journaliser("promotion", version=version, precedente=precedente, **details)
    return reg.index()


def rollback(registry: Registry | None = None, motif: str = "manuel", **details: Any) -> dict[str, Any]:
    reg = registry or Registry()
    idx = reg.index()
    avant = {"active": idx.get("active"), "canary": idx.get("canary")}
    if idx.get("canary"):
        idx = {**idx, "canary": None, "canary_percent": 0}
    elif idx.get("precedente"):
        idx = {**idx, "active": idx.get("precedente"), "precedente": idx.get("active")}
    # Ni canary ni version précédente : il n'y a rien à annuler. On garde
    # l'active en place — la basculer vers `precedente` vide laisserait la
    # gateway sans version à servir (incident du 2026-09-23 : deux rollbacks
    # de suite mettaient `active: null`, /analyse répondait 500).
    reg.ecrire_index(idx)
    apres = {"active": idx.get("active"), "canary": idx.get("canary")}
    reg.journaliser("rollback", motif=motif, avant=avant, apres=apres, **details)
    return reg.index()


def surveiller(
    registry: Registry | None = None,
    metriques: MetricsStore | None = None,
    *,
    fenetre_s: float = 120,
    score_min: float | None = None,
    taux_erreur_max: float | None = None,
    latence_p95_max_ms: float | None = None,
    cout_moyen_max_eur: float | None = None,
    minimum: int = 10,
) -> dict[str, Any]:
    reg = registry or Registry()
    stores = [metriques] if metriques is not None else stores_metriques_par_defaut()
    canary, _ = reg.canary()
    version = canary or reg.active()

    mesures: list[Mesure] = [
        m for store in stores for m in store.lire(depuis_s=fenetre_s, version=version)
    ]

    regles = regles_par_signal()

    motifs: list[str] = []
    if len(mesures) >= minimum:
        taux_erreur = sum(1 for m in mesures if m.erreur) / len(mesures)
        seuil_erreur = taux_erreur_max if taux_erreur_max is not None else seuil_taux_erreur(regles)
        if taux_erreur > seuil_erreur:
            motifs.append(f"taux d'erreur {taux_erreur:.1%} > seuil {seuil_erreur:.1%}")

        sans_erreur = [m for m in mesures if not m.erreur]
        scores = [m.score for m in sans_erreur if m.score is not None]
        if score_min is not None:
            if scores:
                score_moyen = sum(scores) / len(scores)
                if score_moyen < score_min:
                    motifs.append(f"score moyen {score_moyen:.2f} < seuil {score_min:.2f}")
        elif scores:
            proportion_max, score_bas = seuil_score_faible(regles)
            proportion_faible = sum(1 for s in scores if s < score_bas) / len(scores)
            if proportion_faible > proportion_max:
                motifs.append(
                    f"score : {proportion_faible:.1%} des scores < {score_bas:g} "
                    f"> seuil {proportion_max:.1%}"
                )

        latences = sorted(m.latence_ms for m in sans_erreur)
        if latences:
            p95 = percentile(latences, 95)
            seuil_latence = (
                latence_p95_max_ms if latence_p95_max_ms is not None else seuil_latence_p95_ms(regles)
            )
            if p95 > seuil_latence:
                motifs.append(f"latence P95 {p95:.0f}ms > seuil {seuil_latence:.0f}ms")

        couts = [m.cout_eur for m in sans_erreur]
        if couts:
            cout_moyen = sum(couts) / len(couts)
            seuil_cout = (
                cout_moyen_max_eur if cout_moyen_max_eur is not None else seuil_cout_moyen_eur(regles)
            )
            if cout_moyen > seuil_cout:
                motifs.append(f"coût moyen {cout_moyen:.3f}€ > seuil {seuil_cout:.3f}€")

    motif = "; ".join(motifs)
    resultat: dict[str, Any] = {
        "version": version,
        "mesures": len(mesures),
        "derive": bool(motifs),
        "motif": motif,
        "rollback": False,
    }
    if motifs:
        rollback(registry=reg, motif=motif)
        resultat["rollback"] = True
    return resultat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Déploiement Mardik")
    sub = parser.add_subparsers(dest="commande", required=True)
    p = sub.add_parser("publier")
    p.add_argument("version")
    p.add_argument("--bundle", default="v2")
    p.add_argument("--seuil", type=float, default=0.75)
    c = sub.add_parser("canary")
    c.add_argument("version")
    c.add_argument("--pourcentage", type=int, default=None)
    c.add_argument("--declencheur", choices=["auto", "humain"], default="humain")
    c.add_argument("--signal", default=None)
    pr = sub.add_parser("promouvoir")
    pr.add_argument("version")
    pr.add_argument("--declencheur", choices=["auto", "humain"], default="humain")
    pr.add_argument("--signal", default=None)
    r = sub.add_parser("rollback")
    r.add_argument("--motif", default="manuel")
    r.add_argument("--declencheur", choices=["auto", "humain"], default="humain")
    r.add_argument("--signal", default=None)
    s = sub.add_parser("surveiller")
    s.add_argument("--boucle", action="store_true")
    s.add_argument("--intervalle", type=float, default=5.0)
    s.add_argument("--fenetre", type=float, default=120)
    args = parser.parse_args(argv)

    try:
        if args.commande == "publier":
            print(publier(args.version, bundle=args.bundle, seuil=args.seuil))
        elif args.commande == "canary":
            details: dict[str, Any] = {"declencheur": args.declencheur}
            if args.signal is not None:
                details["signal"] = args.signal
            print(deployer_canary(args.version, args.pourcentage, **details))
        elif args.commande == "promouvoir":
            details = {"declencheur": args.declencheur}
            if args.signal is not None:
                details["signal"] = args.signal
            print(promouvoir(args.version, **details))
        elif args.commande == "rollback":
            details = {"declencheur": args.declencheur}
            if args.signal is not None:
                details["signal"] = args.signal
            print(rollback(motif=args.motif, **details))
        elif args.commande == "surveiller":
            while True:
                res = surveiller(fenetre_s=args.fenetre)
                print(res)
                if not args.boucle or res["rollback"]:
                    break
                time.sleep(args.intervalle)
    except ErreurDeploiement as exc:
        print(f"REFUSÉ : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
