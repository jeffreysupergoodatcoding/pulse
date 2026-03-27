import axios from 'axios'

const MAX_RETRIES = 5
const BASE_DELAY_MS = 500

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Attach retry metadata to every request
api.interceptors.request.use((config) => {
  config._retryCount = config._retryCount ?? 0
  return config
})

// Retry on network errors and 5xx responses with exponential backoff
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config
    if (!config) return Promise.reject(error)

    const status = error.response?.status
    const isRetryable =
      !status ||                          // network error (no response)
      status === 429 ||                   // rate limited
      (status >= 500 && status < 600)     // server error

    if (!isRetryable || config._retryCount >= MAX_RETRIES) {
      return Promise.reject(error)
    }

    config._retryCount += 1

    // Honour Retry-After header if present (seconds or HTTP-date)
    const retryAfter = error.response?.headers?.['retry-after']
    let delay = BASE_DELAY_MS * Math.pow(2, config._retryCount - 1)
    if (retryAfter) {
      const secs = parseInt(retryAfter, 10)
      if (!isNaN(secs)) delay = secs * 1000
    }

    await new Promise((r) => setTimeout(r, delay))
    return api(config)
  },
)

export default api
