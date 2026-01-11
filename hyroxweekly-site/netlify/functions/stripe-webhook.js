/**
 * Stripe Webhook Handler
 * POST /api/stripe-webhook
 * Handles: checkout.session.completed, customer.subscription.updated/deleted
 */

const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
const { createClient } = require('@supabase/supabase-js');
const { Resend } = require('resend');
const crypto = require('crypto');

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY
);

const resend = new Resend(process.env.RESEND_API_KEY);

// Beehiiv API configuration
const BEEHIIV_API_KEY = process.env.BEEHIIV_API_KEY;
const BEEHIIV_PUBLICATION_ID = process.env.BEEHIIV_PUBLICATION_ID;
const BEEHIIV_API_URL = 'https://api.beehiiv.com/v2';

// Tag a subscriber as premium in Beehiiv
async function tagBeehiivSubscriber(email, isPremium) {
  if (!BEEHIIV_API_KEY || !BEEHIIV_PUBLICATION_ID) {
    console.log('Beehiiv not configured, skipping tag update');
    return;
  }

  try {
    // First, find the subscriber by email
    const searchResponse = await fetch(
      `${BEEHIIV_API_URL}/publications/${BEEHIIV_PUBLICATION_ID}/subscriptions?email=${encodeURIComponent(email)}`,
      {
        headers: {
          'Authorization': `Bearer ${BEEHIIV_API_KEY}`,
          'Content-Type': 'application/json'
        }
      }
    );

    if (!searchResponse.ok) {
      console.error('Failed to search Beehiiv subscriber:', await searchResponse.text());
      return;
    }

    const searchData = await searchResponse.json();
    const subscriber = searchData.data?.[0];

    if (!subscriber) {
      console.log(`Subscriber ${email} not found in Beehiiv`);
      return;
    }

    // Update the subscriber with premium tag
    const currentTags = subscriber.custom_fields || [];
    const premiumTag = 'premium';

    let newTags;
    if (isPremium) {
      // Add premium tag if not present
      newTags = currentTags.includes(premiumTag) ? currentTags : [...currentTags, premiumTag];
    } else {
      // Remove premium tag
      newTags = currentTags.filter(tag => tag !== premiumTag);
    }

    // Update subscriber tags via PATCH
    const updateResponse = await fetch(
      `${BEEHIIV_API_URL}/publications/${BEEHIIV_PUBLICATION_ID}/subscriptions/${subscriber.id}`,
      {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${BEEHIIV_API_KEY}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          custom_fields: [{ name: 'subscription_status', value: isPremium ? 'premium' : 'free' }]
        })
      }
    );

    if (updateResponse.ok) {
      console.log(`Beehiiv subscriber ${email} tagged as ${isPremium ? 'premium' : 'free'}`);
    } else {
      console.error('Failed to update Beehiiv subscriber:', await updateResponse.text());
    }
  } catch (error) {
    console.error('Error syncing with Beehiiv:', error);
  }
}

// Generate magic link token
function generateMagicToken() {
  return crypto.randomBytes(32).toString('hex');
}

// Send magic link email via Resend
async function sendMagicLinkEmail(email, token, earlyBirdNumber) {
  const baseUrl = process.env.URL || 'https://hyroxweekly.com';
  const magicLink = `${baseUrl}/auth/verify?token=${token}`;

  const earlyBirdText = earlyBirdNumber
    ? `You're Early Bird #${earlyBirdNumber} - thanks for being an early supporter!`
    : '';

  try {
    await resend.emails.send({
      from: process.env.EMAIL_FROM || 'Hyrox Weekly <onboarding@resend.dev>',
      to: email,
      subject: 'Welcome to Hyrox Weekly Premium! Access Your Account',
      html: `
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
          <h1 style="color: #1a1a1a; margin-bottom: 24px;">Welcome to Hyrox Weekly Premium!</h1>

          ${earlyBirdText ? `<p style="background: #fef3c7; padding: 12px; border-radius: 8px; color: #92400e;">${earlyBirdText}</p>` : ''}

          <p style="color: #4a4a4a; font-size: 16px; line-height: 1.6;">
            Click the button below to access your premium content. This link expires in 24 hours.
          </p>

          <a href="${magicLink}" style="display: inline-block; background: #2563eb; color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: 600; margin: 20px 0;">
            Access Premium Content
          </a>

          <p style="color: #6b7280; font-size: 14px; margin-top: 32px;">
            Or copy this link: ${magicLink}
          </p>

          <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 32px 0;">

          <p style="color: #9ca3af; font-size: 12px;">
            Hyrox Weekly Premium - Your edge in Hyrox training
          </p>
        </div>
      `
    });
    console.log(`Magic link email sent to ${email}`);
    return true;
  } catch (error) {
    console.error('Failed to send magic link email:', error);
    return false;
  }
}

// Get early bird status
async function checkEarlyBirdAvailable() {
  const { count, error } = await supabase
    .from('subscribers')
    .select('*', { count: 'exact', head: true })
    .eq('is_early_bird', true)
    .eq('subscription_status', 'active');

  if (error) {
    console.error('Error checking early bird:', error);
    return true; // Default to available if error
  }

  return (count || 0) < 100;
}

// Get next early bird number
async function getNextEarlyBirdNumber() {
  const { data, error } = await supabase
    .from('subscribers')
    .select('early_bird_number')
    .eq('is_early_bird', true)
    .order('early_bird_number', { ascending: false })
    .limit(1);

  if (error || !data || data.length === 0) {
    return 1;
  }

  return (data[0].early_bird_number || 0) + 1;
}

