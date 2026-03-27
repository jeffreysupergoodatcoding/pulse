import api from './index.js'

export const ingestion = {
  pull: (body) => api.post('/ingestion/pull', body),
  getStatus: (taskId) => api.get(`/ingestion/status/${taskId}`),
  preview: (entityId) => api.get(`/ingestion/preview/${entityId}`),
  schedule: (body) => api.post('/ingestion/schedule', body),
  deleteSchedule: (scheduleId) => api.delete(`/ingestion/schedule/${scheduleId}`),
}
