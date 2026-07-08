<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { buildApiUrl, fetchJson, getApiBase, postJson } from "../lib/api";

const props = defineProps({
  user: {
    type: Object,
    default: null,
  },
  activeSection: {
    type: String,
    default: "ceo-workspace",
  },
});
defineEmits(["logout"]);

const apiBase = ref(getApiBase());
const VOICE_AUTOPLAY_STORAGE_KEY = "auralys_voice_autoplay";
const backendStatus = ref("pending");
const reviewRows = ref([]);
const reviewSummary = ref({
  total: 0,
  pending: 0,
  approved: 0,
  corrected: 0,
  rejected: 0,
  with_alert: 0,
  with_llm_error: 0,
  knowledge_ready: 0,
});
const selectedHistoryId = ref(null);
const reviewNotes = ref("");
const correctedAnswer = ref("");
const knowledgeAction = ref("");
const loadingReviews = ref(false);
const savingDecision = ref(false);
const decisionError = ref("");
const conversations = ref([]);
const memories = ref([]);
const selectedConversationKey = ref("");
const conversationMessages = ref([]);
const loadingConversations = ref(false);
const loadingMessages = ref(false);
const loadingMemories = ref(false);
const ceoDiscussionQuery = ref("");
const ceoDiscussionResponse = ref(null);
const ceoDiscussionError = ref("");
const ceoDiscussionLoading = ref(false);
const voiceSupported = ref(false);
const voiceUploadSupported = ref(false);
const voicePlaybackSupported = ref(false);
const voiceAutoplayEnabled = ref(readStoredBoolean(VOICE_AUTOPLAY_STORAGE_KEY, true));
const voicePlaybackPending = ref(false);
const microphonePermission = ref("unknown");
const requestingMicrophone = ref(false);
const voiceListening = ref(false);
const voiceError = ref("");
const voiceTranscriptPreview = ref("");
const voiceMode = ref("none");
const voiceStatusDetail = ref("Micro non accessible");
const audioUploadInput = ref(null);
const imageUploadInput = ref(null);
const selectedImageAttachment = ref(null);
const holdToTalkActive = ref(false);
const liveTranscriptSupported = ref(false);
const ceoConversationId = ref(localStorage.getItem("auralys_ceo_conversation_id") || "");
const ceoChatFeed = ref([]);
const ceoChatViewport = ref(null);
const ceoPromptInput = ref(null);
let refreshTimer = null;
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

const statusLabel = computed(() => {
  if (backendStatus.value === "online") return "Connecte";
  if (backendStatus.value === "offline") return "Hors ligne";
  return "Verification...";
});

const emptyStateGreeting = computed(() => {
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const rawName = String(props.user?.display_name || props.user?.username || "Elyes").trim();
  const normalizedName = /^mr\.?\s+/i.test(rawName) ? rawName : `Mr ${rawName}`;
  return `${greeting}, ${normalizedName}. How can I assist you?`;
});

const emptyStateHint = computed(() => {
  if (backendStatus.value !== "online") return "Backend offline.";
  if (reviewSummary.value.pending) return `${reviewSummary.value.pending} reviews are waiting.`;
  if (reviewSummary.value.with_alert) return `${reviewSummary.value.with_alert} alerts need attention.`;
  const variants = [
    "Review the next priority.",
    "Ask for a concise executive read.",
    "Open a decision or summary.",
  ];
  return variants[new Date().getDate() % variants.length];
});

const pendingReviews = computed(() => reviewRows.value.filter((row) => row.review_status === "pending"));
const activeReview = computed(() => {
  if (!reviewRows.value.length) return null;
  if (selectedHistoryId.value !== null) {
    return reviewRows.value.find((row) => row.history_id === selectedHistoryId.value) || reviewRows.value[0];
  }
  return pendingReviews.value[0] || reviewRows.value[0];
});

const activeConversation = computed(() => {
  if (!conversations.value.length) return null;
  if (selectedConversationKey.value) {
    return conversations.value.find((row) => row.conversation_key === selectedConversationKey.value) || conversations.value[0];
  }
  return conversations.value[0];
});

