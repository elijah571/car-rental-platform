import { chromium } from 'playwright-core';

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173';
const email = process.env.E2E_ADMIN_EMAIL;
const password = process.env.E2E_ADMIN_PASSWORD;
const executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH || '/usr/bin/google-chrome';

if (!email || !password) {
  throw new Error('Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD to a local platform-admin account.');
}

const browser = await chromium.launch({
  headless: true,
  executablePath,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const page = await browser.newPage();
page.setDefaultTimeout(15_000);
const passed = [];
const failures = [];
page.on('pageerror', (error) => failures.push(error.message));
page.on('response', (response) => {
  if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`);
});

try {
  await page.goto(baseURL, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: /Your next ride/i }).waitFor();
  await page.getByRole('button', { name: /Explore all cars/i }).click();
  await page.getByRole('button', { name: /View details/i }).first().click();
  await page.locator('.detail-layout').waitFor();
  passed.push('public fleet pages');

  await page.getByRole('button', { name: /Account/i }).click();
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByText('You are signed in.').waitFor();
  await page.getByRole('button', { name: 'My bookings' }).click();
  await page.getByRole('heading', { name: 'My bookings', exact: true }).waitFor();
  await page.waitForLoadState('networkidle');
  passed.push('customer bookings page');

  await page.getByRole('button', { name: new RegExp(email.split('@')[0], 'i') }).click();
  await page.getByRole('button', { name: /Operations workspace/i }).click();
  await page.getByRole('heading', { name: 'Operations overview', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Customers' }).click();
  await page.getByRole('heading', { name: 'Customer accounts', exact: true }).waitFor();
  await page.getByText(email).waitFor();
  await page.waitForLoadState('networkidle');
  passed.push('admin authorization and customer list');

  await page.locator('.admin-sidebar').getByRole('button', { name: /Vehicles/i }).click();
  await page.getByRole('button', { name: /Add vehicle/i }).click();
  const plate = `E2E-${Date.now()}`;
  const vehicle = { make: 'BrowserTest', model: 'Temporary', year: '2025', color: 'Silver', seats: '5', registration_number: plate, hourly_rate: '100' };
  for (const [field, value] of Object.entries(vehicle)) await page.locator(`input[name="${field}"]`).fill(value);
  await page.getByRole('button', { name: 'Save vehicle' }).click();
  const vehicleRow = page.locator('tr').filter({ hasText: plate });
  await vehicleRow.waitFor();
  await vehicleRow.getByRole('button', { name: 'Edit' }).click();
  await page.locator('input[name="color"]').fill('Blue');
  await page.getByRole('button', { name: 'Save changes' }).click();
  await vehicleRow.getByText(/Blue/).waitFor();
  await vehicleRow.getByRole('button', { name: 'Delete' }).click();
  await vehicleRow.getByText('retired').waitFor();
  passed.push('admin vehicle create/read/update/delete');

  await page.locator('.admin-brand').click();
  await page.getByRole('button', { name: 'Help & support' }).click();
  const subject = `Browser support test ${Date.now()}`;
  await page.locator('input[name="subject"]').fill(subject);
  await page.locator('textarea[name="message"]').fill('Temporary browser smoke test ticket.');
  await page.getByRole('button', { name: 'Open support ticket' }).click();
  await page.getByRole('heading', { name: subject, exact: true }).waitFor();

  await page.getByRole('button', { name: new RegExp(email.split('@')[0], 'i') }).click();
  await page.getByRole('button', { name: /Operations workspace/i }).click();
  await page.getByRole('button', { name: 'Support' }).click();
  await page.getByRole('button', { name: new RegExp(subject) }).click();
  await page.getByLabel('Priority').selectOption('high');
  await page.locator('textarea[name="reply"]').fill('Support reply from browser smoke test.');
  await page.getByRole('button', { name: /Send reply/i }).click();
  await page.getByText('Support reply from browser smoke test.').waitFor();

  await page.locator('.admin-brand').click();
  await page.getByRole('button', { name: 'Help & support' }).click();
  await page.getByRole('button', { name: new RegExp(subject) }).click();
  await page.getByRole('button', { name: 'Reply to this message' }).last().click();
  await page.locator('textarea[name="reply"]').fill('Thread follow-up from browser smoke test.');
  await page.getByRole('button', { name: 'Send reply' }).click();
  await page.getByText('Thread follow-up from browser smoke test.').waitFor();

  await page.getByRole('button', { name: new RegExp(email.split('@')[0], 'i') }).click();
  await page.getByRole('button', { name: /Operations workspace/i }).click();
  await page.getByRole('button', { name: 'Support' }).click();
  await page.getByRole('button', { name: new RegExp(subject) }).click();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Delete ticket' }).click();
  await page.getByText('Select a support ticket').waitFor();
  passed.push('support ticket and threaded chat CRUD');

  await page.getByRole('button', { name: 'Bookings' }).click();
  await page.getByRole('heading', { name: 'Booking management', exact: true }).waitFor();
  passed.push('admin booking operations page');

  console.log(JSON.stringify({ passed, failures }, null, 2));
  if (failures.length) process.exitCode = 1;
} catch (error) {
  console.error(JSON.stringify({ passed, failures, error: error.message }, null, 2));
  process.exitCode = 1;
} finally {
  await browser.close();
}
