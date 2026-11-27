# BACKD00R intro render

This repo renders the frames of the BACKD00R intro video with Blender's Cycles renderer. Each push that changes a file in `v2/` or in `.github/workflows/render.yml` starts one render job per shard on GitHub Actions.

## A push starts one job per shard

Each push runs the same steps. The jobs run separately, and one failed job does not stop the others.

1. Push a change to `v2/` or to `.github/workflows/render.yml`. GitHub starts one job for each number in the `shard` list in `render.yml`. Each job stops after 120 minutes.
2. Each job installs Python 3.11, the system libraries and fonts Blender needs, and `bpy==4.5.*`, which is Blender as a Python module.
3. Each job runs `python v2/fetch.py assets` to download the sky, plant models and textures from Poly Haven. Files already in `assets` are skipped. The `assets` folder is cached until `v2/fetch.py` changes.
4. Each job runs `python v2/scene.py <shard> <shard count>`, which renders that job's frames with the settings in `render.yml`. Output goes to `out`.
5. Each job uploads `out` as an artifact named `frames-<shard>`. This happens even if the render fails.
6. Download the artifacts from the run's page on GitHub. Each artifact holds the frames of one job.

## Settings control the frames, speed and size

Frames come from `v2/frames.txt`. `RATE` and `HIGH` are set in the `env` block of `.github/workflows/render.yml`. `PREVIEW` is read from the environment and is not set in the repo.

| Setting | Values | What it does |
| --- | --- | --- |
| `frames.txt` | `all`, or a list such as `74,80,86` | Picks the frames to render. A negative number such as `-74` renders frame 74 from an outside view of the car. A missing file renders all frames. |
| `RATE` | A number. The repo sets `20`. Empty or unset means 24. | Sets frames per second. Frame `n` shows the shot at `n` divided by `RATE` seconds. |
| `HIGH` | Empty, `1`, or a number from 2 up. The repo leaves it empty. | Empty gives test quality, 540x1170 with 48 samples. `1` gives double size, 1080x2340, with 96 samples. A number from 2 up gives double size with that many samples. |
| `PREVIEW` | Any text. Not set in the repo. | Gives half size, 270x585, with 16 samples. Overrides `HIGH` when both are set. |
| Shards | The `shard` list in `render.yml`, such as `[0, 1, 2]` | Shard 0 takes the first frame in the list, shard 1 the second, and so on. With N shards, each shard then takes every Nth frame. |

## Six files and folders make up the render

- `.github/workflows/render.yml`: Runs the jobs on each push and sets `RATE` and `HIGH`.
- `v2/scene.py`: Builds the scene, sets the render quality, and renders one job's frames. It also runs the ladder part of `v2/ladder.py` when it starts.
- `v2/frames.txt`: Lists the frames to render.
- `v2/fetch.py`: Downloads the sky, plant models and textures from Poly Haven into the folder named in the command, `assets` by default.
- `v2/ladder.py`: Builds the ladder. Run on its own, it also renders a still to `out/ladder.png`.
- `v2/car/`: Holds the car model, `porsche.glb`, which `v2/scene.py` loads.

## Each frame comes out as a JPEG and an EXR file

Each frame is saved as a `.jpg` and an `.exr`. The number in each name has at least four digits.

- `out/f0074.jpg` and `out/f0074.exr`: frame 74 from the shot. The `.exr` file is 16-bit.
- `out/outside0074.jpg` and `out/outside0074.exr`: frame 74 from an outside view of the car. Negative frame numbers write these names.
- Artifacts `frames-0`, `frames-1`, and so on: one per job on the run's page. Each holds that job's `out` folder.

## Credits

- Car: "Porsche 911 with interior" by n.brizitskaya, https://sketchfab.com/3d-models/porsche-911-with-interior-877b1bc1739f4a2bb65d62fd7ffd9f75, licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Changes: badges, logos and number plate removed, open door closed, glass material replaced, placed and animated in a scene.
- Sky, plants, textures: Poly Haven (https://polyhaven.com), CC0, downloaded at render time.
