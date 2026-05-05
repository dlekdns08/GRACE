// KitchenRenderer.cs
// Phase G2 (Render layer) for GRACE.
//
// Reads a Grace.Unity.Core.KitchenLayout and instantiates one tile prefab per
// non-Floor cell at world position (x*tile, 0, -y*tile). Cleared and rebuilt
// when Build() is called; both online (host loads layout) and offline use it.

using Grace.Unity.Core;
using UnityEngine;

namespace Grace.Unity.Render
{
    /// <summary>Instantiates kitchen tile prefabs at grid positions from a parsed layout.</summary>
    public sealed class KitchenRenderer : MonoBehaviour
    {
        [Header("Layout")]
        public string LayoutName = "cramped_room";
        public float TileSize = 1.0f;

        [Header("Tile prefabs")]
        public GameObject FloorPrefab;
        public GameObject CounterPrefab;
        public GameObject WallPrefab;
        public GameObject OnionDispenserPrefab;
        public GameObject DishDispenserPrefab;
        public GameObject PotPrefab;
        public GameObject ServingCounterPrefab;

        /// <summary>Last layout that was built. Null until Build() is called.</summary>
        public KitchenLayout CurrentLayout { get; private set; }

        /// <summary>Build (or rebuild) the kitchen from the named layout file.</summary>
        public void Build(string layoutName)
        {
            CurrentLayout = LayoutLoader.Load(layoutName);
            ClearChildren();

            for (int x = 0; x < CurrentLayout.Width; x++)
            {
                for (int y = 0; y < CurrentLayout.Height; y++)
                {
                    var tile = CurrentLayout.At(new GridPos(x, y));
                    var prefab = PrefabFor(tile);
                    if (prefab == null) continue;
                    var pos = new Vector3(x * TileSize, 0f, -y * TileSize);
                    var go = Instantiate(prefab, pos, Quaternion.identity, transform);
                    go.name = $"{tile}_{x}_{y}";
                }
            }
        }

        private void ClearChildren()
        {
            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                if (Application.isPlaying)
                    Destroy(transform.GetChild(i).gameObject);
                else
                    DestroyImmediate(transform.GetChild(i).gameObject);
            }
        }

        private GameObject PrefabFor(TileKind kind)
        {
            switch (kind)
            {
                case TileKind.Floor: return FloorPrefab;
                case TileKind.Counter: return CounterPrefab;
                case TileKind.Wall: return WallPrefab;
                case TileKind.OnionDispenser: return OnionDispenserPrefab;
                case TileKind.DishDispenser: return DishDispenserPrefab;
                case TileKind.Pot: return PotPrefab;
                case TileKind.ServingCounter: return ServingCounterPrefab;
                default: return null;
            }
        }

        private void Start()
        {
            if (!string.IsNullOrEmpty(LayoutName))
                Build(LayoutName);
        }
    }
}
