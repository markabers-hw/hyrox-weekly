/**
 * Subscribe Handler
 * POST /api/subscribe
 * Body: { email: string, name?: string }
 * Stores subscriber in Supabase and sends welcome email via Resend.
 */

const { createClient } = require('@supabase/supabase-js');
const { Resend } = require('resend');

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY
);

const resend = new Resend(process.env.RESEND_API_KEY);

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

async function sendWelcomeEmail(email, name) {
  const greeting = name ? `Hi ${name},` : 'Hi there,';

  try {
    await resend.emails.send({
      from: process.env.EMAIL_FROM || 'Hyrox Weekly <newsletter@hyroxweekly.com>',
      to: email,
      subject: 'Welcome to Hyrox Weekly!',
      html: `
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
          <h1 style="color: #1a1a1a; margin-bottom: 24px;">Welcome to Hyrox Weekly!</h1>

          <p style="color: #4a4a4a; font-size: 16px; line-height: 1.6;">
            ${greeting}
          </p>

          <p style="color: #4a4a4a; font-size: 16px; line-height: 1.6;">
            You're now on the list. Every week you'll get the best Hyrox videos, podcasts, training tips, and community discussions — all in one email.
          </p>

          <p style="color: #4a4a4a; font-size: 16px; line-height: 1.6;">
            Check out the latest editions while you wait:
          </p>

          <a href="https://hyroxweekly.com/archive" style="display: inline-block; background: #2563eb; color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: 600; margin: 20px 0;">
            Browse the Archive
          </a>

          <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 32px 0;">

          <p style="color: #9ca3af; font-size: 12px;">
            Hyrox Weekly — Everything Hyrox, Every Week.
          </p>
        </div>
      `
    });
    console.log(`Welcome email sent to ${email}`);
    return true;
  } catch (error) {
    console.error('Failed to send welcome email:', error);
    return false;
  }
}

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers: CORS_HEADERS, body: '' };
  }

  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers: CORS_HEADERS, body: 'Method Not Allowed' };
  }

  let body;
  try {
    body = JSON.parse(event.body || '{}');
  } catch {
    return {
      statusCode: 400,
      headers: CORS_HEADERS,
      body: JSON.stringify({ error: 'Invalid JSON' })
    };
  }

  const email = (body.email || '').trim().toLowerCase();
  const name = (body.name || '').trim();

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return {
      statusCode: 400,
      headers: CORS_HEADERS,
      body: JSON.stringify({ error: 'A valid email is required' })
    };
  }

  try {
    // Upsert: re-activate if previously unsubscribed, otherwise insert
    const { data, error } = await supabase
      .from('newsletter_subscribers')
      .upsert(
        {
          email,
          name: name || undefined,
          status: 'active',
          source: 'website',
          subscribed_at: new Date().toISOString(),
          unsubscribed_at: null,
        },
        { onConflict: 'email' }
      )
      .select();

    if (error) {
      console.error('Supabase upsert error:', error);
      return {
        statusCode: 500,
        headers: CORS_HEADERS,
        body: JSON.stringify({ error: 'Failed to subscribe. Please try again.' })
      };
    }

    // Send welcome email (don't block response on failure)
    await sendWelcomeEmail(email, name);

    return {
      statusCode: 200,
      headers: CORS_HEADERS,
      body: JSON.stringify({ success: true, message: "You're subscribed!" })
    };
  } catch (error) {
    console.error('Subscribe error:', error);
    return {
      statusCode: 500,
      headers: CORS_HEADERS,
      body: JSON.stringify({ error: 'Something went wrong. Please try again.' })
    };
  }
};
