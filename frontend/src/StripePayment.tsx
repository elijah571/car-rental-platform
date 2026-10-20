import { useState } from 'react';
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js';
import { loadStripe } from '@stripe/stripe-js';
import { LockKeyhole } from 'lucide-react';

const stripeKey = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || '';
const stripePromise = stripeKey.startsWith('pk_') && !stripeKey.includes('replace_me') ? loadStripe(stripeKey) : null;

export default function StripePayment({ clientSecret, bookingId }: { clientSecret: string; bookingId: string }) {
  if (!stripePromise) return <p className="inline-error">Stripe is not configured. Set the VITE_STRIPE_PUBLISHABLE_KEY value.</p>;
  return <Elements stripe={stripePromise} options={{ clientSecret, appearance: { theme: 'stripe', variables: { colorPrimary: '#119e97', borderRadius: '12px' } } }}><PaymentForm bookingId={bookingId} /></Elements>;
}

function PaymentForm({ bookingId }: { bookingId: string }) {
  const stripe = useStripe();
  const elements = useElements();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  async function pay() {
    if (!stripe || !elements) return;
    setBusy(true);
    setMessage('');
    const result = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: `${window.location.origin}/?payment=return&booking_id=${bookingId}` },
      redirect: 'if_required',
    });
    if (result.error) {
      setMessage(result.error.message || 'Payment could not be completed.');
      setBusy(false);
      return;
    }
    window.location.assign(`/?payment=return&booking_id=${bookingId}`);
  }

  return <div className="stripe-form"><PaymentElement /><button className="btn btn-primary full" disabled={!stripe || busy} onClick={() => void pay()}>{busy ? 'Confirming payment…' : 'Pay securely'} <LockKeyhole size={15} /></button>{message && <p className="inline-error">{message}</p>}</div>;
}
