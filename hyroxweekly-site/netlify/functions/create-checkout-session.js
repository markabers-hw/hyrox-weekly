/**
 * Create Stripe Checkout Session
 * POST /api/create-checkout-session
 * Body: { email: string, priceId: string }
 */

const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

exports.handler = async (event) => {
  // Only allow POST
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  try {
    const { email, priceId } = JSON.parse(event.body);

    if (!email || !priceId) {
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'Email and priceId are required' })
      };
    }

    // Determine success/cancel URLs
    const baseUrl = process.env.URL || 'https://hyroxweekly.com';

    // Create checkout session
    const session = await stripe.checkout.sessions.create({
      customer_email: email,
      payment_method_types: ['card'],
      line_items: [
        {
          price: priceId,
          quantity: 1,
        },
      ],
      mode: 'subscription',
      success_url: `${baseUrl}/premium/success/?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${baseUrl}/premium/`,
      metadata: {
        source: 'hyrox_weekly_premium'
      },
      subscription_data: {
        metadata: {
          source: 'hyrox_weekly_premium'
        }
      }
    });

    return {
      statusCode: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
      body: JSON.stringify({ sessionId: session.id, url: session.url })
    };

  } catch (error) {
    console.error('Checkout session error:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: error.message })
    };
  }
};
