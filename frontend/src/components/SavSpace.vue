<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { buildApiUrl, fetchJson, getApiBase, postJson } from "../lib/api";
import { useBackendStatus } from "../lib/backendStatus";
import { formatMessage } from "../lib/formatMessage";
import { requestCurrentLocation } from "../lib/geolocation";
import { STORAGE_KEYS } from "../lib/storageKeys";

const props = defineProps({
  user: {
    type: Object,
    default: null,
  },
  selectedConversationKey: {
    type: String,
    default: "",
  },
});
const emit = defineEmits(["logout", "conversation-change"]);

const apiBase = ref(getApiBase());
const VOICE_AUTOPLAY_STORAGE_KEY = STORAGE_KEYS.voiceAutoplay;
const { backendStatus, statusLabel, checkBackend } = useBackendStatus(apiBase);
const ragQuery = ref("");
const ragLoading = ref(false);
const ragResponse = ref(null);
const ragError = ref("");
const ragStatus = ref(null);
const voiceSupported = ref(false);
const voiceUploadSupported = ref(false);
const voicePlaybackSupported = ref(false);
const voiceAutoplayEnabled = ref(readStoredBoolean(VOICE_AUTOPLAY_STORAGE_KEY, true));
const voicePlaybackPending = ref(false);
const microphonePermission = ref("unknown");
const locationPermission = ref("unknown");
const currentLocation = ref(null);
const requestingMicrophone = ref(false);
const voiceListening = ref(false);
const voiceError = ref("");
const voiceTranscriptPreview = ref("");
const voiceMode = ref("none");
const voiceStatusDetail = ref("Micro non accessible");
const audioUploadInput = ref(null);
const imageUploadInput = ref(null);
const selectedImageAttachment = ref(null);
const imageLightboxOpen = ref(false);
const holdToTalkActive = ref(false);
const liveTranscriptSupported = ref(false);
let speechRecognition = null;
let mediaRecorder = null;
let mediaStream = null;
let mediaChunks = [];
let audioContext = null;
let audioAnalyser = null;
let audioSourceNode = null;
let audioAnalysisTimer = null;
let activeAudioPlayer = null;
let activeAudioObjectUrl = null;
let playbackRequestToken = 0;
let lastSpeechDetectedAt = 0;
let speechDetectedOnce = false;
let speechRecognitionManuallyStopped = false;
let speechRecognitionRestartCount = 0;

const STREAMING_MAX_DURATION_MS = 15000;
const STREAMING_SILENCE_MS = 1200;
const STREAMING_MIN_SPEECH_MS = 400;
const STREAMING_RMS_THRESHOLD = 0.018;

const referenceCounts = ref({ clients: 0, addresses: 0, emplacements: 0 });
const clientDirectory = ref([]);
const historyRows = ref([]);
const historyLimit = ref(24);
const currentConversationId = ref(localStorage.getItem(STORAGE_KEYS.savConversationId) || "");
const agentPlan = ref(null);
const chatFeed = ref([]);
const chatFeedViewport = ref(null);
const promptInput = ref(null);

const emptyStateGreeting = computed(() => {
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Bonjour" : hour < 18 ? "Bon apres-midi" : "Bonsoir";
  const rawName = String(props.user?.display_name || props.user?.username || "").trim();
  const firstName = rawName.split(/\s+/)[0] || "";
  return firstName ? `${greeting}, ${firstName}` : greeting;
});

const historySummary = computed(() => {
  const groups = new Set(historyRows.value.map((row) => row.conversation_id || "sans-conversation"));
  return {
    rows: historyRows.value.length,
    conversations: groups.size,
  };
});

const emptyStateHint = computed(() => {
  if (backendStatus.value !== "online") return "Le serveur est hors ligne pour le moment.";
  const variants = historySummary.value.rows
    ? [
        "Reprenez une conversation SAV recente ou posez une nouvelle question.",
        "Continuez la ou vous en etiez.",
        "Ouvrez un nouveau dossier ou revenez sur un cas recent.",
      ]
    : [
        "Diagnostic, historique client, planning ou stock : je suis la pour vous aider.",
        "Decrivez le probleme, je m'occupe du reste.",
        "Posez votre question, je verifie les fiches et l'historique.",
      ];
  return variants[new Date().getDate() % variants.length];
});

const ragMetrics = computed(() => {
  if (!ragResponse.value) return [];
  const timings = ragResponse.value.timings || {};
  return [
    { label: "Source", value: ragResponse.value.response_source || "-" },
    { label: "Route", value: ragResponse.value.route || "-" },
    { label: "Preuves", value: String((ragResponse.value.hits || ragResponse.value.sources || []).length) },
    { label: "Latence", value: timings.total_ms ? `${formatNumber(timings.total_ms)} ms` : "-" },
    { label: "Conversation", value: ragResponse.value.conversation_id ? "active" : "-" },
  ];
});

const latestInsightConfidence = computed(() => {
  const sourceCount = (ragResponse.value?.hits || ragResponse.value?.sources || []).length;
  if (!sourceCount) return 68;
  return Math.min(97, 74 + sourceCount * 4);
});

const latestInsightSources = computed(() => {
  const sourceNames = ragResponse.value?.sources || [];
  if (sourceNames.length) {
    return sourceNames.slice(0, 3).map((source, index) => ({
      title: source,
      subtitle: "Agent source",
      confidence: Math.max(82, 96 - index * 4),
    }));
  }
  const hits = ragResponse.value?.hits || [];
  return hits.slice(0, 3).map((hit, index) => ({
    title: hit.title || hit.source_title || hit.document_title || hit.source || `Source ${index + 1}`,
    subtitle: hit.document_type || hit.chunk_type || hit.client_name || "Knowledge source",
    confidence: Math.max(82, 96 - index * 4),
  }));
});

