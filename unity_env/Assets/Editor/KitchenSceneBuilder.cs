// KitchenSceneBuilder.cs
// Phase G2 (Render layer) editor tooling for GRACE.
//
// One-click scaffolding for the gameplay scene `02_GameRoom.unity`. Drops in
// the minimum gray-box objects so the project is buildable without a manual
// scene wiring pass:
//   * NetworkManager (with UnityTransport) + RelayBootstrap + NetworkSetup
//   * Kitchen GameObject (NetworkObject + NetworkKitchen + RoundEndCoordinator)
//   * KitchenRenderer with auto-generated primitive prefabs per TileKind
//   * NetworkPlayerSpawner with a generated NetworkChef prefab
//   * CameraRig with a tilted top-down framing
//   * Directional light
//
// The generated assets (.prefab) live under `Assets/_Generated/` so they are
// easy to delete and re-create. Real art replaces the gray boxes in Phase G3.

using System.IO;
using Grace.Unity.Network;
using Grace.Unity.Render;
using Unity.Netcode;
using Unity.Netcode.Transports.UTP;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Grace.Unity.EditorTools
{
    /// <summary>
    /// Editor-only utilities to scaffold scenes and gray-box prefabs. Open via
    /// <c>Tools → GRACE → Build 02_GameRoom Scaffold</c>.
    /// </summary>
    public static class KitchenSceneBuilder
    {
        private const string GeneratedDir = "Assets/_Generated";
        private const string ScenesDir = "Assets/Scenes";

        [MenuItem("Tools/GRACE/Build 02_GameRoom Scaffold")]
        public static void BuildGameRoomScene()
        {
            EnsureDir(GeneratedDir);
            EnsureDir(ScenesDir);

            // Create primitive tile prefabs.
            var floor = CreateTilePrefab("Floor", PrimitiveType.Cube, new Color(0.85f, 0.85f, 0.85f), 0.05f);
            var counter = CreateTilePrefab("Counter", PrimitiveType.Cube, new Color(0.55f, 0.45f, 0.30f), 0.6f);
            var wall = CreateTilePrefab("Wall", PrimitiveType.Cube, new Color(0.20f, 0.20f, 0.20f), 1.0f);
            var onion = CreateTilePrefab("OnionDispenser", PrimitiveType.Cube, new Color(1.0f, 0.85f, 0.30f), 0.8f);
            var dish = CreateTilePrefab("DishDispenser", PrimitiveType.Cube, new Color(0.75f, 0.85f, 1.0f), 0.8f);
            var pot = CreateTilePrefab("Pot", PrimitiveType.Cylinder, new Color(0.30f, 0.30f, 0.30f), 0.6f);
            var serve = CreateTilePrefab("ServingCounter", PrimitiveType.Cube, new Color(0.30f, 0.85f, 0.30f), 0.6f);
            var chef = CreateNetworkChefPrefab();

            // Create scene.
            var scene = EditorSceneManager.NewScene(
                NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // Light + skybox.
            var lightGO = new GameObject("DirectionalLight");
            var light = lightGO.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1.1f;
            lightGO.transform.rotation = Quaternion.Euler(45f, -30f, 0f);

            // Camera rig.
            var camGO = new GameObject("CameraRig");
            camGO.tag = "MainCamera";
            var cam = camGO.AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.10f, 0.12f, 0.16f);
            camGO.transform.position = new Vector3(2.5f, 6f, -3f);
            camGO.transform.rotation = Quaternion.Euler(45f, 0f, 0f);
            camGO.AddComponent<AudioListener>();
            camGO.AddComponent<CameraRig>();

            // NetworkManager + Transport + Relay + NetworkSetup.
            var nmGO = new GameObject("NetworkManager");
            var nm = nmGO.AddComponent<NetworkManager>();
            var transport = nmGO.AddComponent<UnityTransport>();
            nm.NetworkConfig = new NetworkConfig
            {
                NetworkTransport = transport,
                ConnectionApproval = false,
            };
            nmGO.AddComponent<RelayBootstrap>();
            nmGO.AddComponent<NetworkSetup>();
            nmGO.AddComponent<GameRoomBootstrap>();

            // Kitchen GameObject.
            var kitchenGO = new GameObject("Kitchen");
            kitchenGO.AddComponent<NetworkObject>();
            var kitchen = kitchenGO.AddComponent<NetworkKitchen>();
            kitchen.LayoutName = "cramped_room";
            kitchenGO.AddComponent<RoundEndCoordinator>();

            // Kitchen renderer.
            var rendGO = new GameObject("KitchenRenderer");
            var renderer = rendGO.AddComponent<KitchenRenderer>();
            renderer.LayoutName = "cramped_room";
            renderer.FloorPrefab = floor;
            renderer.CounterPrefab = counter;
            renderer.WallPrefab = wall;
            renderer.OnionDispenserPrefab = onion;
            renderer.DishDispenserPrefab = dish;
            renderer.PotPrefab = pot;
            renderer.ServingCounterPrefab = serve;

            // Player spawner.
            var spawnerGO = new GameObject("PlayerSpawner");
            spawnerGO.AddComponent<NetworkObject>();
            var spawner = spawnerGO.AddComponent<NetworkPlayerSpawner>();
            spawner.NetworkChefPrefab = chef;
            spawner.Kitchen = kitchen;

            // Save scene.
            string scenePath = Path.Combine(ScenesDir, "02_GameRoom.unity");
            EditorSceneManager.SaveScene(scene, scenePath);
            EditorBuildSettingsScene[] existing = EditorBuildSettings.scenes;
            bool registered = false;
            foreach (var s in existing) if (s.path == scenePath) { registered = true; break; }
            if (!registered)
            {
                var list = new System.Collections.Generic.List<EditorBuildSettingsScene>(existing)
                {
                    new EditorBuildSettingsScene(scenePath, true),
                };
                EditorBuildSettings.scenes = list.ToArray();
            }

            // Register the chef prefab as the auto-spawn player object.
            nm.NetworkConfig.PlayerPrefab = chef;

            // Register a NetworkPrefabsList so manual Spawn calls on NetworkChef
            // (NetworkPlayerSpawner.Instantiate + SpawnAsPlayerObject) succeed.
            EnsurePrefabList(nm, chef);

            // Save once so each scene-placed NetworkObject gets a stable
            // GlobalObjectId, then regenerate the GlobalObjectIdHash on each
            // (NGO's OnValidate doesn't auto-fire after programmatic AddComponent,
            // which would leave both Kitchen and PlayerSpawner with hash 0 and
            // make StartHost throw "ScenePlacedObjects already contains hash 0").
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, scenePath);
            RegenerateSceneNetworkHashes();
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, scenePath);

            Debug.Log($"[GRACE KitchenSceneBuilder] Built scene at {scenePath}");
        }

        private static void RegenerateSceneNetworkHashes()
        {
            var type = typeof(NetworkObject);
            var hashField = type.GetField("GlobalObjectIdHash",
                System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
            var validate = type.GetMethod("OnValidate",
                System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
            if (hashField == null) return;

            foreach (var no in Object.FindObjectsByType<NetworkObject>(FindObjectsSortMode.None))
            {
                if (validate != null)
                {
                    try { validate.Invoke(no, null); } catch { /* fall through */ }
                }
                if ((uint)hashField.GetValue(no) == 0u)
                {
                    string path = no.gameObject.scene.name + "/" + no.gameObject.name;
                    uint fallback = unchecked((uint)path.GetHashCode());
                    if (fallback == 0) fallback = 1;
                    hashField.SetValue(no, fallback);
                }
                EditorUtility.SetDirty(no);
            }
        }

        private static void EnsurePrefabList(NetworkManager nm, GameObject chef)
        {
            const string path = "Assets/Settings/GraceNetworkPrefabsList.asset";
            if (!Directory.Exists("Assets/Settings"))
                Directory.CreateDirectory("Assets/Settings");

            var list = AssetDatabase.LoadAssetAtPath<NetworkPrefabsList>(path);
            if (list == null)
            {
                list = ScriptableObject.CreateInstance<NetworkPrefabsList>();
                AssetDatabase.CreateAsset(list, path);
            }

            bool already = false;
            foreach (var p in list.PrefabList)
                if (p != null && p.Prefab == chef) { already = true; break; }
            if (!already) list.Add(new NetworkPrefab { Prefab = chef });
            EditorUtility.SetDirty(list);
            AssetDatabase.SaveAssets();

            if (!nm.NetworkConfig.Prefabs.NetworkPrefabsLists.Contains(list))
                nm.NetworkConfig.Prefabs.NetworkPrefabsLists.Add(list);
        }

        private static GameObject CreateTilePrefab(string name, PrimitiveType prim, Color tint, float height)
        {
            string path = $"{GeneratedDir}/{name}.prefab";
            var existing = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if (existing != null) return existing;

            var go = GameObject.CreatePrimitive(prim);
            go.name = name;
            go.transform.localScale = new Vector3(0.95f, height, 0.95f);
            go.transform.position = new Vector3(0f, height * 0.5f - 0.025f, 0f);
            var renderer = go.GetComponent<MeshRenderer>();
            renderer.sharedMaterial = new Material(Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard"))
            {
                name = $"{name}_Mat",
                color = tint,
            };
            AssetDatabase.CreateAsset(renderer.sharedMaterial, $"{GeneratedDir}/{name}_Mat.mat");

            var prefab = PrefabUtility.SaveAsPrefabAsset(go, path);
            Object.DestroyImmediate(go);
            return prefab;
        }

        private static GameObject CreateNetworkChefPrefab()
        {
            string path = $"{GeneratedDir}/NetworkChef.prefab";
            var existing = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if (existing != null) return existing;

            var go = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            go.name = "NetworkChef";
            go.transform.localScale = new Vector3(0.6f, 0.6f, 0.6f);
            var renderer = go.GetComponent<MeshRenderer>();
            renderer.sharedMaterial = new Material(Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard"))
            {
                name = "NetworkChef_Mat",
                color = new Color(0.95f, 0.45f, 0.35f),
            };
            AssetDatabase.CreateAsset(renderer.sharedMaterial, $"{GeneratedDir}/NetworkChef_Mat.mat");

            go.AddComponent<NetworkObject>();
            var agent = go.AddComponent<NetworkChefAgent>();
            go.AddComponent<Grace.Unity.Input.PlayerInputController>();
            go.AddComponent<Grace.Unity.Input.OnlineTickDriver>();

            // Visual components — without these the chef stays at world (0,0,0)
            // even though replicated state moves on the simulation grid.
            var interp = go.AddComponent<Grace.Unity.Render.MovementInterpolator>();
            interp.tileSize = 1f;
            interp.lerpDuration = 0.15f;
            var visual = go.AddComponent<Grace.Unity.Render.ChefVisual>();
            visual.NetworkAgent = agent;
            visual.Interpolator = interp;
            visual.BodyTransform = go.transform;

            var prefab = PrefabUtility.SaveAsPrefabAsset(go, path);
            Object.DestroyImmediate(go);
            return prefab;
        }

        private static void EnsureDir(string path)
        {
            if (!Directory.Exists(path)) Directory.CreateDirectory(path);
            // AssetDatabase needs a refresh after raw FS creation.
            AssetDatabase.Refresh();
        }
    }
}
