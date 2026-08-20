import { createI18n } from 'vue-i18n'
import en from './locales/en.js'
import ru from './locales/ru.js'
import de from './locales/de.js'
import fr from './locales/fr.js'
import es from './locales/es.js'

const supportedLocales = ['en', 'ru', 'de', 'fr', 'es']
const demoQueryLocale = window.location.pathname.includes('/demo-authentic/')
  ? new URLSearchParams(window.location.search).get('lang')
  : ''
const initialLocale = supportedLocales.includes(demoQueryLocale)
  ? demoQueryLocale
  : (localStorage.getItem('sb_lang') || 'en')

// `silentFallbackWarn` keeps the prod console clean while keys still
// fall back to English when a non-English locale doesn't define them —
// the practical outcome is mixed-locale UI (translated where we have
// it, English otherwise) instead of raw `auth.identifier` literals on
// the page. `missingWarn` is on in dev so a key added to en.js but not
// propagated to es/fr/de surfaces immediately in the browser console.
const i18n = createI18n({
  legacy: false,
  locale: initialLocale,
  fallbackLocale: 'en',
  silentFallbackWarn: true,
  fallbackWarn: false,
  missingWarn: import.meta.env?.DEV ?? false,
  messages: { en, ru, de, fr, es },
})

export default i18n
