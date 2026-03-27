import { createRouter, createWebHistory } from 'vue-router'

import HomeView       from '../views/HomeView.vue'
import IngestView     from '../views/IngestView.vue'
import GraphView      from '../views/GraphView.vue'
import PersonaView    from '../views/PersonaView.vue'
import SimulationView from '../views/SimulationView.vue'
import ReportView     from '../views/ReportView.vue'
import InteractView   from '../views/InteractView.vue'

const routes = [
  { path: '/',                                       name: 'home',       component: HomeView },
  { path: '/entity/:id/ingest',                      name: 'ingest',     component: IngestView },
  { path: '/entity/:id/graph',                       name: 'graph',      component: GraphView },
  { path: '/entity/:id/personas',                    name: 'personas',   component: PersonaView },
  { path: '/entity/:id/simulation',                  name: 'simulation', component: SimulationView },
  { path: '/entity/:id/report/:rid',                 name: 'report',     component: ReportView },
  { path: '/entity/:id/interact/:rid',               name: 'interact',   component: InteractView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
