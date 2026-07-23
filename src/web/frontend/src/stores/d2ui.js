// Topbar context for the new design. His topbar is contextual (title/subtitle +
// optional search + optional primary "+" action per screen). In our multi-view
// app each D2 screen pushes its context here on mount; D2Shell renders it.
import { defineStore } from 'pinia'

export const useD2Ui = defineStore('d2ui', {
  state: () => ({
    title: '',
    subtitle: '',
    search: '',
    searchPh: '',
    onSearch: null,      // fn(value) or null → no search box
    primary: null,       // { label, onClick } or null
    live: null,          // { on:boolean, toggle:fn } or null
  }),
  actions: {
    set(ctx) {
      this.title = ctx.title || ''
      this.subtitle = ctx.subtitle || ''
      this.searchPh = ctx.searchPh || ''
      this.onSearch = ctx.onSearch || null
      this.primary = ctx.primary || null
      this.live = ctx.live || null
      if (!ctx.keepSearch) this.search = ''
    },
    reset() { this.$reset() },
  },
})
