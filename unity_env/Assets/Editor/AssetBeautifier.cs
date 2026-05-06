// AssetBeautifier.cs
// One-shot upgrader that turns the placeholder primitives in Assets/_Generated
// into a recognizable cartoon kitchen + chefs:
//   - NetworkChef gets a body (capsule), head (sphere), chef hat (cylinder),
//     two arms (small spheres) and held-item children (Onion / Dish / Soup).
//   - ChefVisual slots are auto-wired (NetworkAgent, Interpolator, BodyTransform,
//     HeldOnion, HeldDish, HeldSoup).
//   - Each tile prefab gets a thematic decoration child + a clearer material color.
//
// Run via menu: Tools → GRACE → Beautify Assets
//
// Idempotent: replaces decorative children if they already exist, so you can
// re-run safely after tweaking.

using System.IO;
using Grace.Unity.Network;
using Grace.Unity.Render;
using UnityEditor;
using UnityEngine;

namespace Grace.Unity.EditorTools
{
    public static class AssetBeautifier
    {
        private const string GeneratedDir = "Assets/_Generated";
        private const string DecoTag = "_Deco";   // suffix used to recognise decoration children

        // ---------- Material palette --------------------------------------

        private static readonly Color FloorColor          = new Color(0.93f, 0.88f, 0.78f);  // warm cream
        private static readonly Color CounterColor        = new Color(0.65f, 0.46f, 0.30f);  // wood
        private static readonly Color WallColor           = new Color(0.45f, 0.32f, 0.22f);  // dark wood
        private static readonly Color OnionDispenserColor = new Color(0.96f, 0.82f, 0.30f);  // saturated yellow
        private static readonly Color DishDispenserColor  = new Color(0.78f, 0.94f, 1.00f);  // pale ice-blue
        private static readonly Color PotColor            = new Color(0.20f, 0.20f, 0.22f);  // matte dark
        private static readonly Color ServingCounterColor = new Color(0.45f, 0.85f, 0.45f);  // mint
        private static readonly Color ChefBodyP1          = new Color(0.86f, 0.30f, 0.30f);  // chef coat red
        private static readonly Color ChefSkin            = new Color(1.00f, 0.83f, 0.66f);
        private static readonly Color ChefHat             = Color.white;
        private static readonly Color OnionSkin           = new Color(0.93f, 0.78f, 0.43f);
        private static readonly Color OnionStem           = new Color(0.40f, 0.65f, 0.28f);
        private static readonly Color DishWhite           = new Color(0.96f, 0.96f, 0.96f);
        private static readonly Color SoupYellow          = new Color(1.00f, 0.85f, 0.35f);

        [MenuItem("Tools/GRACE/Beautify Assets")]
        public static void BeautifyAll()
        {
            BeautifyMaterials();
            BeautifyTilePrefab("Floor",           withDeco: false);
            BeautifyTilePrefab("Counter",         withDeco: false);
            BeautifyTilePrefab("Wall",            withDeco: false);
            BeautifyOnionDispenser();
            BeautifyDishDispenser();
            BeautifyPot();
            BeautifyServingCounter();
            BeautifyChef();
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            EditorUtility.DisplayDialog(
                "GRACE",
                "에셋 업그레이드 완료!\n\n" +
                "1) 00_Title 씬으로 가서 Play\n" +
                "2) Solo vs AI 클릭\n" +
                "3) WASD로 셰프 조작",
                "OK");
        }

        // -------------------------- Materials -----------------------------

        private static void BeautifyMaterials()
        {
            SetMatColor("Floor_Mat",           FloorColor);
            SetMatColor("Counter_Mat",         CounterColor);
            SetMatColor("Wall_Mat",            WallColor);
            SetMatColor("OnionDispenser_Mat",  OnionDispenserColor);
            SetMatColor("DishDispenser_Mat",   DishDispenserColor);
            SetMatColor("Pot_Mat",             PotColor,            smoothness: 0.6f, metallic: 0.7f);
            SetMatColor("ServingCounter_Mat",  ServingCounterColor);
            SetMatColor("NetworkChef_Mat",     ChefBodyP1);
        }

