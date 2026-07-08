<script setup>
import { computed, ref, watch, nextTick } from "vue";
import LoginPage from "./components/LoginPage.vue";
import SavSpace from "./components/SavSpace.vue";
import CeoSpace from "./components/CeoSpace.vue";
import BrandMark from "./components/BrandMark.vue";
import { fetchJson, getApiBase } from "./lib/api";

function decodeAuthSession(value) {
  try {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const padding = (4 - (normalized.length % 4)) % 4;
    const padded = normalized + "=".repeat(padding);
    return JSON.parse(window.atob(padded));
  } catch {
    return null;
  }
}

const navigationByRole = {
  sav: [],
  ceo: [
    { key: "ceo-workspace", label: "Queue", detail: "" },
    { key: "ceo-discussion", label: "Discussion", detail: "Chat with Auralys" },
  ],
};

const apiBase = ref(getApiBase());
const urlParams = new URLSearchParams(window.location.search);
const callbackSession = urlParams.get("auth_session");
const callbackError = urlParams.get("auth_error");
const storedSession = JSON.parse(localStorage.getItem("auralys_session") || "null");
const currentSession = ref(callbackSession ? decodeAuthSession(callbackSession) : storedSession);
const authError = ref(callbackError || "");
const activeSection = ref("");
const savConversationHistory = ref([]);
const loadingSavConversationHistory = ref(false);
const selectedSavConversationKey = ref(localStorage.getItem("auralys_conversation_id") || "");
const savHistoryExpanded = ref(false);

const SAV_VISIBLE_HISTORY_COUNT = 5;

const primaryNavigation = computed(() => {
  if (!currentSession.value) return [];
  if (currentSession.value.role === "sav") {
    return [
      {
        key: "__new__",
        label: "New chat",
        detail: "",
        active: !selectedSavConversationKey.value,
      },
      ...savConversationHistory.value.map((row) => ({
        key: row.conversation_key,
        label: buildConversationLabel(row),
        detail: "",
        active: row.conversation_key === selectedSavConversationKey.value,
      })),
    ];
  }
  const items = navigationByRole[currentSession.value.role] || [];
  return items.map((item) => ({
    ...item,
    active: item.key === activeSection.value,
  }));
});

const savVisibleNavigation = computed(() => {
  if (currentSession.value?.role !== "sav") return primaryNavigation.value;
  const [newChatItem, ...historyItems] = primaryNavigation.value;
  const visibleHistoryItems = savHistoryExpanded.value
    ? historyItems
    : historyItems.slice(0, SAV_VISIBLE_HISTORY_COUNT);
  return [newChatItem, ...visibleHistoryItems].filter(Boolean);
});

const savHasHiddenHistory = computed(() => (
  currentSession.value?.role === "sav" && primaryNavigation.value.length - 1 > SAV_VISIBLE_HISTORY_COUNT
));

const welcomeTitle = computed(() => {
  if (!currentSession.value) return "";
  const displayName = currentSession.value.display_name || currentSession.value.username || "there";
  return `Hello ${displayName}`;
});

const welcomeSubtitle = computed(() => {
  if (!currentSession.value) return "";
  return currentSession.value.role === "sav"
    ? "Auralys is ready for support, diagnosis, voice input, and client context."
    : "Review queue and decisions.";
});

watch(
  currentSession,
  async (session) => {
    if (!session) {
      activeSection.value = "";
      savConversationHistory.value = [];
      selectedSavConversationKey.value = "";
      savHistoryExpanded.value = false;
      return;
    }
    activeSection.value = session.role === "sav" ? "sav-assistant" : "ceo-workspace";
    if (session.role === "sav") {
      selectedSavConversationKey.value = localStorage.getItem("auralys_conversation_id") || "";
      await loadSavConversationHistory();
    }
  },
  { immediate: true },
);

if (callbackSession && currentSession.value) {
  localStorage.setItem("auralys_session", JSON.stringify(currentSession.value));
}
if (callbackSession || callbackError) {
  window.history.replaceState({}, "", window.location.pathname);
}

function handleLogin(session) {
  currentSession.value = session;
  authError.value = "";
  savHistoryExpanded.value = false;
  localStorage.setItem("auralys_session", JSON.stringify(session));
}

function handleLogout() {
  currentSession.value = null;
  savHistoryExpanded.value = false;
  localStorage.removeItem("auralys_session");
}

