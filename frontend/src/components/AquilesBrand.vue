<template>
  <div
    class="aquiles-brand"
    :class="[`variant-${variant}`, { clickable, 'icon-only': iconOnly }]"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
    @click="handleClick"
    @keydown.enter.prevent="handleClick"
    @keydown.space.prevent="handleClick"
  >
    <span class="aquiles-brand-mark-shell" aria-hidden="true">
      <img :src="aquilesIcon" alt="" class="aquiles-brand-mark" loading="eager" decoding="async" />
    </span>

    <span v-if="!iconOnly" class="aquiles-brand-copy">
      <strong class="aquiles-brand-name">{{ uppercase ? wordmark.toUpperCase() : wordmark }}</strong>
      <span v-if="subtitle" class="aquiles-brand-subtitle">{{ subtitle }}</span>
    </span>
  </div>
</template>

<script setup>
import aquilesIcon from '../assets/branding/aquiles-gladiator-icon.png'

const props = defineProps({
  variant: {
    type: String,
    default: 'header',
  },
  subtitle: {
    type: String,
    default: 'PLATAFORMA QUANT',
  },
  wordmark: {
    type: String,
    default: 'Aquiles',
  },
  uppercase: {
    type: Boolean,
    default: true,
  },
  iconOnly: {
    type: Boolean,
    default: false,
  },
  clickable: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['click'])

const handleClick = () => {
  if (props.clickable) emit('click')
}
</script>

<style scoped>
.aquiles-brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  color: inherit;
  user-select: none;
}

.aquiles-brand.clickable {
  cursor: pointer;
}

.aquiles-brand-mark-shell {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: 16px;
  border: 1px solid rgba(205, 213, 225, 0.24);
  background:
    radial-gradient(circle at 50% 34%, rgba(255, 255, 255, 0.18), transparent 42%),
    linear-gradient(180deg, #11151b 0%, #050608 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.08),
    0 16px 30px rgba(5, 8, 12, 0.22);
}

.aquiles-brand-mark {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.aquiles-brand-copy {
  display: inline-grid;
  gap: 2px;
  min-width: 0;
}

.aquiles-brand-name {
  font-family: 'Cormorant Garamond', serif;
  font-weight: 700;
  letter-spacing: 0.18em;
  line-height: 0.95;
  white-space: nowrap;
}

.aquiles-brand-subtitle {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.64rem;
  letter-spacing: 0.24em;
  opacity: 0.7;
  white-space: nowrap;
}

.variant-nav .aquiles-brand-mark-shell,
.variant-desk .aquiles-brand-mark-shell {
  width: 48px;
  height: 48px;
}

.variant-header .aquiles-brand-mark-shell {
  width: 38px;
  height: 38px;
  border-radius: 14px;
}

.variant-nav .aquiles-brand-name {
  font-size: 1.38rem;
}

.variant-desk .aquiles-brand-name {
  font-size: 1.16rem;
}

.variant-header .aquiles-brand-name {
  font-size: 1rem;
}

.variant-nav .aquiles-brand-subtitle {
  font-size: 0.62rem;
}

.variant-desk .aquiles-brand-subtitle,
.variant-header .aquiles-brand-subtitle {
  font-size: 0.58rem;
}

.icon-only {
  gap: 0;
}

.icon-only .aquiles-brand-mark-shell {
  width: 34px;
  height: 34px;
  border-radius: 12px;
}
</style>
