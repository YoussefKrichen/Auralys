<script setup>
defineProps({
  variant: {
    type: String,
    default: "light",
  },
});
</script>

<template>
  <div class="brand-mark" aria-label="Aromair x Auralys">
    <img
      class="brand-mark-image"
      :class="{ 'brand-mark-image-dark': variant === 'dark' }"
      src="/logo.png"
      alt="Aromair x Auralys"
    />
  </div>
</template>