const savWorkspaceCards = computed(() => [
  {
    label: "Service",
    value: statusLabel.value,
    detail: ragStatus.value?.llm_model || "Connexion en cours",
  },
  {
    label: "Clients",
    value: formatCompactNumber(referenceCounts.value.clients),
    detail: "Fiches disponibles",
  },
  {
    label: "Historique",
    value: formatCompactNumber(historySummary.value.rows),
    detail: `${historySummary.value.conversations} conversation${historySummary.value.conversations > 1 ? "s" : ""}`,
  },
  {
    label: "Micro",
    value: voiceSupported.value || voiceUploadSupported.value ? "Disponible" : "Indisponible",
    detail: voiceStatusDetail.value,
  },
]);

const displayedAgentActions = computed(() => {
  if (ragLoading.value && agentPlan.value?.actions?.length) {
    return agentPlan.value.actions;
  }
  return (ragResponse.value?.proposed_actions || []).map((action) => action.action_type);
});

const displayedAgentTools = computed(() => {
  if (ragLoading.value && agentPlan.value?.tools?.length) {
    return agentPlan.value.tools;
  }
  return ragResponse.value?.agent_tools || [];
});

const listeningStatus = computed(() => {
  if (voiceListening.value && voiceTranscriptPreview.value.trim()) {
    return "Streaming";
  }
  if (voiceListening.value) {
    return "Listening live";
  }
  if (voiceError.value) {
    return voiceError.value;
  }
  return "Ready";
});

const canRequestMicrophone = computed(() => canRecordWithBrowser());
const canReplayLatestAnswer = computed(() => {
  const text = (ragResponse.value?.spoken_text || ragResponse.value?.answer || "").trim();
  return Boolean(voicePlaybackSupported.value && text);
});
const voiceStatusChips = computed(() => [
  {
    label: "Input",
    value: voiceSupported.value ? "Live mic" : voiceUploadSupported.value ? "Upload only" : "Unavailable",
  },
  {
    label: "Mode",
    value: voiceMode.value === "recording" ? "Recorded capture" : "None",
  },
  {
    label: "Playback",
    value: voicePlaybackSupported.value ? "Enabled" : "Unavailable",
  },
]);

function readStoredBoolean(key, fallbackValue) {
  if (typeof window === "undefined") return fallbackValue;
  const raw = window.localStorage.getItem(key);
  if (raw === null) return fallbackValue;
  return raw === "1";
}

function persistVoiceAutoplayPreference() {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(VOICE_AUTOPLAY_STORAGE_KEY, voiceAutoplayEnabled.value ? "1" : "0");
}

async function loadRagStatus() {
  try {
    ragStatus.value = await fetchJson("/rag/status", {}, apiBase.value);
  } catch {
    ragStatus.value = null;
  }
}

function saveConversationState() {
  if (currentConversationId.value) {
    localStorage.setItem(STORAGE_KEYS.savConversationId, currentConversationId.value);
  } else {
    localStorage.removeItem(STORAGE_KEYS.savConversationId);
  }
}

function startNewConversation() {
  currentConversationId.value = "";
  saveConversationState();
  chatFeed.value = [];
}

function mapStoredMessageToChatEntry(row) {
  const text = String(row?.content || row?.transcript || "").trim();
  if (!text) return null;
  return {
    id: `stored-${row.id}`,
    role: row.sender === "assistant" ? "assistant" : "user",
    text,
    status: "done",
  };
}

function createAssistantPendingEntry() {
  return {
    id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role: "assistant",
    text: "Auralys prepare une reponse...",
    status: "pending",
    feedback: null,
  };
}

async function scrollChatFeedToEnd() {
  await nextTick();
  const node = chatFeedViewport.value;
  if (node) {
    node.scrollTop = node.scrollHeight;
  }
}

async function resizePromptInput() {
  await nextTick();
  const node = promptInput.value;
  if (!node) return;
  node.style.height = "0px";
  node.style.height = `${Math.min(node.scrollHeight, 220)}px`;
}

async function loadSavedConversation(conversationKey) {
  if (!conversationKey) {
    startNewConversation();
    return;
  }
  try {
    const payload = await fetchJson(
      `/conversations/${encodeURIComponent(conversationKey)}/messages?limit=120`,
      {},
      apiBase.value,
    );
    chatFeed.value = (payload.rows || []).map(mapStoredMessageToChatEntry).filter(Boolean);
    currentConversationId.value = conversationKey;
    await scrollChatFeedToEnd();
  } catch {
    chatFeed.value = [];
    currentConversationId.value = conversationKey;
  }
}

async function beginChatTurn(message, imageAttachment = null) {
  const trimmed = (message || "").trim();
  if (!trimmed) return null;
  chatFeed.value.push({
    id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role: "user",
    text: trimmed,
    status: "done",
    imageAttachment,
  });
  const pending = createAssistantPendingEntry();
  chatFeed.value.push(pending);
  await scrollChatFeedToEnd();
  return pending.id;
}

function resolveChatTurn(entryId, answer, fallbackError = "", citations = []) {
  const target = chatFeed.value.find((item) => item.id === entryId);
  if (!target) return;
  target.text = answer || fallbackError || "No response available.";
  target.status = answer ? "done" : "error";
  target.citations = answer ? citations || [] : [];
}

