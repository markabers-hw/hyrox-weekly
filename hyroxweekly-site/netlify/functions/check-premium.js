/**
 * Check Premium Status
 * GET /api/check-premium
 * Returns user's premium status from JWT cookie
 */

const jwt = require('jsonwebtoken');

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
  const cookies = parseCookies(event.headers.cookie);
  const token = cookies['hwp_session'];

  // Add CORS headers for API usage
  const headers = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': process.env.URL || 'https://hyroxweekly.com',
    'Access-Control-Allow-Credentials': 'true'
  };

  if (!token) {
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        isPremium: false,
        message: 'No session found'
      })
    };
  }

  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        isPremium: true,
        email: decoded.email,
        tier: decoded.tier,
        isEarlyBird: decoded.earlyBird,
        earlyBirdNumber: decoded.earlyBirdNumber,
        expiresAt: new Date(decoded.exp * 1000).toISOString()
      })
    };

  } catch (error) {
    // Token invalid or expired
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        isPremium: false,
        message: 'Session expired'
      })
    };
  }
};
