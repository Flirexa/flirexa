// Design-variant switch: 'new' (the redesign, DEFAULT) | 'legacy' (the original
// UI, kept byte-for-byte). Persisted in localStorage. The App root renders the
// D2App tree when 'new', else the existing Sidebar/Navbar/router tree.
// Toggle lives in Settings → Interface ("Design mode": New / Legacy).
import { defineStore } from 'pinia'

const KEY = 'panel.designMode'

export const useDesignMode = defineStore('designMode', {
  state: () => ({
    mode: localStorage.getItem(KEY) || 'new', // NEW is the default
  }),
  getters: {
    isNew: (s) => s.mode === 'new',
    isLegacy: (s) => s.mode === 'legacy',
  },
  actions: {
    set(mode) {
      this.mode = mode === 'legacy' ? 'legacy' : 'new'
      localStorage.setItem(KEY, this.mode)
    },
    toggle() {
      this.set(this.isNew ? 'legacy' : 'new')
    },
  },
})
