export type Vehicle = {
  id: string; make: string; model: string; color: string; year: number;
  category: string; seats: number; transmission: string; fuel_type: string;
  hourly_rate: string | number; currency: string; registration_number: string;
  status: string; rental_total_minor?: number; rental_currency?: string;
};

export type Booking = {
  id: string; customer_id: string; vehicle_id: string; pickup_at: string; return_at: string;
  expires_at?: string | null; amount_minor?: number | null; currency: string;
  vehicle_make?: string | null; vehicle_model?: string | null; vehicle_color?: string | null;
  vehicle_license_plate?: string | null; payment_id?: string | null; status: string;
  agreement_version?: string; agreement_accepted_at?: string; created_at: string;
};

export type Receipt = {
  id: string; receipt_number: string; booking_id: string; rental_start: string; rental_end: string;
  amount_minor: number; currency: string; vehicle_make: string; vehicle_model: string;
  vehicle_color: string; vehicle_license_plate: string; created_at: string;
};

export type SupportMessage = { id: string; ticket_id: string; author_id: string; author_name: string; author_role: string; parent_id: string | null; body: string; created_at: string };
export type SupportTicket = { id: string; customer_id: string; subject: string; status: string; priority: string; assigned_to?: string | null; created_at: string; updated_at: string; messages: SupportMessage[] };