async function handleNavigation(sectionKey) {
  if (currentSession.value?.role === "sav") {
    activeSection.value = "sav-assistant";
    selectedSavConversationKey.value = sectionKey === "__new__" ? "" : sectionKey;
    return;
  }
  activeSection.value = sectionKey;
  if (currentSession.value?.role === "ceo") {
    return;
  }
  await nextTick();
  document.getElementById(sectionKey)?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

async function loadSavConversationHistory() {
  if (currentSession.value?.role !== "sav") return;
  loadingSavConversationHistory.value = true;
  try {
    const params = new URLSearchParams({
      limit: "18",
      role: "sav",
      user_id: String(currentSession.value.id),
    });
    const payload = await fetchJson(`/conversations?${params.toString()}`, {}, apiBase.value);
    savConversationHistory.value = await enrichSavConversationRows(payload.rows || []);
  } catch {
    savConversationHistory.value = [];
  } finally {
    loadingSavConversationHistory.value = false;
  }
}

function handleSavConversationChange(conversationKey) {
  selectedSavConversationKey.value = conversationKey || "";
  void loadSavConversationHistory();
}

function buildConversationLabel(row) {
  const preview = sanitizeConversationTitle(row?.title || row?.preview || "");
  if (!preview) return "Untitled";
  return preview.length > 26 ? `${preview.slice(0, 26).trim()}...` : preview;
}

function toggleSavHistoryExpanded() {
  savHistoryExpanded.value = !savHistoryExpanded.value;
}

async function enrichSavConversationRows(rows) {
  const items = Array.isArray(rows) ? rows : [];
  const enriched = await Promise.all(items.map(async (row) => {
    if (sanitizeConversationTitle(row?.title || row?.preview || "")) return row;
    try {
      const payload = await fetchJson(
        `/conversations/${encodeURIComponent(row.conversation_key)}/messages?limit=20`,
        {},
        apiBase.value,
      );
      const firstUserMessage = (payload.rows || []).find((message) => message.sender === "user" && String(message.content || "").trim());
      const fallbackTitle = sanitizeConversationTitle(firstUserMessage?.content || "");
      if (!fallbackTitle) return row;
      return {
        ...row,
        title: fallbackTitle,
        preview: fallbackTitle,
      };
    } catch {
      return row;
    }
  }));
  return enriched;
}

function sanitizeConversationTitle(value) {
  let text = String(value || "").trim();
  for (const marker of ["Contexte image fourni:", "Image context provided:"]) {
    if (text.includes(marker)) {
      text = text.split(marker, 1)[0].trim();
    }
  }
  return text.replace(/\s+/g, " ").trim();
}
</script>

<template>
  <div class="app-shell" :class="{ 'app-shell-auth': currentSession }">
    <LoginPage v-if="!currentSession" :initial-error="authError" @login="handleLogin" />
    <template v-else>
      <aside class="dashboard-sidebar">
        <div class="sidebar-brand">
          <BrandMark />
          <div class="sidebar-brand-copy">
            <strong>Aromair</strong>
            <span>Auralys v1</span>
          </div>
        </div>

        <nav class="sidebar-nav" aria-label="Primary navigation">
          <button
            v-for="item in savVisibleNavigation"
            :key="item.key"
            class="sidebar-link"
            :class="{ active: item.active }"
            type="button"
            @click="handleNavigation(item.key)"
          >
            <span v-if="item.key === '__new__'" class="sidebar-link-icon" aria-hidden="true">+</span>
            <span class="sidebar-link-copy">
              <strong>{{ item.label }}</strong>
              <small v-if="item.detail">{{ item.detail }}</small>
            </span>
          </button>
          <button
            v-if="savHasHiddenHistory"
            class="sidebar-more-button"
            type="button"
            @click="toggleSavHistoryExpanded"
          >
            {{ savHistoryExpanded ? "See less" : "See more" }}
          </button>
        </nav>

        <div class="sidebar-user">
          <div>
            <strong>{{ currentSession.display_name }}</strong>
            <span>{{ currentSession.username }}</span>
          </div>
          <button class="ghost-button sidebar-switch-button" type="button" @click="handleLogout">
            Switch Space
          </button>
        </div>
      </aside>

      <section class="dashboard-main">
        <header class="dashboard-topbar">
          <div class="dashboard-topbar-copy">
            <h1>{{ welcomeTitle }}</h1>
            <p>{{ welcomeSubtitle }}</p>
          </div>

          <div class="dashboard-topbar-tools">
            <span class="meta-chip">{{ currentSession.role.toUpperCase() }}</span>
          </div>
        </header>

        <SavSpace
          v-if="currentSession.role === 'sav'"
          :user="currentSession"
          :selected-conversation-key="selectedSavConversationKey"
          :active-section="activeSection"
          @conversation-change="handleSavConversationChange"
          @logout="handleLogout"
        />
        <CeoSpace
          v-else
          :user="currentSession"
          :active-section="activeSection"
          @logout="handleLogout"
        />
      </section>
    </template>
  </div>
</template>
