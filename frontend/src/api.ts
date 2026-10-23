import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import type { Booking, Receipt, SupportTicket, Vehicle } from './types';

const authBase = import.meta.env.VITE_AUTH_API_URL || '/api/auth';
const carBase = import.meta.env.VITE_CAR_API_URL || '/api/cars';
const bookingBase = import.meta.env.VITE_BOOKING_API_URL || '/api/bookings';

export const tokenStore = {
  get: () => localStorage.getItem('drivewell_access_token'),
  set: (value: string) => localStorage.setItem('drivewell_access_token', value),
  clear: () => localStorage.removeItem('drivewell_access_token'),
  getRefresh: () => localStorage.getItem('drivewell_refresh_token'),
  setRefresh: (value: string) => localStorage.setItem('drivewell_refresh_token', value),
  clearRefresh: () => localStorage.removeItem('drivewell_refresh_token'),
};

type Call = { url: string; body?: unknown; method?: string; headers?: Record<string, string> };
type ToastDetail = { type: 'success' | 'error'; message: string };
function announceToast(detail: ToastDetail) {
  window.dispatchEvent(new CustomEvent<ToastDetail>('drivewell:toast', { detail }));
}
export const apiSlice = createApi({
  reducerPath: 'drivewellApi',
  baseQuery: fetchBaseQuery({
    baseUrl: '',
    prepareHeaders: (headers) => {
      const token = tokenStore.get();
      if (token) headers.set('Authorization', `Bearer ${token}`);
      return headers;
    },
  }),
  tagTypes: ['Vehicles', 'Bookings', 'Tickets'],
  endpoints: (builder) => ({
    read: builder.query<unknown, string>({ query: (url) => url, providesTags: (_r, _e, url) => url.includes('/tickets') ? ['Tickets'] : url.includes('booking') ? ['Bookings'] : ['Vehicles'] }),
    write: builder.mutation<unknown, Call>({ query: ({ url, method = 'POST', body, headers }) => ({ url, method, body, headers }), invalidatesTags: (_r, _e, call) => call.url.includes('/tickets') ? ['Tickets'] : call.url.includes('booking') ? ['Bookings'] : ['Vehicles'] }),
  }),
});

export const { useReadQuery, useLazyReadQuery, useWriteMutation } = apiSlice;
async function get<T>(url: string): Promise<T> {
  try { return await window.__drivewellDispatch!(apiSlice.endpoints.read.initiate(url, { subscribe: false })).unwrap() as T; }
  catch (error) { throw requestError(error); }
}
async function post<T>(url: string, body: unknown, method = 'POST', headers?: Record<string, string>, successMessage?: string): Promise<T> {
  const dispatch = window.__drivewellDispatch!;
  try {
    const result = await dispatch(apiSlice.endpoints.write.initiate({ url, body, method, headers })).unwrap() as T;
    if (successMessage) announceToast({ type: 'success', message: successMessage });
    return result;
  } catch (error) {
    const normalized = requestError(error);
    announceToast({ type: 'error', message: normalized.message });
    throw normalized;
  }
}
function requestError(error: any) { const message = error?.data?.detail; return new Error(typeof message === 'string' ? message : error?.error || 'The request could not be completed.'); }

