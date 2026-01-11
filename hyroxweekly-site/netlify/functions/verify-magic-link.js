/**
 * Verify Magic Link and Set Session
 * GET /api/verify-magic-link?token=xxx
 * Returns: Sets JWT cookie and redirects to premium portal
 */

const { createClient } = require('@supabase/supabase-js');
const jwt = require('jsonwebtoken');

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY
);

exports.handler = async (event) => {
  const { token } = event.queryStringParameters || {};
  const baseUrl = process.env.URL || 'https://hyroxweekly.com';

  if (!token) {
    return {
      statusCode: 302,
      headers: { Location: `${baseUrl}/premium/?error=missing_token` }
    };
  }

  try {
    // Find subscriber with this token
    const { data: subscriber, error } = await supabase
      .from('subscribers')
      .select('id, email, subscription_status, subscription_tier, is_early_bird, early_bird_number')
      .eq('magic_link_token', token)
      .gt('magic_link_expires_at', new Date().toISOString())
      .eq('subscription_status', 'active')
      .single();

    if (error || !subscriber) {
      return {
        statusCode: 302,
        headers: { Location: `${baseUrl}/premium/?error=invalid_token` }
      };
    }

    // Clear the magic link token (one-time use)
    await supabase
      .from('subscribers')
      .update({
        magic_link_token: null,
        magic_link_expires_at: null,
        updated_at: new Date().toISOString()
      })
      .eq('id', subscriber.id);

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
  }
};
