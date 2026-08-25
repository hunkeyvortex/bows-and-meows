(() => {
  const shell = document.querySelector('#bm-quick-view');
  const backdrop = document.querySelector('.bm-quick-backdrop');
  if (!shell || !backdrop) return;
  const content = shell.querySelector('[data-quick-content]');
  let opener = null;
  const close = () => { shell.hidden = true; backdrop.hidden = true; document.body.classList.remove('bm-modal-open'); content.innerHTML = ''; opener?.focus(); };
  const bind = () => {
    shell.querySelectorAll('input[name="variant"]').forEach(input => input.addEventListener('change', () => {
      shell.querySelector('[data-quick-price]').textContent = `₹${input.dataset.price}`;
      const mrp = shell.querySelector('[data-quick-mrp]'); if (mrp) mrp.textContent = input.dataset.mrp ? `₹${input.dataset.mrp}` : '';
      shell.querySelector('[data-quick-stock]').textContent = `${input.dataset.stock} available`;
    }));
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
    if (payload.pincode) localStorage.setItem('bm_delivery_pincode', payload.pincode);
  }));
  document.querySelectorAll('[data-delivery-form] input[name="pincode"]').forEach(input => { input.value ||= localStorage.getItem('bm_delivery_pincode') || ''; });
})();
