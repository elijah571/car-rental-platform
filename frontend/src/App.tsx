import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, ArrowUpRight, BadgeCheck, CalendarDays, CarFront, Check, ChevronDown, CircleHelp, Clock3, Compass, CreditCard, Download, Filter, Fuel, Gauge, KeyRound, LayoutDashboard, ListFilter, LockKeyhole, LogOut, Menu, MessageCircle, Plus, Search, Send, Settings, ShieldCheck, SlidersHorizontal, Sparkles, Users, Wifi, WifiOff, X } from 'lucide-react';
import { api, dateTime, imageFor, money, tokenStore } from './api';
import type { Booking, Receipt, Vehicle } from './types';

type Page = 'explore' | 'results' | 'detail' | 'checkout' | 'bookings' | 'account' | 'support' | 'admin';
const stripeKey = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || '';
const stripeConfigured = stripeKey.startsWith('pk_') && !stripeKey.includes('replace_me');
const StripePaymentWidget = lazy(() => import('./StripePayment'));
const initials = (email?: string) => email ? email.slice(0, 2).toUpperCase() : 'EP';
const localInputDate = (date: Date) => { const offset = date.getTimezoneOffset(); return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 16); };
const rentalDurations = [...Array.from({ length: 24 }, (_, index) => index + 1), 36, 48, 72, 96, 120, 144, 168];
const estimateRentalTotal = (dailyRate: number | string, hours: number) => Math.round(Number(dailyRate) * 100 * hours / 24);