const suggestionChips = [
  "Diagnostiquer un probleme de diffuseur",
  "Historique du dernier client visite",
  "Prochaine destination SAV",
  "Alertes stock en cours",
];

function sendSuggestion(text) {
  if (ragLoading.value) return;
  ragQuery.value = text;
  void runRagQuery();
}

async function copyMessageText(text) {
  try {
    await navigator.clipboard.writeText(text || "");
  } catch {
    // Clipboard access can be denied by the browser; ignore silently.
  }
}

function speakMessage(entry) {
  void speakAnswer({ answer: entry.text }, { forcePlayback: true });
}

async function sendMessageFeedback(entry, rating) {
  if (!currentConversationId.value || entry.feedback) return;
  entry.feedback = rating;
  try {
    await postJson(
      "/agent/feedback",
      {
        conversation_key: currentConversationId.value,
        user_id: Number(props.user?.id || 1),
        rating,
      },
      {},
      apiBase.value,
    );
  } catch {
    entry.feedback = null;
  }
}

function buildAgentPreview(query) {
  const normalized = query.toLowerCase();
  if (normalized.includes("client") || normalized.includes("historique")) {
    return {
      message: "Agent is checking client history before answering.",
      tools: ["Operations data", "RAG tool"],
      actions: ["SEARCH_CLIENT_HISTORY"],
    };
  }
  if (normalized.includes("planning") || normalized.includes("destination") || normalized.includes("route")) {
    return {
      message: "Agent is preparing a SAV planning answer.",
      tools: ["Operations data", "Maps tool"],
      actions: ["RECOMMEND_ROUTE", "UPDATE_SAV_PLANNING"],
    };
  }
  if (normalized.includes("alerte") || normalized.includes("stock")) {
    return {
      message: "Agent is reviewing alerts and stock signals.",
      tools: ["Operations data"],
      actions: ["CREATE_LOW_RISK_ALERT"],
    };
  }
  return {
    message: "Agent is grounding the answer before replying.",
    tools: ["RAG tool"],
    actions: ["SEARCH_KNOWLEDGE"],
  };
}

function normalizeAgentResponse(payload) {
  const intent = payload.intent || "GENERAL_QUESTION";
  const toolsByIntent = {
    ASK_CLIENT_HISTORY: ["Operations data", "RAG tool"],
    ASK_NEXT_SAV_DESTINATION: ["Operations data", "Maps tool"],
    ASK_ALERTS: ["Operations data"],
    ASK_MAINTENANCE_PROBLEM: ["Operations data", "RAG tool"],
    ASK_DAILY_REPORT: ["Operations data"],
    ASK_STOCK_STATUS: ["Operations data"],
    GENERAL_QUESTION: ["RAG tool"],
  };
  return {
    ...payload,
    route: intent,
    response_source: "agent",
    agent_tools: toolsByIntent[intent] || ["RAG tool"],
    timings: payload.timings || {},
  };
}

async function submitRagQuery(message) {
  const imageAttachment = consumeSelectedImageAttachment();
  const submittedPrompt = buildSubmittedPrompt(message, imageAttachment);
  if (!submittedPrompt && !imageAttachment) return;
  const pendingEntryId = await beginChatTurn(submittedPrompt, imageAttachment);
  ragLoading.value = true;
  ragError.value = "";
  agentPlan.value = buildAgentPreview(submittedPrompt);
  try {
    const location = await refreshCurrentLocation();
    const payload = await postJson(
      "/agent/chat",
      {
        user_id: Number(props.user?.id || 1),
        role: props.user?.role || "sav",
        message: submittedPrompt,
        conversation_id: currentConversationId.value || null,
        context: {
          conversation_id: currentConversationId.value || null,
          ...(location ? { current_location: location } : {}),
        },
        images: imageAttachment ? [serializeImageAttachment(imageAttachment)] : [],
      },
      {},
      apiBase.value,
    );
    ragResponse.value = normalizeAgentResponse(payload);
    resolveChatTurn(pendingEntryId, ragResponse.value.answer, "", ragResponse.value.citations);
    void speakAnswer(ragResponse.value);
    if (payload.conversation_id) {
      currentConversationId.value = String(payload.conversation_id);
      saveConversationState();
    }
    await loadHistory();
    await resizePromptInput();
    await scrollChatFeedToEnd();
  } catch (error) {
    ragError.value = String(error.message || error);
    resolveChatTurn(pendingEntryId, "", ragError.value);
  } finally {
    ragLoading.value = false;
    agentPlan.value = null;
  }
}

async function runRagQuery() {
  if (!ragQuery.value.trim() && !selectedImageAttachment.value) return;
  const submittedPrompt = ragQuery.value.trim();
  ragQuery.value = "";
  await stopAnswerPlayback();
  await resizePromptInput();
  await submitRagQuery(submittedPrompt);
}

function openImageUploadPicker() {
  imageUploadInput.value?.click();
}

function buildSubmittedPrompt(message, imageAttachment) {
  const trimmed = (message || "").trim();
  if (trimmed) return trimmed;
  if (imageAttachment) return "Analyse cette image et aide-moi a partir de son contenu.";
  return "";
}

async function handleImageFileSelection(event) {
  const [file] = Array.from(event.target.files || []);
  event.target.value = "";
  if (!file || !file.type.startsWith("image/")) return;
  selectedImageAttachment.value = {
    name: file.name,
    mediaType: file.type,
    dataUrl: await readFileAsDataUrl(file),
  };
  await scrollChatFeedToEnd();
}

function clearSelectedImageAttachment() {
  selectedImageAttachment.value = null;
  imageLightboxOpen.value = false;
}

