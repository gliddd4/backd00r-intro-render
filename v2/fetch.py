import concurrent.futures
import json
import os
import sys
import urllib.request

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "assets")
HDRI = ["kloofendal_48d_partly_cloudy_puresky"]
TEXTURES = ["asphalt_02", "sparse_grass", "leafy_grass", "forrest_sand_01", "palm_tree_bark", "pine_bark", "fabric_leather_01", "rough_wood", "rough_pine_door", "weathered_brown_planks"]
MODELS = ["island_tree_02", "searsia_lucida", "shrub_02", "shrub_04", "fern_02", "grass_medium_02", "grass_bermuda_01", "grass_medium_01", "tree_small_02", "island_tree_01", "pine_sapling_medium"]
AGENT = {"User-Agent": "asset-fetch/1.0"}


def read(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=180) as reply:
        return reply.read()


def inside(folder, name):
    path = os.path.abspath(os.path.join(folder, name))
    if not path.startswith(folder + os.sep):
        raise ValueError("path leaves folder: " + name)
    return path


def save(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = read(url)
    with open(path, "wb") as out:
        out.write(data)
    print("got", os.path.relpath(path, ROOT), len(data) // 1024, "kB", flush=True)


def listing(asset):
    return json.loads(read("https://api.polyhaven.com/files/" + asset))


def main():
    jobs = []
    for asset in HDRI:
        jobs.append((listing(asset)["hdri"]["4k"]["hdr"]["url"], os.path.join(ROOT, asset + ".hdr")))
    for asset in TEXTURES:
        files = listing(asset)
        for key, name in (("Diffuse", "diff"), ("nor_gl", "nor"), ("Rough", "rough"), ("Displacement", "disp")):
            if key in files:
                jobs.append((files[key]["2k"]["jpg"]["url"], os.path.join(ROOT, asset, name + ".jpg")))
    for asset in MODELS:
        entry = listing(asset)["gltf"]["1k"]["gltf"]
        folder = os.path.join(ROOT, asset)
        jobs.append((entry["url"], os.path.join(folder, "model.gltf")))
        for name, part in entry.get("include", {}).items():
            jobs.append((part["url"], inside(folder, name)))
    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        for done in [pool.submit(save, *job) for job in jobs]:
            done.result()


main()
