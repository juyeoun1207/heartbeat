# VR Heartbeat Biofeedback Study — Project Memory & Subagent Guidelines

> **Master Chat Conversation ID:** `09d80b88-f59b-420f-9ac8-4d14e5889362`
> **Purpose:** This file (`AGENTS.md`) serves as the persistent project memory across all chats and subagents in this workspace. Whenever study parameters, technical architecture, or design decisions are updated in the Master Chat (or via subchats), this file MUST be kept in sync.

---

## 1. Study Overview & Research Goal
- **Topic:** Effects of manipulated (accelerated vs. decelerated vs. real-time) heartbeat biofeedback across different sensory modalities in Virtual Reality (VR).
- **Context:** University semester module / empirical user study.

---

## 2. Experimental Design ($3 \times 3$ or $4 \times 3$ Factorial Design)

### Factor A: Feedback Modality (3 or 4 levels)
1. **Haptic Feedback:** Controller vibration (Meta Quest Touch Plus controllers).
2. **Visual Feedback:** Pulsating screen (vignette/shader) or pulsating heart icon in VR.
3. **Audio Feedback:** Heartbeat sound (lub-dub audio trigger).
4. **Multimodal / Combined *(optional 4th level)*:** Haptic + Visual + Audio simultaneously.

### Factor B: Heart Rate Frequency Manipulation (3 levels)
1. **Slower:** Decelerated feedback relative to true HR (exact percentage/BPM offset TBD, e.g., $-20\%$).
2. **Real:** Actual heart rate feedback (true HR / synchronous).
3. **Faster:** Accelerated feedback relative to true HR (exact percentage/BPM offset TBD, e.g., $+20\%$).

- **Total Conditions:** 9 conditions ($3 \times 3$) or 12 conditions ($4 \times 3$).

---

## 3. Hardware & Host Setup
- **Host System:** macOS 26.6.2 (25G83) on Apple Silicon (M2).
- **VR Headset:** Meta Quest 3S (referred to as Meta Vision 3 S) + Quest Touch Plus Controllers.
- **Physiological Sensor:** Polar H10 chest strap (ECG, Heart Rate in BPM, RR-intervals in ms via Bluetooth Low Energy / BLE).

---

## 4. Open Decisions & Status Tracker (To Be Defined)
- [ ] **Design Type:** Within-Subjects vs. Mixed Design (3 vs. 4 modalities, block randomization, counterbalancing / Latin Square).
- [ ] **Manipulation Magnitude:** Percentage (e.g., $\pm 15\%$ / $\pm 20\%$) vs. fixed BPM offset, and whether "Real" is R-peak locked or rolling-average BPM.
- [ ] **Trial & Washout Timing:** Duration of baseline, stimulus exposure per condition, and rest/washout period between trials.
- [ ] **Dependent Variables (DVs):**
  - Physiological: Actual HR change ($\Delta\text{HR}$), HRV metrics (RMSSD, SDNN).
  - Subjective: Questionnaires (e.g., SAM for valence/arousal, perceived stress, manipulation check / interoceptive awareness).
  - Task/Scenario in VR: Passive resting environment vs. active task / stressor.
- [x] **Technical Stack:**
  - **Game Engine:** Unity 6.3 LTS (`6000.3.28f1`) with Meta XR SDK, project located in `VR Template/` (`/Users/Jonah/Documents/antigravity/cool-pythagoras/VR Template`).
  - **Unity CLI & MCP Integration:** Bound via `unity mcp --project-path "/Users/Jonah/Documents/antigravity/cool-pythagoras/VR Template"` (`com.unity.pipeline` package active in Editor).
  - **Polar H10 Connection Architecture:** Mac Python BLE Bridge (`bleak` / CoreBluetooth in `polar-ble-bridge/polar_udp_bridge.py`, launched via `Start_Polar_H10.command`) streaming low-latency JSON packets via UDP (Port `5005`) to Unity (`VR Template/Assets/Scripts/HeartRate/PolarUDPReceiver.cs` & `HeartRateDebugUI.cs`):
    - **Standard GATT (`0x2A37` & `0x2A19`):** Heart Rate (BPM), RR-intervals (ms, $1/1024\,\text{s}$ resolution), skin contact status, and battery level (%).
    - **Polar PMD Service (`FB005C80`):** 130 Hz Raw ECG ($\mu\text{V}$) with real-time QRS / R-Peak detection (`r_peak` trigger) for phase-locked, zero-drift `Real` heartbeat feedback and live ECG oscilloscope rendering in Unity.
    - **Live HRV Computation:** Rolling time-domain HRV metrics (`RMSSD` in ms, `SDNN` in ms, `pNN50` in %).

---

## 5. Instructions for Subchats & Subagents
1. **Always adhere to the setup defined in this file** when writing code, designing experiments, drafting questionnaires, or creating analysis scripts.
2. **If a subchat makes a binding change** to the study setup or architecture, update Section 2–4 of this `AGENTS.md` file (or report back to the Master Chat `09d80b88-f59b-420f-9ac8-4d14e5889362`) so all other chats stay aligned.
