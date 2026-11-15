# Getting every project source onto your Mac

Run Terminal commands from the project directory:

```sh
cd /Users/kmaran3/Desktop/Personal/Tennis-Vision
```

Access checked November 11, 2026. This folder originally contained only the plan.
The current assistant session cannot resolve download hosts from the terminal,
cannot write `.git`, and `gh auth status` reports an invalid saved login.
The commands below are intended for your regular macOS Terminal.
No datasets have been downloaded successfully in this session.

## 1. Download the core data

The quickest route is:

```sh
python3 ingest/download.py fetch --group core
python3 ingest/download.py inventory --check-core
```

No Python packages or API keys are needed. If one source fails, the downloader
continues with the others and exits nonzero. Successful GitHub downloads record
an immutable commit in `data/source-lock.json` and record SHA-256 hashes in a
local `.download.json`. Running again verifies and reuses cached snapshots.
Season CSVs are cached too; to refresh a season, move that CSV outside its source
directory, then run `fetch --source valuebetennis` again.

The inventory reports file presence, not complete season coverage, valid joins,
licensing clearance, or analytical quality. `--check-core` checks for matches,
players, rankings, charting, Slam points, and all odds years from 2021 through
the current year. `--end-year 2025` changes the odds cutoff for fetching/checking.

If downloads fail in Terminal, use the following browser workflow.

### ATP, WTA, rankings, players, and Slam points

