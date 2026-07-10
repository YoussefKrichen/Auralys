import { computed, ref } from "vue";
import { fetchJson } from "./api";

export function useBackendStatus(apiBase) {
  const backendStatus = ref("pending");

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
    return backendStatus.value;
  }

  return { backendStatus, statusLabel, checkBackend };
}
