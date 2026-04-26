import { createI18n } from 'vue-i18n'
import en from './locales/en.js'
import ru from './locales/ru.js'
import de from './locales/de.js'
import fr from './locales/fr.js'
import es from './locales/es.js'

const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem('sb_lang') || 'en',
  fallbackLocale: 'en',
  messages: { en, ru, de, fr, es },
})

export default i18n
