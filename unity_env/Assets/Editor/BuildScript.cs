// BuildScript.cs
// Phase G5 (Build) for GRACE.
//
// Headless build entrypoints for CI (game-ci/unity-builder) and local use.
// Each method picks scenes from EditorBuildSettings, runs BuildPipeline, and
// exits with code 1 on failure so CI fails fast.

using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace Grace.Unity.EditorTools
{
    /// <summary>Headless build entrypoints for Mac, Windows, and WebGL targets.</summary>
    public static class BuildScript
    {
        /// <summary>macOS Apple Silicon + Intel universal app bundle.</summary>
        public static void BuildMacOS() =>
            Build(BuildTarget.StandaloneOSX, "Builds/macos/grace.app");

        /// <summary>Windows x64 standalone .exe.</summary>
        public static void BuildWindows() =>
            Build(BuildTarget.StandaloneWindows64, "Builds/windows/grace.exe");

        /// <summary>WebGL build → directory (index.html lives at the root).</summary>
        public static void BuildWebGL() =>
            Build(BuildTarget.WebGL, "Builds/webgl");

        private static void Build(BuildTarget target, string outputPath)
        {
            // Resolve scenes from the user's Build Settings; CI configurations
            // should commit ProjectSettings/EditorBuildSettings.asset.
            var scenes = GetScenePaths();
            if (scenes.Length == 0)
            {
                Debug.LogError("[GRACE BuildScript] No enabled scenes in EditorBuildSettings.");
                EditorApplication.Exit(1);
                return;
            }

            // Ensure output directory exists.
            var dir = Path.GetDirectoryName(outputPath);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                Directory.CreateDirectory(dir);

            var options = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = outputPath,
                target = target,
                options = BuildOptions.None,
            };

            var report = BuildPipeline.BuildPlayer(options);
            var summary = report.summary;
            Debug.Log($"[GRACE BuildScript] target={target} result={summary.result} size={summary.totalSize} duration={summary.totalTime}");

            if (summary.result != BuildResult.Succeeded)
            {
                EditorApplication.Exit(1);
            }
        }

        private static string[] GetScenePaths()
        {
            var list = new System.Collections.Generic.List<string>();
            foreach (var s in EditorBuildSettings.scenes)
            {
                if (s != null && s.enabled && !string.IsNullOrEmpty(s.path))
                    list.Add(s.path);
            }
            return list.ToArray();
        }
    }
}
