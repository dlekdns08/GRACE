// RepairGameRoom.cs
// Idempotent repair pass for an already-built 02_GameRoom scene.
// - Registers the NetworkChef prefab in NetworkManager's NetworkConfig.Prefabs
//   so runtime Instantiate+Spawn calls succeed.
// - Recomputes GlobalObjectIdHash on every scene-placed NetworkObject so two
//   programmatically-added NetworkObjects don't both end up with hash 0
//   (NGO refuses to spawn duplicates).
// Run via Tools → GRACE → Repair 02_GameRoom.

using System.Collections.Generic;
using System.Reflection;
using Grace.Unity.Network;
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

            // 0. Recompute GlobalObjectIdHash on every scene-placed NetworkObject.
            // Necessary when NetworkObjects were added programmatically because
            // OnValidate often won't have fired with a non-null GlobalObjectId yet.
            foreach (var no in Object.FindObjectsByType<NetworkObject>(FindObjectsSortMode.None))
            {
                if (RegenerateHash(no))
                {
                    EditorUtility.SetDirty(no);
                    Debug.Log($"[GRACE Repair] Regenerated GlobalObjectIdHash on {no.gameObject.name} → {no.GetType().GetField("GlobalObjectIdHash", BindingFlags.Instance | BindingFlags.NonPublic)?.GetValue(no)}.");
                    changes++;
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
    }
}
