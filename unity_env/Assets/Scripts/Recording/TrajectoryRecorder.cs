// TrajectoryRecorder.cs
// Phase 9 (Unity human-play) for GRACE.
//
// Records (state_text, agent_id, action, reward, done) per step into a
// JSON Lines file. The Python side converts JSONL -> parquet downstream
// (see scripts/jsonl_to_parquet.py on the Python repo half).
//
// JSONL is intentionally hand-rolled to avoid pulling in Newtonsoft.Json or
// JsonUtility limitations (JsonUtility doesn't escape strings perfectly).

using System.Globalization;
using System.IO;
using System.Text;
using UnityEngine;

namespace GRACE.Unity
{
    /// <summary>
    /// Append-only JSONL recorder for human-play sessions. One line per
    /// (agent, action) emitted by <see cref="HumanPlayDriver.StepOnce"/>.
    ///
    /// Schema (per line):
    /// <code>
    /// {
    ///   "episode": int,
    ///   "step":    int,                // kitchen.Step at record time
    ///   "agent_id": "agent_{idx}",
    ///   "action":   int,               // 0..6
    ///   "reward":   float,
    ///   "done":     bool,
    ///   "state_text": string           // v1 SerializeKitchen output, escaped
    /// }
    /// </code>
    /// </summary>
    public class TrajectoryRecorder : MonoBehaviour
    {
        [Header("Refs")]
        public KitchenEnvironment kitchen;

        [Tooltip("StateSerializer used to render the v1 state_text payload. " +
                 "If null, recording falls back to an empty string.")]
        public StateSerializer serializer;

        [Header("Output")]
        [Tooltip("Path (relative to project root, or absolute) for the JSONL file. " +
                 "Parent directories are auto-created. File is appended, not truncated.")]
        public string outputPath = "Assets/_demos/play_session.jsonl";

        [Tooltip("Enable to actually write to disk. Useful to leave the " +
                 "component attached but quiet during casual play.")]
        public bool recording = true;

        private StreamWriter _writer;
        private int _episodeId;
        private bool _opened;

        private void Awake()
        {
            TryOpen();
        }

        private void OnDestroy()
        {
            CloseSafe();
        }

        private void OnApplicationQuit()
        {
            CloseSafe();
        }

        private void TryOpen()
        {
            if (_opened) return;
            try
            {
                string dir = Path.GetDirectoryName(outputPath);
                if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                {
                    Directory.CreateDirectory(dir);
                }
                _writer = new StreamWriter(outputPath, append: true, encoding: Encoding.UTF8);
                _opened = true;
            }
            catch (System.Exception e)
            {
                Debug.LogWarning($"[GRACE.TrajectoryRecorder] Failed to open '{outputPath}': {e.Message}");
                _writer = null;
                _opened = false;
            }
        }

        private void CloseSafe()
        {
            if (_writer == null) return;
            try { _writer.Flush(); _writer.Close(); }
            catch (System.Exception) { /* best-effort */ }
            _writer = null;
            _opened = false;
        }

        /// <summary>
        /// Append one transition. Safe to call when not recording (returns
        /// quickly). The episode counter is bumped after a <c>done=true</c>
        /// line so multiple episodes share the same file.
        /// </summary>
        public void Record(int agentIdx, int action, float reward, bool done)
        {
            if (!recording) return;
            if (_writer == null) return;
            if (kitchen == null) return;

            string stateRaw = serializer != null ? serializer.SerializeKitchen(kitchen) : string.Empty;
            string stateEscaped = JsonEscape(stateRaw);

            // Stable invariant-culture float formatting so Python parses
            // identically on every locale.
            string rewardStr = reward.ToString("F3", CultureInfo.InvariantCulture);

            var sb = new StringBuilder(256 + stateEscaped.Length);
            sb.Append('{');
            sb.Append("\"episode\":").Append(_episodeId.ToString(CultureInfo.InvariantCulture));
            sb.Append(",\"step\":").Append(kitchen.Step.ToString(CultureInfo.InvariantCulture));
            sb.Append(",\"agent_id\":\"agent_").Append(agentIdx.ToString(CultureInfo.InvariantCulture)).Append('"');
            sb.Append(",\"action\":").Append(action.ToString(CultureInfo.InvariantCulture));
            sb.Append(",\"reward\":").Append(rewardStr);
            sb.Append(",\"done\":").Append(done ? "true" : "false");
            sb.Append(",\"state_text\":\"").Append(stateEscaped).Append('"');
            sb.Append('}');

            try
            {
                _writer.WriteLine(sb.ToString());
                _writer.Flush();
            }
            catch (System.Exception e)
            {
                Debug.LogWarning($"[GRACE.TrajectoryRecorder] write failed: {e.Message}");
            }

            if (done) _episodeId += 1;
        }

        /// <summary>
        /// Minimal JSON string escape: handles \, ", control chars, and
        /// newlines / tabs. Non-ASCII passes through (UTF-8 encoded).
        /// </summary>
        private static string JsonEscape(string s)
        {
            if (string.IsNullOrEmpty(s)) return string.Empty;
            var sb = new StringBuilder(s.Length + 8);
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                switch (c)
                {
                    case '\\': sb.Append("\\\\"); break;
                    case '"': sb.Append("\\\""); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20)
                        {
                            sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        }
                        else
                        {
                            sb.Append(c);
                        }
                        break;
                }
            }
            return sb.ToString();
        }
    }
}
