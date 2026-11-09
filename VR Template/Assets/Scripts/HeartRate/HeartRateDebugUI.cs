using UnityEngine;

namespace VRHeartbeatStudy
{
    /// <summary>
    /// Full Biofeedback Testbench HUD for Unity 6.3 LTS:
    /// - 3D Visual Heartbeat Pulse Sphere
    /// - Procedural "Lub-Dub" Audio Synthesizer
    /// - Live 130 Hz ECG Oscilloscope Waveform Graph (uV)
    /// - Live HRV Metrics (RMSSD, SDNN, pNN50) & Battery Level
    /// - Interactive Factor A & Factor B Controls
    /// </summary>
    [RequireComponent(typeof(PolarUDPReceiver))]
    [RequireComponent(typeof(AudioSource))]
    public class HeartRateDebugUI : MonoBehaviour
    {
        [Header("Modality Toggles (Factor A Preview)")]
        public bool enableVisualPulse = true;
        public bool enableAudioPulse = true;

        [Header("Visual Pulse Target")]
        [Tooltip("Assign any 3D object to pulse on each heartbeat. Auto-finds 'PolarH10_PulseSphere' if empty.")]
        public Transform pulseTarget;

        [Tooltip("Scale multiplier on heartbeat trigger")]
        public float pulseScaleMultiplier = 1.40f;

        [Tooltip("How fast the object returns to its base scale")]
        public float pulseDecaySpeed = 7.5f;

        private PolarUDPReceiver _receiver;
        private AudioSource _audioSource;
        private AudioClip _lubDubClip;
        private Vector3 _baseScale = Vector3.one;
        private float _currentPulse = 0f;
        private Renderer _targetRenderer;
        private readonly Color _baseColor = new Color(0.85f, 0.12f, 0.18f);
        private readonly Color _pulseColor = new Color(1.0f, 0.35f, 0.40f);

        // Live ECG Oscilloscope Texture
        private Texture2D _ecgTexture;
        private Color32[] _ecgClearPixels;
        private readonly float[] _ecgSamples = new float[PolarUDPReceiver.EcgBufferSize];
        private const int EcgTexWidth = 380;
        private const int EcgTexHeight = 96;

        private void Awake()
        {
            _receiver = GetComponent<PolarUDPReceiver>();
            _audioSource = GetComponent<AudioSource>();
            _audioSource.playOnAwake = false;
            _audioSource.spatialBlend = 0f;
            _lubDubClip = CreateProceduralLubDubClip();

            InitEcgTexture();

            if (pulseTarget == null)
            {
                GameObject existing = GameObject.Find("PolarH10_PulseSphere");
                if (existing != null)
                {
                    pulseTarget = existing.transform;
                }
                else
                {
                    GameObject sphere = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                    sphere.name = "PolarH10_PulseSphere";
                    sphere.transform.position = new Vector3(0.45f, 1.15f, 0.5f);
                    pulseTarget = sphere.transform;
                }
            }

            _baseScale = pulseTarget.localScale;
            _targetRenderer = pulseTarget.GetComponent<Renderer>();
            if (_targetRenderer != null)
            {
                _targetRenderer.material.color = _baseColor;
            }
        }

        private void InitEcgTexture()
        {
            _ecgTexture = new Texture2D(EcgTexWidth, EcgTexHeight, TextureFormat.RGBA32, false)
            {
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp
            };
            _ecgClearPixels = new Color32[EcgTexWidth * EcgTexHeight];
            Color32 bg = new Color32(14, 20, 28, 255);
            Color32 grid = new Color32(28, 42, 56, 255);

            for (int y = 0; y < EcgTexHeight; y++)
            {
                for (int x = 0; x < EcgTexWidth; x++)
                {
                    bool isGrid = (x % 38 == 0) || (y % 24 == 0);
                    _ecgClearPixels[y * EcgTexWidth + x] = isGrid ? grid : bg;
                }
            }
            _ecgTexture.SetPixels32(_ecgClearPixels);
            _ecgTexture.Apply();
        }

