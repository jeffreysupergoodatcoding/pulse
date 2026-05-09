<template>
  <div>
    <div class="view-header">
      <div>
        <h1 class="view-title">Audience Discovery</h1>
        <p class="view-subtitle">
          Find adjacent communities you aren't reaching (Method B) and audiences engaged with competitors but absent from your corpus (Method C)
        </p>
      </div>
    </div>

    <!-- Mode toggle -->
    <div class="mode-toggle">
      <button class="mode-btn" :class="{ active: mode === 'adjacent' }" @click="mode = 'adjacent'">
        Method B — Adjacent Communities
      </button>
      <button class="mode-btn" :class="{ active: mode === 'negative-space' }" @click="mode = 'negative-space'">
        Method C — Negative Space
      </button>
    </div>

    <!-- ── METHOD B ───────────────────────────────────────── -->
    <div v-if="mode === 'adjacent'" class="card">
      <div class="card-label">Method B — Adjacent Communities</div>
      <p class="hint">
        Surface clusters in a broader category corpus that aren't currently reached by this entity.
        First ingest a separate "category" entity with broad query terms (e.g. for a sleep brand:
        <em>sleep OR insomnia OR recovery OR wellness</em>), then select it below.
      </p>

      <div class="field">
        <label>Category entity</label>
        <select v-model="categoryEntityId">
          <option value="">— pick a category corpus —</option>
          <option v-for="e in entities" :key="e.id" :value="e.id" v-show="e.id !== entityId">
            {{ e.name }} ({{ e.id.slice(0, 8) }})
          </option>
        </select>
      </div>
      <div class="field-row">
        <div class="field">
          <label>Number of communities</label>
          <input type="number" v-model.number="nClusters" min="2" max="20" />
        </div>
        <div class="field">
          <label class="check-label">
            <input type="checkbox" v-model="explain" /> LLM-generate "why adjacent" explanations
          </label>
        </div>
      </div>
      <div class="actions">
        <button class="btn btn-primary" :disabled="!categoryEntityId || running" @click="runAdjacent">
          {{ running ? 'Analyzing…' : 'Discover Adjacent Communities' }}
        </button>
      </div>

      <div v-if="error" class="error">{{ error }}</div>

      <div v-if="adjacentResult" class="results">
        <div class="results-summary">
          <strong>{{ adjacentResult.n_communities }}</strong> communities surfaced
          ranked by distance from target audience.
        </div>
        <div v-for="c in adjacentResult.communities" :key="c.cluster_id" class="community-card">
          <div class="community-header">
            <span class="community-label">{{ c.label }}</span>
            <span class="community-score">distance {{ c.distance_from_target.toFixed(2) }}</span>
          </div>
          <div class="community-meta">
            <span>{{ c.n_authors }} authors</span>
            <span>·</span>
            <span>{{ c.n_posts }} posts</span>
            <span>·</span>
            <span>shared with target: {{ c.overlap_with_target.n_shared_authors }}</span>
            <span>·</span>
            <span>sentiment {{ c.sentiment.mean }}</span>
          </div>
          <div v-if="c.why_adjacent" class="why-adjacent">{{ c.why_adjacent }}</div>

          <!-- Chunks 2 & 3 enrichment badges -->
          <div class="enrichment-row">
            <span v-if="c.confidence" :class="['badge', `badge-conf-${c.confidence.level}`]" :title="c.confidence.reasons?.join('; ')">
              Confidence: {{ c.confidence.level }}
            </span>
            <span v-if="c.reach_estimate" class="badge badge-reach" :title="c.reach_estimate.caveats?.join('\n')">
              Reach ~{{ c.reach_estimate.estimated_reach.toLocaleString() }}
            </span>
            <span v-if="c.velocity" :class="['badge', `badge-vel-${c.velocity.momentum}`]">
              {{ c.velocity.momentum === 'rising' ? '↗' : c.velocity.momentum === 'declining' ? '↘' : '→' }}
              {{ c.velocity.momentum }}
            </span>
            <span v-if="c.cannibalization" :class="['badge', `badge-cann-${c.cannibalization.label}`]">
              {{ c.cannibalization.label.replace(/_/g, ' ') }}
            </span>
          </div>
          <div v-if="c.multi_platform_warning" class="multi-platform-warning">
            ⚠ Authors span {{ c.platform_breakdown.length }} platforms; cross-platform sums double-count
            (exact-hash matching only).
            <span class="muted">
              {{ c.platform_breakdown.map(p => `${p.platform}: ${p.n_authors}a`).join(' · ') }}
            </span>
          </div>

          <div class="community-terms">
            <span v-for="t in c.top_terms.slice(0, 8)" :key="t" class="term-pill">{{ t }}</span>
          </div>
          <details v-if="c.sample_posts?.length">
            <summary>Sample posts ({{ c.sample_posts.length }})</summary>
            <ul>
              <li v-for="(p, i) in c.sample_posts" :key="i">{{ p }}</li>
            </ul>
          </details>
          <details v-if="c.influencers?.length">
            <summary>Top influencers ({{ c.influencers.length }})</summary>
            <ul>
              <li v-for="(inf, i) in c.influencers" :key="i">
                <strong>{{ inf.display_name || inf.author_id.slice(0, 8) }}</strong>
                — {{ inf.posts_in_scope }} posts, {{ inf.total_engagement }} engagement
                <em>"{{ inf.sample_post }}"</em>
              </li>
            </ul>
          </details>
          <div class="card-actions">
            <button class="btn btn-primary btn-sm" :disabled="briefRunning === `cluster:${c.cluster_id}`"
                    @click="generateBrief(c, 'method_b_adjacent')">
              {{ briefRunning === `cluster:${c.cluster_id}` ? 'Generating brief…' : 'Generate Brief →' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── BRIEF MODAL ────────────────────────────────────── -->
    <div v-if="briefOpen" class="brief-modal" @click.self="closeBrief">
      <div class="brief-modal-inner">
        <div class="brief-modal-head">
          <div>
            <div class="brief-mod-eyebrow">Execution Brief</div>
            <div class="brief-mod-title">{{ activeBrief?.audience_label }}</div>
            <div class="brief-mod-sub">
              {{ activeBrief?.audience_size?.toLocaleString() }} authors · sentiment
              {{ activeBrief?.sentiment?.toFixed?.(3) ?? '0' }} ·
              {{ activeBrief?.source_method === 'method_b_adjacent' ? 'adjacent community' : 'competitor-only audience' }}
            </div>
          </div>
          <div class="brief-mod-actions">
            <button class="btn btn-secondary btn-sm" @click="copyMarkdown">{{ copyLabel }}</button>
            <button class="btn btn-secondary btn-sm" @click="downloadMarkdown">Download .md</button>
            <button class="btn btn-secondary btn-sm" @click="closeBrief">×</button>
          </div>
        </div>

        <div class="brief-mod-tabs">
          <button :class="['brief-tab', { active: briefTab === 'audience' }]" @click="briefTab = 'audience'">Audience</button>
          <button :class="['brief-tab', { active: briefTab === 'targeting' }]" @click="briefTab = 'targeting'">Targeting</button>
          <button :class="['brief-tab', { active: briefTab === 'creative' }]" @click="briefTab = 'creative'">Creative</button>
          <button :class="['brief-tab', { active: briefTab === 'markdown' }]" @click="briefTab = 'markdown'">Markdown</button>
        </div>

        <div class="brief-mod-body">
          <!-- AUDIENCE -->
          <div v-if="briefTab === 'audience'">
            <p v-if="activeBrief?.audience_summary" class="brief-summary">{{ activeBrief.audience_summary }}</p>
            <h4 v-if="activeBrief?.influencers?.length">Influencers</h4>
            <ul class="brief-list">
              <li v-for="(i, idx) in activeBrief?.influencers || []" :key="idx">
                <strong>{{ i.display_name || i.author_id.slice(0, 10) }}</strong>
                <span class="muted">({{ i.platform }})</span>
                — {{ i.posts_in_scope }} posts, {{ i.total_engagement?.toLocaleString() }} engagement
                <div v-if="i.sample_post" class="quote">"{{ i.sample_post }}"</div>
              </li>
            </ul>
            <h4 v-if="activeBrief?.sample_posts?.length">Verbatim sample posts</h4>
            <ul class="brief-list">
              <li v-for="(p, idx) in (activeBrief?.sample_posts || []).slice(0, 5)" :key="idx" class="quote">"{{ p }}"</li>
            </ul>
          </div>

          <!-- TARGETING -->
          <div v-if="briefTab === 'targeting' && activeBrief?.targeting">
            <h4>Meta</h4>
            <div class="kv"><strong>Interest stack:</strong> {{ activeBrief.targeting.meta?.interest_stack?.join(', ') }}</div>
            <div class="kv"><strong>Behaviors:</strong> {{ activeBrief.targeting.meta?.behaviors?.join(', ') }}</div>
            <div class="kv"><strong>Exclude:</strong> {{ activeBrief.targeting.meta?.exclusions?.join(', ') }}</div>
            <div class="kv"><strong>Placements:</strong> {{ activeBrief.targeting.meta?.recommended_placements?.join(', ') }}</div>

            <h4>Google</h4>
            <div class="kv"><strong>Search intent:</strong> {{ activeBrief.targeting.google?.search_intent }}</div>
            <div v-for="(theme, i) in activeBrief.targeting.google?.keyword_themes || []" :key="i" class="kv">
              <strong>{{ theme.theme }}:</strong> {{ (theme.keywords || []).join(', ') }}
            </div>
            <div class="kv"><strong>Negative keywords:</strong> {{ activeBrief.targeting.google?.negative_keywords?.join(', ') }}</div>

            <h4>TikTok</h4>
            <div v-for="(c, i) in activeBrief.targeting.tiktok?.creator_clusters || []" :key="i" class="kv">
              <strong>Creator cluster:</strong> {{ c }}
            </div>
            <div v-for="(stack, i) in activeBrief.targeting.tiktok?.hashtag_stacks || []" :key="i" class="kv">
              <strong>Hashtag stack:</strong> {{ stack.join(' ') }}
            </div>
            <div v-if="activeBrief.targeting.tiktok?.sound_trends?.length" class="kv">
              <strong>Sound trends:</strong> {{ activeBrief.targeting.tiktok.sound_trends.join(', ') }}
            </div>

            <h4>Lookalike</h4>
            <div class="kv"><strong>Seed source:</strong> {{ activeBrief.targeting.lookalike?.seed_source }}</div>
            <div class="kv"><strong>Lookalike size / geo:</strong> {{ activeBrief.targeting.lookalike?.seed_size_target }}</div>
            <div class="kv"><strong>Exclusion strategy:</strong> {{ activeBrief.targeting.lookalike?.exclusion_strategy }}</div>
          </div>

          <!-- CREATIVE -->
          <div v-if="briefTab === 'creative' && activeBrief?.creative">
            <h4>Hooks</h4>
            <ul class="brief-list"><li v-for="(h, i) in activeBrief.creative.top_hooks || []" :key="i">{{ h }}</li></ul>

            <h4>Pain points</h4>
            <ul class="brief-list"><li v-for="(p, i) in activeBrief.creative.pain_points || []" :key="i">{{ p }}</li></ul>

            <h4>Language patterns</h4>
            <ul class="brief-list"><li v-for="(l, i) in activeBrief.creative.language_patterns || []" :key="i" class="quote">"{{ l }}"</li></ul>

            <h4>Message angles</h4>
            <ol class="brief-list">
              <li v-for="(a, i) in activeBrief.creative.message_angles || []" :key="i" class="angle-item">
                <strong>{{ a.angle }}</strong>
                <span class="tonal">— {{ a.tonal_direction }}<span v-if="a.format"> · {{ a.format }}</span></span>
                <div v-if="a.example_copy" class="quote">"{{ a.example_copy }}"</div>
              </li>
            </ol>
          </div>

          <!-- MARKDOWN -->
          <div v-if="briefTab === 'markdown'">
            <pre class="brief-markdown">{{ activeBrief?.markdown_export }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ── METHOD C ───────────────────────────────────────── -->
    <div v-else class="card">
      <div class="card-label">Method C — Negative Space (competitor audiences)</div>
      <p class="hint">
        Identify authors active in competitors' online conversation but absent from this entity's
        corpus, plus an LLM-driven analysis of the positioning gap that explains why.
      </p>

      <div class="field">
        <label>Competitor entities (multi-select)</label>
        <select multiple v-model="competitorIds" class="multi-select">
          <option v-for="e in entities" :key="e.id" :value="e.id" v-show="e.id !== entityId">
            {{ e.name }}
          </option>
        </select>
      </div>
      <div class="field">
        <label class="check-label">
          <input type="checkbox" v-model="explain" /> LLM-generate positioning-gap analysis
        </label>
      </div>
      <div class="actions">
        <button class="btn btn-primary" :disabled="competitorIds.length === 0 || running" @click="runNegativeSpace">
          {{ running ? 'Analyzing…' : 'Discover Negative Space' }}
        </button>
      </div>

      <div v-if="error" class="error">{{ error }}</div>

      <div v-if="negativeResult" class="results">
        <h3>Audience overlap matrix</h3>
        <table class="overlap-table">
          <thead>
            <tr><th>Competitor</th><th>Authors</th><th>Shared</th><th>Jaccard</th><th>Competitor-only</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in negativeResult.overlap_matrix.pairs" :key="p.entity_id">
              <td>{{ p.name }}</td>
              <td>{{ p.n_authors }}</td>
              <td>{{ p.intersection }}</td>
              <td>{{ p.jaccard }}</td>
              <td>{{ p.competitor_only }}</td>
            </tr>
          </tbody>
        </table>

        <h3>Negative-space audiences</h3>
        <div v-for="aud in negativeResult.negative_space_audiences" :key="aud.competitor_entity_id" class="audience-card">
          <div class="audience-header">
            <span>{{ aud.competitor_name }}</span>
            <span class="muted">— {{ aud.n_authors_competitor_only }} unique authors not in your corpus
              ({{ Math.round(aud.coverage_gap_pct * 100) }}% gap)</span>
          </div>
          <!-- Chunks 2 & 3 enrichment badges -->
          <div class="enrichment-row">
            <span v-if="aud.confidence" :class="['badge', `badge-conf-${aud.confidence.level}`]" :title="aud.confidence.reasons?.join('; ')">
              Confidence: {{ aud.confidence.level }}
            </span>
            <span v-if="aud.reach_estimate" class="badge badge-reach" :title="aud.reach_estimate.caveats?.join('\n')">
              Reach ~{{ aud.reach_estimate.estimated_reach.toLocaleString() }}
            </span>
            <span v-if="aud.velocity" :class="['badge', `badge-vel-${aud.velocity.momentum}`]">
              {{ aud.velocity.momentum === 'rising' ? '↗' : aud.velocity.momentum === 'declining' ? '↘' : '→' }}
              {{ aud.velocity.momentum }}
            </span>
            <span v-if="aud.cannibalization" :class="['badge', `badge-cann-${aud.cannibalization.label}`]">
              {{ aud.cannibalization.label.replace(/_/g, ' ') }}
            </span>
          </div>
          <div v-if="aud.multi_platform_warning" class="multi-platform-warning">
            ⚠ Authors span {{ aud.platform_breakdown.length }} platforms; cross-platform sums double-count.
            <span class="muted">
              {{ aud.platform_breakdown.map(p => `${p.platform}: ${p.n_authors}a`).join(' · ') }}
            </span>
          </div>

          <div class="audience-terms">
            <span v-for="t in aud.top_terms.slice(0, 8)" :key="t" class="term-pill">{{ t }}</span>
          </div>
          <details v-if="aud.top_authors?.length">
            <summary>Top influencers ({{ aud.top_authors.length }})</summary>
            <ul>
              <li v-for="(inf, i) in aud.top_authors" :key="i">
                <strong>{{ inf.display_name || inf.author_id.slice(0, 8) }}</strong>
                — {{ inf.total_engagement }} engagement
                <em>"{{ inf.sample_post }}"</em>
              </li>
            </ul>
          </details>
          <div class="card-actions">
            <button class="btn btn-primary btn-sm" :disabled="briefRunning === `competitor:${aud.competitor_entity_id}`"
                    @click="generateBrief(aud, 'method_c_negative_space')">
              {{ briefRunning === `competitor:${aud.competitor_entity_id}` ? 'Generating brief…' : 'Generate Brief →' }}
            </button>
          </div>
        </div>

        <h3 v-if="negativeResult.positioning_gaps?.length">Positioning gaps</h3>
        <div v-for="gap in negativeResult.positioning_gaps" :key="gap.competitor_entity_id" class="gap-card">
          <div class="gap-header">{{ gap.competitor_name }}</div>
          <p class="gap-summary">{{ gap.gap_summary }}</p>
          <div class="gap-drivers">
            <strong>Drivers:</strong>
            <ul>
              <li v-for="(d, i) in gap.drivers" :key="i">{{ d }}</li>
            </ul>
          </div>
          <details>
            <summary>Evidence quotes</summary>
            <ul><li v-for="(q, i) in gap.evidence_quotes" :key="i"><em>"{{ q }}"</em></li></ul>
          </details>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { graph as graphApi } from '../api/graph.js'
import { audience as audienceApi } from '../api/audience.js'

const route = useRoute()
const entityId = route.params.id

const mode = ref('adjacent')
const entities = ref([])
const categoryEntityId = ref('')
const competitorIds = ref([])
const nClusters = ref(6)
const explain = ref(true)
const running = ref(false)
const error = ref('')
const adjacentResult = ref(null)
const negativeResult = ref(null)

// Brief modal state
const briefOpen = ref(false)
const activeBrief = ref(null)
const briefTab = ref('audience')
const briefRunning = ref('')          // identifier of currently-generating audience
const copyLabel = ref('Copy as Markdown')

onMounted(async () => {
  try {
    const r = await graphApi.listEntities()
    entities.value = r.data
  } catch { /* ignore */ }
})

async function runAdjacent() {
  running.value = true
  error.value = ''
  adjacentResult.value = null
  try {
    const r = await audienceApi.adjacent({
      target_entity_id: entityId,
      category_entity_id: categoryEntityId.value,
      n_clusters: nClusters.value,
      explain: explain.value,
    })
    adjacentResult.value = r.data
  } catch (e) {
    error.value = e.response?.data?.error || e.message
  } finally {
    running.value = false
  }
}

async function runNegativeSpace() {
  running.value = true
  error.value = ''
  negativeResult.value = null
  try {
    const r = await audienceApi.negativeSpace({
      target_entity_id: entityId,
      competitor_entity_ids: competitorIds.value,
      explain: explain.value,
    })
    negativeResult.value = r.data
  } catch (e) {
    error.value = e.response?.data?.error || e.message
  } finally {
    running.value = false
  }
}

// ────────────────────────────────────────────────────────
// Brief generation (Chunk 1 / actionability layer)
// ────────────────────────────────────────────────────────
async function generateBrief(audience, sourceMethod) {
  const id = sourceMethod === 'method_b_adjacent'
    ? `cluster:${audience.cluster_id}`
    : `competitor:${audience.competitor_entity_id}`
  briefRunning.value = id
  error.value = ''
  try {
    const r = await audienceApi.brief({
      target_entity_id: entityId,
      audience,
      source_method: sourceMethod,
    })
    activeBrief.value = r.data
    briefTab.value = 'audience'
    briefOpen.value = true
  } catch (e) {
    error.value = e.response?.data?.error || e.message
  } finally {
    briefRunning.value = ''
  }
}

function closeBrief() {
  briefOpen.value = false
  activeBrief.value = null
}

async function copyMarkdown() {
  const md = activeBrief.value?.markdown_export || ''
  if (!md) return
  try {
    await navigator.clipboard.writeText(md)
    copyLabel.value = 'Copied ✓'
    setTimeout(() => { copyLabel.value = 'Copy as Markdown' }, 1500)
  } catch {
    copyLabel.value = 'Copy failed'
    setTimeout(() => { copyLabel.value = 'Copy as Markdown' }, 1500)
  }
}

function downloadMarkdown() {
  const md = activeBrief.value?.markdown_export || ''
  const label = (activeBrief.value?.audience_label || 'audience').replace(/[^a-z0-9]/gi, '_').toLowerCase()
  const blob = new Blob([md], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `pulse_brief_${label}.md`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.view-header { margin-bottom: 20px; }
.view-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; letter-spacing: -0.4px; }
.view-subtitle { font-size: 13px; color: var(--text-muted); margin: 0; }

.mode-toggle {
  display: inline-flex; border: 1px solid var(--border-default);
  border-radius: var(--radius-md); overflow: hidden; margin-bottom: 16px;
}
.mode-btn {
  padding: 7px 18px; font-size: 13px; font-weight: 500; font-family: var(--font-sans);
  border: none; background: var(--bg-surface); color: var(--text-muted); cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.mode-btn:not(:last-child) { border-right: 1px solid var(--border-default); }
.mode-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.mode-btn.active { background: var(--text-primary); color: #fff; }

.card-label {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 1.1px; color: var(--text-faint); margin-bottom: 14px;
}
.hint { font-size: 13px; color: var(--text-muted); line-height: 1.6; margin: 0 0 16px; }
.hint em { color: var(--text-secondary); }

.field { margin-bottom: 14px; }
.field-row { display: flex; gap: 14px; }
.field label { display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
.field input, .field select { width: 100%; box-sizing: border-box; padding: 7px 10px; font-size: 13px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); }
.multi-select { min-height: 110px; }
.check-label { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); cursor: pointer; }

.actions { padding-top: 6px; }

.error {
  font-size: 12px; color: var(--negative); padding: 8px 0;
  border-top: 1px solid var(--border-subtle); margin-top: 12px;
}

.results { margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--border-subtle); }
.results-summary { font-size: 13px; color: var(--text-secondary); margin-bottom: 14px; }

.community-card, .audience-card, .gap-card {
  border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
  padding: 12px 14px; margin-bottom: 12px; background: var(--bg-canvas);
}
.community-header, .audience-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
.community-label, .audience-header > span:first-child { font-weight: 700; font-size: 14px; }
.community-score { font-family: var(--font-mono); font-size: 11px; color: var(--text-faint); }
.community-meta { font-size: 11px; color: var(--text-faint); display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.why-adjacent { font-size: 13px; color: var(--text-secondary); margin: 6px 0 10px; line-height: 1.55; }
.community-terms, .audience-terms { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.term-pill { font-size: 11px; padding: 2px 8px; background: var(--bg-overlay); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); color: var(--text-muted); font-family: var(--font-mono); }
.muted { color: var(--text-faint); font-weight: 400; margin-left: 6px; font-size: 12px; }

.overlap-table { width: 100%; font-size: 12px; border-collapse: collapse; margin-bottom: 16px; }
.overlap-table th, .overlap-table td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border-subtle); }
.overlap-table th { font-weight: 600; color: var(--text-secondary); }

.gap-card { background: var(--bg-surface); border-left: 3px solid var(--text-primary); }
.gap-header { font-weight: 700; font-size: 14px; margin-bottom: 6px; }
.gap-summary { font-size: 13px; color: var(--text-secondary); line-height: 1.55; }
.gap-drivers ul, details ul { margin: 4px 0 4px 16px; padding: 0; font-size: 12px; color: var(--text-secondary); }
details summary { cursor: pointer; color: var(--text-muted); font-size: 12px; margin-top: 6px; }

.card-actions {
  display: flex; justify-content: flex-end;
  margin-top: 10px; padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
}

/* Chunks 2 & 3 enrichment badges */
.enrichment-row {
  display: flex; gap: 6px; flex-wrap: wrap;
  margin: 8px 0 6px;
}
.badge {
  font-size: 10px; font-weight: 600;
  padding: 3px 9px; border-radius: 999px;
  font-family: var(--font-sans);
  letter-spacing: 0.2px; text-transform: capitalize;
  border: 1px solid transparent;
}
.badge-conf-high   { background: rgba(34,197,94,0.10); color: #15803d; border-color: rgba(34,197,94,0.25); }
.badge-conf-medium { background: rgba(234,179,8,0.10); color: #a16207; border-color: rgba(234,179,8,0.30); }
.badge-conf-low    { background: rgba(239,68,68,0.10); color: #b91c1c; border-color: rgba(239,68,68,0.25); }
.badge-reach       { background: var(--bg-overlay); color: var(--text-secondary); border-color: var(--border-subtle); }
.badge-vel-rising    { background: rgba(34,197,94,0.10); color: #15803d; border-color: rgba(34,197,94,0.25); }
.badge-vel-stable    { background: var(--bg-overlay); color: var(--text-muted); border-color: var(--border-subtle); }
.badge-vel-declining { background: rgba(239,68,68,0.10); color: #b91c1c; border-color: rgba(239,68,68,0.25); }
.badge-cann-net_new          { background: rgba(34,197,94,0.10); color: #15803d; border-color: rgba(34,197,94,0.25); }
.badge-cann-lookalike_likely { background: rgba(234,179,8,0.10); color: #a16207; border-color: rgba(234,179,8,0.30); }
.badge-cann-overlap_likely   { background: rgba(239,68,68,0.10); color: #b91c1c; border-color: rgba(239,68,68,0.25); }

.multi-platform-warning {
  font-size: 11px;
  color: #a16207;
  background: rgba(234,179,8,0.06);
  border: 1px solid rgba(234,179,8,0.25);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  margin: 6px 0;
  line-height: 1.45;
}
.multi-platform-warning .muted { color: var(--text-muted); font-weight: 400; }

/* Brief modal */
.brief-modal {
  position: fixed; inset: 0; background: rgba(0,0,0,0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000; padding: 24px;
}
.brief-modal-inner {
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  width: 100%; max-width: 780px;
  max-height: 88vh; display: flex; flex-direction: column;
  box-shadow: var(--shadow-lg, 0 12px 48px rgba(0,0,0,0.18));
}
.brief-modal-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 16px 20px; border-bottom: 1px solid var(--border-subtle);
}
.brief-mod-eyebrow {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 1.1px; color: var(--text-faint); margin-bottom: 4px;
}
.brief-mod-title { font-size: 18px; font-weight: 700; letter-spacing: -0.3px; }
.brief-mod-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.brief-mod-actions { display: flex; gap: 8px; align-items: center; }

.brief-mod-tabs {
  display: flex; gap: 4px;
  padding: 8px 16px; border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-canvas);
}
.brief-tab {
  padding: 6px 14px; font-size: 12px; font-weight: 500;
  border: none; background: transparent; color: var(--text-muted);
  cursor: pointer; border-radius: var(--radius-sm);
  font-family: var(--font-sans);
}
.brief-tab:hover { background: var(--bg-hover); color: var(--text-primary); }
.brief-tab.active { background: var(--text-primary); color: #fff; }

.brief-mod-body {
  padding: 16px 20px; overflow-y: auto; flex: 1;
}
.brief-summary {
  font-size: 14px; line-height: 1.6; color: var(--text-secondary);
  margin: 0 0 16px;
}
.brief-mod-body h4 {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 1.1px; color: var(--text-faint);
  margin: 18px 0 8px;
}
.brief-list { margin: 0 0 6px 18px; padding: 0; font-size: 13px; line-height: 1.55; color: var(--text-secondary); }
.brief-list li { margin-bottom: 6px; }
.angle-item { padding: 6px 0; }
.angle-item .tonal { color: var(--text-muted); font-weight: 400; font-size: 12px; }
.quote {
  font-size: 12px; color: var(--text-muted);
  font-style: italic; padding-left: 8px;
  border-left: 2px solid var(--border-default); margin: 4px 0;
}
.kv { font-size: 13px; color: var(--text-secondary); margin-bottom: 4px; line-height: 1.55; }
.kv strong { color: var(--text-primary); }

.brief-markdown {
  font-family: var(--font-mono);
  font-size: 11.5px;
  background: var(--bg-canvas);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 14px;
  overflow-x: auto;
  white-space: pre-wrap;
  color: var(--text-secondary);
  line-height: 1.55;
}
</style>