        private static void SetMatColor(string name, Color color, float smoothness = 0.25f, float metallic = 0f)
        {
            string path = $"{GeneratedDir}/{name}.mat";
            var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null) { Debug.LogWarning($"[Beautifier] Missing material: {path}"); return; }
            if (mat.HasProperty("_BaseColor"))   mat.SetColor("_BaseColor", color);
            if (mat.HasProperty("_Color"))       mat.SetColor("_Color", color);
            if (mat.HasProperty("_Smoothness"))  mat.SetFloat("_Smoothness", smoothness);
            if (mat.HasProperty("_Metallic"))    mat.SetFloat("_Metallic", metallic);
            EditorUtility.SetDirty(mat);
        }

        // -------------------------- Tiles ---------------------------------

        private static void BeautifyTilePrefab(string name, bool withDeco)
        {
            string path = $"{GeneratedDir}/{name}.prefab";
            var go = PrefabUtility.LoadPrefabContents(path);
            if (go == null) return;
            try
            {
                ClearDecoChildren(go);
                if (withDeco) { /* per-prefab deco added by callers */ }
                PrefabUtility.SaveAsPrefabAsset(go, path);
            }
            finally { PrefabUtility.UnloadPrefabContents(go); }
        }

        private static void BeautifyOnionDispenser()
        {
            string path = $"{GeneratedDir}/OnionDispenser.prefab";
            var go = PrefabUtility.LoadPrefabContents(path);
            try
            {
                ClearDecoChildren(go);
                // Stack of three onions on top of the tile.
                for (int i = 0; i < 3; i++)
                {
                    float x = (i - 1) * 0.18f;
                    float y = 0.62f + (i % 2 == 0 ? 0f : 0.05f);
                    var onion = MakePrimitive(PrimitiveType.Sphere, $"Onion{i}{DecoTag}", go.transform,
                        new Vector3(x, y, 0f), Vector3.one * 0.28f, OnionSkin);
                    var stem = MakePrimitive(PrimitiveType.Capsule, $"Stem{i}{DecoTag}", onion.transform,
                        new Vector3(0f, 0.35f, 0f), new Vector3(0.15f, 0.4f, 0.15f), OnionStem);
                    StripCollider(stem);
                    StripCollider(onion);
                }
                PrefabUtility.SaveAsPrefabAsset(go, path);
            }
            finally { PrefabUtility.UnloadPrefabContents(go); }
        }

        private static void BeautifyDishDispenser()
        {
            string path = $"{GeneratedDir}/DishDispenser.prefab";
            var go = PrefabUtility.LoadPrefabContents(path);
            try
            {
                ClearDecoChildren(go);
                // Stack of 4 plates.
                for (int i = 0; i < 4; i++)
                {
                    var plate = MakePrimitive(PrimitiveType.Cylinder, $"Plate{i}{DecoTag}", go.transform,
                        new Vector3(0f, 0.55f + i * 0.04f, 0f),
                        new Vector3(0.55f, 0.02f, 0.55f),
                        DishWhite);
                    StripCollider(plate);
                }
                PrefabUtility.SaveAsPrefabAsset(go, path);
            }
            finally { PrefabUtility.UnloadPrefabContents(go); }
        }

        private static void BeautifyPot()
        {
            string path = $"{GeneratedDir}/Pot.prefab";
            var go = PrefabUtility.LoadPrefabContents(path);
            try
            {
                ClearDecoChildren(go);
                // Pot body (squat cylinder) sitting on the tile.
                var body = MakePrimitive(PrimitiveType.Cylinder, $"PotBody{DecoTag}", go.transform,
                    new Vector3(0f, 0.65f, 0f), new Vector3(0.7f, 0.25f, 0.7f), PotColor);
                StripCollider(body);
                // Two handles
                var handleL = MakePrimitive(PrimitiveType.Cube, $"HandleL{DecoTag}", body.transform,
                    new Vector3(-0.6f, 0f, 0f), new Vector3(0.2f, 0.15f, 0.4f), PotColor);
                StripCollider(handleL);
                var handleR = MakePrimitive(PrimitiveType.Cube, $"HandleR{DecoTag}", body.transform,
                    new Vector3(0.6f, 0f, 0f), new Vector3(0.2f, 0.15f, 0.4f), PotColor);
                StripCollider(handleR);
                // Steam puff (visible always; in real game PotVisual would toggle)
                var steam = MakePrimitive(PrimitiveType.Sphere, $"Steam{DecoTag}", go.transform,
                    new Vector3(0f, 1.2f, 0f), Vector3.one * 0.35f,
                    new Color(1f, 1f, 1f, 0.6f));
                StripCollider(steam);
                PrefabUtility.SaveAsPrefabAsset(go, path);
            }
            finally { PrefabUtility.UnloadPrefabContents(go); }
        }

