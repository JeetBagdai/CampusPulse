import { create } from 'zustand'
import { api, wsUrl } from './api'

export const useStore = create((set, get) => ({
  campus: null,
  snap: null,
  connected: false,
  selected: null, // room or bin id
  copilotOpen: false,
  copilotSeed: null,
  demoOpen: false,
  phoneOpen: false,
  tourOn: false,
  welcomeOpen: false,

  init: async () => {
    if (get().campus || get().initing) return
    set({ initing: true })
    // retry until the backend is up (e.g. right after a restart)
    for (;;) {
      try {
        set({ campus: await api.get('/api/campus'), initing: false })
        break
      } catch {
        await new Promise((r) => setTimeout(r, 1500))
      }
    }
    get().connect()
  },

  connect: () => {
    const ws = new WebSocket(wsUrl('/ws/state'))
    ws.onopen = () => set({ connected: true })
    ws.onmessage = (e) => set({ snap: JSON.parse(e.data) })
    ws.onclose = () => {
      set({ connected: false })
      setTimeout(() => get().connect(), 1500)
    }
  },

  select: (id) => set({ selected: id }),
  openCopilot: (seed = null) => set({ copilotOpen: true, copilotSeed: seed }),
  closeCopilot: () => set({ copilotOpen: false, copilotSeed: null }),
  toggleDemo: () => set((s) => ({ demoOpen: !s.demoOpen })),
  togglePhone: () => set((s) => ({ phoneOpen: !s.phoneOpen })),
  setPhone: (open) => set({ phoneOpen: open }),
  startTour: () => set({ tourOn: true, welcomeOpen: false, demoOpen: false, copilotOpen: false }),
  stopTour: () => set({ tourOn: false }),
  setWelcome: (open) => set({ welcomeOpen: open }),
}))

export const STATUS_COLOR = {
  idle: '#6e6e6e', active: '#8ab4f8', energy: '#fb7185', water: '#3b82f6', underused: '#e8e8e8',
  litter: '#fbbf24', waste: '#fbbf24', fixed: '#34d399', ok: '#34d399',
}

export const TYPE_META = {
  ENERGY_WASTE: { label: 'Energy waste', color: '#fb7185' },
  WATER_LEAK: { label: 'Water leak', color: '#3b82f6' },
  BIN_OVERFLOW: { label: 'Bin overflow', color: '#fbbf24' },
  LITTER: { label: 'Litter', color: '#fbbf24' },
  UNDERUSED_BOOKING: { label: 'Underused booking', color: '#e8e8e8' },
}
