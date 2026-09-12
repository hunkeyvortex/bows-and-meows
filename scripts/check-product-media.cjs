// Local layout regression: no live requests or product data changes.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage();
    const root = path.resolve(__dirname, '..');
    const css = ['style.css', 'commerce-features.css', 'commerce-polish.css', 'brand-system.css']
      .map(name => fs.readFileSync(path.join(root, 'store/static/store', name), 'utf8')).join('\n');
    for (const width of [320, 375, 390, 430, 600, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      const cards = [[600, 1200], [1200, 600], [800, 800]].map(([w, h]) => {
        const image = 'data:image/svg+xml,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><rect width="100%" height="100%" fill="coral"/></svg>`);
        return `<article class="v2-product-card"><div class="v2-product-media"><a href="#"><img src="${image}" alt="Test product"></a></div><div class="v2-product-body"><h3>Product name</h3><strong>₹889.00</strong><button>Add to cart</button></div></article>`;
      }).join('');
      await page.setContent(`<style>${css}</style><section class="v2-section"><div class="v2-shell"><div class="v2-products-grid">${cards}</div></div></section>`);
      await page.locator('img').evaluateAll(images => Promise.all(images.map(img => img.decode())));
      const bounds = await page.locator('.v2-product-card').evaluateAll(cards => cards.map(card => {
        const img = card.querySelector('img').getBoundingClientRect();
        const media = card.querySelector('.v2-product-media').getBoundingClientRect();
        const body = card.querySelector('.v2-product-body').getBoundingClientRect();
        return { inside: img.left >= media.left && img.right <= media.right && img.top >= media.top && img.bottom <= media.bottom, noOverlap: img.bottom <= body.top, height: media.height };
      }));
      assert(bounds.every(b => b.inside && b.noOverlap), `Image overflow at ${width}px`);
      assert(bounds.every(b => b.height === bounds[0].height), `Unequal media heights at ${width}px`);
      console.log(`PASS ${width}px: portrait, landscape and square images contained`);
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