exports.handler = async (event) => {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  const sig = event.headers['stripe-signature'];
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

  let stripeEvent;

  try {
    stripeEvent = stripe.webhooks.constructEvent(
      event.body,
      sig,
      webhookSecret
    );
  } catch (err) {
    console.error('Webhook signature verification failed:', err.message);
    return { statusCode: 400, body: `Webhook Error: ${err.message}` };
  }

  try {
    switch (stripeEvent.type) {
      case 'checkout.session.completed': {
        const session = stripeEvent.data.object;
        const email = session.customer_email;
        const customerId = session.customer;
        const subscriptionId = session.subscription;

        // Get subscription details
        const subscription = await stripe.subscriptions.retrieve(subscriptionId);
        const priceId = subscription.items.data[0].price.id;
        const priceCents = subscription.items.data[0].price.unit_amount;

        // Determine tier based on billing interval
        const interval = subscription.items.data[0].price.recurring.interval;
        const tier = interval === 'year' ? 'yearly' : 'monthly';

        // Check if early bird pricing
        const isEarlyBird = await checkEarlyBirdAvailable();
        let earlyBirdNumber = null;

        if (isEarlyBird) {
          earlyBirdNumber = await getNextEarlyBirdNumber();
        }

        // Generate magic link token
        const magicToken = generateMagicToken();
        const tokenExpiry = new Date(Date.now() + 24 * 60 * 60 * 1000); // 24 hours

        // Check if subscriber already exists
        const { data: existing } = await supabase
          .from('subscribers')
          .select('id, is_early_bird, early_bird_number')
          .eq('email', email.toLowerCase())
          .single();

        if (existing) {
          // Update existing subscriber - use their original early bird number
          earlyBirdNumber = existing.early_bird_number;

          const { error } = await supabase
            .from('subscribers')
            .update({
              stripe_customer_id: customerId,
              stripe_subscription_id: subscriptionId,
              subscription_status: 'active',
              subscription_tier: tier,
              price_cents: priceCents,
              magic_link_token: magicToken,
              magic_link_expires_at: tokenExpiry.toISOString(),
              current_period_start: new Date(subscription.current_period_start * 1000).toISOString(),
              current_period_end: new Date(subscription.current_period_end * 1000).toISOString(),
              updated_at: new Date().toISOString()
            })
            .eq('id', existing.id);

          if (error) console.error('Update error:', error);
          console.log(`Updated existing subscriber: ${email}`);
        } else {
          // Insert new subscriber
          const { error } = await supabase
            .from('subscribers')
            .insert({
              email: email.toLowerCase(),
              stripe_customer_id: customerId,
              stripe_subscription_id: subscriptionId,
              subscription_status: 'active',
              subscription_tier: tier,
              price_cents: priceCents,
              is_early_bird: isEarlyBird,
              early_bird_number: earlyBirdNumber,
              magic_link_token: magicToken,
              magic_link_expires_at: tokenExpiry.toISOString(),
              current_period_start: new Date(subscription.current_period_start * 1000).toISOString(),
              current_period_end: new Date(subscription.current_period_end * 1000).toISOString()
            });

          if (error) console.error('Insert error:', error);
          console.log(`Created new subscriber: ${email}`);
        }

        // Send magic link email
        console.log(`Sending magic link email to ${email}...`);
        const emailSent = await sendMagicLinkEmail(email, magicToken, earlyBirdNumber);
        console.log(`Email send result: ${emailSent}`);

        // Sync with Beehiiv - tag as premium
        await tagBeehiivSubscriber(email, true);

        console.log(`Subscriber processed: ${email} (${tier}, early bird #${earlyBirdNumber})`);
        break;
      }

      case 'customer.subscription.updated': {
        const subscription = stripeEvent.data.object;
        const customerId = subscription.customer;

        const { error } = await supabase
          .from('subscribers')
          .update({
            subscription_status: subscription.status,
            current_period_start: new Date(subscription.current_period_start * 1000).toISOString(),
            current_period_end: new Date(subscription.current_period_end * 1000).toISOString(),
            updated_at: new Date().toISOString()
          })
          .eq('stripe_customer_id', customerId);

        if (error) console.error('Update error:', error);
        console.log(`Subscription updated for customer: ${customerId}`);
        break;
      }

      case 'customer.subscription.deleted': {
        const subscription = stripeEvent.data.object;
        const customerId = subscription.customer;

        // Get subscriber email before updating
        const { data: subscriberData } = await supabase
          .from('subscribers')
          .select('email')
          .eq('stripe_customer_id', customerId)
          .single();

        const { error } = await supabase
          .from('subscribers')
          .update({
            subscription_status: 'cancelled',
            cancelled_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
          })
          .eq('stripe_customer_id', customerId);

        if (error) console.error('Update error:', error);

        // Sync with Beehiiv - remove premium tag
        if (subscriberData?.email) {
          await tagBeehiivSubscriber(subscriberData.email, false);
        }

        console.log(`Subscription cancelled for customer: ${customerId}`);
        break;
      }

      default:
        console.log(`Unhandled event type: ${stripeEvent.type}`);
    }

    return { statusCode: 200, body: JSON.stringify({ received: true }) };

  } catch (error) {
    console.error('Webhook processing error:', error);
    return { statusCode: 500, body: JSON.stringify({ error: error.message }) };
  }
};
