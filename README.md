# Tennis Vision / Baseline

A planned tennis analytics warehouse, scouting app, win-probability model,
and video-analysis extension. The project is currently at data acquisition;
the warehouse and app have not been implemented.

## Get the data

Run these commands from this directory using Python 3.9 or newer:

```sh
python3 ingest/download.py list
python3 ingest/download.py fetch --group core
python3 ingest/download.py inventory --check-core
```

The core download includes the Sackmann archival mirror (ATP, WTA, rankings,
players, Slam points), Match Charting, and Valuebetennis odds from 2021 onward.
Downloads run without Python package dependencies. GitHub snapshots are pinned
to commit IDs in `data/source-lock.json` on the first successful fetch.

See [the complete manual download guide](docs/data-setup.md) for browser downloads,
all vision datasets and model weights, optional enrichment, and GitHub setup.
See [the source catalog](data/sources.json) for URLs and destinations.

All datasets, videos, weights, and reference checkouts stay in the local `data/`
directory and are ignored by Git. Code, documentation, and the source lock belong
in the GitHub repository. A download receipt records timestamps and file hashes.
The inventory checks minimum file presence; it does not certify complete coverage
or data quality.

## Project plan

[Full project plan](tennis-analytics-project-plan.md). The acquisition update at
the top supersedes its original source URLs and odds assumptions.

## Attribution

Tennis match, ranking, player, Grand Slam point, and charting data were compiled
by Jeff Sackmann / Tennis Abstract and Match Charting Project volunteers under
CC BY-NC-SA 4.0. The archival mirror preserves the original source READMEs.
Attribute the original contributors and preserve their notices.

Valuebetennis, Tennis results and odds since 2021:
https://www.valuebetennis.com/en/donnees.htm (CC BY 4.0).
These odds have a different schema and shorter history than tennis-data.co.uk.

Vision datasets and model weights retain their individual upstream terms.
This repository does not assign a blanket license to third-party data.

