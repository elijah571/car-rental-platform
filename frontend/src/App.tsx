import { Fragment, lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowLeft, ArrowRight, ArrowUpRight, BadgeCheck, CalendarDays, CarFront, Check, ChevronDown, CircleAlert, CircleHelp, Clock3, Compass, CreditCard, Download, Fuel, Gauge, KeyRound, LayoutDashboard, ListFilter, LockKeyhole, LogOut, Menu, MessageCircle, Plus, Search, Send, Settings, ShieldCheck, SlidersHorizontal, Sparkles, ThumbsUp, Users, Wifi, WifiOff, X } from 'lucide-react';
import { api, dateTime, imageFor, money, tokenStore } from './api';
import type { Booking, Receipt, Vehicle } from './types';
import type { KycReview, KycStatus } from './api';

type Page = 'explore' | 'results' | 'detail' | 'checkout' | 'bookings' | 'account' | 'support' | 'admin';
function pageForPath(path: string): Page {
  if (path === '/cars') return 'results';
  if (path.startsWith('/cars/')) return 'detail';
  if (path === '/checkout') return 'checkout';
  if (path === '/bookings') return 'bookings';
  if (path === '/account') return 'account';
  if (path === '/support') return 'support';
  if (path.startsWith('/admin')) return 'admin';
  return 'explore';
}
function pathForPage(page: Page, selected: Vehicle | null): string | null {
  if (page === 'explore') return '/';
  if (page === 'results') return '/cars';
  if (page === 'detail') return /^\/cars\/[^/]+$/.test(window.location.pathname) ? window.location.pathname : selected ? `/cars/${selected.id}` : null;
  if (page === 'checkout') return '/checkout';
  if (page === 'bookings') return '/bookings';
  if (page === 'account') return '/account';
  if (page === 'support') return '/support';
  return window.location.pathname.startsWith('/admin') ? window.location.pathname : '/admin';
}
type AdminSection = 'overview' | 'vehicles' | 'bookings' | 'inspections' | 'settings' | 'support' | 'customers';
function adminSectionForPath(path: string): AdminSection {
  const section = path.split('/')[2];
  return ['vehicles', 'bookings', 'inspections', 'settings', 'support', 'customers'].includes(section) ? section as AdminSection : 'overview';
}
const stripeKey = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || '';
const stripeConfigured = stripeKey.startsWith('pk_') && !stripeKey.includes('replace_me');
const StripePaymentWidget = lazy(() => import('./StripePayment'));
const initials = (email?: string) => email ? email.slice(0, 2).toUpperCase() : 'EP';
const localInputDate = (date: Date) => { const offset = date.getTimezoneOffset(); return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 16); };
const rentalDurations = [...Array.from({ length: 24 }, (_, index) => index + 1), 36, 48, 72, 96, 120, 144, 168];
const estimateRentalTotal = (hourlyRate: number | string, hours: number) => Math.round(Number(hourlyRate) * 100 * hours);

export default function App() {
  const [page, setPage] = useState<Page>(() => pageForPath(window.location.pathname));
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [matches, setMatches] = useState<Vehicle[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [selected, setSelected] = useState<Vehicle | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [pickup] = useState(() => localInputDate(new Date(Date.now() + 86_400_000)));
  const [durationHours, setDurationHours] = useState(24);
  const dropoff = localInputDate(new Date(new Date(pickup).getTime() + durationHours * 3_600_000));
  const [filter, setFilter] = useState('All vehicles');
  const [brandFilter, setBrandFilter] = useState('All brands');
  const [rateFilter, setRateFilter] = useState('Any rate');
  const [sortBy, setSortBy] = useState('recommended');
  const [view, setView] = useState<'login' | 'register' | 'confirm' | 'resend' | 'forgot' | 'reset' | null>(null);
  const [accountEmail, setAccountEmail] = useState(localStorage.getItem('drivewell_email') || '');
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const toastTimer = useRef<number | undefined>(undefined);
  const lastToast = useRef<{ type: 'success' | 'error'; message: string; at: number } | null>(null);
  function showToast(type: 'success' | 'error', message: string) {
    if (!message) return;
    const previous = lastToast.current;
    if (previous?.type === type && previous.message === message && Date.now() - previous.at < 800) return;
    lastToast.current = { type, message, at: Date.now() };
    setToast({ type, message });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 4200);
  }
  const setError = (message: string) => showToast('error', message);
  const setNotice = (message: string) => showToast('success', message);
  useEffect(() => {
    const onToast = (event: Event) => {
      const detail = (event as CustomEvent<{ type: 'success' | 'error'; message: string }>).detail;
      if (detail?.message) showToast(detail.type, detail.message);
    };
    window.addEventListener('drivewell:toast', onToast);
    return () => {
      window.removeEventListener('drivewell:toast', onToast);
      window.clearTimeout(toastTimer.current);
    };
  }, []);
  const [kycPrompt, setKycPrompt] = useState<{ status: string; message: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeBooking, setActiveBooking] = useState<Booking | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const availabilityRequest = useRef(0);

  useEffect(() => { api.vehicles().then(setVehicles).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    const vehicleId = window.location.pathname.match(/^\/cars\/([^/]+)$/)?.[1];
    if (vehicleId) api.vehicle(vehicleId).then((vehicle) => setSelected(vehicle)).catch((e) => setError(e.message));
    const syncRoute = () => {
      const next = pageForPath(window.location.pathname);
      setPage(next);
      const id = window.location.pathname.match(/^\/cars\/([^/]+)$/)?.[1];
      if (id) api.vehicle(id).then(setSelected).catch((e) => setError(e.message));
    };
    window.addEventListener('popstate', syncRoute);
    return () => window.removeEventListener('popstate', syncRoute);
  }, []);
  useEffect(() => {
    const target = pathForPage(page, selected);
    if (target && window.location.pathname !== target) window.history.pushState({}, '', target);
  }, [page, selected]);
  useEffect(() => { if (page === 'results' && !hasSearched) void findCars(); }, [page, hasSearched]);
  useEffect(() => {
    if (page === 'checkout' && !selected) setPage('explore');
    else if (['bookings', 'account', 'support'].includes(page) && !tokenStore.get()) setView('login');
  }, [page, selected]);
  useEffect(() => {
    if (!showHowItWorks || page !== 'explore') return;
    const section = document.getElementById('how-it-works');
    if (!section) return;
    setShowHowItWorks(false);
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [page, showHowItWorks]);
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const id = query.get('booking_id');
    if (query.get('payment') === 'return' && id) {
      setPage('bookings');
      setNotice('Payment received. Confirming your booking…');
      void syncPaymentUntilSettled(id);
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  const categories = useMemo(() => ['All vehicles', ...Array.from(new Set(vehicles.map((v) => v.category)))], [vehicles]);
  const brands = useMemo(() => ['All brands', ...Array.from(new Set(vehicles.map((v) => v.make).filter(Boolean))).sort((a, b) => a.localeCompare(b))], [vehicles]);
  const visibleVehicles = useMemo(() => {
    const list = (page === 'results' ? (hasSearched ? matches : []) : vehicles).filter((v) => {
      const rate = Number(v.hourly_rate);
      return (filter === 'All vehicles' || v.category === filter) &&
        (brandFilter === 'All brands' || v.make === brandFilter) &&
        (rateFilter === 'Any rate' || (rateFilter === 'Under $25' && rate < 25) || (rateFilter === '$25–$50' && rate >= 25 && rate <= 50) || (rateFilter === '$50+' && rate > 50));
    });
    return [...list].sort((a, b) => {
      const primary = sortBy === 'price-low' ? Number(a.hourly_rate) - Number(b.hourly_rate)
        : sortBy === 'price-high' ? Number(b.hourly_rate) - Number(a.hourly_rate)
          : sortBy === 'brand' ? a.make.localeCompare(b.make) : 0;
      return primary || a.make.localeCompare(b.make) || a.model.localeCompare(b.model) || a.id.localeCompare(b.id);
    });
  }, [brandFilter, filter, hasSearched, matches, page, rateFilter, sortBy, vehicles]);

  async function findCars(category?: string, make?: string) {
    const requestId = ++availabilityRequest.current;
    if (category !== undefined) { setFilter(category); setBrandFilter('All brands'); }
    else if (make === undefined) { setFilter('All vehicles'); setBrandFilter('All brands'); }
    if (make !== undefined) setBrandFilter(make || 'All brands');
    setError(''); setPage('results'); setLoading(true); setHasSearched(true);
    try {
      const pickupIso = new Date(pickup).toISOString(); const returnIso = new Date(new Date(pickup).getTime() + 3_600_000).toISOString();
      const list = await api.availability(pickupIso, returnIso, make || undefined);
      if (requestId === availabilityRequest.current) setMatches(list);
    } catch (e) {
      if (requestId === availabilityRequest.current) { setError((e as Error).message); setMatches([]); }
    } finally { if (requestId === availabilityRequest.current) setLoading(false); }
  }

  function needLogin() { if (!tokenStore.get()) { setView('login'); return false; } return true; }

  async function ensureKycEligible() {
    if (!needLogin()) return false;
    try {
      const status = await api.kycStatus();
      if (status.status === 'verified') return true;
      setKycPrompt({
        status: status.status,
        message: status.status === 'pending'
          ? 'Your documents are submitted and awaiting administrator approval. You can rent after both the driver licence and identity document are approved.'
          : status.status === 'rejected'
            ? 'An administrator rejected a verification document. Upload a replacement in your account, then wait for approval before renting.'
            : 'Upload your driver licence and identity document in your account. An administrator must approve both documents before you can rent.',
      });
      return false;
    } catch (error) {
      setError((error as Error).message);
      return false;
    }
  }

  async function startBooking(vehicle: Vehicle) {
    setSelected(vehicle); setError('');
    if (!await ensureKycEligible()) return;
    setActiveBooking(null); setClientSecret(''); setPage('checkout');
  }

  async function createCheckoutBooking() {
    if (!selected || !await ensureKycEligible()) return;
    setLoading(true); setError('');
    try {
      const booking = await api.createBooking(selected.id, new Date(pickup).toISOString(), new Date(dropoff).toISOString());
      setActiveBooking(booking);
    } catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }

  async function beginPayment() {
    if (!activeBooking || !await ensureKycEligible()) return;
    setLoading(true); setError('');
    try {
      const payment = await api.paymentIntent(activeBooking.id);
      if (!stripeConfigured) throw new Error('Stripe is not configured. Set VITE_STRIPE_PUBLISHABLE_KEY to your test publishable key.');
      setClientSecret(payment.client_secret);
    } catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }

  const [clientSecret, setClientSecret] = useState('');

  async function loadBookings() {
    try { const result = await api.bookings(); setBookings(result); return result; }
    catch (e) { setError((e as Error).message); return []; }
  }

  async function syncPaymentUntilSettled(bookingId: string) {
    const deadline = Date.now() + 90_000;
    do {
      try {
        const payment = await api.syncPayment(bookingId);
        const currentBookings = await loadBookings();
        const booking = currentBookings.find((item) => item.id === bookingId);
        if (booking && ['confirmed', 'active', 'awaiting_inspection', 'inspection_failed', 'completed'].includes(booking.status)) {
          setNotice('Payment successful. Your booking is confirmed.');
          return;
        }
        if (['requires_payment_method', 'canceled'].includes(payment.payment_status)) {
          setNotice('Payment was not completed. Your booking is still pending payment.');
          return;
        }
        if (payment.payment_status === 'not_started') {
          setNotice('No payment was found for this booking. Select the booking to continue payment.');
          return;
        }
      } catch (e) { setError((e as Error).message); }
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
    } while (Date.now() < deadline);
    setNotice('Your payment is still processing. Refresh your bookings in a moment.');
  }

  async function openBookings() { if (!needLogin()) return; setPage('bookings'); await loadBookings(); }

  async function openReceipt(booking: Booking) {
    setError('');
    try { setReceipt(await api.receipt(booking.id)); setActiveBooking(booking); }
    catch (e) { setError((e as Error).message); setReceipt(null); }
  }

  async function handleAuth(form: FormData) {
    const email = String(form.get('email') || ''); const password = String(form.get('password') || '');
    setError(''); setNotice('');
    try {
      if (view === 'register') {
        const result = await api.auth('/register', { email, password, name: String(form.get('name') || '') });
        setAccountEmail(email); setView('confirm'); setNotice(result.verification_code ? `Account created. Local verification code: ${result.verification_code}` : 'Account created. Enter the verification code sent to your email.');
      } else if (view === 'confirm') {
        await api.auth('/confirm', { email, confirmation_code: String(form.get('code') || '') });
        setView('login'); setNotice('Email verified. Sign in to continue.');
      } else if (view === 'resend') {
        const result = await api.auth('/resend-code', { email });
        setAccountEmail(email); setView('confirm');
        setNotice(result.verification_code ? `If this account needs verification, use this local development code: ${result.verification_code}` : 'If this account needs verification, a new code has been sent to your email.');
      } else if (view === 'forgot') {
        const result = await api.auth('/forgot-password', { email });
        setView('reset'); setNotice(result.verification_code ? `Reset code for local development: ${result.verification_code}` : result.message || 'Check your email for a password reset code.');
      } else if (view === 'reset') {
        await api.auth('/reset-password', { email, code: String(form.get('code') || ''), new_password: String(form.get('password') || '') });
        setView('login'); setNotice('Password reset. Sign in with your new password.');
      } else {
        const result = await api.auth('/login', { email, password });
        const access = result.tokens?.AccessToken;
        if (!access) throw new Error('Sign-in did not return an access token. Please try again.');
        tokenStore.set(access);
        if (result.tokens?.RefreshToken) tokenStore.setRefresh(result.tokens.RefreshToken);
        localStorage.setItem('drivewell_email', email);
        if (result.user?.role) localStorage.setItem('drivewell_role', result.user.role);
        setAccountEmail(email); setView(null); setNotice('You are signed in.');
      }
    } catch (e) {
      const message = (e as Error).message;
      setError(message);
      if (view === 'login' && /verify your email/i.test(message)) {
        setAccountEmail(email); setView('confirm'); setNotice('Your email is not verified. Enter your code or request a new one.');
      }
    }
  }

  function logout() {
    const refreshToken = tokenStore.getRefresh();
    if (refreshToken) void api.auth('/logout', { refresh_token: refreshToken }).catch(() => undefined);
    tokenStore.clear(); tokenStore.clearRefresh(); localStorage.removeItem('drivewell_email'); localStorage.removeItem('drivewell_role'); setAccountEmail(''); setBookings([]); setPage('explore'); setNotice('You have signed out.');
  }

  function navigate(next: Page) {
    setMobileOpen(false); setError('');
    if (next === 'bookings') { void openBookings(); return; }
    if ((next === 'account' || next === 'support') && !needLogin()) return;
    if (next === 'admin' && !needLogin()) return;
    setPage(next);
  }

  function openHowItWorks() {
    setMobileOpen(false);
    setError('');
    setPage('explore');
    setShowHowItWorks(true);
  }

  return <>
    <div className="app-shell">
      {page === 'admin' ? <AdminShell vehicles={vehicles} onVehicle={setVehicles} onExit={() => setPage('explore')} onHowItWorks={openHowItWorks} setError={setError} /> : <>
        <header className="topbar">
          <a className="brand" href="#" onClick={(e) => { e.preventDefault(); navigate('explore'); }}><img className="brand-logo" src="/logo.png" alt="Driveflow Car Rental Platform" /></a>
          <button className="mobile-menu" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Toggle menu">{mobileOpen ? <X /> : <Menu />}</button>
          <nav className={mobileOpen ? 'nav-links open' : 'nav-links'}>
            <button className={page === 'explore' || page === 'results' || page === 'detail' ? 'nav-active' : ''} onClick={() => navigate('explore')}>Explore</button>
            <button className={page === 'bookings' ? 'nav-active' : ''} onClick={() => navigate('bookings')}>My bookings</button>
            <button onClick={openHowItWorks}>How it works</button>
            <button onClick={() => navigate('support')}>Help & support</button>
          </nav>
          <div className="account-nav">
            <button className="avatar" onClick={() => navigate('account')}>{initials(tokenStore.get() ? accountEmail : undefined)}</button>
            <button className="account-link" onClick={() => tokenStore.get() ? navigate('account') : setView('login')}>{tokenStore.get() && accountEmail ? accountEmail.split('@')[0] : 'Account'} <ChevronDown size={14} /></button>
          </div>
        </header>
        <main>
          {page === 'explore' && <Landing findCars={findCars} />}
          {page === 'results' && <Results vehicles={visibleVehicles} categories={categories} brands={brands} filter={filter} setFilter={setFilter} brandFilter={brandFilter} onBrandChange={(brand) => void findCars(undefined, brand === 'All brands' ? '' : brand)} rateFilter={rateFilter} setRateFilter={setRateFilter} sortBy={sortBy} setSortBy={setSortBy} loading={loading || !hasSearched} onSelect={(v) => { setSelected(v); setPage('detail'); }} />}
          {page === 'detail' && selected && <Detail vehicle={selected} pickup={pickup} onBack={() => setPage('results')} onBook={() => void startBooking(selected)} loading={loading} />}
          {page === 'checkout' && selected && <Checkout booking={activeBooking} vehicle={selected} pickup={pickup} durationHours={durationHours} setDurationHours={setDurationHours} clientSecret={clientSecret} onCreateBooking={createCheckoutBooking} onPay={beginPayment} loading={loading} onBack={() => { if (activeBooking) void openBookings(); else setPage('detail'); }} />}
          {page === 'bookings' && <Bookings bookings={bookings} onRefresh={loadBookings} onReceipt={openReceipt} onCheckPayment={(id) => syncPaymentUntilSettled(id)} onReturn={async (booking) => { try { await api.requestBookingReturn(booking.id); await loadBookings(); setNotice('Return reported. The support team will inspect the vehicle before it is listed again.'); } catch (e) { setError((e as Error).message); } }} />}
          {page === 'account' && <Account email={accountEmail} onLogout={logout} onAdmin={() => navigate('admin')} onSupport={() => navigate('support')} onPasswordChanged={() => { setAccountEmail(''); setPage('explore'); setView('login'); setNotice('Password changed. Sign in with your new password.'); }} />}
          {page === 'support' && <SupportCenter onError={setError} />}
        </main>
        <footer className="footer"><span>DRIVEWELL / YOUR JOURNEY, WELL TAKEN</span><span>Clear pricing. Confident journeys.</span><span>© 2026 Drivewell</span></footer>
      </>}
    </div>
    {toast && <div className={`action-toast action-toast-${toast.type}`} role={toast.type === 'error' ? 'alert' : 'status'} aria-live={toast.type === 'error' ? 'assertive' : 'polite'}>
      <span className="action-toast-icon">{toast.type === 'success' ? <ThumbsUp size={18} strokeWidth={2.2} /> : <CircleAlert size={18} strokeWidth={2.2} />}</span>
      <span className="action-toast-message">{toast.message}</span>
      <button type="button" onClick={() => setToast(null)} aria-label="Dismiss notification"><X size={16} /></button>
      <span className="action-toast-progress" />
    </div>}
    {receipt && <ReceiptDialog receipt={receipt} onClose={() => setReceipt(null)} />}
    {view && <AuthDialog mode={view} email={accountEmail} onClose={() => setView(null)} onSwitch={setView} onSubmit={handleAuth} />}
    {kycPrompt && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setKycPrompt(null); }}><section className="confirm-modal kyc-required-modal" role="alertdialog" aria-modal="true" aria-labelledby="kyc-required-title" aria-describedby="kyc-required-message"><button className="modal-close" aria-label="Close verification notice" onClick={() => setKycPrompt(null)}><X size={19} /></button><span className="auth-icon"><ShieldCheck size={23} /></span><p className="eyebrow">VERIFICATION REQUIRED</p><h2 id="kyc-required-title">Complete driver verification to rent</h2><p id="kyc-required-message" className="muted">{kycPrompt.message}</p><p className="kyc-approval-note">Your rental stays blocked until an administrator approves both required documents.</p><div className="form-actions"><button className="btn btn-outline" onClick={() => setKycPrompt(null)}>Not now</button><button className="btn btn-primary" onClick={() => { setKycPrompt(null); setPage('account'); }}> {kycPrompt.status === 'pending' ? 'View verification status' : 'Submit documents'} <ArrowRight size={15} /></button></div></section></div>}
  </>;
}

