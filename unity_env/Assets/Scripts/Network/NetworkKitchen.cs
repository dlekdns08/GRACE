// NetworkKitchen.cs
// Phase G-Network for GRACE.
// See unity_env/GAME_DESIGN.md sections 4 & 5.
//
// The host owns one ChefSimulation instance and ticks it at 8 Hz.
// Replicated state is broadcast to all clients via NetworkVariables and
// per-chef / per-pot / per-counter-item NetworkLists.

using System.Collections.Generic;
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
        // Stable enumeration order for pots: enumerated once at LoadAndStart and
        // reused every tick. Dictionary enumeration order is not contractually
        // guaranteed across modifications, so we own the order ourselves.
        private GridPos[] _potKeys;

        // Replicated state — written by host, read by all
        public NetworkVariable<int> Step = new();
        public NetworkVariable<int> Score = new();
        public NetworkVariable<int> SoupsServed = new();
        public NetworkVariable<bool> IsRunning = new();

        // Per-chef / per-pot / per-counter-item replicated arrays.
        public NetworkList<ChefStateNet> Chefs;
        public NetworkList<PotStateNet> Pots;
        public NetworkList<CounterItemNet> CounterItems;

        // Host-only mapping: NGO clientId → 0-based player slot. Persisted across
        // connect/disconnect to avoid OOB on _intents when clientIds skip values.
        private readonly Dictionary<ulong, int> _clientToSlot = new Dictionary<ulong, int>();

        // Per-tick input intents from each client (host-only buffer)
        private const int MaxPlayers = 4;
        private readonly int[] _intents = new int[MaxPlayers];

        private void Awake()
        {
            // NetworkList instances must be constructed before OnNetworkSpawn so
            // they are registered with the NetworkBehaviour replication machinery.
            Chefs ??= new NetworkList<ChefStateNet>();
            Pots ??= new NetworkList<PotStateNet>();
            CounterItems ??= new NetworkList<CounterItemNet>();
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

            // Initialize replicated lists.
            Chefs.Clear();
            Pots.Clear();
            CounterItems.Clear();

            for (int i = 0; i < _sim.Chefs.Count; i++)
            {
                Chefs.Add(ChefStateNet.From(_sim.Chefs[i]));
            }

            // Sort pot keys deterministically so the replicated index assignment
            // is stable across runs (and machines, for parity tests).
            var keys = new List<GridPos>(_sim.Pots.Keys);
            keys.Sort((a, b) =>
            {
                int dy = a.Y.CompareTo(b.Y);
                return dy != 0 ? dy : a.X.CompareTo(b.X);
            });
            _potKeys = keys.ToArray();
            for (int i = 0; i < _potKeys.Length; i++)
            {
                Pots.Add(PotStateNet.From(_potKeys[i], _sim.Pots[_potKeys[i]]));
            }

            IsRunning.Value = true;
        }

        /// <summary>
        /// Register a client → player-slot mapping. Called by NetworkPlayerSpawner
        /// at spawn time. Slots are sticky: a client gets the same slot for the
        /// life of this kitchen instance.
        /// </summary>
        public void RegisterClientSlot(ulong clientId, int slot)
        {
            if (!IsServer) return;
            if (slot < 0 || slot >= MaxPlayers) return;
            _clientToSlot[clientId] = slot;
        }

        public bool TryGetClientSlot(ulong clientId, out int slot) =>
            _clientToSlot.TryGetValue(clientId, out slot);

        [ServerRpc(RequireOwnership = false)]
        public void SubmitIntentServerRpc(int action, ServerRpcParams rpc = default)
        {
            // Derive the player slot from the verified sender clientId so a
            // misbehaving client cannot overwrite another player's intent.
            ulong sender = rpc.Receive.SenderClientId;
            if (!_clientToSlot.TryGetValue(sender, out int slot)) return;
            if (slot < 0 || slot >= _intents.Length) return;
            if (action < 0 || action >= ChefSimulation.NumActions) return;
            _intents[slot] = action;
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

                // Update replicated chef list.
                for (int i = 0; i < _sim.Chefs.Count; i++)
                {
                    Chefs[i] = ChefStateNet.From(_sim.Chefs[i]);
                }
                // Update replicated pot list using the cached, sorted key order.
                for (int i = 0; i < _potKeys.Length; i++)
                {
                    Pots[i] = PotStateNet.From(_potKeys[i], _sim.Pots[_potKeys[i]]);
                }
                // Update counter-item list. Counter items are sparse so we
                // rebuild the list each tick (typical layout has < 10 items).
                CounterItems.Clear();
                foreach (var kv in _sim.CounterItems)
                {
                    CounterItems.Add(CounterItemNet.From(kv.Key, kv.Value));
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

    /// <summary>
    /// Per-counter-item replicated snapshot. One entry per occupied counter tile.
    /// </summary>
    public struct CounterItemNet : INetworkSerializable, System.IEquatable<CounterItemNet>
    {
        public int X, Y;
        public byte Item;   // 1=Onion, 2=Dish, 3=Soup (None=0 should never replicate)

        public static CounterItemNet From(GridPos p, HeldItem item) => new CounterItemNet
        {
            X = p.X,
            Y = p.Y,
            Item = (byte)item,
        };

        public void NetworkSerialize<T>(BufferSerializer<T> s) where T : IReaderWriter
        {
            s.SerializeValue(ref X);
            s.SerializeValue(ref Y);
            s.SerializeValue(ref Item);
        }

        public bool Equals(CounterItemNet o) => X == o.X && Y == o.Y && Item == o.Item;
        public override bool Equals(object obj) => obj is CounterItemNet o && Equals(o);
        public override int GetHashCode() => (X * 73856093) ^ (Y * 19349663) ^ Item;
    }
}
