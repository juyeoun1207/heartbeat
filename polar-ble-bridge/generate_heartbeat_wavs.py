#!/usr/bin/env python3
"""
Generates three calibrated, realistic one-shot heartbeat ("Lub-Dub") .wav files
at 48 kHz / 16-bit PCM for the VR Heartbeat Biofeedback Study.

All three variants have:
- Zero leading silence (S1 onset starts immediately at t = 0.000s for exact R-peak lock)
- Total duration = 0.360s (safe up to 165 BPM without overlap)
- Smooth micro-fades to avoid digital clicks

Variants:
1. Heartbeat_1_Internal_Deep.wav
   - Warm, muffled interoceptive body resonance (simulates hearing/feeling one's own heart inside the chest/inner ear).
2. Heartbeat_2_Stethoscope_Real.wav
   - Authentic acoustic stethoscope recording profile (distinct S1 mitral/tricuspid closure and crisp S2 aortic/pulmonary valve snap; optimized for Meta Quest 3S speakers).
3. Heartbeat_3_SubThump_Multimodal.wav
   - Deep physical sub-bass chest thump with rich upper-bass harmonics, designed to pair with Quest Touch Plus haptic vibrations.
"""

import math
import os
import random
import struct
import wave

SAMPLE_RATE = 48000
DURATION_SEC = 0.360
NUM_SAMPLES = int(SAMPLE_RATE * DURATION_SEC)


def lowpass_filter(samples, cutoff_hz, sample_rate=SAMPLE_RATE, passes=2):
    """Simple cascaded 1-pole RC low-pass filter for organic tissue damping."""
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / sample_rate
    alpha = dt / (rc + dt)
    out = list(samples)
    for _ in range(passes):
        prev = 0.0
        for i in range(len(out)):
            prev = prev + alpha * (out[i] - prev)
            out[i] = prev
    return out


def highpass_filter(samples, cutoff_hz, sample_rate=SAMPLE_RATE):
    """Simple 1-pole RC high-pass filter to remove DC offset."""
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / sample_rate
    alpha = rc / (rc + dt)
    out = [0.0] * len(samples)
    prev_in = 0.0
    prev_out = 0.0
    for i, x in enumerate(samples):
        prev_out = alpha * (prev_out + x - prev_in)
        prev_in = x
        out[i] = prev_out
    return out


def normalize_and_save(filepath, samples, target_peak=0.92):
    """Normalizes float samples to target_peak and writes 16-bit PCM WAV."""
    peak = max(abs(x) for x in samples) or 1.0
    scale = target_peak / peak

    # Apply 4ms fade-out at the very end to guarantee zero trailing click
    fade_samples = int(0.004 * SAMPLE_RATE)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for i, s in enumerate(samples):
            val = s * scale
            if i >= len(samples) - fade_samples:
                val *= (len(samples) - 1 - i) / fade_samples
            val = max(-1.0, min(1.0, val))
            frames.extend(struct.pack("<h", int(val * 32767.0)))
        wf.writeframes(frames)