function Landing({ findCars }: { findCars: (category?: string) => void }) {
  return <>
    <section className="hero wrap">
      <div className="hero-copy"><p className="eyebrow"><span className="eyebrow-line" /> THE KEYS TO YOUR NEXT JOURNEY</p><h1>Your next ride,<br /><em>on your terms.</em></h1><p className="hero-text">Find the right car for your plans. Choose your vehicle and set the rental duration at checkout.</p><div className="price-chip"><Sparkles size={15} /> Vehicle specific hourly rates <span>•</span> USD pricing</div><div className="hero-trust"><span><ShieldCheck size={15} /> Secure booking</span><span><BadgeCheck size={15} /> Verified availability</span></div></div>
      <div className="hero-art"><img src="/cars/tesla-roaster.jpeg" alt="A premium electric car ready for your next journey" /><div className="art-label"><span className="live-dot" /> THE OPEN ROAD IS CALLING</div><div className="art-stamp">DW<br /><span>EST. 2026</span></div></div>
    </section>
    <section className="browse-panel wrap">
      <button className="btn btn-primary find-button" onClick={() => void findCars()}>Browse available cars <ArrowRight size={17} /></button>
    </section>
    <section className="category-section wrap"><div className="section-heading"><div><p className="eyebrow">CURATED FOR YOUR PLANS</p><h2>Find your kind of drive</h2></div><button className="text-link" onClick={() => void findCars()}>Explore all cars <ArrowUpRight size={16} /></button></div><div className="category-grid">
      <CategoryCard name="Everyday" note="Practical for daily plans" category="Sedan" number="01" image="/cars/toyota-camry.jpeg" onClick={() => void findCars('Sedan')} />
      <CategoryCard name="Room for more" note="Space for every passenger" category="SUV" number="02" image="/cars/SUV.jpeg" onClick={() => void findCars('SUV')} />
      <CategoryCard name="Make it memorable" note="The finer things in motion" category="Premium" number="03" image="/cars/BMW.jpeg" onClick={() => void findCars('Premium')} />
    </div></section>
    <section id="how-it-works" className="how-section"><div className="wrap how-inner"><div><p className="eyebrow">A BETTER WAY TO GET THERE</p><h2>Good journeys start<br />with a little clarity.</h2><p className="how-intro">From choosing a vehicle to receiving your confirmation, every step is designed to be straightforward. You can review your rental details and pricing before you pay.</p></div><div className="steps"><Step number="01" title="Choose your car" text="Browse the fleet and compare vehicle details, categories, and hourly rates. Pick the car that fits your plans, passengers, and luggage." /><Step number="02" title="Set your own pace" text="Choose your vehicle, then set the rental duration in checkout. The hourly rate is set for each vehicle and the total updates as you choose your hours." /><Step number="03" title="Drive with confidence" text="Sign in to reserve your vehicle, then complete payment securely. Once payment is verified, your booking is confirmed and your receipt is sent by email." /></div></div></section>
    <div className="wrap reassurance"><div><ShieldCheck size={19} /><span>Secure checkout powered by Stripe</span></div><div><Clock3 size={19} /><span>A 15 minute hold to complete payment</span></div><div><BadgeCheck size={19} /><span>Booking confirmed after verified payment</span></div></div>
  </>;
}

function CategoryCard({ name, note, category, number, image, onClick }: { name: string; note: string; category: string; number: string; image: string; onClick: () => void }) {
  return <button className="category-card" onClick={onClick}><img src={image} alt="" /><span className="category-number">{number} / {category.toUpperCase()}</span><span className="category-info"><strong>{name}</strong><small>{note}</small></span><span className="category-arrow"><ArrowUpRight size={18} /></span></button>;
}

function Step({ number, title, text }: { number: string; title: string; text: string }) { return <div className="step"><span>{number}</span><div><strong>{title}</strong><p>{text}</p></div></div>; }

function useConfirmation() {
  const [dialog, setDialog] = useState<{ title: string; message: string; action: string } | null>(null);
  const resolveRef = useRef<((confirmed: boolean) => void) | null>(null);
  function ask(title: string, message: string, action = 'Confirm') {
    return new Promise<boolean>((resolve) => { resolveRef.current = resolve; setDialog({ title, message, action }); });
  }
  function close(confirmed: boolean) { setDialog(null); resolveRef.current?.(confirmed); resolveRef.current = null; }
  const element = dialog && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) close(false); }}><section className="confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message"><button className="modal-close" aria-label="Close confirmation" onClick={() => close(false)}><X size={19} /></button><span className="auth-icon"><CircleHelp size={22} /></span><p className="eyebrow">CONFIRM ACTION</p><h2 id="confirm-title">{dialog.title}</h2><p id="confirm-message" className="muted">{dialog.message}</p><div className="form-actions"><button className="btn btn-outline" onClick={() => close(false)}>Cancel</button><button className="btn btn-primary" onClick={() => close(true)}>{dialog.action}</button></div></section></div>;
  return { ask, element };
}

