export interface FeatureSettings {
  ai_features: boolean;
  ai_verification: boolean;
  notifications: boolean;
  email_notifications: boolean;
  smart_entry: boolean;
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
