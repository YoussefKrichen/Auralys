<script setup>
import { computed, onMounted, ref } from "vue";
import { fetchJson, getApiBase } from "../lib/api";

const apiBase = ref(getApiBase());
const loading = ref(false);
const loadError = ref("");

// Static snapshot computed offline from data/gold/data_2025_2026_concat.csv
// (3 351 interventions, 500 clients, 2 janv. 2025 -> 30 juin 2026, genere le 2026-07-27).
// Used only as the initial render, before GET /kpis (app/api/agent_routes.py)
// resolves, and as a last-resort fallback if that call fails.
const FALLBACK_KPIS = {
  period: { start: "2 janv. 2025", end: "30 juin 2026" },
  totals: {
    interventions: 3351,
    clients: 500,
    volume_livre: 483318,
    median_interventions_per_client: 3,
  },
  top_clients: [
    { name: "716", count: 136 },
    { name: "Mall of Sousse", count: 109 },
    { name: "Ooredoo", count: 82 },
    { name: "Asteel Flash", count: 59 },
    { name: "Heni", count: 54 },
  ],
  bottom_clients: [
    { name: "Villa Hotel", count: 1 },
    { name: "Hotel Kuriat", count: 1 },
    { name: "Cabinet Dr Slim Kassar", count: 1 },
    { name: "Pharmacie Tabka", count: 1 },
    { name: "Ste Ceram Garden", count: 1 },
  ],
  bottom_clients_note: "129 clients sur 500 (26 %) n'ont eu qu'une seule intervention sur toute la periode - l'echantillon ci-dessus est pris parmi eux, tous strictement ex-aequo.",
  diffuseurs_by_clients: [
    { model: "Astree", clients: 204 },
    { model: "Aromair100", clients: 156 },
    { model: "Zee300", clients: 132 },
    { model: "Iceburg", clients: 75 },
    { model: "Aromair150", clients: 64 },
    { model: "Zee600", clients: 48 },
    { model: "Centrale/CTA", clients: 15 },
    { model: "Zephyr", clients: 14 },
    { model: "Tour", clients: 10 },
    { model: "Aomair50", clients: 5 },
    { model: "Aromair600", clients: 5 },
  ],
  diffuseur_extreme_note: "Classement par adoption client (un client compte une seule fois). Trie par volume de parfum livre, Aromair100 repasse en tete avec 121 540 unites - proxy commercial faute de champ prix dans les donnees.",
  source_breakdown: [
    { label: "Controle", pct: 39.5 },
    { label: "Recharge", pct: 23.6 },
    { label: "Visite", pct: 22.0 },
    { label: "Livraison", pct: 13.6 },
    { label: "Autres", pct: 1.3 },
  ],
  monthly_trend: [
    { label: "Jan 25", count: 244, has_data: true },
    { label: "Fev 25", count: 348, has_data: true },
    { label: "Mar 25", count: 29, has_data: true },
    { label: "Avr 25", count: 227, has_data: true },
    { label: "Mai 25", count: 296, has_data: true },
    { label: "Jun 25", count: 285, has_data: true },
    { label: "Jul 25", count: 222, has_data: true },
    { label: "Aou 25", count: 304, has_data: true },
    { label: "Sep 25", count: 1, has_data: true },
    { label: "Oct 25", count: 128, has_data: true },
    { label: "Nov 25", count: 0, has_data: false },
    { label: "Dec 25", count: 0, has_data: false },
    { label: "Jan 26", count: 292, has_data: true },
    { label: "Fev 26", count: 0, has_data: false },
    { label: "Mar 26", count: 0, has_data: false },
    { label: "Avr 26", count: 0, has_data: false },
    { label: "Mai 26", count: 262, has_data: true },
    { label: "Jun 26", count: 708, has_data: true },
  ],
  year_rhythm: {
    y2025: { total: 2089, months_covered: 10, per_month: 208.9 },
    y2026: { total: 1262, months_covered: 3, per_month: 420.7 },
  },
  parfums_top: [
    { name: "RG", count: 303 },
    { name: "TH", count: 191 },
    { name: "FE3", count: 155 },
    { name: "Melange", count: 115 },
    { name: "FM", count: 108 },
  ],
  villes_top: [
    { name: "Soukra", count: 479 },
    { name: "Lac 1", count: 340 },
    { name: "Sousse", count: 283 },
    { name: "Lac 2", count: 231 },
    { name: "Tunis", count: 160 },
  ],
  // Nombre d'emplacements distincts (colonne "emplacement") par client - le
  // meilleur proxy disponible pour le nombre d'unites physiques installees,
  // faute d'un identifiant de diffuseur individuel dans les donnees source.
  top_diffuser_owners: [
    { name: "Ooredoo", count: 38 },
    { name: "716", count: 37 },
    { name: "Mall of Sousse", count: 35 },
    { name: "Heni", count: 23 },
    { name: "Asteel Flash", count: 22 },
  ],
};

