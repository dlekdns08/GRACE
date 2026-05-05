// RoundEndScreen.cs
// Phase G3 (UI layer) for GRACE.
//
// Shows final score / soups / S-A-B-C rank and offers Play Again or Title.

using Grace.Unity.Network;
using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Grace.Unity.UI
{
    /// <summary>End-of-round summary: shows score, soups, rank, and navigation buttons.</summary>
    public sealed class RoundEndScreen : MonoBehaviour
    {
        [Header("Final stats (populate before activating, or auto-fill from RoundResults.Last)")]
        public int FinalScore;
        public int FinalSoups;

        [Header("Display fields")]
        public TMP_Text ScoreText;
        public TMP_Text SoupsText;
        public TMP_Text RankText;

        [Header("Scene names")]
        public string TitleScene = "00_Title";
        public string GameScene = "02_GameRoom";

        [Header("Rank thresholds (score)")]
        public int RankSScore = 200;
        public int RankAScore = 120;
        public int RankBScore = 60;

        private void OnEnable()
        {
            // If the host has stashed final stats via RoundEndCoordinator, pick
            // them up. Inspector-set values still win when nonzero.
            if (FinalScore == 0 && FinalSoups == 0)
            {
                FinalScore = RoundResults.Last.Score;
                FinalSoups = RoundResults.Last.Soups;
            }
            Refresh();
        }

        public void Show(int score, int soups)
        {
            FinalScore = score;
            FinalSoups = soups;
            gameObject.SetActive(true);
            Refresh();
        }

        public void OnPlayAgain() => SceneManager.LoadScene(GameScene);
        public void OnReturnToTitle() => SceneManager.LoadScene(TitleScene);

        private void Refresh()
        {
            if (ScoreText != null) ScoreText.text = $"Score: {FinalScore}";
            if (SoupsText != null) SoupsText.text = $"Soups: {FinalSoups}";
            if (RankText != null) RankText.text = $"Rank: {ComputeRank(FinalScore)}";
        }

        private string ComputeRank(int score)
        {
            if (score >= RankSScore) return "S";
            if (score >= RankAScore) return "A";
            if (score >= RankBScore) return "B";
            return "C";
        }
    }
}
