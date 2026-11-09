using System;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;
using UnityEngine.Events;

namespace VRHeartbeatStudy
{
    /// <summary>
    /// Full JSON payload structure sent by polar_udp_bridge.py
    /// Includes BPM, RR-intervals (ms), HRV metrics (RMSSD, SDNN, pNN50),
    /// Battery %, 130 Hz Raw ECG samples (uV), and instant R-peak trigger flag.
    /// </summary>
    [Serializable]
    public class PolarHeartRatePacket
    {
        public int seq;
        public string packet_type;
        public double timestamp;
        public int bpm;
        public float[] rr_ms;
        public float latest_rr_ms;
        public float rmssd_ms;
        public float sdnn_ms;
        public float pnn50_pct;
        public int battery_pct;
        public bool contact;
        public bool ecg_active;
        public bool r_peak;
        public int[] ecg_uv;
        public bool simulated;
    }

    /// <summary>
    /// Factor B of the Experimental Design: Heart Rate Frequency Manipulation
    /// </summary>
    public enum HeartRateManipulationMode
    {
        Real = 0,   // 100% of true HR (R-peak / beat-locked in real time)
        Slower = 1, // e.g., -20% frequency (stretched RR-interval)
        Faster = 2  // e.g., +20% frequency (compressed RR-interval)
    }

    /// <summary>
    /// Low-latency, thread-safe UDP receiver for Polar H10 data in Unity 6.3 LTS.
    /// Supports R-Peak Phase-Synchronized triggering in Real mode, HRV-preserving
    /// frequency manipulation in Slower/Faster modes, and a 130 Hz ECG ring buffer.
    /// </summary>
    public class PolarUDPReceiver : MonoBehaviour
    {
        [Header("UDP Network Settings")]
        [Tooltip("Must match the --port argument of polar_udp_bridge.py")]
        public int listenPort = 5005;

        [Header("Factor B: Frequency Manipulation & Phase Lock")]
        public HeartRateManipulationMode manipulationMode = HeartRateManipulationMode.Real;

        [Tooltip("Percentage offset for Slower/Faster conditions (e.g. 0.20 = +/- 20%)")]
        [Range(0.05f, 0.50f)]
        public float manipulationPercentage = 0.20f;

        [Tooltip("If true, Real mode triggers immediately on incoming Polar H10 R-peaks for minimal latency")]
        public bool beatLockedInRealMode = true;

        [Header("Live Telemetry (Read-Only in Inspector)")]
        [SerializeField] private bool isReceivingData;
        [SerializeField] private int trueBpm;
        [SerializeField] private float manipulatedBpm;
        [SerializeField] private float latestRrMs;
        [SerializeField] private float rmssdMs;
        [SerializeField] private float sdnnMs;
        [SerializeField] private float pnn50Pct;
        [SerializeField] private int batteryPct = -1;
        [SerializeField] private bool sensorContact;
        [SerializeField] private bool ecgActive;
        [SerializeField] private bool isSimulated;
        [SerializeField] private int totalPacketsReceived;

        [Header("Events for Biofeedback Modalities (Visual / Audio / Haptic)")]
        [Tooltip("Fired every time a new UDP packet arrives from Polar H10")]
        public UnityEvent<PolarHeartRatePacket> OnPacketReceived = new UnityEvent<PolarHeartRatePacket>();

        [Tooltip("Fired on each heartbeat according to the active Manipulation Mode (Real/Slower/Faster)")]
        public UnityEvent<float> OnHeartbeatTriggered = new UnityEvent<float>();

        // Public properties
        public bool IsReceivingData => isReceivingData;
        public int TrueBpm => trueBpm;
        public float ManipulatedBpm => manipulatedBpm;
        public float LatestRrMs => latestRrMs;
        public float RmssdMs => rmssdMs;
        public float SdnnMs => sdnnMs;
        public float Pnn50Pct => pnn50Pct;
        public int BatteryPct => batteryPct;
        public bool SensorContact => sensorContact;
        public bool EcgActive => ecgActive;
        public bool IsSimulated => isSimulated;
        public int TotalPacketsReceived => totalPacketsReceived;

        // Ring buffer for 2 seconds of 130 Hz Raw ECG (260 samples in microvolts)
        public const int EcgBufferSize = 260;
        private readonly float[] _ecgRingBufferUv = new float[EcgBufferSize];
        private int _ecgWriteIndex = 0;

        private UdpClient _udpClient;
        private Thread _receiveThread;
        private volatile bool _isRunning;
        private readonly ConcurrentQueue<PolarHeartRatePacket> _packetQueue = new ConcurrentQueue<PolarHeartRatePacket>();

        private float _lastPacketTime;
        private float _beatTimer;
        private float _lastBeatTriggerTime = -10f;

        /// <summary>
        /// Copies the chronological 130 Hz ECG waveform (in microvolts) into targetArray.
        /// </summary>
        public void GetChronologicalEcgSamples(float[] targetArray)
        {
            if (targetArray == null || targetArray.Length < EcgBufferSize) return;
            for (int i = 0; i < EcgBufferSize; i++)
            {
                int idx = (_ecgWriteIndex + i) % EcgBufferSize;
                targetArray[i] = _ecgRingBufferUv[idx];
            }
        }

        private void OnEnable()
        {
            StartReceiver();
        }

        private void OnDisable()
        {
            StopReceiver();
        }

        private void OnApplicationQuit()
        {
            StopReceiver();
        }