        private void UpdateEcgGraphTexture()
        {
            if (_ecgTexture == null || _receiver == null) return;

            _receiver.GetChronologicalEcgSamples(_ecgSamples);
            Color32[] pixels = (Color32[])_ecgClearPixels.Clone();
            Color32 lineColor = _receiver.EcgActive
                ? new Color32(0, 230, 118, 255)
                : new Color32(120, 144, 156, 255);

            int prevY = EcgTexHeight / 2;
            for (int x = 0; x < EcgTexWidth; x++)
            {
                int sampleIdx = Mathf.Clamp(
                    Mathf.FloorToInt(((float)x / EcgTexWidth) * PolarUDPReceiver.EcgBufferSize),
                    0,
                    PolarUDPReceiver.EcgBufferSize - 1
                );
                float uv = _ecgSamples[sampleIdx];
                // Map [-800 uV .. +1600 uV] into texture height
                float normalized = Mathf.InverseLerp(-800f, 1600f, uv);
                int y = Mathf.Clamp(Mathf.RoundToInt(normalized * (EcgTexHeight - 8)) + 4, 1, EcgTexHeight - 2);

                int yMin = Mathf.Min(prevY, y);
                int yMax = Mathf.Max(prevY, y);
                for (int py = yMin; py <= yMax; py++)
                {
                    pixels[py * EcgTexWidth + x] = lineColor;
                    if (py + 1 < EcgTexHeight)
                        pixels[(py + 1) * EcgTexWidth + x] = lineColor;
                }
                prevY = y;
            }

            _ecgTexture.SetPixels32(pixels);
            _ecgTexture.Apply();
        }

        private void OnEnable()
        {
            if (_receiver != null)
            {
                _receiver.OnHeartbeatTriggered.AddListener(OnHeartbeat);
            }
        }

        private void OnDisable()
        {
            if (_receiver != null)
            {
                _receiver.OnHeartbeatTriggered.RemoveListener(OnHeartbeat);
            }
        }

        public void OnHeartbeat(float currentManipulatedBpm)
        {
            if (enableVisualPulse)
            {
                _currentPulse = 1.0f;
            }

            if (enableAudioPulse && _audioSource != null && _lubDubClip != null)
            {
                _audioSource.PlayOneShot(_lubDubClip, 0.85f);
            }
        }

        private void Update()
        {
            if (pulseTarget != null)
            {
                _currentPulse = Mathf.MoveTowards(_currentPulse, 0f, Time.deltaTime * pulseDecaySpeed);
                float scaleFactor = enableVisualPulse ? Mathf.Lerp(1.0f, pulseScaleMultiplier, _currentPulse) : 1.0f;
                pulseTarget.localScale = _baseScale * scaleFactor;

                if (_targetRenderer != null)
                {
                    _targetRenderer.material.color = Color.Lerp(_baseColor, _pulseColor, _currentPulse);
                }
            }

            if (Time.frameCount % 2 == 0)
            {
                UpdateEcgGraphTexture();
            }
        }

        private AudioClip CreateProceduralLubDubClip()
        {
            int sampleRate = 44100;
            float duration = 0.38f;
            int totalSamples = Mathf.CeilToInt(sampleRate * duration);
            float[] samples = new float[totalSamples];

            for (int i = 0; i < totalSamples; i++)
            {
                float t = (float)i / sampleRate;
                float sample = 0f;

                if (t < 0.12f)
                {
                    float env = Mathf.Sin((t / 0.12f) * Mathf.PI) * Mathf.Exp(-t * 18f);
                    sample += env * (0.75f * Mathf.Sin(2f * Mathf.PI * 58f * t) + 0.25f * Mathf.Sin(2f * Mathf.PI * 116f * t));
                }

                if (t >= 0.16f && t < 0.27f)
                {
                    float t2 = t - 0.16f;
                    float env2 = Mathf.Sin((t2 / 0.11f) * Mathf.PI) * Mathf.Exp(-t2 * 22f);
                    sample += 0.65f * env2 * (0.7f * Mathf.Sin(2f * Mathf.PI * 72f * t2) + 0.3f * Mathf.Sin(2f * Mathf.PI * 144f * t2));
                }

                samples[i] = Mathf.Clamp(sample * 1.4f, -1f, 1f);
            }

            AudioClip clip = AudioClip.Create("Procedural_LubDub", totalSamples, 1, sampleRate, false);
            clip.SetData(samples, 0);
            return clip;
        }

        private void OnGUI()
        {
            GUIStyle labelStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 14,
                richText = true
            };

            GUILayout.BeginArea(new Rect(16, 16, 420, 540), GUI.skin.box);
            GUILayout.Label("<b><size=16>Polar H10 <-> Unity 6.3 Biofeedback Telemetry</size></b>", labelStyle);
            GUILayout.Space(4);

