/**
 * Stripe Webhook Handler
 * POST /api/stripe-webhook
 * Handles: checkout.session.completed, customer.subscription.updated/deleted
 */

const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
const { Pool } = require('pg');
const crypto = require('crypto');

const pool = new Pool({
  host: process.env.DB_HOST,
  database: process.env.DB_NAME,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  port: process.env.DB_PORT || 5432,
  ssl: { rejectUnauthorized: false }
});

// Generate magic link token
function generateMagicToken() {
  return crypto.randomBytes(32).toString('hex');
}

// Send magic link email (via Beehiiv or other service)
async function sendMagicLinkEmail(email, token) {
  const baseUrl = process.env.URL || 'https://hyroxweekly.com';
  const magicLink = `${baseUrl}/auth/verify/?token=${token}`;

  // For now, log the magic link - integrate with email service later
  console.log(`Magic link for ${email}: ${magicLink}`);

  // TODO: Integrate with Beehiiv transactional email or SendGrid
  // For MVP, the webhook could trigger a Beehiiv automation

  return true;
}

// Get early bird status
async function checkEarlyBirdAvailable(client) {
  const result = await client.query(`
    SELECT
      (SELECT value::INTEGER FROM premium_settings WHERE key = 'early_bird_limit') as limit_val,
      COUNT(*) as current_count
    FROM subscribers
    WHERE is_early_bird = true AND subscription_status = 'active'
  `);

  const { limit_val, current_count } = result.rows[0];
  return parseInt(current_count) < parseInt(limit_val);
}

// Get next early bird number
async function getNextEarlyBirdNumber(client) {
  const result = await client.query(`
    SELECT COALESCE(MAX(early_bird_number), 0) + 1 as next_number
    FROM subscribers WHERE is_early_bird = true
  `);
  return result.rows[0].next_number;
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

  const client = await pool.connect();

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
        const isEarlyBird = await checkEarlyBirdAvailable(client);
        let earlyBirdNumber = null;

        if (isEarlyBird) {
          earlyBirdNumber = await getNextEarlyBirdNumber(client);
        }

        // Generate magic link token
        const magicToken = generateMagicToken();
        const tokenExpiry = new Date(Date.now() + 24 * 60 * 60 * 1000); // 24 hours

        // Insert or update subscriber
        await client.query(`
          INSERT INTO subscribers (
            email, stripe_customer_id, stripe_subscription_id,
            subscription_status, subscription_tier, price_cents,
            is_early_bird, early_bird_number,
            magic_link_token, magic_link_expires_at,
            current_period_start, current_period_end
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
          ON CONFLICT (email) DO UPDATE SET
            stripe_customer_id = EXCLUDED.stripe_customer_id,
            stripe_subscription_id = EXCLUDED.stripe_subscription_id,
            subscription_status = EXCLUDED.subscription_status,
            subscription_tier = EXCLUDED.subscription_tier,
            price_cents = EXCLUDED.price_cents,
            is_early_bird = COALESCE(subscribers.is_early_bird, EXCLUDED.is_early_bird),
            early_bird_number = COALESCE(subscribers.early_bird_number, EXCLUDED.early_bird_number),
            magic_link_token = EXCLUDED.magic_link_token,
            magic_link_expires_at = EXCLUDED.magic_link_expires_at,
            current_period_start = EXCLUDED.current_period_start,
            current_period_end = EXCLUDED.current_period_end,
            updated_at = CURRENT_TIMESTAMP
        `, [
          email, customerId, subscriptionId,
          'active', tier, priceCents,
          isEarlyBird, earlyBirdNumber,
          magicToken, tokenExpiry,
          new Date(subscription.current_period_start * 1000),
          new Date(subscription.current_period_end * 1000)
        ]);

        // Send magic link email
        await sendMagicLinkEmail(email, magicToken);

        console.log(`New subscriber: ${email} (${tier}, early bird: ${isEarlyBird})`);
        break;
      }

      case 'customer.subscription.updated': {
        const subscription = stripeEvent.data.object;
        const customerId = subscription.customer;

        await client.query(`
          UPDATE subscribers SET
            subscription_status = $1,
            current_period_start = $2,
            current_period_end = $3,
            updated_at = CURRENT_TIMESTAMP
          WHERE stripe_customer_id = $4
        `, [
          subscription.status,
          new Date(subscription.current_period_start * 1000),
          new Date(subscription.current_period_end * 1000),
          customerId
        ]);

        console.log(`Subscription updated for customer: ${customerId}`);
        break;
      }

      case 'customer.subscription.deleted': {
        const subscription = stripeEvent.data.object;
        const customerId = subscription.customer;

        await client.query(`
          UPDATE subscribers SET
            subscription_status = 'cancelled',
            cancelled_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
          WHERE stripe_customer_id = $1
        `, [customerId]);

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
  } finally {
    client.release();
  }
};
