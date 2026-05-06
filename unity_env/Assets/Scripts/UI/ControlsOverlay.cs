// ControlsOverlay.cs
// In-game controls/help panel. Drop this script on any GameObject in the
// game scene (e.g. HUDCanvas) and it draws a self-contained IMGUI panel
// listing key bindings and a one-line objective. No Canvas/TMP wiring
// required — this uses Unity's built-in IMGUI so it works even before the
// HUD is fully wired.
//
// Toggle with H. Press F1 to also show a verbose "how to play" panel.

using UnityEngine;

namespace Grace.Unity.UI
{
    /// <summary>Self-contained in-game controls help overlay (IMGUI-based).</summary>
    public sealed class ControlsOverlay : MonoBehaviour
    {
        public enum Anchor { TopLeft, TopRight, BottomLeft, BottomRight }

        [Header("Visibility")]
        [Tooltip("Show the compact controls panel on start.")]
        public bool ShowOnStart = true;

        [Tooltip("Key that toggles the compact panel on/off.")]
        public KeyCode ToggleKey = KeyCode.H;

        [Tooltip("Key that toggles the full how-to-play panel.")]
        public KeyCode HelpKey = KeyCode.F1;

        [Header("Layout")]
        public Anchor PanelAnchor = Anchor.BottomLeft;
        public int Margin = 16;
        public int FontSize = 16;

        [Header("Mode")]
        [Tooltip("If true, show P2 (Arrow keys) bindings as well.")]
        public bool IsTwoPlayer = true;

        private bool _show;
        private bool _showHelp;
        private GUIStyle _label;
        private GUIStyle _title;
        private GUIStyle _box;
        private Texture2D _bgTex;

        private void Start() { _show = ShowOnStart; }

        private void Update()
        {
            if (UnityEngine.Input.GetKeyDown(ToggleKey)) _show = !_show;
            if (UnityEngine.Input.GetKeyDown(HelpKey)) _showHelp = !_showHelp;
        }

        private void OnGUI()
        {
            EnsureStyles();

            if (_show) DrawControlsPanel();
            if (_showHelp) DrawHelpPanel();

            // Always render a small hint so the player can discover the toggle.
            DrawHint();
        }

        private void EnsureStyles()
        {
            if (_bgTex == null)
            {
                _bgTex = new Texture2D(1, 1);
                _bgTex.SetPixel(0, 0, new Color(0f, 0f, 0f, 0.72f));
                _bgTex.Apply();
            }
            if (_box == null)
            {
                _box = new GUIStyle(GUI.skin.box);
                _box.normal.background = _bgTex;
                _box.padding = new RectOffset(14, 14, 12, 12);
                _box.border = new RectOffset(2, 2, 2, 2);
            }
            if (_label == null)
            {
                _label = new GUIStyle(GUI.skin.label);
                _label.normal.textColor = Color.white;
                _label.fontSize = FontSize;
                _label.richText = true;
                _label.wordWrap = true;
            }
            if (_title == null)
            {
                _title = new GUIStyle(_label);
                _title.fontSize = FontSize + 4;
                _title.fontStyle = FontStyle.Bold;
            }
        }

        private void DrawControlsPanel()
        {
            float w = 320f;
            float h = IsTwoPlayer ? 220f : 170f;
            Rect r = AnchorRect(w, h);

            GUI.Box(r, GUIContent.none, _box);
            GUILayout.BeginArea(new Rect(r.x + 14, r.y + 12, r.width - 28, r.height - 24));
            GUILayout.Label("조작 (Controls)", _title);
            GUILayout.Space(6);
            GUILayout.Label("<b>P1</b>   이동: <b>W A S D</b>", _label);
            GUILayout.Label("       상호작용: <b>Space</b>", _label);
            if (IsTwoPlayer)
            {
                GUILayout.Space(4);
                GUILayout.Label("<b>P2</b>   이동: <b>↑ ↓ ← →</b>", _label);
                GUILayout.Label("       상호작용: <b>Right Shift</b>", _label);
            }
            GUILayout.Space(8);
            GUILayout.Label($"<color=#9ad>{HelpKey}: 도움말 · {ToggleKey}: 숨기기</color>", _label);
            GUILayout.EndArea();
        }

        private void DrawHelpPanel()
        {
            float w = 460f;
            float h = 300f;
            float x = (Screen.width - w) * 0.5f;
            float y = (Screen.height - h) * 0.5f;
            Rect r = new Rect(x, y, w, h);

            GUI.Box(r, GUIContent.none, _box);
            GUILayout.BeginArea(new Rect(r.x + 18, r.y + 14, r.width - 36, r.height - 28));
            GUILayout.Label("게임 진행 방법", _title);
            GUILayout.Space(6);
            GUILayout.Label("목표: 제한 시간 안에 양파 수프를 만들어 서빙하세요.", _label);
            GUILayout.Space(8);
            GUILayout.Label("1) <b>노란 타일</b>(양파 디스펜서)에 가서 <b>상호작용</b> → 양파 들기.", _label);
            GUILayout.Label("2) <b>회색 솥</b> 앞에서 상호작용 → 양파 3개 넣기.", _label);
            GUILayout.Label("3) 솥이 'cooking' → 'ready'가 되면, <b>하늘색 타일</b>(접시)에서 상호작용 → 접시 들기.", _label);
            GUILayout.Label("4) 솥 앞에서 상호작용 → 수프 떠담기.", _label);
            GUILayout.Label("5) <b>초록 타일</b>(서빙 카운터)에 가서 상호작용 → 서빙 +20점!", _label);
            GUILayout.Space(10);
            GUILayout.Label($"<color=#9ad>{HelpKey} 다시 누르면 닫힙니다.</color>", _label);
            GUILayout.EndArea();
        }

        private void DrawHint()
        {
            string hint = _show
                ? $"H: 조작 숨기기   {HelpKey}: 도움말"
                : $"H: 조작 보기   {HelpKey}: 도움말";
            var size = _label.CalcSize(new GUIContent(hint));
            float padX = 10, padY = 6;
            Rect r = new Rect(Margin, Margin, size.x + padX * 2, size.y + padY * 2);
            GUI.Box(r, GUIContent.none, _box);
            GUI.Label(new Rect(r.x + padX, r.y + padY, size.x, size.y), hint, _label);
        }

        private Rect AnchorRect(float w, float h)
        {
            float x, y;
            switch (PanelAnchor)
            {
                case Anchor.TopLeft:
                    x = Margin;
                    y = Margin + 40;   // leave room for the always-on hint
                    break;
                case Anchor.TopRight:
                    x = Screen.width - w - Margin;
                    y = Margin;
                    break;
                case Anchor.BottomRight:
                    x = Screen.width - w - Margin;
                    y = Screen.height - h - Margin;
                    break;
                case Anchor.BottomLeft:
                default:
                    x = Margin;
                    y = Screen.height - h - Margin;
                    break;
            }
            return new Rect(x, y, w, h);
        }
    }
}
