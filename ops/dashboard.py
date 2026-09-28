"""Tableau de bord : latence, erreurs, score de confiance, trafic par version.

Contrat :

    resume(metriques=None, *, fenetre_s=300) -> dict
        Agrège les mesures des ``fenetre_s`` dernières secondes de
        ``MetricsStore`` (``ops/metrics.jsonl`` par défaut) :
        {
          "fenetre_s": 300, "total": 128,
          "par_version": {
             "v1.0.0": {"requetes": 115, "trafic_pct": 89.8, "latence_p50_ms": …,
                        "latence_p95_ms": …, "taux_erreur": 0.02,
                        "score_moyen": null, "cout_total_eur": …,
                        "distribution_score": [{"borne_min": 0.0, "borne_max": 0.2, "n": 0}, …]},
             "v2.0.0": {… "score_moyen": 0.84 …}
          },
          "journal": [ …5 derniers événements de déploiement… ]
        }
        Les versions sans trafic dans la fenêtre n'apparaissent pas.
        ``score_moyen`` vaut ``None`` pour une version qui ne produit pas de
        score (v1). Les erreurs sont exclues des latences et des scores.

    python -m ops.dashboard              → affiche le résumé en texte
    python -m ops.dashboard --serve      → page HTML auto-rafraîchie sur :8501
                                           (service ``dashboard`` du docker-compose)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from app.telemetry import CHEMIN_METRIQUES_DEFAUT, Mesure, MetricsStore
from ops.registry import Registry

CHEMIN_METRIQUES_V2_DEFAUT = CHEMIN_METRIQUES_DEFAUT.parent / "metrics_v2.jsonl"


def stores_metriques_par_defaut() -> list[MetricsStore]:
    """Sans ``metriques`` explicite : fusionne le journal v1 (``METRICS_PATH``,
    par défaut ``ops/metrics.jsonl``) et le journal v2 (``METRICS_PATH_V2``,
    par défaut ``ops/metrics_v2.jsonl``) — sinon le trafic du container ``v2``
    (journal séparé, voir ``docker-compose.yml``) resterait invisible."""
    chemin_v2 = os.environ.get("METRICS_PATH_V2", CHEMIN_METRIQUES_V2_DEFAUT)
    return [MetricsStore(), MetricsStore(chemin_v2)]


def percentile(valeurs: list[float], p: float) -> float:
    if not valeurs:
        return 0.0
    k = (len(valeurs) - 1) * p / 100
    f, c = int(k), min(int(k) + 1, len(valeurs) - 1)
    if f == c:
        return round(valeurs[f], 1)
    return round(valeurs[f] + (valeurs[c] - valeurs[f]) * (k - f), 1)


_TRANCHES_SCORE = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]


def distribution_score(scores: list[float]) -> list[dict[str, Any]]:
    """Répartit ``scores`` en 5 tranches de 0,2 (``[0-0,2[`` … ``[0,8-1]``,
    dernière tranche incluse à droite) : le nombre de mesures dans chacune,
    pas seulement la moyenne — une moyenne à 0,75 peut cacher un tas de
    scores très bas et un tas de scores très hauts, ce que la distribution
    révèle et pas la moyenne."""
    tranches = []
    derniere = len(_TRANCHES_SCORE) - 1
    for i, (bas, haut) in enumerate(_TRANCHES_SCORE):
        n = sum(1 for s in scores if bas <= s <= haut) if i == derniere else sum(
            1 for s in scores if bas <= s < haut
        )
        tranches.append({"borne_min": bas, "borne_max": haut, "n": n})
    return tranches


def resume(
    metriques: MetricsStore | None = None,
    *,
    fenetre_s: float = 300,
    registry: Registry | None = None,
) -> dict[str, Any]:
    stores = [metriques] if metriques is not None else stores_metriques_par_defaut()
    mesures: list[Mesure] = [m for store in stores for m in store.lire(depuis_s=fenetre_s)]
    registry = registry or Registry()

    total = len(mesures)
    par_version: dict[str, dict[str, Any]] = {}
    ordre: list[str] = []
    groupes: dict[str, list[Mesure]] = {}
    for m in mesures:
        groupes.setdefault(m.version, []).append(m)
        if m.version not in ordre:
            ordre.append(m.version)

    for version in ordre:
        ms = groupes[version]
        requetes = len(ms)
        sans_erreur = [m for m in ms if not m.erreur]
        latences = sorted(m.latence_ms for m in sans_erreur)
        scores = [m.score for m in sans_erreur if m.score is not None]
        par_version[version] = {
            "requetes": requetes,
            "trafic_pct": round(requetes / total * 100, 1) if total else 0.0,
            "latence_p50_ms": percentile(latences, 50),
            "latence_p95_ms": percentile(latences, 95),
            "taux_erreur": round(sum(1 for m in ms if m.erreur) / requetes, 4) if requetes else 0.0,
            "score_moyen": round(sum(scores) / len(scores), 3) if scores else None,
            "cout_total_eur": round(sum(m.cout_eur for m in sans_erreur), 6),
            "distribution_score": distribution_score(scores),
        }

    return {
        "fenetre_s": fenetre_s,
        "total": total,
        "par_version": par_version,
        "journal": registry.journal()[-5:],
    }


def rendre_texte(r: dict[str, Any]) -> str:
    lignes = [f"Tableau de bord Mardik — fenêtre {r['fenetre_s']:.0f} s, {r['total']} requêtes"]
    for version, v in r["par_version"].items():
        lignes.append(
            f"  {version} : {v['requetes']} req ({v['trafic_pct']}%), "
            f"latence p50={v['latence_p50_ms']}ms p95={v['latence_p95_ms']}ms, "
            f"erreurs={v['taux_erreur']:.1%}, "
            f"score={v['score_moyen'] if v['score_moyen'] is not None else 'n/a'}, "
            f"coût={v['cout_total_eur']}€"
        )
    if not r["par_version"]:
        lignes.append("  aucun trafic sur cette fenêtre")
    if r["journal"]:
        lignes.append("Derniers événements :")
        for e in r["journal"]:
            lignes.append(f"  {e.get('date', '?')} — {e.get('evenement', '?')}")
    return "\n".join(lignes)


def rendre_html(r: dict[str, Any]) -> str:
    lignes_versions = "".join(
        f"<tr><td>{version}</td><td>{v['requetes']}</td><td>{v['trafic_pct']}%</td>"
        f"<td>{v['latence_p50_ms']}</td><td>{v['latence_p95_ms']}</td>"
        f"<td>{v['taux_erreur']:.1%}</td>"
        f"<td>{v['score_moyen'] if v['score_moyen'] is not None else '—'}</td>"
        f"<td>{v['cout_total_eur']}</td></tr>"
        for version, v in r["par_version"].items()
    )
    lignes_journal = "".join(
        f"<li>{e.get('date', '?')} — {e.get('evenement', '?')}</li>" for e in r["journal"]
    )
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<title>Tableau de bord Mardik</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.8rem; text-align: right; }}
  th:first-child, td:first-child {{ text-align: left; }}
</style>
</head>
<body>
<h1>Tableau de bord Mardik</h1>
<p>Fenêtre : {r['fenetre_s']:.0f} s — {r['total']} requêtes</p>
<table>
<thead><tr><th>Version</th><th>Requêtes</th><th>Trafic</th><th>P50 (ms)</th>
<th>P95 (ms)</th><th>Erreurs</th><th>Score moyen</th><th>Coût (€)</th></tr></thead>
<tbody>{lignes_versions}</tbody>
</table>
<h2>Journal</h2>
<ul>{lignes_journal}</ul>
</body>
</html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tableau de bord Mardik")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--fenetre", type=float, default=300)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.serve:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse

        app = FastAPI(title="Mardik dashboard")

        @app.get("/", response_class=HTMLResponse)
        def page() -> str:
            return rendre_html(resume(fenetre_s=args.fenetre))

        @app.get("/api")
        def api() -> dict[str, Any]:
            return resume(fenetre_s=args.fenetre)

        uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
        return 0
    r = resume(fenetre_s=args.fenetre)
    print(json.dumps(r, ensure_ascii=False, indent=2) if args.json else rendre_texte(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
