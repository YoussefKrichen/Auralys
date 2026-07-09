from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Auralys Agent")
    app_env: str = os.getenv("APP_ENV", "dev")
    agent_name: str = os.getenv("AGENT_NAME", "Auralys")
    company_name: str = os.getenv("COMPANY_NAME", "Aromair")
    assistant_role: str = os.getenv(
        "ASSISTANT_ROLE",
        "Assistant de Connaissance & d'Intelligence Olfactive",
    )
    assistant_mission: str = os.getenv(
        "ASSISTANT_MISSION",
        "Guider l'equipe SAV et l'administration dans leurs decisions et verifications avec des recommandations utiles, fiables et exploitables.",
    )
    interaction_modes: str = os.getenv(
        "INTERACTION_MODES",
        "Texte et voix",
    )
    default_response_language: str = os.getenv(
        "DEFAULT_RESPONSE_LANGUAGE",
        "francais",
    )
    assistant_identity: str = os.getenv(
        "ASSISTANT_IDENTITY",
        "Auralys s'appelle toujours Auralys, reconnait toujours que son nom est Auralys, et s'exprime naturellement au feminin quand c'est pertinent.",
    )
    default_greeting: str = os.getenv(
        "DEFAULT_GREETING",
        "Bonjour je suis Auralys, comment je peux vous aider",
    )
    voice_response_principle: str = os.getenv(
        "VOICE_RESPONSE_PRINCIPLE",
        "Quand la reponse est restituee en vocal, elle doit rester naturelle, claire, breve et facile a comprendre a l'oral.",
    )
    hands_free_response_principle: str = os.getenv(
        "HANDS_FREE_RESPONSE_PRINCIPLE",
        "En mode mains libres, la reponse doit pouvoir etre comprise sans ecran, avec des phrases courtes, des instructions explicites, peu d'ambiguite et sans dependre d'elements visuels.",
    )
    decision_principle: str = os.getenv(
        "DECISION_PRINCIPLE",
        "Prendre des decisions qui protegent la qualite de service, facilitent les verifications internes et soutiennent un bilan positif pour la societe.",
    )
    postgres_dsn: str = os.getenv(
        "POSTGRES_DSN",
        "postgresql://auralys:auralys@localhost:5433/auralys",
    )
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "auralys_chunks")
    backend_public_url: str = os.getenv("BACKEND_PUBLIC_URL", "http://127.0.0.1:8000")
    frontend_public_url: str = os.getenv("FRONTEND_PUBLIC_URL", "http://127.0.0.1:5173")
    speech_stt_model: str = os.getenv("SPEECH_STT_MODEL", "base")
    speech_stt_device: str = os.getenv("SPEECH_STT_DEVICE", "cpu")
    speech_stt_compute_type: str = os.getenv("SPEECH_STT_COMPUTE_TYPE", "int8")
    speech_language: str | None = os.getenv("SPEECH_LANGUAGE", "fr") or "fr"
    speech_gemini_stt_model: str = os.getenv("SPEECH_GEMINI_STT_MODEL", "gemini-2.5-flash")
    speech_tts_backend: str = os.getenv("SPEECH_TTS_BACKEND", "pyttsx3").strip().lower()
    speech_tts_rate: int = int(os.getenv("SPEECH_TTS_RATE", "180"))
    speech_tts_volume: float = max(0.0, min(1.0, float(os.getenv("SPEECH_TTS_VOLUME", "1.0"))))
    speech_tts_voice: str | None = os.getenv("SPEECH_TTS_VOICE") or None
    speech_tts_preferred_voices: tuple[str, ...] = tuple(
        voice.strip()
        for voice in os.getenv(
            "SPEECH_TTS_PREFERRED_VOICES",
            "Hortense, Helene, Julie, Harmonie, Sophie, Microsoft Hortense Desktop",
        ).split(",")
        if voice.strip()
    )
    speech_tts_language_preference: str = os.getenv("SPEECH_TTS_LANGUAGE_PREFERENCE", "fr")
    speech_tts_gender_preference: str = os.getenv("SPEECH_TTS_GENDER_PREFERENCE", "female")
    google_api_key: str | None = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    google_routes_api_key: str | None = os.getenv("GOOGLE_ROUTES_API_KEY")
    speech_gemini_tts_model: str = os.getenv(
        "SPEECH_GEMINI_TTS_MODEL",
        "gemini-2.5-flash-preview-tts",
    )
    speech_gemini_tts_voice: str = os.getenv("SPEECH_GEMINI_TTS_VOICE", "Sulafat")
    speech_gemini_tts_instruction: str = os.getenv("SPEECH_GEMINI_TTS_INSTRUCTION", "Say calmly:")
    speech_gemini_tts_sample_rate: int = int(os.getenv("SPEECH_GEMINI_TTS_SAMPLE_RATE", "24000"))
    speech_gemini_tts_channels: int = int(os.getenv("SPEECH_GEMINI_TTS_CHANNELS", "1"))
    speech_gemini_tts_sample_width: int = int(os.getenv("SPEECH_GEMINI_TTS_SAMPLE_WIDTH", "2"))
    speech_piper_model_path: str | None = os.getenv("SPEECH_PIPER_MODEL_PATH") or None
    speech_piper_config_path: str | None = os.getenv("SPEECH_PIPER_CONFIG_PATH") or None
    speech_piper_use_cuda: bool = os.getenv("SPEECH_PIPER_USE_CUDA", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    speech_piper_speaker: int | None = (
        int(os.getenv("SPEECH_PIPER_SPEAKER"))
        if os.getenv("SPEECH_PIPER_SPEAKER") not in {None, ""}
        else None
    )
    speech_piper_sentence_silence: float = float(os.getenv("SPEECH_PIPER_SENTENCE_SILENCE", "0.2"))
    speech_piper_noise_scale: float = float(os.getenv("SPEECH_PIPER_NOISE_SCALE", "0.667"))
    speech_piper_noise_w_scale: float = float(os.getenv("SPEECH_PIPER_NOISE_W_SCALE", "0.8"))
    speech_piper_length_scale: float = float(os.getenv("SPEECH_PIPER_LENGTH_SCALE", "1.0"))
    speech_piper_normalize_audio: bool = os.getenv("SPEECH_PIPER_NORMALIZE_AUDIO", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    speech_speak_content_only: bool = os.getenv("SPEECH_SPEAK_CONTENT_ONLY", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    speech_input_sample_rate: int = int(os.getenv("SPEECH_INPUT_SAMPLE_RATE", "16000"))
    speech_input_channels: int = int(os.getenv("SPEECH_INPUT_CHANNELS", "1"))
    speech_live_turn_seconds: float = float(os.getenv("SPEECH_LIVE_TURN_SECONDS", "6"))
    speech_live_max_turn_seconds: float = float(os.getenv("SPEECH_LIVE_MAX_TURN_SECONDS", "30"))
    speech_silence_stop_seconds: float = float(os.getenv("SPEECH_SILENCE_STOP_SECONDS", "4"))
    speech_voice_activation_threshold: float = float(
        os.getenv("SPEECH_VOICE_ACTIVATION_THRESHOLD", "0.015")
    )
    speech_audio_chunk_seconds: float = float(os.getenv("SPEECH_AUDIO_CHUNK_SECONDS", "0.25"))
    speech_wake_word_enabled: bool = os.getenv("SPEECH_WAKE_WORD_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    speech_wake_word: str = os.getenv("SPEECH_WAKE_WORD", "Auralys")
    speech_wake_word_variants: tuple[str, ...] = tuple(
        variant.strip()
        for variant in os.getenv(
            "SPEECH_WAKE_WORD_VARIANTS",
            "Auralys,Ora-liss,Oralize,Ouralys",
        ).split(",")
        if variant.strip()
    )
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    groq_chat_model: str = os.getenv("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile")
    gemini_chat_model: str = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
    gemini_model: str = os.getenv("GEMINI_MODEL", os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash"))
    langsmith_api_key: str | None = os.getenv("LANGSMITH_API_KEY")
    langsmith_endpoint: str = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    langsmith_project: str = os.getenv("LANGSMITH_PROJECT", "auralys")
    langsmith_tracing: bool = os.getenv("LANGSMITH_TRACING", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    embedding_backend: str = os.getenv("EMBEDDING_BACKEND", "gemini").strip().lower()
    embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-004")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "768"))
    session_secret: str = os.getenv("SESSION_SECRET", "dev-insecure-session-secret-change-me")
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", str(60 * 60 * 12)))
    google_oauth_client_id: str | None = os.getenv("GOOGLE_OAUTH_CLIENT_ID") or None
    google_oauth_client_secret: str | None = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or None
    facebook_oauth_client_id: str | None = os.getenv("FACEBOOK_OAUTH_CLIENT_ID") or None
    facebook_oauth_client_secret: str | None = os.getenv("FACEBOOK_OAUTH_CLIENT_SECRET") or None
    oauth_default_role: str = os.getenv("OAUTH_DEFAULT_ROLE", "sav").strip().lower()
    oauth_allowed_email_domains: tuple[str, ...] = tuple(
        domain.strip().lower()
        for domain in os.getenv("OAUTH_ALLOWED_EMAIL_DOMAINS", "").split(",")
        if domain.strip()
    )
    oauth_ceo_emails: tuple[str, ...] = tuple(
        email.strip().lower()
        for email in os.getenv("OAUTH_CEO_EMAILS", "").split(",")
        if email.strip()
    )
    oauth_sav_emails: tuple[str, ...] = tuple(
        email.strip().lower()
        for email in os.getenv("OAUTH_SAV_EMAILS", "").split(",")
        if email.strip()
    )
    chunk_target_tokens: int = int(os.getenv("CHUNK_TARGET_TOKENS", "600"))
    raw_data_dir: str = os.getenv("RAW_DATA_DIR", "data/raw_json")
    processed_data_dir: str = os.getenv("PROCESSED_DATA_DIR", "data/processed")
    processed_maintenance_dir: str = os.getenv(
        "PROCESSED_MAINTENANCE_DIR",
        "data/processed/maintenance",
    )
    semantic_limit: int = int(os.getenv("SEMANTIC_LIMIT", "6"))
    sql_limit: int = int(os.getenv("SQL_LIMIT", "6"))
    context_limit: int = int(os.getenv("CONTEXT_LIMIT", "6"))
    admin_alert_log_path: str = os.getenv(
        "ADMIN_ALERT_LOG_PATH",
        "data/commercial_opportunities.jsonl",
    )
    admin_alert_min_score: int = int(os.getenv("ADMIN_ALERT_MIN_SCORE", "60"))
    enable_action_execution: bool = os.getenv("ENABLE_ACTION_EXECUTION", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    enable_human_approval: bool = os.getenv("ENABLE_HUMAN_APPROVAL", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


settings = Settings()
