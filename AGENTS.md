# VR Heartbeat Biofeedback Study — Project Memory & Subagent Guidelines

> **Master Chat Conversation ID:** `09d80b88-f59b-420f-9ac8-4d14e5889362`
> **Purpose:** This file (`AGENTS.md`) serves as the persistent project memory across all chats and subagents in this workspace. Whenever study parameters, technical architecture, or design decisions are updated in the Master Chat (or via subchats), this file MUST be kept in sync.

---

## 1. Study Overview & Research Goal
- **Topic:** Effects of manipulated (accelerated vs. decelerated vs. real-time) heartbeat biofeedback across different sensory modalities in Virtual Reality (VR).
- **Context:** University semester module / empirical user study.

---

## 2. Experimental Design ($3 \times 3$ Within-Subjects Factorial Design)

> **Decided Concept (Variant B):** Modality $\times$ Heart Rate Frequency Manipulation.
> **Discarded Alternative:** Simulated running / locomotion in VR was rejected due to high risk of severe cybersickness and emesis (nausea), avoiding sensory-vestibular confounds.

### Factor A: Feedback Modality (3 levels)
1. **Visual Feedback:** Pulsating heart icon on the VR HUD (expanding/fading based on Fink et al., 2026).
2. **Audio Feedback:** Naturalistic low-frequency heartbeat sound (lub-dub stereo cue).
3. **Haptic Feedback:** Dual-pulse vibrotactile feedback (Meta Quest Touch Plus LRA controller vibration).
*(Note: Combined/Multimodal condition "ALL" excluded from main factorial matrix to keep participant session under 40 minutes).*

### Factor B: Heart Rate Frequency Manipulation (3 levels)
1. **Slower (-20%):** Decelerated feedback at $0.80 \times \text{instantaneous HR}$.
2. **Real (0%):** Phase-locked, zero-drift real-time feedback triggered directly by actual ECG R-peaks.
3. **Faster (+20%):** Accelerated feedback at $1.20 \times \text{instantaneous HR}$.

- **Total Conditions:** 9 conditions ($3 \times 3$), balanced via Latin Square.

---

## 3. Hardware & Host Setup
- **Host System:** macOS 26.6.2 (25G83) on Apple Silicon (M2).
- **VR Headset:** Meta Quest 3S (referred to as Meta Vision 3 S) + Quest Touch Plus Controllers.
- **Physiological Sensor:** Polar H10 chest strap (ECG, Heart Rate in BPM, RR-intervals in ms via Bluetooth Low Energy / BLE).
- **Quest 3S Deployment Pipeline:** Unity standalone Android APK on Quest 3S receiving wireless UDP packets from the Mac Python bridge over local 5 GHz Wi-Fi / hotspot (port `5005`).

---

## 4. Decisions & Status Tracker
- [x] **Design Type:** Within-Subjects $3 \times 3$ factorial design, counterbalanced via balanced Latin Square ($N = 20\text{--}24$).
- [x] **Manipulation Magnitude:** $\pm 20\%$ offset. "Real" is phase-locked to QRS R-peaks from raw ECG.
- [x] **Trial & Washout Timing:** Trial-Specific Baseline Design (per condition: 30 s pre-stimulus baseline -> 180 s stimulus exposure -> 45–60 s washout & in-VR survey). Total session $\approx 45\text{--}50$ min ($9 \times 4.5$ min).
- [x] **Dependent Variables (DVs):**
  - Physiological: $\Delta\text{HR}$ (BPM shift vs. baseline), HRV metrics (RMSSD, SDNN).
  - Subjective: 2AFC discrimination ("Did it match your heartbeat?"), Perceived HR visual slider (30–140 BPM), SAM (Valence & Arousal), short SSQ/FMS.
  - Task/Scenario in VR: Seated/standing passive observation in a serene, neutral nature environment (no locomotion).
- [x] **Technical Stack & Architecture:** Fully documented in [Google Doc Specification](https://docs.google.com/document/d/1dHm4Yygn9Af6Jc8HSLo8wOU_TzT_wBg1wsY2C96ijOU/edit).
  - **Game Engine:** Unity 6.3 LTS (`6000.3.28f1`) with Meta XR SDK in `VR Template/`.
  - **Polar H10 Connection Architecture:** Mac Python BLE Bridge (`bleak` / CoreBluetooth) streaming low-latency JSON packets via UDP (`5005`) to Unity:
    - 130 Hz Raw ECG with real-time Pan-Tompkins QRS R-Peak detector (`r_peak` trigger).
    - Standard GATT HR & RR-intervals with rolling RMSSD/SDNN metrics.

---

## 5. Instructions for Subchats & Subagents
1. **Always adhere to the setup defined in this file** when writing code, designing experiments, drafting questionnaires, or creating analysis scripts.
2. **If a subchat makes a binding change** to the study setup or architecture, update Section 2–4 of this `AGENTS.md` file (or report back to the Master Chat `09d80b88-f59b-420f-9ac8-4d14e5889362`) so all other chats stay aligned.
