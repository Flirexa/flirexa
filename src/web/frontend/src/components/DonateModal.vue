<template>
  <Teleport to="body">
    <Transition name="donate-modal">
      <div v-if="modelValue" class="donate-backdrop" @click.self="close">
        <div class="donate-card" role="dialog" aria-modal="true" :aria-labelledby="titleId">
          <button class="donate-close" @click="close" :aria-label="$t('donate.close')">
            <i class="mdi mdi-close"></i>
          </button>

          <div class="donate-heart">
            <i class="mdi mdi-heart"></i>
          </div>

          <h3 :id="titleId" class="donate-title">{{ $t('donate.title') }}</h3>
          <p class="donate-lede">{{ $t('donate.lede') }}</p>

          <ul class="donate-points">
            <li><i class="mdi mdi-check-circle"></i><span>{{ $t('donate.point1') }}</span></li>
            <li><i class="mdi mdi-check-circle"></i><span>{{ $t('donate.point2') }}</span></li>
            <li><i class="mdi mdi-check-circle"></i><span>{{ $t('donate.point3') }}</span></li>
          </ul>

          <a
            :href="donateUrl"
            target="_blank"
            rel="noopener"
            class="donate-cta"
            @click="onCtaClick"
          >
            <i class="mdi mdi-github"></i>
            <span>{{ $t('donate.cta') }}</span>
            <i class="mdi mdi-arrow-top-right donate-cta-arrow"></i>
          </a>

          <button class="donate-later" @click="close">
            {{ $t('donate.later') }}
          </button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'dismissed'])

const donateUrl = 'https://github.com/Flirexa/flirexa#support-the-project'
const titleId = 'donate-modal-title-' + Math.random().toString(36).slice(2, 8)

function close() {
  emit('update:modelValue', false)
  emit('dismissed')
}
function onCtaClick() {
  // User clicked the donate CTA — count this as a "dismiss" so the
  // 7-day reminder doesn't fire again right away.
  emit('dismissed')
}
</script>

<style scoped>
.donate-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(8, 10, 18, .7);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  z-index: 2050;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.donate-card {
  position: relative;
  width: 100%;
  max-width: 460px;
  background: linear-gradient(180deg, var(--vxy-modal-bg, #1a1a25) 0%, var(--vxy-modal-bg-alt, #14141d) 100%);
  border: 1px solid rgba(255, 255, 255, .08);
  border-radius: 18px;
  padding: 36px 32px 28px;
  text-align: center;
  box-shadow: 0 30px 80px rgba(0, 0, 0, .45);
  color: var(--vxy-text, #e7e9ee);
}

.donate-close {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: transparent;
  border: 0;
  color: var(--vxy-text-muted, #9aa0ad);
  font-size: 1.2rem;
  cursor: pointer;
  transition: all .15s;
}
.donate-close:hover {
  background: rgba(255, 255, 255, .06);
  color: var(--vxy-text, #fff);
}

.donate-heart {
  width: 72px;
  height: 72px;
  margin: 0 auto 18px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, rgba(255, 90, 135, .25), rgba(255, 90, 135, .05));
  border: 1px solid rgba(255, 90, 135, .4);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ff5a87;
  font-size: 2rem;
  animation: donate-heart-pulse 2.4s ease-in-out infinite;
}
@keyframes donate-heart-pulse {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 90, 135, .35); }
  50%      { transform: scale(1.06); box-shadow: 0 0 0 14px rgba(255, 90, 135, 0); }
}

.donate-title {
  font-size: 1.45rem;
  font-weight: 800;
  margin: 0 0 8px;
  letter-spacing: -.01em;
}
.donate-lede {
  color: #ffffff;
  font-size: .95rem;
  line-height: 1.55;
  margin: 0 0 20px;
  opacity: .92;
}

.donate-points {
  list-style: none;
  padding: 0;
  margin: 0 auto 26px;
  text-align: left;
  display: inline-block;
}
.donate-points li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  font-size: .9rem;
  color: var(--vxy-text-secondary, #c5c8cf);
}
.donate-points i {
  color: #22c55e;
  font-size: 1.05rem;
  flex-shrink: 0;
}

.donate-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  padding: 14px 22px;
  background: linear-gradient(135deg, #ff5a87 0%, #b04bff 100%);
  color: #fff;
  border: 0;
  border-radius: 12px;
  font-size: .95rem;
  font-weight: 700;
  text-decoration: none;
  letter-spacing: .01em;
  cursor: pointer;
  transition: all .2s;
  box-shadow: 0 8px 24px rgba(255, 90, 135, .25);
}
.donate-cta:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 30px rgba(255, 90, 135, .35);
  color: #fff;
}
.donate-cta i.mdi-github {
  font-size: 1.2rem;
}
.donate-cta-arrow {
  font-size: .95rem;
  opacity: .85;
}

.donate-later {
  display: block;
  width: 100%;
  margin-top: 14px;
  padding: 10px 16px;
  background: transparent;
  border: 0;
  color: var(--vxy-text-muted, #9aa0ad);
  font-size: .85rem;
  cursor: pointer;
  transition: color .15s;
}
.donate-later:hover {
  color: var(--vxy-text, #fff);
}

/* Light theme adjustments via global var */
:global(.theme-light) .donate-card {
  background: linear-gradient(180deg, #ffffff 0%, #f8f9fc 100%);
  color: #1a1d23;
  border-color: rgba(0, 0, 0, .08);
  box-shadow: 0 30px 80px rgba(40, 50, 80, .15);
}
:global(.theme-light) .donate-lede {
  color: #1a1d23;
  opacity: 1;
}
:global(.theme-light) .donate-points li {
  color: #2c3038;
}

/* Transition */
.donate-modal-enter-active,
.donate-modal-leave-active {
  transition: opacity .25s ease;
}
.donate-modal-enter-active .donate-card,
.donate-modal-leave-active .donate-card {
  transition: transform .3s cubic-bezier(.34, 1.56, .64, 1), opacity .25s ease;
}
.donate-modal-enter-from,
.donate-modal-leave-to {
  opacity: 0;
}
.donate-modal-enter-from .donate-card,
.donate-modal-leave-to .donate-card {
  opacity: 0;
  transform: translateY(20px) scale(.95);
}
</style>
