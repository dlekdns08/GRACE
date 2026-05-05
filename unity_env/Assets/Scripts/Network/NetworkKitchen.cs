// NetworkKitchen.cs
// Phase G-Network for GRACE.
// See unity_env/GAME_DESIGN.md sections 4 & 5.
//
// The host owns one ChefSimulation instance and ticks it at 8 Hz.
// Replicated state is broadcast to all clients via NetworkVariables and
// per-chef / per-pot NetworkLists.

using Grace.Unity.Core;
using Unity.Netcode;
using UnityEngine;

namespace Grace.Unity.Network
{
    /// <summary>
    /// Server-authoritative kitchen. The host instantiates and ticks ChefSimulation;
    /// state is broadcast via NetworkVariables and per-pot/per-chef sync structs.
    /// Tick rate: 8 Hz (every 0.125s).
    /// </summary>
    public sealed class NetworkKitchen : NetworkBehaviour
    {
        public string LayoutName = "cramped_room";
        public float ticksPerSecond = 8f;

        // Host-only
        private ChefSimulation _sim;
        private float _accumulator;

        // Replicated state — written by host, read by all
        public NetworkVariable<int> Step = new();
        public NetworkVariable<int> Score = new();
        public NetworkVariable<int> SoupsServed = new();
        public NetworkVariable<bool> IsRunning = new();

        // Per-chef state arrays — fixed size 4 for now
        public NetworkList<ChefStateNet> Chefs;
        public NetworkList<PotStateNet> Pots;

        // Per-tick input intents from each client (host-only buffer)
        private readonly int[] _intents = new int[4];

        private void Awake()
        {
            // NetworkList instances must be constructed before OnNetworkSpawn so
            // they are registered with the NetworkBehaviour replication machinery.
            Chefs ??= new NetworkList<ChefStateNet>();
            Pots ??= new NetworkList<PotStateNet>();
        }

        public override void OnNetworkSpawn()
        {
            if (IsServer)
            {
                LoadAndStart();
            }
        }

        private void LoadAndStart()
        {
            var layout = LayoutLoader.Load(LayoutName);
            _sim = new ChefSimulation(layout);

            // Initialize replicated lists
            Chefs.Clear();
            Pots.Clear();
            for (int i = 0; i < _sim.Chefs.Count; i++)
            {
                Chefs.Add(ChefStateNet.From(_sim.Chefs[i]));
            }
            foreach (var kv in _sim.Pots)
            {
                Pots.Add(PotStateNet.From(kv.Key, kv.Value));
            }
            IsRunning.Value = true;
        }

        [ServerRpc(RequireOwnership = false)]
        public void SubmitIntentServerRpc(int playerIdx, int action, ServerRpcParams rpc = default)
        {
            if (playerIdx < 0 || playerIdx >= _intents.Length) return;
            _intents[playerIdx] = action;
        }

        private void Update()
        {
            if (!IsServer || !IsRunning.Value) return;
            _accumulator += Time.deltaTime;
            float dt = 1f / ticksPerSecond;
            while (_accumulator >= dt)
            {
                _accumulator -= dt;
                int reward = _sim.Tick(_intents);
                System.Array.Clear(_intents, 0, _intents.Length);   // intents are one-shot per tick

                Step.Value = _sim.Step;
                Score.Value = _sim.Score;
                SoupsServed.Value = _sim.SoupsServed;

                // Update replicated chef/pot lists
                for (int i = 0; i < _sim.Chefs.Count; i++)
                {
                    Chefs[i] = ChefStateNet.From(_sim.Chefs[i]);
                }
                int j = 0;
                foreach (var kv in _sim.Pots)
                {
                    Pots[j] = PotStateNet.From(kv.Key, kv.Value);
                    j++;
                }

                if (_sim.IsDone()) IsRunning.Value = false;
            }
        }
    }

    /// <summary>
    /// Per-chef replicated snapshot. Mirrors the relevant fields of
    /// <see cref="Grace.Unity.Core.ChefSimulationState"/> in a network-safe shape.
    /// </summary>
    public struct ChefStateNet : INetworkSerializable, System.IEquatable<ChefStateNet>
    {
        public int X, Y;
        public byte Facing;     // 0=N, 1=S, 2=E, 3=W
        public byte Held;       // 0=None, 1=Onion, 2=Dish, 3=Soup

        public static ChefStateNet From(ChefSimulationState s) => new ChefStateNet
        {
            X = s.Position.X,
            Y = s.Position.Y,
            Facing = (byte)s.Facing,
            Held = (byte)s.Held,
        };

        public void NetworkSerialize<T>(BufferSerializer<T> s) where T : IReaderWriter
        {
            s.SerializeValue(ref X);
            s.SerializeValue(ref Y);
            s.SerializeValue(ref Facing);
            s.SerializeValue(ref Held);
        }

        public bool Equals(ChefStateNet o) =>
            X == o.X && Y == o.Y && Facing == o.Facing && Held == o.Held;

        public override bool Equals(object obj) => obj is ChefStateNet o && Equals(o);
        public override int GetHashCode() => (X * 73856093) ^ (Y * 19349663) ^ (Facing << 8) ^ Held;
    }

    /// <summary>
    /// Per-pot replicated snapshot. Mirrors <see cref="Grace.Unity.Core.PotState"/>.
    /// </summary>
    public struct PotStateNet : INetworkSerializable, System.IEquatable<PotStateNet>
    {
        public int X, Y;
        public byte OnionsIn;
        public byte CookingTime;
        public bool IsReady;

        public static PotStateNet From(GridPos p, PotState s) => new PotStateNet
        {
            X = p.X,
            Y = p.Y,
            OnionsIn = (byte)s.OnionsIn,
            CookingTime = (byte)s.CookingTime,
            IsReady = s.IsReady,
        };

        public void NetworkSerialize<T>(BufferSerializer<T> s) where T : IReaderWriter
        {
            s.SerializeValue(ref X);
            s.SerializeValue(ref Y);
            s.SerializeValue(ref OnionsIn);
            s.SerializeValue(ref CookingTime);
            s.SerializeValue(ref IsReady);
        }

        public bool Equals(PotStateNet o) =>
            X == o.X && Y == o.Y && OnionsIn == o.OnionsIn &&
            CookingTime == o.CookingTime && IsReady == o.IsReady;

        public override bool Equals(object obj) => obj is PotStateNet o && Equals(o);
        public override int GetHashCode() =>
            (X * 73856093) ^ (Y * 19349663) ^ (OnionsIn << 16) ^ (CookingTime << 8) ^ (IsReady ? 1 : 0);
    }
}
