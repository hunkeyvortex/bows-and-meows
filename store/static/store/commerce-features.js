(() => {
  const shell = document.querySelector('#bm-quick-view');
  const backdrop = document.querySelector('.bm-quick-backdrop');
  if (!shell || !backdrop) return;
  const content = shell.querySelector('[data-quick-content]');
  let opener = null;
  const close = () => { shell.hidden = true; backdrop.hidden = true; document.body.classList.remove('bm-modal-open'); content.innerHTML = ''; opener?.focus(); };
  const bind = () => {
    const syncVariant = input => {
      const price = shell.querySelector('[data-quick-price]');
      if (price) price.textContent = `₹${Number(input.dataset.price).toFixed(2)}`;

      const mrp = shell.querySelector('[data-quick-mrp]');
      if (mrp) {
        mrp.hidden = !input.dataset.mrp;
        mrp.textContent = input.dataset.mrp ? `₹${Number(input.dataset.mrp).toFixed(2)}` : '';
      }

      const stock = shell.querySelector('[data-quick-stock]');
      if (stock) stock.textContent = `${input.dataset.stock} available`;

      const image = shell.querySelector('[data-quick-image]');
      if (image && input.dataset.image) {
        image.src = input.dataset.image;
        image.alt = `${shell.querySelector('.bm-quick-copy h2')?.textContent.trim() || 'Product'} — ${input.dataset.size}`;
      }
    };

    const inputs = shell.querySelectorAll('input[name="variant"]');
    inputs.forEach(input => input.addEventListener('change', () => syncVariant(input)));
    const selected = shell.querySelector('input[name="variant"]:checked');
    if (selected) syncVariant(selected);
  };
  document.addEventListener('click', async event => {
    const trigger = event.target.closest('.bm-quick-trigger');
    if (!trigger) return;
    opener = trigger; trigger.disabled = true;
    try { const response = await fetch(trigger.dataset.quickUrl, {headers: {'X-Requested-With': 'XMLHttpRequest'}}); if (!response.ok) throw new Error(); content.innerHTML = await response.text(); shell.hidden = false; backdrop.hidden = false; document.body.classList.add('bm-modal-open'); bind(); shell.querySelector('button, a, input')?.focus(); }
    catch (_) { window.location.assign(trigger.dataset.quickUrl.replace('/quick-view/', '/product/')); }
    finally { trigger.disabled = false; }
  });
  document.querySelectorAll('[data-quick-close]').forEach(node => node.addEventListener('click', close));
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !shell.hidden) close(); });

  document.querySelectorAll('[data-delivery-form]').forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault(); const result = form.querySelector('[data-delivery-result]'); const data = new FormData(form);
    const response = await fetch(form.action, {method: 'POST', headers: {'X-CSRFToken': data.get('csrfmiddlewaretoken')}, body: data});
    const payload = await response.json();
    result.className = `bm-delivery-result ${payload.available ? 'ok' : 'error'}`;
    result.textContent = payload.available ? `Delivery to ${payload.city}: ${payload.min_days}–${payload.max_days} business days. ${payload.cod_available ? 'COD available.' : 'Prepaid only.'}` : (payload.error || payload.message);
    if (payload.pincode) {
      localStorage.setItem('bm_delivery_pincode', payload.pincode);
      const checkoutPincode = document.querySelector('[data-checkout-pincode]');
      if (checkoutPincode) checkoutPincode.value = payload.pincode;
    }
  }));
  document.querySelectorAll('[data-delivery-form] input[name="pincode"]').forEach(input => { input.value ||= localStorage.getItem('bm_delivery_pincode') || ''; });
})();