// Existing page handlers use this small facade; all transport, auth headers, cache, and invalidation are RTK Query managed.
export const api = {
  async auth(path: string, body: unknown) { return post<{ message?: string; verification_code?: string; user?: { id: string; email: string; name: string; role: string }; tokens?: Record<string, string> }>(`${authBase}${path}`, body); },
  vehicles() { return get<Vehicle[]>(`${carBase}?limit=250`); },
  vehicle(id: string) { return get<Vehicle>(`${carBase}/${id}`); },
  createVehicle(payload: Record<string, unknown>) { return post<Vehicle>(carBase, payload, 'POST', undefined, 'Vehicle added to your fleet.'); },
  updateVehicle(id: string, payload: Record<string, unknown>) { return post<Vehicle>(`${carBase}/${id}`, payload, 'PATCH', undefined, 'Vehicle details updated.'); },
  deleteVehicle(id: string) { return post<Vehicle>(`${carBase}/${id}`, {}, 'DELETE', undefined, 'Vehicle retired from the fleet.'); },
  availability(pickup: string, returnTime: string, make?: string) { const query = new URLSearchParams({ pickup_at: pickup, return_at: returnTime, limit: '250' }); if (make) query.set('make', make); return get<Vehicle[]>(`${bookingBase}/availability?${query}`); },
  createBooking(vehicleId: string, pickup: string, returnTime: string) { return post<Booking>(bookingBase, { vehicle_id: vehicleId, pickup_at: pickup, return_at: returnTime, agreement_accepted: true, agreement_version: 'draft-1' }, 'POST', undefined, 'Booking created. Continue to secure checkout.'); },
  kycStatus() { return get<KycStatus>(`${authBase}/kyc`); },
  uploadKycDocument(type: 'driver_license' | 'identity_document', file: File) { const body = new FormData(); body.append('file', file); return post(`${authBase}/kyc/documents/${type}`, body, 'POST', undefined, 'Verification document submitted for review.'); },
  kycReviews() { return get<KycReview[]>(`${authBase}/admin/kyc`); },
  reviewKycDocument(id: string, decision: 'approved' | 'rejected', note: string) { return post(`${authBase}/admin/kyc/documents/${id}/review`, { decision, note }, 'POST', undefined, `Document ${decision}.`); },
  async kycDocument(id: string) {
    const response = await fetch(`${authBase}/admin/kyc/documents/${id}`, { headers: { Authorization: `Bearer ${tokenStore.get()}` }, cache: 'no-store' });
    if (!response.ok) throw new Error('Could not load the private verification document.');
    return URL.createObjectURL(await response.blob());
  },
  bookings() { return get<Booking[]>(bookingBase); },
  operationsBookings(status?: string) { const query = new URLSearchParams(); if (status) query.set('status', status); return get<Booking[]>(`${bookingBase}/operations${query.size ? `?${query}` : ''}`); },
  bookingAction(id: string, action: 'cancel' | 'start' | 'return' | 'inspection', payload?: unknown) {
    const success = { cancel: 'Booking cancelled.', start: 'Rental started.', return: 'Vehicle return recorded.', inspection: 'Inspection submitted.' }[action];
    return post<Booking>(`${bookingBase}/${id}/${action}`, payload ?? {}, 'POST', undefined, success);
  },
  requestBookingReturn(id: string) { return post<Booking>(`${bookingBase}/${id}/return-request`, {}); },
  booking(id: string) { return get<Booking>(`${bookingBase}/${id}`); },
  receipt(id: string) { return get<Receipt>(`${bookingBase}/${id}/receipt`); },
  paymentIntent(id: string) { return post<{ client_secret: string; amount_minor: number; currency: string }>(`${bookingBase}/${id}/payment-intent`, {}, 'POST', { 'Idempotency-Key': `drivewell-${id}` }, 'Secure checkout is ready.'); },
  syncPayment(id: string) { return post<{ booking_id: string; booking_status: string; payment_status: string }>(`${bookingBase}/${id}/payment-status`, {}); },
  tickets(all = false) { return get<SupportTicket[]>(`${authBase}/support/tickets${all ? '?all_tickets=true' : ''}`); },
  createTicket(payload: { subject: string; message: string }) { return post<SupportTicket>(`${authBase}/support/tickets`, payload, 'POST', undefined, 'Support conversation created.'); },
  replyTicket(id: string, body: string, parent_id?: string) { return post(`${authBase}/support/tickets/${id}/messages`, { body, parent_id }, 'POST', undefined, 'Your message was sent.'); },
  updateTicket(id: string, payload: Record<string, unknown>) { return post<SupportTicket>(`${authBase}/support/tickets/${id}`, payload, 'PATCH', undefined, 'Support ticket updated.'); },
  deleteTicket(id: string) { return post<void>(`${authBase}/support/tickets/${id}`, {}, 'DELETE', undefined, 'Support ticket deleted.'); },
  users() { return get<Array<{ id: string; email: string; name: string; role: string; is_active: boolean; is_email_verified: boolean; created_at: string }>>(`${authBase}/admin/users`); },
  updateUser(id: string, payload: Record<string, unknown>) { return post<{ id: string; email: string; name: string; role: string; is_active: boolean; is_email_verified: boolean; created_at: string }>(`${authBase}/admin/users/${id}`, payload, 'PATCH', undefined, 'Customer account updated.'); },
  deleteUser(id: string) { return post<void>(`${authBase}/admin/users/${id}`, {}, 'DELETE', undefined, 'Customer account disabled.'); },
};

declare global { interface Window { __drivewellDispatch?: (action: unknown) => any } }

export type KycStatus = { status: 'not_submitted' | 'pending' | 'rejected' | 'verified'; documents: Record<'driver_license' | 'identity_document', 'missing' | 'pending' | 'approved' | 'rejected'> };
export type KycReview = { user: { id: string; name: string; email: string }; status: KycStatus['status']; documents: KycStatus['documents']; items: Array<{ id: string; type: 'driver_license' | 'identity_document'; status: 'pending' | 'approved' | 'rejected'; filename: string; submitted_at: string; review_note?: string | null }> };

export function imageFor(vehicle: Pick<Vehicle, 'make' | 'model' | 'category'>) {
  const key = `${vehicle.make} ${vehicle.model} ${vehicle.category}`.toLowerCase();
  if (key.includes('tesla') || key.includes('roadster')) return '/cars/tesla-roaster.jpeg';
  if (key.includes('g-class') || key.includes('g-wagon') || key.includes('g-wankon')) return '/cars/g-wankon.jpeg';
  if (key.includes('rolls')) return '/cars/rolls-royce.jpeg';
  if (key.includes('lamborghini') || key.includes('lambo')) return '/cars/LAMBO.jpeg';
  if (key.includes('bmw')) return '/cars/BMW.jpeg';
  if (key.includes('benz') || key.includes('mercedes')) return '/cars/benz.jpeg';
  if (key.includes('ford')) return '/cars/ford.jpeg';
  if (key.includes('jeep')) return '/cars/jeep.jpeg';
  if (key.includes('toyota') && key.includes('camry')) return '/cars/toyota-camry.jpeg';
  return '/cars/SUV.jpeg';
}
export function money(minor: number | null | undefined, currency = 'USD') { return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format((minor || 0) / 100); }
export function dateTime(value: string, options: Intl.DateTimeFormatOptions = {}) { const format: Intl.DateTimeFormatOptions = Object.keys(options).length ? options : { dateStyle: 'medium', timeStyle: 'short' }; return new Intl.DateTimeFormat('en-US', format).format(new Date(value)); }
