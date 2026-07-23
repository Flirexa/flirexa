import { createI18n } from 'vue-i18n'
import en from './locales/en.js'
import ru from './locales/ru.js'
import de from './locales/de.js'
import fr from './locales/fr.js'
import es from './locales/es.js'
// New-design (design2) translations — generated from the designer's reference,
// deep-merged so their namespaces (nav, clients, payments, …) don't clobber the
// Legacy keys. English uses the in-screen `|| 'fallback'` strings, so no en file.
import d2ru from './design2/ru.js'
import d2de from './design2/de.js'
import d2fr from './design2/fr.js'
import d2es from './design2/es.js'

// Deep-merge b into a (b wins on leaf collisions). Mutates+returns a.
function deepMerge(a, b) {
  for (const k of Object.keys(b)) {
    if (b[k] && typeof b[k] === 'object' && !Array.isArray(b[k])) {
      if (!a[k] || typeof a[k] !== 'object') a[k] = {}
      deepMerge(a[k], b[k])
    } else {
      a[k] = b[k]
    }
  }
  return a
}

deepMerge(ru, d2ru)
deepMerge(de, d2de)
deepMerge(fr, d2fr)
deepMerge(es, d2es)

const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem('sb_lang') || 'en',
  fallbackLocale: 'en',
  messages: { en, ru, de, fr, es },
})

export default i18n
