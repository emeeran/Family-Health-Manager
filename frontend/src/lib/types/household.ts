export interface ProviderConfigItem {
  id: string;
  enabled: boolean;
  model: string;
}

export interface AIProviderConfig {
  providers: ProviderConfigItem[];
  /** Which provider group is tried first; the other is automatic fallback. */
  primary_provider: "cloud" | "local";
}

export interface AIProviderConfigResponse {
  config: AIProviderConfig;
  available_models: Record<string, string[]>;
  provider_labels: Record<string, string>;
}

export interface FetchedModelsResponse {
  models: Record<string, string[]>;
}

export interface FeatureSettings {
  ai_features: boolean;
  ai_verification: boolean;
  notifications: boolean;
  email_notifications: boolean;
  smart_entry: boolean;
  // Data / backup configuration (Data tab)
  backup_schedule: "off" | "daily" | "weekly";
  backup_keep_max: number;
}

export interface HouseholdUpdate {
  name?: string | null;
}

export interface HouseholdResponse {
  id: string;
  name: string;
  primary_user_id: string;
  created_at: string;
  settings: FeatureSettings;
}

export interface HouseholdSettingsResponse {
  settings: FeatureSettings;
}

export interface HouseholdSettingsUpdate {
  settings: FeatureSettings;
}

export interface ProviderKeyStatus {
  provider: string;
  label: string;
  is_set: boolean;
  using_env: boolean;
  masked: string | null;
  is_secret: boolean;
}

export interface ProviderKeysResponse {
  keys: ProviderKeyStatus[];
}

export interface ImportFromEnvResponse {
  imported: string[];
  skipped: string[];
}