function openImageLightbox() {
  imageLightboxOpen.value = true;
}

function closeImageLightbox() {
  imageLightboxOpen.value = false;
}

function consumeSelectedImageAttachment() {
  const attachment = selectedImageAttachment.value;
  selectedImageAttachment.value = null;
  imageLightboxOpen.value = false;
  return attachment;
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Unable to read image file."));
    reader.readAsDataURL(file);
  });
}

function serializeImageAttachment(imageAttachment) {
  return {
    name: imageAttachment.name,
    media_type: imageAttachment.mediaType,
    data_url: imageAttachment.dataUrl,
  };
}

function isLocalhost(hostname) {
  return ["localhost", "127.0.0.1", "::1"].includes(hostname);
}

function hasSecureMicrophoneContext() {
  if (typeof window === "undefined") return false;
  if (window.isSecureContext) return true;
  return isLocalhost(window.location.hostname);
}

function canRecordWithBrowser() {
  return typeof window !== "undefined"
    && typeof window.MediaRecorder !== "undefined"
    && typeof navigator !== "undefined"
    && hasSecureMicrophoneContext()
    && Boolean(navigator.mediaDevices?.getUserMedia);
}

function canUploadAudioFromBrowser() {
  return typeof window !== "undefined"
    && typeof window.FormData !== "undefined"
    && typeof window.File !== "undefined";
}

function canPlaySpeechInBrowser() {
  return typeof window !== "undefined" && typeof window.Audio !== "undefined";
}

function getSpeechRecognitionConstructor() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

async function syncMicrophonePermission() {
  if (typeof navigator === "undefined" || !navigator.permissions?.query || !canRecordWithBrowser()) {
    microphonePermission.value = "unsupported";
    return;
  }
  try {
    const status = await navigator.permissions.query({ name: "microphone" });
    microphonePermission.value = status.state;
    status.onchange = () => {
      microphonePermission.value = status.state;
      setupVoiceRecognition();
    };
  } catch {
    microphonePermission.value = "unknown";
  }
}

async function syncLocationPermission() {
  if (typeof navigator === "undefined" || !navigator.permissions?.query || !navigator.geolocation) {
    locationPermission.value = "unsupported";
    return;
  }
  try {
    const status = await navigator.permissions.query({ name: "geolocation" });
    locationPermission.value = status.state;
    status.onchange = () => {
      locationPermission.value = status.state;
    };
  } catch {
    locationPermission.value = "unknown";
  }
}

async function refreshCurrentLocation() {
  const location = await requestCurrentLocation();
  currentLocation.value = location;
  if (location) {
    locationPermission.value = "granted";
  } else if (locationPermission.value === "unknown") {
    locationPermission.value = "denied";
  }
  return location;
}

async function stopVoiceInput() {
  holdToTalkActive.value = false;
  if (voiceMode.value === "recording" && mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    return;
  }
  await stopLiveTranscriptPreview();
  if (!speechRecognition && !mediaRecorder) {
    voiceListening.value = false;
  }
}

async function toggleVoiceInput() {
  if (voiceListening.value) {
    await stopVoiceInput();
    return;
  }
  if (holdToTalkActive.value || ragLoading.value) return;
  voiceError.value = "";
  voiceTranscriptPreview.value = "";
  holdToTalkActive.value = true;

  if (!voiceSupported.value) {
    if (canRequestMicrophone.value && microphonePermission.value !== "granted") {
      await requestMicrophoneAccess();
      if (!voiceSupported.value) {
        holdToTalkActive.value = false;
        return;
      }
    } else {
      voiceError.value = "La dictee vocale n'est pas disponible ici.";
      holdToTalkActive.value = false;
      return;
    }
  }

  // For hold-to-talk, recorded capture is more reliable than browser speech recognition.
  if (canRecordWithBrowser()) {
    voiceMode.value = "recording";
    voiceSupported.value = true;
    voiceStatusDetail.value = liveTranscriptSupported.value
      ? "Streaming mic + preview + transcription backend"
      : "Streaming mic + transcription backend";
    await startRecordedVoiceInput();
    return;
  }

  holdToTalkActive.value = false;
}

async function handleVoiceAnswerPayload(payload) {
  ragResponse.value = payload;
  const transcript = payload.transcript || "";
  if (transcript) {
    chatFeed.value.push({
      id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      role: "user",
      text: transcript,
      status: "done",
    });
  }
  chatFeed.value.push({
    id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role: "assistant",
    text: payload.answer || "No response available.",
    status: "done",
    feedback: null,
  });
  voiceTranscriptPreview.value = payload.transcript || "";
  if (payload.conversation_id) {
    currentConversationId.value = String(payload.conversation_id);
    saveConversationState();
  }
  void speakAnswer(ragResponse.value);
  await loadHistory();
  await scrollChatFeedToEnd();
}

