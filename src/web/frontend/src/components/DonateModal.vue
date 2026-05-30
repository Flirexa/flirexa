<script setup>
// DonateModal — second pass (2026-05-30): two-screen flow with amount
// picker + confetti success overlay. Replaces the prior single-screen
// GitHub-link variant.
//
// Payment back-end is intentionally a stub for now — clicking "Support
// with $X" just plays the success animation. The user will wire up
// Stripe / Patreon / whatever later; until then this is pure UI.
//
// Keeps the same v-model API as the old DonateModal so App.vue
// doesn't need to change:
//   <DonateModal v-model="open" @dismissed="..." />
//
// i18n strings live inline (DICT) instead of in the global locale files
// so this component stays self-contained — the only locale signal we
// need from the host app is `useI18n().locale.value` (or fall back to
// document.documentElement.lang). Languages bundled: ru / en / de / fr / es.

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'dismissed'])

const { locale } = useI18n()

const DICT = {
  ru: {
    title: 'Flirexa <span class="dm-accent">бесплатен</span> — и останется таким.',
    sub: 'Никакой рекламы, телеметрии или допродаж. Если Flirexa экономит ваше время или деньги — поддержите автора, который его делает и поддерживает.',
    f1: '<b>Open-core под MIT</b> — ваше навсегда',
    f2: 'Подписка не нужна для использования бесплатного тира',
    f3: 'Донаты идут на разработку, а не инвесторам',
    support: 'Поддержать',
    later: 'Может быть позже',
    s2Title: 'Поддержать разработку',
    s2Desc: 'Любая сумма помогает Flirexa оставаться свободным.',
    amount: 'Сумма',
    customPh: 'Своя сумма',
    commentLabel: 'Комментарий',
    optional: '— необязательно',
    commentPh: 'Скажите пару слов автору…',
    summary: 'К оплате',
    payTpl: 'Поддержать на ',
    payEmpty: 'Введите сумму',
    successTitle: 'Спасибо за поддержку!',
    successNote: (l) => `Ваш вклад ${l} и тёплые слова уже у автора`,
    successPlain: (l) => `Ваш вклад ${l} помогает Flirexa расти`,
    done: 'Готово',
  },
  en: {
    title: 'Flirexa is <span class="dm-accent">free</span> — and always will be.',
    sub: 'No ads, no telemetry, no upsells. If Flirexa saves you time or money — support the author who builds and maintains it.',
    f1: '<b>Open-core under MIT</b> — yours forever',
    f2: 'No subscription needed to use the free tier',
    f3: 'Donations go to development, not investors',
    support: 'Support',
    later: 'Maybe later',
    s2Title: 'Support development',
    s2Desc: 'Any amount helps keep Flirexa free.',
    amount: 'Amount',
    customPh: 'Custom amount',
    commentLabel: 'Comment',
    optional: '— optional',
    commentPh: 'Say a few words to the author…',
    summary: 'Total',
    payTpl: 'Support with ',
    payEmpty: 'Enter an amount',
    successTitle: 'Thank you for your support!',
    successNote: (l) => `Your ${l} and kind words are already with the author. Thank you!`,
    successPlain: (l) => `Your ${l} helps Flirexa grow. You're the best.`,
    done: 'Done',
  },
  de: {
    title: 'Flirexa ist <span class="dm-accent">kostenlos</span> — und bleibt es.',
    sub: 'Keine Werbung, keine Telemetrie, keine Upsells. Wenn Flirexa dir Zeit oder Geld spart — unterstütze den Autor, der es entwickelt und pflegt.',
    f1: '<b>Open-core unter MIT</b> — für immer deins',
    f2: 'Kein Abo nötig für die kostenlose Stufe',
    f3: 'Spenden gehen in die Entwicklung, nicht an Investoren',
    support: 'Unterstützen',
    later: 'Vielleicht später',
    s2Title: 'Entwicklung unterstützen',
    s2Desc: 'Jeder Betrag hilft Flirexa frei zu bleiben.',
    amount: 'Betrag',
    customPh: 'Eigener Betrag',
    commentLabel: 'Kommentar',
    optional: '— optional',
    commentPh: 'Schreib dem Autor ein paar Worte…',
    summary: 'Gesamt',
    payTpl: 'Unterstützen mit ',
    payEmpty: 'Betrag eingeben',
    successTitle: 'Danke für deine Unterstützung!',
    successNote: (l) => `Dein Beitrag ${l} und deine warmen Worte sind beim Autor angekommen.`,
    successPlain: (l) => `Dein Beitrag ${l} hilft Flirexa zu wachsen.`,
    done: 'Fertig',
  },
  fr: {
    title: 'Flirexa est <span class="dm-accent">gratuit</span> — et le restera.',
    sub: "Pas de pub, pas de télémétrie, pas de ventes additionnelles. Si Flirexa vous fait gagner du temps ou de l'argent — soutenez l'auteur qui le développe.",
    f1: "<b>Open-core sous MIT</b> — à vous pour toujours",
    f2: "Pas besoin d'abonnement pour le palier gratuit",
    f3: "Les dons vont au développement, pas aux investisseurs",
    support: 'Soutenir',
    later: 'Peut-être plus tard',
    s2Title: 'Soutenir le développement',
    s2Desc: 'Tout montant aide à garder Flirexa libre.',
    amount: 'Montant',
    customPh: 'Montant personnalisé',
    commentLabel: 'Commentaire',
    optional: '— optionnel',
    commentPh: 'Dites quelques mots à l\'auteur…',
    summary: 'Total',
    payTpl: 'Soutenir avec ',
    payEmpty: 'Entrez un montant',
    successTitle: 'Merci pour votre soutien !',
    successNote: (l) => `Votre don ${l} et vos mots gentils sont avec l'auteur.`,
    successPlain: (l) => `Votre don ${l} aide Flirexa à grandir.`,
    done: 'Terminé',
  },
  es: {
    title: 'Flirexa es <span class="dm-accent">gratis</span> — y siempre lo será.',
    sub: 'Sin anuncios, sin telemetría, sin ventas adicionales. Si Flirexa te ahorra tiempo o dinero — apoya al autor que lo crea y lo mantiene.',
    f1: '<b>Open-core bajo MIT</b> — tuyo para siempre',
    f2: 'No necesitas suscripción para usar el plan gratuito',
    f3: 'Las donaciones van al desarrollo, no a los inversores',
    support: 'Apoyar',
    later: 'Quizás más tarde',
    s2Title: 'Apoyar el desarrollo',
    s2Desc: 'Cualquier cantidad ayuda a mantener Flirexa libre.',
    amount: 'Cantidad',
    customPh: 'Cantidad personalizada',
    commentLabel: 'Comentario',
    optional: '— opcional',
    commentPh: 'Dile unas palabras al autor…',
    summary: 'Total',
    payTpl: 'Apoyar con ',
    payEmpty: 'Introduce una cantidad',
    successTitle: '¡Gracias por tu apoyo!',
    successNote: (l) => `Tu aporte ${l} y tus palabras ya están con el autor. ¡Gracias!`,
    successPlain: (l) => `Tu aporte ${l} ayuda a Flirexa a crecer.`,
    done: 'Listo',
  },
}

