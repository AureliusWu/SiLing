export type VoiceState = "IDLE" | "WAKE_DETECTED" | "LISTENING" | "TRANSCRIBING" | "MUTED" | "ERROR" | "STOPPING";
export interface Settings {
  wake_word: string; device: number | null; silence_ms: number; speech_wait_ms: number;
  max_record_ms: number; min_speech_ms: number; cooldown_ms: number; kws_threshold: number;
  num_threads: number; chime: boolean;
}
export interface VoiceEvent {id: number; type: string; state?: VoiceState; text?: string; reason?: string; code?: string; asr_ms?: number; at: number; session?: number}
export interface Status {
  state: VoiceState; mode: "demo" | "local"; cloud: false; level: number; loading: boolean;
  hardware_acceptance: "NOT_VERIFIED"; settings: Settings; event_id: number;
  events: VoiceEvent[]; running: boolean; models_installed: boolean;
}
export interface Device {id: number; name: string; channels: number; sample_rate: number; default: boolean}
export interface Connection {url: string; token: string}