async function uploadRecordedAudio(audioBlob) {
  const formData = new FormData();
  formData.append("audio", audioBlob, "voice-input.webm");
  if (currentConversationId.value) {
    formData.append("conversation_id", currentConversationId.value);
  }
  const response = await fetch(buildApiUrl("/ask-audio-upload", apiBase.value), {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function processUploadedAudio(file) {
  if (!file) return;
  voiceError.value = "";
  voiceTranscriptPreview.value = "Transcription en cours...";
  ragLoading.value = true;
  try {
    const payload = await uploadRecordedAudio(file);
    await handleVoiceAnswerPayload(payload);
  } catch (error) {
    voiceError.value = String(error.message || error);
    voiceTranscriptPreview.value = "";
  } finally {
    ragLoading.value = false;
  }
}

async function stopLiveTranscriptPreview() {
  speechRecognitionManuallyStopped = true;
  if (!speechRecognition) return;
  speechRecognition.onstart = null;
  speechRecognition.onresult = null;
  speechRecognition.onerror = null;
  speechRecognition.onend = null;
  try {
    speechRecognition.stop();
  } catch {
    // Ignore browser stop errors.
  }
  speechRecognition = null;
}

async function teardownAudioAnalysis() {
  if (audioAnalysisTimer) {
    window.clearInterval(audioAnalysisTimer);
    audioAnalysisTimer = null;
  }
  if (audioSourceNode) {
    audioSourceNode.disconnect();
    audioSourceNode = null;
  }
  if (audioAnalyser) {
    audioAnalyser.disconnect();
    audioAnalyser = null;
  }
  if (audioContext) {
    try {
      await audioContext.close();
    } catch {
      // Ignore close failures from already-closed contexts.
    }
    audioContext = null;
  }
}

async function cleanupMediaStream() {
  await stopLiveTranscriptPreview();
  await teardownAudioAnalysis();
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
  mediaRecorder = null;
  mediaChunks = [];
  holdToTalkActive.value = false;
}

function startLiveTranscriptPreview() {
  const RecognitionConstructor = getSpeechRecognitionConstructor();
  if (!RecognitionConstructor) return;

  speechRecognitionManuallyStopped = false;
  speechRecognitionRestartCount = 0;
  const recognition = new RecognitionConstructor();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "fr-FR";
  recognition.maxAlternatives = 1;
  recognition.onresult = (event) => {
    let finalText = "";
    let interimText = "";
    for (let index = 0; index < event.results.length; index += 1) {
      const result = event.results[index];
      const chunk = result[0]?.transcript?.trim() || "";
      if (!chunk) continue;
      if (result.isFinal) {
        finalText += `${chunk} `;
      } else {
        interimText += `${chunk} `;
      }
    }
    const previewText = `${finalText}${interimText}`.trim();
    if (previewText) {
      voiceTranscriptPreview.value = previewText;
    }
  };
  recognition.onerror = (event) => {
    const errorCode = String(event?.error || "");
    if (errorCode === "aborted" || errorCode === "no-speech") {
      return;
    }
    if (errorCode === "not-allowed" || errorCode === "service-not-allowed") {
      voiceError.value = "Le navigateur a bloque la previsualisation vocale en direct.";
    }
  };
  recognition.onend = () => {
    speechRecognition = null;
    if (
      !speechRecognitionManuallyStopped
      && voiceListening.value
      && mediaRecorder
      && mediaRecorder.state === "recording"
      && speechRecognitionRestartCount < 2
    ) {
      speechRecognitionRestartCount += 1;
      startLiveTranscriptPreview();
    }
  };
  speechRecognition = recognition;
  recognition.start();
}

async function setupAudioStreamingAnalysis() {
  if (typeof window === "undefined" || typeof window.AudioContext === "undefined") {
    return;
  }
  audioContext = new window.AudioContext();
  audioAnalyser = audioContext.createAnalyser();
  audioAnalyser.fftSize = 2048;
  audioSourceNode = audioContext.createMediaStreamSource(mediaStream);
  audioSourceNode.connect(audioAnalyser);
  const frame = new Uint8Array(audioAnalyser.fftSize);
  const startedAt = Date.now();
  lastSpeechDetectedAt = startedAt;
  speechDetectedOnce = false;

  audioAnalysisTimer = window.setInterval(async () => {
    if (!audioAnalyser || !mediaRecorder || mediaRecorder.state !== "recording") return;
    audioAnalyser.getByteTimeDomainData(frame);
    let sumSquares = 0;
    for (let index = 0; index < frame.length; index += 1) {
      const normalized = (frame[index] - 128) / 128;
      sumSquares += normalized * normalized;
    }
    const rms = Math.sqrt(sumSquares / frame.length);
    const now = Date.now();
    if (rms >= STREAMING_RMS_THRESHOLD) {
      lastSpeechDetectedAt = now;
      speechDetectedOnce = true;
    }
    const recordingDuration = now - startedAt;
    const silenceDuration = now - lastSpeechDetectedAt;
    const hasReachedMaxDuration = recordingDuration >= STREAMING_MAX_DURATION_MS;
    const shouldAutoStop = speechDetectedOnce
      && recordingDuration >= STREAMING_MIN_SPEECH_MS
      && silenceDuration >= STREAMING_SILENCE_MS;
    if (shouldAutoStop || hasReachedMaxDuration) {
      await stopVoiceInput();
    }
  }, 150);
}

async function startRecordedVoiceInput() {
  voiceError.value = "";
  voiceTranscriptPreview.value = "";
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaChunks = [];
    mediaRecorder = new MediaRecorder(mediaStream);
    mediaRecorder.onstart = () => {
      voiceListening.value = true;
      if (liveTranscriptSupported.value) {
        startLiveTranscriptPreview();
      }
    };
    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        mediaChunks.push(event.data);
      }
    };
    mediaRecorder.onerror = () => {
      voiceListening.value = false;
      voiceError.value = "Erreur lors de l'enregistrement du microphone.";
    };
    mediaRecorder.onstop = async () => {
      voiceListening.value = false;
      const mimeType = mediaRecorder?.mimeType || "audio/webm";
      const audioBlob = new Blob(mediaChunks, { type: mimeType });
      await cleanupMediaStream();
      if (!audioBlob.size) {
        voiceError.value = "Aucun audio n'a ete capture.";
        return;
      }
      ragLoading.value = true;
      voiceTranscriptPreview.value = "Transcription en cours...";
      try {
        const payload = await uploadRecordedAudio(audioBlob);
        await handleVoiceAnswerPayload(payload);
      } catch (error) {
        voiceError.value = String(error.message || error);
        voiceTranscriptPreview.value = "";
      } finally {
        ragLoading.value = false;
      }
    };
    await setupAudioStreamingAnalysis();
    mediaRecorder.start(250);
  } catch {
    voiceListening.value = false;
    voiceError.value = "Le microphone n'est pas accessible dans ce navigateur.";
    await cleanupMediaStream();
  }
}

