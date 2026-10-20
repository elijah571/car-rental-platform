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
export const apiSlice = createApi({
  reducerPath: 'drivewellApi',
  baseQuery: fetchBaseQuery({
    baseUrl: '',
    prepareHeaders: (headers) => {
      headers.set('Content-Type', 'application/json');
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
async function post<T>(url: string, body: unknown, method = 'POST', headers?: Record<string, string>): Promise<T> {
  const dispatch = window.__drivewellDispatch!;
  try { return await dispatch(apiSlice.endpoints.write.initiate({ url, body, method, headers })).unwrap() as T; }
  catch (error) { throw requestError(error); }
}
function requestError(error: any) { const message = error?.data?.detail; return new Error(typeof message === 'string' ? message : error?.error || 'The request could not be completed.'); }

// Existing page handlers use this small facade; all transport, auth headers, cache, and invalidation are RTK Query managed.
export const api = {
  async auth(path: string, body: unknown) { return post<{ message?: string; verification_code?: string; user?: { id: string; email: string; name: string; role: string }; tokens?: Record<string, string> }>(`${authBase}${path}`, body); },
  vehicles() { return get<Vehicle[]>(carBase); },
  createVehicle(payload: Record<string, unknown>) { return post<Vehicle>(carBase, payload); },
  updateVehicle(id: string, payload: Record<string, unknown>) { return post<Vehicle>(`${carBase}/${id}`, payload, 'PATCH'); },
  deleteVehicle(id: string) { return post<Vehicle>(`${carBase}/${id}`, {}, 'DELETE'); },
  availability(pickup: string, returnTime: string) { const query = new URLSearchParams({ pickup_at: pickup, return_at: returnTime }); return get<Vehicle[]>(`${bookingBase}/availability?${query}`); },
  createBooking(vehicleId: string, pickup: string, returnTime: string) { return post<Booking>(bookingBase, { vehicle_id: vehicleId, pickup_at: pickup, return_at: returnTime }); },
  bookings() { return get<Booking[]>(bookingBase); },
  operationsBookings(status?: string) { const query = new URLSearchParams(); if (status) query.set('status', status); return get<Booking[]>(`${bookingBase}/operations${query.size ? `?${query}` : ''}`); },
  bookingAction(id: string, action: 'cancel' | 'start' | 'return' | 'inspection', payload?: unknown) { return post<Booking>(`${bookingBase}/${id}/${action}`, payload ?? {}); },
  booking(id: string) { return get<Booking>(`${bookingBase}/${id}`); },
  receipt(id: string) { return get<Receipt>(`${bookingBase}/${id}/receipt`); },
  paymentIntent(id: string) { return post<{ client_secret: string; amount_minor: number; currency: string }>(`${bookingBase}/${id}/payment-intent`, {}, 'POST', { 'Idempotency-Key': `drivewell-${id}` }); },
  syncPayment(id: string) { return post<{ booking_id: string; booking_status: string; payment_status: string }>(`${bookingBase}/${id}/payment-status`, {}); },
  tickets(all = false) { return get<SupportTicket[]>(`${authBase}/support/tickets${all ? '?all_tickets=true' : ''}`); },
  createTicket(payload: { subject: string; message: string }) { return post<SupportTicket>(`${authBase}/support/tickets`, payload); },
  replyTicket(id: string, body: string, parent_id?: string) { return post(`${authBase}/support/tickets/${id}/messages`, { body, parent_id }); },
  updateTicket(id: string, payload: Record<string, unknown>) { return post<SupportTicket>(`${authBase}/support/tickets/${id}`, payload, 'PATCH'); },
  deleteTicket(id: string) { return post<void>(`${authBase}/support/tickets/${id}`, {}, 'DELETE'); },
  users() { return get<Array<{ id: string; email: string; name: string; role: string; is_active: boolean; is_email_verified: boolean; created_at: string }>>(`${authBase}/admin/users`); },
  updateUser(id: string, payload: Record<string, unknown>) { return post<{ id: string; email: string; name: string; role: string; is_active: boolean; is_email_verified: boolean; created_at: string }>(`${authBase}/admin/users/${id}`, payload, 'PATCH'); },
  deleteUser(id: string) { return post<void>(`${authBase}/admin/users/${id}`, {}, 'DELETE'); },
};

declare global { interface Window { __drivewellDispatch?: (action: unknown) => any } }

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
