<template>
  <div class="feature-locked">
    <div class="feature-locked__icon"><i class="mdi mdi-lock-outline"></i></div>
    <h3 class="feature-locked__title">{{ title }}</h3>
    <p class="feature-locked__desc">{{ description }}</p>
    <div class="feature-locked__tier-pill">{{ tierLabel }} tier</div>
    <button class="btn btn-primary mt-3" @click="upgrade">
      Upgrade to {{ tierLabel }}
    </button>
    <a :href="upgradeUrl" target="_blank" rel="noopener" class="d-block mt-2 small text-muted">
      View pricing →
    </a>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title:       { type: String, required: true },
  description: { type: String, required: true },
  tier:        { type: String, default: 'business' },
  feature:     { type: String, default: '' },
})

const tierLabel = computed(() =>
  props.tier.charAt(0).toUpperCase() + props.tier.slice(1)
)
const upgradeUrl = computed(() =>
  `https://flirexa.biz/#pricing`
)

function upgrade() {
  if (window.flirexaOpenUpgrade) {
    window.flirexaOpenUpgrade({ tier: props.tier, url: upgradeUrl.value, feature: props.feature })
    return
  }
  window.open(upgradeUrl.value, '_blank', 'noopener')
}
</script>

<style scoped>
.feature-locked {
  max-width: 480px;
  margin: 80px auto;
  padding: 40px 32px;
  background: var(--card-bg, #14171c);
  border: 1px solid var(--card-border, #232830);
  border-radius: 12px;
  text-align: center;
}
.feature-locked__icon  { font-size: 36px; margin-bottom: 12px; }
.feature-locked__title { margin: 0 0 8px; font-size: 22px; font-weight: 600; }
.feature-locked__desc  { color: var(--muted, #8a93a3); line-height: 1.5; margin: 0 0 16px; }
.feature-locked__tier-pill {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 999px;
  background: rgba(88, 101, 242, .12);
  color: #5865f2;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: .02em;
  text-transform: uppercase;
}
</style>