            string statusColor = _receiver.IsReceivingData ? "#4CAF50" : "#FF5252";
            string statusText = _receiver.IsReceivingData
                ? (_receiver.IsSimulated ? "CONNECTED (PYTHON SIMULATION)" : "CONNECTED (POLAR H10 BLE)")
                : $"WAITING FOR UDP (Port {_receiver.listenPort})...";

            string battText = _receiver.BatteryPct >= 0 ? $"{_receiver.BatteryPct}%" : "N/A";
            GUILayout.Label($"Status: <color={statusColor}><b>{statusText}</b></color>", labelStyle);
            GUILayout.Label($"Packets: <b>{_receiver.TotalPacketsReceived}</b>  |  Contact: <b>{(_receiver.SensorContact ? "<color=#4CAF50>OK</color>" : "<color=#FFC107>NO</color>")}</b>  |  Battery: <b>{battText}</b>", labelStyle);
            GUILayout.Space(4);

            // Cardiac & HRV Section
            GUILayout.Label($"True Heart Rate: <b><size=19>{_receiver.TrueBpm} BPM</size></b>   |   Latest RR: <b>{_receiver.LatestRrMs:F1} ms</b>", labelStyle);
            GUILayout.Label($"<b>Live HRV (Time-Domain):</b>  RMSSD: <b><color=#80D8FF>{_receiver.RmssdMs:F1} ms</color></b>  |  SDNN: <b>{_receiver.SdnnMs:F1} ms</b>  |  pNN50: <b>{_receiver.Pnn50Pct:F0}%</b>", labelStyle);
            GUILayout.Space(6);

            // 130 Hz Raw ECG Oscilloscope
            string ecgStatus = _receiver.EcgActive ? "<color=#00E676>ACTIVE (130 Hz uV + R-Peak Lock)</color>" : "<color=#FFB74D>WAITING FOR PMD STREAM...</color>";
            GUILayout.Label($"<b>Raw ECG Stream:</b> {ecgStatus}", labelStyle);
            if (_ecgTexture != null)
            {
                GUILayout.Label(_ecgTexture, GUILayout.Width(EcgTexWidth), GUILayout.Height(EcgTexHeight));
            }
            GUILayout.Space(4);

            // Factor B Controls
            GUILayout.Label($"<b>Factor B – Frequency Manipulation ({_receiver.manipulationMode}):</b>  Target: <b><size=16>{_receiver.ManipulatedBpm:F1} BPM</size></b>", labelStyle);

            GUILayout.BeginHorizontal();
            if (GUILayout.Button($"Slower (-{_receiver.manipulationPercentage * 100:F0}%)", GUILayout.Height(28)))
            {
                _receiver.manipulationMode = HeartRateManipulationMode.Slower;
            }
            if (GUILayout.Button("Real (R-Peak Sync)", GUILayout.Height(28)))
            {
                _receiver.manipulationMode = HeartRateManipulationMode.Real;
            }
            if (GUILayout.Button($"Faster (+{_receiver.manipulationPercentage * 100:F0}%)", GUILayout.Height(28)))
            {
                _receiver.manipulationMode = HeartRateManipulationMode.Faster;
            }
            GUILayout.EndHorizontal();

            _receiver.beatLockedInRealMode = GUILayout.Toggle(
                _receiver.beatLockedInRealMode,
                " R-Peak Phase-Lock in 'Real' Mode (Zero Drift)"
            );

            GUILayout.Space(4);
            GUILayout.Label("<b>Factor A – Active Feedback Modalities:</b>", labelStyle);
            GUILayout.BeginHorizontal();
            enableVisualPulse = GUILayout.Toggle(enableVisualPulse, " Visual Pulse (3D Sphere)", GUILayout.Height(22));
            enableAudioPulse = GUILayout.Toggle(enableAudioPulse, " Audio (Lub-Dub)", GUILayout.Height(22));
            GUILayout.EndHorizontal();

            GUILayout.Space(4);
            if (GUILayout.Button("Trigger Manual Test Heartbeat", GUILayout.Height(26)))
            {
                OnHeartbeat(_receiver.ManipulatedBpm > 0 ? _receiver.ManipulatedBpm : 72f);
            }

            GUILayout.EndArea();
        }
    }
}
