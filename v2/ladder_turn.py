import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
source = open(os.path.join(HERE, "ladder.py")).read()
head = source[:source.index('rail("left",')]
tail = source[source.index("glow = bpy.data.lights.new"):source.index('scene.render.filepath = os.path.join(OUT, "ladder.png")')]
exec(compile(head, "ladder_head", "exec"))

STEPS = 14
LENGTH, SPAN = 4.27, 0.38
RUNGS = [0.55, 1.25, 1.95, 2.65, 3.3, 3.85]
foot = (at(543, 732) + at(640, 735)) / 2
top, bottom = at(410, 282), at(543, 732)
lean = math.atan2(-(top - bottom).x, (top - bottom).z)
near, far = at(433, 348, D - 0.5), at(526, 337.5, D - 0.14)
yaw = math.atan2(far.y - near.y, far.x - near.x)


def beam(name, length, width, depth, material, edge, axis):
    bm = bmesh.new()
    rings, sides = 90, 28
    rows = []
    for i in range(rings + 1):
        f = i / rings
        row = []
        for j in range(sides):
            a = j / sides * math.tau
            c, s = math.cos(a), math.sin(a)
            r = 1.0 / max(abs(c), abs(s)) ** 0.85
            u, v = c * r * width / 2, s * r * depth / 2
            p = Vector((u, v, f * length)) if axis == "Z" else Vector((f * length - length / 2, v, u))
            rough = noise.noise(p * 7.0) * 1.5 + noise.noise(p * 19.0) * 0.8 + noise.noise(p * 47.0) * 0.4
            chip = max(0.0, noise.noise(p * 4.5 + Vector((7, 3, 1))) - 0.25) * 1.5
            out = (Vector((u, v, 0)) if axis == "Z" else Vector((0, v, u))).normalized()
            row.append(bm.verts.new(p + out * 0.006 * (rough - chip * 2.0)))
        rows.append(row)
    for a, b in zip(rows, rows[1:]):
        for j in range(sides):
            face = bm.faces.new((a[j], a[(j + 1) % sides], b[(j + 1) % sides], b[j]))
            face.material_index = 1 if sides // 4 <= j < sides // 2 else 0
    bm.faces.new(rows[0])
    bm.faces.new(list(reversed(rows[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    mesh.materials.append(edge)
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    return obj


pivot = bpy.data.objects.new("pivot", None)
scene.collection.objects.link(pivot)
parts = []
left = beam("left", LENGTH, 0.1, 0.085, wood("l", 1, char_from=LENGTH - 0.55, tint=0.82), wood("le", 11, char_from=LENGTH - 0.55, tint=2.15), "Z")
left.location = (-SPAN, 0, 0)
right = beam("right", LENGTH + 0.05, 0.1, 0.085, wood("r", 2, char_from=LENGTH + 0.4, tint=0.82), wood("re", 12, char_from=LENGTH + 0.4, tint=2.15), "Z")
right.location = (SPAN, 0, 0)
parts += [left, right]
for n, z in enumerate(RUNGS):
    rung = beam("rung%d" % n, 2 * SPAN + 0.22, 0.075, 0.05, wood("g%d" % n, 3 + n, tint=1.38), dark, "X")
    rung.location = (0.03, -0.06, z)
    rung.rotation_euler = (0, 0.02 * math.sin(n * 2.1), 0)
    parts.append(rung)
for obj in parts:
    obj.parent = pivot
exec(compile(tail, "ladder_tail", "exec"))
lamp = scene.objects["firelight"]
lamp.parent = pivot
lamp.location = (-SPAN + 0.05, -0.25, LENGTH - 0.15)


def project(p):
    return 500 + p.x / p.y * F, HORIZON - p.z / p.y * F


anchors = []
shard, shards = (int(a) for a in sys.argv[-2:])
for k in range(STEPS):
    f = k / (STEPS - 1)
    pivot.matrix_world = Matrix.Translation(foot) @ Matrix.Rotation(-lean * (1 - f), 4, "Y") @ Matrix.Rotation(yaw * (1 - f), 4, "Z")
    bpy.context.view_layer.update()
    anchors.append(project(pivot.matrix_world @ Vector((-SPAN, 0, LENGTH))))
    if k % shards != shard:
        continue
    scene.render.filepath = os.path.join(OUT, "ladder_turn%02d.png" % k)
    bpy.ops.render.render(write_still=True)
    print("ladder turn", k, flush=True)
json.dump({"lean": lean, "yaw": yaw, "anchors": anchors}, open(os.path.join(OUT, "ladder_turn.json"), "w"))
