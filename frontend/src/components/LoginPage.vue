<script setup>
import { computed, onMounted, ref } from "vue";
import BrandMark from "./BrandMark.vue";
import { buildApiUrl, fetchJson, getApiBase, postJson } from "../lib/api";

const props = defineProps({
  initialError: {
    type: [String, Object],
    default: "",
  },
});
const emit = defineEmits(["login"]);
const apiBase = ref(getApiBase());
const backendStatus = ref("pending");
const loginUsername = ref("");
const loginPassword = ref("");
const loginError = ref(typeof props.initialError === "string" ? props.initialError : "");
const loginLoading = ref(false);
const authProviders = ref({
  google: { configured: false },
  facebook: { configured: false },
});

const statusLabel = computed(() => {
  if (backendStatus.value === "online") return "Connecte";
  if (backendStatus.value === "offline") return "Hors ligne";
  return "Verification...";
});

async function checkBackend() {
  backendStatus.value = "pending";
  try {
    const payload = await fetchJson("/health", {}, apiBase.value);
    backendStatus.value = payload.status === "ok" ? "online" : "offline";
  } catch {
    backendStatus.value = "offline";
  }
}

async function submitLogin() {
  if (!loginUsername.value.trim() || !loginPassword.value) {
    loginError.value = "Entrez votre username et votre mot de passe.";
    return;
  }
  loginLoading.value = true;
  loginError.value = "";
  try {
    const payload = await postJson(
      "/auth/login",
      {
        username: loginUsername.value.trim(),
        password: loginPassword.value,
      },
      {},
      apiBase.value,
    );
    loginPassword.value = "";
    emit("login", payload);
  } catch (error) {
    loginError.value = String(error.message || error);
  } finally {
    loginLoading.value = false;
  }
}

async function loadAuthProviders() {
  try {
    const payload = await fetchJson("/auth/providers", {}, apiBase.value);
    authProviders.value = payload.providers || authProviders.value;
  } catch {
    authProviders.value = {
      google: { configured: false },
      facebook: { configured: false },
    };
  }
}

function startSocialLogin(provider) {
  loginError.value = "";
  window.location.href = buildApiUrl(`/auth/${provider}/start`, apiBase.value);
}

onMounted(async () => {
  await Promise.all([checkBackend(), loadAuthProviders()]);
});
</script>

<template>
  <section class="login-hero">
    <div class="login-copy">
      <BrandMark variant="dark" />
      <span class="eyebrow">Auralys Workspace</span>
      <h1>Connexion</h1>
      <span class="login-luxe-note">Private operational access</span>
    </div>

    <div class="login-grid login-grid-simple">
      <article class="panel login-panel login-panel-simple">
        <div class="login-panel-head login-panel-head-simple">
          <div class="login-panel-title">
            <span class="meta-chip login-product-chip">Secure access</span>
          </div>
          <span class="meta-chip login-status-chip" :class="backendStatus">{{ statusLabel }}</span>
        </div>

        <label class="search-field">
          <span>Identifiant</span>
          <input v-model="loginUsername" type="text" placeholder="Votre username" @keydown.enter="submitLogin" />
        </label>

        <label class="search-field">
          <span>Mot de passe</span>
          <input v-model="loginPassword" type="password" placeholder="Votre mot de passe" @keydown.enter="submitLogin" />
        </label>

        <div v-if="loginError" class="message error-message">{{ loginError }}</div>

        <div class="login-submit-row">
          <button class="primary-button login-submit-button" :disabled="loginLoading || backendStatus !== 'online'" @click="submitLogin">
            {{ loginLoading ? "Connexion..." : "Se connecter" }}
          </button>
        </div>

        <div class="login-divider">
          <span>ou continuer avec</span>
        </div>

        <div class="social-login-row">
          <button
            class="social-login-button"
            type="button"
            :disabled="!authProviders.google.configured || backendStatus !== 'online'"
            @click="startSocialLogin('google')"
          >
            <span class="social-icon social-google" aria-hidden="true">G</span>
            <span>Google</span>
          </button>
          <button
            class="social-login-button"
            type="button"
            :disabled="!authProviders.facebook.configured || backendStatus !== 'online'"
            @click="startSocialLogin('facebook')"
          >
            <span class="social-icon social-facebook" aria-hidden="true">f</span>
            <span>Facebook</span>
          </button>
        </div>


      </article>
    </div>
  </section>
</template>