async function requestMicrophoneAccess() {
  if (!canRecordWithBrowser()) {
    voiceError.value = "Le micro navigateur n'est disponible que sur localhost, 127.0.0.1 ou HTTPS.";
    return;
  }
  requestingMicrophone.value = true;
  voiceError.value = "";
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => track.stop());
    microphonePermission.value = "granted";
    setupVoiceRecognition();
  } catch (error) {
    microphonePermission.value = "denied";
    const message = String(error?.name || error || "");
    if (message.includes("NotAllowedError") || message.includes("PermissionDeniedError")) {
      voiceError.value = "Autorisation micro refusee. Autorisez le micro dans le navigateur puis reessayez.";
    } else if (message.includes("NotFoundError")) {
      voiceError.value = "Aucun microphone detecte sur cet appareil.";
    } else {
      voiceError.value = "Impossible d'activer le microphone dans ce navigateur.";
    }
  } finally {
    requestingMicrophone.value = false;
  }
}

async function initializeActiveMicrophone() {
  if (!canRecordWithBrowser()) return;
  if (microphonePermission.value === "denied" || microphonePermission.value === "granted") return;
  await requestMicrophoneAccess();
}

function openAudioUploadPicker() {
  audioUploadInput.value?.click();
}

async function handleAudioFileSelection(event) {
  const [file] = Array.from(event.target.files || []);
  event.target.value = "";
  await processUploadedAudio(file);
}

async function clearAnswerPlayback() {
  if (activeAudioPlayer) {
    activeAudioPlayer.pause();
    activeAudioPlayer.src = "";
    activeAudioPlayer = null;
  }
  if (activeAudioObjectUrl) {
    URL.revokeObjectURL(activeAudioObjectUrl);
    activeAudioObjectUrl = null;
  }
}

async function stopAnswerPlayback() {
  playbackRequestToken += 1;
  voicePlaybackPending.value = false;
  await clearAnswerPlayback();
}

async function toggleVoiceAutoplay() {
  voiceAutoplayEnabled.value = !voiceAutoplayEnabled.value;
  persistVoiceAutoplayPreference();
  voiceError.value = "";
  if (!voiceAutoplayEnabled.value) {
    await stopAnswerPlayback();
  }
}

function playLatestAnswer() {
  void speakAnswer(ragResponse.value, { forcePlayback: true });
}

async function speakAnswer(responsePayload = ragResponse.value, options = {}) {
  const forcePlayback = Boolean(options.forcePlayback);
  if (!voicePlaybackSupported.value || !responsePayload) return;
  if (!voiceAutoplayEnabled.value && !forcePlayback) return;
  const text = (responsePayload.spoken_text || responsePayload.answer || "").trim();
  if (!text) return;
  const requestToken = ++playbackRequestToken;
  voicePlaybackPending.value = true;
  try {
    const response = await fetch(buildApiUrl("/speak-audio", apiBase.value), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const audioBlob = await response.blob();
    if (requestToken !== playbackRequestToken) return;
    await clearAnswerPlayback();
    activeAudioObjectUrl = URL.createObjectURL(audioBlob);
    activeAudioPlayer = new Audio(activeAudioObjectUrl);
    activeAudioPlayer.onended = () => {
      void clearAnswerPlayback();
    };
    voiceError.value = "";
    await activeAudioPlayer.play();
  } catch (error) {
    if (requestToken === playbackRequestToken) {
      voiceError.value = `Lecture audio impossible: ${String(error.message || error)}`;
    }
  } finally {
    if (requestToken === playbackRequestToken) {
      voicePlaybackPending.value = false;
    }
  }
}

function setupVoiceRecognition() {
  voiceUploadSupported.value = canUploadAudioFromBrowser();
  voicePlaybackSupported.value = canPlaySpeechInBrowser();
  liveTranscriptSupported.value = Boolean(getSpeechRecognitionConstructor());
  speechRecognition = null;
  if (canRecordWithBrowser()) {
    voiceMode.value = "recording";
    voiceSupported.value = true;
    voiceStatusDetail.value = microphonePermission.value === "granted"
      ? liveTranscriptSupported.value
        ? "Streaming mic + preview + transcription backend"
        : "Streaming mic + transcription backend"
      : "Micro pret a autoriser";
  } else {
    voiceMode.value = "none";
    voiceSupported.value = false;
    if (voiceUploadSupported.value && typeof window !== "undefined" && !hasSecureMicrophoneContext()) {
      voiceStatusDetail.value = "Upload audio disponible, micro bloque hors contexte securise";
    } else if (voiceUploadSupported.value) {
      voiceStatusDetail.value = "Upload audio disponible";
    } else {
      voiceStatusDetail.value = "Micro et upload indisponibles";
    }
  }
}

async function loadReferenceValues() {
  try {
    const fullPayload = await fetchJson("/reference-values", {}, apiBase.value);
    referenceCounts.value = fullPayload.counts || referenceCounts.value;
    clientDirectory.value = fullPayload.clients || [];
  } catch {
    clientDirectory.value = [];
    referenceCounts.value = { clients: 0, addresses: 0, emplacements: 0 };
  }
}

async function loadHistory() {
  const params = new URLSearchParams();
  params.set("limit", String(historyLimit.value));
  try {
    const payload = await fetchJson(`/history?${params.toString()}`, {}, apiBase.value);
    historyRows.value = payload.rows || [];
  } catch {
    historyRows.value = [];
  }
}

async function refreshWorkspace() {
  await checkBackend();
  if (backendStatus.value === "online") {
    await Promise.all([loadReferenceValues(), loadRagStatus(), loadHistory()]);
  }
}

function formatNumber(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "-";
  return String(Math.round(Number(value)));
}

function formatCompactNumber(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "-";
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value));
}