function Results({ vehicles, categories, brands, filter, setFilter, brandFilter, onBrandChange, rateFilter, setRateFilter, sortBy, setSortBy, loading, onSelect }: { vehicles: Vehicle[]; categories: string[]; brands: string[]; filter: string; setFilter: (v: string) => void; brandFilter: string; onBrandChange: (v: string) => void; rateFilter: string; setRateFilter: (v: string) => void; sortBy: string; setSortBy: (v: string) => void; loading: boolean; onSelect: (v: Vehicle) => void }) {
  const [search, setSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(8);
  const matchingVehicles = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return query ? vehicles.filter((vehicle) => `${vehicle.make} ${vehicle.model} ${vehicle.category}`.toLocaleLowerCase().includes(query)) : vehicles;
  }, [search, vehicles]);
  const pageCount = Math.max(1, Math.ceil(matchingVehicles.length / pageSize));
  const safePage = Math.min(currentPage, pageCount);
  const pageVehicles = matchingVehicles.slice((safePage - 1) * pageSize, safePage * pageSize);
  const firstResult = matchingVehicles.length ? (safePage - 1) * pageSize + 1 : 0;
  const lastResult = Math.min(safePage * pageSize, matchingVehicles.length);
  const pageItems = Array.from(new Set([1, pageCount, safePage - 1, safePage, safePage + 1].filter((page) => page >= 1 && page <= pageCount))).sort((a, b) => a - b);
  const hasFilters = Boolean(search.trim()) || filter !== 'All vehicles' || brandFilter !== 'All brands' || rateFilter !== 'Any rate';
  useEffect(() => { setCurrentPage(1); }, [vehicles, search, pageSize]);
  useEffect(() => { if (currentPage > pageCount) setCurrentPage(pageCount); }, [currentPage, pageCount]);
  function clearFilters() { setSearch(''); setFilter('All vehicles'); onBrandChange('All brands'); setRateFilter('Any rate'); setCurrentPage(1); }

  return <section className="wrap page-content"><div className="breadcrumb"><span>Explore</span><ArrowRight size={13} /><strong>Find your car</strong></div><div className="page-title-row"><div><p className="eyebrow">THE DRIVEWELL FLEET</p><h1>Find your car</h1><p className="muted">The right vehicle for wherever the day takes you.</p></div><label className="sort-pill"><ListFilter size={15} /><select aria-label="Sort vehicles" value={sortBy} onChange={(e) => setSortBy(e.target.value)}><option value="recommended">Recommended</option><option value="price-low">Hourly rate: low to high</option><option value="price-high">Hourly rate: high to low</option><option value="brand">Brand: A to Z</option></select><ChevronDown size={14} /></label></div>
    <div className="results-layout"><aside className="filter-panel" aria-label="Car filters"><div className="filter-title"><SlidersHorizontal size={17} /><strong>Filters</strong><button onClick={clearFilters} disabled={!hasFilters}>Reset all</button></div><div className="filter-group"><span className="filter-label">VEHICLE TYPE</span>{categories.map((c) => <label className="check-row" key={c}><input type="radio" name="category" checked={filter === c} onChange={() => setFilter(c)} /><span>{c}</span><span className="radio-mark" /></label>)}</div><div className="filter-group"><label className="filter-label" htmlFor="brand-filter">BRAND</label><select id="brand-filter" value={brandFilter} onChange={(e) => onBrandChange(e.target.value)}>{brands.map((brand) => <option key={brand}>{brand}</option>)}</select></div><div className="filter-group"><label className="filter-label" htmlFor="rate-filter">HOURLY RATE</label><select id="rate-filter" value={rateFilter} onChange={(e) => setRateFilter(e.target.value)}><option>Any rate</option><option>Under $25</option><option>$25–$50</option><option>$50+</option></select></div><div className="filter-note"><LockKeyhole size={16} /><span>Set your rental duration in checkout to see the full total.</span></div></aside>
      <div className="vehicle-results"><div className="results-title results-toolbar"><div><h2>Available vehicles</h2><p>{loading ? 'Checking availability…' : `Showing ${firstResult}–${lastResult} of ${matchingVehicles.length} ${matchingVehicles.length === 1 ? 'vehicle' : 'vehicles'}`}</p></div><label className="vehicle-search"><Search size={16} /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search make, model, or type" aria-label="Search cars" />{search && <button type="button" onClick={() => setSearch('')} aria-label="Clear search"><X size={15} /></button>}</label></div>
        {hasFilters && <div className="active-filters" aria-label="Active filters"><span>Filtered by</span>{search.trim() && <button onClick={() => setSearch('')}>“{search.trim()}” <X size={13} /></button>}{filter !== 'All vehicles' && <button onClick={() => setFilter('All vehicles')}>{filter} <X size={13} /></button>}{brandFilter !== 'All brands' && <button onClick={() => onBrandChange('All brands')}>{brandFilter} <X size={13} /></button>}{rateFilter !== 'Any rate' && <button onClick={() => setRateFilter('Any rate')}>{rateFilter} <X size={13} /></button>}<button className="clear-filter-link" onClick={clearFilters}>Clear all</button></div>}
        {loading ? <div className="empty-state" role="status"><span className="spinner" /> Checking available vehicles…</div> : matchingVehicles.length === 0 ? <div className="empty-state"><CarFront size={34} /><h3>{vehicles.length ? 'No cars match these filters' : 'No cars available for these dates'}</h3><p>{vehicles.length ? 'Try removing a filter or changing your search.' : 'Please check back soon as our fleet availability changes.'}</p>{hasFilters && <button className="btn btn-outline" onClick={clearFilters}>Clear filters</button>}</div> : <><div className="vehicle-grid">{pageVehicles.map((v) => <VehicleCard key={v.id} vehicle={v} onSelect={() => onSelect(v)} />)}</div><div className="pagination-bar"><label>Cars per page<select aria-label="Cars per page" value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}><option value={8}>8</option><option value={12}>12</option><option value={24}>24</option></select></label><nav className="pagination" aria-label="Car listing pages"><button className="page-control" onClick={() => setCurrentPage((page) => Math.max(1, page - 1))} disabled={safePage === 1} aria-label="Previous page">‹ <span>Previous</span></button>{pageItems.map((pageNumber, index) => <Fragment key={pageNumber}>{index > 0 && pageNumber - pageItems[index - 1] > 1 && <span className="page-ellipsis" aria-hidden="true">…</span>}<button className={`page-number ${safePage === pageNumber ? 'current' : ''}`} onClick={() => setCurrentPage(pageNumber)} aria-label={`Page ${pageNumber}`} aria-current={safePage === pageNumber ? 'page' : undefined}>{pageNumber}</button></Fragment>)}<button className="page-control" onClick={() => setCurrentPage((page) => Math.min(pageCount, page + 1))} disabled={safePage === pageCount} aria-label="Next page"><span>Next</span> ›</button></nav><span className="page-range">{firstResult}–{lastResult} of {matchingVehicles.length}</span></div></>}
      </div>
    </div></section>;
}

function VehicleCard({ vehicle, onSelect }: { vehicle: Vehicle; onSelect: () => void }) {
  const [saved, setSaved] = useState(() => JSON.parse(localStorage.getItem('drivewell_saved_cars') || '[]').includes(vehicle.id));
  const price = `${money(Math.round(Number(vehicle.hourly_rate) * 100))} / hour`;
  return <article className="vehicle-card"><button className="vehicle-photo" onClick={onSelect}><img src={imageFor(vehicle)} alt={`${vehicle.make} ${vehicle.model}`} /><span className="availability-tag"><span className="live-dot" /> Available</span><span className="photo-arrow"><ArrowUpRight size={17} /></span></button><div className="vehicle-card-body"><div className="vehicle-card-title"><div><h3>{vehicle.make} {vehicle.model}</h3><p>{vehicle.category} <span>·</span> {vehicle.seats} seats <span>·</span> {vehicle.transmission}</p></div><button className="heart" aria-label={saved ? 'Remove saved car' : 'Save car'} aria-pressed={saved} onClick={() => { const ids: string[] = JSON.parse(localStorage.getItem('drivewell_saved_cars') || '[]'); const next = saved ? ids.filter((id) => id !== vehicle.id) : [...new Set([...ids, vehicle.id])]; localStorage.setItem('drivewell_saved_cars', JSON.stringify(next)); setSaved(!saved); }}>{saved ? '♥' : '♡'}</button></div><div className="vehicle-specs"><span><span className="color-dot" style={{ backgroundColor: vehicle.color.toLowerCase() }} />{vehicle.color}</span><span><Fuel size={14} />{vehicle.fuel_type}</span></div><div className="vehicle-card-footer"><div><strong>{price}</strong><small>vehicle hourly rate</small></div><button className="btn btn-dark" onClick={onSelect}>View details <ArrowRight size={15} /></button></div></div></article>;
}

function Detail({ vehicle, pickup, onBack, onBook, loading }: { vehicle: Vehicle; pickup: string; onBack: () => void; onBook: () => void; loading: boolean }) {
  return <section className="wrap page-content"><button className="back-link" onClick={onBack}><ArrowLeft size={16} /> Back to available cars</button><div className="detail-layout"><div><div className="detail-photo"><img src={imageFor(vehicle)} alt={`${vehicle.make} ${vehicle.model}`} /><span className="availability-tag"><span className="live-dot" /> Available</span></div><div className="detail-description"><p className="eyebrow">A DRIVEWELL FAVORITE</p><h1>{vehicle.make} {vehicle.model}</h1><p>A comfortable, carefully selected {vehicle.category.toLowerCase()} for business trips, weekend plans, and everything in between.</p></div><div className="spec-grid"><Spec label="Seats" value={`${vehicle.seats} passengers`} icon={<Users size={18} />} /><Spec label="Transmission" value={vehicle.transmission} icon={<Gauge size={18} />} /><Spec label="Fuel type" value={vehicle.fuel_type} icon={<Fuel size={18} />} /><Spec label="Color" value={vehicle.color} icon={<span className="color-dot" style={{ backgroundColor: vehicle.color.toLowerCase() }} />} /></div><p className="availability-hint"><ShieldCheck size={16} /> Choose the rental duration at checkout. Availability and final pricing are confirmed when you reserve.</p></div><aside className="booking-summary"><p className="eyebrow">YOUR DRIVE, YOUR WAY</p><h3>{vehicle.make} {vehicle.model}</h3><p className="summary-sub">{vehicle.category} · {vehicle.color} · {vehicle.transmission}</p><div className="summary-status"><span className="live-dot" /> Available to reserve</div><div className="summary-price"><strong>{money(Math.round(Number(vehicle.hourly_rate) * 100))}</strong><span>per hour</span><small>USD · set by the fleet administrator</small></div><div className="summary-row"><span><CalendarDays size={15} /> Pickup</span><b>{dateTime(new Date(pickup).toISOString())}</b></div><button className="btn btn-primary full" onClick={onBook} disabled={loading}>Continue to checkout <ArrowRight size={16} /></button><p className="summary-foot"><LockKeyhole size={13} /> Review your duration and total before reserving.</p></aside></div></section>;
}