const ceoDiscussionStatus = computed(() => {
  if (ceoDiscussionLoading.value) return "Auralys is preparing a response.";
  if (voiceListening.value && voiceTranscriptPreview.value.trim()) return voiceTranscriptPreview.value;
  if (voiceListening.value) return "Speak normally. Auralys will send the prompt after a short silence.";
  if (voiceError.value) return voiceError.value;
  if (ceoDiscussionError.value) return ceoDiscussionError.value;
  if (ceoDiscussionResponse.value?.answer) return "Last answer received successfully.";
  return "Use this space to discuss priorities, ask for summaries, or prepare decisions.";
});

const listeningStatus = computed(() => {
  if (voiceListening.value && voiceTranscriptPreview.value.trim()) return "Streaming";
  if (voiceListening.value) return "Listening live";
  if (voiceError.value) return voiceError.value;
  return "Ready";
});

const canRequestMicrophone = computed(() => canRecordWithBrowser());
const canReplayLatestAnswer = computed(() => {
  const text = (ceoDiscussionResponse.value?.spoken_text || ceoDiscussionResponse.value?.answer || "").trim();
  return Boolean(voicePlaybackSupported.value && text);
});
const workspaceStatusLine = computed(() => {
  if (backendStatus.value !== "online") return "Backend offline";
  if (reviewSummary.value.pending) return `${reviewSummary.value.pending} reviews need attention`;
  if (reviewSummary.value.with_alert) return `${reviewSummary.value.with_alert} alerts detected`;
  return "No urgent review";
});

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

watch(activeReview, (row) => {
  reviewNotes.value = row?.review_notes || "";
  correctedAnswer.value = row?.corrected_answer || "";
  knowledgeAction.value = row?.knowledge_action || "";
}, { immediate: true });

watch(selectedConversationKey, async (value) => {
  await loadMessages(value);
});