Open the [Sackmann archival mirror](https://github.com/Aneeshers/tennis-sackmann-archive).
Choose **Code → Download ZIP**, then import the ZIP without extracting it yourself:

```sh
python3 ingest/download.py import-zip --source sackmann_archive --zip "$HOME/Downloads/tennis-sackmann-archive-main.zip"
```

If the filename differs, substitute the actual downloaded path. The import creates:

```text
data/raw/sackmann_archive/
  atp/                 # match seasons, rankings, players, dictionary
  wta/                 # match seasons, rankings, players
  slam_pointbypoint/    # matches, points, dictionary
```

Keep the upstream READMEs and license. The mirror reports ATP/WTA snapshots from
June 2026 and Slam coverage for 2011–2024. A 2026 file does not represent the full
2026 season. The three original Sackmann repositories return 404. This archive
supports historical work; it is not a verified current-results feed.

Browser ZIP imports record the ZIP hash, with an unverified commit revision.
They do not inherit any existing lock's commit claim. An import refuses to
overwrite a populated destination.

### Shot-by-shot Match Charting data

Open [Match Charting Project](https://github.com/JeffSackmann/tennis_MatchChartingProject),
choose **Code → Download ZIP**, and run:

```sh
python3 ingest/download.py import-zip --source match_charting --zip "$HOME/Downloads/tennis_MatchChartingProject-master.zip"
```

Destination: `data/raw/match_charting/`. Keep both genders' match files, all point
shards, aggregate CSVs, `data_dictionary.txt`, and the charting workbook. Its
Instructions tab explains shot notation. Do not download only the match metadata.

### Odds for the market benchmark

Use [Valuebetennis open data](https://www.valuebetennis.com/en/donnees.htm), which
publishes season CSVs under CC BY 4.0. Download each listed year from 2021 onward
and save the original filenames in:

```text
data/raw/odds/valuebetennis/valuebetennis-matchs-2021.csv
data/raw/odds/valuebetennis/valuebetennis-matchs-2022.csv
...
```

These files contain ATP/WTA matches including lower tours, player IDs/names, and
opening/closing Pinnacle odds. They require a different staging model and player
bridge from the original plan. Market comparisons must use the common covered
matches, starting in 2021, and report exclusions. Do not treat earlier seasons
as having market benchmarks.

The original [tennis-data.co.uk](https://www.tennis-data.co.uk/) returns 403 through
the web tool. Its indexed homepage states that use is for private individuals,
excluding automated bots/scrapers/AI/data-training products. Browser access does
not remove that restriction. The downloader therefore does not scrape it.
If you want this particular source for the public project, clarify permitted use
with the provider first. If permitted, use its [data page](https://www.tennis-data.co.uk/data.php)
to save ATP season spreadsheets under `data/raw/odds/tennis_data_uk/atp/` and WTA
spreadsheets under `data/raw/odds/tennis_data_uk/wta/`, keeping the notes/terms.
It is optional with the alternative above.

## 2. Get all vision data and model weights

These are Phase 8 assets. Downloading code alone does not download datasets or
weights. Keep the original folder layout and annotation files. Allow ample disk
space; image/video datasets and extracted archives can consume tens of GB.

| Asset | Manual action | Local destination |
|---|---|---|
| Court keypoint dataset | From [TennisCourtDetector](https://github.com/yastrebksv/TennisCourtDetector), follow the Dataset Google Drive link; download and extract it. | `data/raw/vision/court_keypoints/` |
| Court detector weights | Follow the same README's Pretrained model link; download the actual weight file. | `data/models/court/` |
| TrackNet labeled frames | From [TrackNet](https://github.com/yastrebksv/TrackNet), open the Dataset Drive folder; download all dataset folders and extract them, keeping frame labels. | `data/raw/vision/tracknet/` |
| TrackNet weights | Follow that implementation's Pretrained model link. Use weights matching its architecture. | `data/models/tracknet/` |
| THETIS strokes | Open [THETIS](https://github.com/THETIS-dataset/dataset), Code → Download ZIP; extract all RGB, depth, mask, and skeleton folders. | `data/raw/vision/thetis/` |
| RacketVision clips and labels | Download the complete [official Hugging Face dataset](https://huggingface.co/datasets/linfeng302/RacketVision) using the command below. | `data/raw/vision/racketvision/` |
| Your own match footage | Record 10–20 singles rally clips, fixed camera behind the baseline, ideally 1080p/60fps. Keep original video files. | `data/raw/video/own/` |
| Optional additional images | Search [Roboflow Universe](https://universe.roboflow.com/search?q=tennis) for ball/court datasets. Pick a specific version with clear terms; export images **and** annotations. | `data/raw/vision/roboflow/<dataset>-<version>/` |

THETIS can also be downloaded/imported by the script:

```sh
python3 ingest/download.py fetch --source thetis
# Or, after a browser ZIP download:
python3 ingest/download.py import-zip --source thetis --zip "$HOME/Downloads/dataset-main.zip"
```

To check THETIS file sizes without interrupting an active download, run this in
a separate Terminal tab:

```sh
python3 ingest/check_thetis_size.py
```

This queries GitHub metadata folder by folder and retries temporary server
errors. Its default commit matches the THETIS download observed in this session;
use `--revision COMMIT` for another snapshot. The total describes repository file
contents, not the compressed ZIP size. Both ZIP and extracted files coexist
during extraction. Git LFS payloads, if any, can differ from Git metadata sizes.

For RacketVision and the alternative court mirror, install the Hugging Face CLI
in a local environment (Python 3.10+ recommended for current packages):

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade huggingface_hub
hf download linfeng302/RacketVision --repo-type dataset --local-dir data/raw/vision/racketvision
```

If the court Drive download fails, use its [Hugging Face mirror](https://huggingface.co/datasets/oweng/tennis_court_keypoints_dataset):

```sh
hf download oweng/tennis_court_keypoints_dataset --repo-type dataset --local-dir data/raw/vision/court_keypoints
```

The mirror's viewer reports a parsing error; downloading files directly avoids
depending on the viewer. If an archive is included, extract it. Mirror storage is
advertised at roughly 7.26 GB. A tiny Git LFS pointer file is not a video/model;
check actual sizes and open a sample image/video after downloads.

For RacketVision pretrained checkpoints, follow the [official repository](https://github.com/OrcustD/RacketVision)
instructions after fetching the reference code below. Its `source/download_checkpoints.py`
downloads weights to the upstream implementation's expected locations; retain
those paths or document copies under `data/models/racketvision/`. Downloaded video
and label files suffice for acquisition; frame extraction is a later pipeline step.

TrackNet V4/V5 are alternative models, not extra mandatory tennis datasets:

- [V4 dataset instructions](https://github.com/TrackNetV4/TrackNetV4/blob/main/docs/DATASET.md)
  and [checkpoints](https://github.com/TrackNetV4/TrackNetV4/blob/main/docs/RESULT.md).
- [V5 official SDK](https://github.com/thaonan/TrackNetV5-SDK): follow its current
  weight/setup instructions if selected.
- YOLO, MediaPipe Pose, and RTMPose are detection/pose alternatives. Install and
  obtain the matching official model assets when selecting the implementation.

For the phase's evaluation, hand-label 3–5 of your own rallies (hit/bounce frames
and in/out). Public datasets cannot replace these labels for validating your camera.
Store authored labels separately under `data/labels/` so small labels can be tracked.

## 3. Keep reference implementations and papers here

```sh
python3 ingest/download.py fetch --group reference
```

This places code snapshots for TennisCourtDetector, TrackNet, TrackNetV4,
TrackNetV5, RacketVision, and tennis_analysis in `data/reference/`. These are
reference checkouts, not our project source or installed dependencies.
For a browser-only workflow, download each repository's ZIP using the source URLs
in `data/sources.json` and import with its source ID, just like the core ZIPs.

Open the papers and use **View PDF** to save references under `data/reference/papers/`:

- [TrackNet](https://arxiv.org/abs/1907.03698)
- [TrackNetV4](https://arxiv.org/abs/2409.14543)
- [TrackNetV5](https://arxiv.org/abs/2512.02789)
- [RacketVision](https://arxiv.org/abs/2511.17045)

## 4. Optional enrichment

- **Weather/altitude:** create a tournament → latitude/longitude seed before
  querying [Open-Meteo historical weather](https://open-meteo.com/en/docs/historical-weather-api).
  Use its browser API builder for the required coordinates and date ranges;
  save JSON responses under `data/raw/weather/`. Record coordinates, timezone,
  request URL, and acquisition date. This is generated per tournament, not one
  pre-existing tennis download. Venue elevation can be stored in the location seed.
- **Elo sanity checks:** view [Tennis Abstract Elo](https://www.tennisabstract.com/reports/atp_elo_ratings.html)
  and manually record a few named players and the ratings' observation date under
  `data/raw/elo_reference/`. Historical comparisons need contemporaneous ratings;
  today's table cannot validate a June 2026 endpoint. The project computes its own Elo.

For manual acquisitions, keep the original README/license alongside the files
and add a small `provenance.txt` with source URL, downloaded date, dataset version,
and any unpacking/renaming. Preserve third-party notices.

## 5. Create your new GitHub repository

From your regular Terminal, reauthenticate to GitHub and initialize this folder:

```sh
cd /Users/kmaran3/Desktop/Personal/Tennis-Vision
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
git init -b main
git add .
git status --short
git commit -m "Set up tennis data acquisition and project documentation"
gh repo create tennis-vision --private --source=. --remote=origin --push
```

This creates **a new repository in the account selected by `gh auth login`**,
named `tennis-vision`. It is private initially; replace `--private` with `--public`
if you want it public immediately. If that name is already taken in your account,
choose another new name. If `git commit` asks for your identity, configure your
name/email for this repository and rerun the commit. If the repository already
exists because you created it in the browser, add its URL with `git remote add
origin URL` and run `git push -u origin main` instead of `gh repo create`.

Raw files, reference snapshots, model weights, and databases stay local under
`data/` and are excluded by `.gitignore`. GitHub receives the plan, code, docs,
catalog, and lock. Keep an independent backup of your own footage. Large raw
datasets do not need to be committed for the repository to reproduce downloads.
Commit updated `data/source-lock.json` after successful automated acquisition.

GitHub CLI references: [authentication](https://cli.github.com/manual/gh_auth_login)
and [creating a repository from a local folder](https://cli.github.com/manual/gh_repo_create).

## 6. Verify what is actually here

```sh
python3 ingest/download.py inventory
python3 ingest/download.py inventory --check-core
python3 -m unittest discover -s tests -v
```

`data/inventory.json` distinguishes absent/partial sources from files present but
not analytically validated. Optional inputs remain listed even when intentionally
unused. A successful `fetch --group all` only means automatic downloads succeeded;
manual sources still need their own downloads and verification.

Before modeling, inspect headers, per-year match/point counts, date coverage,
odds availability, and player joins. Those checks belong to staging and are not
replaced by a presence inventory.