def generate_variant_1_internal_deep():
    """
    Variant 1: Interoceptive / Internal Body Resonance ("Im eigenen Körper").
    Models bone/tissue conduction: soft downward pitch-glide on S1 and S2,
    filtered blood-flow turbulence, warm low-pass roll-off at 150 Hz.
    """
    random.seed(42)
    raw = [0.0] * NUM_SAMPLES
    noise_buf = [random.uniform(-1.0, 1.0) for _ in range(NUM_SAMPLES)]
    filtered_noise = lowpass_filter(noise_buf, cutoff_hz=110.0, passes=3)

    phase1 = 0.0
    phase2 = 0.0

    for i in range(NUM_SAMPLES):
        t = i / SAMPLE_RATE
        val = 0.0

        # S1 ("Lub"): 0.000s to 0.135s (Mitral + Tricuspid closure + blood turbulence)
        if t < 0.135:
            # Fast attack (8ms), smooth exponential tissue decay
            attack = min(1.0, t / 0.006)
            env = attack * math.sin((t / 0.135) * math.pi) * math.exp(-t * 19.0)
            # Pitch glides down from 68 Hz to 44 Hz as ventricular wall tenses
            freq1 = 44.0 + 24.0 * math.exp(-t * 35.0)
            phase1 += 2.0 * math.pi * freq1 / SAMPLE_RATE

            fundamental = math.sin(phase1)
            second_harm = 0.38 * math.sin(2.0 * phase1 + 0.3)
            third_harm = 0.12 * math.sin(3.0 * phase1)
            turbulence = 0.22 * filtered_noise[i]

            val += env * (fundamental + second_harm + third_harm + turbulence)

        # S2 ("Dub"): 0.185s to 0.295s (Aortic + Pulmonary closure, shorter & slightly higher)
        if 0.185 <= t < 0.295:
            t2 = t - 0.185
            attack2 = min(1.0, t2 / 0.005)
            env2 = attack2 * math.sin((t2 / 0.110) * math.pi) * math.exp(-t2 * 25.0)
            freq2 = 54.0 + 28.0 * math.exp(-t2 * 45.0)
            phase2 += 2.0 * math.pi * freq2 / SAMPLE_RATE

            fundamental2 = math.sin(phase2)
            second_harm2 = 0.42 * math.sin(2.0 * phase2 + 0.5)
            turbulence2 = 0.18 * filtered_noise[i]

            val += 0.72 * env2 * (fundamental2 + second_harm2 + turbulence2)

        raw[i] = val

    out = highpass_filter(raw, cutoff_hz=25.0)
    out = lowpass_filter(out, cutoff_hz=155.0, passes=2)
    return out


def generate_variant_2_stethoscope_real():
    """
    Variant 2: Clinical Stethoscope Auscultation ("Echtes Stethoskop / Quest 3S Optimiert").
    Models the acoustic membrane of a stethoscope including the realistic physiological
    split of M1/T1 in S1 and A2/P2 in S2, plus clear 90-220 Hz valve transients for Quest 3S speakers.
    """
    random.seed(108)
    raw = [0.0] * NUM_SAMPLES
    noise_buf = [random.uniform(-1.0, 1.0) for _ in range(NUM_SAMPLES)]
    valve_noise = lowpass_filter(highpass_filter(noise_buf, 60.0), cutoff_hz=260.0, passes=2)

    def gabor_valve_component(t, t0, f0, f_drop, tau, amp, harm_ratio):
        dt = t - t0
        if dt < 0.0 or dt > 0.130:
            return 0.0
        attack = min(1.0, dt / 0.004)
        env = attack * (dt / tau) * math.exp(1.0 - dt / tau)
        inst_f = f0 - f_drop * (1.0 - math.exp(-dt * 30.0))
        sig = (
            math.sin(2.0 * math.pi * inst_f * dt)
            + harm_ratio * math.sin(2.0 * math.pi * (inst_f * 1.95) * dt + 0.4)
            + (harm_ratio * 0.45) * math.sin(2.0 * math.pi * (inst_f * 2.85) * dt)
        )
        return amp * env * sig

    for i in range(NUM_SAMPLES):
        t = i / SAMPLE_RATE
        val = 0.0

        # S1 ("Lub"): M1 (Mitral at 0.000s) + T1 (Tricuspid at 0.018s)
        m1 = gabor_valve_component(t, 0.000, f0=78.0, f_drop=22.0, tau=0.018, amp=1.00, harm_ratio=0.55)
        t1 = gabor_valve_component(t, 0.018, f0=68.0, f_drop=18.0, tau=0.022, amp=0.65, harm_ratio=0.45)
        if t < 0.120:
            s1_noise_env = math.sin((t / 0.120) * math.pi) * math.exp(-t * 22.0)
            val += m1 + t1 + 0.25 * s1_noise_env * valve_noise[i]

        # S2 ("Dub"): A2 (Aortic at 0.195s) + P2 (Pulmonary at 0.212s) - crisper valve snap
        a2 = gabor_valve_component(t, 0.195, f0=98.0, f_drop=25.0, tau=0.014, amp=0.82, harm_ratio=0.65)
        p2 = gabor_valve_component(t, 0.212, f0=86.0, f_drop=20.0, tau=0.016, amp=0.50, harm_ratio=0.50)
        if 0.195 <= t < 0.300:
            t2 = t - 0.195
            s2_noise_env = math.sin((t2 / 0.105) * math.pi) * math.exp(-t2 * 28.0)
            val += a2 + p2 + 0.20 * s2_noise_env * valve_noise[i]

        raw[i] = val

    out = highpass_filter(raw, cutoff_hz=35.0)
    out = lowpass_filter(out, cutoff_hz=280.0, passes=2)
    return out


