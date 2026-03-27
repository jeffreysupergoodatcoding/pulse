<template>
  <div class="chat-wrap">
    <div class="chat-header">
      <div class="avatar">{{ initials }}</div>
      <div>
        <div class="agent-name">{{ agentName }}</div>
        <div class="agent-sub">{{ subtitle }}</div>
      </div>
    </div>

    <div class="messages" ref="messagesRef">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="msg"
        :class="msg.role"
      >
        <div class="msg-bubble">{{ msg.content }}</div>
      </div>
      <div v-if="loading" class="msg assistant">
        <div class="msg-bubble typing">Thinking…</div>
      </div>
    </div>

    <div class="chat-input-row">
      <input
        v-model="input"
        :placeholder="`Message ${agentName}…`"
        @keydown.enter="send"
        :disabled="loading"
      />
      <button class="btn btn-primary btn-sm" @click="send" :disabled="loading || !input.trim()">Send</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'

const props = defineProps({
  agentName: { type: String, default: 'Agent' },
  subtitle: { type: String, default: '' },
  onSend: { type: Function, required: true },
})

const messages = ref([])
const input = ref('')
const loading = ref(false)
const messagesRef = ref(null)

const initials = computed(() => {
  return props.agentName.split(/\s+/).map(w => w[0]).join('').toUpperCase().slice(0, 2)
})

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: text })
  loading.value = true
  await scrollDown()
  try {
    const history = messages.value.slice(-10).map(m => ({ role: m.role, content: m.content }))
    const response = await props.onSend(text, history)
    messages.value.push({ role: 'assistant', content: response })
  } catch (err) {
    messages.value.push({ role: 'assistant', content: `Error: ${err.message}` })
  } finally {
    loading.value = false
    await scrollDown()
  }
}

async function scrollDown() {
  await nextTick()
  if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
}
</script>

<style scoped>
.chat-wrap {
  display: flex; flex-direction: column; height: 480px;
  background: var(--bg-raised);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.chat-header {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-surface);
}
.avatar {
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--accent);
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; color: var(--text-inverse); flex-shrink: 0;
}
.agent-name { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.agent-sub { font-size: 11px; color: var(--text-faint); }
.messages {
  flex: 1; overflow-y: auto; padding: 16px;
  display: flex; flex-direction: column; gap: 10px;
  background: var(--bg-canvas);
}
.msg { display: flex; }
.msg.user { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }
.msg-bubble {
  max-width: 75%; padding: 8px 12px;
  border-radius: var(--radius-md);
  font-size: 13px; line-height: 1.5;
}
.user .msg-bubble {
  background: var(--accent); color: var(--text-inverse);
  border-bottom-right-radius: 2px;
}
.assistant .msg-bubble {
  background: var(--bg-surface); color: var(--text-primary);
  border: 1px solid var(--border-subtle);
  border-bottom-left-radius: 2px;
}
.typing {
  color: var(--text-faint); font-style: italic;
  background: var(--bg-surface); border: 1px solid var(--border-subtle);
}
.chat-input-row {
  display: flex; gap: 8px; padding: 12px;
  border-top: 1px solid var(--border-subtle);
  background: var(--bg-raised);
}
.chat-input-row input { flex: 1; }
</style>
