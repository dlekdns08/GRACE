// LayoutSelector.cs
// Phase G3 (UI layer) for GRACE.
//
// 4-button selector for Carroll's standard layouts. Sets
// GameModeFlags.SelectedLayout (read by KitchenRenderer / NetworkKitchen) and
// loads the game scene.

using UnityEngine;
using UnityEngine.SceneManagement;

namespace Grace.Unity.UI
{
    /// <summary>4-button picker for the 4 supported layouts; sets a static flag and loads the game scene.</summary>
    public sealed class LayoutSelector : MonoBehaviour
    {
        [Header("Scene to load after selection")]
        public string GameScene = "02_GameRoom";

        public void SelectCrampedRoom() => Choose("cramped_room");
        public void SelectAsymmetricAdvantages() => Choose("asymmetric_advantages");
        public void SelectCoordinationRing() => Choose("coordination_ring");
        public void SelectForcedCoordination() => Choose("forced_coordination");

        private void Choose(string layoutName)
        {
            GameModeFlags.SelectedLayout = layoutName;
            SceneManager.LoadScene(GameScene);
        }
    }
}