def generate_variant_3_subthump_multimodal():
    """
    Variant 3: Cinematic Sub-Thump / Multimodal ("Kräftiger Puls + Haptik-optimiert").
    Designed with a punchy chest transient and warm saturation (soft-clipping harmonics)
    so it feels visceral both on headphones and Meta Quest 3S built-in strap speakers.
    """
    random.seed(777)
    raw = [0.0] * NUM_SAMPLES
    noise_buf = [random.uniform(-1.0, 1.0) for _ in range(NUM_SAMPLES)]
    chest_noise = lowpass_filter(noise_buf, cutoff_hz=140.0, passes=2)

    phase1 = 0.0
    phase2 = 0.0

    for i in range(NUM_SAMPLES):
        t = i / SAMPLE_RATE
        val = 0.0

        # S1 ("Lub"): Punchy chest thump (0.000s - 0.130s)
        if t < 0.130:
            attack = min(1.0, t / 0.003)  # Crisp 3ms transient onset
            env = attack * math.exp(-t * 24.0)
            # Rapid pitch envelope (110 Hz -> 48 Hz) creates realistic physical impact
            freq1 = 48.0 + 62.0 * math.exp(-t * 55.0)
            phase1 += 2.0 * math.pi * freq1 / SAMPLE_RATE

            body = math.sin(phase1) + 0.50 * math.sin(2.0 * phase1) + 0.25 * math.sin(3.0 * phase1)
            val += env * (body + 0.18 * chest_noise[i])

        # S2 ("Dub"): Defined rebound thump (0.180s - 0.290s)
        if 0.180 <= t < 0.290:
            t2 = t - 0.180
            attack2 = min(1.0, t2 / 0.003)
            env2 = attack2 * math.exp(-t2 * 30.0)
            freq2 = 58.0 + 70.0 * math.exp(-t2 * 65.0)
            phase2 += 2.0 * math.pi * freq2 / SAMPLE_RATE

            body2 = math.sin(phase2) + 0.55 * math.sin(2.0 * phase2) + 0.28 * math.sin(3.0 * phase2)
            val += 0.78 * env2 * (body2 + 0.15 * chest_noise[i])

        # Warm analog-style tanh saturation for upper-bass presence on small VR speakers
        raw[i] = math.tanh(val * 1.65)

    out = highpass_filter(raw, cutoff_hz=30.0)
    out = lowpass_filter(out, cutoff_hz=230.0, passes=2)
    return out


def main():
    repo_root = "/Users/Jonah/Documents/antigravity/cool-pythagoras"
    target_dirs = [
        os.path.join(repo_root, "VR Template", "Assets", "Resources", "Audio", "Heartbeats"),
        os.path.join(repo_root, "VR Template", "Assets", "Audio", "Heartbeats"),
    ]

    v1 = generate_variant_1_internal_deep()
    v2 = generate_variant_2_stethoscope_real()
    v3 = generate_variant_3_subthump_multimodal()

    variants = [
        ("Heartbeat_1_Internal_Deep.wav", v1),
        ("Heartbeat_2_Stethoscope_Real.wav", v2),
        ("Heartbeat_3_SubThump_Multimodal.wav", v3),
    ]

    for d in target_dirs:
        for filename, samples in variants:
            out_path = os.path.join(d, filename)
            normalize_and_save(out_path, samples)
            print(f"Saved: {out_path} ({len(samples)} samples, {DURATION_SEC*1000:.0f} ms)")


if __name__ == "__main__":
    main()
