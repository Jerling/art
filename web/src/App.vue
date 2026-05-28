<script setup>
import NavHeader from './components/NavHeader.vue'
</script>

<template>
  <div class="app-shell">
    <NavHeader />
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<style>
.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-main {
  flex: 1;
  display: flex;
  flex-direction: column;
}
</style>
