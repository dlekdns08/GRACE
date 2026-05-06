// RepairGameRoom.cs
// Idempotent repair pass for an already-built 02_GameRoom scene.
// Adds GameRoomBootstrap to the NetworkManager GO if missing, and registers
// the NetworkChef prefab in NetworkManager's NetworkConfig.Prefabs list so
// runtime Instantiate+Spawn calls succeed. Run via
// Tools → GRACE → Repair 02_GameRoom.

using System.Collections.Generic;
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

            // 1. Ensure GameRoomBootstrap is attached.
            var bootstrap = nm.gameObject.GetComponent<GameRoomBootstrap>();
            if (bootstrap == null)
            {
                nm.gameObject.AddComponent<GameRoomBootstrap>();
                Debug.Log("[GRACE Repair] Added GameRoomBootstrap to NetworkManager.");
                changes++;
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
                    list.PrefabList.Add(new NetworkPrefab { Prefab = chef });
                    EditorUtility.SetDirty(list);
                    AssetDatabase.SaveAssets();
                    Debug.Log("[GRACE Repair] Added NetworkChef to NetworkPrefabsList.");
                    changes++;
                }

                if (list != null && (nm.NetworkConfig.Prefabs.NetworkPrefabsLists == null
                    || !nm.NetworkConfig.Prefabs.NetworkPrefabsLists.Contains(list)))
                {
                    if (nm.NetworkConfig.Prefabs.NetworkPrefabsLists == null)
                        nm.NetworkConfig.Prefabs.NetworkPrefabsLists = new List<NetworkPrefabsList>();
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
            list.PrefabList = new List<NetworkPrefab>();
            AssetDatabase.CreateAsset(list, path);
            AssetDatabase.SaveAssets();
            Debug.Log($"[GRACE Repair] Created {path}.");
            return list;
        }

        private static bool ContainsPrefab(NetworkPrefabsList list, GameObject prefab)
        {
            if (list.PrefabList == null) return false;
            foreach (var p in list.PrefabList)
                if (p != null && p.Prefab == prefab) return true;
            return false;
        }
    }
}
