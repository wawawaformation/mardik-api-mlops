// Client web de pilotage — vanilla JS, aucune dépendance, aucun build.
// Toute écriture passe par l'API du serveur de pilotage (ops/serveur_pilotage.py) ;
// ce fichier ne fait que lire/afficher/poster, il ne décide de rien.

// Vide par défaut : les appels /pilotage/* partent en relatif, vers la
// même origine que la page. Servi via Caddy (port 8090), ça atteint
// automatiquement serveur_pilotage sans souci de CORS.
const API_BASE = window.MARDIK_API_BASE || "";

const LIBELLE_SIGNAL = {
  latence_p95: "Latence P95",
  taux_erreur: "Taux d'erreur",
  score_faible: "Score < 0,6",
  cout_moyen: "Coût moyen",
  canary: "Canary",
};

const LIBELLE_ACTION = {
  rollback: "Rollback",
  promotion: "Promotion",
  canary: "Canary",
  ajustement_seuil: "Seuil ajusté",
  maintien: "Maintien",
  publication: "Publication",
  promotion_refusee: "Promotion refusée",
};

function libelleSignal(signal) {
  return LIBELLE_SIGNAL[signal] || signal || "—";
}

function libelleAction(action) {
  return LIBELLE_ACTION[action] || action || "—";
}

function tagAction(action) {
  if (action === "rollback" || action === "promotion_refusee") return "tag tag--danger";
  if (action === "promotion" || action === "canary") return "tag tag--ok";
  return "tag";
}

async function appelApi(chemin, options) {
  const reponse = await fetch(API_BASE + chemin, options);
  if (!reponse.ok) {
    let detail = reponse.statusText;
    try {
      const corps = await reponse.json();
      detail = corps.detail || detail;
    } catch (_) {
      // corps non-JSON, on garde statusText
    }
    throw new Error(`${reponse.status} : ${detail}`);
  }
  if (reponse.status === 204) return null;
  return reponse.json();
}

function afficherErreur(conteneur, erreur) {
  conteneur.innerHTML =
    `<div class="callout callout--warn"><span class="callout__label">Erreur :</span> ${erreur.message}</div>`;
}

function formatEuros(valeur) {
  return valeur.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 3 }) + " €";
}

function formatSecondes(ms) {
  return (ms / 1000).toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " s";
}

function formatPourcent(ratio) {
  return (ratio * 100).toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " %";
}

function statutClasse(valeur, seuil) {
  return valeur < seuil ? "status status--ok" : "status status--critical";
}

function statutLibelle(valeur, seuil) {
  return valeur < seuil ? "Conforme" : "Hors contrainte";
}

function formatHorodatage(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("fr-FR");
}
