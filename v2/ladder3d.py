import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
source = open(os.path.join(HERE, "ladder.py")).read()
source = source.replace("for size, low, high, tone, amount in ((34, 0.57, 0.64, (0.80, 0.66, 0.52, 1), 0.95), ", "for size, low, high, tone, amount in (")
source = source.replace("fade_in.inputs[\"To Max\"].default_value = 0.85", "fade_in.inputs[\"To Max\"].default_value = 0.6")
source = source.replace("worn.inputs[2].default_value = (0.58, 0.42, 0.30, 1)", "worn.inputs[2].default_value = (0.80, 0.70, 0.60, 1)")
source = source.replace("(0.46, (172, 104, 70)), (0.57, (206, 138, 98))", "(0.46, (172, 114, 76)), (0.57, (210, 156, 112))")
source = source.replace("ramp(t, pits, [(0.32, (96, 72, 62)), (0.41, (255, 255, 255))])", "ramp(t, pits, [(0.32, (170, 140, 120)), (0.41, (255, 255, 255))])")
source = source.replace("ramp(t, knots, [(0.34, (120, 92, 80)), (0.44, (255, 255, 255))])", "ramp(t, knots, [(0.34, (180, 150, 128)), (0.44, (255, 255, 255))])")
source = source.replace("def wood(name, seed, char_from=None, tint=1.0):", "def wood(name, seed, char_from=None, tint=1.0, char=1.0):")
source = source.replace("(1.0, (42, 30, 26))", "(1.0, tuple(round(255 - (255 - c) * char) for c in (42, 30, 26)))")
source = source.replace("(1.0, (56, 46, 44))", "(1.0, tuple(round(255 - (255 - c) * char) for c in (56, 46, 44)))")
head = source[:source.index('rail("left",')]
tail = source[source.index("glow = bpy.data.lights.new"):source.index('scene.render.filepath = os.path.join(OUT, "ladder.png")')]
exec(compile(head, "ladder_head", "exec"))

import json
FIT = json.load(open(os.path.join(HERE, "ladder3d.json")))
foot_l, top_l = Vector(FIT["rails"][0][0]), Vector(FIT["rails"][0][1])
foot_r, top_r = Vector(FIT["rails"][1][0]), Vector(FIT["rails"][1][1])
up = ((top_l - foot_l) + (top_r - foot_r)).normalized()
across = foot_r - foot_l
across = (across - up * across.dot(up)).normalized()
normal = across.cross(up).normalized()
if normal.dot(-foot_l) < 0:
    normal = -normal


def beam(name, start, end, width, depth, side, materials, pick, shape=None, rough=1.0):
    axis = end - start
    length = axis.length
    z = axis.normalized()
    x = (side - z * side.dot(z)).normalized()
    y = z.cross(x)
    basis = Matrix((x, y, z)).transposed().to_4x4()
    bm = bmesh.new()
    rings, sides = max(12, int(length * 40)), 32
    rows = []
    for i in range(rings + 1):
        f = i / rings
        row = []
        for j in range(sides):
            a = j / sides * math.tau
            c, s = math.cos(a), math.sin(a)
            r = 1.0 / max(abs(c), abs(s))
            p = Vector((c * r * width / 2, s * r * depth / 2, f * length))
            if shape:
                p = shape(p, f, length)
            world = start + basis.to_3x3() @ p
            n = noise.noise(world * 7.0) * 1.5 + noise.noise(world * 19.0) * 0.8 + noise.noise(world * 47.0) * 0.4
            chip = max(0.0, noise.noise(world * 4.5 + Vector((7, 3, 1))) - 0.25) * 1.5
            out = Vector((c, s, 0)).normalized()
            row.append(bm.verts.new(p + out * 0.004 * rough * (n - chip * 2.0)))
        rows.append(row)
    for a_row, b_row in zip(rows, rows[1:]):
        for j in range(sides):
            face = bm.faces.new((a_row[j], a_row[(j + 1) % sides], b_row[(j + 1) % sides], b_row[j]))
            face.material_index = pick(j / sides)
    first = bm.faces.new(rows[0])
    last = bm.faces.new(list(reversed(rows[-1])))
    first.material_index, last.material_index = pick("start"), pick("end")
    bmesh.ops.triangulate(bm, faces=[first, last])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for m in materials:
        mesh.materials.append(m)
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.matrix_world = Matrix.Translation(start) @ basis
    return obj


ladder = bpy.data.objects.new("ladder3d", None)
scene.collection.objects.link(ladder)
SHAPE = FIT["shape"]
RAIL_FACE = SHAPE["rail_face"]
RAIL_SIDE = RAIL_FACE * SHAPE["rail_side_per_face"]
STEP_THICK = SHAPE["step_thick"]
STEP_WIDE = (foot_r - foot_l).length + RAIL_FACE + SHAPE["step_overhang"]
STEP_LONG = STEP_WIDE / SHAPE["step_wide_per_long"]
gap = SHAPE["bottom_gap"]
steps_up = [SHAPE["lowest_step"]]
for g in SHAPE["gaps_bottom_up"]:
    steps_up.append(steps_up[-1] + g * gap)
rail_len = steps_up[-1] + SHAPE["rail_above_top_step"] * gap
top_l, top_r = foot_l + up * rail_len, foot_r + up * rail_len
flame_at = top_l - up * 0.08


def shaved(inner):
    drop = SHAPE["top_shave"]

    def shape(p, f, length):
        inward = p.y * inner / (RAIL_FACE / 2)
        if f > 0.99:
            p.z -= drop * max(0.0, inward)
        return p
    return shape


def rail_pick(where):
    if where in ("start", "end"):
        return 1
    return 0


