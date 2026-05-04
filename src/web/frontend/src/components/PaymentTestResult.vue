<!--
  Inline checklist shown under a provider card after clicking "Test".
  Receives the result dict returned by POST /system/payment-test/{provider}:
    { provider, configured, checks: [{name, ok, detail}], passed, failed }
-->

<template>
  <div class="ptr-card" :class="result.failed === 0 ? 'ptr-pass' : 'ptr-fail'">
    <div class="ptr-head">
      <i class="mdi" :class="result.failed === 0 ? 'mdi-check-circle text-success' : 'mdi-alert-circle text-danger'"></i>
      <strong>
        {{ result.failed === 0
          ? `All ${result.passed} checks passed`
          : `${result.failed} check(s) failed, ${result.passed} passed` }}
      </strong>
    </div>

    <ul class="ptr-list">
      <li v-for="(c, i) in result.checks" :key="i" :class="c.ok ? 'ok' : 'fail'">
        <i class="mdi" :class="c.ok ? 'mdi-check' : 'mdi-close'"></i>
        <span class="ptr-name">{{ c.name }}</span>
        <span v-if="c.detail" class="ptr-detail text-muted">— {{ c.detail }}</span>
      </li>
    </ul>
  </div>
</template>

<script>
export default {
  name: 'PaymentTestResult',
  props: {
    result: { type: Object, required: true },
  },
}
</script>

<style scoped>
.ptr-card {
  margin-top: .6rem;
  padding: .65rem .85rem;
  border-radius: .5rem;
  border: 1px solid;
  font-size: .82rem;
  line-height: 1.45;
}
.ptr-pass {
  background: rgba(40, 199, 111, .08);
  border-color: rgba(40, 199, 111, .35);
}
.ptr-fail {
  background: rgba(234, 84, 85, .08);
  border-color: rgba(234, 84, 85, .35);
}
.ptr-head {
  display: flex;
  align-items: center;
  gap: .4rem;
  margin-bottom: .35rem;
}
.ptr-head .mdi { font-size: 1rem; }

.ptr-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: .15rem;
}
.ptr-list li {
  display: flex;
  align-items: flex-start;
  gap: .4rem;
}
.ptr-list li.ok .mdi { color: var(--vxy-success, #28C76F); }
.ptr-list li.fail .mdi { color: var(--vxy-danger, #EA5455); }
.ptr-list li .mdi { font-size: .95rem; flex-shrink: 0; margin-top: 2px; }
.ptr-name { color: inherit; }
.ptr-detail {
  font-size: .75rem;
  margin-left: .15rem;
  word-break: break-word;
}
</style>
