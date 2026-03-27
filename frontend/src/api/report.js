import api from './index.js'

export const report = {
  generate: (simulationId) => api.post('/report/generate', { simulation_id: simulationId }),
  getStatus: (reportId) => api.get(`/report/${reportId}/status`),
  getContent: (reportId) => api.get(`/report/${reportId}/content`),
  chatAgent: (reportId, body) => api.post(`/report/${reportId}/chat/agent`, body),
  chatReportAgent: (reportId, body) => api.post(`/report/${reportId}/chat/report_agent`, body),
  drilldown: (reportId, body) => api.post(`/report/${reportId}/drilldown`, body),
  signal: (reportId) => api.post(`/report/${reportId}/signal`),
}
