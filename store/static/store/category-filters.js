(function () {
    "use strict";

    const trigger = document.querySelector(".category-filter-trigger");
    const sheet = document.querySelector("#category-filter-sheet");
    const backdrop = document.querySelector(".category-filter-backdrop");
    const closeButton = sheet && sheet.querySelector(".filter-sheet-close");

    if (!trigger || !sheet || !backdrop || !closeButton) return;

    let lastFocused = null;

    function setOpen(open) {
        const mobile = window.innerWidth <= 768;
        sheet.classList.toggle("is-open", open);
        backdrop.classList.toggle("is-open", open);
        sheet.setAttribute("aria-hidden", String(mobile && !open));
        sheet.setAttribute("role", mobile ? "dialog" : "search");
        if (mobile) sheet.setAttribute("aria-modal", "true");
        else sheet.removeAttribute("aria-modal");
        trigger.setAttribute("aria-expanded", String(open));
        document.body.classList.toggle("bm-filter-sheet-open", open);

        if (open) {
            lastFocused = document.activeElement;
            window.requestAnimationFrame(() => closeButton.focus());
        } else if (lastFocused) {
            lastFocused.focus();
        }
    }

    trigger.addEventListener("click", () => setOpen(true));
    closeButton.addEventListener("click", () => setOpen(false));
    backdrop.addEventListener("click", () => setOpen(false));

    document.addEventListener("keydown", (event) => {
        if (!sheet.classList.contains("is-open")) return;
        if (event.key === "Escape") {
            event.preventDefault();
            setOpen(false);
            return;
        }
        if (event.key !== "Tab") return;

        const focusable = Array.from(sheet.querySelectorAll("button, input, select, a[href]"))
            .filter((element) => !element.disabled && element.offsetParent !== null);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });

    window.addEventListener("resize", () => {
        if (window.innerWidth > 768 && sheet.classList.contains("is-open")) setOpen(false);
    });

    setOpen(false);
}());
