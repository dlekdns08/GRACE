# 03_RoundEnd.unity — Manual Build Guide

> Estimated build time: **10 min**.
> Round-summary screen: final score, soups served, S/A/B/C rank, Play Again / Title buttons.

## Prerequisites

- `00_Title` and `02_GameRoom` already exist in Build Settings.

## Steps

### 1. Create scene

`[INSPECTOR]` Right-click `Assets/Scenes` → **Create → Scene** → `03_RoundEnd`. Open it.

### 2. Camera

`[INSPECTOR]` **GameObject → Camera**. Tag `MainCamera`. Same orthographic UI camera as `00_Title`. Background `#1B1F2A`.

### 3. EventSystem + Canvas

`[INSPECTOR]`
1. **GameObject → UI → Event System**.
2. **GameObject → UI → Canvas** → rename `RoundEndCanvas`. Reference resolution `1920×1080`.

### 4. Stats display

`[INSPECTOR]` Inside `RoundEndCanvas`, add three TMP Text fields stacked vertically:
- `ScoreText`  — large, "Score: 0"
- `SoupsText`  — medium, "Soups: 0"
- `RankText`   — large with accent color, "Rank: -"

Add a `TitleText` ("Round Complete") above them.

### 5. Buttons

`[INSPECTOR]` Add two TMP Buttons under `RoundEndCanvas`:
- `BtnPlayAgain` → "Play Again"
- `BtnTitle`     → "Back to Title"

Stack them under the stats. `360 × 80`.

### 6. RoundEndScreen component

`[INSPECTOR]`
1. **GameObject → Create Empty** → name `RoundEndManager`.
2. Add **Grace.Unity.UI.RoundEndScreen**.
3. Wire fields:
   - `ScoreText`, `SoupsText`, `RankText` → drag the matching TMP Text fields.
   - `TitleScene = 00_Title`, `GameScene = 02_GameRoom`.
   - `RankSScore = 200`, `RankAScore = 120`, `RankBScore = 60` (tweak after playtests).

### 7. Wire buttons

`[INSPECTOR]`
- `BtnPlayAgain.OnClick` → `RoundEndManager.RoundEndScreen.OnPlayAgain()`.
- `BtnTitle.OnClick`     → `RoundEndManager.RoundEndScreen.OnReturnToTitle()`.

### 8. Score handoff (one-line bootstrap)

The simplest cross-scene handoff: extend `Grace.Unity.UI.GameModeFlags` (in `TitleMenu.cs`) with two static fields `LastScore` and `LastSoups`, set them when `02_GameRoom` ends, and have `RoundEndScreen.OnEnable()` read them. (Defer if not needed for your first build — the screen will show 0/0 initially.)

### 9. Save + Build Settings

`Ctrl/Cmd-S`. **File → Build Settings → Add Open Scenes**. Should be index 3.

## Done when

- [ ] Entering Play Mode shows the 3-stat readout (defaults to 0/0/C).
- [ ] Clicking Play Again loads `02_GameRoom`.
- [ ] Clicking Back to Title loads `00_Title`.
- [ ] No Console errors.
