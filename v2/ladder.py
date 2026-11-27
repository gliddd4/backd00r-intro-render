import math
import os
import bpy
import bmesh
from mathutils import Matrix, Vector, noise

OUT = os.path.abspath("out")
os.makedirs(OUT, exist_ok=True)
F, HORIZON, D = 1100.0, 538.0, 10.0


def at(u, v, depth=D):
    return Vector(((u - 500) / F * depth, depth, (HORIZON - v) / F * depth))


def px(n, depth=D):
    return n / F * depth


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def node(tree, kind, **values):
    n = tree.nodes.new(kind)
    for key, value in values.items():
        setattr(n, key, value)
    return n


def math_node(tree, op, a, b=None):
    n = node(tree, "ShaderNodeMath", operation=op)
    for i, value in enumerate((a, b)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            n.inputs[i].default_value = value
        else:
            tree.links.new(value, n.inputs[i])
    return n.outputs[0]


def ramp(tree, source, stops):
    n = node(tree, "ShaderNodeValToRGB")
    elements = n.color_ramp.elements
    while len(elements) < len(stops):
        elements.new(0.5)
    for element, (pos, color) in zip(elements, stops):
        element.position = pos
        element.color = [(c / 255) ** 2.2 for c in color] + [1]
    tree.links.new(source, n.inputs[0])
    return n.outputs["Color"]


def noise_node(tree, coords, scale, detail=8, rough=0.65):
    mapping = node(tree, "ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = scale
    tree.links.new(coords, mapping.inputs["Vector"])
    n = node(tree, "ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 1
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    tree.links.new(mapping.outputs["Vector"], n.inputs["Vector"])
    return n.outputs["Fac"]


def multiply(tree, a, factor):
    n = node(tree, "ShaderNodeMixRGB", blend_type="MULTIPLY")
    n.inputs[0].default_value = 1
    tree.links.new(a, n.inputs[1])
    tree.links.new(factor, n.inputs[2])
    return n.outputs[0]


def wood(name, seed, char_from=None, tint=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    bsdf = t.nodes["Principled BSDF"]
    coords = node(t, "ShaderNodeTexCoord").outputs["Object"]
    shift = node(t, "ShaderNodeVectorMath", operation="ADD")
    shift.inputs[1].default_value = (seed * 3.1, seed * 1.7, seed * 5.9)
    t.links.new(coords, shift.inputs[0])
    p = shift.outputs[0]
    grain = noise_node(t, p, (26, 26, 3.0), 10, 0.72)
    color = ramp(t, grain, [(0.32, (92, 52, 38)), (0.46, (172, 104, 70)), (0.57, (206, 138, 98)), (0.70, (244, 208, 172))])
    mottle = noise_node(t, p, (10, 10, 6), 11, 0.8)
    color = multiply(t, color, ramp(t, mottle, [(0.36, (122, 100, 92)), (0.46, (222, 206, 196)), (0.55, (255, 250, 244))]))
    knots = noise_node(t, p, (6, 6, 3.2), 5, 0.6)
    color = multiply(t, color, ramp(t, knots, [(0.34, (120, 92, 80)), (0.44, (255, 255, 255))]))
    pits = noise_node(t, p, (34, 34, 20), 6, 0.7)
    color = multiply(t, color, ramp(t, pits, [(0.32, (96, 72, 62)), (0.41, (255, 255, 255))]))
    worn = node(t, "ShaderNodeMixRGB", blend_type="MIX")
    patches = noise_node(t, p, (21, 21, 11), 9, 0.82)
    fade_in = node(t, "ShaderNodeMapRange")
    fade_in.inputs["From Min"].default_value = 0.57
    fade_in.inputs["From Max"].default_value = 0.66
    fade_in.inputs["To Max"].default_value = 0.85
    t.links.new(patches, fade_in.inputs["Value"])
    t.links.new(fade_in.outputs[0], worn.inputs[0])
    t.links.new(color, worn.inputs[1])
    worn.inputs[2].default_value = (0.58, 0.42, 0.30, 1)
    color = worn.outputs[0]
    if char_from is not None:
        z = node(t, "ShaderNodeSeparateXYZ")
        t.links.new(coords, z.inputs[0])
        ragged = noise_node(t, p, (9, 9, 6), 7, 0.75)
        amount = math_node(t, "ADD", z.outputs["Z"], math_node(t, "MULTIPLY", math_node(t, "SUBTRACT", ragged, 0.5), 1.5))
        fade = node(t, "ShaderNodeMapRange")
        fade.inputs["From Min"].default_value = char_from - 0.25
        fade.inputs["From Max"].default_value = char_from + 0.25
        t.links.new(amount, fade.inputs["Value"])
        color = multiply(t, color, ramp(t, fade.outputs[0], [(0.0, (255, 255, 255)), (1.0, (42, 30, 26))]))
    for size, low, high, tone, amount in ((34, 0.57, 0.64, (0.80, 0.66, 0.52, 1), 0.95), (27, 0.60, 0.66, (0.022, 0.012, 0.010, 1), 0.95), (11, 0.56, 0.66, (0.24, 0.20, 0.18, 1), 0.65)):
        speck = noise_node(t, p, (size, size, size * 0.42), 4, 0.7)
        gate = node(t, "ShaderNodeMapRange")
        gate.inputs["From Min"].default_value = low
        gate.inputs["From Max"].default_value = high
        gate.inputs["To Max"].default_value = amount
        t.links.new(speck, gate.inputs["Value"])
        over = node(t, "ShaderNodeMixRGB", blend_type="MIX")
        t.links.new(gate.outputs[0], over.inputs[0])
        t.links.new(color, over.inputs[1])
        over.inputs[2].default_value = tone
        color = over.outputs[0]
    if char_from is not None:
        z2 = node(t, "ShaderNodeSeparateXYZ")
        t.links.new(coords, z2.inputs[0])
        torn = noise_node(t, p, (13, 13, 9), 8, 0.8)
        level = math_node(t, "ADD", z2.outputs["Z"], math_node(t, "MULTIPLY", math_node(t, "SUBTRACT", torn, 0.5), 0.9))
        top = node(t, "ShaderNodeMapRange")
        top.inputs["From Min"].default_value = char_from + 0.05
        top.inputs["From Max"].default_value = char_from + 0.35
        t.links.new(level, top.inputs["Value"])
        color = multiply(t, color, ramp(t, top.outputs[0], [(0.0, (255, 255, 255)), (1.0, (56, 46, 44))]))
    scale = node(t, "ShaderNodeVectorMath", operation="SCALE")
    scale.inputs["Scale"].default_value = tint
    t.links.new(color, scale.inputs[0])
    t.links.new(scale.outputs[0], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.82
    bsdf.inputs["Specular IOR Level"].default_value = 0.2
    bump = node(t, "ShaderNodeBump")
    bump.inputs["Strength"].default_value = 1.0
    bump.inputs["Distance"].default_value = 0.05
    height = math_node(t, "ADD", grain, math_node(t, "ADD", math_node(t, "MULTIPLY", pits, 1.2), math_node(t, "MULTIPLY", mottle, 1.4)))
    t.links.new(height, bump.inputs["Height"])
    t.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def rail(name, left, crease, right, material, edge):
    def along(points, v):
        for (u0, v0), (u1, v1) in zip(points, points[1:]):
            if v <= v1:
                return u0 + (u1 - u0) * (v - v0) / (v1 - v0)
        return points[-1][0]

    rings, steps = 160, 12
    loops = []
    for i in range(rings + 1):
        f = i / rings
        corners = []
        for points, deep in ((left, 0.42), (crease, 0.0), (right, 0.12)):
            top, bottom = points[0][1], points[-1][1]
            v = top + (bottom - top) * f
            corners.append(at(along(points, v), v, D + deep))
        a, b, c = corners
        corners.append(a + c - b)
        centre = sum(corners, Vector()) / 4
        loop = []
        for k in range(4):
            p0, p1 = corners[k], corners[(k + 1) % 4]
            for j in range(steps):
                g = j / steps
                p = p0.lerp(p1, g)
                round_off = 0.07 if j == 0 else 0.02 if j in (1, steps - 1) else 0.0
                p = p.lerp(centre, round_off)
                out = (p - centre).normalized()
                rough = noise.noise(p * 7.0) * 1.5 + noise.noise(p * 19.0) * 0.8 + noise.noise(p * 47.0) * 0.4
                chip = max(0.0, noise.noise(p * 4.5 + Vector((7, 3, 1))) - 0.25) * (2.5 if j < 2 or j > steps - 2 else 0.8)
                loop.append(p + out * px(0.75) * (rough - chip * 2.0))
        loops.append(loop)
    axis = at(crease[0][0], crease[0][1]) - at(crease[-1][0], crease[-1][1])
    direction = axis.normalized()
    side = direction.cross(Vector((0, -1, 0))).normalized()
    front = direction.cross(side).normalized()
    basis = Matrix((side, front, direction)).transposed()
    middle = (at(crease[0][0], crease[0][1]) + at(crease[-1][0], crease[-1][1])) / 2
    frame = Matrix.Translation(middle) @ basis.to_4x4()
    back = frame.inverted()
    bm = bmesh.new()
    rows = [[bm.verts.new(back @ p) for p in loop] for loop in loops]
    per = len(rows[0])
    for a, b in zip(rows, rows[1:]):
        for j in range(per):
            face = bm.faces.new((a[j], a[(j + 1) % per], b[(j + 1) % per], b[j]))
            face.material_index = 1 if steps <= j < 2 * steps else 0
    bm.faces.new(rows[0])
    bm.faces.new(list(reversed(rows[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    mesh.materials.append(edge)
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.matrix_world = frame
    return obj


dark = wood("endgrain", 9, tint=0.2)
def plank(name, top, bottom, material, near, far):
    def along(points, f):
        u = points[0][0] + (points[-1][0] - points[0][0]) * f
        for (u0, v0), (u1, v1) in zip(points, points[1:]):
            if u <= u1:
                return u, v0 + (v1 - v0) * (u - u0) / (u1 - u0)
        return points[-1]

    loops = []
    rings = 70
    for i in range(rings + 1):
        f = i / rings
        t, b = along(top, f), along(bottom, f)
        depth = near + (far - near) * f
        mu, mv = t[0] + (b[0] - t[0]) * 0.28, t[1] + (b[1] - t[1]) * 0.28
        corners = [at(*t, depth + 0.07), at(mu, mv, depth), at(*b, depth + 0.02), at(*b, depth + 0.16), at(*t, depth + 0.18)]
        centre = sum(corners, Vector()) / len(corners)
        loop = []
        for k in range(len(corners)):
            p0, p1 = corners[k], corners[(k + 1) % len(corners)]
            for j in range(7):
                p = p0.lerp(p1, j / 7)
                if j == 0:
                    p = p.lerp(centre, 0.06)
                out = (p - centre).normalized()
                rough = noise.noise(p * 11.0) + noise.noise(p * 29.0) * 0.6
                loop.append(p + out * px(0.7) * rough)
        loops.append(loop)
    start = at(*along(top, 0.0), near)
    end = at(*along(top, 1.0), far)
    direction = (end - start).normalized()
    side = direction.cross(Vector((0, -1, 0))).normalized()
    front = direction.cross(side).normalized()
    basis = Matrix((side, front, direction)).transposed()
    frame = Matrix.Translation((start + end) / 2) @ basis.to_4x4()
    back = frame.inverted()
    bm = bmesh.new()
    rows = [[bm.verts.new(back @ p) for p in loop] for loop in loops]
    per = len(rows[0])
    for a, b in zip(rows, rows[1:]):
        for j in range(per):
            bm.faces.new((a[j], a[(j + 1) % per], b[(j + 1) % per], b[j]))
    bm.faces.new(rows[0])
    bm.faces.new(list(reversed(rows[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.matrix_world = frame


def endcap(name, outline, depth, material):
    mesh = bpy.data.meshes.new(name)
    front = [at(u, v, depth) for u, v in outline]
    centre = sum(front, Vector()) / len(front)
    points = [centre + Vector((0, -0.015, 0))] + front
    n = len(front)
    mesh.from_pydata(points, [], [(0, 1 + k, 1 + (k + 1) % n) for k in range(n)])
    mesh.materials.append(material)
    scene.collection.objects.link(bpy.data.objects.new(name, mesh))


rail("left",
     [(402, 293), (408, 335), (415, 377), (430, 420), (447.5, 480), (461.7, 530), (473, 560), (488, 600), (499, 640), (509, 670), (517.5, 700), (525, 732)],
     [(410, 282), (414, 290), (426, 335), (436.7, 377), (449, 420), (471.7, 480), (484, 530), (493, 560), (510, 600), (518.3, 640), (528, 670), (536, 700), (543, 732)],
     [(417, 284.5), (420, 300), (431, 335), (444, 377), (456.5, 420), (479, 480), (492.5, 530), (504, 560), (518, 600), (527.5, 640), (538, 670), (547, 700), (556, 732)],
     wood("l", 1, char_from=px(95), tint=0.82), wood("le", 11, char_from=px(95), tint=2.15))
rail("right",
     [(474, 292), (477, 307), (485, 335), (492, 357), (500, 382), (511, 418), (522.5, 460), (535, 490), (550, 530), (563, 562), (575, 600), (588, 640), (598, 670), (608, 700), (618, 735)],
     [(488, 272.5), (498, 307), (502, 322), (512, 368), (522, 397), (531, 420), (548, 460), (560, 490), (573, 530), (586, 562), (597, 600), (608, 640), (618, 670), (629, 700), (640, 735)],
     [(493, 275), (503, 303), (513, 332), (520, 357), (530, 385), (541, 415), (556, 460), (568, 490), (581, 530), (594, 562), (603, 600), (616, 640), (627, 670), (637, 700), (648, 735)],
     wood("r", 2, char_from=px(218), tint=0.82), wood("re", 12, char_from=px(218), tint=2.15))
rungs = [
    ([(433, 348), (487, 341), (512, 337), (526, 337.5)], [(436, 363), (487, 353), (523, 345.5)], None),
    ([(455, 398.5), (487, 392), (543, 386), (547.5, 390)], [(459, 415), (503, 408), (541, 401)], [(443.5, 403), (455, 397.5), (460, 401.5), (459, 415), (448, 418), (443, 412)]),
    ([(475, 462.5), (520, 456), (567, 448), (570.5, 453)], [(479, 480), (520, 473.5), (561, 466)], [(466, 472), (475, 461.5), (478.5, 463), (480, 475), (472, 480.5), (468, 477.5)]),
    ([(498, 525.5), (545, 519), (587, 512.5), (592.5, 517)], [(501, 544), (545, 537), (584, 529.5)], [(487, 531), (498, 525), (502, 528), (501, 543.5), (490, 545), (487, 539)]),
    ([(527.5, 613.5), (573, 606), (621.5, 597.5), (624.5, 602)], [(529, 628), (573, 621.5), (613, 615)], [(513, 620), (527.5, 613.5), (529.5, 617.5), (528.5, 628), (517, 630.5), (514.5, 626)]),
    ([(550, 693.5), (598, 686), (648, 678.5), (650.5, 682.5)], [(552, 710.5), (598, 703), (639, 696)], [(537, 697), (550, 693), (552.5, 698), (552, 710.5), (542, 709.5), (537.5, 702)]),
]
for n, (top, bottom, outline) in enumerate(rungs):
    char = px(5) if n == 0 else None
    plank("rung%d" % n, top, bottom, wood("g%d" % n, 3 + n, char_from=char, tint=1.38), D - 0.5, D - 0.14)
    if outline:
        endcap("cap%d" % n, outline, D - 0.53, dark)


glow = bpy.data.lights.new("firelight", "POINT")
glow.color = (1.0, 0.42, 0.1)
glow.energy = 2.5
glow.shadow_soft_size = 0.15
lamp = bpy.data.objects.new("firelight", glow)
lamp.location = at(412, 332, D - 0.8)
scene.collection.objects.link(lamp)

sun = bpy.data.lights.new("sun", "SUN")
sun.energy = 7.0
sun.color = (1.0, 0.86, 0.68)
sun.angle = math.radians(2)
obj = bpy.data.objects.new("sun", sun)
obj.rotation_euler = Vector((-0.74, 0.40, -0.54)).to_track_quat("-Z", "Y").to_euler()
scene.collection.objects.link(obj)

world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
t = world.node_tree
coords = node(t, "ShaderNodeTexCoord").outputs["Generated"]
sep = node(t, "ShaderNodeSeparateXYZ")
t.links.new(coords, sep.inputs[0])
up = math_node(t, "ADD", math_node(t, "MULTIPLY", sep.outputs["Z"], 0.5), 0.5)
color = ramp(t, up, [(0.0, (190, 175, 160)), (0.46, (230, 216, 190)), (0.56, (130, 175, 205)), (1.0, (60, 90, 150))])
t.links.new(color, t.nodes["Background"].inputs["Color"])
t.nodes["Background"].inputs["Strength"].default_value = 1.15

cam = bpy.data.cameras.new("c")
cam.lens = F / 1000 * 36
cam.sensor_width = 36
cam.sensor_fit = "HORIZONTAL"
cam.shift_y = (HORIZON - 499) / 1000
obj = bpy.data.objects.new("c", cam)
obj.rotation_euler = (math.pi / 2, 0, 0)
scene.collection.objects.link(obj)
scene.camera = obj

scene.render.engine = "CYCLES"
scene.cycles.samples = 96
scene.cycles.use_denoising = True
scene.cycles.volume_step_rate = 0.25
scene.cycles.volume_max_steps = 512
scene.render.film_transparent = True
scene.view_settings.view_transform = "Standard"
scene.render.resolution_x = 1000
scene.render.resolution_y = 998
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.filepath = os.path.join(OUT, "ladder.png")
bpy.ops.render.render(write_still=True)
print("done ladder", flush=True)
