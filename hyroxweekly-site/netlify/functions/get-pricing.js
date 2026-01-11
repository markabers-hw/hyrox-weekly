/**
 * Get Current Pricing
 * GET /api/get-pricing
 * Returns current prices (early bird vs regular) and availability
 */

const { createClient } = require('@supabase/supabase-js');

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_ANON_KEY
);

exports.handler = async (event) => {
  let isEarlyBirdAvailable = true;
  let earlyBirdRemaining = 100;
  const earlyBirdLimit = 100;

  try {
    // Get early bird count from database
    const { count, error } = await supabase
      .from('subscribers')
      .select('*', { count: 'exact', head: true })
      .eq('is_early_bird', true)
      .eq('subscription_status', 'active');

    if (!error) {
      const earlyBirdCount = count || 0;
      earlyBirdRemaining = Math.max(0, earlyBirdLimit - earlyBirdCount);
      isEarlyBirdAvailable = earlyBirdRemaining > 0;
    } else {
      console.error('Database error:', error.message);
    }
  } catch (error) {
    console.error('Error fetching early bird count:', error.message);
  }

  const pricing = {
    isEarlyBirdAvailable,
    earlyBirdRemaining,
    earlyBirdLimit,
    prices: {
      monthly: {
        regular: 500,
        earlyBird: 400,
        current: isEarlyBirdAvailable ? 400 : 500,
        priceId: isEarlyBirdAvailable
          ? process.env.STRIPE_EARLY_BIRD_MONTHLY_PRICE_ID
          : process.env.STRIPE_MONTHLY_PRICE_ID
      },
      yearly: {
        regular: 3900,
        earlyBird: 3000,
        current: isEarlyBirdAvailable ? 3000 : 3900,
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
      'Cache-Control': 'public, max-age=60'
    },
    body: JSON.stringify(pricing)
  };
};
