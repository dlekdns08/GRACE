// PotVisual.cs
// Phase G2 (Render layer) for GRACE.
//
// Visual driver for one cooking pot. Looks up its grid cell in either
// NetworkKitchen.Pots[] (online) or a local PotState (offline) and toggles
// onion-stack visuals + steam particles + ready glow accordingly.

using Grace.Unity.Core;
using Grace.Unity.Network;
using UnityEngine;

namespace Grace.Unity.Render
{
    /// <summary>Renders one pot's onion count, cooking steam, and ready glow.</summary>
    public sealed class PotVisual : MonoBehaviour
    {
        [Header("Grid identity")]
        public int X;
        public int Y;

        [Header("Source (one of these must be set)")]
        public NetworkKitchen Kitchen;
        public PotState OfflinePot;

        [Header("Visual children")]
        public ParticleSystem SteamParticles;
        public GameObject ReadyGlow;
        public GameObject Onion1;
        public GameObject Onion2;
        public GameObject Onion3;

        private int _lastOnions = -1;
        private bool _lastCooking;
        private bool _lastReady;

        private void LateUpdate()
        {
            if (!TryReadState(out int onions, out bool cooking, out bool ready))
                return;

            if (onions != _lastOnions)
            {
                _lastOnions = onions;
                if (Onion1 != null) Onion1.SetActive(onions >= 1);
                if (Onion2 != null) Onion2.SetActive(onions >= 2);
                if (Onion3 != null) Onion3.SetActive(onions >= 3);
            }

            if (cooking != _lastCooking)
            {
                _lastCooking = cooking;
                if (SteamParticles != null)
                {
                    if (cooking) SteamParticles.Play();
                    else SteamParticles.Stop();
                }
            }

            if (ready != _lastReady)
            {
                _lastReady = ready;
                if (ReadyGlow != null) ReadyGlow.SetActive(ready);
            }
        }

        private bool TryReadState(out int onions, out bool cooking, out bool ready)
        {
            onions = 0;
            cooking = false;
            ready = false;

            if (Kitchen != null && Kitchen.Pots != null)
            {
                for (int i = 0; i < Kitchen.Pots.Count; i++)
                {
                    var p = Kitchen.Pots[i];
                    if (p.X == X && p.Y == Y)
                    {
                        onions = p.OnionsIn;
                        cooking = p.CookingTime > 0 && !p.IsReady;
                        ready = p.IsReady;
                        return true;
                    }
                }
                return false;
            }

            if (OfflinePot != null)
            {
                onions = OfflinePot.OnionsIn;
                cooking = OfflinePot.IsCooking;
                ready = OfflinePot.IsReady;
                return true;
            }

            return false;
        }
    }
}
