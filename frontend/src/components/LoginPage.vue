<script setup>
import { onMounted, ref } from "vue";
import BrandMark from "./BrandMark.vue";
import { buildApiUrl, fetchJson, getApiBase, postJson } from "../lib/api";
import { useBackendStatus } from "../lib/backendStatus";

const props = defineProps({
  initialError: {
    type: [String, Object],
    default: "",
  },
});
const emit = defineEmits(["login"]);
const apiBase = ref(getApiBase());
const { backendStatus, statusLabel, checkBackend } = useBackendStatus(apiBase);
const loginUsername = ref("");
const loginPassword = ref("");
const loginError = ref(typeof props.initialError === "string" ? props.initialError : "");
const loginLoading = ref(false);
const authProviders = ref({
  google: { configured: false },
  facebook: { configured: false },
});

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
      <span class="eyebrow">Espace Auralys</span>
      <h1>Bienvenue sur Auralys</h1>
    </div>

    <div class="login-grid login-grid-simple">
      <article class="panel login-panel login-panel-simple">
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
            <svg class="social-icon" viewBox="0 0 48 48" aria-hidden="true">
              <path fill="#4285F4" d="M45.12 24.5c0-1.56-.14-3.06-.4-4.5H24v8.51h11.84c-.51 2.75-2.06 5.08-4.39 6.64v5.52h7.11c4.16-3.83 6.56-9.47 6.56-16.17z" />
              <path fill="#34A853" d="M24 46c5.94 0 10.92-1.97 14.56-5.33l-7.11-5.52c-1.97 1.32-4.49 2.1-7.45 2.1-5.73 0-10.58-3.87-12.31-9.07H4.34v5.7C7.96 41.07 15.4 46 24 46z" />
              <path fill="#FBBC05" d="M11.69 28.18A13.9 13.9 0 0 1 10.9 24c0-1.45.25-2.86.79-4.18v-5.7H4.34A21.93 21.93 0 0 0 2 24c0 3.55.85 6.91 2.34 9.88z" />
              <path fill="#EA4335" d="M24 10.75c3.23 0 6.13 1.11 8.41 3.29l6.31-6.31C34.91 4.18 29.93 2 24 2 15.4 2 7.96 6.93 4.34 14.12l7.35 5.7c1.73-5.2 6.58-9.07 12.31-9.07z" />
            </svg>
            <span>Google</span>
          </button>
          <button
            class="social-login-button"
            type="button"
            :disabled="!authProviders.facebook.configured || backendStatus !== 'online'"
            @click="startSocialLogin('facebook')"
          >
            <svg class="social-icon" viewBox="0 0 48 48" aria-hidden="true">
              <path fill="#1877F2" d="M46 24c0-12.15-9.85-22-22-22S2 11.85 2 24c0 10.97 8.04 20.06 18.56 21.72V30.44h-5.59V24h5.59v-4.85c0-5.52 3.29-8.56 8.31-8.56 2.41 0 4.93.43 4.93.43v5.42h-2.78c-2.74 0-3.59 1.7-3.59 3.44V24h6.11l-.98 6.44h-5.13v15.28C37.96 44.06 46 34.97 46 24z" />
              <path fill="#ffffff" d="M31.98 30.44 32.96 24h-6.11v-4.12c0-1.74.85-3.44 3.59-3.44h2.78v-5.42s-2.52-.43-4.93-.43c-5.02 0-8.31 3.04-8.31 8.56V24h-5.59v6.44h5.59v15.28a22.2 22.2 0 0 0 6.88 0V30.44z" />
            </svg>
            <span>Facebook</span>
          </button>
        </div>


      </article>
    </div>
  </section>
</template>
