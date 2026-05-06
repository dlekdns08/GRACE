// SetupDiagnosticOverlay.cs
// In-game runtime check that explains *why* the chef isn't visible / movable.
// Drop this on any GameObject in 02_GameRoom and it scans the scene each
// second, listing the missing wiring (NetworkObject on PlayerSpawner,
// missing prefab references, NGO not started, etc.) directly on screen.
//
// Toggle with F2.

using System.Collections.Generic;
using System.Text;
using Grace.Unity.Network;
using Unity.Netcode;
using UnityEngine;

namespace Grace.Unity.UI
{
    /// <summary>Runtime checklist that surfaces common 02_GameRoom wiring mistakes.</summary>
    public sealed class SetupDiagnosticOverlay : MonoBehaviour
    {
        [Tooltip("Toggle key for the diagnostic panel.")]
        public KeyCode ToggleKey = KeyCode.F2;

        [Tooltip("Show automatically on start (recommended while debugging).")]
        public bool ShowOnStart = true;

        private bool _show;
        private string _cached = "";
        private float _refreshTimer;
        private GUIStyle _label;
        private GUIStyle _box;
        private Texture2D _bgTex;

        private void Start()
        {
            _show = ShowOnStart;
            Refresh();
        }

        private void Update()
        {
            if (UnityEngine.Input.GetKeyDown(ToggleKey)) _show = !_show;
            _refreshTimer += Time.deltaTime;
            if (_refreshTimer >= 0.5f)
            {
                _refreshTimer = 0f;
                Refresh();
            }
        }