const kpis = ref(FALLBACK_KPIS);

// --- Period reports (GET /reports, CEO-only) --------------------------------
// Reuses the same `kpis` ref and every computed/rendering path below: a
// report response has the exact same shape as GET /kpis, just filtered to
// one day/week/month/year instead of the full history.
const REPORT_PERIODS = [
  { value: "day", label: "Jour" },
  { value: "week", label: "Semaine" },
  { value: "month", label: "Mois" },
  { value: "year", label: "Annee" },
];
const reportPeriod = ref("month");
const reportDate = ref(new Date().toISOString().slice(0, 10));
const reportMeta = ref(null); // { period, label, range_start, range_end } once a report is loaded
const reportLoading = ref(false);
const reportError = ref("");

async function generateReport() {
  reportLoading.value = true;
  reportError.value = "";
  try {
    const query = `/reports?period=${encodeURIComponent(reportPeriod.value)}&on=${encodeURIComponent(reportDate.value)}`;
    const payload = await fetchJson(query, {}, apiBase.value);
    if (payload && payload.totals) {
      kpis.value = payload;
      reportMeta.value = payload.report || null;
    }
  } catch (error) {
    reportError.value = error?.message || "Impossible de generer le rapport.";
  } finally {
    reportLoading.value = false;
  }
}

async function backToOverview() {
  reportMeta.value = null;
  reportError.value = "";
  await loadKpis();
}

// Option B: one headline number carries the hero, the rest reads as a
// slim strip underneath instead of six equal-weight cards.
const heroHeadline = computed(() => {
  const t = kpis.value.totals;
  return {
    value: t.interventions.toLocaleString("fr-FR"),
    label: `interventions realisees sur la periode, ${t.clients.toLocaleString("fr-FR")} clients actifs`,
  };
});

const heroStrip = computed(() => {
  const t = kpis.value.totals;
  const busiestMonth = kpis.value.monthly_trend.reduce(
    (best, row) => (row.count > (best?.count ?? -1) ? row : best),
    null,
  );
  const topDiffuseur = kpis.value.diffuseurs_by_clients[0];
  const topVille = kpis.value.villes_top[0];
  return [
    { label: "Clients actifs", value: t.clients.toLocaleString("fr-FR"), detail: `mediane : ${t.median_interventions_per_client} / client` },
    { label: "Volume livre", value: t.volume_livre.toLocaleString("fr-FR"), detail: "unites de parfum" },
    { label: "Ville la + desservie", value: topVille?.name ?? "-", detail: `${topVille?.count ?? 0} interventions` },
    { label: "Mois le + charge", value: busiestMonth?.label ?? "-", detail: `${busiestMonth?.count ?? 0} interventions` },
    { label: "Diffuseur le + utilise", value: topDiffuseur?.model ?? "-", detail: `${topDiffuseur?.clients ?? 0} clients equipes` },
  ];
});

