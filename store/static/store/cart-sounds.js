(() => {
    "use strict";

    const scriptUrl =
        document.currentScript &&
        document.currentScript.src;

    const assetBase = scriptUrl
        ? new URL("sounds/", scriptUrl)
        : "/static/store/sounds/";

    const soundFiles = {
        dog: new URL(
            "dog-bark.ogg",
            assetBase
        ).href,

        cat: new URL(
            "cat-meow.ogg",
            assetBase
        ).href,
    };

    function playAnimalSound(kind) {
        const audio = new Audio(
            soundFiles[kind] || soundFiles.dog
        );

        audio.preload = "auto";

        audio.volume =
            kind === "cat"
                ? 0.46
                : 0.42;

        const playback = audio.play();

        if (
            playback &&
            typeof playback.catch === "function"
        ) {
            playback.catch(() => {});
        }

        return audio;
    }

    const activeSubmissions =
        new WeakSet();

    function resetCartSoundState() {
        document
            .querySelectorAll(
                "form[data-cart-sound]"
            )
            .forEach((form) => {

                activeSubmissions.delete(form);

                form
                    .querySelectorAll(
                        "button:disabled, input[type='submit']:disabled"
                    )
                    .forEach((control) => {
                        control.disabled = false;
                    });
            });
    }

    document.addEventListener(
        "submit",
        (event) => {

            const form =
                event.target.closest(
                    "form[data-cart-sound]"
                );

            if (!form) return;

            /*
             * Prevent accidental double-click
             * during the SAME submission only.
             */
            if (
                activeSubmissions.has(form)
            ) {
                event.preventDefault();
                return;
            }

            event.preventDefault();

            activeSubmissions.add(form);

            const submitter =
                event.submitter;

            if (submitter) {
                submitter.disabled = true;
            }

            try {
                playAnimalSound(
                    form.dataset.cartSound
                );
            } catch (_) {
                /*
                 * Sound is decorative.
                 * Cart submission must continue.
                 */
            }

            const delay =
                form.dataset.cartSound === "cat"
                    ? 820
                    : 1050;

            window.setTimeout(
                () => {

                    /*
                     * IMPORTANT:
                     * Unlock BEFORE navigation.
                     *
                     * Mobile browsers may restore
                     * the page from bfcache after
                     * pressing Back.
                     */
                    activeSubmissions.delete(
                        form
                    );

                    if (submitter) {
                        submitter.disabled = false;
                    }

                    try {
                        HTMLFormElement
                            .prototype
                            .submit
                            .call(form);
                    } catch (_) {

                        activeSubmissions.delete(
                            form
                        );

                        if (submitter) {
                            submitter.disabled =
                                false;
                        }
                    }
                },
                delay
            );
        }
    );

    /*
     * Critical fix for:
     *
     * Product
     * → Add variant 1
     * → Cart
     * → Browser Back
     * → Select variant 2
     * → Add again
     *
     * Browsers often restore the previous
     * DOM state from the back-forward cache.
     */
    window.addEventListener(
        "pageshow",
        resetCartSoundState
    );
})();