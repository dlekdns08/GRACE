// CounterItemRenderer.cs
// Renders the items that chefs have placed on counter tiles. Reads
// NetworkKitchen.CounterItems (online) or ChefSimulation.CounterItems
// (offline) and spawns/destroys simple visuals (onion / dish / soup) at the
// matching world cells. Idempotent per frame: items added/removed in the
// sim show up / disappear within a tick.

using System.Collections.Generic;
using Grace.Unity.Core;
using Grace.Unity.Network;
using UnityEngine;

namespace Grace.Unity.Render
{
    /// <summary>Renders counter-top items (onion / dish / soup) from kitchen state.</summary>
    public sealed class CounterItemRenderer : MonoBehaviour
    {
        [Header("Source (one of these must be set)")]
        public NetworkKitchen Kitchen;
        public ChefSimulation OfflineSim;

        [Header("Visual prefabs (optional — spawned procedurally if null)")]
        public GameObject OnionPrefab;
        public GameObject DishPrefab;
        public GameObject SoupPrefab;

        [Header("Layout")]
        public float TileSize = 1f;
        public float ItemHeight = 0.55f;

        private readonly Dictionary<long, GameObject> _live = new Dictionary<long, GameObject>();

        private void Update()
        {
            CollectAndRender();
        }

        private void CollectAndRender()
        {
            // Build a "what should exist" map keyed by (x*10000+y) → item kind.
            var desired = new Dictionary<long, byte>();
            if (Kitchen != null && Kitchen.CounterItems != null)
            {
                for (int i = 0; i < Kitchen.CounterItems.Count; i++)
                {
                    var c = Kitchen.CounterItems[i];
                    desired[Key(c.X, c.Y)] = c.Item;
                }
            }
            else if (OfflineSim != null)
            {
                foreach (var kv in OfflineSim.CounterItems)
                    desired[Key(kv.Key.X, kv.Key.Y)] = (byte)kv.Value;
            }
            else { return; }

            // Remove visuals whose key no longer exists or whose kind changed.
            var stale = new List<long>();
            foreach (var kv in _live)
            {
                if (!desired.TryGetValue(kv.Key, out byte want) ||
                    kv.Value == null || kv.Value.GetComponent<CounterItemTag>()?.Kind != want)
                {
                    if (kv.Value != null) Destroy(kv.Value);
                    stale.Add(kv.Key);
                }
            }
            foreach (var k in stale) _live.Remove(k);

            // Spawn newly-needed visuals.
            foreach (var kv in desired)
            {
                if (_live.ContainsKey(kv.Key)) continue;
                int gx = (int)(kv.Key / 10000);
                int gy = (int)(kv.Key % 10000);
                var go = SpawnItem(kv.Value);
                if (go == null) continue;
                go.transform.SetParent(transform, false);
                go.transform.localPosition = new Vector3(gx * TileSize, ItemHeight, -gy * TileSize);
                go.AddComponent<CounterItemTag>().Kind = kv.Value;
                _live[kv.Key] = go;
            }
        }

        private GameObject SpawnItem(byte kind)
        {
            GameObject prefab = kind switch
            {
                1 => OnionPrefab,
                2 => DishPrefab,
                3 => SoupPrefab,
                _ => null,
            };
            if (prefab != null) return Instantiate(prefab);
            return MakeProcedural(kind);
        }

        private static GameObject MakeProcedural(byte kind)
        {
            var root = new GameObject($"CounterItem_{kind}");
            switch (kind)
            {
                case 1: // Onion
                    Build(root, PrimitiveType.Sphere, Vector3.zero, Vector3.one * 0.32f,
                        new Color(0.93f, 0.78f, 0.43f));
                    Build(root, PrimitiveType.Capsule, new Vector3(0f, 0.18f, 0f),
                        new Vector3(0.08f, 0.1f, 0.08f), new Color(0.40f, 0.65f, 0.28f));
                    break;
                case 2: // Dish
                    Build(root, PrimitiveType.Cylinder, Vector3.zero,
                        new Vector3(0.45f, 0.04f, 0.45f), new Color(0.96f, 0.96f, 0.96f));
                    break;
                case 3: // Soup (dish + yellow liquid)
                    Build(root, PrimitiveType.Cylinder, Vector3.zero,
                        new Vector3(0.45f, 0.05f, 0.45f), new Color(0.96f, 0.96f, 0.96f));
                    Build(root, PrimitiveType.Cylinder, new Vector3(0f, 0.04f, 0f),
                        new Vector3(0.40f, 0.025f, 0.40f), new Color(1.00f, 0.85f, 0.35f));
                    break;
            }
            return root;
        }

        private static void Build(GameObject parent, PrimitiveType type, Vector3 pos,
            Vector3 scale, Color color)
        {
            var p = GameObject.CreatePrimitive(type);
            p.transform.SetParent(parent.transform, false);
            p.transform.localPosition = pos;
            p.transform.localScale = scale;
            var col = p.GetComponent<Collider>();
            if (col != null) Destroy(col);
            var rend = p.GetComponent<Renderer>();
            if (rend != null)
            {
                var mat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
                if (mat.HasProperty("_BaseColor")) mat.SetColor("_BaseColor", color);
                rend.sharedMaterial = mat;
            }
        }

        private static long Key(int x, int y) => (long)x * 10000 + y;
    }

    /// <summary>Internal marker so we can detect when a counter cell's item kind changed.</summary>
    public sealed class CounterItemTag : MonoBehaviour
    {
        public byte Kind;
    }
}
