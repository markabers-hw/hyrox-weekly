/* Hyrox Weekly page-view beacon. Cookieless; sends only the page path, referrer and query string to /api/track. */
(function () {
  try {
    // Respect Do Not Track / Global Privacy Control, and skip pages the browser is only prerendering.
    if (navigator.doNotTrack === '1' || navigator.globalPrivacyControl) return;
    if (document.visibilityState === 'prerender') return;

    var body = JSON.stringify({
      path: location.pathname,
      referrer: document.referrer,
      search: location.search
    });

    if (navigator.sendBeacon) {
      // text/plain keeps this a "simple" request, so the browser skips a CORS preflight.
      navigator.sendBeacon('/api/track', new Blob([body], { type: 'text/plain' }));
    } else {
      fetch('/api/track', { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: body, keepalive: true });
    }
  } catch (e) { /* tracking must never break a page */ }
})();
