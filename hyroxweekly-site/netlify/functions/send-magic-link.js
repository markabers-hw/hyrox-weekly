/**
 * Send Magic Link Email
 * POST /api/send-magic-link
 * Body: { email: string }
 * For existing subscribers to request a new login link
 */

const { createClient } = require('@supabase/supabase-js');
const { Resend } = require('resend');
const crypto = require('crypto');

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY
);

const resend = new Resend(process.env.RESEND_API_KEY);

// Generate magic link token
function generateMagicToken() {
  return crypto.randomBytes(32).toString('hex');
}

// Send magic link email via Resend
async function sendLoginEmail(email, token) {
  const baseUrl = process.env.URL || 'https://hyroxweekly.com';
  const magicLink = `${baseUrl}/auth/verify?token=${token}`;

  try {
    await resend.emails.send({
      from: process.env.EMAIL_FROM || 'Hyrox Weekly <onboarding@resend.dev>',
      to: email,
      subject: 'Your Hyrox Weekly Premium Login Link',
      html: `
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
          <h1 style="color: #1a1a1a; margin-bottom: 24px;">Login to Hyrox Weekly Premium</h1>

          <p style="color: #4a4a4a; font-size: 16px; line-height: 1.6;">
            Click the button below to access your premium content. This link expires in 1 hour.
          </p>

          <a href="${magicLink}" style="display: inline-block; background: #2563eb; color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: 600; margin: 20px 0;">
            Access Premium Content
          </a>

          <p style="color: #6b7280; font-size: 14px; margin-top: 32px;">
            Or copy this link: ${magicLink}
          </p>

          <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 32px 0;">

          <p style="color: #9ca3af; font-size: 12px;">
            If you didn't request this link, you can safely ignore this email.
          </p>
        </div>
      `
    });
    console.log(`Login email sent to ${email}`);
    return true;
  } catch (error) {
    console.error('Failed to send login email:', error);
    return false;
  }
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

  try {
    // Check if subscriber exists and has active subscription
    const { data: subscriber, error } = await supabase
      .from('subscribers')
      .select('id, email, subscription_status')
      .eq('email', email.toLowerCase())
      .single();

    if (error || !subscriber) {
      // Don't reveal if email exists or not for security
      return {
        statusCode: 200,
        body: JSON.stringify({
          message: 'If this email has a premium subscription, a login link will be sent.'
        })
      };
    }

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

    await supabase
      .from('subscribers')
      .update({
        magic_link_token: magicToken,
        magic_link_expires_at: tokenExpiry.toISOString(),
        updated_at: new Date().toISOString()
      })
      .eq('id', subscriber.id);

    // Send login email
    await sendLoginEmail(email, magicToken);

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
  }
};
