(() => {
    const opener = document.querySelector("[data-category-open]");
    const sheet = document.querySelector("#bm-category-sheet");
    const backdrop = document.querySelector(".bm-category-sheet-backdrop");
    if (!opener || !sheet || !backdrop) return;

    const closeButtons = document.querySelectorAll("[data-category-close]");
    let lastFocus = null;

    const openSheet = () => {
        lastFocus = document.activeElement;
        sheet.hidden = false;
        backdrop.hidden = false;
        requestAnimationFrame(() => {
            document.body.classList.add("bm-category-sheet-open");
            opener.setAttribute("aria-expanded", "true");
            sheet.querySelector("[data-category-close]")?.focus();
        });
    };

    const closeSheet = () => {
        document.body.classList.remove("bm-category-sheet-open");
        opener.setAttribute("aria-expanded", "false");
        window.setTimeout(() => {
            sheet.hidden = true;
            backdrop.hidden = true;
        }, 220);
        lastFocus?.focus();
    };

    opener.addEventListener("click", openSheet);
    closeButtons.forEach((button) => button.addEventListener("click", closeSheet));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && document.body.classList.contains("bm-category-sheet-open")) closeSheet();
    });
})();