        public void StartReceiver()
        {
            if (_isRunning) return;

            try
            {
                _udpClient = new UdpClient(listenPort);
                _isRunning = true;
                _receiveThread = new Thread(ReceiveLoop)
                {
                    IsBackground = true,
                    Name = "PolarH10_UDP_Thread"
                };
                _receiveThread.Start();
                Debug.Log($"[PolarUDPReceiver] Listening for Polar H10 UDP packets on port {listenPort}...");
            }
            catch (Exception e)
            {
                Debug.LogError($"[PolarUDPReceiver] Failed to start UDP listener on port {listenPort}: {e.Message}");
            }
        }

        public void StopReceiver()
        {
            _isRunning = false;

            if (_udpClient != null)
            {
                try { _udpClient.Close(); } catch { /* ignore */ }
                _udpClient = null;
            }

            if (_receiveThread != null && _receiveThread.IsAlive)
            {
                _receiveThread.Join(200);
                _receiveThread = null;
            }
        }

        private void ReceiveLoop()
        {
            IPEndPoint remoteEndPoint = new IPEndPoint(IPAddress.Any, 0);

            while (_isRunning)
            {
                try
                {
                    byte[] data = _udpClient.Receive(ref remoteEndPoint);
                    string json = Encoding.UTF8.GetString(data);
                    PolarHeartRatePacket packet = JsonUtility.FromJson<PolarHeartRatePacket>(json);
                    if (packet != null)
                    {
                        _packetQueue.Enqueue(packet);
                    }
                }
                catch (SocketException)
                {
                    break;
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[PolarUDPReceiver] Packet parse error: {e.Message}");
                }
            }
        }

        private void Update()
        {
            bool instantRPeakReceivedThisFrame = false;

            // 1. Dequeue all packets received on the background thread
            while (_packetQueue.TryDequeue(out PolarHeartRatePacket packet))
            {
                if (packet.bpm > 0) trueBpm = packet.bpm;
                if (packet.latest_rr_ms > 0f) latestRrMs = packet.latest_rr_ms;
                rmssdMs = packet.rmssd_ms;
                sdnnMs = packet.sdnn_ms;
                pnn50Pct = packet.pnn50_pct;
                if (packet.battery_pct >= 0) batteryPct = packet.battery_pct;
                sensorContact = packet.contact;
                ecgActive = packet.ecg_active;
                isSimulated = packet.simulated;
                totalPacketsReceived = packet.seq;
                _lastPacketTime = Time.unscaledTime;
                isReceivingData = true;

                // Append any 130 Hz ECG samples (in microvolts) to ring buffer
                if (packet.ecg_uv != null && packet.ecg_uv.Length > 0)
                {
                    for (int i = 0; i < packet.ecg_uv.Length; i++)
                    {
                        _ecgRingBufferUv[_ecgWriteIndex] = packet.ecg_uv[i];
                        _ecgWriteIndex = (_ecgWriteIndex + 1) % EcgBufferSize;
                    }
                }

                if (packet.r_peak)
                {
                    instantRPeakReceivedThisFrame = true;
                }

                UpdateManipulatedBpm();
                OnPacketReceived?.Invoke(packet);
            }

            // Timeout check (if no packet for > 3.5 seconds)
            if (isReceivingData && (Time.unscaledTime - _lastPacketTime > 3.5f))
            {
                isReceivingData = false;
            }

            UpdateManipulatedBpm();
            if (!isReceivingData || manipulatedBpm <= 20f) return;

            // 2. Real-Time Beat Triggering (R-Peak Phase-Locked vs. Manipulated Interval)
            float baseIntervalSec = (latestRrMs >= 300f && latestRrMs <= 2000f)
                ? (latestRrMs / 1000f)
                : (60f / Mathf.Max(30f, trueBpm));

            float targetIntervalSec = GetManipulatedIntervalSeconds(baseIntervalSec);

            // In REAL mode with beat-locking, fire immediately when a physical R-peak arrives
            if (manipulationMode == HeartRateManipulationMode.Real && beatLockedInRealMode && instantRPeakReceivedThisFrame)
            {
                if (Time.unscaledTime - _lastBeatTriggerTime >= 0.28f)
                {
                    TriggerHeartbeat();
                    return;
                }
            }

            // Phase-aligned oscillator (bridges between beats and drives Slower/Faster modes)
            _beatTimer += Time.unscaledDeltaTime;
            if (_beatTimer >= targetIntervalSec)
            {
                TriggerHeartbeat();
            }
        }

        private void TriggerHeartbeat()
        {
            _beatTimer = 0f;
            _lastBeatTriggerTime = Time.unscaledTime;
            OnHeartbeatTriggered?.Invoke(manipulatedBpm);
        }

        private float GetManipulatedIntervalSeconds(float trueIntervalSeconds)
        {
            switch (manipulationMode)
            {
                case HeartRateManipulationMode.Slower:
                    return trueIntervalSeconds / Mathf.Max(0.2f, 1f - manipulationPercentage);
                case HeartRateManipulationMode.Faster:
                    return trueIntervalSeconds / (1f + manipulationPercentage);
                case HeartRateManipulationMode.Real:
                default:
                    return trueIntervalSeconds;
            }
        }

        private void UpdateManipulatedBpm()
        {
            if (trueBpm <= 0)
            {
                manipulatedBpm = 0f;
                return;
            }

            switch (manipulationMode)
            {
                case HeartRateManipulationMode.Slower:
                    manipulatedBpm = trueBpm * (1f - manipulationPercentage);
                    break;
                case HeartRateManipulationMode.Faster:
                    manipulatedBpm = trueBpm * (1f + manipulationPercentage);
                    break;
                case HeartRateManipulationMode.Real:
                default:
                    manipulatedBpm = trueBpm;
                    break;
            }
        }
    }
}