        private static void BeautifyServingCounter()
        {
            string path = $"{GeneratedDir}/ServingCounter.prefab";
            var go = PrefabUtility.LoadPrefabContents(path);
            try
            {
                ClearDecoChildren(go);
                // A glowing star marker.
                var star = MakePrimitive(PrimitiveType.Cube, $"OrderUp{DecoTag}", go.transform,
                    new Vector3(0f, 0.55f, 0f), new Vector3(0.45f, 0.05f, 0.45f),
                    new Color(1f, 0.9f, 0.4f));
                StripCollider(star);
                // Tiny arrow marker
                var arrow = MakePrimitive(PrimitiveType.Cube, $"Arrow{DecoTag}", go.transform,
                    new Vector3(0f, 0.62f, 0f), new Vector3(0.15f, 0.12f, 0.15f),
                    new Color(1f, 0.5f, 0.2f));
                arrow.transform.localRotation = Quaternion.Euler(45f, 45f, 0f);
                StripCollider(arrow);
                PrefabUtility.SaveAsPrefabAsset(go, path);
            }
            finally { PrefabUtility.UnloadPrefabContents(go); }
        }

        // -------------------------- Chef ----------------------------------

        private static void BeautifyChef()
        {
            string path = $"{GeneratedDir}/NetworkChef.prefab";
            var go = PrefabUtility.LoadPrefabContents(path);
            try
            {
                ClearDecoChildren(go);

                // The root capsule already exists as the body. Tone its scale down a touch
                // so head/hat sit naturally above.
                go.transform.localScale = new Vector3(0.6f, 0.6f, 0.6f);

                // Body is the existing capsule on the root — paint via NetworkChef_Mat.
                // Add head, hat, arms, and an empty BodyParts root used as facing pivot.
                var bodyParts = new GameObject($"BodyParts{DecoTag}");
                bodyParts.transform.SetParent(go.transform, false);
                bodyParts.transform.localPosition = Vector3.zero;

                // Head (sphere)
                var head = MakePrimitive(PrimitiveType.Sphere, $"Head{DecoTag}", bodyParts.transform,
                    new Vector3(0f, 1.15f, 0f), Vector3.one * 0.55f, ChefSkin);
                StripCollider(head);

                // Hat (cylinder + sphere puff)
                var hat = MakePrimitive(PrimitiveType.Cylinder, $"Hat{DecoTag}", bodyParts.transform,
                    new Vector3(0f, 1.55f, 0f), new Vector3(0.48f, 0.28f, 0.48f), ChefHat);
                StripCollider(hat);
                var hatPuff = MakePrimitive(PrimitiveType.Sphere, $"HatPuff{DecoTag}", bodyParts.transform,
                    new Vector3(0f, 1.85f, 0f), Vector3.one * 0.62f, ChefHat);
                StripCollider(hatPuff);

                // Arms (small spheres)
                var armL = MakePrimitive(PrimitiveType.Sphere, $"ArmL{DecoTag}", bodyParts.transform,
                    new Vector3(-0.45f, 0.2f, 0f), Vector3.one * 0.32f, ChefSkin);
                StripCollider(armL);
                var armR = MakePrimitive(PrimitiveType.Sphere, $"ArmR{DecoTag}", bodyParts.transform,
                    new Vector3(0.45f, 0.2f, 0f), Vector3.one * 0.32f, ChefSkin);
                StripCollider(armR);

                // Eyes (tiny black spheres) facing +Z (which becomes "south" via ChefVisual rotation)
                var eyeL = MakePrimitive(PrimitiveType.Sphere, $"EyeL{DecoTag}", head.transform,
                    new Vector3(-0.18f, 0.05f, 0.42f), Vector3.one * 0.12f, Color.black);
                StripCollider(eyeL);
                var eyeR = MakePrimitive(PrimitiveType.Sphere, $"EyeR{DecoTag}", head.transform,
                    new Vector3(0.18f, 0.05f, 0.42f), Vector3.one * 0.12f, Color.black);
                StripCollider(eyeR);

                // Held items: anchored slightly in front of the chest. Inactive by default.
                var heldOnion = BuildHeldOnion(go.transform);
                var heldDish  = BuildHeldDish(go.transform);
                var heldSoup  = BuildHeldSoup(go.transform);

                // Wire ChefVisual slots if present.
                var visual = go.GetComponent<ChefVisual>();
                if (visual != null)
                {
                    visual.NetworkAgent = go.GetComponent<NetworkChefAgent>();
                    visual.Interpolator = go.GetComponent<MovementInterpolator>();
                    visual.BodyTransform = bodyParts.transform;
                    visual.HeldOnion = heldOnion;
                    visual.HeldDish = heldDish;
                    visual.HeldSoup = heldSoup;
                    EditorUtility.SetDirty(visual);
                }

                // Wire PlayerInputController.NetworkAgent for convenience.
                var input = go.GetComponent<Grace.Unity.Input.PlayerInputController>();
                if (input != null)
                {
                    input.NetworkAgent = go.GetComponent<NetworkChefAgent>();
                    EditorUtility.SetDirty(input);
                }

                PrefabUtility.SaveAsPrefabAsset(go, path);
            }
            finally { PrefabUtility.UnloadPrefabContents(go); }
        }

