import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
source = open(os.path.join(HERE, "ladder.py")).read()
source = source.replace("for size, low, high, tone, amount in ((34, 0.57, 0.64, (0.80, 0.66, 0.52, 1), 0.95), ", "for size, low, high, tone, amount in (")
source = source.replace("fade_in.inputs[\"To Max\"].default_value = 0.85", "fade_in.inputs[\"To Max\"].default_value = 0.0")
head = source[:source.index('rail("left",')]
tail = source[source.index("glow = bpy.data.lights.new"):source.index('scene.render.filepath = os.path.join(OUT, "ladder.png")')]
exec(compile(head, "ladder_head", "exec"))

import json
FIT = json.load(open(os.path.join(HERE, "ladder3d.json")))
foot_l, top_l = Vector(FIT["rails"][0][0]), Vector(FIT["rails"][0][1])
foot_r, top_r = Vector(FIT["rails"][1][0]), Vector(FIT["rails"][1][1])
flame_at = Vector(FIT["top_left"])
up = ((top_l - foot_l) + (top_r - foot_r)).normalized()
across = foot_r - foot_l
across = (across - up * across.dot(up)).normalized()
normal = across.cross(up).normalized()
if normal.dot(-foot_l) < 0:
    normal = -normal


def beam(name, start, end, width, depth, side, material, edge, rough=1.0):
    axis = end - start
    length = axis.length
    z = axis.normalized()
    x = (side - z * side.dot(z)).normalized()
    y = z.cross(x)
    basis = Matrix((x, y, z)).transposed().to_4x4()
    bm = bmesh.new()
    rings, sides = max(12, int(length * 40)), 28
    rows = []
    for i in range(rings + 1):
        f = i / rings
        row = []
        for j in range(sides):
            a = j / sides * math.tau
            c, s = math.cos(a), math.sin(a)
            r = 1.0 / max(abs(c), abs(s)) ** 0.85
            p = Vector((c * r * width / 2, s * r * depth / 2, f * length))
            world = start + basis.to_3x3() @ p
            n = noise.noise(world * 7.0) * 1.5 + noise.noise(world * 19.0) * 0.8 + noise.noise(world * 47.0) * 0.4
            chip = max(0.0, noise.noise(world * 4.5 + Vector((7, 3, 1))) - 0.25) * 1.5
            out = Vector((c, s, 0)).normalized()
            row.append(bm.verts.new(p + out * 0.007 * rough * (n - chip * 2.0)))
        rows.append(row)
    for a_row, b_row in zip(rows, rows[1:]):
        for j in range(sides):
            face = bm.faces.new((a_row[j], a_row[(j + 1) % sides], b_row[(j + 1) % sides], b_row[j]))
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
    obj.matrix_world = Matrix.Translation(start) @ basis
    return obj


ladder = bpy.data.objects.new("ladder3d", None)
scene.collection.objects.link(ladder)
rail_len = (top_l - foot_l).length
burn = (flame_at - foot_l).length - 0.45
RAIL_DEEP, RAIL_WIDE, STEP_WIDE, STEP_THICK = 0.10, 0.12, 0.10, 0.10
parts = [
    beam("left", foot_l, top_l, RAIL_DEEP, RAIL_WIDE, normal, wood("l", 1, char_from=burn, tint=0.82), wood("le", 11, char_from=burn, tint=0.82), 0.35),
    beam("right", foot_r, top_r, RAIL_DEEP, RAIL_WIDE, normal, wood("r", 2, char_from=rail_len + 0.4, tint=0.82), wood("re", 12, char_from=rail_len + 0.4, tint=0.82), 0.35),
]
flat = Vector((0, 0, 1)).cross(across).normalized()
if flat.dot(normal) < 0:
    flat = -flat
on_top = normal * (RAIL_DEEP / 2) + Vector((0, 0, STEP_THICK / 2)) + flat * 0.0
for n, (a, b) in enumerate(FIT["rungs"]):
    step_wood = wood("g%d" % n, 3 + n, char_from=None, tint=0.95)
    parts.append(beam("rung%d" % n, Vector(a) + on_top, Vector(b) + on_top, STEP_WIDE, STEP_THICK, flat, step_wood, step_wood, 0.3))
for obj in parts:
    world = obj.matrix_world.copy()
    obj.parent = ladder
    obj.matrix_world = world
fire_at = flame_at + normal * 0.25 - up * 0.1
ladder_across, ladder_normal = across.copy(), normal.copy()
exec(compile(tail, "ladder_tail", "exec"))
scene.objects["firelight"].location = fire_at
across, normal = ladder_across, ladder_normal
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "ladder3d.blend"))

shard, shards = (int(v) for v in sys.argv[-2:])
views = ["cover", "front"]
scene.camera.rotation_euler = (math.pi / 2 + math.radians(FIT.get("camera_pitch", 0.0)), 0, 0)
for k, view in enumerate(views):
    if k % shards != shard:
        continue
    if view == "front":
        zz = Vector((0, 0, 1))
        fwd = zz.cross(across).normalized()
        foot = (foot_l + foot_r) / 2
        if fwd.dot(normal) > 0:
            fwd = -fwd
        right = across if across.dot(foot_r - foot_l) > 0 else -across
        upv = right.cross(fwd).normalized()
        if upv.z < 0:
            upv = -upv
        eye = foot - fwd * 2.4 + upv * 1.65
        cam_obj = scene.camera
        cam_obj.data.shift_y = 0
        cam_obj.matrix_world = Matrix.Translation(eye) @ Matrix((right, upv, -fwd)).transposed().to_4x4()
        scene.render.resolution_x, scene.render.resolution_y = 540, 1170
        cam_obj.data.sensor_fit = "VERTICAL"
        scene.render.film_transparent = False
    scene.render.filepath = os.path.join(OUT, "ladder3d_%s.png" % view)
    bpy.ops.render.render(write_still=True)
    print("rendered", view, flush=True)
