(async function() {
  let config;
  try {
    const res = await fetch('/assets/edition-config.json', { cache: 'no-store' });
    config = await res.json();
  } catch (e) {
    return; // fail open
  }
  const latest = config.latestEdition || 0;
  const freeCount = 3;

  document.querySelectorAll('.archive-item').forEach(function(item) {
    const href = item.getAttribute('href') || '';
    const m = href.match(/edition-(\d+)/);
    if (!m) return;
    const num = parseInt(m[1], 10);
    if (num > latest - freeCount) return; // within free window
    const label = item.querySelector('.archive-item-edition');
    if (!label || label.querySelector('.archive-item-badge')) return;
    const badge = document.createElement('span');
    badge.className = 'archive-item-badge';
    badge.textContent = '🔒 Premium';
    label.appendChild(badge);
  });
})();