        private static GameObject BuildHeldOnion(Transform parent)
        {
            var root = new GameObject($"HeldOnion{DecoTag}");
            root.transform.SetParent(parent, false);
            root.transform.localPosition = new Vector3(0f, 0.4f, 0.55f);
            var skin = MakePrimitive(PrimitiveType.Sphere, "Skin", root.transform,
                Vector3.zero, Vector3.one * 0.32f, OnionSkin);
            StripCollider(skin);
            var stem = MakePrimitive(PrimitiveType.Capsule, "Stem", root.transform,
                new Vector3(0f, 0.18f, 0f), new Vector3(0.08f, 0.1f, 0.08f), OnionStem);
            StripCollider(stem);
            root.SetActive(false);
            return root;
        }

        private static GameObject BuildHeldDish(Transform parent)
        {
            var root = new GameObject($"HeldDish{DecoTag}");
            root.transform.SetParent(parent, false);
            root.transform.localPosition = new Vector3(0f, 0.4f, 0.55f);
            var disk = MakePrimitive(PrimitiveType.Cylinder, "Disk", root.transform,
                Vector3.zero, new Vector3(0.45f, 0.04f, 0.45f), DishWhite);
            StripCollider(disk);
            root.SetActive(false);
            return root;
        }

        private static GameObject BuildHeldSoup(Transform parent)
        {
            var root = new GameObject($"HeldSoup{DecoTag}");
            root.transform.SetParent(parent, false);
            root.transform.localPosition = new Vector3(0f, 0.4f, 0.55f);
            var bowl = MakePrimitive(PrimitiveType.Cylinder, "Bowl", root.transform,
                Vector3.zero, new Vector3(0.45f, 0.05f, 0.45f), DishWhite);
            StripCollider(bowl);
            var liquid = MakePrimitive(PrimitiveType.Cylinder, "Liquid", root.transform,
                new Vector3(0f, 0.04f, 0f), new Vector3(0.40f, 0.025f, 0.40f), SoupYellow);
            StripCollider(liquid);
            root.SetActive(false);
            return root;
        }

        // -------------------------- Helpers -------------------------------

        private static GameObject MakePrimitive(PrimitiveType type, string name, Transform parent,
            Vector3 localPos, Vector3 localScale, Color color)
        {
            var go = GameObject.CreatePrimitive(type);
            go.name = name;
            go.transform.SetParent(parent, false);
            go.transform.localPosition = localPos;
            go.transform.localScale = localScale;
            var rend = go.GetComponent<Renderer>();
            if (rend != null)
            {
                var mat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
                if (mat.HasProperty("_BaseColor")) mat.SetColor("_BaseColor", color);
                if (mat.HasProperty("_Color"))     mat.SetColor("_Color", color);
                if (color.a < 1f && mat.HasProperty("_Surface"))
                {
                    mat.SetFloat("_Surface", 1f); // transparent
                    mat.renderQueue = 3000;
                }
                rend.sharedMaterial = mat;
            }
            return go;
        }

        private static void StripCollider(GameObject go)
        {
            var col = go.GetComponent<Collider>();
            if (col != null) Object.DestroyImmediate(col, true);
        }

        private static void ClearDecoChildren(GameObject root)
        {
            for (int i = root.transform.childCount - 1; i >= 0; i--)
            {
                var child = root.transform.GetChild(i);
                if (child.name.EndsWith(DecoTag) || child.name.Contains(DecoTag))
                    Object.DestroyImmediate(child.gameObject, true);
            }
        }
    }
}
