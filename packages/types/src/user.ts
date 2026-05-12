export type UserType = 'Student' | 'Farmer' | 'Researcher' | 'NGO' | 'Business' | 'Government';

export interface UserRead {
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  isd_code: string;
  mobile_no: number;
  address: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  user_type: UserType | string;
  preferred_language: string;
  default_crop_interest: string | null;
  geo_lat: string | null;
  geo_lng: string | null;
  status: string;
  kyc_verified: boolean;
  add_date: string;
  modify_date: string;
}

export interface UserUpdate {
  user_name?: string;
  user_email?: string;
  address?: string;
  city?: string;
  state?: string;
  country?: string;
  user_type?: UserType | string;
  preferred_language?: string;
  default_crop_interest?: string;
  geo_lat?: string;
  geo_lng?: string;
}