        private void Refresh()
        {
            var sb = new StringBuilder();
            var problems = new List<string>();
            var ok = new List<string>();

            // 1) NetworkManager
            var nm = NetworkManager.Singleton;
            if (nm == null)
            {
                problems.Add("NetworkManager.Singleton 없음 — 씬에 NetworkManager가 없거나 비활성.");
            }
            else
            {
                bool listening = nm.IsListening;
                if (!listening)
                    problems.Add("NetworkManager가 시작되지 않음 — Host/Client/Server 시작 필요 (StartHost).");
                else
                    ok.Add($"NetworkManager listening (IsServer={nm.IsServer}, IsHost={nm.IsHost}, Clients={nm.ConnectedClientsIds.Count})");
            }

            // 2) NetworkKitchen
            var kitchen = FindFirstObjectByType<NetworkKitchen>();
            if (kitchen == null)
            {
                problems.Add("NetworkKitchen 없음 — 씬에 NetworkKitchen GameObject 누락.");
            }
            else
            {
                if (!kitchen.TryGetComponent<NetworkObject>(out _))
                    problems.Add("NetworkKitchen에 NetworkObject 컴포넌트 누락.");
                if (!kitchen.IsSpawned)
                    problems.Add("NetworkKitchen.IsSpawned=false — host 시작 후에만 스폰됨.");
                else
                    ok.Add($"NetworkKitchen spawned (Chefs.Count={kitchen.Chefs?.Count ?? -1})");

                if (kitchen.Chefs != null && kitchen.Chefs.Count == 0 && kitchen.IsSpawned)
                    problems.Add("Kitchen.Chefs 비어있음 — 레이아웃 ChefStarts가 비어있거나 LoadAndStart 실패.");
            }

            // 3) NetworkPlayerSpawner — biggest source of "no chef" issues.
            var spawner = FindFirstObjectByType<NetworkPlayerSpawner>();
            if (spawner == null)
            {
                problems.Add("NetworkPlayerSpawner 없음 — PlayerSpawner GameObject 누락.");
            }
            else
            {
                if (!spawner.TryGetComponent<NetworkObject>(out _))
                    problems.Add("PlayerSpawner에 NetworkObject 컴포넌트 누락 — 추가해야 OnNetworkSpawn 호출됨.");
                if (spawner.NetworkChefPrefab == null)
                    problems.Add("PlayerSpawner.NetworkChefPrefab 비어있음 — ChefPrefab을 드래그해 넣어야 함.");
                else if (!spawner.NetworkChefPrefab.GetComponent<NetworkObject>())
                    problems.Add("ChefPrefab에 NetworkObject 컴포넌트 없음.");
                if (spawner.Kitchen == null)
                    problems.Add("PlayerSpawner.Kitchen 슬롯이 비어있음 — NetworkKitchen 드래그해 넣기.");
                if (spawner.NetworkChefPrefab != null && spawner.Kitchen != null
                    && spawner.TryGetComponent<NetworkObject>(out _))
                    ok.Add("PlayerSpawner 기본 와이어링 OK");
            }

            // 4) Was any chef spawned at all?
            int chefsInScene = FindObjectsByType<NetworkChefAgent>(FindObjectsSortMode.None).Length;
            if (chefsInScene == 0)
                problems.Add("씬에 NetworkChefAgent 인스턴스가 0개 — 스폰 자체가 일어나지 않음.");
            else
                ok.Add($"NetworkChefAgent 인스턴스 {chefsInScene}개 활성");

            // 5) Default network prefabs list — NGO requires registration.
            if (spawner != null && spawner.NetworkChefPrefab != null && nm != null
                && nm.NetworkConfig != null && nm.NetworkConfig.Prefabs != null)
            {
                bool registered = false;
                foreach (var p in nm.NetworkConfig.Prefabs.Prefabs)
                {
                    if (p.Prefab == spawner.NetworkChefPrefab) { registered = true; break; }
                }
                if (!registered)
                    problems.Add("ChefPrefab이 NetworkManager.NetworkConfig.Prefabs에 등록되지 않음 — DefaultNetworkPrefabs.asset 확인.");
            }

            // Build display string.
            sb.AppendLine("<b>GRACE 셋업 진단</b>");
            sb.AppendLine();
            if (problems.Count == 0)
            {
                sb.AppendLine("<color=#9f9>모든 기본 와이어링 정상.</color>");
                sb.AppendLine("그래도 캐릭터가 안 움직이면 PlayerInputController의 NetworkAgent / Controls 슬롯을 확인하세요.");
            }
            else
            {
                sb.AppendLine($"<color=#fa6>문제 {problems.Count}개 발견:</color>");
                for (int i = 0; i < problems.Count; i++)
                    sb.AppendLine($"  {i + 1}. {problems[i]}");
            }
            if (ok.Count > 0)
            {
                sb.AppendLine();
                sb.AppendLine("<color=#9bd>정상 항목:</color>");
                foreach (var line in ok) sb.AppendLine($"  • {line}");
            }
            sb.AppendLine();
            sb.AppendLine($"<color=#aaa>{ToggleKey} 키로 숨기기</color>");

            _cached = sb.ToString();
        }

        private void OnGUI()
        {
            if (!_show) return;
            EnsureStyles();

            float w = 560f, h = 360f;
            float x = (Screen.width - w) * 0.5f;
            float y = 80f;
            Rect r = new Rect(x, y, w, h);
            GUI.Box(r, GUIContent.none, _box);
            GUI.Label(new Rect(r.x + 16, r.y + 14, r.width - 32, r.height - 28), _cached, _label);
        }

        private void EnsureStyles()
        {
            if (_bgTex == null)
            {
                _bgTex = new Texture2D(1, 1);
                _bgTex.SetPixel(0, 0, new Color(0f, 0f, 0f, 0.82f));
                _bgTex.Apply();
            }
            if (_box == null)
            {
                _box = new GUIStyle(GUI.skin.box);
                _box.normal.background = _bgTex;
            }
            if (_label == null)
            {
                _label = new GUIStyle(GUI.skin.label);
                _label.normal.textColor = Color.white;
                _label.fontSize = 14;
                _label.richText = true;
                _label.wordWrap = true;
            }
        }
    }
}