const maxTopClient = computed(() => Math.max(1, ...kpis.value.top_clients.map((row) => row.count)));
const maxBottomClient = computed(() => Math.max(1, ...kpis.value.bottom_clients.map((row) => row.count)));

function shareOfInterventions(count) {
  const total = kpis.value.totals.interventions || 1;
  return (count / total * 100).toLocaleString("fr-FR", { maximumFractionDigits: 1 }) + " %";
}

// Bars start at 0 and animate to their real width just after mount, staggered
// per row, so the ranking reads as a reveal rather than a static block.
const barsRevealed = ref(false);
const maxDiffuseur = computed(() => Math.max(1, ...kpis.value.diffuseurs_by_clients.map((row) => row.clients)));
const maxMonthly = computed(() => Math.max(1, ...kpis.value.monthly_trend.map((row) => row.count)));

const diffuseurTop = computed(() => kpis.value.diffuseurs_by_clients[0] || null);
const diffuseurBottom = computed(() => {
  const list = kpis.value.diffuseurs_by_clients;
  return list.length ? list[list.length - 1] : null;
});

// Five distinct hues (blue / green / gold / orange / grey) so adjacent
// slices never blend together - two shades of the same hue read as one slice.
const donutColors = ["var(--accent)", "var(--success)", "var(--warning)", "var(--urgent)", "var(--muted)"];
const donutGradient = computed(() => {
  let cursor = 0;
  const stops = kpis.value.source_breakdown.map((row, index) => {
    const start = cursor;
    cursor += row.pct;
    const color = donutColors[index % donutColors.length];
    return `${color} ${start}% ${cursor}%`;
  });
  return `conic-gradient(${stops.join(", ")})`;
});

// Built from whichever years actually appear in kpis.year_rhythm -- a
// period report (day/week/month) will often only cover one year, so this
// can't hardcode y2025/y2026 the way the all-time dashboard used to.
const yearRhythmRows = computed(() => {
  const years = Object.keys(kpis.value.year_rhythm || {}).sort();
  const stats = years.map((key) => ({ year: key.replace(/^y/, ""), ...kpis.value.year_rhythm[key] }));
  const maxTotal = Math.max(1, ...stats.map((row) => row.total));
  const maxPerMonth = Math.max(1, ...stats.map((row) => row.per_month));
  return {
    totals: stats.map((row) => ({
      label: `${row.year} (${row.months_covered} mois)`,
      value: row.total,
      pct: (row.total / maxTotal) * 100,
    })),
    perMonth: stats.map((row) => ({
      label: `${row.year} / mois`,
      value: row.per_month,
      pct: (row.per_month / maxPerMonth) * 100,
    })),
  };
});

async function loadKpis() {
  loading.value = true;
  loadError.value = "";
  try {
    const payload = await fetchJson("/kpis", {}, apiBase.value);
    if (payload && payload.totals) {
      kpis.value = payload;
    }
  } catch (error) {
    // Surface the failure instead of silently passing off the stale bundled
    // snapshot as current data - a CEO reading this page should know when
    // it's not live.
    loadError.value = error?.message || "Impossible de charger les KPIs en direct.";
    kpis.value = FALLBACK_KPIS;
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void loadKpis();
  window.setTimeout(() => {
    barsRevealed.value = true;
  }, 30);
});
</script>

