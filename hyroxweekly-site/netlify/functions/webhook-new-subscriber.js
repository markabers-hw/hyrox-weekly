const NTFY_TOPIC = process.env.NTFY_TOPIC || "hyroxweekly-subs-x7k9m2";
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
