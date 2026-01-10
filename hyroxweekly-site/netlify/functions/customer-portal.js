/**
 * Create Stripe Customer Portal Session
 * POST /api/customer-portal
 * Allows subscribers to manage their billing
 */

const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
const jwt = require('jsonwebtoken');
const { Pool } = require('pg');

const pool = new Pool({
  host: process.env.DB_HOST,
  database: process.env.DB_NAME,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  port: process.env.DB_PORT || 5432,
  ssl: { rejectUnauthorized: false }
});

function parseCookies(cookieHeader) {
  const cookies = {};
  if (!cookieHeader) return cookies;

  cookieHeader.split(';').forEach(cookie => {
    const [name, value] = cookie.trim().split('=');
    cookies[name] = value;
  });

  return cookies;
}

exports.handler = async (event) => {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  const cookies = parseCookies(event.headers.cookie);
  const token = cookies['hwp_session'];
  const baseUrl = process.env.URL || 'https://hyroxweekly.com';

  if (!token) {
    return {
      statusCode: 401,
      body: JSON.stringify({ error: 'Not authenticated' })
    };
  }

  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    const subscriberId = decoded.sub;

    const client = await pool.connect();

    try {
      // Get Stripe customer ID
      const result = await client.query(`
        SELECT stripe_customer_id FROM subscribers WHERE id = $1
      `, [subscriberId]);

      if (result.rows.length === 0 || !result.rows[0].stripe_customer_id) {
        return {
          statusCode: 400,
          body: JSON.stringify({ error: 'No billing account found' })
        };
      }

      const customerId = result.rows[0].stripe_customer_id;

      // Create portal session
      const portalSession = await stripe.billingPortal.sessions.create({
        customer: customerId,
        return_url: `${baseUrl}/premium/portal/`,
      });

      return {
        statusCode: 200,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: portalSession.url })
      };

    } finally {
      client.release();
    }

  } catch (error) {
    console.error('Customer portal error:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to create portal session' })
    };
  }
};
