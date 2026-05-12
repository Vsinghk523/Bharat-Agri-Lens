export type OtpChannel = 'email' | 'whatsapp';

export interface OtpRequest {
  channel: OtpChannel;
  email?: string;
  isd_code?: string;
  mobile_no?: number;
}

export interface OtpRequestResponse {
  delivery_id: string;
  expires_in_seconds: number;
  channel: OtpChannel;
}

export interface OtpVerify {
  channel: OtpChannel;
  email?: string;
  mobile_no?: number;
  code: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  user_id: string;
}

export interface ConsentAccept {
  consent_version: string;
}
