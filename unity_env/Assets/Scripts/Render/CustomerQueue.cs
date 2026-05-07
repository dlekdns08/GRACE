// CustomerQueue.cs
// Decorative queue of cartoon customers waiting near the serving counter.
// Builds N customers procedurally (sphere head + capsule body, varied colours),
// gently bobs each one, and triggers a hop+thumbs-up flash whenever
// SoupsServed increments. Pure cosmetic — does not touch simulation state.

using System.Collections.Generic;
using Grace.Unity.Core;
using Grace.Unity.Network;
using UnityEngine;

namespace Grace.Unity.Render
{
    /// <summary>Spawns cartoon customers near the serving counter and reacts to served soups.</summary>
    public sealed class CustomerQueue : MonoBehaviour
    {
        [Header("Source (one of these must be set)")]
        public NetworkKitchen Kitchen;
        public ChefSimulation OfflineSim;

        [Header("Queue placement")]
        [Tooltip("World position of the first customer; queue stretches along +X.")]
        public Vector3 QueueOrigin = new Vector3(2.5f, 0f, 2.5f);
        [Tooltip("Direction the queue stretches in (will be normalised).")]
        public Vector3 QueueDirection = new Vector3(1f, 0f, 0f);
        public int CustomerCount = 4;
        public float Spacing = 1.1f;

        [Header("Animation")]
        public float BobAmplitude = 0.08f;
        public float BobSpeed = 1.2f;
        public float CheerHopHeight = 0.6f;
        public float CheerDuration = 0.5f;

        private static readonly Color[] OutfitPalette = new Color[]
        {
            new Color(0.36f, 0.55f, 0.85f),  // blue
            new Color(0.85f, 0.45f, 0.55f),  // pink
            new Color(0.55f, 0.40f, 0.75f),  // purple
            new Color(0.55f, 0.75f, 0.40f),  // green
            new Color(0.85f, 0.65f, 0.30f),  // amber
        };

        private readonly List<Customer> _customers = new List<Customer>();
        private int _lastSoups = -1;
        private float _cheerTimer;
        private int _cheerIndex = -1;

        private void Start()
        {
            BuildCustomers();
        }

        private void BuildCustomers()
        {
            var dir = QueueDirection.sqrMagnitude < 1e-4f
                ? Vector3.right
                : QueueDirection.normalized;

            for (int i = 0; i < CustomerCount; i++)
            {
                var c = new Customer();
                c.Root = new GameObject($"Customer_{i}");
                c.Root.transform.SetParent(transform, false);
                c.Root.transform.localPosition = QueueOrigin + dir * (i * Spacing);
                c.BasePosition = c.Root.transform.localPosition;
                c.PhaseOffset = i * 0.7f;

                var color = OutfitPalette[i % OutfitPalette.Length];

                // Body
                BuildPart(c.Root, PrimitiveType.Capsule,
                    new Vector3(0f, 0.55f, 0f), new Vector3(0.45f, 0.55f, 0.45f), color);
                // Head
                var head = BuildPart(c.Root, PrimitiveType.Sphere,
                    new Vector3(0f, 1.25f, 0f), Vector3.one * 0.45f,
                    new Color(1f, 0.83f, 0.66f));
                // Eyes
                BuildPart(head, PrimitiveType.Sphere,
                    new Vector3(-0.13f, 0.05f, 0.18f), Vector3.one * 0.07f, Color.black);
                BuildPart(head, PrimitiveType.Sphere,
                    new Vector3(0.13f, 0.05f, 0.18f), Vector3.one * 0.07f, Color.black);
                // Mouth
                BuildPart(head, PrimitiveType.Cube,
                    new Vector3(0f, -0.1f, 0.20f), new Vector3(0.18f, 0.04f, 0.02f),
                    new Color(0.55f, 0.20f, 0.18f));

                // Thought bubble (hidden by default; flashes on cheer)
                c.Cheer = new GameObject("Cheer");
                c.Cheer.transform.SetParent(c.Root.transform, false);
                c.Cheer.transform.localPosition = new Vector3(0f, 1.9f, 0f);
                BuildPart(c.Cheer, PrimitiveType.Sphere, Vector3.zero, Vector3.one * 0.4f,
                    new Color(1f, 1f, 0.5f, 0.9f));
                BuildPart(c.Cheer, PrimitiveType.Cube, new Vector3(0f, 0.05f, 0f),
                    new Vector3(0.18f, 0.18f, 0.04f), Color.white);
                c.Cheer.SetActive(false);

                _customers.Add(c);
            }
        }

        private static GameObject BuildPart(GameObject parent, PrimitiveType type,
            Vector3 pos, Vector3 scale, Color color)
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
                if (color.a < 1f && mat.HasProperty("_Surface"))
                {
                    mat.SetFloat("_Surface", 1f);
                    mat.renderQueue = 3000;
                }
                rend.sharedMaterial = mat;
            }
            return p;
        }

        private void Update()
        {
            int soups = ReadSoups();
            if (_lastSoups < 0) _lastSoups = soups;
            if (soups > _lastSoups)
            {
                TriggerCheer();
                _lastSoups = soups;
            }

            float t = Time.time;
            for (int i = 0; i < _customers.Count; i++)
            {
                var c = _customers[i];
                float bob = Mathf.Sin((t + c.PhaseOffset) * BobSpeed) * BobAmplitude;
                Vector3 p = c.BasePosition + new Vector3(0f, Mathf.Abs(bob), 0f);
                if (i == _cheerIndex && _cheerTimer > 0f)
                {
                    float frac = 1f - (_cheerTimer / CheerDuration);
                    float arc = Mathf.Sin(frac * Mathf.PI);
                    p += Vector3.up * arc * CheerHopHeight;
                }
                c.Root.transform.localPosition = p;
            }

            if (_cheerTimer > 0f)
            {
                _cheerTimer -= Time.deltaTime;
                if (_cheerTimer <= 0f && _cheerIndex >= 0 && _cheerIndex < _customers.Count)
                {
                    _customers[_cheerIndex].Cheer.SetActive(false);
                    _cheerIndex = -1;
                }
            }
        }

        private int ReadSoups()
        {
            if (Kitchen != null) return Kitchen.SoupsServed.Value;
            if (OfflineSim != null) return OfflineSim.SoupsServed;
            return 0;
        }

        private void TriggerCheer()
        {
            if (_customers.Count == 0) return;
            _cheerIndex = Random.Range(0, _customers.Count);
            _cheerTimer = CheerDuration;
            _customers[_cheerIndex].Cheer.SetActive(true);
        }

        private sealed class Customer
        {
            public GameObject Root;
            public GameObject Cheer;
            public Vector3 BasePosition;
            public float PhaseOffset;
        }
    }
}
