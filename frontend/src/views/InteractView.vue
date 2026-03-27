<template>
  <div>
    <div class="flex" style="align-items:center;justify-content:space-between;margin-bottom:20px">
      <div class="section-title" style="margin-bottom:0">Interact</div>
      <div class="flex gap-2">
        <button class="btn btn-sm" :class="mode === 'report' ? 'btn-primary' : 'btn-secondary'" @click="mode = 'report'">
          ReportAgent
        </button>
        <button class="btn btn-sm" :class="mode === 'agent' ? 'btn-primary' : 'btn-secondary'" @click="mode = 'agent'">
          Agent Chat
        </button>
      </div>
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
</style>
