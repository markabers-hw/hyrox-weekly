/**
 * Send Magic Link Email
 * POST /api/send-magic-link
 * Body: { email: string }
 * For existing subscribers to request a new login link
 */

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

exports.handler = async (event) => {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  const { email } = JSON.parse(event.body || '{}');

  if (!email) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: 'Email is required' })
    };
  }

  const client = await pool.connect();

  try {
    // Check if subscriber exists and has active subscription
    const result = await client.query(`
      SELECT id, email, subscription_status
      FROM subscribers
      WHERE email = $1
    `, [email.toLowerCase()]);

    if (result.rows.length === 0) {
      // Don't reveal if email exists or not for security
      return {
        statusCode: 200,
        body: JSON.stringify({
          message: 'If this email has a premium subscription, a login link will be sent.'
        })
      };
    }

    const subscriber = result.rows[0];

    if (subscriber.subscription_status !== 'active') {
      return {
        statusCode: 200,
        body: JSON.stringify({
          message: 'If this email has a premium subscription, a login link will be sent.'
        })
      };
    }

    // Generate new magic link token
    const magicToken = generateMagicToken();
    const tokenExpiry = new Date(Date.now() + 60 * 60 * 1000); // 1 hour

    await client.query(`
      UPDATE subscribers
      SET magic_link_token = $1, magic_link_expires_at = $2, updated_at = CURRENT_TIMESTAMP
      WHERE id = $3
    `, [magicToken, tokenExpiry, subscriber.id]);

    // Send email (log for now - integrate with email service)
    const baseUrl = process.env.URL || 'https://hyroxweekly.com';
    const magicLink = `${baseUrl}/auth/verify/?token=${magicToken}`;

    console.log(`Magic link for ${email}: ${magicLink}`);

    // TODO: Send via Beehiiv transactional or SendGrid
    // Example with SendGrid:
    // await sendgrid.send({
    //   to: email,
    //   from: 'premium@hyroxweekly.com',
    //   subject: 'Your Hyrox Weekly Premium Login Link',
    //   html: `<p>Click here to access your premium content: <a href="${magicLink}">Login</a></p>`
    // });

    return {
      statusCode: 200,
      body: JSON.stringify({
        message: 'If this email has a premium subscription, a login link will be sent.'
      })
    };

  } catch (error) {
    console.error('Send magic link error:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to process request' })
    };
  } finally {
    client.release();
  }
};
