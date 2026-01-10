/**
 * Get Current Pricing
 * GET /api/get-pricing
 * Returns current prices (early bird vs regular) and availability
 */

const { Pool } = require('pg');

const pool = new Pool({
  host: process.env.DB_HOST,
  database: process.env.DB_NAME,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  port: process.env.DB_PORT || 5432,
  ssl: { rejectUnauthorized: false }
});

exports.handler = async (event) => {
  const client = await pool.connect();

  try {
    // Get settings and early bird count
    const settingsResult = await client.query(`
      SELECT key, value FROM premium_settings
    `);

    const settings = {};
    settingsResult.rows.forEach(row => {
      settings[row.key] = row.value;
    });

    // Get early bird stats
    const statsResult = await client.query(`
      SELECT * FROM subscriber_stats
    `);

    const stats = statsResult.rows[0] || {
      total_active: 0,
      monthly_count: 0,
      yearly_count: 0,
      early_bird_count: 0,
      early_bird_remaining: parseInt(settings.early_bird_limit || 100)
    };

    const isEarlyBirdAvailable = parseInt(stats.early_bird_remaining) > 0;

    // Return pricing info
    const pricing = {
      isEarlyBirdAvailable,
      earlyBirdRemaining: parseInt(stats.early_bird_remaining),
      earlyBirdLimit: parseInt(settings.early_bird_limit || 100),
      prices: {
        monthly: {
          regular: parseInt(settings.monthly_price_cents || 500),
          earlyBird: parseInt(settings.early_bird_monthly_price_cents || 400),
          current: isEarlyBirdAvailable
            ? parseInt(settings.early_bird_monthly_price_cents || 400)
            : parseInt(settings.monthly_price_cents || 500),
          // Stripe Price IDs - set these in env vars
          priceId: isEarlyBirdAvailable
            ? process.env.STRIPE_EARLY_BIRD_MONTHLY_PRICE_ID
            : process.env.STRIPE_MONTHLY_PRICE_ID
        },
        yearly: {
          regular: parseInt(settings.yearly_price_cents || 3900),
          earlyBird: parseInt(settings.early_bird_yearly_price_cents || 3000),
          current: isEarlyBirdAvailable
            ? parseInt(settings.early_bird_yearly_price_cents || 3000)
            : parseInt(settings.yearly_price_cents || 3900),
          priceId: isEarlyBirdAvailable
            ? process.env.STRIPE_EARLY_BIRD_YEARLY_PRICE_ID
            : process.env.STRIPE_YEARLY_PRICE_ID
        }
      }
    };

    return {
      statusCode: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'public, max-age=60' // Cache for 1 minute
      },
      body: JSON.stringify(pricing)
    };

  } catch (error) {
    console.error('Get pricing error:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to get pricing' })
    };
  } finally {
    client.release();
  }
};
