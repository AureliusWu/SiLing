export type VoiceState = "IDLE" | "WAKE_DETECTED" | "LISTENING" | "TRANSCRIBING" | "THINKING" | "ACTING" | "SPEAKING" | "MUTED" | "ERROR" | "STOPPING";
export interface Settings {
  wake_word: string; device: number | null; silence_ms: number; speech_wait_ms: number;
  max_record_ms: number; min_speech_ms: number; cooldown_ms: number; kws_threshold: number;
  num_threads: number; chime: boolean;
  provider: "disabled" | "mock" | "ollama" | "compatible"; api_base: string; llm_model: string;
  cloud_consent: boolean; request_timeout_s: number; context_turns: number;
  tts: "off" | "mock" | "kokoro" | "system"; tts_speaker: number; tts_speed: number;
  save_history: boolean;
}
export interface VoiceEvent {id: number; type: string; state?: VoiceState; text?: string; reason?: string; code?: string; asr_ms?: number; at: number; session?: number}
export interface Status {
  state: VoiceState; mode: "demo" | "local"; cloud: boolean; level: number; loading: boolean;
  hardware_acceptance: "NOT_VERIFIED"; settings: Settings; event_id: number;
  events: VoiceEvent[]; running: boolean; models_installed: boolean;
  dialogue_active: boolean; api_key_configured: boolean; context_messages: number;
}
export interface Device {id: number; name: string; channels: number; sample_rate: number; default: boolean}
export interface Connection {url: string; token: string}
