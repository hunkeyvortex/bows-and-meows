(() => {
    "use strict";

    const scriptUrl = document.currentScript && document.currentScript.src;
    const assetBase = scriptUrl ? new URL("sounds/", scriptUrl) : "/static/store/sounds/";
    const soundFiles = {
        dog: new URL("dog-bark.ogg", assetBase).href,
        cat: new URL("cat-meow.ogg", assetBase).href,
    };

    function playAnimalSound(kind) {
        const audio = new Audio(soundFiles[kind] || soundFiles.dog);
        audio.preload = "auto";
        audio.volume = kind === "cat" ? 0.46 : 0.42;
        const playback = audio.play();
        if (playback && typeof playback.catch === "function") playback.catch(() => {});
        return audio;
    }

    document.addEventListener("submit", (event) => {
        const form = event.target.closest("form[data-cart-sound]");
        if (!form || form.dataset.soundPlayed === "true") return;

        event.preventDefault();
        form.dataset.soundPlayed = "true";
        const submitter = event.submitter;
        if (submitter) submitter.disabled = true;

        try {
            playAnimalSound(form.dataset.cartSound);
        } catch (_) {
            // Audio is decorative; shopping must continue if playback is blocked.
        }

        const delay = form.dataset.cartSound === "cat" ? 820 : 1050;
        window.setTimeout(() => form.submit(), delay);
    });
})();