rail_wood = [wood("rail_l", 1, char_from=SHAPE["rail_char_from"], char=1.0, tint=0.9), wood("rail_end", 11, char_from=-5.0, char=0.9, tint=0.7)]
rail_wood_r = [wood("rail_r", 2, char_from=SHAPE["rail_char_from"], char=1.0, tint=0.9), rail_wood[1]]
parts = []
for name, foot, top, mats in (("left", foot_l, top_l, rail_wood), ("right", foot_r, top_r, rail_wood_r)):
    side_to_other = (foot_r - foot_l) if name == "left" else (foot_l - foot_r)
    x_axis = (normal - up * normal.dot(up)).normalized()
    inner = 1.0 if up.cross(x_axis).dot(side_to_other) > 0 else -1.0
    parts.append(beam(name, foot, top, RAIL_SIDE, RAIL_FACE, normal, mats, rail_pick, shaved(inner)))

flat = Vector((0, 0, 1)).cross(across).normalized()
if flat.dot(normal) < 0:
    flat = -flat
STEP_LOOKS = SHAPE["steps_top_down"]
for k, along in enumerate(reversed(steps_up)):
    look = STEP_LOOKS[k]
    char = SHAPE["step_char_top"] + (SHAPE["step_char_bottom"] - SHAPE["step_char_top"]) * k / (len(steps_up) - 1)
    body = wood("step%d" % k, 3 + k, char_from=STEP_WIDE * 0.5, char=char, tint=0.95)
    left_end = wood("step%d_l" % k, 20 + k, tint=look.get("left_end_tint", 0.55))
    right_end = wood("step%d_r" % k, 30 + k, tint=look.get("right_end_tint", 0.55))
    bow = look.get("right_end_bow", 0.0)

    def shape(p, f, length, bow=bow):
        if bow and f > 0.999:
            p.z += bow * (1 - (p.x / (STEP_LONG / 2)) ** 2)
        return p

    def pick(where):
        return {"start": 1, "end": 2}.get(where, 0) if isinstance(where, str) else 0

    centre_l = foot_l + up * along + normal * (RAIL_SIDE / 2) + flat * (STEP_LONG / 2) + Vector((0, 0, STEP_THICK / 2))
    a = centre_l - across * (RAIL_FACE / 2)
    b = a + across * STEP_WIDE
    parts.append(beam("step%d" % (k + 1), a, b, STEP_LONG, STEP_THICK, flat, [body, left_end, right_end], pick, shape, 0.5))
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

from mathutils import Euler
shard, shards = (int(v) for v in sys.argv[-2:])
views = ["cover", "front"]
TURN = int(os.environ.get("TURN", "0"))
if TURN:
    views = ["turn%02d" % k for k in range(TURN)]
scene.camera.rotation_euler = (math.pi / 2 + math.radians(FIT.get("camera_pitch", 0.0)), 0, 0)
from bpy_extras.object_utils import world_to_camera_view


def square_view(cam_obj=None):
    fwd = Vector((0, 0, 1)).cross(across).normalized()
    if fwd.dot(normal) > 0:
        fwd = -fwd
    right = across if across.dot(foot_r - foot_l) > 0 else -across
    upv = right.cross(fwd).normalized()
    if upv.z < 0:
        upv = -upv
    corners = [obj.matrix_world @ Vector(c) for obj in parts for c in obj.bound_box]
    low, high = Vector([min(c[i] for c in corners) for i in range(3)]), Vector([max(c[i] for c in corners) for i in range(3)])
    center = (low + high) / 2
    turn = Matrix((right, upv, -fwd)).transposed().to_4x4()
    if cam_obj is None:
        return Matrix.Translation(center - fwd * 3.0) @ turn
    for step in range(200):
        far = 1.0 + step * 0.05
        cam_obj.matrix_world = Matrix.Translation(center - fwd * far) @ turn
        bpy.context.view_layer.update()
        seen_at = [world_to_camera_view(scene, cam_obj, c) for c in corners]
        if all(0.08 <= v.x <= 0.92 and 0.12 <= v.y <= 0.88 and v.z > 0 for v in seen_at):
            break
    return cam_obj.matrix_world.copy()


for k, view in enumerate(views):
    if k % shards != shard:
        continue
    if view == "front":
        cam_obj = scene.camera
        cam_obj.data.shift_y = 0
        scene.render.resolution_x, scene.render.resolution_y = 540, 1170
        cam_obj.data.sensor_fit = "VERTICAL"
        cam_obj.matrix_world = square_view(cam_obj)
        scene.render.film_transparent = False
    if view.startswith("turn"):
        cam_obj = scene.camera
        start = Matrix.Translation(Vector((0, 0, 0))) @ Euler((math.pi / 2 + math.radians(FIT.get("camera_pitch", 0.0)), 0, 0)).to_matrix().to_4x4()
        end = square_view()
        f = int(view[4:]) / max(1, TURN - 1)
        f = f * f * (3 - 2 * f)
        loc = start.to_translation().lerp(end.to_translation(), f)
        rot = start.to_quaternion().slerp(end.to_quaternion(), f)
        cam_obj.matrix_world = Matrix.Translation(loc) @ rot.to_matrix().to_4x4()
        cam_obj.data.shift_y = (HORIZON - 499) / 1000 * (1 - f)
        cam_obj.data.sensor_fit = "HORIZONTAL"
        scene.render.resolution_x, scene.render.resolution_y = 540, 1170
        scene.render.film_transparent = False
    scene.render.filepath = os.path.join(OUT, "ladder3d_%s.png" % view)
    bpy.ops.render.render(write_still=True)
    print("rendered", view, flush=True)
