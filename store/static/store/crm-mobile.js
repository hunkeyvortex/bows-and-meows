const menuButton = document.querySelector('.crm-menu-toggle');
const backdrop = document.querySelector('.crm-menu-backdrop');
const sidebar = document.querySelector('.crm-sidebar');
const mobile = window.matchMedia('(max-width: 760px)');
function setMenu(open) {
    document.body.classList.toggle('crm-menu-open', open);
    menuButton.setAttribute('aria-expanded', String(open));
    menuButton.textContent = open ? '✕ Close' : '☰ Menu';
    backdrop.hidden = !open;
    sidebar.inert = mobile.matches && !open;
}
menuButton.addEventListener('click', () => setMenu(menuButton.getAttribute('aria-expanded') !== 'true'));
backdrop.addEventListener('click', () => setMenu(false));
document.addEventListener('keydown', event => {
    if (event.key === 'Escape') { setMenu(false); menuButton.focus(); }
});
mobile.addEventListener('change', () => setMenu(false));
setMenu(false);
document.querySelectorAll('.crm-table').forEach(table => {
    const headings = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
    if (!headings.length) return;
    table.classList.add('crm-mobile-cards');
    table.querySelectorAll('tbody tr').forEach(row => {
        [...row.cells].forEach((cell, index) => {
            if (cell.colSpan === 1) cell.dataset.label = headings[index] || '';
        });
    });
});
