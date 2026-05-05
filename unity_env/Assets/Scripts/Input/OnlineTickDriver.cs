// OnlineTickDriver.cs
// Phase G-Network for GRACE.
//
// Owner-only 8 Hz driver that polls a PlayerInputController and forwards the
// latched intent to the host via NetworkChefAgent.SubmitAction. Without this
// component an online client can render the kitchen but cannot move its chef:
// PlayerInputController.FlushIntent() is never called and SubmitIntentServerRpc
// is never sent.
//
// Attach to the NetworkChef prefab alongside NetworkChefAgent and a sibling /
// child PlayerInputController. The host's NetworkKitchen drives the simulation
// itself; this component only handles the *client's* intent submission.

using Grace.Unity.Network;
using Unity.Netcode;
using UnityEngine;

namespace Grace.Unity.Input
{
    /// <summary>
    /// Owner-only client tick driver. Sends the latched action intent to the
    /// host once per simulation tick (default 8 Hz, mirroring NetworkKitchen).
    /// </summary>
    [RequireComponent(typeof(NetworkChefAgent))]
    public sealed class OnlineTickDriver : NetworkBehaviour
    {
        [Tooltip("Tick rate in Hz. Should match NetworkKitchen.ticksPerSecond.")]
        public float TicksPerSecond = 8f;

        [Tooltip("Input source. If unset, falls back to GetComponentInChildren.")]
        public PlayerInputController Input;

        private NetworkChefAgent _agent;
        private float _accumulator;

        private void Awake()
        {
            _agent = GetComponent<NetworkChefAgent>();
            if (Input == null) Input = GetComponentInChildren<PlayerInputController>();
        }

        public override void OnNetworkSpawn()
        {
            // Wire the input controller's NetworkAgent target so its convenience
            // forwarder also lands on this agent (defense in depth — this driver
            // calls SubmitAction directly).
            if (Input != null && Input.NetworkAgent == null) Input.NetworkAgent = _agent;
        }

        private void Update()
        {
            if (!IsOwner) return;
            if (Input == null || _agent == null) return;

            _accumulator += Time.deltaTime;
            float dt = 1f / TicksPerSecond;
            // Drain whole ticks; cap at one submission per frame to avoid
            // double-submitting the same latched intent.
            if (_accumulator >= dt)
            {
                _accumulator -= dt;
                int action = Input.FlushIntent();
                _agent.SubmitAction(action);
            }
        }
    }
}
