import { chromium } from 'playwright-core';

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173';
const userEmail = process.env.E2E_USER_EMAIL;
const adminEmail = process.env.E2E_ADMIN_EMAIL;
const password = process.env.E2E_PASSWORD;
const recoverBookingId = process.env.E2E_RECOVER_BOOKING_ID;
const executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH || '/usr/bin/google-chrome';

if (!userEmail || !adminEmail || !password) {
  throw new Error('Set E2E_USER_EMAIL, E2E_ADMIN_EMAIL, and E2E_PASSWORD.');
}

const browser = await chromium.launch({ headless: true, executablePath, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const page = await browser.newPage();
page.setDefaultTimeout(15_000);
const passed = [];
const failures = [];
let createdBookingId;
let createdBookingAmount;
let createdSubject;
let availableVehicles = [];
page.on('pageerror', (error) => failures.push(error.message));
page.on('response', (response) => { if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`); });
page.on('response', async (response) => {
  if (response.request().method() === 'POST' && /\/api\/bookings\/?$/.test(response.url()) && response.ok()) {
    try { const booking = await response.json(); createdBookingId = booking.id; createdBookingAmount = booking.amount_minor; } catch { /* Ignore non-JSON responses. */ }
  }
});

try {
  await page.goto(baseURL, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: /Your next ride/i }).waitFor();

  await page.getByRole('button', { name: /Account/i }).click();
  await page.getByRole('button', { name: 'Resend verification code' }).click();
  await page.getByLabel('Email address').fill(`missing-${Date.now()}@example.com`);
  await page.getByRole('button', { name: 'Resend verification code' }).last().click();
  await page.getByRole('heading', { name: 'Check your inbox.' }).waitFor();
  await page.getByText(/If this account needs verification/i).waitFor();
  await page.locator('.auth-modal .modal-close').click();
  passed.push('resend verification-code flow handles unknown accounts generically');

  if (await page.locator('#rental-duration').count()) throw new Error('Rental duration selector should only appear in checkout.');
  const availabilityPromise = page.waitForResponse((response) => response.url().includes('/api/bookings/availability') && response.request().method() === 'GET');
  await page.getByRole('button', { name: /Find a car/i }).click();
  const availabilityResponse = await availabilityPromise;
  if (!availabilityResponse.ok()) throw new Error(`Availability request failed (${availabilityResponse.status()}).`);
  availableVehicles = await availabilityResponse.json();
  if (!availableVehicles.length || availableVehicles.some((vehicle) => !Number(vehicle.hourly_rate))) throw new Error('Vehicles are missing their admin-set hourly rate.');
  const pickupAt = new Date(Date.now() + 86_400_000);
  const tooLong = new URLSearchParams({ pickup_at: pickupAt.toISOString(), return_at: new Date(pickupAt.getTime() + 8 * 86_400_000).toISOString() });
  const rejectedDuration = await page.request.get(`${baseURL}/api/bookings/availability?${tooLong}`);
  if (rejectedDuration.status() !== 422) throw new Error('The API accepted a rental longer than seven days.');
  passed.push('home search has no duration selector and vehicles expose their hourly rates');
  passed.push('booking API rejects rental durations longer than seven days');
  await page.getByRole('heading', { name: 'Available vehicles' }).waitFor();
  await page.getByRole('button', { name: /View details/i }).first().click();
  await page.locator('.detail-layout').waitFor();
  passed.push('customer fleet search and vehicle details');

  await page.getByRole('button', { name: /Account/i }).click();
  await page.getByLabel('Email address').fill(userEmail);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByText('You are signed in.').waitFor();

  await page.getByRole('button', { name: 'My bookings' }).click();
  await page.getByRole('heading', { name: 'My bookings', exact: true }).waitFor();
  await page.waitForLoadState('networkidle');
  passed.push('customer authentication and bookings');
  if (recoverBookingId) {
    await page.getByRole('button', { name: /^Upcoming/ }).click();
    const paidBooking = page.locator('.booking-card').filter({ hasText: recoverBookingId.slice(0, 8).toUpperCase() });
    await paidBooking.waitFor();
    if (await paidBooking.getByRole('button', { name: 'Check payment status' }).count()) {
      await paidBooking.getByRole('button', { name: 'Check payment status' }).click();
    }
    await paidBooking.locator('.status-confirmed').waitFor({ timeout: 30_000 });
    passed.push('previously successful Stripe payment reconciles to confirmed booking');
  }

  await page.getByRole('link', { name: /Driveflow Car Rental Platform/i }).click();
  const pickupValue = await page.locator('input[type="datetime-local"]').inputValue();
  const pickupInstant = new Date(pickupValue);
  const weekAvailability = new URLSearchParams({ pickup_at: pickupInstant.toISOString(), return_at: new Date(pickupInstant.getTime() + 168 * 3_600_000).toISOString() });
  const weekResponse = await page.request.get(`${baseURL}/api/bookings/availability?${weekAvailability}`);
  if (!weekResponse.ok()) throw new Error('Could not find vehicles for the seven-day checkout test.');
  const weekVehicles = await weekResponse.json();
  const checkoutVehicle = weekVehicles[0];
  if (!checkoutVehicle) throw new Error('No vehicle was available for a seven-day rental test.');
  await page.getByRole('button', { name: /Find a car/i }).click();
  await page.locator('.vehicle-card').filter({ hasText: `${checkoutVehicle.make} ${checkoutVehicle.model}` }).first().getByRole('button', { name: /View details/i }).click();
  await page.getByRole('button', { name: /Continue to checkout/i }).click();
  await page.getByRole('heading', { name: 'Review your rental', exact: true }).waitFor();
  await page.locator('#rental-duration').selectOption('168');
  await page.getByText('Estimated total').waitFor();
  await page.getByRole('button', { name: /Reserve & continue to payment/i }).click();
  await page.getByRole('heading', { name: 'Secure checkout', exact: true }).waitFor();
  if (!createdBookingId) throw new Error('The booking request succeeded in the UI but no booking ID was returned.');
  const expectedTotal = Math.round(Number(checkoutVehicle.hourly_rate) * 100 * 168);
  if (createdBookingAmount !== expectedTotal) throw new Error(`Server checkout total ${createdBookingAmount} did not match the ${expectedTotal} cent hourly-rate quote.`);
  passed.push('customer booking creation and checkout hold');
  await page.getByRole('button', { name: /Continue to payment/i }).click();
  await page.getByText(/Pay securely with Stripe|Stripe is not configured/i).waitFor();
  if (await page.getByText(/Stripe is not configured/i).count()) {
    throw new Error('Stripe keys are available in local configuration, but the frontend reports Stripe is not configured.');
  }
  await page.locator('.stripe-form').waitFor();
  passed.push('test-mode payment intent and Stripe payment form');

  await page.getByRole('button', { name: new RegExp(userEmail.split('@')[0], 'i') }).click();
  await page.getByRole('heading', { name: 'Your account', exact: true }).waitFor();
  await page.getByLabel('Current password').fill('intentionally-incorrect');
  await page.getByLabel('New password').fill('Unchanged-test-password-987!');
  await page.getByRole('button', { name: /Update password/i }).click();
  await page.getByText(/Current password is incorrect/i).waitFor();
  passed.push('customer account security rejects an incorrect current password');

  await page.getByRole('navigation').getByRole('button', { name: 'Help & support' }).click();
  const subject = `Customer-admin E2E ${Date.now()}`;
  createdSubject = subject;
  await page.locator('input[name="subject"]').fill(subject);
  await page.locator('textarea[name="message"]').fill('Temporary end-to-end support request.');
  await page.getByRole('button', { name: 'Open support ticket' }).click();
  await page.getByRole('heading', { name: subject, exact: true }).waitFor();
  await page.getByRole('button', { name: 'Reply to this message' }).first().click();
  await page.locator('textarea[name="reply"]').fill('Customer thread reply for end-to-end verification.');
  await page.getByRole('button', { name: 'Send reply' }).click();
  await page.getByText('Customer thread reply for end-to-end verification.').waitFor();
  passed.push('customer support ticket creation and threaded replies');

  await page.getByRole('button', { name: new RegExp(userEmail.split('@')[0], 'i') }).click();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await page.getByRole('button', { name: /Account/i }).waitFor();

  await page.getByRole('button', { name: /Account/i }).click();
  await page.getByLabel('Email address').fill(adminEmail);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByText('You are signed in.').waitFor();
  await page.getByRole('button', { name: new RegExp(adminEmail.split('@')[0], 'i') }).click();
  await page.getByRole('button', { name: /Operations workspace/i }).click();
  await page.getByRole('heading', { name: 'Operations overview', exact: true }).waitFor();
  passed.push('administrator authentication and authorization');

  await page.locator('.admin-sidebar').getByRole('button', { name: /Customers/i }).click();
  await page.getByRole('heading', { name: 'Customer accounts', exact: true }).waitFor();
  const userRow = page.locator('tr').filter({ hasText: userEmail });
  await userRow.waitFor();
  await userRow.getByRole('button', { name: 'Disable' }).click();
  await userRow.getByText('Disabled').waitFor();
  await userRow.getByRole('button', { name: 'Enable' }).click();
  await userRow.getByText('Active').waitFor();
  passed.push('administrator customer access disable and restore');

  if (createdBookingId) {
    await page.locator('.admin-sidebar').getByRole('button', { name: 'Bookings' }).click();
    const bookingRow = page.locator('tr').filter({ hasText: createdBookingId.slice(0, 8).toUpperCase() });
    await bookingRow.waitFor();
    page.once('dialog', (dialog) => dialog.accept());
    await bookingRow.getByRole('button', { name: 'Cancel' }).click();
    await bookingRow.getByText('cancelled').waitFor();
    passed.push('administrator cancels temporary unpaid booking hold');
  }

  await page.locator('.admin-sidebar').getByRole('button', { name: 'Support' }).click();
  await page.getByRole('button', { name: new RegExp(subject) }).click();
  await page.getByText('Customer thread reply for end-to-end verification.').waitFor();
  await page.locator('textarea[name="reply"]').fill('Administrator response to customer support thread.');
  await page.getByRole('button', { name: /Send reply/i }).click();
  await page.getByText('Administrator response to customer support thread.').waitFor();
  await page.getByLabel('Priority').selectOption('high');
  await page.getByLabel('Status').selectOption('in_progress');
  await page.getByLabel('Status').evaluate((select) => {
    if (select.value !== 'in_progress') throw new Error('Support status did not update.');
  });
  passed.push('administrator support response, priority and status management');

  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Delete ticket' }).click();
  await page.getByText('Select a support ticket').waitFor();
  passed.push('administrator support ticket deletion');

  const staleTestTickets = page.getByRole('button', { name: /Customer-admin E2E/ });
  while (await staleTestTickets.count()) {
    await staleTestTickets.first().click();
    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: 'Delete ticket' }).click();
    await page.getByText('Select a support ticket').waitFor();
  }

  console.log(JSON.stringify({ passed, failures }, null, 2));
  if (failures.length) process.exitCode = 1;
} catch (error) {
  // Best-effort cleanup keeps interrupted browser runs from leaving test records behind.
  try {
    const login = await fetch(`${baseURL}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: adminEmail, password }) });
    if (!login.ok) throw new Error(`cleanup admin login failed (${login.status})`);
    const { tokens } = await login.json();
    const headers = { Authorization: `Bearer ${tokens.AccessToken}`, 'Content-Type': 'application/json' };
    if (createdBookingId) await fetch(`${baseURL}/api/bookings/${createdBookingId}/cancel`, { method: 'POST', headers, body: '{}' });
    if (createdSubject) {
      const ticketsResponse = await fetch(`${baseURL}/api/auth/support/tickets?all_tickets=true`, { headers });
      if (ticketsResponse.ok) {
        const tickets = await ticketsResponse.json();
        const ticket = tickets.find((item) => item.subject === createdSubject);
        if (ticket) await fetch(`${baseURL}/api/auth/support/tickets/${ticket.id}`, { method: 'DELETE', headers, body: '{}' });
      }
    }
  } catch (cleanupError) {
    failures.push(`test data cleanup failed: ${cleanupError.message}`);
  }
  console.error(JSON.stringify({ passed, failures, error: error.message }, null, 2));
  process.exitCode = 1;
} finally {
  await browser.close();
}