<template>
  <section id="ceo-kpis" class="ceo-workspace-shell kpi-space">
    <section class="panel executive-overview-hero">
      <div class="executive-overview-head">
        <div class="executive-overview-copy">
          <h2>Aromair, en chiffres <span class="kpi-title-credit">avec Auralys</span></h2>
          <p>Vue d'ensemble des interventions, clients et diffuseurs sur la periode couverte par les donnees.</p>
        </div>
        <div class="kpi-hero-chips">
          <span v-if="reportMeta" class="meta-chip meta-chip-report">Rapport : {{ reportMeta.label }}</span>
          <span v-else class="meta-chip">{{ kpis.period.start }} &rarr; {{ kpis.period.end }}</span>
          <span class="meta-chip" :class="{ 'meta-chip-warning': loadError }">
            {{ loading || reportLoading ? "Actualisation..." : loadError ? "Donnees figees (hors ligne)" : "A jour" }}
          </span>
        </div>
      </div>
      <p v-if="loadError" class="kpi-note kpi-load-error">
        Echec du chargement des KPIs en direct ({{ loadError }}) - affichage de l'instantane statique inclus dans la page.
      </p>

      <div class="kpi-report-bar">
        <div class="kpi-report-periods" role="group" aria-label="Periode du rapport">
          <button
            v-for="option in REPORT_PERIODS"
            :key="option.value"
            type="button"
            class="kpi-report-period-btn"
            :class="{ active: reportPeriod === option.value }"
            @click="reportPeriod = option.value"
          >
            {{ option.label }}
          </button>
        </div>
        <input v-model="reportDate" type="date" class="kpi-report-date" aria-label="Date de reference du rapport" />
        <button type="button" class="kpi-report-generate-btn" :disabled="reportLoading" @click="generateReport">
          {{ reportLoading ? "Generation..." : "Generer le rapport" }}
        </button>
        <button v-if="reportMeta" type="button" class="kpi-report-reset-btn" @click="backToOverview">
          &larr; Vue globale
        </button>
      </div>
      <p v-if="reportError" class="kpi-note kpi-load-error">{{ reportError }}</p>
      <p v-else-if="reportMeta" class="kpi-note">
        Rapport reserve au CEO, genere pour la periode du {{ reportMeta.range_start }} au {{ reportMeta.range_end }}.
      </p>
      <div class="kpi-hero-number-row">
        <span class="kpi-hero-number">{{ heroHeadline.value }}</span>
        <span class="kpi-hero-number-label">{{ heroHeadline.label }}</span>
      </div>
      <div class="kpi-hero-strip">
        <div v-for="stat in heroStrip" :key="stat.label" class="kpi-hero-strip-item">
          <span>{{ stat.label }}</span>
          <strong>{{ stat.value }}</strong>
          <small>{{ stat.detail }}</small>
        </div>
      </div>
    </section>

    <div class="kpi-grid-2">
      <section class="panel kpi-panel">
        <div class="section-title">
          <div>
            <h3>Top 5 clients</h3>
            <p>Classement par nombre d'interventions realisees sur la periode.</p>
          </div>
        </div>
        <div class="kpi-rank-list">
          <div
            v-for="(row, index) in kpis.top_clients"
            :key="row.name"
            class="kpi-rank-row"
            :title="`${row.name} - ${row.count} interventions (${shareOfInterventions(row.count)} du total)`"
          >
            <span class="kpi-rank-badge kpi-rank-badge-top" :class="{ 'kpi-rank-badge-lead': index === 0 }">{{ index + 1 }}</span>
            <div class="kpi-rank-label">
              <span class="kpi-rank-name">{{ row.name }}</span>
              <div class="kpi-bar-track">
                <div
                  class="kpi-bar-fill kpi-bar-top"
                  :style="{
                    width: (barsRevealed ? Math.max(4, (row.count / maxTopClient) * 100) : 0) + '%',
                    transitionDelay: index * 70 + 'ms',
                  }"
                />
              </div>
            </div>
            <span class="kpi-rank-val">
              {{ row.count }}
              <small class="kpi-rank-pct">{{ shareOfInterventions(row.count) }}</small>
            </span>
          </div>
        </div>
      </section>

      <section class="panel kpi-panel">
        <div class="section-title">
          <div>
            <h3>5 clients les moins actifs</h3>
            <p>Une seule intervention sur toute la periode.</p>
          </div>
        </div>
        <div class="kpi-rank-list">
          <div
            v-for="(row, index) in kpis.bottom_clients"
            :key="row.name"
            class="kpi-rank-row"
            :title="`${row.name} - ${row.count} intervention sur toute la periode`"
          >
            <span class="kpi-rank-badge kpi-rank-badge-bottom">{{ index + 1 }}</span>
            <div class="kpi-rank-label">
              <span class="kpi-rank-name">{{ row.name }}</span>
              <div class="kpi-bar-track">
                <div
                  class="kpi-bar-fill kpi-bar-bottom"
                  :style="{
                    width: (barsRevealed ? Math.max(4, (row.count / maxBottomClient) * 100) : 0) + '%',
                    transitionDelay: index * 70 + 'ms',
                  }"
                />
              </div>
            </div>
            <span class="kpi-rank-val">{{ row.count }}</span>
          </div>
        </div>
        <p class="kpi-note">{{ kpis.bottom_clients_note }}</p>
      </section>
    </div>

    <div class="kpi-grid-2">
      <section class="panel kpi-panel">
        <div class="section-title">
          <div>
            <h3>Diffuseur le plus vs le moins utilise</h3>
            <p>Par nombre de clients distincts equipes (un client compte une seule fois), modeles avec au moins 5 clients.</p>
          </div>
        </div>
        <div class="kpi-extreme-pair">
          <div v-if="diffuseurTop" class="kpi-extreme-card kpi-extreme-win">
            <span class="kpi-extreme-tag">Le plus utilise</span>
            <h4>{{ diffuseurTop.model }}</h4>
            <strong>{{ diffuseurTop.clients }} clients equipes</strong>
          </div>
          <div v-if="diffuseurBottom" class="kpi-extreme-card kpi-extreme-low">
            <span class="kpi-extreme-tag">Le moins utilise</span>
            <h4>{{ diffuseurBottom.model }}</h4>
            <strong>{{ diffuseurBottom.clients }} clients equipes</strong>
          </div>
        </div>
        <div class="kpi-model-mini">
          <div v-for="row in kpis.diffuseurs_by_clients" :key="row.model" class="kpi-model-row">
            <span class="kpi-model-name">{{ row.model }}</span>
            <div class="kpi-bar-track">
              <div class="kpi-bar-fill kpi-bar-top" :style="{ width: Math.max(3, (row.clients / maxDiffuseur) * 100) + '%' }" />
            </div>
            <span class="kpi-model-val">{{ row.clients }}</span>
          </div>
        </div>
        <p class="kpi-note">{{ kpis.diffuseur_extreme_note }}</p>
      </section>

      <section class="panel kpi-panel">
        <div class="section-title">
          <div>
            <h3>Repartition par type d'intervention</h3>
            <p>Part de chaque nature sur {{ kpis.totals.interventions.toLocaleString("fr-FR") }} interventions.</p>
          </div>
        </div>
        <div class="kpi-donut-wrap">
          <div class="kpi-donut" :style="{ background: donutGradient }">
            <div class="kpi-donut-hole" />
          </div>
          <div class="kpi-donut-legend">
            <div v-for="(row, index) in kpis.source_breakdown" :key="row.label" class="kpi-donut-legend-row">
              <span class="kpi-legend-label">
                <i class="kpi-swatch" :style="{ background: donutColors[index % donutColors.length] }" />{{ row.label }}
              </span>
              <span class="kpi-legend-val">{{ row.pct }}%</span>
            </div>
          </div>
        </div>
        <div class="kpi-subsection">
          <h4>Clients avec le plus de diffuseurs</h4>
          <p class="kpi-subsection-caption">Nombre d'emplacements distincts equipes - le meilleur proxy disponible, faute d'un identifiant d'unite physique dans les donnees.</p>
          <div class="kpi-mini-table">
            <div v-for="(row, index) in kpis.top_diffuser_owners" :key="row.name" class="kpi-mini-table-row">
              <span class="kpi-mini-rank">#{{ index + 1 }}</span>
              <span>{{ row.name }}</span>
              <span class="kpi-mini-val">{{ row.count }}</span>
            </div>
          </div>
        </div>
      </section>
    </div>

    <section class="panel kpi-panel">
      <div class="section-title">
        <div>
          <h3>Charge mensuelle</h3>
          <p>Interventions par mois. Les colonnes grisees indiquent une absence de donnees dans le fichier source.</p>
        </div>
      </div>
      <div class="kpi-trend">
        <div v-for="row in kpis.monthly_trend" :key="row.label" class="kpi-trend-col" :title="`${row.label} - ${row.has_data ? row.count + ' interventions' : 'pas de donnees'}`">
          <div class="kpi-trend-bar-track">
            <div
              class="kpi-trend-bar"
              :class="{ 'kpi-trend-bar-empty': !row.has_data }"
              :style="{ height: (row.has_data ? Math.max(2, (row.count / maxMonthly) * 100) : 4) + '%' }"
            />
          </div>
          <span class="kpi-trend-label">{{ row.label }}</span>
        </div>
      </div>
    </section>

    <div class="kpi-grid-3">
      <section class="panel kpi-panel">
        <div class="section-title">
          <div>
            <h3>Rythme annuel</h3>
            <p>Normalise par mois couvert.</p>
          </div>
        </div>
        <div class="kpi-model-mini">
          <div v-for="row in yearRhythmRows.totals" :key="row.label" class="kpi-model-row">
            <span class="kpi-model-name">{{ row.label }}</span>
            <div class="kpi-bar-track">
              <div class="kpi-bar-fill kpi-bar-top" :style="{ width: row.pct + '%' }" />
            </div>
            <span class="kpi-model-val">{{ row.value.toLocaleString("fr-FR") }}</span>
          </div>
          <div v-for="row in yearRhythmRows.perMonth" :key="row.label" class="kpi-model-row">
            <span class="kpi-model-name">{{ row.label }}</span>
            <div class="kpi-bar-track">
              <div class="kpi-bar-fill kpi-bar-bottom" :style="{ width: row.pct + '%' }" />
            </div>
            <span class="kpi-model-val">&asymp;{{ Math.round(row.value) }}</span>
          </div>
        </div>
      </section>

      <section class="panel kpi-panel">
        <div class="section-title">
          <div>
            <h3>Parfums les plus demandes</h3>
            <p>Top 5 par nombre d'interventions.</p>
          </div>
        </div>
        <div class="kpi-mini-table">
          <div v-for="(row, index) in kpis.parfums_top" :key="row.name" class="kpi-mini-table-row">
            <span class="kpi-mini-rank">#{{ index + 1 }}</span>
            <span>{{ row.name }}</span>
            <span class="kpi-mini-val">{{ row.count }}</span>
          </div>
        </div>
      </section>

      <section class="panel kpi-panel">
        <div class="section-title">
          <div>
            <h3>Zones les plus desservies</h3>
            <p>Top 5 par nombre d'interventions.</p>
          </div>
        </div>
        <div class="kpi-mini-table">
          <div v-for="(row, index) in kpis.villes_top" :key="row.name" class="kpi-mini-table-row">
            <span class="kpi-mini-rank">#{{ index + 1 }}</span>
            <span>{{ row.name }}</span>
            <span class="kpi-mini-val">{{ row.count }}</span>
          </div>
        </div>
      </section>
    </div>

    <p class="kpi-footnote">
      Source : data/gold/data_2025_2026_concat.csv, recalcule a chaque chargement par GET /kpis.
      {{ loadError ? "L'appel a echoue pour ce chargement : les chiffres affiches sont l'instantane statique inclus dans la page, pas les donnees actuelles." : "" }}
    </p>
  </section>
</template>