watch(ceoConversationId, saveCeoConversationState);
watch(ceoDiscussionQuery, () => {
  void resizeCeoPromptInput();
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

async function loadReviews() {
  loadingReviews.value = true;
  try {
    const payload = await fetchJson("/admin/reviews?limit=48&status=all", {}, apiBase.value);
    reviewRows.value = payload.rows || [];
    reviewSummary.value = payload.summary || reviewSummary.value;
    if (!activeReview.value && reviewRows.value.length) {
      selectedHistoryId.value = reviewRows.value[0].history_id;
    }
  } catch {
    reviewRows.value = [];
  } finally {
    loadingReviews.value = false;
  }
}

async function loadConversations() {
  loadingConversations.value = true;
  try {
    const payload = await fetchJson("/conversations?limit=40", {}, apiBase.value);
    conversations.value = payload.rows || [];
    if (!selectedConversationKey.value && conversations.value.length) {
      selectedConversationKey.value = conversations.value[0].conversation_key;
    } else if (
      selectedConversationKey.value
      && !conversations.value.some((row) => row.conversation_key === selectedConversationKey.value)
    ) {
      selectedConversationKey.value = conversations.value[0]?.conversation_key || "";
    }
  } catch {
    conversations.value = [];
  } finally {
    loadingConversations.value = false;
  }
}

async function loadMessages(conversationKey) {
  if (!conversationKey) {
    conversationMessages.value = [];
    return;
  }
  loadingMessages.value = true;
  try {
    const payload = await fetchJson(
      `/conversations/${encodeURIComponent(conversationKey)}/messages?limit=120`,
      {},
      apiBase.value,
    );
    conversationMessages.value = payload.rows || [];
  } catch {
    conversationMessages.value = [];
  } finally {
    loadingMessages.value = false;
  }
}

async function loadMemories() {
  loadingMemories.value = true;
  try {
    const payload = await fetchJson("/memories/active", {}, apiBase.value);
    memories.value = payload.rows || [];
  } catch {
    memories.value = [];
  } finally {
    loadingMemories.value = false;
  }
}

async function refreshCeoData() {
  await checkBackend();
  if (backendStatus.value !== "online") {
    reviewRows.value = [];
    conversations.value = [];
    conversationMessages.value = [];
    memories.value = [];
    return;
  }
  await Promise.all([loadReviews(), loadConversations(), loadMemories()]);
  await loadMessages(selectedConversationKey.value);
}

function selectReview(row) {
  selectedHistoryId.value = row.history_id;
  decisionError.value = "";
}

async function selectConversation(row) {
  selectedConversationKey.value = row.conversation_key;
  await loadMessages(row.conversation_key);
}

function formatHistoryDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatConversationLabel(row) {
  if (!row) return "-";
  return row.role || row.channel || row.conversation_key;
}

function formatConversationMeta(row) {
  if (!row) return "-";
  return row.user_id ? `user ${row.user_id}` : row.channel || "-";
}

function formatMessageLabel(row) {
  if (!row) return "-";
  return row.sender === "assistant" ? "Auralys" : row.sender;
}

function formatHistoryLabel(row) {
  const filters = row?.filters || {};
  return filters.client || row.intent || row.route || `Interaction ${row.history_id}`;
}

function formatHistoryStatus(row) {
  if (row?.review_status && row.review_status !== "pending") return row.review_status;
  if (row?.admin_alert) return "urgent";
  if (row?.llm_error) return "review";
  return "pending";
}

function formatResponseQuality(row) {
  if (!row) return "Aucune analyse disponible.";
  if (row.llm_error) return row.llm_error;
  if (row.reasoning_summary) return row.reasoning_summary;
  if (row.sav_admin_analysis?.summary) return row.sav_admin_analysis.summary;
  return "Aucun resume de raisonnement enregistre pour cette reponse.";
}

async function submitDecision(decision) {
  if (!activeReview.value) return;
  savingDecision.value = true;
  decisionError.value = "";
  try {
    const payload = await postJson(
      `/admin/reviews/${activeReview.value.history_id}/decision`,
      {
        decision,
        reviewed_by: props.user?.username || props.user?.display_name || "ceo",
        review_notes: reviewNotes.value,
        corrected_answer: correctedAnswer.value,
        knowledge_action: knowledgeAction.value,
      },
      {},
      apiBase.value,
    );
    const updatedRow = payload.row;
    reviewRows.value = reviewRows.value.map((row) => (row.history_id === updatedRow.history_id ? updatedRow : row));
    selectedHistoryId.value = updatedRow.history_id;
    await loadReviews();
  } catch (error) {
    decisionError.value = String(error.message || error);
  } finally {
    savingDecision.value = false;
  }
}

function saveCeoConversationState() {
  if (ceoConversationId.value) {
    localStorage.setItem("auralys_ceo_conversation_id", ceoConversationId.value);
  } else {
    localStorage.removeItem("auralys_ceo_conversation_id");
  }
}

async function scrollCeoChatToEnd() {
  await nextTick();
  const node = ceoChatViewport.value;
  if (node) {
    node.scrollTop = node.scrollHeight;
  }
}

async function resizeCeoPromptInput() {
  await nextTick();
  const node = ceoPromptInput.value;
  if (!node) return;
  node.style.height = "0px";
  node.style.height = `${Math.min(node.scrollHeight, 220)}px`;
}

function mapStoredDiscussionMessage(row) {
  const text = String(row?.content || row?.transcript || "").trim();
  if (!text) return null;
  return {
    id: `stored-${row.id}`,
    role: row.sender === "assistant" ? "assistant" : "user",
    text,
    status: "done",
  };
}

async function loadSavedCeoDiscussion(conversationKey) {
  if (!conversationKey) {
    ceoChatFeed.value = [];
    return;
  }
  try {
    const payload = await fetchJson(
      `/conversations/${encodeURIComponent(conversationKey)}/messages?limit=120`,
      {},
      apiBase.value,
    );
    ceoChatFeed.value = (payload.rows || []).map(mapStoredDiscussionMessage).filter(Boolean);
    await scrollCeoChatToEnd();
  } catch {
    ceoChatFeed.value = [];
  }
}

function createPendingCeoEntry() {
  return {
    id: `ceo-assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role: "assistant",
    text: "Auralys is preparing a response...",
    status: "pending",
  };
}

async function beginCeoDiscussionTurn(message, imageAttachment = null) {
  const trimmed = (message || "").trim();
  if (!trimmed) return null;
  ceoChatFeed.value.push({
    id: `ceo-user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role: "user",
    text: trimmed,
    status: "done",
    imageAttachment,
  });
  const pending = createPendingCeoEntry();
  ceoChatFeed.value.push(pending);
  await scrollCeoChatToEnd();
  return pending.id;
}

function resolveCeoDiscussionTurn(entryId, answer, fallbackError = "") {
  const target = ceoChatFeed.value.find((item) => item.id === entryId);
  if (!target) return;
  target.text = answer || fallbackError || "No response available.";
  target.status = answer ? "done" : "error";
}

async function submitCeoDiscussion(message) {
  const imageAttachment = consumeSelectedImageAttachment();
  const submittedPrompt = buildSubmittedPrompt(message, imageAttachment);
  if (!submittedPrompt && !imageAttachment) return;
  const pendingEntryId = await beginCeoDiscussionTurn(submittedPrompt, imageAttachment);
  ceoDiscussionLoading.value = true;
  ceoDiscussionError.value = "";
  try {
    const payload = await postJson(
      "/agent/chat",
      {
        user_id: Number(props.user?.id || 1),
        role: props.user?.role || "ceo",
        message: submittedPrompt,
        conversation_id: ceoConversationId.value || null,
        context: {
          conversation_id: ceoConversationId.value || null,
        },
        images: imageAttachment ? [serializeImageAttachment(imageAttachment)] : [],
      },
      {},
      apiBase.value,
    );
    ceoDiscussionResponse.value = payload;
    resolveCeoDiscussionTurn(pendingEntryId, payload.answer);
    void speakAnswer(ceoDiscussionResponse.value);
    if (payload.conversation_id) {
      ceoConversationId.value = String(payload.conversation_id);
      saveCeoConversationState();
    }
    await Promise.all([loadConversations(), loadMessages(selectedConversationKey.value)]);
    await scrollCeoChatToEnd();
  } catch (error) {
    ceoDiscussionError.value = String(error.message || error);
    resolveCeoDiscussionTurn(pendingEntryId, "", ceoDiscussionError.value);
  } finally {
    ceoDiscussionLoading.value = false;
  }
}

async function runCeoDiscussionQuery() {
  if (!ceoDiscussionQuery.value.trim() && !selectedImageAttachment.value) return;
  const submittedPrompt = ceoDiscussionQuery.value.trim();
  ceoDiscussionQuery.value = "";
  ceoDiscussionResponse.value = null;
  await stopAnswerPlayback();
  await resizeCeoPromptInput();
  await submitCeoDiscussion(submittedPrompt);
}

function buildSubmittedPrompt(message, imageAttachment) {
  const trimmed = (message || "").trim();
  if (trimmed) return trimmed;
  if (imageAttachment) return "Analyse cette image et aide-moi a partir de son contenu.";
  return "";
}

function openImageUploadPicker() {
  imageUploadInput.value?.click();
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
  await scrollCeoChatToEnd();
}

function clearSelectedImageAttachment() {
  selectedImageAttachment.value = null;
}

function consumeSelectedImageAttachment() {
  const attachment = selectedImageAttachment.value;
  selectedImageAttachment.value = null;
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
  if (holdToTalkActive.value || ceoDiscussionLoading.value) return;
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

async function handleVoiceAnswerPayload(transcript) {
  const normalizedTranscript = (transcript || "").trim();
  if (!normalizedTranscript) {
    voiceError.value = "Aucune transcription exploitable n'a ete capturee.";
    voiceTranscriptPreview.value = "";
    return;
  }
  voiceTranscriptPreview.value = normalizedTranscript;
  await submitCeoDiscussion(normalizedTranscript);
}

async function uploadRecordedAudio(audioBlob) {
  const formData = new FormData();
  formData.append("audio", audioBlob, "voice-input.webm");
  const response = await fetch(buildApiUrl("/transcribe-upload", apiBase.value), {
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
  ceoDiscussionLoading.value = true;
  try {
    const payload = await uploadRecordedAudio(file);
    await handleVoiceAnswerPayload(payload.transcript || "");
  } catch (error) {
    voiceError.value = String(error.message || error);
    voiceTranscriptPreview.value = "";
  } finally {
    ceoDiscussionLoading.value = false;
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
      ceoDiscussionLoading.value = true;
      voiceTranscriptPreview.value = "Transcription en cours...";
      try {
        const payload = await uploadRecordedAudio(audioBlob);
        await handleVoiceAnswerPayload(payload.transcript || "");
      } catch (error) {
        voiceError.value = String(error.message || error);
        voiceTranscriptPreview.value = "";
      } finally {
        ceoDiscussionLoading.value = false;
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
  void speakAnswer(ceoDiscussionResponse.value, { forcePlayback: true });
}

async function speakAnswer(responsePayload = ceoDiscussionResponse.value, options = {}) {
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

onMounted(async () => {
  await syncMicrophonePermission();
  setupVoiceRecognition();
  await initializeActiveMicrophone();
  await refreshCeoData();
  if (ceoConversationId.value) {
    await loadSavedCeoDiscussion(ceoConversationId.value);
  }
  await resizeCeoPromptInput();
  refreshTimer = window.setInterval(refreshCeoData, 10000);
});

onBeforeUnmount(() => {
  void stopAnswerPlayback();
  void stopLiveTranscriptPreview();
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  void cleanupMediaStream();
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
});
</script>

<template>
  <main class="ceo-dashboard">
    <section v-if="props.activeSection === 'ceo-workspace'" id="ceo-workspace" class="ceo-workspace-shell ceo-minimal-workspace">
      <section class="panel ceo-compact-header">
        <div class="ceo-compact-title">
          <h2>CEO workspace</h2>
          <p>{{ workspaceStatusLine }}</p>
        </div>
        <div class="ceo-inline-metrics">
          <article class="ceo-inline-metric">
            <strong>{{ reviewSummary.pending || 0 }}</strong>
            <span>Pending</span>
          </article>
          <article class="ceo-inline-metric">
            <strong>{{ reviewSummary.with_alert || 0 }}</strong>
            <span>Alerts</span>
          </article>
          <article class="ceo-inline-metric">
            <strong>{{ conversations.length || 0 }}</strong>
            <span>Chats</span>
          </article>
          <span class="brand-state" :class="backendStatus">{{ statusLabel }}</span>
        </div>
      </section>

      <section class="panel executive-queue-panel">
        <div class="assistant-panel-header">
          <div class="assistant-panel-copy">
            <div>
              <h2>Validation queue</h2>
            </div>
          </div>
          <span class="queue-status">{{ reviewRows.length }}</span>
        </div>
        <div v-if="reviewRows.length" class="review-grid single-column-grid">
          <article
            v-for="item in reviewRows"
            :key="item.history_id"
            class="queue-card"
            :class="[formatHistoryStatus(item), { active: activeReview?.history_id === item.history_id }]"
            @click="selectReview(item)"
          >
            <div class="queue-card-head">
              <strong>{{ formatHistoryLabel(item) }}</strong>
              <span class="queue-status">{{ formatHistoryStatus(item) }}</span>
            </div>
            <p>{{ item.original_query }}</p>
            <small>{{ formatHistoryDate(item.created_at) }}</small>
          </article>
        </div>
        <div v-else class="message muted-message">
          {{ loadingReviews ? "Loading queue..." : "No pending review." }}
        </div>
      </section>

      <aside class="panel executive-detail-panel">
        <div class="insight-panel-head">
          <div>
            <h2>Decision</h2>
          </div>
        </div>

        <div v-if="activeReview" class="executive-detail-stack">
          <div class="insight-block">
            <h3>Request summary</h3>
            <ul class="simple-list">
              <li><strong>SAV question:</strong> {{ activeReview.original_query }}</li>
              <li><strong>Route:</strong> {{ activeReview.route || "-" }}</li>
              <li><strong>Source:</strong> {{ activeReview.response_source || "-" }}</li>
              <li><strong>Evidence count:</strong> {{ activeReview.hits?.length || 0 }}</li>
              <li><strong>System note:</strong> {{ formatResponseQuality(activeReview) }}</li>
            </ul>
          </div>

          <div class="insight-block">
            <h3>Suggested answer</h3>
            <p>{{ activeReview.answer }}</p>
          </div>

          <label class="composer-field">
            <span>Comment</span>
            <textarea v-model="reviewNotes" placeholder="Explain the decision briefly"></textarea>
          </label>
          <label class="composer-field">
            <span>Corrected answer</span>
            <textarea v-model="correctedAnswer" placeholder="Write the preferred answer if a correction is needed"></textarea>
          </label>
          <label class="composer-field">
            <span>Knowledge action</span>
            <input v-model="knowledgeAction" type="text" placeholder="add to KB, follow up with client" />
          </label>
          <div v-if="decisionError" class="message error-message">{{ decisionError }}</div>

          <div class="decision-grid">
            <article class="decision-card approve">
              <div class="decision-head">
                <h3>Approve</h3>
                <span class="decision-indicator" aria-hidden="true"></span>
              </div>
              <p>The answer is clear and safe to keep.</p>
              <button class="text-button" :disabled="!activeReview || savingDecision" @click="submitDecision('approve')">Approve</button>
            </article>
            <article class="decision-card correct">
              <div class="decision-head">
                <h3>Correct</h3>
                <span class="decision-indicator" aria-hidden="true"></span>
              </div>
              <p>The answer is useful but needs revision.</p>
              <button class="text-button" :disabled="!activeReview || savingDecision" @click="submitDecision('correct')">Correct</button>
            </article>
            <article class="decision-card reject">
              <div class="decision-head">
                <h3>Reject</h3>
                <span class="decision-indicator" aria-hidden="true"></span>
              </div>
              <p>The answer should not be reused as is.</p>
              <button class="text-button" :disabled="!activeReview || savingDecision" @click="submitDecision('reject')">Reject</button>
            </article>
          </div>
        </div>

        <div v-else class="message muted-message">Select a review to inspect it.</div>
      </aside>

      <section class="panel executive-data-panel ceo-history-panel">
        <div class="section-title">
          <div>
            <h2>History</h2>
          </div>
        </div>

        <div class="admin-data-grid">
          <article class="insight-block admin-data-block">
            <div class="admin-data-head">
              <h3>Conversations</h3>
              <span class="queue-status">{{ conversations.length }}</span>
            </div>
            <div v-if="conversations.length" class="admin-list">
              <button
                v-for="row in conversations"
                :key="row.id"
                type="button"
                class="admin-row-button"
                :class="{ active: activeConversation?.conversation_key === row.conversation_key }"
                @click="selectConversation(row)"
              >
                <strong>{{ formatConversationLabel(row) }}</strong>
                <small>{{ row.conversation_key }}</small>
                <small>{{ formatConversationMeta(row) }} · {{ formatHistoryDate(row.last_message_at) }}</small>
              </button>
            </div>
            <div v-else class="message muted-message">
              {{ loadingConversations ? "Loading conversations..." : "No conversation stored yet." }}
            </div>
          </article>

          <article class="insight-block admin-data-block">
            <div class="admin-data-head">
              <h3>Messages</h3>
              <span class="queue-status">{{ conversationMessages.length }}</span>
            </div>
            <div v-if="conversationMessages.length" class="admin-message-list">
              <div v-for="row in conversationMessages" :key="row.id" class="admin-message-card">
                <div class="queue-card-head">
                  <strong>{{ formatMessageLabel(row) }}</strong>
                  <span class="queue-status">{{ row.message_type }}</span>
                </div>
                <p>{{ row.content }}</p>
                <small>{{ formatHistoryDate(row.created_at) }}</small>
              </div>
            </div>
            <div v-else class="message muted-message">
              {{ loadingMessages ? "Loading messages..." : "Select a conversation to inspect its messages." }}
            </div>
          </article>
        </div>

        <article class="insight-block admin-data-block">
          <div class="admin-data-head">
            <h3>Memories</h3>
            <span class="queue-status">{{ memories.length }}</span>
          </div>
          <div v-if="memories.length" class="admin-memory-list">
            <div v-for="row in memories" :key="row.id" class="admin-memory-card">
              <div class="queue-card-head">
                <strong>{{ row.memory_type }}</strong>
                <span class="queue-status">{{ row.status }}</span>
              </div>
              <p>{{ row.content }}</p>
              <small>{{ row.scope || "global" }} · {{ row.confidence ?? "-" }}</small>
            </div>
          </div>
          <div v-else class="message muted-message">
            {{ loadingMemories ? "Loading memories..." : "No active memory is stored yet." }}
          </div>
        </article>
      </section>
    </section>

    <section v-else-if="props.activeSection === 'ceo-discussion'" id="ceo-discussion" class="ceo-workspace-shell">
      <section class="panel chat-panel executive-discussion-panel experience-chat-panel">
        <div class="assistant-panel-header">
          <div class="assistant-panel-copy">
            <div>
              <h2>Discussion</h2>
            </div>
          </div>
          <div class="assistant-panel-actions assistant-panel-actions-stacked">
            <button
              class="ghost-button header-mini-button"
              type="button"
              :disabled="!voicePlaybackSupported"
              :class="{ active: voiceAutoplayEnabled }"
              @click="toggleVoiceAutoplay"
            >
              Voice
            </button>
            <button
              class="ghost-button header-mini-button"
              type="button"
              :disabled="!canReplayLatestAnswer || voicePlaybackPending"
              @click="playLatestAnswer"
            >
              {{ voicePlaybackPending ? "..." : "Play" }}
            </button>
            <span class="brand-state" :class="backendStatus">{{ statusLabel }}</span>
          </div>
        </div>

        <div ref="ceoChatViewport" class="chat-feed-stage">
          <div v-if="ceoChatFeed.length" class="chat-feed-list">
            <div class="chat-day-divider">
              <span>Today</span>
            </div>
            <article
              v-for="entry in ceoChatFeed"
              :key="entry.id"
              class="chat-feed-entry"
              :class="[`role-${entry.role}`, `status-${entry.status}`]"
            >
              <span class="chat-feed-role">{{ entry.role === "user" ? "CEO" : "AURALYS" }}</span>
              <p>{{ entry.text }}</p>
              <div v-if="entry.imageAttachment" class="chat-image-card">
                <img :src="entry.imageAttachment.dataUrl" :alt="entry.imageAttachment.name" class="chat-image-preview" >
                <small>{{ entry.imageAttachment.name }}</small>
              </div>
            </article>
          </div>
          <div v-else class="chat-feed-empty chat-feed-empty-home">
            <div class="chat-feed-empty-copy">
              <h3>{{ emptyStateGreeting }}</h3>
              <p>{{ emptyStateHint }}</p>
            </div>
          </div>
        </div>

        <section class="prompt-stage" aria-label="CEO discussion">
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

          <div class="prompt-stage-main">
            <button
              class="plus-activator"
              type="button"
              :disabled="ceoDiscussionLoading"
              aria-label="Import image"
              @click="openImageUploadPicker"
            >
              <span class="plus-icon" aria-hidden="true"></span>
            </button>

            <textarea
              ref="ceoPromptInput"
              v-model="ceoDiscussionQuery"
              class="prompt-stage-input"
              placeholder="Ask"
              rows="1"
              @keydown.enter.exact.prevent="runCeoDiscussionQuery"
            ></textarea>

            <div class="prompt-stage-actions">
              <button
                class="voice-activator"
                :class="{ 'is-listening': voiceListening || holdToTalkActive }"
                type="button"
                :disabled="(!voiceSupported && microphonePermission === 'unsupported') || ceoDiscussionLoading || requestingMicrophone"
                :aria-label="voiceListening ? 'Stop voice input' : 'Start voice input'"
                @click="toggleVoiceInput"
              >
                <span class="mic-icon" aria-hidden="true">
                  <span class="mic-icon-head"></span>
                  <span class="mic-icon-stem"></span>
                  <span class="mic-icon-base"></span>
                </span>
              </button>
              <button
                class="send-button"
                type="button"
                :disabled="ceoDiscussionLoading || (!ceoDiscussionQuery.trim() && !selectedImageAttachment)"
                @click="runCeoDiscussionQuery"
              >
                Send
              </button>
            </div>
          </div>

          <div v-if="selectedImageAttachment" class="selected-image-attachment">
            <img
              :src="selectedImageAttachment.dataUrl"
              :alt="selectedImageAttachment.name"
              class="selected-image-preview"
          >
            <div class="selected-image-copy">
              <strong>{{ selectedImageAttachment.name }}</strong>
            </div>
            <button class="text-button" type="button" @click="clearSelectedImageAttachment">Remove</button>
          </div>

          <div
            v-if="voiceTranscriptPreview || voiceListening || voiceError || microphonePermission === 'denied' || ceoDiscussionLoading"
            class="prompt-stage-status"
          >
            <small v-if="voiceTranscriptPreview">{{ voiceTranscriptPreview }}</small>
            <small v-else-if="voiceListening">Listening...</small>
            <small v-else-if="voiceError">{{ voiceError }}</small>
            <small v-else-if="microphonePermission === 'denied'">Enable microphone.</small>
            <small v-else>{{ ceoDiscussionLoading ? "Thinking..." : "" }}</small>
          </div>
        </section>
      </section>
    </section>
  </main>
</template>
