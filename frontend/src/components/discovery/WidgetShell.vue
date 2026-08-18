<template>
  <div
    class="widget-shell"
    :style="{
      left: widget.x + 'px',
      top:  widget.y + 'px',
      width: widget.w + 'px',
      height: widget.h + 'px',
      zIndex: widget.z || 1
    }"
    @mousedown.capture="bringToFront"
  >
    <!-- Title bar (drag handle) -->
    <div
      class="widget-titlebar"
      @mousedown.stop="$emit('start-drag', $event, widget)"
    >
      <span class="widget-icon">{{ widget.icon }}</span>
      <span class="widget-title">{{ widget.title }}</span>
      <div class="widget-controls">
        <button class="wctl wctl-reload" @click.stop="$emit('reload', widget)" title="Recarregar">↺</button>
        <button class="wctl wctl-close"  @click.stop="$emit('close', widget.id)" title="Fechar">✕</button>
      </div>
    </div>

    <!-- Content area -->
    <div class="widget-body">
      <slot />
    </div>

    <!-- Resize handle -->
    <div
      class="resize-handle"
      @mousedown.stop="$emit('start-resize', $event, widget)"
    />
  </div>
</template>

<script setup>
defineProps({ widget: { type: Object, required: true } })
defineEmits(['start-drag', 'start-resize', 'close', 'reload'])

function bringToFront() {
  // parent handles z-index via emit if needed
}
</script>

<style scoped>
.widget-shell {
  position: absolute;
  display: flex;
  flex-direction: column;
  background: #0e1420;
  border: 1px solid rgba(59, 130, 246, 0.18);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 24px rgba(0,0,0,0.5);
  min-width: 220px;
  min-height: 140px;
  transition: box-shadow 0.15s;
}
.widget-shell:hover {
  border-color: rgba(59, 130, 246, 0.35);
  box-shadow: 0 6px 32px rgba(0,0,0,0.6);
}

.widget-titlebar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background:
    linear-gradient(180deg, rgba(19, 27, 46, 0.98), rgba(15, 23, 42, 0.96));
  border-bottom: 1px solid rgba(59, 130, 246, 0.12);
  cursor: grab;
  user-select: none;
  flex-shrink: 0;
}
.widget-titlebar:active { cursor: grabbing; }

.widget-icon {
  display: inline-block;
  min-width: 0;
  padding: 0;
  background: transparent;
  border: none;
  box-shadow: none;
  color: #f7b955;
  font-family: "JetBrains Mono", "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: -0.08em;
  font-stretch: condensed;
  text-transform: uppercase;
  flex-shrink: 0;
  text-shadow: 0 0 12px rgba(247, 185, 85, 0.18);
  transform: scaleX(0.92);
  transform-origin: left center;
  line-height: 1;
}
.widget-title {
  flex: 1;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #94a3b8;
}

.widget-controls { display: flex; gap: 4px; }
.wctl {
  width: 20px; height: 20px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-size: 12px;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.1s, color 0.1s;
}
.wctl:hover { background: rgba(255,255,255,0.08); color: #e2e8f0; }
.wctl-close:hover { background: rgba(239,68,68,0.2); color: #f87171; }

.widget-body {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.resize-handle {
  position: absolute;
  bottom: 0; right: 0;
  width: 16px; height: 16px;
  cursor: se-resize;
  opacity: 0;
  transition: opacity 0.2s;
}
.widget-shell:hover .resize-handle { opacity: 1; }
.resize-handle::after {
  content: '';
  position: absolute;
  bottom: 4px; right: 4px;
  width: 8px; height: 8px;
  border-right: 2px solid rgba(99,102,241,0.6);
  border-bottom: 2px solid rgba(99,102,241,0.6);
  border-radius: 1px;
}
</style>
