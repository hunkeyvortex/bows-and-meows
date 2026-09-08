(() => {
  const form = document.querySelector('[data-suggestions-url]');
  if (!form) return;
  const input = form.querySelector('input[name="q"]');
  const panel = form.querySelector('.mobile-search-results');
  const status = form.querySelector('[role="status"]');
  const mobile = matchMedia('(max-width: 900px)');
  let timer, controller, version = 0;
  input.setAttribute('aria-controls', panel.id);
  input.setAttribute('aria-expanded', 'false');
  function close() {
    clearTimeout(timer); controller?.abort(); version++;
    panel.hidden = true; input.setAttribute('aria-expanded', 'false'); status.textContent = '';
  }
  function link(name, url, kind) {
    const a = document.createElement('a'); a.href = url;
    const label = document.createElement('span'); label.className = 'suggestion-label'; label.textContent = name;
    if (kind) { const small = document.createElement('small'); small.textContent = kind; label.append(small); }
    a.append(label); return a;
  }
  function search() {
    close();
    const query = input.value.trim();
    if (!mobile.matches || query.length < 2) return;
    const current = version;
    timer = setTimeout(async () => {
      controller = new AbortController();
      try {
        const url = new URL(form.dataset.suggestionsUrl, location.origin); url.searchParams.set('q', query);
        const response = await fetch(url, {signal: controller.signal});
        if (!response.ok) return;
        const data = await response.json();
        if (version !== current || !mobile.matches) return;
        panel.replaceChildren();
        data.brands.forEach(b => panel.append(link(b.name, b.url, 'Brand')));
        data.products.forEach(p => {
          const a = link(p.name, p.url);
          if (p.image) { const img = document.createElement('img'); img.src = p.image; img.alt = ''; img.onerror = () => img.remove(); a.prepend(img); }
          const price = document.createElement('span'); price.className = 'suggestion-price';
          price.textContent = '₹' + Number(p.price).toLocaleString('en-IN', {maximumFractionDigits:2}); a.append(price); panel.append(a);
        });
        const all = new URL(form.action); all.searchParams.set('q', query);
        const footer = link(`View all results for “${query}”`, all.href); footer.className = 'suggestion-all'; panel.append(footer);
        panel.hidden = false; input.setAttribute('aria-expanded', 'true');
        status.textContent = `${data.products.length} product suggestions, ${data.brands.length} brand suggestions.`;
      } catch (_) { /* Normal search remains available on network failure. */ }
    }, 250);
  }
  input.addEventListener('input', search);
  input.addEventListener('focus', search);
  form.addEventListener('submit', close);
  mobile.addEventListener('change', close);
  document.addEventListener('pointerdown', e => { if (!form.contains(e.target)) close(); });
  form.addEventListener('focusout', e => { if (!form.contains(e.relatedTarget)) close(); });
  form.addEventListener('keydown', e => {
    if (e.key === 'Escape') { input.focus(); close(); return; }
    if (panel.hidden || !['ArrowDown', 'ArrowUp'].includes(e.key)) return;
    e.preventDefault(); const links = [...panel.querySelectorAll('a')];
    const index = links.indexOf(document.activeElement);
    links[(index + (e.key === 'ArrowDown' ? 1 : links.length - 1) + links.length) % links.length]?.focus();
  });
})();
