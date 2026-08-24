(async function() {
  // TEMPORARY (2026-07-04): paywall disabled during catch-up so all prior editions
  // are free. Flip PAYWALL_DISABLED back to false (and redeploy) to re-enable gating.
  var PAYWALL_DISABLED = true;
  if (PAYWALL_DISABLED) return;

  // Extract edition number from URL (e.g., /archive/edition-14-2026-03-16.html → 14)
  var match = window.location.pathname.match(/edition-(\d+)/);
  if (!match) return;
  var editionNumber = parseInt(match[1], 10);

  // Fetch the latest edition number
  var config;
  try {
    var res = await fetch('/assets/edition-config.json');
    config = await res.json();
  } catch (e) {
    return; // If config fails, don't gate (fail open)
  }

  var latest = config.latestEdition || 0;
  var freeCount = 3;

  // If this edition is within the free window, no gate needed
  if (editionNumber > latest - freeCount) return;

  // Check if user has premium access
  try {
    var premRes = await fetch('/api/check-premium');
    if (premRes.ok) {
      var data = await premRes.json();
      if (data.isPremium) return; // Premium user, no gate
    }
  } catch (e) {
    // If check fails, still gate
  }

  // Gate the content
  var article = document.querySelector('.newsletter-container');
  if (!article) return;

  // Blur everything after the intro
  var sections = article.querySelectorAll('.section, .subscribe-box, .archive-nav');
  sections.forEach(function(el) {
    el.style.filter = 'blur(8px)';
    el.style.pointerEvents = 'none';
    el.style.userSelect = 'none';
  });

  // Create overlay
  var overlay = document.createElement('div');
  overlay.style.cssText = 'position:relative;background:#fff;border-radius:12px;padding:48px 32px;text-align:center;max-width:560px;margin:-60px auto 40px;box-shadow:0 4px 24px rgba(0,0,0,0.12);z-index:10;';
  overlay.innerHTML = '<div style="font-size:48px;margin-bottom:16px;">🔒</div>'
    + '<h2 style="font-size:24px;font-weight:800;margin-bottom:12px;color:#1a1a1a;">This edition is for Premium members</h2>'
    + '<p style="color:#666;font-size:16px;line-height:1.6;margin-bottom:24px;">The 3 most recent editions are always free. Unlock the full archive and more with Hyrox Weekly Premium.</p>'
    + '<a href="/premium" style="display:inline-block;background:#CC5500;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;letter-spacing:0.5px;">Get Premium Access</a>'
    + '<p style="margin-top:16px;"><a href="/premium" style="color:#666;font-size:13px;text-decoration:none;">Already a member? <strong>Log in</strong></a></p>';

  // Insert overlay after the intro section
  var intro = article.querySelector('.intro');
  if (intro) {
    intro.parentNode.insertBefore(overlay, intro.nextSibling);
  } else {
    article.insertBefore(overlay, article.firstChild);
  }
})();