const dict = computed(() => DICT[locale.value] || DICT.en)

const PRESET_AMOUNTS = [3, 5, 10, 25]
const screen = ref(0)
const amount = ref(5)             // selected preset (mirrored to custom)
const customInput = ref('')       // raw user input — wins when non-empty
const comment = ref('')
const successShown = ref(false)
const confettiKey = ref(0)

const effectiveAmount = computed(() => {
  if (customInput.value) {
    const v = parseFloat(customInput.value)
    return Number.isFinite(v) && v > 0 ? v : 0
  }
  return amount.value
})

const formattedAmount = computed(() => {
  const v = effectiveAmount.value
  if (!v) return null
  return Number.isInteger(v) ? `$${v}` : `$${v.toFixed(2)}`
})

const payLabel = computed(() =>
  formattedAmount.value
    ? dict.value.payTpl + formattedAmount.value
    : dict.value.payEmpty
)

function selectPreset(v) {
  amount.value = v
  customInput.value = ''
}

function close() {
  emit('update:modelValue', false)
  emit('dismissed')
  // Reset state for next open.
  setTimeout(() => {
    screen.value = 0
    amount.value = 5
    customInput.value = ''
    comment.value = ''
    successShown.value = false
  }, 350)
}

function submit() {
  if (!effectiveAmount.value) return
  successShown.value = true
  confettiKey.value++           // re-mount confetti so anim restarts
}

