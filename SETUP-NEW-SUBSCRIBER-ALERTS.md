# Hyrox Weekly — New Subscriber Phone Alerts

## Goal
Get a push notification on your phone every time someone subscribes to the Hyrox Weekly newsletter (free or premium).

## Architecture
Same pattern as Week+ signup alerts:
- **Supabase Database Webhook** fires on INSERT into subscriber tables
- **Netlify Function** receives the webhook, formats the message
- **ntfy.sh** delivers the push notification to your phone

## Prerequisites
- ntfy app installed on iPhone (same app used for Week+ alerts)
- Subscribe to topic: `<NTFY_TOPIC — see 1Password>` (or choose your own secret topic name)

---

## Step 1: Create the Netlify Function

Create file: `hyroxweekly-site/netlify/functions/webhook-new-subscriber.js`

```javascript
const NTFY_TOPIC = process.env.NTFY_TOPIC || "<NTFY_TOPIC — see 1Password>";
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || "";

exports.handler = async (event) => {
  // Only accept POST
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method not allowed" };
  }

  // Verify webhook secret
  const authHeader = event.headers["authorization"] || "";
  if (WEBHOOK_SECRET && authHeader !== `Bearer ${WEBHOOK_SECRET}`) {
    return { statusCode: 401, body: "Unauthorized" };
  }

  try {
    const body = JSON.parse(event.body);
    const record = body.record;
    const table = body.table;

    let title, message;

    if (table === "newsletter_subscribers") {
      // Free newsletter signup
      const email = record?.email || "unknown";
      const name = record?.name || "";
      const source = record?.source || "website";
      title = "New Hyrox Weekly subscriber!";
      message = `${email}${name ? ` (${name})` : ""}\nSource: ${source}`;
    } else if (table === "subscribers") {
      // Premium subscriber
      const email = record?.email || "unknown";
      const tier = record?.subscription_tier || "unknown";
      const isEarlyBird = record?.is_early_bird ? " (Early Bird!)" : "";
      title = "New Premium subscriber!";
      message = `${email}\nTier: ${tier}${isEarlyBird}`;
    } else {
      title = "New subscriber activity";
      message = JSON.stringify(record).slice(0, 200);
    }

    // Send push notification via ntfy
    await fetch(`https://ntfy.sh/${NTFY_TOPIC}`, {
      method: "POST",
      headers: {
        Title: title,
        Tags: table === "subscribers" ? "money_mouth_face,star" : "tada,newspaper",
      },
      body: message,
    });

    return { statusCode: 200, body: JSON.stringify({ ok: true }) };
  } catch (err) {
    console.error("[webhook-new-subscriber] error:", err);
    return { statusCode: 500, body: "Failed" };
  }
};
```

## Step 2: Add Environment Variables to Netlify

In Netlify dashboard → Site settings → Environment variables, add:

| Name | Value |
|---|---|
| `NTFY_TOPIC` | `<NTFY_TOPIC — see 1Password>` |
| `WEBHOOK_SECRET` | `<WEBHOOK_SECRET — see 1Password>` |

Deploy the site so the new function is live.

## Step 3: Create Supabase Database Webhooks

In the Supabase dashboard for the Hyrox Weekly project (ref: `ksqrakczmecdbzxwsvea`):

### Webhook 1: Free newsletter subscribers

1. Go to **Database → Webhooks** → **Create a new hook**
2. Configure:
   - **Name:** `new-free-subscriber`
   - **Schema:** `public`
   - **Table:** `newsletter_subscribers`
   - **Events:** INSERT only
   - **Type:** HTTP Request
   - **Method:** POST
   - **URL:** `https://hyroxweekly.com/.netlify/functions/webhook-new-subscriber`
   - **Headers:** `Authorization: Bearer <WEBHOOK_SECRET — see 1Password>`
3. Click **Create**

### Webhook 2: Premium subscribers

1. Create another hook:
   - **Name:** `new-premium-subscriber`
   - **Schema:** `public`
   - **Table:** `subscribers`
   - **Events:** INSERT only
   - **Type:** HTTP Request
   - **Method:** POST
   - **URL:** `https://hyroxweekly.com/.netlify/functions/webhook-new-subscriber`
   - **Headers:** `Authorization: Bearer <WEBHOOK_SECRET — see 1Password>`
2. Click **Create**

## Step 4: Subscribe to the ntfy topic

In the ntfy app on your iPhone:
1. Tap "+" → subscribe to: `<NTFY_TOPIC — see 1Password>`
2. You'll now receive alerts from BOTH Hyrox Weekly and Week+ on the same app, different topics

## What you'll see on your phone

**Free subscriber:**
> **New Hyrox Weekly subscriber!**
> jane@example.com (Jane)
> Source: website

**Premium subscriber:**
> **New Premium subscriber!**
> jane@example.com
> Tier: yearly (Early Bird!)

## Supabase project details (for reference)

- **Project ref:** ksqrakczmecdbzxwsvea
- **URL:** https://ksqrakczmecdbzxwsvea.supabase.co
- **Region:** us-west-1
- **Free subscriber table:** `newsletter_subscribers` (columns: email, name, status, source, subscribed_at)
- **Premium subscriber table:** `subscribers` (columns: email, stripe_customer_id, subscription_status, subscription_tier, is_early_bird)

## Testing

1. After setup, go to hyroxweekly.com and subscribe with a test email
2. You should get a push notification within seconds
3. Check Supabase → Database → Webhooks → click the hook → "Recent deliveries" to debug if needed
