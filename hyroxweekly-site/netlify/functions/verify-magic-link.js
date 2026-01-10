/**
 * Verify Magic Link and Set Session
 * GET /api/verify-magic-link?token=xxx
 * Returns: Sets JWT cookie and redirects to premium portal
 */

const { Pool } = require('pg');
const jwt = require('jsonwebtoken');

const pool = new Pool({
  host: process.env.DB_HOST,
  database: process.env.DB_NAME,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  port: process.env.DB_PORT || 5432,
  ssl: { rejectUnauthorized: false }
});

exports.handler = async (event) => {
  const { token } = event.queryStringParameters || {};
  const baseUrl = process.env.URL || 'https://hyroxweekly.com';

  if (!token) {
    return {
      statusCode: 302,
      headers: { Location: `${baseUrl}/premium/?error=missing_token` }
    };
  }

  const client = await pool.connect();

  try {
    // Find subscriber with this token
    const result = await client.query(`
      SELECT id, email, subscription_status, subscription_tier, is_early_bird, early_bird_number
      FROM subscribers
      WHERE magic_link_token = $1
        AND magic_link_expires_at > CURRENT_TIMESTAMP
        AND subscription_status = 'active'
    `, [token]);

    if (result.rows.length === 0) {
      return {
        statusCode: 302,
        headers: { Location: `${baseUrl}/premium/?error=invalid_token` }
      };
    }

    const subscriber = result.rows[0];

    // Clear the magic link token (one-time use)
    await client.query(`
      UPDATE subscribers
      SET magic_link_token = NULL, magic_link_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
      WHERE id = $1
    `, [subscriber.id]);

    // Create JWT session token (30 days)
    const jwtToken = jwt.sign(
      {
        sub: subscriber.id,
        email: subscriber.email,
        tier: subscriber.subscription_tier,
        earlyBird: subscriber.is_early_bird,
        earlyBirdNumber: subscriber.early_bird_number
      },
      process.env.JWT_SECRET,
      { expiresIn: '30d' }
    );

    // Set cookie and redirect to premium portal
    const cookieOptions = [
      `hwp_session=${jwtToken}`,
      'Path=/',
      'HttpOnly',
      'Secure',
      'SameSite=Strict',
      'Max-Age=2592000' // 30 days
    ].join('; ');

    return {
      statusCode: 302,
      headers: {
        'Set-Cookie': cookieOptions,
        'Location': `${baseUrl}/premium/portal/`
      }
    };

  } catch (error) {
    console.error('Magic link verification error:', error);
    return {
      statusCode: 302,
      headers: { Location: `${baseUrl}/premium/?error=verification_failed` }
    };
  } finally {
    client.release();
  }
};