function dismissSuccess() {
  successShown.value = false
  setTimeout(() => {
    screen.value = 0
    customInput.value = ''
    comment.value = ''
    amount.value = 5
  }, 320)
}

const successText = computed(() => {
  const l = formattedAmount.value || ''
  const fn = comment.value.trim() ? dict.value.successNote : dict.value.successPlain
  return fn(l)
})

// Lock background scroll while modal is open (matches the prior behaviour).
watch(() => props.modelValue, (open) => {
  if (typeof document === 'undefined') return
  document.body.style.overflow = open ? 'hidden' : ''
}, { immediate: true })

// Generate 22 confetti hearts, fresh on each success.
const confettiSprites = computed(() => {
  if (!confettiKey.value) return []
  const glyphs = ['♥', '♡', '✦']
  return Array.from({ length: 22 }, (_, i) => ({
    char: glyphs[i % glyphs.length],
    left: Math.random() * 100,
    size: 12 + Math.random() * 16,
    opacity: 0.5 + Math.random() * 0.5,
    duration: 1.8 + Math.random() * 1.8,
    delay: Math.random() * 0.6,
  }))
})
</script>

<template>
  <Teleport to="body">
    <Transition name="dm-fade">
      <div v-if="modelValue" class="dm-backdrop" @click.self="close" role="dialog" aria-modal="true">
        <!-- shared SVG gradient for the heart -->
        <svg width="0" height="0" style="position:absolute" aria-hidden="true">
          <defs>
            <linearGradient id="dmHeartGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#a5b4fc" />
              <stop offset="55%" stop-color="#6366f1" />
              <stop offset="100%" stop-color="#4f46e5" />
            </linearGradient>
          </defs>
        </svg>

        <div class="dm-modal">
          <button class="dm-close" :aria-label="dict.later" @click="close">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>

          <div class="dm-viewport">
            <div class="dm-track" :data-screen="screen">
              <!-- SCREEN 1 -->
              <section class="dm-screen">
                <div class="dm-heart-wrap">
                  <div class="dm-heart-stage">
                    <div class="dm-ring dm-r1"></div>
                    <div class="dm-ring dm-r2"></div>
                    <div class="dm-ring dm-r3"></div>
                    <div class="dm-heart-disc">
                      <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M12 21s-7.5-4.8-10-9.3C.6 9 1.4 5.6 4.3 4.4 6.4 3.5 8.7 4.2 10 6c.5.7.8 1 2 1s1.5-.3 2-1c1.3-1.8 3.6-2.5 5.7-1.6C22.6 5.6 23.4 9 22 11.7 19.5 16.2 12 21 12 21z" />
                      </svg>
                    </div>
                  </div>
                </div>

                <h1 class="dm-h1" v-html="dict.title"></h1>
                <p class="dm-sub">{{ dict.sub }}</p>

                <ul class="dm-features">
                  <li class="dm-feature">
                    <span class="dm-check">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
                    </span>
                    <span v-html="dict.f1"></span>
                  </li>
                  <li class="dm-feature">
                    <span class="dm-check">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
                    </span>
                    <span v-html="dict.f2"></span>
                  </li>
                  <li class="dm-feature">
                    <span class="dm-check">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
                    </span>
                    <span v-html="dict.f3"></span>
                  </li>
                </ul>

                <div class="dm-actions">
                  <button class="dm-btn-primary" @click="screen = 1">
                    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 21s-7.5-4.8-10-9.3C.6 9 1.4 5.6 4.3 4.4 6.4 3.5 8.7 4.2 10 6c.5.7.8 1 2 1s1.5-.3 2-1c1.3-1.8 3.6-2.5 5.7-1.6C22.6 5.6 23.4 9 22 11.7 19.5 16.2 12 21 12 21z"/></svg>
                    <span>{{ dict.support }}</span>
                  </button>
                  <button class="dm-btn-ghost" @click="close">{{ dict.later }}</button>
                </div>
              </section>

              <!-- SCREEN 2 -->
              <section class="dm-screen">
                <div class="dm-s2-head">
                  <button class="dm-back" :aria-label="'Back'" @click="screen = 0">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
                  </button>
                  <div>
                    <div class="dm-s2-title">{{ dict.s2Title }}</div>
                    <div class="dm-s2-desc">{{ dict.s2Desc }}</div>
                  </div>
                </div>

                <div class="dm-field">
                  <label class="dm-field-label">{{ dict.amount }}</label>
                  <div class="dm-amounts">
                    <button v-for="v in PRESET_AMOUNTS" :key="v" type="button"
                            class="dm-amount" :class="{ active: !customInput && amount === v }"
                            @click="selectPreset(v)">${{ v }}</button>
                  </div>
                  <div class="dm-custom-wrap">
                    <span class="dm-currency">$</span>
                    <input class="dm-custom" type="number" min="1" inputmode="decimal"
                           v-model="customInput" :placeholder="dict.customPh" />
                  </div>
                </div>

                <div class="dm-field">
                  <label class="dm-field-label">
                    <span>{{ dict.commentLabel }}</span>
                    <span class="dm-optional">{{ dict.optional }}</span>
                  </label>
                  <textarea class="dm-comment" v-model="comment" maxlength="180" :placeholder="dict.commentPh"></textarea>
                  <div class="dm-char-count">{{ comment.length }}/180</div>
                </div>

                <div class="dm-summary">
                  <span class="dm-lab">{{ dict.summary }}</span>
                  <span class="dm-val"><span class="dm-grad">{{ formattedAmount || '—' }}</span></span>
                </div>

                <button class="dm-btn-primary" :disabled="!effectiveAmount" @click="submit">
                  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 21s-7.5-4.8-10-9.3C.6 9 1.4 5.6 4.3 4.4 6.4 3.5 8.7 4.2 10 6c.5.7.8 1 2 1s1.5-.3 2-1c1.3-1.8 3.6-2.5 5.7-1.6C22.6 5.6 23.4 9 22 11.7 19.5 16.2 12 21 12 21z"/></svg>
                  <span>{{ payLabel }}</span>
                </button>
              </section>
            </div>
          </div>

          <!-- success overlay -->
          <Transition name="dm-success">
            <div v-if="successShown" class="dm-success-overlay">
              <div class="dm-confetti" :key="confettiKey">
                <span v-for="(s, i) in confettiSprites" :key="i"
                      :style="{
                        left: s.left + '%',
                        fontSize: s.size + 'px',
                        opacity: s.opacity,
                        animationDuration: s.duration + 's',
                        animationDelay: s.delay + 's',
                      }">{{ s.char }}</span>
              </div>
              <div class="dm-success-card">
                <div class="dm-tick">
                  <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
                </div>
                <h2>{{ dict.successTitle }}</h2>
                <p>{{ successText }}</p>
                <button class="dm-btn-ghost dm-restart" @click="dismissSuccess">{{ dict.done }}</button>
              </div>
            </div>
          </Transition>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