export default function App() {
  const [page, setPage] = useState<Page>('explore');
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [matches, setMatches] = useState<Vehicle[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [selected, setSelected] = useState<Vehicle | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [pickup, setPickup] = useState(() => localInputDate(new Date(Date.now() + 86_400_000)));
  const [durationHours, setDurationHours] = useState(24);
  const dropoff = localInputDate(new Date(new Date(pickup).getTime() + durationHours * 3_600_000));
  const [filter, setFilter] = useState('All vehicles');
  const [view, setView] = useState<'login' | 'register' | 'confirm' | 'resend' | 'forgot' | 'reset' | null>(null);
  const [accountEmail, setAccountEmail] = useState(localStorage.getItem('drivewell_email') || '');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeBooking, setActiveBooking] = useState<Booking | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [showHowItWorks, setShowHowItWorks] = useState(false);

  useEffect(() => { api.vehicles().then(setVehicles).catch((e) => setError(e.message)); }, []);
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
  const visibleVehicles = useMemo(() => (page === 'results' && hasSearched ? matches : vehicles).filter((v) => filter === 'All vehicles' || v.category === filter), [filter, hasSearched, matches, page, vehicles]);

  async function findCars() {
    setError(''); setPage('results'); setLoading(true); setHasSearched(true);
    try {
      const pickupIso = new Date(pickup).toISOString(); const returnIso = new Date(dropoff).toISOString();
      const list = await api.availability(pickupIso, returnIso);
      setMatches(list); setFilter('All vehicles');
    } catch (e) { setError((e as Error).message); setMatches([]); }
    finally { setLoading(false); }
  }

  function needLogin() { if (!tokenStore.get()) { setView('login'); return false; } return true; }

  async function startBooking(vehicle: Vehicle) {
    setSelected(vehicle); setError('');
    if (!needLogin()) return;
    setLoading(true);
    try {
      const booking = await api.createBooking(vehicle.id, new Date(pickup).toISOString(), new Date(dropoff).toISOString());
      setActiveBooking(booking); setPage('checkout');
    } catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }

  async function beginPayment() {
    if (!activeBooking || !needLogin()) return;
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
          {page === 'explore' && <Landing pickup={pickup} dropoff={dropoff} durationHours={durationHours} setPickup={setPickup} setDurationHours={setDurationHours} findCars={findCars} setPage={setPage} />}
          {page === 'results' && <Results vehicles={visibleVehicles} categories={categories} filter={filter} setFilter={setFilter} loading={loading} onSelect={(v) => { setSelected(v); setPage('detail'); }} />}
          {page === 'detail' && selected && <Detail vehicle={selected} pickup={pickup} dropoff={dropoff} onBack={() => setPage('results')} onBook={() => void startBooking(selected)} loading={loading} />}
          {page === 'checkout' && activeBooking && <Checkout booking={activeBooking} vehicle={selected} clientSecret={clientSecret} onPay={beginPayment} loading={loading} onBack={() => setPage('detail')} />}
          {page === 'bookings' && <Bookings bookings={bookings} onRefresh={loadBookings} onReceipt={openReceipt} onCheckPayment={(id) => syncPaymentUntilSettled(id)} />}
          {page === 'account' && <Account email={accountEmail} onLogout={logout} onAdmin={() => navigate('admin')} onSupport={() => navigate('support')} onPasswordChanged={() => { setAccountEmail(''); setPage('explore'); setView('login'); setNotice('Password changed. Sign in with your new password.'); }} />}
          {page === 'support' && <SupportCenter onError={setError} />}
        </main>
        <footer className="footer"><span>DRIVEWELL / YOUR JOURNEY, WELL TAKEN</span><span>Clear pricing. Confident journeys.</span><span>© 2026 Drivewell</span></footer>
      </>}
    </div>
    {error && <div className="toast toast-error" role="alert"><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss"><X size={16} /></button></div>}
    {notice && <div className="toast" role="status"><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Dismiss"><X size={16} /></button></div>}
    {receipt && <ReceiptDialog receipt={receipt} onClose={() => setReceipt(null)} />}
    {view && <AuthDialog mode={view} email={accountEmail} onClose={() => setView(null)} onSwitch={setView} onSubmit={handleAuth} />}
  </>;
}

function Landing({ pickup, dropoff, durationHours, setPickup, setDurationHours, findCars, setPage }: { pickup: string; dropoff: string; durationHours: number; setPickup: (v: string) => void; setDurationHours: (v: number) => void; findCars: () => void; setPage: (p: Page) => void }) {
  return <>
    <section className="hero wrap">
      <div className="hero-copy"><p className="eyebrow"><span className="eyebrow-line" /> THE KEYS TO YOUR NEXT JOURNEY</p><h1>Your next ride,<br /><em>on your terms.</em></h1><p className="hero-text">Find the right car for your plans. Choose a rental duration, see the total, and book with confidence.</p><div className="price-chip"><Sparkles size={15} /> Vehicle specific hourly rates <span>•</span> USD pricing</div><div className="hero-trust"><span><ShieldCheck size={15} /> Secure booking</span><span><BadgeCheck size={15} /> Verified availability</span></div></div>
      <div className="hero-art"><img src="/cars/tesla-roaster.jpeg" alt="A premium electric car ready for your next journey" /><div className="art-label"><span className="live-dot" /> THE OPEN ROAD IS CALLING</div><div className="art-stamp">DW<br /><span>EST. 2026</span></div></div>
    </section>
    <section className="search-panel wrap">
      <div className="search-field location-field"><span className="field-icon"><Compass size={17} /></span><label>Pickup location</label><strong>Abuja, Nigeria</strong><span className="field-caption">Central pickup point</span></div>
      <div className="search-field"><span className="field-icon"><CalendarDays size={17} /></span><label>Pickup date & time</label><input type="datetime-local" value={pickup} onChange={(e) => setPickup(e.target.value)} /></div>
      <div className="search-field"><span className="field-icon"><Clock3 size={17} /></span><label htmlFor="rental-duration">Rental duration</label><select id="rental-duration" value={durationHours} onChange={(e) => setDurationHours(Number(e.target.value))}>{rentalDurations.map((hours) => <option key={hours} value={hours}>{hours < 24 ? `${hours} ${hours === 1 ? 'hour' : 'hours'}` : `${hours / 24} ${hours === 24 ? 'day' : 'days'}`}</option>)}</select><span className="field-caption">Up to 7 days</span></div>
      <div className="search-field location-field"><span className="field-icon"><CalendarDays size={17} /></span><label>Return date & time</label><strong>{dateTime(new Date(dropoff).toISOString())}</strong><span className="field-caption">Based on selected duration</span></div>
      <button className="btn btn-primary find-button" onClick={findCars}>Find a car <ArrowRight size={17} /></button>
    </section>
    <section className="category-section wrap"><div className="section-heading"><div><p className="eyebrow">CURATED FOR YOUR PLANS</p><h2>Find your kind of drive</h2></div><button className="text-link" onClick={() => setPage('results')}>Explore all cars <ArrowUpRight size={16} /></button></div><div className="category-grid">
      <CategoryCard name="Everyday" note="Practical for daily plans" category="Sedan" number="01" image="/cars/toyota-camry.jpeg" onClick={() => setPage('results')} />
      <CategoryCard name="Room for more" note="Space for every passenger" category="SUV" number="02" image="/cars/SUV.jpeg" onClick={() => setPage('results')} />
      <CategoryCard name="Make it memorable" note="The finer things in motion" category="Premium" number="03" image="/cars/BMW.jpeg" onClick={() => setPage('results')} />
    </div></section>
    <section id="how-it-works" className="how-section"><div className="wrap how-inner"><div><p className="eyebrow">A BETTER WAY TO GET THERE</p><h2>Good journeys start<br />with a little clarity.</h2><p className="how-intro">From choosing a vehicle to receiving your confirmation, every step is designed to be straightforward. You can review your rental details and pricing before you pay.</p></div><div className="steps"><Step number="01" title="Choose your car" text="Browse the fleet and compare vehicle details, categories, and hourly rates. Pick the car that fits your plans, passengers, and luggage." /><Step number="02" title="Set your own pace" text="Select your pick-up time and rental duration to check availability. We calculate the estimated total up front, so you can review the timing and cost before booking." /><Step number="03" title="Drive with confidence" text="Sign in to reserve your vehicle, then complete payment securely. Once payment is verified, your booking is confirmed and your receipt is sent by email." /></div></div></section>
    <div className="wrap reassurance"><div><ShieldCheck size={19} /><span>Secure checkout powered by Stripe</span></div><div><Clock3 size={19} /><span>A 15 minute hold to complete payment</span></div><div><BadgeCheck size={19} /><span>Booking confirmed after verified payment</span></div></div>
  </>;
}

function CategoryCard({ name, note, category, number, image, onClick }: { name: string; note: string; category: string; number: string; image: string; onClick: () => void }) {
  return <button className="category-card" onClick={onClick}><img src={image} alt="" /><span className="category-number">{number} / {category.toUpperCase()}</span><span className="category-info"><strong>{name}</strong><small>{note}</small></span><span className="category-arrow"><ArrowUpRight size={18} /></span></button>;
}

function Step({ number, title, text }: { number: string; title: string; text: string }) { return <div className="step"><span>{number}</span><div><strong>{title}</strong><p>{text}</p></div></div>; }

function Results({ vehicles, categories, filter, setFilter, loading, onSelect }: { vehicles: Vehicle[]; categories: string[]; filter: string; setFilter: (v: string) => void; loading: boolean; onSelect: (v: Vehicle) => void }) {
  return <section className="wrap page-content"><div className="breadcrumb"><span>Explore</span><ArrowRight size={13} /><strong>Find your car</strong></div><div className="page-title-row"><div><p className="eyebrow">THE DRIVEWELL FLEET</p><h1>Find your car</h1><p className="muted">The right vehicle for wherever the day takes you.</p></div><div className="sort-pill"><ListFilter size={15} /> Recommended <ChevronDown size={14} /></div></div>
    <div className="results-layout"><aside className="filter-panel"><div className="filter-title"><SlidersHorizontal size={17} /><strong>Filters</strong><button onClick={() => setFilter('All vehicles')}>Reset</button></div><div className="filter-group"><span className="filter-label">VEHICLE TYPE</span>{categories.map((c) => <label className="check-row" key={c}><input type="radio" name="category" checked={filter === c} onChange={() => setFilter(c)} /><span>{c}</span><span className="radio-mark" /></label>)}</div><div className="filter-group"><span className="filter-label">HOURLY RATE</span><div className="filter-rate-label">Each vehicle has its own hourly rate.</div></div><div className="filter-note"><LockKeyhole size={16} /><span>Select a rental duration to see your vehicle’s total.</span></div></aside>
      <div className="vehicle-results"><div className="results-title"><div><h2>Available vehicles</h2><p>{loading ? 'Checking availability…' : `${vehicles.length} ${vehicles.length === 1 ? 'vehicle' : 'vehicles'} available for your dates`}</p></div><button className="icon-button" aria-label="Filter vehicles"><Filter size={17} /></button></div>{loading ? <div className="empty-state"><span className="spinner" /> Finding the right drive…</div> : vehicles.length === 0 ? <div className="empty-state"><CarFront size={34} /><h3>No cars found for these dates</h3><p>Try another time window or check back soon as our fleet grows.</p></div> : <div className="vehicle-grid">{vehicles.map((v) => <VehicleCard key={v.id} vehicle={v} onSelect={() => onSelect(v)} />)}</div>}</div>
    </div></section>;
}

function VehicleCard({ vehicle, onSelect }: { vehicle: Vehicle; onSelect: () => void }) {
  const price = vehicle.rental_total_minor != null ? money(vehicle.rental_total_minor) : `$${vehicle.hourly_rate} / day`;
  return <article className="vehicle-card"><button className="vehicle-photo" onClick={onSelect}><img src={imageFor(vehicle)} alt={`${vehicle.make} ${vehicle.model}`} /><span className="availability-tag"><span className="live-dot" /> Available</span><span className="photo-arrow"><ArrowUpRight size={17} /></span></button><div className="vehicle-card-body"><div className="vehicle-card-title"><div><h3>{vehicle.make} {vehicle.model}</h3><p>{vehicle.category} <span>·</span> {vehicle.seats} seats <span>·</span> {vehicle.transmission}</p></div><button className="heart" aria-label="Save car">♡</button></div><div className="vehicle-specs"><span><span className="color-dot" style={{ backgroundColor: vehicle.color.toLowerCase() }} />{vehicle.color}</span><span><Fuel size={14} />{vehicle.fuel_type}</span></div><div className="vehicle-card-footer"><div><strong>{price}</strong>{vehicle.rental_total_minor != null && <small>total for selected dates</small>}</div><button className="btn btn-dark" onClick={onSelect}>View details <ArrowRight size={15} /></button></div></div></article>;
}

function Detail({ vehicle, pickup, dropoff, onBack, onBook, loading }: { vehicle: Vehicle; pickup: string; dropoff: string; onBack: () => void; onBook: () => void; loading: boolean }) {
  const hours = Math.max(1, Math.ceil((new Date(dropoff).getTime() - new Date(pickup).getTime()) / 3_600_000));
  const totalMinor = vehicle.rental_total_minor ?? estimateRentalTotal(vehicle.hourly_rate, hours);
  return <section className="wrap page-content"><button className="back-link" onClick={onBack}><ArrowLeft size={16} /> Back to available cars</button><div className="detail-layout"><div><div className="detail-photo"><img src={imageFor(vehicle)} alt={`${vehicle.make} ${vehicle.model}`} /><span className="availability-tag"><span className="live-dot" /> Available for your dates</span></div><div className="detail-description"><p className="eyebrow">A DRIVEWELL FAVORITE</p><h1>{vehicle.make} {vehicle.model}</h1><p>A comfortable, carefully selected {vehicle.category.toLowerCase()} for business trips, weekend plans, and everything in between.</p></div><div className="spec-grid"><Spec label="Seats" value={`${vehicle.seats} passengers`} icon={<Users size={18} />} /><Spec label="Transmission" value={vehicle.transmission} icon={<Gauge size={18} />} /><Spec label="Fuel type" value={vehicle.fuel_type} icon={<Fuel size={18} />} /><Spec label="Color" value={vehicle.color} icon={<span className="color-dot" style={{ backgroundColor: vehicle.color.toLowerCase() }} />} /></div><p className="availability-hint"><ShieldCheck size={16} /> Availability is checked again when you submit. Final pricing is confirmed by the backend.</p></div><aside className="booking-summary"><p className="eyebrow">YOUR DRIVE, YOUR WAY</p><h3>{vehicle.make} {vehicle.model}</h3><p className="summary-sub">{vehicle.category} · {vehicle.color} · {vehicle.transmission}</p><div className="summary-status"><span className="live-dot" /> Available for your dates</div><div className="summary-price"><strong>{money(totalMinor)}</strong><span>total</span><small>{money(Math.round(Number(vehicle.hourly_rate) * 100))} per day · USD</small></div><div className="summary-row"><span><CalendarDays size={15} /> Pickup</span><b>{dateTime(new Date(pickup).toISOString())}</b></div><div className="summary-row"><span><CalendarDays size={15} /> Return</span><b>{dateTime(new Date(dropoff).toISOString())}</b></div><div className="summary-total"><span>Rental duration</span><b>{hours} {hours === 1 ? 'hour' : 'hours'}</b></div><button className="btn btn-primary full" onClick={onBook} disabled={loading}>{loading ? 'Creating your booking…' : 'Continue to booking'} <ArrowRight size={16} /></button><p className="summary-foot"><LockKeyhole size={13} /> Your final total is calculated securely by the backend.</p></aside></div></section>;
}

function Spec({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) { return <div className="spec-item"><span className="spec-icon">{icon}</span><div><small>{label}</small><strong>{value}</strong></div></div>; }

function Checkout({ booking, vehicle, clientSecret, onPay, loading, onBack }: { booking: Booking; vehicle: Vehicle | null; clientSecret: string; onPay: () => void; loading: boolean; onBack: () => void }) {
  const [seconds, setSeconds] = useState(booking.expires_at ? Math.max(0, Math.floor((new Date(booking.expires_at).getTime() - Date.now()) / 1000)) : 900);
  useEffect(() => { const timer = window.setInterval(() => setSeconds((s) => Math.max(0, s - 1)), 1000); return () => window.clearInterval(timer); }, []);
  const hours = Math.max(1, Math.ceil((new Date(booking.return_at).getTime() - new Date(booking.pickup_at).getTime()) / 3_600_000));
  const dailyRateMinor = vehicle ? Math.round(Number(vehicle.hourly_rate) * 100) : Math.round((booking.amount_minor || 0) * 24 / hours);
  return <section className="wrap page-content"><button className="back-link" onClick={onBack}><ArrowLeft size={16} /> Back to vehicle</button><div className="page-title-row checkout-title"><div><p className="eyebrow">YOUR JOURNEY IS ALMOST SET</p><h1>Secure checkout</h1><p className="muted">Your vehicle is held temporarily while you complete payment.</p></div><div className="hold-clock"><Clock3 size={17} /><span>{String(Math.floor(seconds / 60)).padStart(2, '0')}:{String(seconds % 60).padStart(2, '0')}<small> minutes remaining</small></span></div></div><div className="checkout-steps"><span className="done"><Check size={14} /> Rental details</span><i /><span className="current"><CreditCard size={14} /> Payment</span><i /><span><BadgeCheck size={14} /> Confirmation</span></div><div className="checkout-layout"><div className="checkout-card"><div className="checkout-card-heading"><span className="step-icon"><CreditCard size={18} /></span><div><h2>Payment method</h2><p>Secure payment powered by Stripe</p></div></div>{clientSecret ? <Suspense fallback={<p className="muted stripe-loading">Loading Stripe’s secure form…</p>}><StripePaymentWidget clientSecret={clientSecret} bookingId={booking.id} /></Suspense> : <div className="stripe-intro"><div className="stripe-symbol">S</div><div><strong>Pay securely with Stripe</strong><p>You’ll continue to Stripe’s secure payment experience. Card details are handled by Stripe and never touch our servers.</p></div><button className="btn btn-primary" onClick={onPay} disabled={loading || seconds === 0}>{loading ? 'Preparing secure checkout…' : 'Continue to payment'} <ArrowRight size={16} /></button></div>}<p className="secure-note"><LockKeyhole size={14} /> Encrypted payment flow · Your card details remain with Stripe</p></div><aside className="booking-summary checkout-summary"><p className="eyebrow">PAYMENT SUMMARY</p><div className="summary-car"><img src={vehicle ? imageFor(vehicle) : '/cars/SUV.jpeg'} alt="" /><div><strong>{booking.vehicle_make || vehicle?.make} {booking.vehicle_model || vehicle?.model}</strong><small>{hours} hours · {dateTime(booking.pickup_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}–{dateTime(booking.return_at, { hour: 'numeric', minute: '2-digit' })}</small></div></div><div className="summary-row"><span>Rental period</span><b>{hours} hours</b></div><div className="summary-row"><span>Hourly rate</span><b>{money(dailyRateMinor)} / day</b></div><div className="summary-total"><span>Total due</span><b>{money(booking.amount_minor)} USD</b></div><p className="checkout-assurance"><ShieldCheck size={16} /> Your booking is confirmed only after Stripe verifies the payment.</p></aside></div></section>;
}

function Bookings({ bookings, onRefresh, onReceipt, onCheckPayment }: { bookings: Booking[]; onRefresh: () => void; onReceipt: (b: Booking) => void; onCheckPayment: (id: string) => Promise<void> }) {
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
    {list.length ? <div className="booking-list">{list.map((booking) => <article className="booking-card" key={booking.id}>
      <div className="booking-vehicle-image"><img src={imageFor({ make: booking.vehicle_make || 'Toyota', model: booking.vehicle_model || 'SUV', category: 'SUV' })} alt="" /></div>
      <div className="booking-main"><div className="booking-topline"><div><h3>{booking.vehicle_make} {booking.vehicle_model}</h3><p>Booking {booking.id.slice(0, 8).toUpperCase()} · {booking.vehicle_color} · {booking.vehicle_license_plate}</p></div><span className={`status-pill status-${booking.status}`}>{booking.status.replaceAll('_', ' ')}</span></div>
        <div className="booking-window"><div><small>PICKUP</small><b>{dateTime(booking.pickup_at)}</b></div><ArrowRight size={16} /><div><small>RETURN</small><b>{dateTime(booking.return_at)}</b></div></div>
        <div className="booking-bottom"><span><Check size={14} /> {booking.status === 'confirmed' ? 'Paid in USD' : booking.status === 'pending' ? 'Payment pending' : booking.status}</span><strong>{money(booking.amount_minor)}</strong>
          {['pending', 'expired'].includes(booking.status) && <button className="text-link" disabled={checkingId === booking.id} onClick={() => void checkPayment(booking.id)}>{checkingId === booking.id ? 'Checking payment…' : 'Check payment status'}</button>}
          {['confirmed', 'active', 'awaiting_inspection', 'inspection_failed', 'completed'].includes(booking.status) && <button className="text-link" onClick={() => onReceipt(booking)}>View ticket <ArrowUpRight size={15} /></button>}
        </div>
      </div>
    </article>)}</div> : <div className="empty-state booking-empty"><CalendarDays size={32} /><h3>No {tab.toLowerCase()} yet</h3><p>When you book a vehicle, it will show up here.</p><button className="btn btn-primary" onClick={() => { window.location.hash = ''; window.location.reload(); }}>Explore the fleet <ArrowRight size={15} /></button></div>}
  </section>;
}

function Account({ email, onLogout, onAdmin, onSupport, onPasswordChanged }: { email: string; onLogout: () => void; onAdmin: () => void; onSupport: () => void; onPasswordChanged: () => void }) {
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  async function changePassword(form: FormData) {
    setMessage(''); setError('');
    try {
      const result = await api.auth('/change-password', { current_password: String(form.get('current_password') || ''), new_password: String(form.get('new_password') || '') });
      setMessage(result.message || 'Password changed. Sign in again.'); tokenStore.clear(); tokenStore.clearRefresh(); localStorage.removeItem('drivewell_email'); localStorage.removeItem('drivewell_role'); onPasswordChanged();
    } catch (e) { setError((e as Error).message); }
  }
  return <section className="wrap page-content account-page"><div className="page-title-row"><div><p className="eyebrow">YOUR PROFILE</p><h1>Your account</h1><p className="muted">Your details and sign-in preferences.</p></div></div><div className="account-layout"><aside className="account-card"><div className="avatar large">{initials(email)}</div><h3>{email || 'Drivewell guest'}</h3><p>{email ? 'Signed in securely' : 'Create a local Drivewell account'}</p><div className="verified-badge"><BadgeCheck size={15} /> Email verified</div><button className="account-menu-item active"><Users size={17} /> Personal details <ArrowRight size={15} /></button><button className="account-menu-item" onClick={() => document.getElementById('security-settings')?.scrollIntoView({ behavior: 'smooth' })}><KeyRound size={17} /> Security <ArrowRight size={15} /></button><button className="account-menu-item" onClick={onSupport}><CircleHelp size={17} /> Help & support <ArrowRight size={15} /></button></aside><div className="account-details"><div className="settings-panel"><p className="eyebrow">PERSONAL DETAILS</p><h2>Account identity</h2><p className="muted">Your verified identity is stored securely in the platform database.</p><div className="account-fields"><div><small>EMAIL ADDRESS</small><strong>{email || 'Not signed in'}</strong></div><div><small>ACCOUNT STATUS</small><strong className="verified-text"><BadgeCheck size={15} /> {email ? 'Verified' : 'Guest'}</strong></div></div><div className="account-note"><LockKeyhole size={16} /><span>Email verification is handled through the configured SMTP server.</span></div></div><form id="security-settings" className="settings-panel auth-form" onSubmit={(e) => { e.preventDefault(); void changePassword(new FormData(e.currentTarget)); }}><p className="eyebrow">SECURITY</p><h2>Change password</h2><label>Current password<input name="current_password" type="password" required autoComplete="current-password" /></label><label>New password<input name="new_password" type="password" minLength={8} required autoComplete="new-password" /></label>{message && <p className="verified-text">{message}</p>}{error && <p className="inline-error">{error}</p>}<button className="btn btn-primary">Update password <KeyRound size={15} /></button></form><div className="settings-actions"><button className="btn btn-outline" onClick={onSupport}><CircleHelp size={16} /> Support tickets</button><button className="btn btn-outline" onClick={onAdmin}><LayoutDashboard size={16} /> Operations workspace</button>{email && <button className="btn btn-danger-outline" onClick={onLogout}><LogOut size={16} /> Sign out</button>}</div></div></div></section>;
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
  const [section, setSection] = useState<'overview' | 'vehicles' | 'bookings' | 'support' | 'customers'>('overview');
  const [adminAccess, setAdminAccess] = useState<boolean | null>(null);
  const [opsBookings, setOpsBookings] = useState<Booking[]>([]);
  const [bookingFilter, setBookingFilter] = useState('All bookings');
  const [showCreate, setShowCreate] = useState(false); const [editing, setEditing] = useState<Vehicle | null>(null); const [search, setSearch] = useState(''); const [busy, setBusy] = useState(false);
  const [supportTickets, setSupportTickets] = useState<import('./types').SupportTicket[]>([]);
  const [activeTicket, setActiveTicket] = useState<import('./types').SupportTicket | null>(null);
  const [supportLive, setSupportLive] = useState(true);
  const adminMessagesEnd = useRef<HTMLDivElement | null>(null);
  const [customers, setCustomers] = useState<Array<{ id: string; email: string; name: string; role: string; is_active: boolean; is_email_verified: boolean; created_at: string }>>([]);
  const filtered = vehicles.filter((v) => `${v.make} ${v.model} ${v.registration_number}`.toLowerCase().includes(search.toLowerCase()));
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

  async function updateBooking(booking: Booking, action: 'cancel' | 'start' | 'return' | 'inspection') {
    if (action === 'cancel' && !window.confirm('Cancel this unpaid booking hold?')) return;
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
  const title = section === 'overview' ? 'Operations overview' : section === 'vehicles' ? 'Vehicle inventory' : section === 'support' ? 'Support inbox' : section === 'customers' ? 'Customer accounts' : 'Booking management';
  const subtitle = section === 'overview' ? 'A clear view of your fleet and upcoming rental activity.' : section === 'vehicles' ? 'Manage the vehicles customers can browse and book.' : section === 'support' ? 'Manage tickets, threaded replies, priority, and status.' : section === 'customers' ? 'Review accounts and manage access.' : 'Monitor payment holds, confirmed rentals, and vehicle returns.';
  if (adminAccess === false) return <div className="admin-denied"><span className="auth-icon"><LockKeyhole size={23} /></span><p className="eyebrow">OPERATIONS WORKSPACE</p><h1>Administrator access required</h1><p>Sign in with an account assigned the <b>platform-admin</b> role to manage vehicles, bookings, and inspections.</p><button className="btn btn-outline" onClick={onExit}>Return to Drivewell</button></div>;

  return <div className="admin-app"><aside className="admin-sidebar"><button className="brand admin-brand" onClick={onExit}><img className="brand-logo" src="/logo.png" alt="Driveflow Car Rental Platform" /></button><span className="sidebar-label">WORKSPACE</span><p className="sidebar-section">ADMINISTRATION</p><button className={`admin-nav ${section === 'overview' ? 'active' : ''}`} onClick={() => setSection('overview')}><LayoutDashboard size={17} /> Overview</button><button className={`admin-nav ${section === 'vehicles' ? 'active' : ''}`} onClick={() => setSection('vehicles')}><CarFront size={17} /> Vehicles <span>{vehicles.length}</span></button><button className={`admin-nav ${section === 'bookings' ? 'active' : ''}`} onClick={() => setSection('bookings')}><CalendarDays size={17} /> Bookings</button><button className={`admin-nav ${section === 'support' ? 'active' : ''}`} onClick={() => { setSection('support'); void refreshSupport(); }}><CircleHelp size={17} /> Support</button><button className={`admin-nav ${section === 'customers' ? 'active' : ''}`} onClick={() => { setSection('customers'); void refreshCustomers(); }}><Users size={17} /> Customers</button><button className="admin-nav" onClick={() => { setSection('bookings'); setBookingFilter('Return review'); }}><BadgeCheck size={17} /> Inspections</button><button className="admin-nav" onClick={() => { setSection('bookings'); setBookingFilter('All bookings'); }}><CreditCard size={17} /> Payments</button><button className="admin-nav"><Settings size={17} /> Settings</button><div className="admin-user"><span className="avatar">AD</span><div><b>Administrator</b><small>Operations</small></div><button onClick={onExit} title="Exit operations"><LogOut size={16} /></button></div></aside><main className="admin-main"><header className="admin-topbar"><span>Operations <span>/</span> {title}</span><div><button className="admin-how-link" onClick={onHowItWorks}>How it works</button><button className="icon-button" onClick={() => { if (section === 'support') void refreshSupport(); else if (section === 'customers') void refreshCustomers(); else void refreshOperations(); }} title="Refresh operations"><CircleHelp size={18} /></button><span className="avatar">AD</span><span>Admin</span></div></header><section className="admin-content"><div className="admin-heading"><div><p className="eyebrow">{section === 'overview' ? 'OPERATIONS' : section === 'vehicles' ? 'FLEET MANAGEMENT' : section === 'support' ? 'CUSTOMER CARE' : section === 'customers' ? 'ACCOUNT MANAGEMENT' : 'BOOKING OPERATIONS'}</p><h1>{title}</h1><p>{subtitle}</p></div>{section === 'vehicles' && <button className="btn btn-primary" onClick={() => setShowCreate(true)}><Plus size={17} /> Add vehicle</button>}</div>
    {section === 'overview' && <><div className="admin-stats"><div><span>ACTIVE VEHICLES</span><b>{vehicles.filter((v) => v.status === 'active').length}</b><small>Available fleet inventory</small></div><div><span>UPCOMING BOOKINGS</span><b>{opsBookings.filter((b) => ['pending', 'confirmed'].includes(b.status)).length}</b><small>{opsBookings.filter((b) => b.status === 'pending').length} awaiting payment</small></div><div><span>INSPECTIONS DUE</span><b>{opsBookings.filter((b) => ['awaiting_inspection', 'inspection_failed'].includes(b.status)).length}</b><small>Review before releasing vehicles</small></div></div><div className="inventory-card overview-bookings"><div className="inventory-head"><div><h2>Recent bookings</h2><p>Latest customer rental activity.</p></div><button className="text-link" onClick={() => setSection('bookings')}>View all <ArrowRight size={14} /></button></div><OperationsTable bookings={opsBookings.slice(0, 5)} onAction={updateBooking} compact /></div></>}
    {section === 'vehicles' && <><div className="admin-stats"><div><span>ACTIVE VEHICLES</span><b>{vehicles.filter((v) => v.status === 'active').length}</b><small>Available to customers</small></div><div><span>VEHICLE CATEGORIES</span><b>{new Set(vehicles.map((v) => v.category)).size}</b><small>Across your fleet</small></div><div><span>FLEET HOURLY RATES</span><b>{vehicles.length ? `${money(Math.round(Math.min(...vehicles.map((v) => Number(v.hourly_rate))) * 100))}–${money(Math.round(Math.max(...vehicles.map((v) => Number(v.hourly_rate))) * 100))}` : '—'}</b><small>USD · vehicle specific</small></div></div><div className="inventory-card"><div className="inventory-head"><div><h2>All vehicles <span>{vehicles.length}</span></h2><p>Keep inventory details current and accurate.</p></div><div className="inventory-search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search make, model or plate…" /></div></div><div className="inventory-table-wrap"><table><thead><tr><th>VEHICLE</th><th>PLATE</th><th>RATE</th><th>STATUS</th><th>ACTIONS</th></tr></thead><tbody>{filtered.map((v) => <tr key={v.id}><td><div className="table-vehicle"><img src={imageFor(v)} alt="" /><div><b>{v.make} {v.model}</b><small>{v.color} · {v.year} · {v.category}</small></div></div></td><td>{v.registration_number}</td><td>{money(Math.round(Number(v.hourly_rate) * 100))}/day</td><td><span className="status-pill status-confirmed"><span className="live-dot" /> {v.status}</span></td><td><button className="table-action" onClick={() => setEditing(v)}>Edit</button>{v.status !== 'retired' && <button className="table-action archive" onClick={async () => { try { const updated = await api.deleteVehicle(v.id); onVehicle(vehicles.map((current) => current.id === updated.id ? updated : current)); } catch (e) { setError((e as Error).message); } }}>Delete</button>}</td></tr>)}</tbody></table>{!filtered.length && <div className="empty-state table-empty"><CarFront size={30} /><h3>Your fleet starts here</h3><p>Add a vehicle to make it available to customers.</p><button className="btn btn-primary" onClick={() => setShowCreate(true)}><Plus size={15} /> Add your first vehicle</button></div>}</div><div className="inventory-foot"><ShieldCheck size={15} /> Delete retires a vehicle so existing rental history remains intact.</div></div></>}
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
            <div><span>Your reply will appear in the customer’s support inbox.</span><div><button type="button" className="btn btn-danger-outline" onClick={async () => { if (!window.confirm('Permanently delete this support ticket and its messages?')) return; try { await api.deleteTicket(activeTicket.id); setActiveTicket(null); await refreshSupport(); } catch (error) { setError((error as Error).message); } }}>Delete ticket</button><button className="btn btn-primary">Send reply <Send size={15} /></button></div></div>
          </form>
        </> : <div className="support-admin-empty"><MessageCircle size={34} /><h2>Select a conversation</h2><p>Choose a customer ticket to read the conversation and send a reply.</p></div>}
      </div>
    </div>}
    {section === 'customers' && <div className="inventory-card"><div className="inventory-head"><div><h2>Customer accounts <span>{customers.length}</span></h2><p>Deleting an account disables sign-in and preserves booking records.</p></div><button className="btn btn-outline" onClick={() => void refreshCustomers()}>Refresh</button></div><div className="inventory-table-wrap"><table><thead><tr><th>ACCOUNT</th><th>ROLE</th><th>EMAIL STATUS</th><th>ACCESS</th><th>ACTIONS</th></tr></thead><tbody>{customers.map((customer) => <tr key={customer.id}><td><b>{customer.name}</b><small className="table-sub">{customer.email}</small></td><td><select aria-label={`Role for ${customer.email}`} value={customer.role} onChange={async (e) => { try { const updated = await api.updateUser(customer.id, { role: e.target.value }); setCustomers((items) => items.map((item) => item.id === customer.id ? { ...item, ...updated } : item)); } catch (error) { setError((error as Error).message); } }}><option value="customer">Customer</option><option value="platform-admin">Administrator</option></select></td><td>{customer.is_email_verified ? 'Verified' : 'Unverified'}</td><td><span className={`status-pill ${customer.is_active ? 'status-confirmed' : 'status-cancelled'}`}>{customer.is_active ? 'Active' : 'Disabled'}</span></td><td><button className="table-action" onClick={async () => { try { const updated = await api.updateUser(customer.id, { is_active: !customer.is_active }); setCustomers((items) => items.map((item) => item.id === customer.id ? { ...item, ...updated } : item)); } catch (error) { setError((error as Error).message); } }}>{customer.is_active ? 'Disable' : 'Enable'}</button>{customer.is_active && <button className="table-action archive" onClick={async () => { if (!window.confirm(`Disable ${customer.email}?`)) return; try { await api.deleteUser(customer.id); setCustomers((items) => items.map((item) => item.id === customer.id ? { ...item, is_active: false } : item)); } catch (error) { setError((error as Error).message); } }}>Delete</button>}</td></tr>)}</tbody></table>{!customers.length && <div className="empty-state table-empty"><Users size={28} /><h3>No customer accounts</h3><p>Registered users will appear here.</p></div>}</div></div>}
    {section === 'bookings' && <><div className="ops-tabs">{['All bookings', 'Pending payment', 'Confirmed', 'Active rentals', 'Return review'].map((tab) => <button className={bookingFilter === tab ? 'ops-tab active' : 'ops-tab'} key={tab} onClick={() => setBookingFilter(tab)}>{tab}</button>)}</div><div className="inventory-card"><div className="inventory-head"><div><h2>{bookingFilter} <span>{bookingRows.length}</span></h2><p>Rental state changes are recorded by booking-service.</p></div><button className="btn btn-outline" onClick={refreshOperations}>Refresh <ArrowRight size={14} /></button></div><OperationsTable bookings={bookingRows} onAction={updateBooking} /></div><div className="inventory-foot ops-notice"><ShieldCheck size={15} /> Vehicles remain unavailable after the rental ends until an authorized return inspection is approved.</div></>}
    </section></main>{(showCreate || editing) && <VehicleForm vehicle={editing} onClose={() => { setShowCreate(false); setEditing(null); }} onSubmit={create} busy={busy} />}</div>;
}

function OperationsTable({ bookings, onAction, compact = false }: { bookings: Booking[]; onAction: (booking: Booking, action: 'cancel' | 'start' | 'return' | 'inspection') => void; compact?: boolean }) {
  return <div className="inventory-table-wrap"><table><thead><tr><th>BOOKING</th><th>VEHICLE</th>{!compact && <th>RENTAL WINDOW</th>}<th>STATUS</th><th>TOTAL</th><th>ACTION</th></tr></thead><tbody>{bookings.map((booking) => <tr key={booking.id}><td><b>{booking.id.slice(0, 8).toUpperCase()}</b><small className="table-sub">Customer {booking.customer_id.slice(0, 8)}</small></td><td><b>{booking.vehicle_make} {booking.vehicle_model}</b><small className="table-sub">{booking.vehicle_license_plate}</small></td>{!compact && <td><small>{dateTime(booking.pickup_at, { month: 'short', day: 'numeric', hour: 'numeric' })}</small><small className="table-sub">to {dateTime(booking.return_at, { hour: 'numeric' })}</small></td>}<td><span className={`status-pill status-${booking.status}`}>{booking.status.replaceAll('_', ' ')}</span></td><td>{money(booking.amount_minor)}</td><td>{booking.status === 'pending' ? <button className="table-action archive" onClick={() => onAction(booking, 'cancel')}>Cancel</button> : booking.status === 'confirmed' ? <button className="table-action" onClick={() => onAction(booking, 'start')}>Start rental</button> : booking.status === 'active' ? <button className="table-action" onClick={() => onAction(booking, 'return')}>Record return</button> : ['awaiting_inspection', 'inspection_failed'].includes(booking.status) ? <button className="table-action" onClick={() => onAction(booking, 'inspection')}>Approve inspection</button> : <span className="muted">—</span>}</td></tr>)}</tbody></table>{!bookings.length && <div className="empty-state table-empty"><CalendarDays size={30} /><h3>No bookings in this view</h3><p>New customer reservations will appear here.</p></div>}</div>;
}

function VehicleForm({ vehicle, onClose, onSubmit, busy }: { vehicle: Vehicle | null; onClose: () => void; onSubmit: (data: FormData) => void; busy: boolean }) {
  return <div className="modal-backdrop" onClick={onClose}><div className="vehicle-form-modal" onClick={(e) => e.stopPropagation()}><button className="modal-close" onClick={onClose}><X size={19} /></button><p className="eyebrow">FLEET MANAGEMENT</p><h2>{vehicle ? 'Edit vehicle' : 'Add a vehicle'}</h2><p className="muted">Accurate details appear on customer rental tickets.</p><form className="vehicle-form" onSubmit={(e) => { e.preventDefault(); onSubmit(new FormData(e.currentTarget)); }}><label>Make<input name="make" required defaultValue={vehicle?.make} placeholder="Toyota" /></label><label>Model<input name="model" required defaultValue={vehicle?.model} placeholder="Camry" /></label><label>Year<input name="year" type="number" min="1900" max="2100" defaultValue={vehicle?.year || 2025} required /></label><label>Color<input name="color" required defaultValue={vehicle?.color} placeholder="Silver" /></label><label>Category<select name="category" defaultValue={vehicle?.category || 'Sedan'}><option>Sedan</option><option>SUV</option><option>Premium</option><option>Coupe</option><option>Van</option></select></label><label>Seats<input name="seats" type="number" min="1" max="20" defaultValue={vehicle?.seats || 5} required /></label><label>Transmission<select name="transmission" defaultValue={vehicle?.transmission || 'automatic'}><option value="automatic">Automatic</option><option value="manual">Manual</option></select></label><label>Fuel type<select name="fuel_type" defaultValue={vehicle?.fuel_type || 'petrol'}><option value="petrol">Petrol</option><option value="diesel">Diesel</option><option value="hybrid">Hybrid</option><option value="electric">Electric</option></select></label><label>License plate<input name="registration_number" required defaultValue={vehicle?.registration_number} placeholder="ABC 123 XY" /></label><label>Hourly rate (USD)<input name="hourly_rate" type="number" min="1" step="0.01" defaultValue={vehicle?.hourly_rate || 100} required /></label><label>Status<select name="status" defaultValue={vehicle?.status || 'active'}><option value="active">Available</option><option value="maintenance">Maintenance</option><option value="retired">Retired</option></select></label><div className="form-actions"><button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : vehicle ? 'Save changes' : 'Save vehicle'} <ArrowRight size={15} /></button></div></form></div></div>;
}