watch(currentConversationId, (value) => {
  saveConversationState();
  emit("conversation-change", value || "");
});
watch(
  () => props.selectedConversationKey,
  async (value) => {
    const nextConversationKey = value || "";
    if (!nextConversationKey) {
      if (currentConversationId.value || chatFeed.value.length) {
        startNewConversation();
      }
      return;
    }
    if (nextConversationKey === currentConversationId.value && chatFeed.value.length) return;
    await loadSavedConversation(nextConversationKey);
  },
  { immediate: true },
);
watch(ragQuery, () => {
  void resizePromptInput();
});

onMounted(async () => {
  await syncMicrophonePermission();
  setupVoiceRecognition();
  await initializeActiveMicrophone();
  await syncLocationPermission();
  await refreshWorkspace();
  await resizePromptInput();
});

onBeforeUnmount(() => {
  void stopLiveTranscriptPreview();
  void stopAnswerPlayback();
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  void cleanupMediaStream();
});
</script>

<template>
  <main class="sav-dashboard">
    <section id="sav-assistant" class="panel chat-panel experience-chat-panel">
      <div class="assistant-panel-header">
        <div class="assistant-panel-copy">
          <div>
            <h2>Conversation</h2>
          </div>
        </div>
        <div class="assistant-panel-actions assistant-panel-actions-stacked">
          <div class="audio-controls">
            <button
              type="button"
              class="audio-control-btn"
              :class="{ active: voiceAutoplayEnabled }"
              :disabled="!voicePlaybackSupported"
              :aria-label="voiceAutoplayEnabled ? 'Desactiver la lecture automatique' : 'Activer la lecture automatique'"
              :title="voiceAutoplayEnabled ? 'Lecture automatique activee' : 'Lecture automatique desactivee'"
              @click="toggleVoiceAutoplay"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M4 10v4h4l5 5V5L8 10H4z" />
                <path v-if="voiceAutoplayEnabled" d="M16.5 8.5a5 5 0 0 1 0 7" />
                <template v-else>
                  <line x1="16" y1="9" x2="21" y2="15" />
                  <line x1="21" y1="9" x2="16" y2="15" />
                </template>
              </svg>
            </button>
            <span class="audio-controls-divider" aria-hidden="true"></span>
            <button
              type="button"
              class="audio-control-btn"
              :disabled="!canReplayLatestAnswer || voicePlaybackPending"
              aria-label="Reecouter la derniere reponse"
              title="Reecouter la derniere reponse"
              @click="playLatestAnswer"
            >
              <svg v-if="!voicePlaybackPending" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M3 12a9 9 0 1 0 2.6-6.3" />
                <path d="M3 4v5h5" />
              </svg>
              <svg v-else class="audio-control-spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
                <path d="M12 3a9 9 0 1 1-9 9" />
              </svg>
            </button>
          </div>
          <span class="brand-state" :class="backendStatus">{{ statusLabel }}</span>
        </div>
      </div>

      <div ref="chatFeedViewport" class="chat-feed-stage">
        <div v-if="chatFeed.length" class="chat-feed-list">
          <div class="chat-day-divider">
            <span>Today</span>
          </div>
          <article
            v-for="entry in chatFeed"
            :key="entry.id"
            class="chat-feed-entry"
            :class="[`role-${entry.role}`, `status-${entry.status}`]"
          >
            <span class="chat-feed-role">{{ entry.role === "user" ? "PROMPT" : "AURALYS" }}</span>
            <div class="chat-feed-text" v-html="formatMessage(entry.text)"></div>
            <div v-if="entry.imageAttachment" class="chat-image-card">
              <img :src="entry.imageAttachment.dataUrl" :alt="entry.imageAttachment.name" class="chat-image-preview" >
              <small>{{ entry.imageAttachment.name }}</small>
            </div>
            <ul v-if="entry.citations && entry.citations.length" class="chat-citations">
              <li v-for="citation in entry.citations" :key="citation.index">
                <span class="chat-citation-marker">[{{ citation.index }}]</span>
                {{ citation.client || "Client inconnu" }}
                <template v-if="citation.maintenance_number">— fiche {{ citation.maintenance_number }}</template>
              </li>
            </ul>
            <div v-if="entry.role === 'assistant' && entry.status === 'done'" class="message-action-row">
              <button class="message-action-button" type="button" aria-label="Copier" @click="copyMessageText(entry.text)">
                <svg class="message-action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                  <rect x="8" y="8" width="12" height="12" rx="2" />
                  <path d="M5 15.5A2 2 0 0 1 4 13.7V6a2 2 0 0 1 2-2h7.7a2 2 0 0 1 1.8 1" />
                </svg>
              </button>
              <button
                class="message-action-button"
                type="button"
                :disabled="!voicePlaybackSupported"
                aria-label="Ecouter"
                @click="speakMessage(entry)"
              >
                <svg class="message-action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                  <path d="M4 10v4h4l5 5V5L8 10H4z" />
                  <path d="M16.5 8.5a5 5 0 0 1 0 7" />
                  <path d="M19 6a8.5 8.5 0 0 1 0 12" />
                </svg>
              </button>
              <button
                class="message-action-button"
                type="button"
                :class="{ active: entry.feedback === 'up' }"
                aria-label="Reponse utile"
                @click="sendMessageFeedback(entry, 'up')"
              >
                <svg class="message-action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                  <path d="M7 11v9H4v-9h3zm0 0 4-7a2 2 0 0 1 3.6 1.4L13.7 10H18a2 2 0 0 1 2 2.3l-1.2 6A2 2 0 0 1 16.8 20H7" />
                </svg>
              </button>
              <button
                class="message-action-button"
                type="button"
                :class="{ active: entry.feedback === 'down' }"
                aria-label="Reponse pas utile"
                @click="sendMessageFeedback(entry, 'down')"
              >
                <svg class="message-action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                  <path d="M7 13V4H4v9h3zm0 0-4 7a2 2 0 0 0 3.6-1.4l.9-3.6H18a2 2 0 0 0 2-2.3l-1.2-6A2 2 0 0 0 16.8 4H7" />
                </svg>
              </button>
            </div>
          </article>
        </div>
        <div v-else class="chat-feed-empty chat-feed-empty-home">
          <div class="chat-feed-empty-copy">
            <h3>{{ emptyStateGreeting }}</h3>
            <p>{{ emptyStateHint }}</p>
          </div>
          <div class="prompt-chip-row home-suggestion-row">
            <button
              v-for="chip in suggestionChips"
              :key="chip"
              class="prompt-chip"
              type="button"
              @click="sendSuggestion(chip)"
            >
              {{ chip }}
            </button>
          </div>
        </div>
      </div>

      <section id="sav-voice" class="voice-control-panel prompt-stage" aria-label="Voice controls">
        <input
          ref="audioUploadInput"
          type="file"
          accept="audio/*"
          capture="microphone"
          class="sr-only"
          @change="handleAudioFileSelection"
        />
        <input
          ref="imageUploadInput"
          type="file"
          accept="image/*"
          class="sr-only"
          @change="handleImageFileSelection"
        />

        <div v-if="selectedImageAttachment" class="composer-image-chip">
          <button type="button" class="composer-image-thumb" aria-label="Agrandir l'image" @click="openImageLightbox">
            <img :src="selectedImageAttachment.dataUrl" :alt="selectedImageAttachment.name" >
          </button>
          <button type="button" class="composer-image-remove" aria-label="Retirer l'image" @click="clearSelectedImageAttachment">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div class="prompt-stage-main">
          <textarea
            ref="promptInput"
            v-model="ragQuery"
            class="prompt-stage-input"
            placeholder="Ecrire ton message..."
            rows="1"
            @keydown.enter.exact.prevent="runRagQuery"
          ></textarea>

          <div class="prompt-toolbar">
            <button
              class="plus-activator"
              type="button"
              :disabled="ragLoading"
              aria-label="Import image"
              title="Joindre une image"
              @click="openImageUploadPicker"
            >
              <span class="plus-icon" aria-hidden="true"></span>
            </button>

            <div class="prompt-stage-actions">
              <button
                class="voice-activator"
                :class="{ 'is-listening': voiceListening || holdToTalkActive }"
                type="button"
                :disabled="(!voiceSupported && microphonePermission === 'unsupported') || ragLoading || requestingMicrophone"
                :aria-label="voiceListening ? 'Stop voice input' : 'Start voice input'"
                title="Dicter la question"
                @click="toggleVoiceInput"
              >
                <svg class="mic-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" y1="19" x2="12" y2="23" />
                </svg>
              </button>
              <button
                class="send-button"
                type="button"
                :disabled="ragLoading || (!ragQuery.trim() && !selectedImageAttachment)"
                aria-label="Envoyer"
                title="Envoyer"
                @click="runRagQuery"
              >
                <svg class="send-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M12 19V5" />
                  <path d="M6 11l6-6 6 6" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <div
          v-if="voiceTranscriptPreview || voiceListening || voiceError"
          class="prompt-stage-status"
        >
          <span class="status-pill" :class="{ live: voiceListening, warn: !voiceListening && voiceError }">
            <span class="status-pill-dot" aria-hidden="true"></span>
            <small v-if="voiceTranscriptPreview">{{ voiceTranscriptPreview }}</small>
            <small v-else-if="voiceListening">Listening...</small>
            <small v-else-if="voiceError">{{ voiceError }}</small>
          </span>
        </div>
        <div v-if="locationPermission === 'denied' || locationPermission === 'unsupported'" class="prompt-stage-status">
          <span class="status-pill warn">
            <span class="status-pill-dot" aria-hidden="true"></span>
            <small>Localisation non partagee : les itineraires utilisent l'adresse AROM AIR par defaut.</small>
          </span>
        </div>
      </section>

      <div v-if="selectedImageAttachment && imageLightboxOpen" class="image-lightbox-overlay" @click.self="closeImageLightbox">
        <div class="image-lightbox-panel">
          <img :src="selectedImageAttachment.dataUrl" :alt="selectedImageAttachment.name" >
          <button type="button" class="image-lightbox-close" aria-label="Fermer" @click="closeImageLightbox">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      <div v-if="ragError" class="message error-message">{{ ragError }}</div>
    </section>
  </main>
</template>