:root, .dm-modal {
  --dm-indigo-300: #a5b4fc;
  --dm-indigo-400: #818cf8;
  --dm-indigo-500: #6366f1;
  --dm-indigo-600: #4f46e5;
  --dm-grad: linear-gradient(135deg, #6366f1 0%, #818cf8 55%, #a78bfa 100%);
  --dm-ink: #f5f6fb;
  --dm-ink-dim: rgba(228, 231, 246, .66);
  --dm-ink-faint: rgba(214, 219, 242, .42);
  --dm-glass-edge: rgba(255, 255, 255, .10);
  --dm-ok: #4ade80;
  --dm-ok-dim: rgba(74, 222, 128, .16);
}

.dm-backdrop {
  position: fixed; inset: 0; z-index: 2050;
  display: grid; place-items: center; padding: 16px;
  background: rgba(8, 10, 22, .58);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
  font-family: 'Manrope', 'Helvetica Neue', Helvetica, system-ui, sans-serif;
  color: var(--dm-ink);
}

.dm-modal {
  position: relative; width: 440px; max-width: 100%;
  border-radius: 28px; overflow: hidden;
  background: linear-gradient(180deg, rgba(50,52,78,.50) 0%, rgba(26,27,42,.54) 60%, rgba(16,17,30,.60) 100%);
  border: 1px solid rgba(255,255,255,.16);
  box-shadow: 0 1px 0 rgba(255,255,255,.12) inset, 0 40px 90px -24px rgba(0,0,0,.65), 0 0 0 1px rgba(0,0,0,.15);
  backdrop-filter: blur(40px) saturate(165%); -webkit-backdrop-filter: blur(40px) saturate(165%);
}
.dm-modal::before {
  content: ""; position: absolute; inset: 0; pointer-events: none; border-radius: inherit;
  background: radial-gradient(120% 60% at 50% -12%, rgba(129,140,248,.22) 0%, transparent 60%);
}

.dm-close {
  position: absolute; top: 16px; right: 16px; z-index: 5;
  width: 34px; height: 34px; border-radius: 11px;
  display: grid; place-items: center;
  border: 1px solid transparent; background: transparent; cursor: pointer;
  color: var(--dm-ink-faint); transition: .2s ease;
}
.dm-close:hover { color: var(--dm-ink); background: rgba(255,255,255,.07); border-color: var(--dm-glass-edge); }
.dm-close svg { width: 17px; height: 17px; }

.dm-viewport { position: relative; overflow: hidden; }
.dm-track { display: flex; width: 200%; transition: transform .5s cubic-bezier(.65,0,.2,1); }
.dm-track[data-screen="1"] { transform: translateX(-50%); }
.dm-screen { width: 50%; flex: 0 0 50%; padding: 40px 36px 30px; }

.dm-heart-wrap { display: grid; place-items: center; margin: 6px 0 26px; }
.dm-heart-stage { position: relative; width: 116px; height: 116px; display: grid; place-items: center; }
.dm-ring {
  position: absolute; inset: 0; border-radius: 50%;
  border: 1.5px solid var(--dm-indigo-400);
  opacity: 0; transform: scale(.6);
  animation: dm-ripple 2.6s ease-out infinite;
}
.dm-r2 { animation-delay: .9s; }
.dm-r3 { animation-delay: 1.8s; }
@keyframes dm-ripple {
  0%   { opacity: .55; transform: scale(.55); }
  70%  { opacity: 0; }
  100% { opacity: 0; transform: scale(1.45); }
}
.dm-heart-disc {
  position: relative; width: 84px; height: 84px; border-radius: 50%;
  display: grid; place-items: center;
  background: radial-gradient(120% 120% at 30% 22%, rgba(165,180,252,.35), transparent 60%),
              linear-gradient(160deg, rgba(99,102,241,.30), rgba(67,70,200,.14));
  border: 1px solid rgba(165,180,252,.30);
  box-shadow: 0 12px 30px -8px rgba(79,70,229,.6), 0 0 0 8px rgba(99,102,241,.07);
}
.dm-heart-disc svg { width: 40px; height: 40px; filter: drop-shadow(0 4px 10px rgba(79,70,229,.55)); animation: dm-beat 1.5s ease-in-out infinite; }
.dm-heart-disc svg path { fill: url(#dmHeartGrad); }
@keyframes dm-beat {
  0%,100% { transform: scale(1); }
  14% { transform: scale(1.22); }
  28% { transform: scale(1); }
  42% { transform: scale(1.16); }
  56% { transform: scale(1); }
}

.dm-h1 { font-size: 25px; line-height: 1.18; font-weight: 800; letter-spacing: -.02em; text-align: center; color: var(--dm-ink); margin: 0; }
.dm-h1 :deep(.dm-accent) { background: var(--dm-grad); -webkit-background-clip: text; background-clip: text; color: transparent; }
.dm-sub { margin: 14px auto 0; max-width: 340px; text-align: center; font-size: 14.5px; line-height: 1.6; font-weight: 500; color: var(--dm-ink-dim); }

.dm-features { list-style: none; margin: 26px 0 0; padding: 0; display: flex; flex-direction: column; gap: 14px; }
.dm-feature { display: flex; gap: 12px; align-items: flex-start; font-size: 13.5px; line-height: 1.45; color: var(--dm-ink-dim); font-weight: 500; }
.dm-feature :deep(b) { color: var(--dm-ink); font-weight: 600; }
.dm-check { flex: 0 0 auto; width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; margin-top: -1px; background: var(--dm-ok-dim); color: var(--dm-ok); }
.dm-check svg { width: 12px; height: 12px; }

.dm-actions { margin-top: 30px; display: flex; flex-direction: column; gap: 6px; }
.dm-btn-primary {
  position: relative; width: 100%; height: 56px; border: 0; cursor: pointer; overflow: hidden;
  border-radius: 16px; font-family: inherit; font-size: 15.5px; font-weight: 700; color: #fff;
  background: var(--dm-grad);
  box-shadow: 0 14px 30px -10px rgba(79,70,229,.7), 0 1px 0 rgba(255,255,255,.25) inset;
  display: flex; align-items: center; justify-content: center; gap: 10px;
  transition: transform .15s ease, box-shadow .2s ease;
}
.dm-btn-primary::after {
  content: ""; position: absolute; top: 0; left: -60%; width: 45%; height: 100%;
  background: linear-gradient(110deg, transparent, rgba(255,255,255,.45), transparent);
  transform: skewX(-18deg); animation: dm-sheen 4.5s ease-in-out infinite;
}
@keyframes dm-sheen { 0%,70% { left: -60%; } 100% { left: 130%; } }
.dm-btn-primary:hover  { transform: translateY(-1px); box-shadow: 0 20px 40px -10px rgba(79,70,229,.85), 0 1px 0 rgba(255,255,255,.25) inset; }
.dm-btn-primary:active { transform: translateY(0) scale(.99); }
.dm-btn-primary:disabled { opacity: .45; cursor: not-allowed; filter: grayscale(.3); }
.dm-btn-primary:disabled::after { display: none; }
.dm-btn-primary:disabled:hover { transform: none; box-shadow: 0 14px 30px -10px rgba(79,70,229,.4); }
.dm-btn-primary svg { width: 18px; height: 18px; }

.dm-btn-ghost {
  width: 100%; height: 48px; border: 0; background: transparent; cursor: pointer;
  border-radius: 14px; font-family: inherit; font-size: 14px; font-weight: 600; color: var(--dm-ink-faint);
  transition: .2s ease;
}
.dm-btn-ghost:hover { color: var(--dm-ink-dim); background: rgba(255,255,255,.04); }

.dm-s2-head { display: flex; align-items: center; gap: 14px; margin-bottom: 24px; }
.dm-back {
  width: 38px; height: 38px; flex: 0 0 auto; border-radius: 12px; cursor: pointer;
  display: grid; place-items: center; border: 1px solid var(--dm-glass-edge);
  background: rgba(255,255,255,.04); color: var(--dm-ink-dim); transition: .2s ease;
}
.dm-back:hover { color: var(--dm-ink); background: rgba(255,255,255,.08); }
.dm-back svg { width: 16px; height: 16px; }
.dm-s2-title { font-size: 18px; font-weight: 800; letter-spacing: -.01em; color: var(--dm-ink); }
.dm-s2-desc  { font-size: 12.5px; color: var(--dm-ink-faint); font-weight: 500; margin-top: 2px; }

.dm-field { margin-bottom: 22px; }
.dm-field-label {
  font-size: 12px; font-weight: 700; letter-spacing: .02em; text-transform: uppercase;
  color: var(--dm-ink-faint); margin-bottom: 11px; display: block;
}
.dm-optional { text-transform: none; font-weight: 500; color: var(--dm-ink-faint); }

.dm-amounts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; margin-bottom: 12px; }
.dm-amount {
  height: 50px; border-radius: 13px; cursor: pointer; font-family: inherit;
  font-size: 15px; font-weight: 700; color: var(--dm-ink-dim);
  background: rgba(255,255,255,.04); border: 1.5px solid var(--dm-glass-edge);
  transition: .18s ease;
}
.dm-amount:hover  { border-color: rgba(129,140,248,.5); color: var(--dm-ink); }
.dm-amount.active {
  color: #fff; border-color: transparent;
  background: var(--dm-grad);
  box-shadow: 0 8px 20px -8px rgba(79,70,229,.7);
}

.dm-custom-wrap { position: relative; }
.dm-currency {
  position: absolute; left: 18px; top: 50%; transform: translateY(-50%);
  font-size: 17px; font-weight: 700; color: var(--dm-ink-faint); pointer-events: none;
}
.dm-custom, .dm-comment {
  width: 100%; font-family: inherit; color: var(--dm-ink); font-weight: 600;
  background: rgba(255,255,255,.04); border: 1.5px solid var(--dm-glass-edge);
  border-radius: 14px; transition: .18s ease; resize: none;
}
.dm-custom { height: 54px; padding: 0 18px 0 36px; font-size: 16px; }
.dm-comment { padding: 14px 18px; font-size: 14.5px; line-height: 1.5; min-height: 92px; font-weight: 500; }
.dm-custom::placeholder, .dm-comment::placeholder { color: var(--dm-ink-faint); font-weight: 500; }
.dm-custom:focus, .dm-comment:focus {
  outline: none; border-color: var(--dm-indigo-400);
  background: rgba(99,102,241,.08);
  box-shadow: 0 0 0 4px rgba(99,102,241,.16);
}
.dm-char-count { text-align: right; font-size: 11.5px; color: var(--dm-ink-faint); margin-top: 7px; font-weight: 500; }

.dm-summary {
  display: flex; align-items: baseline; justify-content: space-between;
  padding: 14px 18px; border-radius: 14px; margin-bottom: 16px;
  background: linear-gradient(135deg, rgba(99,102,241,.14), rgba(129,140,248,.06));
  border: 1px solid rgba(129,140,248,.22);
}
.dm-summary .dm-lab { font-size: 13px; font-weight: 600; color: var(--dm-ink-dim); }
.dm-summary .dm-val { font-size: 22px; font-weight: 800; letter-spacing: -.02em; }
.dm-summary .dm-grad {
  background: var(--dm-grad); -webkit-background-clip: text; background-clip: text; color: transparent;
}

/* Success overlay */
.dm-success-overlay {
  position: absolute; inset: 0; z-index: 20;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 40px 32px; text-align: center;
  background: linear-gradient(180deg, rgba(36,38,60,.55), rgba(16,17,30,.62));
  backdrop-filter: blur(24px) saturate(150%); -webkit-backdrop-filter: blur(24px) saturate(150%);
}
.dm-success-overlay h2 { font-size: 23px; font-weight: 800; color: var(--dm-ink); letter-spacing: -.02em; margin: 0; }
.dm-success-overlay p  { margin: 10px 0 0; font-size: 14px; color: var(--dm-ink-dim); font-weight: 500; line-height: 1.55; }
.dm-success-card { position: relative; z-index: 1; max-width: 100%; display: flex; flex-direction: column; align-items: center; }
.dm-tick {
  width: 84px; height: 84px; border-radius: 50%; display: grid; place-items: center; margin: 0 auto 22px;
  background: var(--dm-grad); box-shadow: 0 18px 40px -10px rgba(79,70,229,.8);
  animation: dm-pop .5s cubic-bezier(.16,1,.3,1) both;
}
@keyframes dm-pop { 0% { transform: scale(0); } 70% { transform: scale(1.12); } 100% { transform: scale(1); } }
.dm-tick svg { width: 40px; height: 40px; }
.dm-restart { margin-top: 26px; width: auto; padding: 0 22px; }

.dm-confetti { position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
.dm-confetti span {
  position: absolute; bottom: -20px; color: var(--dm-indigo-400);
  animation: dm-floatUp linear forwards;
}
@keyframes dm-floatUp {
  0%   { transform: translateY(0) rotate(0) scale(.6); opacity: 0; }
  15%  { opacity: 1; }
  100% { transform: translateY(-520px) rotate(220deg) scale(1.1); opacity: 0; }
}

/* Fade backdrop */
.dm-fade-enter-active, .dm-fade-leave-active { transition: opacity .25s ease; }
.dm-fade-enter-from,  .dm-fade-leave-to     { opacity: 0; }
.dm-fade-enter-active .dm-modal,
.dm-fade-leave-active .dm-modal { transition: transform .35s cubic-bezier(.16,1,.3,1), opacity .25s ease; }
.dm-fade-enter-from .dm-modal,
.dm-fade-leave-to   .dm-modal   { opacity: 0; transform: translateY(14px) scale(.96); }

.dm-success-enter-active, .dm-success-leave-active { transition: opacity .35s ease; }
.dm-success-enter-from,  .dm-success-leave-to     { opacity: 0; }

@media (max-width: 480px) {
  .dm-screen { padding: 36px 22px 24px; }
  .dm-modal  { border-radius: 24px; }
  .dm-h1     { font-size: 22px; }
}
</style>
