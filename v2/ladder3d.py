import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
source = open(os.path.join(HERE, "ladder.py")).read()
head = source[:source.index('rail("left",')]
tail = source[source.index("glow = bpy.data.lights.new"):source.index('scene.render.filepath = os.path.join(OUT, "ladder.png")')]
exec(compile(head, "ladder_head", "exec"))

LEFT = [(410, 282), (414, 290), (426, 335), (436.7, 377), (449, 420), (471.7, 480), (484, 530), (493, 560), (510, 600), (518.3, 640), (528, 670), (536, 700), (543, 732)]
RIGHT = [(488, 272.5), (498, 307), (502, 322), (512, 368), (522, 397), (531, 420), (548, 460), (560, 490), (573, 530), (586, 562), (597, 600), (608, 640), (618, 670), (629, 700), (640, 735)]
TOPS = [[(433, 348), (526, 337.5)], [(455, 398.5), (547.5, 390)], [(475, 462.5), (570.5, 453)], [(498, 525.5), (592.5, 517)], [(527.5, 613.5), (624.5, 602)], [(550, 693.5), (650.5, 682.5)]]
FIT = (7.0141, -1.0312, 7.1155, -1.0172)


def u_at(rail, v):
    for (u0, v0), (u1, v1) in zip(rail, rail[1:]):
        if v <= v1:
            return u0 + (u1 - u0) * (v - v0) / (v1 - v0)
    return rail[-1][0]


def rail_point(rail, a, b, v):
    return at(u_at(rail, v), v, a + b * (v - 500) / 250)


def left_at(v):
    return rail_point(LEFT, FIT[0], FIT[1], v)


def right_at(v):
    return rail_point(RIGHT, FIT[2], FIT[3], v)


foot_l, foot_r = left_at(732), right_at(735)
top_l, top_r = left_at(282), right_at(272.5)
up = ((top_l - foot_l) + (top_r - foot_r)).normalized()
across = (foot_r - foot_l)
across = (across - up * across.dot(up)).normalized()
normal = across.cross(up).normalized()
if normal.dot(Vector((0, 0, 0)) - foot_l) < 0:
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
parts = [
    beam("left", foot_l - up * 0.05, top_l + up * 0.02, 0.11, 0.09, normal, wood("l", 1, char_from=rail_len - 0.55, tint=0.82), wood("le", 11, char_from=rail_len - 0.55, tint=2.15)),
    beam("right", foot_r - up * 0.05, top_r + up * 0.02, 0.11, 0.09, normal, wood("r", 2, char_from=rail_len + 0.4, tint=0.82), wood("re", 12, char_from=rail_len + 0.4, tint=2.15)),
]
for n, (a, b) in enumerate(TOPS):
    l, r = left_at(a[1]), right_at(b[1])
    span = (r - l).normalized()
    drop = -up * 0.04
    parts.append(beam("rung%d" % n, l - span * 0.07 + drop, r + span * 0.02 + drop, 0.085, 0.055, up, wood("g%d" % n, 3 + n, char_from=None, tint=1.38), dark, 0.8))
for obj in parts:
    world = obj.matrix_world.copy()
    obj.parent = ladder
    obj.matrix_world = world
exec(compile(tail, "ladder_tail", "exec"))
scene.objects["firelight"].location = top_l + normal * 0.25 - up * 0.1
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "ladder3d.blend"))

shard, shards = (int(v) for v in sys.argv[-2:])
views = ["cover", "front"]
for k, view in enumerate(views):
    if k % shards != shard:
        continue
    if view == "front":
        level = Vector((normal.x, normal.y, 0)).normalized()
        foot = (foot_l + foot_r) / 2
        eye = foot + level * 2.4 + Vector((0, 0, 1.65))
        target = foot + up * 1.6
        look = Vector((target.x - eye.x, target.y - eye.y, 0)).normalized()
        cam_obj = scene.camera
        cam_obj.data.shift_y = 0
        cam_obj.location = eye
        cam_obj.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
        scene.render.film_transparent = False
    scene.render.filepath = os.path.join(OUT, "ladder3d_%s.png" % view)
    bpy.ops.render.render(write_still=True)
    print("rendered", view, flush=True)