function Spec({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) { return <div className="spec-item"><span className="spec-icon">{icon}</span><div><small>{label}</small><strong>{value}</strong></div></div>; }

function Checkout({ booking, vehicle, pickup, durationHours, setDurationHours, clientSecret, onCreateBooking, onPay, loading, onBack }: { booking: Booking | null; vehicle: Vehicle; pickup: string; durationHours: number; setDurationHours: (value: number) => void; clientSecret: string; onCreateBooking: () => void; onPay: () => void; loading: boolean; onBack: () => void }) {
  const [seconds, setSeconds] = useState(900);
  const [agreementAccepted, setAgreementAccepted] = useState(false);
  const [agreementOpen, setAgreementOpen] = useState(false);
  const [agreementText, setAgreementText] = useState('');
  const [agreementError, setAgreementError] = useState('');
  async function openAgreement() {
    try { setAgreementText(await (await fetch('/legal/car-rental-agreement.md')).text()); setAgreementError(''); setAgreementOpen(true); }
    catch { setAgreementError('The rental agreement could not be loaded. Please try again.'); }
  }
  useEffect(() => {
    if (!booking) return;
    setSeconds(booking.expires_at ? Math.max(0, Math.floor((new Date(booking.expires_at).getTime() - Date.now()) / 1000)) : 900);
    const timer = window.setInterval(() => setSeconds((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [booking?.id, booking?.expires_at]);
  const hours = booking ? Math.max(1, Math.ceil((new Date(booking.return_at).getTime() - new Date(booking.pickup_at).getTime()) / 3_600_000)) : durationHours;
  const hourlyRateMinor = Math.round(Number(vehicle.hourly_rate) * 100);
  const estimatedTotalMinor = estimateRentalTotal(vehicle.hourly_rate, hours);
  if (!booking) return <><section className="wrap page-content"><button className="back-link" onClick={onBack}><ArrowLeft size={16} /> Back to vehicle</button><div className="page-title-row checkout-title"><div><p className="eyebrow">YOUR RENTAL CART</p><h1>Review your rental</h1><p className="muted">Choose how long you need this car. The total updates from this vehicle’s hourly price.</p></div></div><div className="checkout-layout"><div className="checkout-card"><div className="checkout-card-heading"><span className="step-icon"><CarFront size={18} /></span><div><h2>{vehicle.make} {vehicle.model}</h2><p>{vehicle.category} · {vehicle.color} · {vehicle.seats} seats</p></div></div><div className="rental-picker"><label htmlFor="rental-duration">Rental duration</label><select id="rental-duration" value={durationHours} onChange={(event) => setDurationHours(Number(event.target.value))}>{rentalDurations.map((value) => <option key={value} value={value}>{value < 24 ? `${value} ${value === 1 ? 'hour' : 'hours'}` : `${value / 24} ${value === 24 ? 'day' : 'days'}`}</option>)}</select><small>Maximum rental period: 7 days</small></div><div className="summary-row"><span>Pickup</span><b>{dateTime(new Date(pickup).toISOString())}</b></div><div className="summary-row"><span>Return</span><b>{dateTime(new Date(new Date(pickup).getTime() + hours * 3_600_000).toISOString())}</b></div><div className="agreement-consent"><label><input type="checkbox" checked={agreementAccepted} onChange={(event) => setAgreementAccepted(event.target.checked)} /> I have read and agree to the <button type="button" className="inline-agreement-link" onClick={() => void openAgreement()}>rental agreement</button> (version draft-1).</label><p>Draft only: company details and governing law are placeholders, and legal review is pending. This agreement is not yet approved for legal use.</p>{agreementError && <p className="inline-error">{agreementError}</p>}</div><button className="btn btn-primary full" onClick={onCreateBooking} disabled={loading || !agreementAccepted}>{loading ? 'Checking eligibility…' : 'Accept, reserve & continue'} <ArrowRight size={16} /></button><p className="kyc-checkout-link">Driver licence and identity verification are required before a booking can be reserved. <a href="/account" onClick={(event) => { event.preventDefault(); window.history.pushState({}, '', '/account'); window.dispatchEvent(new PopStateEvent('popstate')); }}>Review verification</a></p></div><aside className="booking-summary checkout-summary"><p className="eyebrow">PRICE SUMMARY</p><div className="summary-car"><img src={imageFor(vehicle)} alt="" /><div><strong>{vehicle.make} {vehicle.model}</strong><small>{hours} {hours === 1 ? 'hour' : 'hours'}</small></div></div><div className="summary-row"><span>Hourly rate</span><b>{money(hourlyRateMinor)} / hour</b></div><div className="summary-total"><span>Estimated total</span><b>{money(estimatedTotalMinor)} USD</b></div><p className="checkout-assurance"><ShieldCheck size={16} /> The server verifies this quote and vehicle availability before reserving.</p></aside></div></section>{agreementOpen && <div className="modal-backdrop" onClick={() => setAgreementOpen(false)}><section className="agreement-modal" role="dialog" aria-modal="true" aria-labelledby="agreement-title" onClick={(event) => event.stopPropagation()}><button className="modal-close" aria-label="Close agreement" onClick={() => setAgreementOpen(false)}><X size={19} /></button><p className="eyebrow">VERSION DRAFT-1</p><h2 id="agreement-title">Car rental agreement and terms of use</h2><div className="agreement-draft-warning">Draft only. Legal review and completion of company, effective date, platform, and governing-law fields are required.</div><pre>{agreementText}</pre><div className="form-actions"><button className="btn btn-outline" onClick={() => setAgreementOpen(false)}>Close</button><button className="btn btn-primary" onClick={() => { setAgreementAccepted(true); setAgreementOpen(false); }}>I agree to this draft</button></div></section></div>}</>;
  return <section className="wrap page-content"><button className="back-link" onClick={onBack}><ArrowLeft size={16} /> Back to vehicle</button><div className="page-title-row checkout-title"><div><p className="eyebrow">YOUR JOURNEY IS ALMOST SET</p><h1>Secure checkout</h1><p className="muted">Your vehicle is held temporarily while you complete payment.</p></div><div className="hold-clock"><Clock3 size={17} /><span>{String(Math.floor(seconds / 60)).padStart(2, '0')}:{String(seconds % 60).padStart(2, '0')}<small> minutes remaining</small></span></div></div><div className="checkout-steps"><span className="done"><Check size={14} /> Rental details</span><i /><span className="current"><CreditCard size={14} /> Payment</span><i /><span><BadgeCheck size={14} /> Confirmation</span></div><div className="checkout-layout"><div className="checkout-card"><div className="checkout-card-heading"><span className="step-icon"><CreditCard size={18} /></span><div><h2>Payment method</h2><p>Secure payment powered by Stripe</p></div></div>{clientSecret ? <Suspense fallback={<p className="muted stripe-loading">Loading Stripe’s secure form…</p>}><StripePaymentWidget clientSecret={clientSecret} bookingId={booking.id} /></Suspense> : <div className="stripe-intro"><div className="stripe-symbol">S</div><div><strong>Pay securely with Stripe</strong><p>You’ll continue to Stripe’s secure payment experience. Card details are handled by Stripe and never touch our servers.</p></div><button className="btn btn-primary" onClick={onPay} disabled={loading || seconds === 0}>{loading ? 'Preparing secure checkout…' : 'Continue to payment'} <ArrowRight size={16} /></button></div>}<p className="secure-note"><LockKeyhole size={14} /> Encrypted payment flow · Your card details remain with Stripe</p></div><aside className="booking-summary checkout-summary"><p className="eyebrow">PAYMENT SUMMARY</p><div className="summary-car"><img src={imageFor(vehicle)} alt="" /><div><strong>{booking.vehicle_make || vehicle.make} {booking.vehicle_model || vehicle.model}</strong><small>{hours} hours · {dateTime(booking.pickup_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}–{dateTime(booking.return_at, { hour: 'numeric', minute: '2-digit' })}</small></div></div><div className="summary-row"><span>Rental period</span><b>{hours} hours</b></div><div className="summary-row"><span>Hourly rate</span><b>{money(hourlyRateMinor)} / hour</b></div><div className="summary-total"><span>Total due</span><b>{money(booking.amount_minor)} USD</b></div><p className="checkout-assurance"><ShieldCheck size={16} /> Your booking is confirmed only after Stripe verifies the payment.</p></aside></div></section>;
}

function Bookings({ bookings, onRefresh, onReceipt, onCheckPayment, onReturn }: { bookings: Booking[]; onRefresh: () => void; onReceipt: (b: Booking) => void; onCheckPayment: (id: string) => Promise<void>; onReturn: (booking: Booking) => Promise<void> }) {
  const [tab, setTab] = useState('Upcoming');
  const [checkingId, setCheckingId] = useState<string | null>(null);
  const upcoming = bookings.filter((b) => ['pending', 'confirmed', 'active', 'awaiting_inspection'].includes(b.status));
  const past = bookings.filter((b) => ['completed', 'expired'].includes(b.status));
  const cancelled = bookings.filter((b) => b.status === 'cancelled');
  const list = tab === 'Upcoming' ? upcoming : tab === 'Past rentals' ? past : cancelled;
  useEffect(() => { onRefresh(); }, []);
  async function checkPayment(id: string) {
    setCheckingId(id);
    try { await onCheckPayment(id); }
    finally { setCheckingId(null); }
  }
  return <section className="wrap page-content">
    <div className="page-title-row"><div><p className="eyebrow">YOUR DRIVEWELL ACCOUNT</p><h1>My bookings</h1><p className="muted">Your plans, all in one place.</p></div><button className="btn btn-outline" onClick={onRefresh}>Refresh <ArrowRight size={15} /></button></div>
    <div className="tabs">{['Upcoming', 'Past rentals', 'Cancelled'].map((t) => <button key={t} className={tab === t ? 'tab active' : 'tab'} onClick={() => setTab(t)}>{t}<span>{t === 'Upcoming' ? upcoming.length : t === 'Past rentals' ? past.length : cancelled.length}</span></button>)}</div>
    {list.length ? <div className="booking-list">{list.map((booking) => { const overdue = booking.status === 'active' && new Date(booking.return_at).getTime() <= Date.now(); return <article className="booking-card" key={booking.id}>
      <div className="booking-vehicle-image"><img src={imageFor({ make: booking.vehicle_make || 'Toyota', model: booking.vehicle_model || 'SUV', category: 'SUV' })} alt="" /></div>
      <div className="booking-main"><div className="booking-topline"><div><h3>{booking.vehicle_make} {booking.vehicle_model}</h3><p>Booking {booking.id.slice(0, 8).toUpperCase()} · {booking.vehicle_color} · {booking.vehicle_license_plate}</p></div><span className={`status-pill ${overdue ? 'status-overdue' : `status-${booking.status}`}`}>{overdue ? 'return overdue' : booking.status.replaceAll('_', ' ')}</span></div>
        <div className="booking-window"><div><small>PICKUP</small><b>{dateTime(booking.pickup_at)}</b></div><ArrowRight size={16} /><div><small>RETURN</small><b>{dateTime(booking.return_at)}</b></div></div>
        <div className="booking-bottom"><span><Check size={14} /> {overdue ? 'Contact support to coordinate the return' : booking.status === 'confirmed' ? 'Paid in USD' : booking.status === 'pending' ? 'Payment pending' : booking.status}</span><strong>{money(booking.amount_minor)}</strong>
          {['pending', 'expired'].includes(booking.status) && <button className="text-link" disabled={checkingId === booking.id} onClick={() => void checkPayment(booking.id)}>{checkingId === booking.id ? 'Checking payment…' : 'Check payment status'}</button>}
          {['confirmed', 'active', 'awaiting_inspection', 'inspection_failed', 'completed'].includes(booking.status) && <button className="text-link" onClick={() => onReceipt(booking)}>View ticket <ArrowUpRight size={15} /></button>}
          {booking.status === 'active' && new Date(booking.return_at).getTime() <= Date.now() && <button className="btn btn-primary" onClick={() => void onReturn(booking)}>Report car returned <ArrowRight size={15} /></button>}
        </div>
      </div>
    </article>; })}</div> : <div className="empty-state booking-empty"><CalendarDays size={32} /><h3>No {tab.toLowerCase()} yet</h3><p>When you book a vehicle, it will show up here.</p><button className="btn btn-primary" onClick={() => { window.location.hash = ''; window.location.reload(); }}>Explore the fleet <ArrowRight size={15} /></button></div>}
  </section>;
}

function Account({ email, onLogout, onAdmin, onSupport, onPasswordChanged }: { email: string; onLogout: () => void; onAdmin: () => void; onSupport: () => void; onPasswordChanged: () => void }) {
  const isAdmin = localStorage.getItem('drivewell_role') === 'platform-admin';
  const [section, setSection] = useState<'personal' | 'verification' | 'security'>('personal');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [kyc, setKyc] = useState<KycStatus | null>(null);
  const [kycBusy, setKycBusy] = useState(false);
  useEffect(() => {
    if (!isAdmin && tokenStore.get()) api.kycStatus().then(setKyc).catch((e) => setError((e as Error).message));
  }, [isAdmin]);
  async function refreshKyc() {
    setKycBusy(true); setError('');
    try { setKyc(await api.kycStatus()); }
    catch (e) { setError((e as Error).message); }
    finally { setKycBusy(false); }
  }
  async function uploadKyc(type: 'driver_license' | 'identity_document', file?: File) {
    if (!file) return;
    setKycBusy(true); setError(''); setMessage('');
    try { await api.uploadKycDocument(type, file); setKyc(await api.kycStatus()); setMessage('Document securely submitted. An administrator will review it.'); }
    catch (e) { setError((e as Error).message); }
    finally { setKycBusy(false); }
  }
  async function changePassword(form: FormData) {
    setMessage(''); setError('');
    try {
      const result = await api.auth('/change-password', { current_password: String(form.get('current_password') || ''), new_password: String(form.get('new_password') || '') });
      setMessage(result.message || 'Password changed. Sign in again.'); tokenStore.clear(); tokenStore.clearRefresh(); localStorage.removeItem('drivewell_email'); localStorage.removeItem('drivewell_role'); onPasswordChanged();
    } catch (e) { setError((e as Error).message); }
  }
  const navItem = (key: 'personal' | 'verification' | 'security', label: string, icon: ReactNode) => <button className={`account-menu-item ${section === key ? 'active' : ''}`} aria-current={section === key ? 'page' : undefined} onClick={() => { setSection(key); setMessage(''); setError(''); }}>{icon}{label}<ArrowRight size={15} /></button>;
  const securityPanel = <form className="settings-panel auth-form" onSubmit={(e) => { e.preventDefault(); void changePassword(new FormData(e.currentTarget)); }}><p className="eyebrow">SECURITY</p><h2>Change password</h2><p className="muted">Update your sign-in password. You will need to sign in again after the change.</p><label>Current password<input name="current_password" type="password" required autoComplete="current-password" /></label><label>New password<input name="new_password" type="password" minLength={8} required autoComplete="new-password" /></label><button className="btn btn-primary">Update password <KeyRound size={15} /></button>{message && <p className="verified-text">{message}</p>}{error && <p className="inline-error">{error}</p>}</form>;
  return <section className={`wrap page-content account-page ${isAdmin ? 'admin-profile-page' : ''}`}>
    <div className="page-title-row"><div><p className="eyebrow">{isAdmin ? 'PLATFORM ADMINISTRATION' : 'YOUR PROFILE'}</p><h1>{isAdmin ? 'Administrator profile' : 'Your account'}</h1><p className="muted">{isAdmin ? 'Manage your administrator sign-in and platform access.' : 'Your details and sign-in preferences.'}</p></div></div>
    <div className="account-layout">
      <aside className="account-card"><div className="avatar large">{initials(email)}</div><h3>{email || 'Drivewell guest'}</h3><p>{isAdmin ? 'Platform administrator' : email ? 'Customer account' : 'Not signed in'}</p><div className={isAdmin ? 'verified-badge admin-role-badge' : 'verified-badge'}><BadgeCheck size={15} /> {isAdmin ? 'Administrator access' : 'Email verified'}</div>
        {isAdmin ? <>{navItem('personal', 'Admin profile', <LayoutDashboard size={17} />)}{navItem('security', 'Security', <KeyRound size={17} />)}<button className="account-menu-item" onClick={onAdmin}><LayoutDashboard size={17} /> Operations workspace <ArrowRight size={15} /></button></> : <>{navItem('personal', 'Personal details', <Users size={17} />)}{navItem('verification', 'Driver verification', <ShieldCheck size={17} />)}{navItem('security', 'Security', <KeyRound size={17} />)}</>}
        <button className="account-menu-item" onClick={onSupport}><CircleHelp size={17} /> Help & support <ArrowRight size={15} /></button>
      </aside>
      <div className="account-details">
        {isAdmin ? <>
          {section === 'personal' && <div className="settings-panel"><p className="eyebrow">ADMINISTRATOR PROFILE</p><h2>Platform account</h2><p className="muted">This account has privileged access to Drivewell operations. Use the operations workspace to manage the fleet, bookings, customer accounts, support, and KYC reviews.</p><div className="account-fields"><div><small>ADMIN EMAIL</small><strong>{email || 'Not signed in'}</strong></div><div><small>ACCESS ROLE</small><strong className="verified-text"><ShieldCheck size={15} /> Platform administrator</strong></div></div><div className="account-note"><LockKeyhole size={16} /><span>Administrator access is restricted to accounts assigned the platform-admin role.</span></div><div className="settings-actions"><button className="btn btn-primary" onClick={onAdmin}><LayoutDashboard size={16} /> Open operations workspace</button></div></div>}
          {section === 'security' && securityPanel}
        </> : <>
          {section === 'personal' && <div className="settings-panel"><p className="eyebrow">PERSONAL DETAILS</p><h2>Account identity</h2><p className="muted">Your verified identity and account details.</p><div className="account-fields"><div><small>EMAIL ADDRESS</small><strong>{email || 'Not signed in'}</strong></div><div><small>ACCOUNT STATUS</small><strong className="verified-text"><BadgeCheck size={15} /> {email ? 'Verified' : 'Guest'}</strong></div></div><div className="account-note"><LockKeyhole size={16} /><span>Email verification is handled through the configured SMTP server.</span></div></div>}
          {section === 'verification' && <div className="settings-panel"><p className="eyebrow">REQUIRED BEFORE RENTING</p><div className="inventory-head"><div><h2>Driver and identity verification</h2><p className="muted">Upload a current driver licence and one government identity document. Administrators review both before rentals are enabled.</p></div><button className="btn btn-outline" onClick={() => void refreshKyc()} disabled={kycBusy}>{kycBusy ? 'Refreshing…' : 'Refresh status'}</button></div><div className="kyc-overall"><span className={`status-pill status-${kyc?.status || 'pending'}`}>{kyc?.status?.replaceAll('_', ' ') || 'Loading status'}</span><span>{kyc?.status === 'verified' ? 'You can reserve a car.' : 'Both documents must be approved before you can reserve.'}</span></div><div className="kyc-upload-grid">{([['driver_license', 'Driver licence'], ['identity_document', 'Identity document']] as const).map(([type, title]) => <label className="kyc-upload-card" key={type}><span><b>{title}</b><small className={`kyc-doc-status ${kyc?.documents[type] || 'missing'}`}>{(kyc?.documents[type] || 'missing').replaceAll('_', ' ')}</small></span><small>PDF, JPEG or PNG · up to 5 MB</small><input type="file" accept="application/pdf,image/jpeg,image/png" disabled={kycBusy || !tokenStore.get()} onChange={(event) => { void uploadKyc(type, event.currentTarget.files?.[0]); event.currentTarget.value = ''; }} /></label>)}</div>{kycBusy && <p className="muted">Uploading encrypted document…</p>}{message && <p className="verified-text">{message}</p>}{error && <p className="inline-error">{error}</p>}<div className="account-note"><LockKeyhole size={16} /><span>Rental access is enabled after an administrator approves both documents.</span></div></div>}
          {section === 'security' && securityPanel}
        </>}
        <div className="settings-actions">{email && <button className="btn btn-danger-outline" onClick={onLogout}><LogOut size={16} /> Sign out</button>}</div>
      </div>
    </div>
  </section>;
}

function SupportCenter({ onError }: { onError: (message: string) => void }) {
  const [tickets, setTickets] = useState<import('./types').SupportTicket[]>([]);
  const [active, setActive] = useState<import('./types').SupportTicket | null>(null);
  const [replyTo, setReplyTo] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [isLive, setIsLive] = useState(true);
  const messagesEnd = useRef<HTMLDivElement | null>(null);
  async function refresh(reportError = true) {
    try {
      const items = await api.tickets();
      setTickets(items);
      setActive((current) => current ? items.find((item) => item.id === current.id) || current : null);
      setIsLive(true);
    } catch (e) {
      setIsLive(false);
      if (reportError) onError((e as Error).message);
    }
  }
  useEffect(() => {
    void refresh();
    let polling = false;
    const poll = window.setInterval(() => {
      if (document.visibilityState !== 'visible' || polling) return;
      polling = true;
      void refresh(false).finally(() => { polling = false; });
    }, 3000);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') void refresh(false);
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.clearInterval(poll);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);
  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [active?.id, active?.messages.length]);
  async function create(form: FormData): Promise<boolean> {
    setBusy(true);
    try { const ticket = await api.createTicket({ subject: String(form.get('subject') || ''), message: String(form.get('message') || '') }); setActive(ticket); setTickets((items) => [ticket, ...items]); return true; }
    catch (e) { onError((e as Error).message); return false; } finally { setBusy(false); }
  }
  async function reply(form: FormData): Promise<boolean> {
    if (!active) return false; setBusy(true);
    try {
      await api.replyTicket(active.id, String(form.get('reply') || ''), replyTo);
      await refresh();
      setReplyTo(undefined);
      return true;
    }
    catch (e) { onError((e as Error).message); return false; } finally { setBusy(false); }
  }
  return <section className="wrap page-content support-page">
    <div className="support-heading">
      <div><p className="eyebrow">DRIVEWELL CUSTOMER CARE</p><h1>Help & support</h1><p className="muted">Have a question? Start a conversation and our team will get back to you here.</p></div>
      <div className={`support-live ${isLive ? 'connected' : 'disconnected'}`} aria-live="polite">{isLive ? <Wifi size={15} /> : <WifiOff size={15} />}{isLive ? 'Live updates on' : 'Reconnecting…'}</div>
    </div>
    <div className="support-workspace">
      <aside className="support-ticket-list">
        <div className="support-list-heading"><div><p className="eyebrow">YOUR INBOX</p><h2>Conversations <span>{tickets.length}</span></h2></div><button className="icon-button" onClick={() => void refresh()} aria-label="Refresh conversations" title="Refresh"><ArrowRight size={16} /></button></div>
        <div className="support-ticket-items">
          {tickets.map((ticket) => {
            const latest = ticket.messages[ticket.messages.length - 1];
            return <button className={`support-ticket-item ${active?.id === ticket.id ? 'active' : ''}`} key={ticket.id} onClick={() => setActive(ticket)}>
              <span className="support-ticket-icon"><MessageCircle size={17} /></span>
              <span className="support-ticket-copy"><strong>{ticket.subject}</strong><small>{latest?.body || 'No messages yet'}</small><span><i className={`support-status-dot ${ticket.status}`} />{ticket.status.replaceAll('_', ' ')}<time>{dateTime(ticket.updated_at, { month: 'short', day: 'numeric' })}</time></span></span>
            </button>;
          })}
          {!tickets.length && <div className="support-list-empty"><MessageCircle size={24} /><strong>No conversations yet</strong><span>Start a new ticket and we’ll be happy to help.</span></div>}
        </div>
        <button className="btn btn-primary support-new-ticket" onClick={() => { setActive(null); setReplyTo(undefined); }}><Plus size={16} /> New conversation</button>
      </aside>
      <div className="support-chat-card">
        {active ? <>
          <header className="support-chat-header"><div className="support-chat-avatar"><MessageCircle size={18} /></div><div><p className="eyebrow">TICKET {active.id.slice(0, 8).toUpperCase()}</p><h2>{active.subject}</h2></div><span className={`support-ticket-status ${active.status}`}>{active.status.replaceAll('_', ' ')}</span></header>
          <div className="support-chat-subheader"><span><i className={`support-status-dot ${active.status}`} />{active.status === 'resolved' || active.status === 'closed' ? 'This conversation is closed' : 'Our support team will reply here'}</span><span>Priority: {active.priority}</span></div>
          <div className="support-chat-messages" aria-live="polite" aria-label="Ticket conversation">
            {!active.messages.length && <p className="support-chat-empty">Send a message to start this conversation.</p>}
            <SupportConversationMessages messages={active.messages} viewerRole="customer" onReply={(id) => setReplyTo(id)} />
            <div ref={messagesEnd} />
          </div>
          {replyTo && <div className="support-reply-context"><span>Replying in thread</span><button type="button" onClick={() => setReplyTo(undefined)}>Cancel</button></div>}
          <form className="support-composer" onSubmit={(e) => { e.preventDefault(); const form = e.currentTarget; void reply(new FormData(form)).then((sent) => { if (sent) form.reset(); }); }}>
            <textarea name="reply" required rows={2} disabled={busy || ['resolved', 'closed'].includes(active.status)} placeholder={replyTo ? 'Write a threaded reply…' : 'Write your message…'} aria-label="Write your message" />
            <div><span>Replies update automatically while this page is open.</span><button className="btn btn-primary" disabled={busy || ['resolved', 'closed'].includes(active.status)}>{busy ? 'Sending…' : 'Send message'} <Send size={15} /></button></div>
          </form>
        </> : <>
          <div className="support-new-conversation"><div className="support-new-icon"><MessageCircle size={25} /></div><p className="eyebrow">WE’RE HERE TO HELP</p><h2>What can we help you with?</h2><p>Tell us a little about your question or issue. Your conversation will stay in your inbox so you can return to it any time.</p>
            <form className="support-new-form" onSubmit={(e) => { e.preventDefault(); const form = e.currentTarget; void create(new FormData(form)).then((created) => { if (created) form.reset(); }); }}>
              <label>Subject<input name="subject" required minLength={4} maxLength={160} placeholder="For example, a question about my booking" /></label>
              <label>How can we help?<textarea name="message" required rows={5} placeholder="Share the details that will help our team understand your question…" /></label>
              <button className="btn btn-primary" disabled={busy}>{busy ? 'Opening ticket…' : 'Start conversation'} <ArrowRight size={16} /></button>
            </form>
          </div>
        </>}
      </div>
    </div>
  </section>;
}

function SupportConversationMessages({ messages, viewerRole, onReply }: { messages: import('./types').SupportMessage[]; viewerRole: 'customer' | 'platform-admin'; onReply?: (id: string) => void }) {
  return <>{messages.map((message) => {
    const parent = message.parent_id ? messages.find((item) => item.id === message.parent_id) : undefined;
    const isOwn = message.author_role === viewerRole;
    return <article key={message.id} className={`support-chat-row ${isOwn ? 'own' : 'theirs'}`}>
      <div className={`support-chat-bubble ${isOwn ? 'own' : 'theirs'}`}>
        <div className="support-bubble-meta"><strong>{message.author_name}</strong><time>{dateTime(message.created_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</time></div>
        {parent && <div className="support-quoted-message">Replying to {parent.author_name}: “{parent.body.slice(0, 100)}{parent.body.length > 100 ? '…' : ''}”</div>}
        <p>{message.body}</p>
        {onReply && <button type="button" className="support-reply-link" aria-label="Reply to this message" onClick={() => onReply(message.id)}>Reply</button>}
      </div>
    </article>;
  })}</>;
}

function ReceiptDialog({ receipt, onClose }: { receipt: Receipt; onClose: () => void }) {
  function download() { window.print(); }
  return <div className="modal-backdrop" onClick={onClose}><div className="ticket-modal" onClick={(e) => e.stopPropagation()}><button className="modal-close" onClick={onClose}><X size={19} /></button><div className="ticket-success"><span><Check size={22} /></span><div><strong>Your booking is confirmed</strong><small>Payment verified. Your rental ticket is ready.</small></div></div><div className="ticket-paper"><div className="ticket-head"><div className="brand"><span className="brand-mark"><Compass size={19} /></span> DRIVEWELL</div><span className="status-pill status-confirmed">CONFIRMED</span></div><p className="eyebrow">RENTAL TICKET</p><h2>{receipt.receipt_number}</h2><div className="ticket-car"><img src={imageFor({ make: receipt.vehicle_make, model: receipt.vehicle_model, category: 'Sedan' })} alt="" /><div><h3>{receipt.vehicle_make} {receipt.vehicle_model}</h3><p>{receipt.vehicle_color} · Rental vehicle</p></div></div><small className="ticket-label">LICENSE PLATE</small><strong>{receipt.vehicle_license_plate}</strong><div className="ticket-dates"><div><small>PICKUP</small><b>{dateTime(receipt.rental_start)}</b></div><div><small>RETURN</small><b>{dateTime(receipt.rental_end)}</b></div></div><div className="ticket-paid"><span>Paid</span><strong>{money(receipt.amount_minor)} USD</strong></div><p className="ticket-number">Issued {dateTime(receipt.created_at)}</p></div><div className="ticket-actions"><button className="btn btn-outline" onClick={download}><Download size={16} /> Download ticket</button><button className="btn btn-primary" onClick={onClose}>Done</button></div><p className="ticket-disclaimer">Keep this ticket for your rental. Vehicle availability after return depends on inspection.</p></div></div>;
}

function AuthDialog({ mode, email, onClose, onSwitch, onSubmit }: { mode: 'login' | 'register' | 'confirm' | 'resend' | 'forgot' | 'reset'; email: string; onClose: () => void; onSwitch: (v: 'login' | 'register' | 'confirm' | 'resend' | 'forgot' | 'reset' | null) => void; onSubmit: (data: FormData) => void }) {
  const [error, setError] = useState('');
  const submit = async (e: React.FormEvent<HTMLFormElement>) => { e.preventDefault(); const form = new FormData(e.currentTarget); try { await onSubmit(form); } catch (err) { setError((err as Error).message); } };
  const authTitle = mode === 'login' ? 'Good to have you back.' : mode === 'register' ? 'Your next journey starts here.' : mode === 'confirm' || mode === 'reset' ? 'Check your inbox.' : mode === 'resend' ? 'Verify your email.' : 'Reset your password.';
  const needsPassword = mode === 'login' || mode === 'register' || mode === 'reset';
  return <div className="modal-backdrop" onClick={onClose}><div className="auth-modal" onClick={(e) => e.stopPropagation()}><button className="modal-close" onClick={onClose}><X size={19} /></button><span className="auth-icon"><Compass size={24} /></span><p className="eyebrow">WELCOME TO DRIVEWELL</p><h2>{authTitle}</h2><p className="muted">{mode === 'confirm' ? `Enter the verification code sent to ${email}.` : mode === 'resend' ? 'Enter your account email and we will send a new verification code if verification is still needed.' : mode === 'reset' ? `Enter the reset code sent to ${email} and choose a new password.` : mode === 'forgot' ? 'We will email a reset code if this account exists.' : 'Sign in securely to save your plans and manage your bookings.'}</p><form onSubmit={(e) => void submit(e)} className="auth-form">{mode === 'register' && <label>Your name<input name="name" required autoComplete="name" placeholder="Your full name" /></label>}{mode !== 'confirm' && <label>Email address<input name="email" type="email" required defaultValue={email} autoComplete="email" placeholder="you@example.com" /></label>}{needsPassword && <label>{mode === 'reset' ? 'New password' : 'Password'}<input name="password" type="password" required minLength={8} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder="At least 8 characters" /></label>}{(mode === 'confirm' || mode === 'reset') && <><input type="hidden" name="email" value={email} /><label>{mode === 'confirm' ? 'Verification code' : 'Password reset code'}<input name="code" required autoComplete="one-time-code" placeholder="Enter your code" /></label></>}{error && <p className="inline-error">{error}</p>}<button className="btn btn-primary full">{mode === 'login' ? 'Sign in' : mode === 'register' ? 'Create account' : mode === 'confirm' ? 'Verify email' : mode === 'resend' ? 'Resend verification code' : mode === 'forgot' ? 'Send reset code' : 'Reset password'} <ArrowRight size={16} /></button></form><p className="auth-switch">{mode === 'login' ? <>New to Drivewell? <button onClick={() => onSwitch('register')}>Create an account</button> · <button onClick={() => onSwitch('forgot')}>Forgot password?</button><br /><button onClick={() => onSwitch('resend')}>Resend verification code</button></> : mode === 'register' ? <>Already have an account? <button onClick={() => onSwitch('login')}>Sign in</button></> : mode === 'confirm' ? <>Didn’t receive a code? <button onClick={() => onSwitch('resend')}>Resend verification code</button> · <button onClick={() => onSwitch('login')}>Sign in</button></> : <>Return to <button onClick={() => onSwitch('login')}>sign in</button></>}</p><div className="auth-security"><LockKeyhole size={13} /> Secure sign-in with your Drivewell account</div></div></div>;
}

function AdminShell({ vehicles, onVehicle, onExit, onHowItWorks, setError }: { vehicles: Vehicle[]; onVehicle: (v: Vehicle[]) => void; onExit: () => void; onHowItWorks: () => void; setError: (v: string) => void }) {
  const [section, setSection] = useState<AdminSection>(() => adminSectionForPath(window.location.pathname));
  const [adminAccess, setAdminAccess] = useState<boolean | null>(null);
  const [opsBookings, setOpsBookings] = useState<Booking[]>([]);
  const [bookingFilter, setBookingFilter] = useState('All bookings');
  const [showCreate, setShowCreate] = useState(false); const [editing, setEditing] = useState<Vehicle | null>(null); const [search, setSearch] = useState(''); const [busy, setBusy] = useState(false);
  const [supportTickets, setSupportTickets] = useState<import('./types').SupportTicket[]>([]);
  const [activeTicket, setActiveTicket] = useState<import('./types').SupportTicket | null>(null);
  const [supportLive, setSupportLive] = useState(true);
  const adminMessagesEnd = useRef<HTMLDivElement | null>(null);
  const [customers, setCustomers] = useState<Array<{ id: string; email: string; name: string; role: string; is_active: boolean; is_email_verified: boolean; created_at: string }>>([]);
  const [kycReviews, setKycReviews] = useState<KycReview[]>([]);
  const [reviewNote, setReviewNote] = useState('');
  const [kycPreview, setKycPreview] = useState<{ url: string; name: string } | null>(null);
  const { ask, element: confirmElement } = useConfirmation();
  const filtered = vehicles.filter((v) => `${v.make} ${v.model} ${v.registration_number}`.toLowerCase().includes(search.toLowerCase()));
  useEffect(() => {
    const onPopState = () => setSection(adminSectionForPath(window.location.pathname));
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);
  useEffect(() => {
    const target = section === 'overview' ? '/admin' : `/admin/${section}`;
    if (window.location.pathname !== target) window.history.pushState({}, '', target);
  }, [section]);
  useEffect(() => {
    if (!tokenStore.get()) { setAdminAccess(false); return; }
    api.operationsBookings().then((items) => { setOpsBookings(items); setAdminAccess(true); }).catch(() => setAdminAccess(false));
  }, []);

  async function refreshOperations() {
    try { setOpsBookings(await api.operationsBookings()); setAdminAccess(true); }
    catch (e) { setError((e as Error).message); }
  }
  async function refreshSupport(reportError = true) {
    try {
      const items = await api.tickets(true);
      setSupportTickets(items);
      setActiveTicket((current) => current ? items.find((item) => item.id === current.id) || null : null);
      setSupportLive(true);
    } catch (e) {
      setSupportLive(false);
      if (reportError) setError((e as Error).message);
    }
  }
  useEffect(() => {
    if (section !== 'support') return;
    void refreshSupport(false);
    let polling = false;
    const poll = window.setInterval(() => {
      if (document.visibilityState !== 'visible' || polling) return;
      polling = true;
      void refreshSupport(false).finally(() => { polling = false; });
    }, 3000);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') void refreshSupport(false);
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.clearInterval(poll);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [section]);
  useEffect(() => {
    if (section === 'support') adminMessagesEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [section, activeTicket?.id, activeTicket?.messages.length]);
  async function refreshCustomers() {
    try { setCustomers(await api.users()); } catch (e) { setError((e as Error).message); }
  }
  async function refreshKyc() {
    try { setKycReviews(await api.kycReviews()); }
    catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { if (section === 'inspections' || section === 'customers') void refreshKyc(); }, [section]);
  async function reviewDocument(id: string, decision: 'approved' | 'rejected') {
    const label = decision === 'approved' ? 'Approve this document?' : 'Reject this document?';
    if (!await ask(label, decision === 'approved' ? 'The renter can book only after both required documents are approved.' : 'The renter will need to upload a replacement document.', decision === 'approved' ? 'Approve' : 'Reject')) return;
    try { await api.reviewKycDocument(id, decision, reviewNote); setReviewNote(''); await refreshKyc(); }
    catch (e) { setError((e as Error).message); }
  }
  async function openKycDocument(id: string, name: string) {
    try { const url = await api.kycDocument(id); setKycPreview({ url, name }); }
    catch (e) { setError((e as Error).message); }
  }

  async function updateBooking(booking: Booking, action: 'cancel' | 'start' | 'return' | 'inspection') {
    const actionText = action === 'inspection' ? 'Approve return inspection?' : action === 'cancel' ? 'Cancel this unpaid booking hold?' : action === 'return' ? 'Record that this vehicle was returned?' : 'Start this rental?';
    if (!await ask(actionText, action === 'inspection' ? 'Approving the inspection makes the vehicle available in the listing again.' : action === 'cancel' ? 'This releases the temporary vehicle hold.' : 'This updates the booking and vehicle workflow.', action === 'inspection' ? 'Approve & relist' : 'Continue')) return;
    try {
      const result = await api.bookingAction(booking.id, action, action === 'inspection' ? { approved: true, note: 'Approved in operations workspace.' } : undefined);
      setOpsBookings((items) => items.map((item) => item.id === result.id ? result : item));
    } catch (e) { setError((e as Error).message); }
  }

  const bookingRows = opsBookings.filter((booking) => {
    if (bookingFilter === 'All bookings') return true;
    if (bookingFilter === 'Return review') return ['awaiting_inspection', 'inspection_failed'].includes(booking.status);
    const expected: Record<string, string> = { 'Pending payment': 'pending', Confirmed: 'confirmed', 'Active rentals': 'active' };
    return booking.status === expected[bookingFilter];
  });
  async function create(form: FormData) {
    setBusy(true); setError('');
    const value = Object.fromEntries(form.entries());
    const payload = { ...value, year: Number(value.year), seats: Number(value.seats), hourly_rate: Number(value.hourly_rate), currency: 'USD' };
    try {
      if (editing) {
        const vehicle = await api.updateVehicle(editing.id, payload);
        onVehicle(vehicles.map((current) => current.id === vehicle.id ? vehicle : current));
      } else {
        const vehicle = await api.createVehicle(payload);
        onVehicle([vehicle, ...vehicles]);
      }
      setShowCreate(false); setEditing(null);
    }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  const title = section === 'overview' ? 'Operations overview' : section === 'vehicles' ? 'Vehicle inventory' : section === 'support' ? 'Support inbox' : section === 'customers' ? 'Customer accounts' : section === 'inspections' ? 'Vehicle return inspections' : section === 'settings' ? 'Platform settings' : 'Booking management';
  const subtitle = section === 'overview' ? 'A clear view of your fleet and upcoming rental activity.' : section === 'vehicles' ? 'Manage the vehicles customers can browse and book.' : section === 'support' ? 'Manage tickets, threaded replies, priority, and status.' : section === 'customers' ? 'Manage customer accounts and review submitted identity documents.' : section === 'inspections' ? 'Review returned vehicles before making them available again.' : section === 'settings' ? 'Review agreement and verification settings for this deployment.' : 'Monitor payment holds, confirmed rentals, and vehicle returns.';
  if (adminAccess === null) return <div className="admin-denied" role="status"><span className="auth-icon"><LockKeyhole size={23} /></span><p className="eyebrow">OPERATIONS WORKSPACE</p><h1>Checking administrator access</h1><p>Verifying your account permissions…</p></div>;
  if (adminAccess === false) return <div className="admin-denied"><span className="auth-icon"><LockKeyhole size={23} /></span><p className="eyebrow">OPERATIONS WORKSPACE</p><h1>Administrator access required</h1><p>Sign in with an account assigned the <b>platform-admin</b> role to manage vehicles, bookings, and inspections.</p><button className="btn btn-outline" onClick={onExit}>Return to Drivewell</button></div>;

  return <div className="admin-app"><aside className="admin-sidebar"><button className="brand admin-brand" onClick={onExit}><img className="brand-logo" src="/logo.png" alt="Driveflow Car Rental Platform" /></button><span className="sidebar-label">WORKSPACE</span><p className="sidebar-section">ADMINISTRATION</p><button className={`admin-nav ${section === 'overview' ? 'active' : ''}`} onClick={() => setSection('overview')}><LayoutDashboard size={17} /> Overview</button><button className={`admin-nav ${section === 'vehicles' ? 'active' : ''}`} onClick={() => setSection('vehicles')}><CarFront size={17} /> Vehicles <span>{vehicles.length}</span></button><button className={`admin-nav ${section === 'bookings' ? 'active' : ''}`} onClick={() => setSection('bookings')}><CalendarDays size={17} /> Bookings</button><button className={`admin-nav ${section === 'inspections' ? 'active' : ''}`} onClick={() => setSection('inspections')}><BadgeCheck size={17} /> Inspections <span>{opsBookings.filter((b) => ['awaiting_inspection', 'inspection_failed'].includes(b.status)).length}</span></button><button className={`admin-nav ${section === 'support' ? 'active' : ''}`} onClick={() => { setSection('support'); void refreshSupport(); }}><CircleHelp size={17} /> Support</button><button className={`admin-nav ${section === 'customers' ? 'active' : ''}`} onClick={() => { setSection('customers'); void refreshCustomers(); }}><Users size={17} /> Customers {kycReviews.some((review) => review.status !== 'verified') && <span>{kycReviews.filter((review) => review.status !== 'verified').length}</span>}</button><button className={`admin-nav ${section === 'settings' ? 'active' : ''}`} onClick={() => setSection('settings')}><Settings size={17} /> Settings</button><div className="admin-user"><span className="avatar">AD</span><div><b>Administrator</b><small>Operations</small></div><button onClick={onExit} title="Exit operations"><LogOut size={16} /></button></div></aside><main className="admin-main"><header className="admin-topbar"><span>Operations <span>/</span> {title}</span><div><button className="admin-how-link" onClick={onHowItWorks}>How it works</button><button className="icon-button" onClick={() => { if (section === 'support') void refreshSupport(); else if (section === 'customers') { void refreshCustomers(); void refreshKyc(); } else if (section === 'inspections') void refreshOperations(); else void refreshOperations(); }} title="Refresh operations"><CircleHelp size={18} /></button><span className="avatar">AD</span><span>Admin</span></div></header><section className="admin-content"><div className="admin-heading"><div><p className="eyebrow">{section === 'overview' ? 'OPERATIONS' : section === 'vehicles' ? 'FLEET MANAGEMENT' : section === 'support' ? 'CUSTOMER CARE' : section === 'customers' ? 'ACCOUNT MANAGEMENT' : section === 'inspections' ? 'RENTAL SAFETY' : section === 'settings' ? 'CONFIGURATION' : 'BOOKING OPERATIONS'}</p><h1>{title}</h1><p>{subtitle}</p></div>{section === 'vehicles' && <button className="btn btn-primary" onClick={() => setShowCreate(true)}><Plus size={17} /> Add vehicle</button>}</div>
    {section === 'overview' && <><div className="admin-stats"><div><span>ACTIVE VEHICLES</span><b>{vehicles.filter((v) => v.status === 'active').length}</b><small>Available fleet inventory</small></div><div><span>UPCOMING BOOKINGS</span><b>{opsBookings.filter((b) => ['pending', 'confirmed'].includes(b.status)).length}</b><small>{opsBookings.filter((b) => b.status === 'pending').length} awaiting payment</small></div><div><span>INSPECTIONS DUE</span><b>{opsBookings.filter((b) => ['awaiting_inspection', 'inspection_failed'].includes(b.status)).length}</b><small>Review before releasing vehicles</small></div></div><div className="inventory-card overview-bookings"><div className="inventory-head"><div><h2>Recent bookings</h2><p>Latest customer rental activity.</p></div><button className="text-link" onClick={() => setSection('bookings')}>View all <ArrowRight size={14} /></button></div><OperationsTable bookings={opsBookings.slice(0, 5)} onAction={updateBooking} compact /></div></>}
    {section === 'vehicles' && <><div className="admin-stats"><div><span>ACTIVE VEHICLES</span><b>{vehicles.filter((v) => v.status === 'active').length}</b><small>Available to customers</small></div><div><span>VEHICLE CATEGORIES</span><b>{new Set(vehicles.map((v) => v.category)).size}</b><small>Across your fleet</small></div><div><span>FLEET HOURLY RATES</span><b>{vehicles.length ? `${money(Math.round(Math.min(...vehicles.map((v) => Number(v.hourly_rate))) * 100))}–${money(Math.round(Math.max(...vehicles.map((v) => Number(v.hourly_rate))) * 100))}` : '—'}</b><small>USD · vehicle specific</small></div></div><div className="inventory-card"><div className="inventory-head"><div><h2>All vehicles <span>{vehicles.length}</span></h2><p>Keep inventory details current and accurate.</p></div><div className="inventory-search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search make, model or plate…" /></div></div><div className="inventory-table-wrap"><table><thead><tr><th>VEHICLE</th><th>PLATE</th><th>RATE</th><th>STATUS</th><th>ACTIONS</th></tr></thead><tbody>{filtered.map((v) => <tr key={v.id}><td><div className="table-vehicle"><img src={imageFor(v)} alt="" /><div><b>{v.make} {v.model}</b><small>{v.color} · {v.year} · {v.category}</small></div></div></td><td>{v.registration_number}</td><td>{money(Math.round(Number(v.hourly_rate) * 100))}/hour</td><td><span className="status-pill status-confirmed"><span className="live-dot" /> {v.status}</span></td><td><button className="table-action" onClick={() => setEditing(v)}>Edit</button>{v.status !== 'retired' && <button className="table-action archive" onClick={async () => { if (!await ask('Retire this vehicle?', 'It will no longer appear as available to customers. Existing rental records are preserved.', 'Retire vehicle')) return; try { const updated = await api.deleteVehicle(v.id); onVehicle(vehicles.map((current) => current.id === updated.id ? updated : current)); } catch (e) { setError((e as Error).message); } }}>Delete</button>}</td></tr>)}</tbody></table>{!filtered.length && <div className="empty-state table-empty"><CarFront size={30} /><h3>Your fleet starts here</h3><p>Add a vehicle to make it available to customers.</p><button className="btn btn-primary" onClick={() => setShowCreate(true)}><Plus size={15} /> Add your first vehicle</button></div>}</div><div className="inventory-foot"><ShieldCheck size={15} /> Delete retires a vehicle so existing rental history remains intact.</div></div></>}
    {section === 'support' && <div className="admin-support-layout">
      <aside className="inventory-card support-list">
        <div className="support-list-heading"><div><p className="eyebrow">CUSTOMER CARE</p><h2>All tickets <span>{supportTickets.length}</span></h2></div><button className="icon-button" onClick={() => void refreshSupport()} aria-label="Refresh tickets"><ArrowRight size={16} /></button></div>
        <div className="support-ticket-items">{supportTickets.map((ticket) => {
          const latest = ticket.messages[ticket.messages.length - 1];
          return <button className={`support-ticket-item ${activeTicket?.id === ticket.id ? 'active' : ''}`} key={ticket.id} onClick={() => setActiveTicket(ticket)}>
            <span className="support-ticket-icon"><MessageCircle size={17} /></span>
            <span className="support-ticket-copy"><strong>{ticket.subject}</strong><small>{latest?.body || 'No messages yet'}</small><span><i className={`support-status-dot ${ticket.status}`} />{ticket.status.replaceAll('_', ' ')}<time>{dateTime(ticket.updated_at, { month: 'short', day: 'numeric' })}</time></span></span>
          </button>;
        })}{!supportTickets.length && <div className="support-list-empty"><MessageCircle size={24} /><strong>No open conversations</strong><span>New customer tickets will appear here.</span></div>}</div>
        <div className={`support-live support-admin-live ${supportLive ? 'connected' : 'disconnected'}`}>{supportLive ? <Wifi size={14} /> : <WifiOff size={14} />}{supportLive ? 'Live updates on' : 'Reconnecting…'}</div>
      </aside>
      <div className="support-admin-chat inventory-card">
        {activeTicket ? <>
          <header className="support-chat-header"><div className="support-chat-avatar"><MessageCircle size={18} /></div><div><p className="eyebrow">TICKET {activeTicket.id.slice(0, 8).toUpperCase()} · CUSTOMER {activeTicket.customer_id.slice(0, 8)}</p><h2>{activeTicket.subject}</h2></div><span className={`support-ticket-status ${activeTicket.status}`}>{activeTicket.status.replaceAll('_', ' ')}</span></header>
          <div className="support-admin-controls">
            <label>Status<select value={activeTicket.status} onChange={async (e) => { try { const updated = await api.updateTicket(activeTicket.id, { status: e.target.value }); setActiveTicket(updated); await refreshSupport(); } catch (error) { setError((error as Error).message); } }}><option value="open">Open</option><option value="in_progress">In progress</option><option value="waiting_customer">Waiting for customer</option><option value="resolved">Resolved</option><option value="closed">Closed</option></select></label>
            <label>Priority<select value={activeTicket.priority} onChange={async (e) => { try { const updated = await api.updateTicket(activeTicket.id, { priority: e.target.value }); setActiveTicket(updated); await refreshSupport(); } catch (error) { setError((error as Error).message); } }}><option>low</option><option>normal</option><option>high</option><option>urgent</option></select></label>
            <label>Assigned to<input key={`${activeTicket.id}-${activeTicket.assigned_to || ''}`} defaultValue={activeTicket.assigned_to || ''} placeholder="Agent email" onBlur={async (e) => { try { const updated = await api.updateTicket(activeTicket.id, { assigned_to: e.target.value || null }); setActiveTicket(updated); } catch (error) { setError((error as Error).message); } }} /></label>
          </div>
          <div className="support-chat-messages" aria-live="polite" aria-label="Ticket conversation"><SupportConversationMessages messages={activeTicket.messages} viewerRole="platform-admin" /><div ref={adminMessagesEnd} /></div>
          <form className="support-composer support-admin-composer" onSubmit={async (e) => { e.preventDefault(); const formElement = e.currentTarget; const form = new FormData(formElement); try { await api.replyTicket(activeTicket.id, String(form.get('reply') || '')); formElement.reset(); await refreshSupport(); } catch (error) { setError((error as Error).message); } }}>
            <textarea name="reply" required rows={2} placeholder="Write a thoughtful reply to the customer…" aria-label="Reply to customer" />
            <div><span>Your reply will appear in the customer’s support inbox.</span><div><button type="button" className="btn btn-danger-outline" onClick={async () => { if (!await ask('Delete this support ticket?', 'The ticket and its message history will be permanently removed.', 'Delete ticket')) return; try { await api.deleteTicket(activeTicket.id); setActiveTicket(null); await refreshSupport(); } catch (error) { setError((error as Error).message); } }}>Delete ticket</button><button className="btn btn-primary">Send reply <Send size={15} /></button></div></div>
          </form>
        </> : <div className="support-admin-empty"><MessageCircle size={34} /><h2>Select a conversation</h2><p>Choose a customer ticket to read the conversation and send a reply.</p></div>}
      </div>
    </div>}
    {section === 'customers' && <><div className="inventory-card"><div className="inventory-head"><div><h2>Customer accounts <span>{customers.length}</span></h2><p>Deleting an account disables sign-in and preserves booking records.</p></div><button className="btn btn-outline" onClick={() => { void refreshCustomers(); void refreshKyc(); }}>Refresh</button></div><div className="inventory-table-wrap"><table><thead><tr><th>ACCOUNT</th><th>ROLE</th><th>EMAIL STATUS</th><th>ACCESS</th><th>ACTIONS</th></tr></thead><tbody>{customers.map((customer) => <tr key={customer.id}><td><b>{customer.name}</b><small className="table-sub">{customer.email}</small></td><td><select aria-label={`Role for ${customer.email}`} value={customer.role} onChange={async (e) => { try { const updated = await api.updateUser(customer.id, { role: e.target.value }); setCustomers((items) => items.map((item) => item.id === customer.id ? { ...item, ...updated } : item)); } catch (error) { setError((error as Error).message); } }}><option value="customer">Customer</option><option value="platform-admin">Administrator</option></select></td><td>{customer.is_email_verified ? 'Verified' : 'Unverified'}</td><td><span className={`status-pill ${customer.is_active ? 'status-confirmed' : 'status-cancelled'}`}>{customer.is_active ? 'Active' : 'Disabled'}</span></td><td><button className="table-action" onClick={async () => { if (customer.is_active && !await ask('Disable this account?', `${customer.email} will no longer be able to sign in.`, 'Disable account')) return; try { const updated = await api.updateUser(customer.id, { is_active: !customer.is_active }); setCustomers((items) => items.map((item) => item.id === customer.id ? { ...item, ...updated } : item)); } catch (error) { setError((error as Error).message); } }}>{customer.is_active ? 'Disable' : 'Enable'}</button>{customer.is_active && <button className="table-action archive" onClick={async () => { if (!await ask('Disable this customer account?', `${customer.email} will lose sign-in access. Booking records will remain.`, 'Disable account')) return; try { await api.deleteUser(customer.id); setCustomers((items) => items.map((item) => item.id === customer.id ? { ...item, is_active: false } : item)); } catch (error) { setError((error as Error).message); } }}>Delete</button>}</td></tr>)}</tbody></table>{!customers.length && <div className="empty-state table-empty"><Users size={28} /><h3>No customer accounts</h3><p>Registered users will appear here.</p></div>}</div></div><div className="inventory-card kyc-review-card"><div className="inventory-head"><div><h2>Driver and identity verification <span>{kycReviews.filter((r) => r.status !== 'verified').length}</span></h2><p>Approve both the driver licence and identity document to unlock rentals. Each decision is recorded against the submitted document.</p></div></div>{kycReviews.map((review) => <div className="kyc-review-user" key={review.user.id}><div className="kyc-review-heading"><div><b>{review.user.name}</b><small>{review.user.email}</small></div><span className={`status-pill status-${review.status}`}>{review.status.replaceAll('_', ' ')}</span></div><div className="kyc-admin-docs">{review.items.map((doc) => <article className="kyc-admin-doc" key={doc.id}><div><b>{doc.type === 'driver_license' ? 'Driver licence' : 'Identity document'}</b><small>{doc.filename} · {dateTime(doc.submitted_at, { month: 'short', day: 'numeric', year: 'numeric' })}</small><span className={`kyc-doc-status ${doc.status}`}>{doc.status}</span>{doc.review_note && <small>Review note: {doc.review_note}</small>}</div><div className="kyc-admin-actions"><button className="btn btn-outline" onClick={() => void openKycDocument(doc.id, doc.filename)}>View private file</button>{doc.status === 'pending' && <><button className="btn btn-primary" onClick={() => void reviewDocument(doc.id, 'approved')}>Approve</button><button className="btn btn-danger-outline" onClick={() => void reviewDocument(doc.id, 'rejected')}>Reject</button></>}</div></article>)}</div></div>)}{!kycReviews.length && <div className="empty-state table-empty"><ShieldCheck size={28} /><h3>No documents awaiting review</h3><p>Customer submissions will appear here.</p></div>}<label className="kyc-review-note">Review note for the next decision<input value={reviewNote} maxLength={500} onChange={(event) => setReviewNote(event.target.value)} placeholder="Optional reason or next steps for the customer" /></label></div><div className="inventory-foot ops-notice"><LockKeyhole size={15} /> Identity files contain sensitive personal information. Review only when needed and do not download or share them outside the authorized process.</div></>}
    {section === 'inspections' && <><div className="inventory-card"><div className="inventory-head"><div><h2>Vehicle return inspections <span>{opsBookings.filter((b) => ['awaiting_inspection', 'inspection_failed'].includes(b.status)).length}</span></h2><p>Approve only after the returned vehicle has been checked and cleared for the next rental.</p></div><button className="btn btn-outline" onClick={() => void refreshOperations()}>Refresh</button></div><OperationsTable bookings={opsBookings.filter((b) => ['awaiting_inspection', 'inspection_failed'].includes(b.status))} onAction={updateBooking} /></div></>}    {section === 'settings' && <div className="settings-panel admin-settings-panel"><p className="eyebrow">RENTAL REQUIREMENTS</p><h2>Agreement and identity checks</h2><p className="muted">These settings describe the active workflow. Agreement text and service secrets are changed through a reviewed deployment so administrators do not accidentally alter terms or expose credentials.</p><div className="admin-setting-row"><div><b>Rental agreement</b><small>Version draft-1 · mandatory at checkout · acceptance timestamp stored with each booking.</small></div><span className="status-pill status-pending">Draft · legal review required</span></div><div className="admin-setting-row"><div><b>Company and governing-law fields</b><small>Placeholders remain in the supplied agreement and must be completed before using it as a finalized contract.</small></div><span className="status-pill status-pending">Incomplete</span></div><div className="admin-setting-row"><div><b>Driver eligibility</b><small>Email verification plus administrator approval of both a driver licence and identity document.</small></div><span className="status-pill status-confirmed">Enforced</span></div><div className="admin-setting-row"><div><b>Document storage</b><small>Encrypted in the auth database. Viewing requires an administrator token and responses are marked private/no-store.</small></div><span className="status-pill status-confirmed">Private</span></div><div className="account-note"><ShieldCheck size={16} /><span>Identity checks are manual in this setup. There is no automated document authenticity or biometric service connected.</span></div></div>}
    {section === 'bookings' && <><div className="ops-tabs">{['All bookings', 'Pending payment', 'Confirmed', 'Active rentals', 'Return review'].map((tab) => <button className={bookingFilter === tab ? 'ops-tab active' : 'ops-tab'} key={tab} onClick={() => setBookingFilter(tab)}>{tab}</button>)}</div><div className="inventory-card"><div className="inventory-head"><div><h2>{bookingFilter} <span>{bookingRows.length}</span></h2><p>Rental state changes are recorded by booking-service.</p></div><button className="btn btn-outline" onClick={refreshOperations}>Refresh <ArrowRight size={14} /></button></div><OperationsTable bookings={bookingRows} onAction={updateBooking} /></div><div className="inventory-foot ops-notice"><ShieldCheck size={15} /> Vehicles remain unavailable after the rental ends until an authorized return inspection is approved.</div></>}
    </section></main>{confirmElement}{kycPreview && <div className="modal-backdrop" onClick={() => { URL.revokeObjectURL(kycPreview.url); setKycPreview(null); }}><section className="kyc-preview-modal" role="dialog" aria-modal="true" aria-label="Private identity document preview" onClick={(event) => event.stopPropagation()}><button className="modal-close" aria-label="Close document" onClick={() => { URL.revokeObjectURL(kycPreview.url); setKycPreview(null); }}><X size={19} /></button><p className="eyebrow">PRIVATE KYC DOCUMENT</p><h2>{kycPreview.name}</h2><iframe title={kycPreview.name} src={kycPreview.url} referrerPolicy="no-referrer" /></section></div>}{(showCreate || editing) && <VehicleForm vehicle={editing} onClose={() => { setShowCreate(false); setEditing(null); }} onSubmit={create} busy={busy} />}</div>;
}

function OperationsTable({ bookings, onAction, compact = false }: { bookings: Booking[]; onAction: (booking: Booking, action: 'cancel' | 'start' | 'return' | 'inspection') => void; compact?: boolean }) {
  return <div className="inventory-table-wrap"><table><thead><tr><th>BOOKING</th><th>VEHICLE</th>{!compact && <th>RENTAL WINDOW</th>}<th>STATUS</th><th>TOTAL</th><th>AGREEMENT</th><th>ACTION</th></tr></thead><tbody>{bookings.map((booking) => <tr key={booking.id}><td><b>{booking.id.slice(0, 8).toUpperCase()}</b><small className="table-sub">Customer {booking.customer_id.slice(0, 8)}</small></td><td><b>{booking.vehicle_make} {booking.vehicle_model}</b><small className="table-sub">{booking.vehicle_license_plate}</small></td>{!compact && <td><small>{dateTime(booking.pickup_at, { month: 'short', day: 'numeric', hour: 'numeric' })}</small><small className="table-sub">to {dateTime(booking.return_at, { hour: 'numeric' })}</small></td>}<td><span className={`status-pill status-${booking.status}`}>{booking.status.replaceAll('_', ' ')}</span></td><td>{money(booking.amount_minor)}</td><td><small>{booking.agreement_version || 'legacy'}</small><small className="table-sub">{booking.agreement_accepted_at ? dateTime(booking.agreement_accepted_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : 'not recorded'}</small></td><td>{booking.status === 'pending' ? <button className="table-action archive" onClick={() => onAction(booking, 'cancel')}>Cancel</button> : booking.status === 'confirmed' ? <button className="table-action" onClick={() => onAction(booking, 'start')}>Start rental</button> : booking.status === 'active' ? <button className="table-action" onClick={() => onAction(booking, 'return')}>Record return</button> : ['awaiting_inspection', 'inspection_failed'].includes(booking.status) ? <button className="table-action" onClick={() => onAction(booking, 'inspection')}>Approve &amp; relist</button> : <span className="muted">—</span>}</td></tr>)}</tbody></table>{!bookings.length && <div className="empty-state table-empty"><CalendarDays size={30} /><h3>No bookings in this view</h3><p>New customer reservations will appear here.</p></div>}</div>;
}

function VehicleForm({ vehicle, onClose, onSubmit, busy }: { vehicle: Vehicle | null; onClose: () => void; onSubmit: (data: FormData) => void; busy: boolean }) {
  return <div className="modal-backdrop" onClick={onClose}><div className="vehicle-form-modal" onClick={(e) => e.stopPropagation()}><button className="modal-close" onClick={onClose}><X size={19} /></button><p className="eyebrow">FLEET MANAGEMENT</p><h2>{vehicle ? 'Edit vehicle' : 'Add a vehicle'}</h2><p className="muted">Accurate details appear on customer rental tickets.</p><form className="vehicle-form" onSubmit={(e) => { e.preventDefault(); onSubmit(new FormData(e.currentTarget)); }}><label>Make<input name="make" required defaultValue={vehicle?.make} placeholder="Toyota" /></label><label>Model<input name="model" required defaultValue={vehicle?.model} placeholder="Camry" /></label><label>Year<input name="year" type="number" min="1900" max="2100" defaultValue={vehicle?.year || 2025} required /></label><label>Color<input name="color" required defaultValue={vehicle?.color} placeholder="Silver" /></label><label>Category<select name="category" defaultValue={vehicle?.category || 'Sedan'}><option>Sedan</option><option>SUV</option><option>Premium</option><option>Coupe</option><option>Van</option></select></label><label>Seats<input name="seats" type="number" min="1" max="20" defaultValue={vehicle?.seats || 5} required /></label><label>Transmission<select name="transmission" defaultValue={vehicle?.transmission || 'automatic'}><option value="automatic">Automatic</option><option value="manual">Manual</option></select></label><label>Fuel type<select name="fuel_type" defaultValue={vehicle?.fuel_type || 'petrol'}><option value="petrol">Petrol</option><option value="diesel">Diesel</option><option value="hybrid">Hybrid</option><option value="electric">Electric</option></select></label><label>License plate<input name="registration_number" required defaultValue={vehicle?.registration_number} placeholder="ABC 123 XY" /></label><label>Hourly rate (USD)<input name="hourly_rate" type="number" min="0.01" step="0.01" defaultValue={vehicle?.hourly_rate || 25} required /></label><label>Status<select name="status" defaultValue={vehicle?.status || 'active'}><option value="active">Available</option><option value="maintenance">Maintenance</option><option value="retired">Retired</option></select></label><div className="form-actions"><button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : vehicle ? 'Save changes' : 'Save vehicle'} <ArrowRight size={15} /></button></div></form></div></div>;
}
