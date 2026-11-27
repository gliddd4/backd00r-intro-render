import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
source = open(os.path.join(HERE, "ladder.py")).read()
source = source[:source.index('scene.render.filepath = os.path.join(OUT, "ladder.png")')]
exec(compile(source, "ladder", "exec"))

STEPS = 14
foot = (at(543, 732) + at(640, 735)) / 2
top, bottom = at(410, 282), at(543, 732)
lean = math.atan2(-(top - bottom).x, (top - bottom).z)
near, far = at(433, 348, D - 0.5), at(526, 337.5, D - 0.14)
turn = -math.atan2(far.y - near.y, far.x - near.x)

pivot = bpy.data.objects.new("pivot", None)
scene.collection.objects.link(pivot)
pivot.location = foot
bpy.context.view_layer.update()
for obj in list(scene.collection.objects):
    if obj.type in ("MESH",) or obj.name == "firelight":
        world = obj.matrix_world.copy()
        obj.parent = pivot
        obj.matrix_world = world


def project(p):
    return 500 + p.x / p.y * F, HORIZON - p.z / p.y * F


anchors = []
shard, shards = (int(a) for a in sys.argv[-2:])
for k in range(STEPS):
    f = k / (STEPS - 1)
    pivot.rotation_euler = (0, 0, 0)
    pivot.rotation_mode = "XYZ"
    pivot.matrix_world = Matrix.Translation(foot) @ Matrix.Rotation(turn * f, 4, "Z") @ Matrix.Rotation(lean * f, 4, "Y")
    bpy.context.view_layer.update()
    moved = pivot.matrix_world @ (top - foot)
    anchors.append(project(moved))
    if k % shards != shard:
        continue
    scene.render.filepath = os.path.join(OUT, "ladder_turn%02d.png" % k)
    bpy.ops.render.render(write_still=True)
    print("ladder turn", k, flush=True)
json.dump({"lean": lean, "turn": turn, "anchors": anchors}, open(os.path.join(OUT, "ladder_turn.json"), "w"))
