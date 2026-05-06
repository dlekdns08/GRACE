// RepairGameRoom.cs
// Idempotent repair pass for an already-built 02_GameRoom scene + chef prefab.
// - Registers the NetworkChef prefab in NetworkManager's NetworkConfig.Prefabs
//   so runtime Instantiate+Spawn calls succeed.
// - Recomputes GlobalObjectIdHash on every scene-placed NetworkObject so two
//   programmatically-added NetworkObjects don't both end up with hash 0
//   (NGO refuses to spawn duplicates).
// - Adds ChefVisual + MovementInterpolator to NetworkChef.prefab so spawned
//   chefs visibly follow their replicated grid position. Without these, the
//   chef stays at world (0,0,0) even though the simulation moves it.
// Run via Tools → GRACE → Repair 02_GameRoom.

using System.Collections.Generic;
using System.Reflection;
using Grace.Unity.Network;
using Grace.Unity.Render;
using Unity.Netcode;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Grace.Unity.EditorTools
{
    public static class RepairGameRoom
    {
        private const string ChefPrefabPath = "Assets/_Generated/NetworkChef.prefab";

        [MenuItem("Tools/GRACE/Repair 02_GameRoom")]
        public static void Repair()
        {
            var nm = Object.FindAnyObjectByType<NetworkManager>();
            if (nm == null)
            {
                Debug.LogError("[GRACE Repair] No NetworkManager in current scene. Open 02_GameRoom first.");
                return;
            }

            int changes = 0;

            // 0. Force a unique GlobalObjectIdHash on every scene-placed NetworkObject.
            // OnValidate doesn't reliably update the hash for NetworkObjects that were
            // added programmatically — they all stay at 0, and NGO refuses to spawn
            // duplicates (Exception: "ScenePlacedObjects already contains hash 0").
            foreach (var no in Object.FindObjectsByType<NetworkObject>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                uint before = ReadHash(no);
                if (RegenerateHash(no))
                {
                    EditorUtility.SetDirty(no);
                    uint after = ReadHash(no);
                    Debug.Log($"[GRACE Repair] {no.gameObject.name}: GlobalObjectIdHash {before} → {after}.");
                    changes++;
                }
                else
                {
                    Debug.LogWarning($"[GRACE Repair] {no.gameObject.name}: hash unchanged ({before}). Will be force-set if 0.");
                }
            }

            // 2. Ensure a NetworkPrefabsList exists and contains NetworkChef.
            var chef = AssetDatabase.LoadAssetAtPath<GameObject>(ChefPrefabPath);
            if (chef == null)
            {
                Debug.LogWarning($"[GRACE Repair] NetworkChef prefab not found at {ChefPrefabPath}. Run Build 02_GameRoom Scaffold first.");
            }
            else
            {
                var list = EnsurePrefabList();
                if (list != null && !ContainsPrefab(list, chef))
                {
                    list.Add(new NetworkPrefab { Prefab = chef });
                    EditorUtility.SetDirty(list);
                    AssetDatabase.SaveAssets();
                    Debug.Log("[GRACE Repair] Added NetworkChef to NetworkPrefabsList.");
                    changes++;
                }

                if (list != null && !nm.NetworkConfig.Prefabs.NetworkPrefabsLists.Contains(list))
                {
                    nm.NetworkConfig.Prefabs.NetworkPrefabsLists.Add(list);
                    Debug.Log("[GRACE Repair] Hooked NetworkPrefabsList into NetworkManager.NetworkConfig.");
                    changes++;
                }

                if (nm.NetworkConfig.PlayerPrefab != chef)
                {
                    nm.NetworkConfig.PlayerPrefab = chef;
                    Debug.Log("[GRACE Repair] Reassigned NetworkConfig.PlayerPrefab → NetworkChef.");
                    changes++;
                }
            }

            // 3. Make sure the NetworkChef prefab has visual components so
            // spawned chefs actually move on screen.
            if (chef != null && RepairChefPrefab(chef))
            {
                Debug.Log("[GRACE Repair] Patched NetworkChef prefab with ChefVisual + MovementInterpolator.");
                changes++;
            }

            if (changes > 0)
            {
                EditorUtility.SetDirty(nm);
                EditorSceneManager.MarkSceneDirty(nm.gameObject.scene);
                EditorSceneManager.SaveScene(nm.gameObject.scene);
                Debug.Log($"[GRACE Repair] Saved scene with {changes} change(s).");
            }
            else
            {
                Debug.Log("[GRACE Repair] No changes needed; scene already up to date.");
            }
        }

        private static bool RepairChefPrefab(GameObject chefAsset)
        {
            string path = AssetDatabase.GetAssetPath(chefAsset);
            if (string.IsNullOrEmpty(path)) return false;

            var root = PrefabUtility.LoadPrefabContents(path);
            try
            {
                bool changed = false;

                var interp = root.GetComponent<MovementInterpolator>();
                if (interp == null)
                {
                    interp = root.AddComponent<MovementInterpolator>();
                    interp.tileSize = 1f;
                    interp.lerpDuration = 0.15f;
                    changed = true;
                }

                var visual = root.GetComponent<ChefVisual>();
                if (visual == null)
                {
                    visual = root.AddComponent<ChefVisual>();
                    changed = true;
                }
                if (visual.NetworkAgent == null)
                {
                    visual.NetworkAgent = root.GetComponent<Grace.Unity.Network.NetworkChefAgent>();
                    if (visual.NetworkAgent != null) changed = true;
                }
                if (visual.Interpolator == null)
                {
                    visual.Interpolator = interp;
                    changed = true;
                }
                if (visual.BodyTransform == null)
                {
                    visual.BodyTransform = root.transform;
                    changed = true;
                }

                if (changed)
                {
                    PrefabUtility.SaveAsPrefabAsset(root, path);
                }
                return changed;
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(root);
            }
        }

        private static NetworkPrefabsList EnsurePrefabList()
        {
            const string path = "Assets/Settings/GraceNetworkPrefabsList.asset";
            var list = AssetDatabase.LoadAssetAtPath<NetworkPrefabsList>(path);
            if (list != null) return list;

            if (!System.IO.Directory.Exists("Assets/Settings"))
                System.IO.Directory.CreateDirectory("Assets/Settings");

            list = ScriptableObject.CreateInstance<NetworkPrefabsList>();
            AssetDatabase.CreateAsset(list, path);
            AssetDatabase.SaveAssets();
            Debug.Log($"[GRACE Repair] Created {path}.");
            return list;
        }

        private static bool ContainsPrefab(NetworkPrefabsList list, GameObject prefab)
        {
            foreach (var p in list.PrefabList)
                if (p != null && p.Prefab == prefab) return true;
            return false;
        }

        /// <summary>
        /// Forces a unique non-zero GlobalObjectIdHash on the NetworkObject.
        /// Tries NGO's internal OnValidate first; if that leaves the hash at 0
        /// (common after programmatic AddComponent), assigns a deterministic
        /// fallback derived from the GameObject's scene path so two objects
        /// in the same scene end up with different hashes.
        /// Returns true if the hash actually changed.
        /// </summary>
        private static bool RegenerateHash(NetworkObject no)
        {
            var type = typeof(NetworkObject);
            var hashField = type.GetField("GlobalObjectIdHash",
                BindingFlags.Instance | BindingFlags.NonPublic);
            if (hashField == null) return false;

            uint before = (uint)hashField.GetValue(no);

            var validate = type.GetMethod("OnValidate",
                BindingFlags.Instance | BindingFlags.NonPublic);
            if (validate != null)
            {
                try { validate.Invoke(no, null); } catch { /* swallow — fallback below */ }
            }

            uint after = (uint)hashField.GetValue(no);
            if (after == 0)
            {
                // OnValidate didn't produce a non-zero hash (typical for
                // programmatically-created NetworkObjects). Derive a stable
                // hash from the scene path so siblings always differ.
                uint fallback = unchecked((uint)ScenePath(no.gameObject).GetHashCode());
                if (fallback == 0) fallback = 1;
                hashField.SetValue(no, fallback);
                after = fallback;
            }

            return before != after;
        }

        private static uint ReadHash(NetworkObject no)
        {
            var f = typeof(NetworkObject).GetField("GlobalObjectIdHash",
                BindingFlags.Instance | BindingFlags.NonPublic);
            return f != null ? (uint)f.GetValue(no) : 0u;
        }

        private static string ScenePath(GameObject go)
        {
            string path = go.name;
            var t = go.transform.parent;
            while (t != null)
            {
                path = t.name + "/" + path;
                t = t.parent;
            }
            return $"{go.scene.name}/{path}";
        }
    }
}
