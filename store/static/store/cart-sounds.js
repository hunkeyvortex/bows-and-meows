(() => {
    "use strict";

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;

    let context;

    function audioContext() {
        if (!context) context = new AudioContextClass();
        if (context.state === "suspended") context.resume();
        return context;
    }

    function outputBus(ctx, volume = 0.45) {
        const compressor = ctx.createDynamicsCompressor();
        const gain = ctx.createGain();
        compressor.threshold.value = -20;
        compressor.knee.value = 16;
        compressor.ratio.value = 7;
        gain.gain.value = volume;
        compressor.connect(gain).connect(ctx.destination);
        return compressor;
    }

    function noiseBuffer(ctx, seconds) {
        const buffer = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * seconds), ctx.sampleRate);
        const samples = buffer.getChannelData(0);
        let previous = 0;
        for (let index = 0; index < samples.length; index += 1) {
            const white = Math.random() * 2 - 1;
            previous = previous * 0.72 + white * 0.28;
            samples[index] = previous;
        }
        return buffer;
    }

    function barkPulse(ctx, destination, start, strength) {
        const duration = 0.25;
        const noise = ctx.createBufferSource();
        const throat = ctx.createOscillator();
        const barkFilter = ctx.createBiquadFilter();
        const throatFilter = ctx.createBiquadFilter();
        const envelope = ctx.createGain();

        noise.buffer = noiseBuffer(ctx, duration);
        barkFilter.type = "bandpass";
        barkFilter.frequency.setValueAtTime(720, start);
        barkFilter.frequency.exponentialRampToValueAtTime(300, start + duration);
        barkFilter.Q.value = 1.8;

        throat.type = "sawtooth";
        throat.frequency.setValueAtTime(155, start);
        throat.frequency.exponentialRampToValueAtTime(72, start + duration);
        throatFilter.type = "lowpass";
        throatFilter.frequency.value = 520;

        envelope.gain.setValueAtTime(0.0001, start);
        envelope.gain.exponentialRampToValueAtTime(strength, start + 0.018);
        envelope.gain.exponentialRampToValueAtTime(strength * 0.45, start + 0.09);
        envelope.gain.exponentialRampToValueAtTime(0.0001, start + duration);

        noise.connect(barkFilter).connect(envelope);
        throat.connect(throatFilter).connect(envelope);
        envelope.connect(destination);
        noise.start(start);
        noise.stop(start + duration);
        throat.start(start);
        throat.stop(start + duration);
    }

    function woof(ctx) {
        const bus = outputBus(ctx, 0.58);
        const now = ctx.currentTime + 0.015;
        barkPulse(ctx, bus, now, 0.95);
        barkPulse(ctx, bus, now + 0.31, 0.72);
    }

    function meow(ctx) {
        const bus = outputBus(ctx, 0.38);
        const now = ctx.currentTime + 0.015;
        const duration = 0.68;
        const voice = ctx.createOscillator();
        const harmonic = ctx.createOscillator();
        const vibrato = ctx.createOscillator();
        const vibratoDepth = ctx.createGain();
        const formant = ctx.createBiquadFilter();
        const envelope = ctx.createGain();

        voice.type = "sawtooth";
        voice.frequency.setValueAtTime(430, now);
        voice.frequency.exponentialRampToValueAtTime(690, now + 0.19);
        voice.frequency.exponentialRampToValueAtTime(590, now + 0.43);
        voice.frequency.exponentialRampToValueAtTime(330, now + duration);

        harmonic.type = "triangle";
        harmonic.frequency.setValueAtTime(860, now);
        harmonic.frequency.exponentialRampToValueAtTime(1380, now + 0.19);
        harmonic.frequency.exponentialRampToValueAtTime(660, now + duration);

        vibrato.frequency.value = 15;
        vibratoDepth.gain.setValueAtTime(0, now);
        vibratoDepth.gain.linearRampToValueAtTime(22, now + 0.18);
        vibratoDepth.gain.linearRampToValueAtTime(8, now + duration);
        vibrato.connect(vibratoDepth).connect(voice.frequency);

        formant.type = "bandpass";
        formant.frequency.setValueAtTime(1150, now);
        formant.frequency.exponentialRampToValueAtTime(780, now + duration);
        formant.Q.value = 2.3;

        envelope.gain.setValueAtTime(0.0001, now);
        envelope.gain.exponentialRampToValueAtTime(0.62, now + 0.08);
        envelope.gain.setValueAtTime(0.55, now + 0.38);
        envelope.gain.exponentialRampToValueAtTime(0.0001, now + duration);

        voice.connect(formant);
        harmonic.connect(formant);
        formant.connect(envelope).connect(bus);
        voice.start(now);
        harmonic.start(now);
        vibrato.start(now);
        voice.stop(now + duration);
        harmonic.stop(now + duration);
        vibrato.stop(now + duration);
    }

    document.addEventListener("submit", (event) => {
        const form = event.target.closest("form[data-cart-sound]");
        if (!form || form.dataset.soundPlayed === "true") return;

        event.preventDefault();
        form.dataset.soundPlayed = "true";
        const submitter = event.submitter;
        if (submitter) submitter.disabled = true;

        try {
            const ctx = audioContext();
            form.dataset.cartSound === "cat" ? meow(ctx) : woof(ctx);
        } catch (_) {
            // Audio is decorative; cart actions must always continue.
        }

        const delay = form.dataset.cartSound === "cat" ? 720 : 650;
        window.setTimeout(() => form.submit(), delay);
    });
})();
