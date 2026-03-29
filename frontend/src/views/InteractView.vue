<template>
  <div>
    <div class="view-header">
      <div>
        <h1 class="view-title">Chat</h1>
        <p class="view-subtitle">Interact with the ReportAgent or individual simulation agents</p>
      </div>
    </div>

    <!-- Mode tabs -->
    <div class="interact-tabs">
      <button
        class="interact-tab"
        :class="{ active: mode === 'report' }"
        @click="mode = 'report'"
      >
        ReportAgent
      </button>
      <button
        class="interact-tab"
        :class="{ active: mode === 'agent' }"
        @click="mode = 'agent'"
      >
        Agent Chat
      </button>
    </div>

    <!-- ReportAgent chat -->
    <div v-if="mode === 'report'">
      <AgentChat
        agent-name="ReportAgent"
        subtitle="Market intelligence analyst with full simulation context"
        :on-send="sendToReportAgent"
      />
    </div>

    <!-- Agent chat -->
    <div v-else>
      <div class="card mb-4" style="max-width:400px">
        <label>Select Agent ID</label>
        <div class="flex gap-2 mt-2">
          <input v-model="agentId" placeholder="Agent UUID or index (0, 1, 2…)" />
        </div>
        <div v-if="profiles.length" class="mt-2">
          <select v-model="agentId" style="width:100%">
            <option v-for="p in profiles.slice(0,20)" :key="p.user_id" :value="String(p.user_id)">
              {{ p.name }} ({{ p.archetype_id || 'agent' }})
            </option>
          </select>
        </div>
      </div>

      <AgentChat
        v-if="agentId"
        :agent-name="selectedAgentName"
        :subtitle="selectedAgentArchetype"
        :on-send="sendToAgent"
        :key="agentId"
      />
      <div v-else class="text-muted">Select an agent above to start chatting.</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { report as reportApi } from '../api/report.js'
import AgentChat from '../components/AgentChat.vue'

const route = useRoute()
const entityId = route.params.id
const reportId = route.params.rid
const mode = ref('report')
const agentId = ref('')
const profiles = ref([])

// Try to load profiles for the associated simulation
onMounted(async () => {
  const simId = localStorage.getItem(`sim_${entityId}`)
  if (!simId) return
  try {
    const resp = await fetch(`/api/simulation/${simId}/status`)
    const data = await resp.json()
    // Profiles live in the sim dir — we can't read them directly here.
    // Fall back to just letting the user type an agent id.
  } catch { /* ignore */ }
})

const selectedAgentName = computed(() => {
  const p = profiles.value.find(p => String(p.user_id) === agentId.value)
  return p?.name || `Agent ${agentId.value}`
})
const selectedAgentArchetype = computed(() => {
  const p = profiles.value.find(p => String(p.user_id) === agentId.value)
  return p?.archetype_id || ''
})

async function sendToReportAgent(message, history) {
  const r = await reportApi.chatReportAgent(reportId, { message, history })
  return r.data.response
}

async function sendToAgent(message, history) {
  const r = await reportApi.chatAgent(reportId, { agent_id: agentId.value, message, history })
  return r.data.response
}
</script>

<style scoped>
.mb-4 { margin-bottom: 16px; }

.interact-tabs {
  display: flex;
  gap: 2px;
  margin-bottom: 20px;
  background: var(--bg-overlay);
  border-radius: var(--radius-md);
  padding: 3px;
  width: fit-content;
}
.interact-tab {
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 500;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  background: none;
  color: var(--text-muted);
  transition: background var(--transition-fast), color var(--transition-fast);
}
.interact-tab:hover { color: var(--text-primary); }
.interact-tab.active {
  background: var(--bg-surface);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}
</style>
