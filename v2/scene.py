import math
import os
import random
import sys
import time

import bpy
from mathutils import Matrix, Vector, noise

import math

import os

import random

import sys

import time

import bpy

from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))

OUT = os.path.abspath("out")

os.makedirs(OUT, exist_ok=True)

FPS = 24

LENGTH = 15.6

FRAMES = int(round(LENGTH * FPS)) + 1

random.seed(7)

source = open(os.path.join(HERE, "ladder.py")).read()

source = source[:source.index("glow = bpy.data.lights.new")]

exec(compile(source, "ladder", "exec"), {"__name__": "ladder", "__file__": os.path.join(HERE, "ladder.py")})

scene = bpy.context.scene

ladder_parts = list(scene.collection.objects)

CORAL = (250, 116, 98)

MAGENTA = (150, 38, 126)

INDIGO = (44, 20, 92)

CREAM = (255, 236, 222)

def clamp(x):
    return max(0.0, min(1.0, x))

def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)

def span(t, a, b):
    return smooth((t - a) / (b - a))

def lin(c, k=1.0):
    return tuple((v / 255) ** 2.2 * k for v in c) + (1.0,)

def link_object(obj, parent=None):
    scene.collection.objects.link(obj)
    if parent:
        obj.parent = parent
    return obj

def empty(name, parent=None):
    return link_object(bpy.data.objects.new(name, None), parent)

def mesh_object(name, verts, faces, mat, parent=None, soft=False):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    mesh.materials.append(mat)
    if soft:
        for polygon in mesh.polygons:
            polygon.use_smooth = True
    return link_object(bpy.data.objects.new(name, mesh), parent)

def box(name, size, loc, mat, parent=None, bevel=0.0, rot=(0, 0, 0)):
    x, y, z = (s / 2 for s in size)
    verts = [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z), (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    obj = mesh_object(name, verts, faces, mat, parent)
    obj.location = loc
    obj.rotation_euler = rot
    if bevel:
        m = obj.modifiers.new("b", "BEVEL")
        m.width = bevel
        m.segments = 3
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    return obj

def loft(name, sections, mat, parent=None, closed=True, caps=True, bevel=0.0):
    n = len(sections[0])
    verts = [v for s in sections for v in s]
    faces = []
    for i in range(len(sections) - 1):
        for j in range(n if closed else n - 1):
            a, b = i * n + j, i * n + (j + 1) % n
            faces.append((a, b, b + n, a + n))
    if caps and closed:
        faces.append(tuple(reversed(range(n))))
        faces.append(tuple(range((len(sections) - 1) * n, len(sections) * n)))
    obj = mesh_object(name, verts, faces, mat, parent, soft=True)
    if bevel:
        m = obj.modifiers.new("b", "BEVEL")
        m.width = bevel
        m.segments = 3
        m.limit_method = "ANGLE"
    return obj

def tube(name, points, radius, mat, parent=None, radii=None):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    curve.use_fill_caps = True
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for i, p in enumerate(points):
        spline.points[i].co = (p[0], p[1], p[2], 1)
        if radii:
            spline.points[i].radius = radii[i]
    curve.materials.append(mat)
    return link_object(bpy.data.objects.new(name, curve), parent)

def shared_value(name, start=0.0):
    group = bpy.data.node_groups.new(name, "ShaderNodeTree")
    group.interface.new_socket(name="v", in_out="OUTPUT", socket_type="NodeSocketFloat")
    value = group.nodes.new("ShaderNodeValue")
    out = group.nodes.new("NodeGroupOutput")
    group.links.new(value.outputs[0], out.inputs[0])
    value.outputs[0].default_value = start
    return group, value

NIGHT = shared_value("night")

PHASE = shared_value("phase")

MIST = shared_value("mist")

CLOCK = shared_value("clock")

OPEN = shared_value("open")

def new(tree, kind, **settings):
    n = tree.nodes.new(kind)
    for key, value in settings.items():
        setattr(n, key, value)
    return n

def wire(tree, value, socket):
    if isinstance(value, (int, float, tuple)):
        socket.default_value = value
    else:
        tree.links.new(value, socket)

def shared(tree, pair):
    n = new(tree, "ShaderNodeGroup")
    n.node_tree = pair[0]
    return n.outputs[0]

def op(tree, kind, a, b=None):
    n = new(tree, "ShaderNodeMath", operation=kind)
    wire(tree, a, n.inputs[0])
    if b is not None:
        wire(tree, b, n.inputs[1])
    return n.outputs[0]

def remap(tree, value, a, b, c=0.0, d=1.0):
    n = new(tree, "ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
    wire(tree, value, n.inputs["Value"])
    for key, v in (("From Min", a), ("From Max", b), ("To Min", c), ("To Max", d)):
        n.inputs[key].default_value = v
    return n.outputs["Result"]

def blend(tree, factor, a, b, kind="MIX"):
    n = new(tree, "ShaderNodeMixRGB", blend_type=kind)
    wire(tree, factor, n.inputs[0])
    wire(tree, a, n.inputs[1])
    wire(tree, b, n.inputs[2])
    return n.outputs[0]

def gradient(tree, source, stops):
    n = new(tree, "ShaderNodeValToRGB")
    elements = n.color_ramp.elements
    while len(elements) < len(stops):
        elements.new(0.5)
    for element, (pos, color) in zip(elements, stops):
        element.position = pos
        element.color = lin(color)
    tree.links.new(source, n.inputs[0])
    return n.outputs["Color"]

def grain(tree, coords, scale, detail=6, rough=0.65, offset=(0, 0, 0)):
    mapping = new(tree, "ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = scale
    mapping.inputs["Location"].default_value = offset
    tree.links.new(coords, mapping.inputs["Vector"])
    n = new(tree, "ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 1
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    tree.links.new(mapping.outputs["Vector"], n.inputs["Vector"])
    return n.outputs["Fac"]

def surface(name, color, rough=0.5, metal=0.0, glow=None, strength=0.0, coat=0.0, car=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    bsdf = t.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = lin(color)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Coat Weight"].default_value = coat
    if glow:
        bsdf.inputs["Emission Color"].default_value = lin(glow)
        bsdf.inputs["Emission Strength"].default_value = strength
    if car:
        out = t.nodes["Material Output"]
        facing = new(t, "ShaderNodeLayerWeight")
        facing.inputs["Blend"].default_value = 0.35
        edge = new(t, "ShaderNodeEmission")
        edge.inputs["Color"].default_value = (0, 0, 0, 1)
        wire(t, op(t, "MULTIPLY", op(t, "POWER", facing.outputs["Facing"], 3.0), 0.55), edge.inputs["Strength"])
        clear = new(t, "ShaderNodeBsdfTransparent")
        ghost = new(t, "ShaderNodeAddShader")
        t.links.new(clear.outputs[0], ghost.inputs[0])
        t.links.new(edge.outputs[0], ghost.inputs[1])
        mix = new(t, "ShaderNodeMixShader")
        t.links.new(shared(t, PHASE), mix.inputs[0])
        t.links.new(bsdf.outputs[0], mix.inputs[1])
        t.links.new(ghost.outputs[0], mix.inputs[2])
        t.links.new(mix.outputs[0], out.inputs["Surface"])
    return m

def bare(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    return m, m.node_tree, new(m.node_tree, "ShaderNodeOutputMaterial")

def see_through(t, out, color, alpha, strength=1.0):
    emission = new(t, "ShaderNodeEmission")
    wire(t, color, emission.inputs["Color"])
    wire(t, strength, emission.inputs["Strength"])
    clear = new(t, "ShaderNodeBsdfTransparent")
    mix = new(t, "ShaderNodeMixShader")
    wire(t, alpha, mix.inputs[0])
    t.links.new(clear.outputs[0], mix.inputs[1])
    t.links.new(emission.outputs[0], mix.inputs[2])
    t.links.new(mix.outputs[0], out.inputs["Surface"])

def lamp(name, kind, color, energy, parent=None, loc=(0, 0, 0), **settings):
    light = bpy.data.lights.new(name, kind)
    light.color = tuple(c / 255 for c in color)
    light.energy = energy
    for key, value in settings.items():
        setattr(light, key, value)
    obj = link_object(bpy.data.objects.new(name, light), parent)
    obj.location = loc
    return obj

def ramp_offset(y):
    return 15 * smooth((y - 145) / 65) + max(0.0, y - 210) * 0.25

def car_x(y):
    return 3.6 * smooth((y - 130) / 30) + ramp_offset(y)

def speed(t):
    if t < 2.4:
        return 28.0
    if t < 4.4:
        return 28 - 11 * span(t, 2.4, 3.0)
    if t < 7.0:
        return 17 + 11 * span(t, 4.4, 5.0)
    return 28 - 19 * span(t, 7.0, 10.0)

TRACK = [0.0]

for i in range(1, 2000):
    TRACK.append(TRACK[-1] + speed(i * 0.01) * 0.01)

def car_y(t):
    i = max(0.0, min(1998.0, t * 100))
    a = int(i)
    return TRACK[a] + (TRACK[a + 1] - TRACK[a]) * (i - a)

def car_z(t):
    if t < 7.0:
        return 0.0
    if t < 10.4:
        return 28 * ((t - 7.0) / 3.4) ** 2
    return 28 + (t - 10.4) * 16.5

def car_frame(t):
    y = car_y(t)
    slope = (car_x(y + 0.5) - car_x(y - 0.5))
    heading = -math.atan(slope)
    pitch = 0.24 * span(t, 6.9, 8.1) - 0.12 * span(t, 9.0, 10.4)
    shake = (1 - span(t, 7.0, 7.6)) * 0.006 * (math.sin(t * 41) + math.sin(t * 23.7)) * 0.5
    bob = span(t, 7.4, 8.4) * 0.07 * math.sin(t * 3.1)
    return Matrix.Translation((car_x(y), y, car_z(t) + shake + bob)) @ Matrix.Rotation(heading, 4, "Z") @ Matrix.Rotation(pitch, 4, "X")

def flat(name, color, strength=1.0):
    m, t, out = bare(name)
    emission = new(t, "ShaderNodeEmission")
    emission.inputs["Color"].default_value = lin(color)
    emission.inputs["Strength"].default_value = strength
    t.links.new(emission.outputs[0], out.inputs["Surface"])
    return m

def build_car():
    root = empty("car")
    paint = surface("black", (9, 8, 12), 0.18, 0.55, coat=1.0, car=True)
    trim = surface("trim", (16, 14, 18), 0.45, car=True)
    leather = surface("leather", (28, 21, 28), 0.55, car=True)
    chrome = surface("chrome", (180, 170, 175), 0.18, 1.0, car=True)
    rubber = surface("rubber", (10, 10, 11), 0.85, car=True)
    accent = surface("accent", CORAL, 0.4, glow=CORAL, strength=4.0, car=True)
    tail = surface("tail", (255, 20, 20), 0.3, glow=(255, 24, 20), strength=6.0, car=True)
    head = surface("head", (255, 240, 220), 0.3, glow=(255, 240, 215), strength=0.7, car=True)

    def hull(y, w, top, bottom=0.24, crown=0.05):
        return [(-w * 0.9, y, bottom), (-w, y, bottom + 0.16), (-w, y, top - 0.14), (-w * 0.86, y, top - 0.02), (-w * 0.55, y, top + crown * 0.4), (-w * 0.2, y, top + crown), (w * 0.2, y, top + crown), (w * 0.55, y, top + crown * 0.4), (w * 0.86, y, top - 0.02), (w, y, top - 0.14), (w, y, bottom + 0.16), (w * 0.9, y, bottom)]

    loft("hood", [hull(0.74, 0.97, 0.84, crown=0.015), hull(1.05, 0.99, 0.82), hull(1.6, 0.98, 0.76), hull(2.05, 0.92, 0.66), hull(2.32, 0.76, 0.52, 0.28, 0.02)], paint, root)
    loft("tail_deck", [hull(-2.28, 0.82, 0.66, 0.34), hull(-2.0, 0.95, 0.82), hull(-1.55, 0.99, 0.90), hull(-1.12, 0.97, 0.87)], paint, root)
    for side in (-1, 1):
        sections = []
        for y, w in ((-1.14, 0.97), (-0.5, 0.95), (0.2, 0.95), (0.76, 0.97)):
            outer, inner = side * w, side * (w - 0.13)
            sections.append([(inner, y, 0.26), (outer, y, 0.34), (outer, y, 0.76), (side * (w - 0.04), y, 0.85), (inner, y, 0.855)])
        loft("door", sections, paint, root, bevel=0.015)
        tube("sill", [(side * 0.80, -1.1, 0.865), (side * 0.815, 0.73, 0.865)], 0.018, trim, root)
        box("door_pad", (0.05, 1.5, 0.30), (side * 0.80, -0.2, 0.62), leather, root, bevel=0.02)
        tube("door_seam", [(side * 0.775, -1.0, 0.74), (side * 0.775, 0.55, 0.77)], 0.006, chrome, root)
        tube("pillar_a", [(side * 0.87, 0.76, 0.84), (side * 0.76, 0.40, 1.12), (side * 0.63, 0.02, 1.32)], 0.038, trim, root)
        tube("roof_rail", [(side * 0.63, 0.02, 1.32), (side * 0.66, -0.4, 1.35), (side * 0.63, -0.85, 1.30)], 0.036, paint, root)
        tube("pillar_c", [(side * 0.63, -0.85, 1.30), (side * 0.82, -1.35, 0.92)], 0.075, paint, root)
        box("mirror", (0.24, 0.12, 0.13), (side * 1.08, 0.58, 0.94), paint, root, bevel=0.05)
        tube("mirror_arm", [(side * 0.92, 0.62, 0.85), (side * 1.05, 0.60, 0.91)], 0.025, trim, root)
        box("headlight", (0.34, 0.12, 0.05), (side * 0.55, 2.27, 0.58), head, root, bevel=0.02, rot=(0, 0, -side * 0.35))
        for wy in (-1.42, 1.5):
            tube("tire", [(side * 0.76, wy, 0.35), (side * 1.02, wy, 0.35)], 0.35, rubber, root)
            tube("rim", [(side * 1.015, wy, 0.35), (side * 1.04, wy, 0.35)], 0.22, chrome, root)
            tube("cap", [(side * 1.03, wy, 0.35), (side * 1.055, wy, 0.35)], 0.17, rubber, root)
    tube("tail_bar", [(-0.7, -2.30, 0.62), (0.7, -2.30, 0.62)], 0.022, tail, root)
    box("floor", (1.66, 2.0, 0.08), (0, -0.2, 0.24), trim, root)
    box("firewall", (1.66, 0.06, 0.55), (0, 0.76, 0.52), trim, root)
    box("back_wall", (1.66, 0.08, 0.66), (0, -1.15, 0.55), leather, root, bevel=0.03)
    roof = []
    for y, w, z in ((-0.86, 0.62, 1.31), (-0.6, 0.66, 1.355), (-0.25, 0.66, 1.37), (0.03, 0.62, 1.34)):
        roof.append([(-w, y, z - 0.035), (-w * 0.5, y, z), (w * 0.5, y, z), (w, y, z - 0.035), (w * 0.5, y, z - 0.022), (-w * 0.5, y, z - 0.022)])
    loft("roof", roof, paint, root)
    tube("header", [(-0.63, 0.025, 1.318), (0, 0.04, 1.338), (0.63, 0.025, 1.318)], 0.025, trim, root)
    tube("cowl", [(-0.87, 0.755, 0.845), (0, 0.775, 0.862), (0.87, 0.755, 0.845)], 0.022, trim, root)

    dash = []
    for x in (-0.84, -0.62, -0.42, -0.2, 0.0, 0.3, 0.6, 0.84):
        hump = 0.07 * max(0.0, 1 - abs(x + 0.42) / 0.24)
        dash.append([(x, 0.76, 0.855), (x, 0.60, 0.872 + hump), (x, 0.43, 0.835 + hump), (x, 0.40, 0.76), (x, 0.47, 0.60), (x, 0.58, 0.40), (x, 0.76, 0.40)])
    loft("dash", dash, leather, root, bevel=0.012)
    tube("dash_seam", [(-0.8, 0.392, 0.752), (0.0, 0.385, 0.752), (0.8, 0.392, 0.752)], 0.0045, chrome, root)
    for x in (0.34, 0.62):
        box("vent", (0.20, 0.02, 0.065), (x, 0.405, 0.70), trim, root, bevel=0.008)
        for i in range(3):
            box("slat", (0.18, 0.012, 0.006), (x, 0.39, 0.68 + i * 0.02), chrome, root)
    m, t, out = bare("screen")
    uv = new(t, "ShaderNodeTexCoord").outputs["Object"]
    glow = gradient(t, grain(t, uv, (6, 1, 12), 3, 0.5), [(0.3, (6, 9, 16)), (0.5, (14, 28, 44)), (0.72, (40, 86, 104))])
    emission = new(t, "ShaderNodeEmission")
    t.links.new(glow, emission.inputs["Color"])
    emission.inputs["Strength"].default_value = 0.02
    clear = new(t, "ShaderNodeBsdfTransparent")
    mix = new(t, "ShaderNodeMixShader")
    t.links.new(shared(t, PHASE), mix.inputs[0])
    t.links.new(emission.outputs[0], mix.inputs[1])
    t.links.new(clear.outputs[0], mix.inputs[2])
    t.links.new(mix.outputs[0], out.inputs["Surface"])
    screen = empty("screen_root", root)
    screen.location = (0.05, 0.37, 0.71)
    screen.rotation_euler = (-0.22, 0, 0.12)
    box("screen_case", (0.36, 0.035, 0.22), (0, 0.012, 0), trim, screen, bevel=0.012)
    box("screen", (0.32, 0.006, 0.185), (0, -0.01, 0), m, screen)
    for i, width in enumerate((0.16, 0.11)):
        box("line", (width, 0.003, 0.009), (-0.12 + width / 2, -0.015, -0.045 - i * 0.022), flat("screen_text%d" % i, CREAM, 1.3), screen)
    box("console", (0.34, 1.0, 0.30), (-0.0, -0.08, 0.40), leather, root, bevel=0.07)
    box("console_trim", (0.17, 0.62, 0.02), (0.0, 0.0, 0.555), chrome, root, bevel=0.008)
    box("shifter", (0.065, 0.10, 0.09), (0.0, 0.08, 0.60), trim, root, bevel=0.028)

    bpy.ops.mesh.primitive_torus_add(major_radius=0.185, minor_radius=0.025, major_segments=64, minor_segments=14)
    wheel = bpy.context.object
    wheel.data.materials.append(leather)
    bpy.ops.object.shade_smooth()
    wheel.parent = root
    wheel.location = (-0.42, 0.27, 0.80)
    wheel.rotation_euler = (math.radians(70), 0, 0)
    for angle in (0.0, math.pi, -math.pi / 2):
        tube("spoke", [(0, 0, -0.02), (math.cos(angle) * 0.17, math.sin(angle) * 0.17, 0)], 0.018, trim, wheel)
    tube("hub", [(0, 0, -0.05), (0, 0, 0.0)], 0.06, leather, wheel)
    for side in (-0.50, -0.34):
        tube("gauge", [(side + 0.065 * math.cos(a / 24 * math.tau * 0.75 + 2.4), 0.392, 0.80 + 0.045 * math.sin(a / 24 * math.tau * 0.75 + 2.4)) for a in range(25)], 0.004, accent, root)

    box("mirror_in", (0.22, 0.035, 0.065), (-0.08, 0.10, 1.255), trim, root, bevel=0.02)
    tube("mirror_stem", [(-0.08, 0.11, 1.28), (-0.08, 0.06, 1.33)], 0.008, trim, root)
    for x in (-0.42, 0.40):
        y = -0.62
        box("seat_base", (0.52, 0.55, 0.14), (x, y + 0.2, 0.34), leather, root, bevel=0.06)
        if x < 0:
            box("seat_back", (0.50, 0.16, 0.72), (x, y - 0.16, 0.70), leather, root, bevel=0.07, rot=(math.radians(14), 0, 0))
            box("headrest", (0.26, 0.12, 0.17), (x, y - 0.27, 1.12), leather, root, bevel=0.055)
    lamp("cabin", "AREA", (255, 214, 190), 2.0, root, (0.0, -0.55, 1.28), size=0.7)
    pane = surface("glass", (14, 8, 22), 0.08, 0.3, coat=1.0, car=True)
    panes = [
        mesh_object("windshield", [(-0.86, 0.755, 0.85), (0.86, 0.755, 0.85), (0.62, 0.02, 1.32), (-0.62, 0.02, 1.32)], [(0, 1, 2, 3)], pane, root),
        mesh_object("rear_glass", [(-0.62, -0.86, 1.30), (0.62, -0.86, 1.30), (0.80, -1.34, 0.92), (-0.80, -1.34, 0.92)], [(0, 1, 2, 3)], pane, root),
    ]
    for side in (-1, 1):
        panes.append(mesh_object("side_glass", [(side * 0.86, 0.73, 0.865), (side * 0.64, 0.02, 1.31), (side * 0.64, -0.85, 1.29), (side * 0.82, -1.28, 0.93)], [(0, 1, 2, 3)], pane, root))
    return root, panes

def hermite(keys, tangents, t):
    if t <= keys[0][0]:
        return keys[0][1]
    for i in range(len(keys) - 1):
        (a, p), (b, q) = keys[i], keys[i + 1]
        if t <= b:
            u = (t - a) / (b - a)
            m, n = tangents[i] * (b - a), tangents[i + 1] * (b - a)
            u2, u3 = u * u, u * u * u
            return p * (2 * u3 - 3 * u2 + 1) + m * (u3 - 2 * u2 + u) + q * (-2 * u3 + 3 * u2) + n * (u3 - u2)
    return keys[-1][1]

def slopes(keys, first=None):
    out = []
    for i, (t, p) in enumerate(keys):
        if i == 0:
            out.append(first if first is not None else (keys[1][1] - p) / (keys[1][0] - t))
        elif i == len(keys) - 1:
            out.append((p - keys[i - 1][1]) / (t - keys[i - 1][0]) * 1.5)
        else:
            before = (p - keys[i - 1][1]) / (t - keys[i - 1][0])
            after = (keys[i + 1][1] - p) / (keys[i + 1][0] - t)
            out.append((before + after) / 2)
    return out

SEAT = Vector((-0.37, -0.35, 1.06))

AHEAD = Vector((-0.37, 20.0, 0.55))

RISE = [(8.6, None, None), (9.4, Vector((-0.2, 0.1, 2.3)), Vector((3.0, 22.0, 14.3))), (10.5, Vector((0.0, 1.2, 6.5)), Vector((1.0, 13.2, 27.5)))]

def in_seat(t):
    frame = car_frame(t)
    pos = frame @ SEAT
    ahead = (frame @ AHEAD - pos).normalized()
    lock = span(t, 2.2, 3.8) * (1 - span(t, 4.3, 5.6))
    sign = (SIGN - pos).normalized()
    aim = ahead.lerp(sign, lock).normalized()
    out_window = (frame.to_3x3() @ Vector((-0.93, 0.34, -0.1))).normalized()
    aim = aim.lerp(out_window, span(t, 7.15, 7.75) * (1 - span(t, 8.05, 8.6))).normalized()
    sway = Vector((math.sin(t * 2.3) * 0.004, 0, math.sin(t * 3.7) * 0.003))
    return pos, pos + (aim + sway) * 20, 24 + 8 * lock

def rising(t):
    frame = car_frame(8.6)
    origin = Vector(frame.translation)
    offsets = [(8.6, frame @ SEAT - origin)] + [(k, p) for k, p, _ in RISE[1:]]
    targets = [(8.6, frame @ AHEAD - origin)] + [(k, q) for k, _, q in RISE[1:]]
    pos = hermite(offsets, slopes(offsets, Vector((0, 0, 0))), t)
    aim = hermite(targets, slopes(targets, Vector((0, 0, 0))), t)
    here = Vector(car_frame(t).translation)
    return here + pos, here + aim

def flight_plan():
    start, aim = rising(10.5)
    velocity = (start - rising(10.48)[0]) / 0.02
    turn = (aim - rising(10.48)[1]) / 0.02
    ladder_at = start + Vector((0.0, 50.0, 44.0))

    def near(x, y, z):
        return ladder_at + Vector((x, y, z))

    path = [(10.5, start), (11.3, start + Vector((0, 4, 13))), (12.05, start + Vector((0, 16, 32))), (12.85, near(0.9, -23, -2.4)), (13.7, near(0.25, -12.6, 1.35)), (14.4, near(0.2, -8.4, 2.9)), (14.95, near(0.32, -4.6, 3.62)), (15.6, near(0.32, -0.22, 3.66))]
    look = [(10.5, aim), (11.3, start + Vector((0, 13, 21))), (12.05, start + Vector((0, 34, 40))), (12.85, near(0.2, 0, 0.9)), (13.7, near(0.0, 0, 1.45)), (14.4, near(0.3, 0, 3.3)), (14.95, near(0.32, 0, 3.66)), (15.6, near(0.32, 1, 3.66))]
    return start, ladder_at, (path, slopes(path, velocity)), (look, slopes(look, turn))

START, LADDER_AT, PATH, LOOK = flight_plan()

def lens_at(t):
    keys = [(8.6, 24), (10.5, 24), (12.0, 23), (13.2, 33), (14.2, 33), (15.0, 30), (15.6, 28)]
    for (a, p), (b, q) in zip(keys, keys[1:]):
        if t <= b:
            return p + (q - p) * smooth((t - a) / (b - a))
    return keys[-1][1]

def view(t):
    if t <= 8.6:
        return in_seat(t)
    if t <= 10.5:
        pos, aim = rising(t)
    else:
        pos, aim = hermite(PATH[0], PATH[1], t), hermite(LOOK[0], LOOK[1], t)
    return pos, aim, lens_at(t)

import numpy as np

ASSETS = os.path.abspath("assets")


def picture(path, data=False):
    image = bpy.data.images.load(path, check_existing=True)
    if data:
        image.colorspace_settings.name = "Non-Color"
    return image


def sample(t, path, vector, data=False, box_mapping=False):
    n = new(t, "ShaderNodeTexImage")
    n.image = picture(path, data)
    if box_mapping:
        n.projection = "BOX"
        n.projection_blend = 0.25
    t.links.new(vector, n.inputs["Vector"])
    return n.outputs["Color"]


def scaled(t, vector, scale):
    n = new(t, "ShaderNodeVectorMath", operation="MULTIPLY")
    t.links.new(vector, n.inputs[0])
    n.inputs[1].default_value = scale
    return n.outputs[0]


def textured(name, folder, scale, tint=(255, 255, 255), rough=(0.3, 0.9), bump=1.0, boxed=False, translucent=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    bsdf = t.nodes["Principled BSDF"]
    coords = new(t, "ShaderNodeTexCoord").outputs["Object" if boxed else "UV"]
    vector = scaled(t, coords, (scale, scale, scale))
    base = os.path.join(ASSETS, folder)
    color = sample(t, os.path.join(base, "diff.jpg"), vector, box_mapping=boxed)
    t.links.new(blend(t, 1.0, color, lin(tint), "MULTIPLY"), bsdf.inputs["Base Color"])
    value = sample(t, os.path.join(base, "rough.jpg"), vector, True, boxed)
    t.links.new(remap(t, value, 0.0, 1.0, rough[0], rough[1]), bsdf.inputs["Roughness"])
    if boxed:
        relief = new(t, "ShaderNodeBump")
        relief.inputs["Strength"].default_value = bump * 0.5
        relief.inputs["Distance"].default_value = 0.004
        t.links.new(value, relief.inputs["Height"])
    else:
        relief = new(t, "ShaderNodeNormalMap")
        relief.inputs["Strength"].default_value = bump
        t.links.new(sample(t, os.path.join(base, "nor.jpg"), vector, True), relief.inputs["Color"])
    t.links.new(relief.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def asphalt_material(name, paint=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    bsdf = t.nodes["Principled BSDF"]
    uv = new(t, "ShaderNodeTexCoord").outputs["UV"]
    vector = scaled(t, uv, (0.24, 0.24, 0.24))
    base = os.path.join(ASSETS, "asphalt_02")
    place = new(t, "ShaderNodeNewGeometry").outputs["Position"]
    xyz = new(t, "ShaderNodeSeparateXYZ")
    t.links.new(place, xyz.inputs[0])
    off = op(t, "ABSOLUTE", op(t, "SUBTRACT", op(t, "FLOORED_MODULO", op(t, "ADD", xyz.outputs["X"], 1.8), 3.6), 1.8))
    track = remap(t, op(t, "ABSOLUTE", op(t, "SUBTRACT", off, 0.85)), 0.1, 0.55, 1.0, 0.0)
    track = op(t, "MULTIPLY", track, remap(t, grain(t, place, (0.7, 0.04, 1), 4, 0.6), 0.3, 0.65))
    color = sample(t, os.path.join(base, "diff.jpg"), vector)
    color = blend(t, remap(t, grain(t, place, (0.22, 0.03, 1), 6, 0.65), 0.38, 0.66), color, blend(t, 1.0, color, lin((170, 165, 165)), "MULTIPLY"))
    color = blend(t, track, color, blend(t, 1.0, color, lin((150, 145, 145)), "MULTIPLY"))
    value = sample(t, os.path.join(base, "rough.jpg"), vector, True)
    shine = op(t, "SUBTRACT", remap(t, value, 0.0, 1.0, 0.36, 0.78), op(t, "MULTIPLY", track, 0.14))
    if paint:
        worn = remap(t, grain(t, place, (9, 3.5, 9), 6, 0.75), 0.34, 0.5)
        color = blend(t, worn, color, lin(paint))
        shine = op(t, "ADD", op(t, "MULTIPLY", shine, 0.5), 0.2)
    t.links.new(color, bsdf.inputs["Base Color"])
    wire(t, shine, bsdf.inputs["Roughness"])
    normal = new(t, "ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.9
    t.links.new(sample(t, os.path.join(base, "nor.jpg"), vector, True), normal.inputs["Color"])
    t.links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def planar_uv(obj):
    mesh = obj.data
    layer = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        co = mesh.vertices[loop.vertex_index].co
        layer.data[loop.index].uv = (co.x, co.y)


SKY = "kloofendal_48d_partly_cloudy_puresky"
LIGHT_AZ = math.radians(-145.0)
LIGHT_EL = math.radians(32.0)
SUN_CORE = math.radians(3.0)


def heading(az, el):
    return Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))


def find_sun(path):
    image = picture(path)
    w, h = image.size
    pixels = np.empty(w * h * 4, np.float32)
    image.pixels.foreach_get(pixels)
    rgb = pixels.reshape(h, w, 4)[..., :3]
    light = rgb.sum(-1)
    block = 8
    small = light[: h // block * block, : w // block * block].reshape(h // block, block, w // block, block).mean((1, 3))
    small[: small.shape[0] // 2] = 0
    row, col = np.unravel_index(np.argmax(small), small.shape)
    az = (0.5 - (col + 0.5) * block / w) * math.tau
    el = ((row + 0.5) * block / h - 0.5) * math.pi
    lat = ((np.arange(h) + 0.5) / h - 0.5) * math.pi
    lon = (0.5 - (np.arange(w) + 0.5) / w) * math.tau
    toward = np.cos(lat)[:, None] * math.cos(el) * np.cos(lon - az)[None, :] + np.sin(lat)[:, None] * math.sin(el)
    core = toward > math.cos(SUN_CORE)
    ring = (toward > math.cos(SUN_CORE * 2)) & ~core
    level = np.median(rgb[ring], axis=0)
    area = (math.tau / w) * (math.pi / h) * np.cos(lat)
    power = (np.clip(rgb - level, 0, None) * core[..., None] * area[:, None, None]).sum((0, 1))
    return az, el, level, power


def build_sky():
    path = os.path.join(ASSETS, SKY + ".hdr")
    found_az, elevation, level, power = find_sun(path)
    strength = float(power.max())
    color = tuple(float(c) for c in power / max(strength, 1e-6))
    print("sun found", math.degrees(found_az), math.degrees(elevation), "power", strength, color, "level", level, flush=True)
    world = bpy.data.worlds.new("sky")
    scene.world = world
    world.use_nodes = True
    t = world.node_tree
    background = t.nodes["Background"]
    ray = new(t, "ShaderNodeTexCoord").outputs["Generated"]
    xyz = new(t, "ShaderNodeSeparateXYZ")
    t.links.new(ray, xyz.inputs[0])
    z = xyz.outputs["Z"]
    mapping = new(t, "ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (0, 0, found_az - (math.pi / 2 - LIGHT_AZ))
    t.links.new(ray, mapping.inputs["Vector"])
    photo = new(t, "ShaderNodeTexEnvironment")
    photo.image = picture(path)
    t.links.new(mapping.outputs["Vector"], photo.inputs["Vector"])
    capped = new(t, "ShaderNodeVectorMath", operation="MINIMUM")
    t.links.new(photo.outputs["Color"], capped.inputs[0])
    capped.inputs[1].default_value = tuple(float(c) for c in level)
    aim = new(t, "ShaderNodeVectorMath", operation="NORMALIZE")
    t.links.new(ray, aim.inputs[0])
    toward = new(t, "ShaderNodeVectorMath", operation="DOT_PRODUCT")
    t.links.new(aim.outputs["Vector"], toward.inputs[0])
    toward.inputs[1].default_value = tuple(heading(LIGHT_AZ, elevation))
    disc = remap(t, toward.outputs["Value"], math.cos(SUN_CORE * 1.2), math.cos(SUN_CORE * 0.8))
    plain = blend(t, disc, photo.outputs["Color"], capped.outputs[0])
    overhead = new(t, "ShaderNodeHueSaturation")
    overhead.inputs["Saturation"].default_value = 1.4
    t.links.new(plain, overhead.inputs["Color"])
    overhead = blend(t, 1.0, overhead.outputs["Color"], remap(t, z, 0.1, 0.9, 1.0, 0.8), "MULTIPLY")
    vivid = new(t, "ShaderNodeHueSaturation")
    vivid.inputs["Saturation"].default_value = 1.6
    t.links.new(plain, vivid.inputs["Color"])
    crisp = new(t, "ShaderNodeGamma")
    crisp.inputs["Gamma"].default_value = 1.2
    t.links.new(vivid.outputs["Color"], crisp.inputs["Color"])
    low = blend(t, 1.0, crisp.outputs["Color"], remap(t, z, 0.0, 0.8, 0.95, 0.74), "MULTIPLY")
    deep = blend(t, remap(t, z, 0.45, 0.75), low, overhead)
    trails = None
    for normal, width, strength, seed in (((0.31, 0.25, -0.92), 0.0022, 0.85, 1), ((-0.55, 0.12, -0.83), 0.007, 0.4, 5)):
        across = new(t, "ShaderNodeVectorMath", operation="DOT_PRODUCT")
        t.links.new(aim.outputs["Vector"], across.inputs[0])
        across.inputs[1].default_value = tuple(Vector(normal).normalized())
        line = remap(t, op(t, "ABSOLUTE", across.outputs["Value"]), width, 0.0)
        pieces = remap(t, grain(t, aim.outputs["Vector"], (5.0, 5.0, 5.0), 3, 0.5, (seed, 0, 0)), 0.38, 0.6)
        trail = op(t, "MULTIPLY", op(t, "MULTIPLY", line, pieces), strength)
        trails = trail if trails is None else op(t, "ADD", trails, trail)
    trails = op(t, "MULTIPLY", trails, remap(t, z, 0.12, 0.3))
    deep = blend(t, op(t, "MINIMUM", trails, 1.0), deep, lin((255, 255, 255), 1.3))
    dusk = blend(t, new(t, "ShaderNodeLightPath").outputs["Is Camera Ray"], plain, deep)
    up = op(t, "ADD", op(t, "MULTIPLY", z, 0.5), 0.5)
    high = gradient(t, up, [(0.40, (96, 140, 190)), (0.495, (170, 208, 224)), (0.52, (132, 192, 224)), (0.57, (82, 148, 207)), (0.65, (40, 96, 170)), (0.80, (18, 46, 104)), (1.0, (6, 16, 46))])
    stars = new(t, "ShaderNodeTexVoronoi")
    stars.inputs["Scale"].default_value = 170
    t.links.new(ray, stars.inputs["Vector"])
    points = op(t, "MULTIPLY", remap(t, stars.outputs["Distance"], 0.04, 0.11, 1.0, 0.0), remap(t, grain(t, ray, (55, 55, 55), 2, 0.5), 0.5, 0.72, 0.0, 2.2))
    points = op(t, "MULTIPLY", points, remap(t, z, 0.07, 0.35))
    high = blend(t, points, high, lin((235, 242, 255)), "ADD")
    t.links.new(blend(t, shared(t, NIGHT), dusk, high), background.inputs["Color"])
    background.inputs["Strength"].default_value = 1.0
    return heading(LIGHT_AZ, LIGHT_EL), min(max(strength, 1.0), 40.0), color


def template(name, verts, faces, slots, uvs, mats):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    for mat in mats:
        mesh.materials.append(mat)
    layer = mesh.uv_layers.new(name="UVMap")
    loop = 0
    for face, (polygon, slot) in enumerate(zip(mesh.polygons, slots)):
        polygon.material_index = slot
        for corner in range(len(faces[face])):
            layer.data[loop].uv = uvs[faces[face][corner]]
            loop += 1
    mesh.update()
    return [(mesh, Matrix.Identity(4))]


class Shape:
    def __init__(self):
        self.verts, self.faces, self.slots, self.uvs = [], [], [], []

    def point(self, p, uv=(0, 0)):
        self.verts.append(Vector(p))
        self.uvs.append(uv)
        return len(self.verts) - 1

    def face(self, ids, slot):
        self.faces.append(tuple(ids))
        self.slots.append(slot)

    def limb(self, path, radii, sides, slot, rnd=None, rough=0.0):
        rings = []
        length = 0.0
        for i, (p, r) in enumerate(zip(path, radii)):
            ahead = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
            reference = Vector((1, 0, 0)) if abs(ahead.x) < 0.9 else Vector((0, 1, 0))
            side = ahead.cross(reference).normalized()
            other = ahead.cross(side)
            if i:
                length += (p - path[i - 1]).length
            ring = []
            for k in range(sides + 1):
                a = (k % sides) / sides * math.tau
                bumpy = r * (1 + (rnd.uniform(-rough, rough) if rnd and k < sides else 0.0))
                ring.append(self.point(p + (side * math.cos(a) + other * math.sin(a)) * bumpy, (k / sides * 2, length / 1.4)))
            rings.append(ring)
        for a, b in zip(rings, rings[1:]):
            for k in range(sides):
                self.face((a[k], a[k + 1], b[k + 1], b[k]), slot)

    def build(self, name, mats):
        return template(name, self.verts, self.faces, self.slots, self.uvs, mats)


def foliage(name, color, through):
    m, t, out = bare(name)
    place = new(t, "ShaderNodeObjectInfo").outputs["Random"]
    shade = blend(t, remap(t, place, 0.0, 1.0), lin(color), lin(tuple(int(c * 0.65) for c in color)))
    front = new(t, "ShaderNodeBsdfPrincipled")
    t.links.new(shade, front.inputs["Base Color"])
    front.inputs["Roughness"].default_value = 0.42
    back = new(t, "ShaderNodeBsdfTranslucent")
    t.links.new(blend(t, 1.0, shade, lin(through), "ADD"), back.inputs["Color"])
    mix = new(t, "ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.35
    t.links.new(front.outputs[0], mix.inputs[1])
    t.links.new(back.outputs[0], mix.inputs[2])
    t.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def fan_leaf(shape, rnd, start, direction, stalk, radius, leaflets, slot, droop):
    direction = direction.normalized()
    path = [start + direction * stalk * u + Vector((0, 0, -droop * 0.35 * stalk * u * u)) for u in (0, 0.34, 0.67, 1.0)]
    shape.limb(path, [0.035, 0.028, 0.022, 0.016], 5, slot)
    hub = path[-1]
    ahead = (path[-1] - path[-2]).normalized()
    side = ahead.cross(Vector((0, 0, 1)))
    side = side.normalized() if side.length > 0.01 else Vector((1, 0, 0))
    normal = side.cross(ahead).normalized()
    for i in range(leaflets):
        f = i / (leaflets - 1) * 2 - 1
        angle = f * math.radians(118) + rnd.uniform(-0.04, 0.04)
        heading = (ahead * math.cos(angle) + side * math.sin(angle) + normal * (0.28 * abs(math.sin(angle)) + rnd.uniform(-0.08, 0.08))).normalized()
        length = radius * (1 - 0.32 * abs(f)) * rnd.uniform(0.85, 1.15)
        across = heading.cross(normal).normalized()
        width = radius * 0.045
        previous = None
        for step in range(5):
            u = step / 4
            sag = droop * length * 0.75 * u ** 2.6
            p = hub + heading * length * u + Vector((0, 0, -sag))
            w = width * (0.35 + 1.3 * u) if u < 0.5 else width * 2.0 * (1 - u) + 0.002
            pair = (shape.point(p - across * w, (0, u)), shape.point(p + normal * w * 0.7, (0.5, u)), shape.point(p + across * w, (1, u)))
            if previous:
                shape.face((previous[0], previous[1], pair[1], pair[0]), slot)
                shape.face((previous[1], previous[2], pair[2], pair[1]), slot)
            previous = pair


def sabal(seed, bark, green, dry):
    rnd = random.Random(seed)
    shape = Shape()
    height = rnd.uniform(4.5, 9.0)
    lean = Vector((rnd.uniform(-0.7, 0.7), rnd.uniform(-0.7, 0.7), 0))
    path = [Vector((0, 0, height * i / 16)) + lean * (i / 16) ** 2 for i in range(17)]
    radii = [0.27 if i == 0 else 0.2 + (0.09 if i > 12 else 0.0) for i in range(17)]
    shape.limb(path, radii, 14, 0, rnd, 0.1)
    crown = path[-1]
    for i in range(34):
        az = i * 2.399 + rnd.uniform(-0.3, 0.3)
        el = math.radians(-30 + 110 * (i / 33) + rnd.uniform(-8, 8))
        direction = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
        dead = i < 5
        fan_leaf(shape, rnd, crown + Vector((0, 0, rnd.uniform(-0.25, 0.2))), direction, rnd.uniform(0.8, 1.35), rnd.uniform(0.95, 1.3), 34, 2 if dead else 1, 1.0 if dead else 0.65 - 0.4 * (i / 33))
    return shape.build("sabal%d" % seed, [bark, green, dry])


def palmetto(seed, green, dry):
    rnd = random.Random(seed)
    shape = Shape()
    for i in range(16):
        az = i * 2.399 + rnd.uniform(-0.3, 0.3)
        el = math.radians(rnd.uniform(18, 80))
        direction = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
        fan_leaf(shape, rnd, Vector((rnd.uniform(-0.25, 0.25), rnd.uniform(-0.25, 0.25), 0)), direction, rnd.uniform(0.5, 1.1), rnd.uniform(0.5, 0.75), 22, 1 if i == 0 else 0, rnd.uniform(0.15, 0.5))
    return shape.build("palmetto%d" % seed, [green, dry])


def slash_pine(seed, bark, needle):
    rnd = random.Random(seed)
    shape = Shape()
    height = rnd.uniform(13.0, 20.0)
    path = [Vector((rnd.uniform(-0.08, 0.08), rnd.uniform(-0.08, 0.08), height * i / 12)) for i in range(13)]
    shape.limb(path, [0.27 - 0.22 * i / 12 for i in range(13)], 10, 0, rnd, 0.06)
    for b in range(30):
        f = 0.55 + 0.45 * b / 29
        start = Vector((0, 0, height * f))
        az = b * 2.399 + rnd.uniform(-0.4, 0.4)
        reach = (1 - f) * 6.0 + rnd.uniform(0.6, 1.5)
        direction = Vector((math.cos(az), math.sin(az), rnd.uniform(-0.1, 0.45)))
        limb = [start + direction * reach * u + Vector((0, 0, 0.35 * reach * u * u)) for u in (0, 0.35, 0.7, 1.0)]
        shape.limb(limb, [0.06, 0.045, 0.03, 0.012], 5, 0)
        for k in range(6):
            u = 0.4 + 0.6 * k / 5
            center = start + direction * reach * u + Vector((rnd.uniform(-0.3, 0.3), rnd.uniform(-0.3, 0.3), 0.35 * reach * u * u + rnd.uniform(-0.15, 0.25)))
            for _ in range(75):
                aim = Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0.25, 0.8))).normalized()
                length = rnd.uniform(0.22, 0.4)
                across = aim.orthogonal().normalized() * 0.014
                a = shape.point(center - across)
                c = shape.point(center + across)
                d = shape.point(center + aim * length)
                shape.face((a, c, d), 1)
    return shape.build("pine%d" % seed, [bark, needle])


def imported(asset, together=False):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(ASSETS, asset, "model.gltf"))
    bpy.context.view_layer.update()
    added = [o for o in bpy.data.objects if o not in before]
    meshes = [(o.data, o.matrix_world.copy()) for o in added if o.type == "MESH"]
    for o in added:
        bpy.data.objects.remove(o)
    groups = [meshes] if together else [[m] for m in meshes]
    result = []
    for group in groups:
        points = np.array([matrix @ Vector(corner) for mesh, matrix in group for corner in bounds(mesh)])
        low, high = points.min(0), points.max(0)
        shift = Matrix.Translation((-(low[0] + high[0]) / 2, -(low[1] + high[1]) / 2, -low[2]))
        height = max(0.05, high[2] - low[2])
        result.append(([(mesh, shift @ matrix) for mesh, matrix in group], height))
    print(asset, len(result), [round(float(h), 2) for _, h in result], flush=True)
    return result


def bounds(mesh):
    co = np.empty(len(mesh.vertices) * 3, np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    low, high = co.min(0), co.max(0)
    return [(x, y, z) for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])]


def moss_for(tree, seed, mat):
    rnd = random.Random(seed)
    parts, height = tree
    points = []
    for mesh, matrix in parts:
        count = len(mesh.vertices)
        for _ in range(2600):
            p = matrix @ mesh.vertices[rnd.randrange(count)].co
            if height * 0.4 < p.z < height * 0.8 and math.hypot(p.x, p.y) > height * 0.18:
                points.append(p)
    shape = Shape()
    unit = height / 9.0
    for p in rnd.sample(points, min(260, len(points))):
        for _ in range(7):
            q = p + Vector((rnd.uniform(-0.15, 0.15), rnd.uniform(-0.15, 0.15), 0)) * unit
            length = rnd.uniform(0.25, 0.95) * unit
            across = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), 0)).normalized() * 0.022 * unit
            previous = None
            for step in range(4):
                u = step / 3
                c = q + Vector((rnd.uniform(-0.05, 0.05), rnd.uniform(-0.05, 0.05), -length * u)) * 1.0
                w = across * (1 - u * 0.85)
                pair = (shape.point(c - w), shape.point(c + w))
                if previous:
                    shape.face((previous[0], previous[1], pair[1], pair[0]), 0)
                previous = pair
    return shape.build("moss%d" % seed, [mat])


def vary(kinds, hue=0.05, value=0.35):
    done = set()
    for parts, _ in kinds:
        for mesh, _ in parts:
            for material in mesh.materials:
                if material is None or material.name in done or not material.use_nodes:
                    continue
                done.add(material.name)
                t = material.node_tree
                bsdf = next((n for n in t.nodes if n.type == "BSDF_PRINCIPLED"), None)
                if bsdf is None or not bsdf.inputs["Base Color"].is_linked:
                    continue
                link = bsdf.inputs["Base Color"].links[0]
                source = link.from_socket
                t.links.remove(link)
                seed = new(t, "ShaderNodeObjectInfo").outputs["Random"]
                other = op(t, "FRACT", op(t, "MULTIPLY", seed, 7.31))
                shift = new(t, "ShaderNodeHueSaturation")
                wire(t, op(t, "ADD", 0.5 - hue / 2, op(t, "MULTIPLY", seed, hue)), shift.inputs["Hue"])
                wire(t, op(t, "ADD", 0.9, op(t, "MULTIPLY", other, 0.2)), shift.inputs["Saturation"])
                wire(t, op(t, "ADD", 0.68 - value / 2, op(t, "MULTIPLY", other, value)), shift.inputs["Value"])
                t.links.new(source, shift.inputs["Color"])
                t.links.new(shift.outputs["Color"], bsdf.inputs["Base Color"])


def plant(kind, location, size, turn, tilt=0.0):
    parts, height = kind
    place = Matrix.Translation(location) @ Matrix.Rotation(turn, 4, "Z") @ Matrix.Rotation(tilt, 4, "X") @ Matrix.Scale(size / height, 4)
    for mesh, local in parts:
        obj = bpy.data.objects.new(mesh.name, mesh)
        scene.collection.objects.link(obj)
        obj.matrix_world = place @ local


def lawn_carpet(name, x0, x1, y0, y1, density, kinds, low, high, seed):
    source = bpy.data.collections.get("grass_sources")
    if source is None:
        source = bpy.data.collections.new("grass_sources")
        for i, (parts, height) in enumerate(kinds):
            for mesh, matrix in parts:
                baked = mesh.copy()
                baked.transform(Matrix.Scale(1.0 / height, 4) @ matrix)
                source.objects.link(bpy.data.objects.new("grass_src%d" % i, baked))
    ground = mesh_object(name, [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0)], [(0, 1, 2, 3)], None)
    group = bpy.data.node_groups.new(name, "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, links = group.nodes, group.links
    given = nodes.new("NodeGroupInput")
    out = nodes.new("NodeGroupOutput")
    scatter = nodes.new("GeometryNodeDistributePointsOnFaces")
    scatter.inputs["Density"].default_value = density
    scatter.inputs["Seed"].default_value = seed
    links.new(given.outputs[0], scatter.inputs["Mesh"])
    info = nodes.new("GeometryNodeCollectionInfo")
    info.inputs["Collection"].default_value = source
    info.inputs["Separate Children"].default_value = True
    info.inputs["Reset Children"].default_value = True
    place = nodes.new("GeometryNodeInstanceOnPoints")
    place.inputs["Pick Instance"].default_value = True
    links.new(scatter.outputs["Points"], place.inputs["Points"])
    links.new(info.outputs[0], place.inputs["Instance"])

    def chance(a, b, offset):
        r = nodes.new("FunctionNodeRandomValue")
        r.data_type = "FLOAT"
        [i for i in r.inputs if i.name == "Min" and i.type == "VALUE"][0].default_value = a
        [i for i in r.inputs if i.name == "Max" and i.type == "VALUE"][0].default_value = b
        r.inputs["Seed"].default_value = seed + offset
        return [o for o in r.outputs if o.type == "VALUE"][0]

    pick = nodes.new("FunctionNodeRandomValue")
    pick.data_type = "INT"
    [i for i in pick.inputs if i.name == "Min" and i.type == "INT"][0].default_value = 0
    [i for i in pick.inputs if i.name == "Max" and i.type == "INT"][0].default_value = 999
    pick.inputs["Seed"].default_value = seed + 7
    links.new([o for o in pick.outputs if o.type == "INT"][0], place.inputs["Instance Index"])
    turn = nodes.new("ShaderNodeCombineXYZ")
    links.new(chance(-0.12, 0.12, 1), turn.inputs["X"])
    links.new(chance(0.0, math.tau, 2), turn.inputs["Z"])
    links.new(turn.outputs[0], place.inputs["Rotation"])
    links.new(chance(low, high, 3), place.inputs["Scale"])
    links.new(place.outputs[0], out.inputs[0])
    ground.modifiers.new(name, "NODES").node_group = group
    return ground


def exit_center(y):
    return 3.6 + ramp_offset(y)


def build_forest():
    bark = textured("palm_bark", "palm_tree_bark", 1.0, bump=1.2)
    pine_bark = textured("pine_bark", "pine_bark", 1.0, bump=1.2)
    green = foliage("frond", (74, 104, 42), (90, 80, 10))
    saw = foliage("saw", (92, 112, 52), (80, 75, 10))
    dry = foliage("dry", (132, 100, 58), (60, 35, 5))
    needle = foliage("needle", (56, 82, 40), (45, 45, 5))
    moss = foliage("spanish_moss", (142, 146, 118), (60, 55, 35))
    palms = [(sabal(i, bark, green, dry), 1.0) for i in range(1, 5)]
    palms = [(parts, max(v.co.z for v in parts[0][0].vertices)) for parts, _ in palms]
    pines = [slash_pine(i, pine_bark, needle) for i in range(11, 14)]
    saplings = imported("pine_sapling_medium")
    for parts, _ in saplings[:2]:
        for mesh, _ in parts:
            bpy.data.meshes.remove(mesh)
    pines = [(parts, max(v.co.z for v in parts[0][0].vertices)) for parts in pines] + saplings[2:]
    saws = [palmetto(i, saw, dry) for i in range(21, 24)]
    saws = [(parts, max(v.co.z for v in parts[0][0].vertices)) for parts in saws]
    oak = imported("island_tree_02", together=True)[0]
    oak_moss = moss_for(oak, 3, moss)
    oak = (oak[0] + oak_moss, oak[1])
    wall = [oak, imported("tree_small_02", together=True)[0], imported("island_tree_01", together=True)[0]]
    broad = imported("searsia_lucida")
    shrubs = imported("shrub_02") + imported("shrub_04")
    ferns = imported("fern_02")
    tufts = imported("grass_medium_02")
    lawn = imported("grass_bermuda_01")
    vary(wall + broad + shrubs + ferns + pines)
    rnd = random.Random(77)

    def span_of(kinds, x, y, low, high, lean=0.05):
        plant(rnd.choice(kinds), (x, y, 0), rnd.uniform(low, high), rnd.uniform(0, math.tau), rnd.uniform(-lean, lean))

    def roadside(side, edge, y, step):
        for _ in range(2):
            span_of(saws, edge + side * rnd.uniform(0.4, 5.0), y + rnd.uniform(0, step), 0.8, 1.7)
        for _ in range(2):
            span_of(shrubs + ferns, edge + side * rnd.uniform(0.2, 5.0), y + rnd.uniform(0, step), 0.6, 1.6)
        if rnd.random() < 0.25:
            span_of(palms, edge + side * rnd.uniform(3.0, 14.0), y + rnd.uniform(0, step), 5.0, 9.5)
        span_of(broad, edge + side * rnd.uniform(2.5, 9.0), y + rnd.uniform(0, step), 2.6, 5.0)
        for _ in range(2):
            span_of(wall, edge + side * rnd.uniform(5.0, 16.0), y + rnd.uniform(0, step), 5.5, 12.0)
        for _ in range(2):
            span_of(pines, edge + side * rnd.uniform(10.0, 40.0), y + rnd.uniform(0, step), 13.0, 22.0, 0.03)
        for _ in range(3):
            span_of(wall, edge + side * rnd.uniform(14.0, 40.0), y + rnd.uniform(0, step), 8.0, 15.0)
        for _ in range(3):
            span_of(wall + pines, edge + side * rnd.uniform(40.0, 80.0), y + rnd.uniform(0, step), 10.0, 20.0)

    y = -30.0
    while y < 440:
        right = 15.0 if y < 128 else max(15.0, exit_center(y) + 8.0)
        roadside(1, right, y, 5.0)
        roadside(-1, -49.0, y, 5.0)
        gap = exit_center(y) - 8.0
        if y > 170 and gap > 10:
            for _ in range(4):
                x = rnd.uniform(11.5, max(12.0, gap))
                span_of(palms + broad + saws, x, y + rnd.uniform(0, 5), 1.0, 4.5)
                span_of(tufts, rnd.uniform(8.0, gap), y + rnd.uniform(0, 5), 0.2, 0.5)
        y += 5.0
    for _ in range(900):
        x, y = rnd.uniform(-130, 130), rnd.uniform(430, 760)
        if -50 < x < 16 or abs(x - exit_center(y)) < 14:
            continue
        span_of(pines + pines + broad, x, y, 9.0, 20.0)
    blades = tufts + imported("grass_medium_01")
    lawn_carpet("median_grass", -25.4, -8.9, -20, 200, 110.0, blades, 0.11, 0.22, 11)
    lawn_carpet("right_grass", 7.5, 14.8, -20, 124, 120.0, blades, 0.11, 0.24, 12)
    lawn_carpet("far_grass", -48.5, -42.0, -20, 200, 40.0, blades, 0.12, 0.24, 13)


def build_road():
    asphalt = asphalt_material("asphalt")
    white = asphalt_material("paint_white", (214, 208, 196))
    yellow = asphalt_material("paint_yellow", (222, 160, 40))
    grass = textured("grass_ground", "leafy_grass", 0.3, (150, 190, 95), (0.7, 1.0))
    steel = surface("steel", (150, 150, 152), 0.38, 1.0)
    reflector = surface("reflector", (255, 190, 60), 0.15, 0.3, (255, 170, 50), 0.35)

    def sheet(name, x0, x1, y0, y1, z, mat):
        obj = mesh_object(name, [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [(0, 1, 2, 3)], mat)
        planar_uv(obj)

    def ribbon(name, center, half, a, b, z, mat, step=3.0):
        sections = []
        y = a
        while y < b + step - 0.001:
            yy = min(y, b)
            c = center(yy)
            sections.append([(c - half, yy, z), (c + half, yy, z)])
            y += step
        planar_uv(loft(name, sections, mat, closed=False, caps=False))

    sheet("ground", -900, 900, -300, 1500, -0.05, grass)
    sheet("road", -8.4, 7.2, -60, 900, 0, asphalt)
    ribbon("ramp", exit_center, 3.4, 128, 460, 0.004, asphalt, 2.0)
    ribbon("ramp_left", lambda y: exit_center(y) - 2.4, 0.08, 172, 460, 0.012, yellow, 2.0)
    ribbon("ramp_right", lambda y: exit_center(y) + 2.4, 0.08, 150, 460, 0.012, white, 2.0)
    ribbon("median_line", lambda y: -5.6, 0.09, -60, 900, 0.012, yellow, 20)
    ribbon("edge_a", lambda y: 5.5, 0.09, -60, 144, 0.012, white, 12)
    ribbon("edge_b", lambda y: 5.5, 0.09, 192, 900, 0.012, white, 59)
    y = -50.0
    index = 0
    while y < 560:
        for x in (-1.8, 1.8):
            ribbon("dash", lambda _, x=x: x, 0.075, y, y + 3.0, 0.012, white)
            box("marker", (0.1, 0.1, 0.018), (x, y + 6.5, 0.012), reflector, bevel=0.006)
        y += 12.0
    sheet("road_far", -41.6, -26.0, -60, 900, 0, asphalt)
    ribbon("far_median_line", lambda y: -28.8, 0.09, -60, 900, 0.012, yellow, 20)
    ribbon("far_edge", lambda y: -39.4, 0.09, -60, 900, 0.012, white, 20)
    y = -50.0
    while y < 700:
        for x in (-32.3, -35.9):
            ribbon("far_dash", lambda _, x=x: x, 0.075, y, y + 3.0, 0.012, white)
        y += 12.0
    groove = surface("rumble", (40, 40, 42), 0.9)
    for edge in (6.15, -6.25):
        y = -50.0
        while y < 560:
            if (y // 18) % 2 == 0 and not (edge > 0 and 124 < y < 200):
                box("rumble", (0.42, 0.16, 0.008), (edge, y, 0.006), groove)
            y += 0.55
    pole_steel = surface("pole_steel", (170, 172, 170), 0.45, 0.9)
    lamp_head = surface("lamp_head", (120, 122, 120), 0.5, 0.6)
    for y in range(-20, 560, 64):
        x = 9.6 if y < 120 else exit_center(y) + 6.5
        tube("pole", [(x, y, 0), (x, y, 11.5)], 0.11, pole_steel, radii=[1.0, 0.7])
        tube("arm", [(x, y, 11.2), (x - 1.2, y, 11.9), (x - 2.6, y, 12.05)], 0.05, pole_steel)
        box("lamp_head", (0.75, 0.32, 0.16), (x - 2.9, y, 12.0), lamp_head, bevel=0.05)
    for side, a, b in ((lambda y: -23.6, -60, 700), (lambda y: exit_center(y) + 4.4, 128, 360)):
        sections = []
        for y in range(a, b + 1, 3):
            x = side(y)
            sections.append([(x + dx, y, dz) for dx, dz in ((0, 0.46), (-0.05, 0.52), (0.0, 0.58), (-0.05, 0.65), (0, 0.72), (0.02, 0.72), (-0.03, 0.65), (0.02, 0.58), (-0.03, 0.52), (0.02, 0.46))])
        loft("rail", sections, steel)
        for y in range(a, b + 1, 3):
            box("post", (0.09, 0.07, 0.74), (side(y) + 0.09, y, 0.35), steel, bevel=0.008)


def build_traffic():
    glass = surface("traffic_glass", (14, 16, 20), 0.08, 0.0, coat=1.0)
    tyre = surface("tyre", (18, 18, 18), 0.8)
    tail = flat("traffic_tail", (255, 26, 20), 2.5)
    plan = [
        ((236, 236, 232), -3.6, 46.0, 21.0, "car"),
        ((40, 42, 46), -3.6, 92.0, 21.5, "suv"),
        ((150, 152, 156), 0.0, 165.0, 23.0, "car"),
        ((232, 232, 228), 3.6, 250.0, 20.0, "truck"),
        ((22, 24, 30), -3.6, 300.0, 22.0, "car"),
        ((200, 198, 190), -33.9, 260.0, -29.0, "car"),
        ((70, 74, 80), -37.5, 420.0, -27.0, "suv"),
        ((232, 232, 228), -33.9, 560.0, -26.0, "truck"),
        ((120, 20, 24), -37.5, 640.0, -30.0, "car"),
    ]
    cars = []
    for i, (color, x, y, speed, kind) in enumerate(plan):
        paint = surface("traffic_paint%d" % i, color, 0.22, 0.55, coat=0.6)
        root = empty("traffic%d" % i)
        if kind == "truck":
            box("trailer", (2.55, 13.5, 2.9), (0, -3.0, 2.35), paint, root, bevel=0.06)
            box("cab", (2.45, 2.4, 2.6), (0, 4.9, 1.75), paint, root, bevel=0.18)
            box("windshield", (2.2, 0.08, 0.9), (0, 6.12, 2.45), glass, root, bevel=0.03)
            for wy in (-8.2, -7.0, 3.8, 5.2):
                for wx in (-1.05, 1.05):
                    tube("wheel", [(wx - 0.16, wy, 0.5), (wx + 0.16, wy, 0.5)], 0.5, tyre, root)
            for side in (-1.0, 1.0):
                box("tail", (0.25, 0.05, 0.12), (side, -9.76, 1.0), tail, root, bevel=0.01)
        else:
            high = 0.15 if kind == "suv" else 0.0
            box("body", (1.86, 4.6, 0.72 + high), (0, 0, 0.62 + high / 2), paint, root, bevel=0.22)
            box("cabin", (1.6, 2.5 + high * 3, 0.52 + high), (0, -0.25, 1.18 + high), glass, root, bevel=0.2)
            box("roof", (1.5, 1.9 + high * 3, 0.06), (0, -0.3, 1.45 + high * 1.5), paint, root, bevel=0.03)
            for side in (-0.66, 0.66):
                box("tail", (0.4, 0.05, 0.1), (side, -2.31, 0.82 + high), tail, root, bevel=0.02)
            for wx in (-0.84, 0.84):
                for wy in (-1.42, 1.42):
                    tube("wheel", [(wx - 0.11, wy, 0.34), (wx + 0.11, wy, 0.34)], 0.34, tyre, root)
        if speed < 0:
            root.rotation_euler = (0, 0, math.pi)
        cars.append((root, x, y, speed))
    return cars


SIGN = Vector((2.0, 135.0, 6.9))


def highway_font():
    for folder, _, names in os.walk("/usr/share/fonts"):
        for name in sorted(names):
            low = name.lower()
            if low.startswith("overpass") and "bold" in low and "mono" not in low and "italic" not in low and "extra" not in low and "semi" not in low:
                return os.path.join(folder, name)
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def words(text, size, loc, mat):
    curve = bpy.data.curves.new(text, "FONT")
    curve.body = text
    curve.size = size
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    path = highway_font()
    if os.path.exists(path):
        curve.font = bpy.data.fonts.load(path, check_existing=True)
    curve.materials.append(mat)
    obj = link_object(bpy.data.objects.new(text, curve))
    obj.location = loc
    obj.rotation_euler = (math.pi / 2, 0, 0)
    return obj


def sheeting(name, color, glow):
    m = surface(name, color, 0.38, 0.0, color, glow)
    t = m.node_tree
    bsdf = t.nodes["Principled BSDF"]
    place = new(t, "ShaderNodeNewGeometry").outputs["Position"]
    xyz = new(t, "ShaderNodeSeparateXYZ")
    t.links.new(place, xyz.inputs[0])
    dirt = remap(t, grain(t, place, (1.3, 1.3, 0.5), 8, 0.7), 0.35, 0.75, 1.0, 0.74)
    streaks = remap(t, grain(t, place, (26.0, 26.0, 0.6), 6, 0.6), 0.45, 0.8, 1.0, 0.82)
    faded = remap(t, grain(t, place, (0.7, 0.7, 0.9), 4, 0.55, (3, 1, 7)), 0.4, 0.7, 0.0, 0.16)
    seam = remap(t, op(t, "ABSOLUTE", op(t, "SUBTRACT", op(t, "FLOORED_MODULO", xyz.outputs["X"], 1.22), 0.61)), 0.588, 0.605, 1.0, 0.55)
    worn = blend(t, 1.0, blend(t, 1.0, lin(color), dirt, "MULTIPLY"), streaks, "MULTIPLY")
    worn = blend(t, faded, blend(t, 1.0, worn, seam, "MULTIPLY"), lin((200, 205, 190)))
    t.links.new(worn, bsdf.inputs["Base Color"])
    wire(t, op(t, "ADD", 0.38, op(t, "MULTIPLY", faded, 1.2)), bsdf.inputs["Roughness"])
    return m


def build_sign():
    steel = surface("gantry", (140, 142, 146), 0.45, 1.0)
    green = sheeting("sign_green", (0, 96, 64), 0.02)
    white = sheeting("sign_white", (225, 228, 222), 0.07)
    blue = sheeting("shield_blue", (24, 62, 140), 0.03)
    red = sheeting("shield_red", (170, 32, 42), 0.03)
    x, y, z = SIGN
    for px in (-9.6, 11.4):
        tube("pole", [(px, y + 0.4, 0), (px, y + 0.4, 8.7)], 0.2, steel)
        box("footing", (0.8, 0.8, 0.3), (px, y + 0.4, 0.15), steel, bevel=0.05)
    for h in (6.4, 7.9):
        for depth in (0.25, 0.75):
            tube("chord", [(-9.6, y + depth, h), (11.4, y + depth, h)], 0.065, steel)
    for i in range(15):
        a = -9.6 + i * 1.4
        for depth in (0.25, 0.75):
            tube("brace", [(a, y + depth, 6.4), (a + 0.7, y + depth, 7.9), (a + 1.4, y + depth, 6.4)], 0.03, steel)
        tube("cross", [(a, y + 0.25, 7.9), (a + 1.4, y + 0.75, 7.9)], 0.025, steel)
    box("sign_edge", (8.2, 0.05, 3.5), (x, y + 0.05, z), white, bevel=0.02)
    box("sign_face", (8.04, 0.06, 3.34), (x, y + 0.015, z), green, bevel=0.015)
    for bx in (-3.8, -1.9, 0.0, 1.9, 3.8):
        for bz in (-1.5, 1.5):
            tube("bolt", [(x + bx, y - 0.02, z + bz), (x + bx, y - 0.035, z + bz)], 0.025, steel)
    shield = [(-0.52, 0.52), (-0.2, 0.62), (0.2, 0.62), (0.52, 0.52), (0.58, 0.1), (0.42, -0.34), (0.0, -0.66), (-0.42, -0.34), (-0.58, 0.1)]
    sx, sz = x - 2.7, z + 0.85
    for scale, mat, depth in ((0.98, white, -0.022), (0.89, blue, -0.026)):
        verts = [(sx + a * scale, y + depth, sz + b * scale) for a, b in shield]
        mesh_object("shield", verts, [tuple(range(len(verts)))], mat)
    mesh_object("band", [(sx - 0.43, y - 0.03, sz + 0.24), (sx + 0.43, y - 0.03, sz + 0.24), (sx + 0.4, y - 0.03, sz + 0.45), (sx + 0.17, y - 0.03, sz + 0.51), (sx - 0.17, y - 0.03, sz + 0.51), (sx - 0.4, y - 0.03, sz + 0.45)], [(0, 1, 2, 3, 4, 5)], red)
    words("75", 0.55, (sx, y - 0.04, sz - 0.12), white)
    words("NORTH", 0.62, (x + 0.6, y - 0.03, z + 0.85), white)
    words("BACKD00R", 1.18, (x, y - 0.03, z - 0.2), white)
    words("EXIT 00", 0.54, (x - 0.6, y - 0.03, z - 1.18), white)
    ax, az = x + 1.8, z - 1.18
    arrow = [(-0.4, -0.38), (-0.26, -0.47), (0.18, 0.07), (0.3, -0.04), (0.4, 0.42), (-0.07, 0.37), (0.05, 0.26)]
    mesh_object("arrow", [(ax + a, y - 0.035, az + b) for a, b in arrow], [tuple(range(len(arrow)))], white)


def cloud_matter(name="cloud_volume", thickness=2.4, glow=0.24):
    m, t, out = bare(name)
    attribute = new(t, "ShaderNodeAttribute")
    attribute.attribute_name = "density"
    amount = op(t, "MULTIPLY", attribute.outputs["Fac"], thickness)
    scatter = new(t, "ShaderNodeVolumeScatter")
    scatter.inputs["Anisotropy"].default_value = 0.25
    wire(t, blend(t, shared(t, NIGHT), (0.98, 0.86, 0.80, 1), (1.0, 0.95, 0.86, 1)), scatter.inputs["Color"])
    wire(t, amount, scatter.inputs["Density"])
    ambient = new(t, "ShaderNodeEmission")
    wire(t, blend(t, shared(t, NIGHT), lin((116, 96, 118)), lin((96, 140, 208))), ambient.inputs["Color"])
    wire(t, op(t, "MULTIPLY", amount, glow), ambient.inputs["Strength"])
    add = new(t, "ShaderNodeAddShader")
    t.links.new(scatter.outputs[0], add.inputs[0])
    t.links.new(ambient.outputs[0], add.inputs[1])
    t.links.new(add.outputs[0], out.inputs["Volume"])
    return m


def cloud_kind(seed, mat):
    rnd = random.Random(seed)
    group = bpy.data.node_groups.new("cumulus%d" % seed, "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    position = new(group, "GeometryNodeInputPosition").outputs["Position"]

    def vector(kind, a, b=None):
        n = new(group, "ShaderNodeVectorMath", operation=kind)
        wire(group, a, n.inputs[0])
        if b is not None:
            wire(group, b, n.inputs[1])
        return n

    def billow(scale, detail, rough, offset):
        moved = vector("ADD", vector("MULTIPLY", position, scale).outputs[0], offset).outputs[0]
        n = new(group, "ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 1
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        group.links.new(moved, n.inputs["Vector"])
        return n.outputs["Fac"]

    lumps = [(Vector((0, 0, -0.12)), Vector((1.05, 0.85, 0.52)))]
    for _ in range(7):
        r = rnd.uniform(0.28, 0.55)
        lumps.append((Vector((rnd.uniform(-0.9, 0.9), rnd.uniform(-0.65, 0.65), rnd.uniform(-0.1, 0.42))), Vector((r, r, r))))
    shape = None
    for center, radius in lumps:
        offset = vector("SUBTRACT", position, tuple(center)).outputs[0]
        stretched = vector("MULTIPLY", offset, (1 / radius.x, 1 / radius.y, 1 / radius.z)).outputs[0]
        inside_amount = op(group, "SUBTRACT", 1.0, vector("LENGTH", stretched).outputs["Value"])
        shape = inside_amount if shape is None else op(group, "MAXIMUM", shape, inside_amount)
    big = billow((2.3, 2.3, 2.6), 5, 0.62, (seed * 2.1, seed * 5.3, seed * 1.7))
    small = billow((7.5, 7.5, 8.0), 4, 0.65, (seed, seed * 3.0, seed * 7.0))
    body = op(group, "ADD", shape, op(group, "MULTIPLY", op(group, "SUBTRACT", big, 0.5), 2.2))
    body = op(group, "ADD", body, op(group, "MULTIPLY", op(group, "SUBTRACT", small, 0.5), 0.9))
    xyz = new(group, "ShaderNodeSeparateXYZ")
    group.links.new(position, xyz.inputs[0])
    cells = new(group, "ShaderNodeTexVoronoi")
    cells.inputs["Scale"].default_value = 3.4
    group.links.new(vector("ADD", position, (seed * 1.3, seed * 4.1, seed * 2.9)).outputs[0], cells.inputs["Vector"])
    body = op(group, "ADD", body, op(group, "MULTIPLY", op(group, "SUBTRACT", 0.5, cells.outputs["Distance"]), 0.7))
    density = op(group, "MULTIPLY", remap(group, body, 0.1, 0.24), remap(group, xyz.outputs["Z"], -0.62, -0.36))
    for axis, limit in (("X", 1.6), ("Y", 1.3), ("Z", 0.98)):
        density = op(group, "MULTIPLY", density, remap(group, op(group, "ABSOLUTE", xyz.outputs[axis]), limit * 0.82, limit * 0.98, 1.0, 0.0))
    cube = new(group, "GeometryNodeVolumeCube")
    wire(group, density, cube.inputs["Density"])
    cube.inputs["Min"].default_value = (-1.6, -1.3, -0.8)
    cube.inputs["Max"].default_value = (1.6, 1.3, 1.0)
    cube.inputs["Resolution X"].default_value = 72
    cube.inputs["Resolution Y"].default_value = 58
    cube.inputs["Resolution Z"].default_value = 42
    paint = new(group, "GeometryNodeSetMaterial")
    paint.inputs["Material"].default_value = mat
    out = new(group, "NodeGroupOutput")
    group.links.new(cube.outputs["Volume"], paint.inputs["Geometry"])
    group.links.new(paint.outputs["Geometry"], out.inputs["Geometry"])
    mesh = bpy.data.meshes.new("cumulus%d" % seed)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new("cumulus%d" % seed, mesh)
    modifier = obj.modifiers.new("cloud", "NODES")
    modifier.node_group = group
    collection = bpy.data.collections.new("cumulus%d" % seed)
    collection.objects.link(obj)
    return collection


def sea_slab(name, mat, ladder_at, low, high, resolution):
    group = bpy.data.node_groups.new(name, "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    position = new(group, "GeometryNodeInputPosition").outputs["Position"]
    xyz = new(group, "ShaderNodeSeparateXYZ")
    group.links.new(position, xyz.inputs[0])

    def scaled_place(scale, flatten):
        n = new(group, "ShaderNodeVectorMath", operation="MULTIPLY")
        group.links.new(position, n.inputs[0])
        n.inputs[1].default_value = (scale, scale, scale * flatten)
        return n.outputs[0]

    def billow(scale, detail, flatten=1.0):
        n = new(group, "ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 1
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = 0.6
        group.links.new(scaled_place(scale, flatten), n.inputs["Vector"])
        return n.outputs["Fac"]

    def puffs(scale):
        n = new(group, "ShaderNodeTexVoronoi")
        n.inputs["Scale"].default_value = 1
        group.links.new(scaled_place(scale, 0.6), n.inputs["Vector"])
        d = op(group, "MINIMUM", n.outputs["Distance"], 1.0)
        return op(group, "SQRT", op(group, "SUBTRACT", 1.0, op(group, "POWER", d, 2.0)))

    base = ladder_at.z - 9.4
    cover = op(group, "MULTIPLY", op(group, "SUBTRACT", billow(0.07, 3, 0.2), 0.47), 9.0)
    top = op(group, "ADD", base, op(group, "MULTIPLY", puffs(0.2), 2.2))
    top = op(group, "ADD", top, op(group, "MULTIPLY", puffs(0.55), 1.0))
    top = op(group, "ADD", top, cover)
    top = op(group, "ADD", top, op(group, "MULTIPLY", op(group, "SUBTRACT", billow(0.9, 5), 0.5), 2.0))
    dx = op(group, "SUBTRACT", xyz.outputs["X"], ladder_at.x + 0.7)
    dy = op(group, "SUBTRACT", xyz.outputs["Y"], ladder_at.y + 0.3)
    near = op(group, "ADD", op(group, "POWER", op(group, "ABSOLUTE", dx), 2.0), op(group, "POWER", op(group, "ABSOLUTE", dy), 2.0))
    mound = op(group, "POWER", 2.718, op(group, "MULTIPLY", near, -1 / 9.0))
    top = op(group, "ADD", top, op(group, "MULTIPLY", mound, 5.0))
    top = op(group, "MINIMUM", top, ladder_at.z - 1.35)
    depth = op(group, "SUBTRACT", top, xyz.outputs["Z"])
    density = op(group, "MULTIPLY", remap(group, depth, 0.0, 0.45), remap(group, xyz.outputs["Z"], low[2], low[2] + 1.0))
    cube = new(group, "GeometryNodeVolumeCube")
    wire(group, density, cube.inputs["Density"])
    cube.inputs["Min"].default_value = low
    cube.inputs["Max"].default_value = high
    for axis, count in zip("XYZ", resolution):
        cube.inputs["Resolution " + axis].default_value = count
    paint = new(group, "GeometryNodeSetMaterial")
    paint.inputs["Material"].default_value = mat
    out = new(group, "NodeGroupOutput")
    group.links.new(cube.outputs["Volume"], paint.inputs["Geometry"])
    group.links.new(paint.outputs["Geometry"], out.inputs["Geometry"])
    mesh = bpy.data.meshes.new(name)
    mesh.materials.append(mat)
    obj = link_object(bpy.data.objects.new(name, mesh))
    modifier = obj.modifiers.new("cloud", "NODES")
    modifier.node_group = group
    return obj


def build_sea(ladder_at):
    mat = cloud_matter("cloud_sea", 3.2, 0.2)
    mat.cycles.volume_step_rate = 0.4
    x, y, z = ladder_at
    low, high = z - 12.5, z - 1.2
    near = sea_slab("sea_near", mat, ladder_at, (x - 34, y - 34, low), (x + 34, y + 40, high), (190, 205, 40))
    far = sea_slab("sea_far", mat, ladder_at, (x - 190, y + 40, low), (x + 190, y + 330, z - 3.0), (260, 200, 14))
    left = sea_slab("sea_left", mat, ladder_at, (x - 190, y - 34, low), (x - 34, y + 40, z - 3.0), (104, 52, 14))
    right = sea_slab("sea_right", mat, ladder_at, (x + 34, y - 34, low), (x + 190, y + 40, z - 3.0), (104, 52, 14))
    deep, t, out = bare("below_clouds")
    place = new(t, "ShaderNodeNewGeometry").outputs["Position"]
    emission = new(t, "ShaderNodeEmission")
    t.links.new(gradient(t, grain(t, place, (0.05, 0.05, 0.05), 6, 0.65), [(0.38, (54, 94, 150)), (0.55, (104, 146, 192)), (0.7, (176, 198, 216))]), emission.inputs["Color"])
    t.links.new(emission.outputs[0], out.inputs["Surface"])
    under = mesh_object("under", [(x - 1500, y - 200, low - 0.4), (x + 1500, y - 200, low - 0.4), (x + 1500, y + 2500, low - 0.4), (x - 1500, y + 2500, low - 0.4)], [(0, 1, 2, 3)], deep)
    return [near, far, left, right, under]


def build_clouds(base, ladder_at):
    mat = cloud_matter()
    kinds = [cloud_kind(i, mat) for i in range(1, 6)]
    rnd = random.Random(23)

    def add(loc, size, flat=1.0):
        obj = bpy.data.objects.new("cloud", None)
        obj.instance_type = "COLLECTION"
        obj.instance_collection = rnd.choice(kinds)
        scene.collection.objects.link(obj)
        obj.location = loc
        obj.rotation_euler = (0, 0, rnd.uniform(0, math.tau))
        obj.scale = (size, size, size * flat)
        return obj

    layer = []
    route = [hermite(PATH[0], PATH[1], 10.5 + i * 0.05) for i in range(45)]
    while len(layer) < 22:
        loc = base + Vector((rnd.uniform(-38, 38), rnd.uniform(0, 50), rnd.uniform(13, 27)))
        size = rnd.uniform(3.5, 6.5)
        if min((loc - p).length for p in route) > size * 1.5 + 1.5:
            layer.append(add(loc, size, 0.8))
    return layer, build_sea(ladder_at)


def build_flame(parent, location):
    m, t, out = bare("fire")
    p = new(t, "ShaderNodeTexCoord").outputs["Object"]
    xyz = new(t, "ShaderNodeSeparateXYZ")
    t.links.new(p, xyz.inputs[0])
    x, y, z = (xyz.outputs[a] for a in "XYZ")
    shifted = new(t, "ShaderNodeVectorMath", operation="SUBTRACT")
    t.links.new(p, shifted.inputs[0])
    rise = new(t, "ShaderNodeCombineXYZ")
    t.links.new(op(t, "MULTIPLY", shared(t, CLOCK), 2.6), rise.inputs["Z"])
    t.links.new(rise.outputs[0], shifted.inputs[1])
    wobble = op(t, "SUBTRACT", grain(t, shifted.outputs[0], (3.2, 3.2, 1.8), 7, 0.68), 0.5)
    lick = op(t, "SUBTRACT", grain(t, shifted.outputs[0], (6.5, 6.5, 2.6), 5, 0.65, (4, 1, 7)), 0.5)
    lean = op(t, "ADD", x, op(t, "ADD", op(t, "MULTIPLY", z, 0.32), op(t, "MULTIPLY", wobble, 1.1)))
    radial = op(t, "SQRT", op(t, "ADD", op(t, "POWER", op(t, "ABSOLUTE", lean), 2.0), op(t, "POWER", op(t, "ABSOLUTE", op(t, "ADD", y, wobble)), 2.0)))
    width = remap(t, z, -0.7, 1.0, 0.8, 0.12)
    body = remap(t, op(t, "ADD", op(t, "DIVIDE", radial, width), op(t, "MULTIPLY", lick, 2.4)), 0.15, 0.95, 1.0, 0.0)
    body = op(t, "MULTIPLY", body, remap(t, z, -1.0, -0.65))
    body = op(t, "MULTIPLY", body, remap(t, op(t, "ADD", z, op(t, "MULTIPLY", lick, 3.2)), 0.15, 0.9, 1.0, 0.0))
    color = gradient(t, body, [(0.05, (120, 14, 4)), (0.3, (232, 62, 4)), (0.65, (255, 146, 18)), (0.97, (255, 226, 130))])
    emission = new(t, "ShaderNodeEmission")
    t.links.new(color, emission.inputs["Color"])
    wire(t, op(t, "MULTIPLY", op(t, "POWER", body, 1.8), 17.0), emission.inputs["Strength"])
    t.links.new(emission.outputs[0], out.inputs["Volume"])
    m.cycles.volume_step_rate = 0.12
    obj = box("flame", (2, 2, 2), location, m, parent)
    obj.scale = (0.19, 0.19, 0.36)
    spark = surface("ember", (255, 130, 30), 0.5, 0.0, (255, 120, 24), 14.0)
    rnd = random.Random(9)
    embers = []
    for _ in range(46):
        e = box("ember", (1, 1, 1), location, spark, parent)
        size = rnd.uniform(0.006, 0.017)
        e.scale = (size, size, size * 1.8)
        embers.append((e, Vector(location), rnd.random(), rnd.uniform(-0.55, 0.35), rnd.uniform(-0.3, 0.3), rnd.uniform(0.7, 1.9)))
    return embers


def relief_map(folder):
    image = picture(os.path.join(ASSETS, folder, "disp.jpg"), True)
    w, h = image.size
    pixels = np.empty(w * h * 4, np.float32)
    image.pixels.foreach_get(pixels)
    grid = pixels.reshape(h, w, 4)[..., 0]
    low, high = np.percentile(grid, (2, 98))
    grid = np.clip((grid - low) / max(1e-4, high - low), 0, 1)

    def at(u, v):
        return float(grid[int((v % 1.0) * (h - 1)), int((u % 1.0) * (w - 1))])

    return at


def timber(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    bsdf = t.nodes["Principled BSDF"]
    uv = new(t, "ShaderNodeTexCoord").outputs["UV"]
    base = os.path.join(ASSETS, "rough_wood")
    place = new(t, "ShaderNodeNewGeometry").outputs["Position"]
    color = sample(t, os.path.join(base, "diff.jpg"), uv)
    rich = new(t, "ShaderNodeHueSaturation")
    rich.inputs["Saturation"].default_value = 1.2
    rich.inputs["Value"].default_value = 1.7
    t.links.new(color, rich.inputs["Color"])
    warm = blend(t, 1.0, rich.outputs["Color"], lin((255, 186, 122)), "MULTIPLY")
    warm = blend(t, remap(t, grain(t, place, (2.2, 2.2, 1.1), 6, 0.7), 0.42, 0.66), warm, blend(t, 1.0, warm, lin((150, 112, 90)), "MULTIPLY"))
    burnt = new(t, "ShaderNodeAttribute")
    burnt.attribute_name = "char"
    char = burnt.outputs["Fac"]
    black = blend(t, grain(t, place, (26, 26, 26), 5, 0.7), lin((10, 7, 6)), lin((46, 38, 34)))
    t.links.new(blend(t, char, warm, black), bsdf.inputs["Base Color"])
    rough = sample(t, os.path.join(base, "rough.jpg"), uv, True)
    t.links.new(remap(t, rough, 0.0, 1.0, 0.45, 0.92), bsdf.inputs["Roughness"])
    normal = new(t, "ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 1.6
    t.links.new(sample(t, os.path.join(base, "nor.jpg"), uv, True), normal.inputs["Color"])
    t.links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
    cracks = new(t, "ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
    cracks.inputs["Scale"].default_value = 22
    t.links.new(place, cracks.inputs["Vector"])
    ember = op(t, "MULTIPLY", remap(t, cracks.outputs["Distance"], 0.0, 0.07, 1.0, 0.0), remap(t, char, 0.55, 1.0))
    ember = op(t, "MULTIPLY", ember, remap(t, grain(t, place, (5, 5, 5), 3, 0.6), 0.45, 0.68))
    bsdf.inputs["Emission Color"].default_value = lin((255, 92, 14))
    wire(t, op(t, "MULTIPLY", ember, 9.0), bsdf.inputs["Emission Strength"])
    return m


def end_grain(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    bsdf = t.nodes["Principled BSDF"]
    uv = new(t, "ShaderNodeTexCoord").outputs["UV"]
    xyz = new(t, "ShaderNodeSeparateXYZ")
    t.links.new(uv, xyz.inputs[0])
    place = new(t, "ShaderNodeNewGeometry").outputs["Position"]
    wobble = op(t, "MULTIPLY", grain(t, place, (30, 30, 30), 4, 0.7), 5.0)
    rings = op(t, "SINE", op(t, "ADD", op(t, "MULTIPLY", xyz.outputs["X"], 42.0), wobble))
    t.links.new(blend(t, remap(t, rings, -0.6, 0.6), lin((74, 46, 30)), lin((150, 102, 66))), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    return m


def beam(name, start, end, size_start, size_end, mats, relief, seed, square, parent, char_at):
    rnd = random.Random(seed)
    axis = end - start
    length = axis.length
    direction = axis.normalized()
    side = direction.cross(Vector((0, 1, 0))).normalized()
    front = side.cross(direction).normalized()
    rings, around = max(60, int(length * 70)), 56
    verts, uvs, chars, faces, slots = [], [], [], [], []
    offset = rnd.random()
    for i in range(rings + 1):
        f = i / rings
        size = size_start + (size_end - size_start) * f
        bend = side * noise.noise(Vector((f * length * 1.3, seed, 0))) * 0.035 + front * noise.noise(Vector((f * length * 1.3, 0, seed))) * 0.03
        center = start + axis * f + bend
        end_rag = max(0.0, 1 - min(f, 1 - f) * length / 0.09)
        for k in range(around + 1):
            a = (k % around) / around * math.tau
            c, s = math.cos(a), math.sin(a)
            cx = math.copysign(abs(c) ** square, c)
            cy = math.copysign(abs(s) ** square, s)
            u = k / around * size * 6.0 + offset
            v = f * length / 1.15 + offset * 3
            wrapped = (0 if k == around else k) / around * size * 6.0 + offset
            lift = (relief(wrapped, v) - 0.55) * size * 0.34
            chip = max(0.0, noise.noise(center * 5.0 + side * cx * 2.0 + Vector((seed, 0, 0))) - 0.28) * size * 0.7
            out = (side * cx + front * cy * 0.85)
            p = center + out * (size * (1 - 0.16 * end_rag * rnd.random()) + lift - chip)
            p += direction * end_rag * noise.noise(Vector((k * 0.45, seed, f * 9))) * 0.07 * (1 if f > 0.5 else -1)
            verts.append(p)
            uvs.append((u, v))
            chars.append(char_at(p))
    row = around + 1
    for i in range(rings):
        for k in range(around):
            a = i * row + k
            faces.append((a, a + 1, a + row + 1, a + row))
            slots.append(0)
    for ring, flip in ((0, True), (rings, False)):
        first = ring * row
        middle = sum((verts[first + k] for k in range(around)), Vector()) / around
        for k in range(around):
            ids = []
            for p, radius in ((middle, 0.0), (verts[first + k], 1.0), (verts[first + k + 1], 1.0)):
                verts.append(p.copy())
                uvs.append((radius, 0))
                chars.append(char_at(p))
                ids.append(len(verts) - 1)
            faces.append(tuple(reversed(ids)) if flip else tuple(ids))
            slots.append(1)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    for mat in mats:
        mesh.materials.append(mat)
    layer = mesh.uv_layers.new(name="UVMap")
    loop = 0
    for index, polygon in enumerate(mesh.polygons):
        polygon.material_index = slots[index]
        polygon.use_smooth = slots[index] == 0
        for corner in faces[index]:
            layer.data[loop].uv = uvs[corner]
            loop += 1
    burnt = mesh.attributes.new("char", "FLOAT", "POINT")
    burnt.data.foreach_set("value", np.array(chars, np.float32))
    mesh.update()
    return link_object(bpy.data.objects.new(name, mesh), parent)


def build_ladder(parent):
    wood = timber("ladder_wood")
    grain_end = end_grain("ladder_end")
    relief = relief_map("rough_wood")

    top = Vector((0.32, 9.83, 2.62))
    bottom = Vector((1.5, 9.28, -2.3))
    axis = (top - bottom).normalized()
    side = axis.cross(Vector((0, 1, 0))).normalized()
    if side.x < 0:
        side.negate()
    half = 0.29
    left_top = top - side * half

    def burn(p):
        ragged = noise.noise(p * 8.0) * 0.14 + noise.noise(p * 23.0) * 0.07
        return smooth((0.62 - (p - left_top).length + ragged) / 0.28)

    for i, sign in enumerate((-1, 1)):
        beam("rail%d" % i, bottom + side * half * sign, top + side * half * sign, 0.05, 0.046, [wood, grain_end], relief, 3 + i, 0.4, parent, burn)
    length = (top - bottom).length
    place = 0.22
    step = 0
    while place < length - 0.18:
        middle = top - axis * place
        beam("rung%d" % step, middle - side * (half + 0.075), middle + side * (half + 0.075), 0.027, 0.027, [wood, grain_end], relief, 20 + step, 1.0, parent, burn)
        place += 0.3
        step += 1


DOOR = Vector((0.32, 0.14, 3.66))


def build_door(ladder_root):
    root = empty("door_root")
    wood = textured("door_wood", "rough_pine_door", 0.46, (255, 226, 196), (0.32, 0.7), 1.2, True)
    frame = textured("door_frame", "weathered_brown_planks", 0.9, (205, 160, 125), (0.45, 0.85), 1.4, True)
    iron = surface("iron", (44, 36, 32), 0.45, 0.9)
    brass = surface("brass", (214, 164, 92), 0.26, 1.0)
    width, height = 1.16, 2.2
    for side in (-1, 1):
        box("jamb", (0.16, 0.26, height + 0.32), (side * (width / 2 + 0.085), 0, 0), frame, root, bevel=0.022)
        box("trim", (0.05, 0.3, height + 0.12), (side * (width / 2 + 0.025), 0, 0), frame, root, bevel=0.012)
    for z in (-1, 1):
        box("lintel", (width + 0.52, 0.29, 0.16), (0, 0, z * (height / 2 + 0.085)), frame, root, bevel=0.022)
    box("crown", (width + 0.66, 0.34, 0.07), (0, 0, height / 2 + 0.2), frame, root, bevel=0.018)
    box("step", (width + 0.66, 0.42, 0.08), (0, -0.04, -height / 2 - 0.2), frame, root, bevel=0.018)
    m, t, out = bare("beyond")
    p = new(t, "ShaderNodeTexCoord").outputs["Object"]
    warped = new(t, "ShaderNodeVectorMath", operation="MULTIPLY")
    t.links.new(p, warped.inputs[0])
    warped.inputs[1].default_value = (1.5, 1.0, 0.8)
    length = new(t, "ShaderNodeVectorMath", operation="LENGTH")
    t.links.new(warped.outputs[0], length.inputs[0])
    mist = op(t, "SUBTRACT", grain(t, p, (2.4, 1, 1.7), 7, 0.66), 0.5)
    heat = op(t, "ADD", length.outputs["Value"], op(t, "MULTIPLY", mist, 0.9))
    color = gradient(t, remap(t, heat, 0.0, 1.35), [(0.0, (255, 252, 240)), (0.35, (255, 226, 164)), (0.62, (255, 170, 98)), (0.85, (214, 104, 92)), (1.0, (120, 66, 110))])
    emission = new(t, "ShaderNodeEmission")
    t.links.new(color, emission.inputs["Color"])
    wire(t, remap(t, shared(t, OPEN), 0.0, 1.0, 2.6, 1.25), emission.inputs["Strength"])
    t.links.new(emission.outputs[0], out.inputs["Surface"])
    mesh_object("beyond", [(-width / 2, 0.09, -height / 2), (width / 2, 0.09, -height / 2), (width / 2, 0.09, height / 2), (-width / 2, 0.09, height / 2)], [(0, 1, 2, 3)], m, root)
    hinge = empty("hinge", root)
    hinge.location = (-width / 2 + 0.012, -0.07, 0)
    leaf = width - 0.045
    box("leaf", (leaf, 0.075, height - 0.04), (leaf / 2, 0, 0), wood, hinge, bevel=0.008)
    for z in (0.72, -0.72):
        box("strap", (leaf * 0.72, 0.018, 0.075), (leaf * 0.36, -0.045, z), iron, hinge, bevel=0.006)
        for i in range(5):
            tube("rivet", [(0.07 + i * 0.17, -0.05, z), (0.07 + i * 0.17, -0.068, z)], 0.017, iron, hinge)
    box("plate", (0.09, 0.016, 0.26), (leaf - 0.12, -0.045, -0.04), iron, hinge, bevel=0.006)
    tube("knob_stem", [(leaf - 0.12, -0.04, 0.0), (leaf - 0.12, -0.12, 0.0)], 0.018, brass, hinge)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.052, segments=48, ring_count=24)
    knob = bpy.context.object
    knob.data.materials.append(brass)
    bpy.ops.object.shade_smooth()
    knob.parent = hinge
    knob.location = (leaf - 0.12, -0.14, 0.0)
    haze, t, out = bare("door_haze")
    p = new(t, "ShaderNodeTexCoord").outputs["Object"]
    flat_place = new(t, "ShaderNodeVectorMath", operation="MULTIPLY")
    t.links.new(p, flat_place.inputs[0])
    flat_place.inputs[1].default_value = (1.0, 0.35, 0.9)
    length = new(t, "ShaderNodeVectorMath", operation="LENGTH")
    t.links.new(flat_place.outputs[0], length.inputs[0])
    rays = remap(t, grain(t, p, (7.0, 0.5, 5.0), 3, 0.6), 0.4, 0.68, 0.15, 1.6)
    thick = op(t, "MULTIPLY", op(t, "POWER", remap(t, length.outputs["Value"], 0.15, 0.95, 1.0, 0.0), 2.0), rays)
    thick = op(t, "MULTIPLY", thick, remap(t, shared(t, OPEN), 0.0, 1.0, 0.08, 1.0))
    glow = new(t, "ShaderNodeEmission")
    glow.inputs["Color"].default_value = lin((255, 190, 120))
    wire(t, op(t, "MULTIPLY", thick, 0.65), glow.inputs["Strength"])
    t.links.new(glow.outputs[0], out.inputs["Volume"])
    haze.cycles.volume_step_rate = 0.5
    cloud = box("haze", (2, 2, 2), (0, -0.7, 0), haze, root)
    cloud.scale = (1.7, 1.3, 2.1)
    spill = lamp("spill", "AREA", (255, 196, 140), 8.0, root, (0, -0.15, 0), size=1.0)
    spill.rotation_euler = (math.radians(-90), 0, 0)
    face = lamp("door_key", "AREA", (255, 220, 180), 80.0, root, (1.7, -2.4, 0.9), size=1.2)
    face.rotation_euler = Vector((-1.7, 2.4, -0.9)).to_track_quat("-Z", "Y").to_euler()
    root.location = ladder_root.location + Vector((0, 10, 0)) + DOOR
    return root, hinge, spill


CAR_FILE = os.path.join(HERE, "car", "porsche.glb")
HIDDEN = ("logo_", "number_plate", "window_door_1_windows_0", "window_door_2_windows_0")


def points(mesh):
    co = np.empty(len(mesh.vertices) * 3, np.float64)
    mesh.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def islands(mesh):
    parent = list(range(len(mesh.vertices)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    edges = np.empty(len(mesh.edges) * 2, np.int64)
    mesh.edges.foreach_get("vertices", edges)
    for a, b in edges.reshape(-1, 2).tolist():
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[ra] = rb
    return np.array([root(i) for i in range(len(parent))])


def close_door(meshes):
    door = []
    for mesh in meshes:
        co = points(mesh)
        label = islands(mesh)
        for part in np.unique(label):
            pick = np.nonzero(label == part)[0]
            lo, hi = co[pick].min(0), co[pick].max(0)
            if hi[1] > 1.0 and lo[1] > 0.2 and hi[0] - lo[0] < 2.0:
                door.append((mesh, pick))
    if not door:
        return 0.0
    pts = np.concatenate([points(mesh)[pick] for mesh, pick in door])
    front = pts[pts[:, 0] > pts[:, 0].max() - 0.05]
    hinge = np.array([pts[:, 0].max(), front[:, 1].min()])
    flat = pts[:, :2] - hinge
    spread = np.cov(flat.T)
    axis = np.linalg.eigh(spread)[1][:, -1]
    if axis @ flat.mean(0) < 0:
        axis = -axis
    angle = math.pi - math.atan2(axis[1], axis[0])
    angle = (angle + math.pi) % math.tau - math.pi
    c, s = math.cos(angle), math.sin(angle)
    for mesh, pick in door:
        co = points(mesh)
        x, y = co[pick, 0] - hinge[0], co[pick, 1] - hinge[1]
        co[pick, 0] = hinge[0] + x * c - y * s
        co[pick, 1] = hinge[1] + x * s + y * c
        mesh.vertices.foreach_set("co", co.ravel())
        mesh.update()
    return math.degrees(angle)


def weather(material):
    t = material.node_tree
    bsdf = t.nodes.get("Principled BSDF")
    if bsdf is None:
        return
    place = new(t, "ShaderNodeTexCoord").outputs["Object"]
    edge = remap(t, new(t, "ShaderNodeNewGeometry").outputs["Pointiness"], 0.52, 0.62)
    blotch = remap(t, grain(t, place, (7.0, 7.0, 7.0), 5, 0.62), 0.42, 0.72)

    def taken(name):
        socket = bsdf.inputs[name]
        if not socket.is_linked:
            value = socket.default_value
            return float(value) if isinstance(value, float) else tuple(value)
        link = socket.links[0]
        source = link.from_socket
        t.links.remove(link)
        return source

    grimy = blend(t, op(t, "MULTIPLY", blotch, 0.05), taken("Base Color"), lin((40, 36, 32)))
    t.links.new(blend(t, op(t, "MULTIPLY", edge, 0.08), grimy, lin((235, 230, 222))), bsdf.inputs["Base Color"])
    patchy = op(t, "MULTIPLY", taken("Roughness"), op(t, "ADD", 0.94, op(t, "MULTIPLY", blotch, 0.12)))
    wire(t, op(t, "ADD", patchy, op(t, "MULTIPLY", edge, 0.05)), bsdf.inputs["Roughness"])
    bump = new(t, "ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.03
    bump.inputs["Distance"].default_value = 0.001
    wire(t, grain(t, place, (140.0, 140.0, 140.0), 3, 0.55), bump.inputs["Height"])
    if bsdf.inputs["Normal"].is_linked:
        link = bsdf.inputs["Normal"].links[0]
        t.links.new(link.from_socket, bump.inputs["Normal"])
        t.links.remove(link)
    t.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def ghost(material):
    t = material.node_tree
    out = next((n for n in t.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if out is None or not out.inputs["Surface"].is_linked:
        return
    link = out.inputs["Surface"].links[0]
    shader = link.from_socket
    t.links.remove(link)
    clear = new(t, "ShaderNodeBsdfTransparent")
    mix = new(t, "ShaderNodeMixShader")
    t.links.new(shared(t, PHASE), mix.inputs[0])
    t.links.new(shader, mix.inputs[1])
    t.links.new(clear.outputs[0], mix.inputs[2])
    t.links.new(mix.outputs[0], out.inputs["Surface"])


def build_porsche():
    root = empty("car")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=CAR_FILE)
    bpy.context.view_layer.update()
    added = [o for o in bpy.data.objects if o not in before]
    parts = []
    for o in added:
        if o.type == "MESH":
            mesh = o.data if o.data.users == 1 else o.data.copy()
            mesh.transform(o.matrix_world)
            parts.append((o.name, mesh))
    for o in added:
        bpy.data.objects.remove(o)
    opened = close_door([mesh for _, mesh in parts])
    body = points(next(mesh for name, mesh in parts if "body_main" in name))
    ground = min(points(mesh)[:, 2].min() for name, mesh in parts if "tire" in name)
    lo, hi = body.min(0), body.max(0)
    center = Vector(((lo[0] + hi[0]) / 2, (lo[1] + min(hi[1], -lo[1])) / 2, ground))
    place = Matrix.Rotation(math.pi / 2, 4, "Z") @ Matrix.Translation(-center)
    pane = thin_glass("porsche_glass")
    faded = set()
    for name, mesh in parts:
        if any(name.startswith(prefix) for prefix in HIDDEN):
            continue
        mesh.transform(place)
        if name.startswith("windows_main_windows"):
            mesh.materials.clear()
            mesh.materials.append(pane)
        elif name.startswith("mirror_middle"):
            for material in mesh.materials:
                bsdf = material.node_tree.nodes.get("Principled BSDF")
                for socket in ("Base Color", "Metallic", "Roughness"):
                    for link in list(bsdf.inputs[socket].links):
                        material.node_tree.links.remove(link)
                bsdf.inputs["Base Color"].default_value = (0.92, 0.92, 0.92, 1)
                bsdf.inputs["Metallic"].default_value = 1.0
                bsdf.inputs["Roughness"].default_value = 0.02
        else:
            for material in mesh.materials:
                if material is not None and material.use_nodes and material.name not in faded:
                    faded.add(material.name)
                    bsdf = material.node_tree.nodes.get("Principled BSDF")
                    if bsdf is not None and ("leather" in material.name or "steering" in material.name):
                        bsdf.inputs["Coat Weight"].default_value = 0.2
                        bsdf.inputs["Coat Roughness"].default_value = 0.3
                    weather(material)
                    ghost(material)
        link_object(bpy.data.objects.new(name, mesh), root)
    print("porsche door turned %.1f deg, body size" % opened, [round(float(v), 2) for v in hi - lo], "ground", round(float(ground), 3), flush=True)
    return root


def thin_glass(name):
    m, t, out = bare(name)
    geometry = new(t, "ShaderNodeNewGeometry")
    facing = new(t, "ShaderNodeVectorMath", operation="DOT_PRODUCT")
    t.links.new(geometry.outputs["Incoming"], facing.inputs[0])
    t.links.new(geometry.outputs["Normal"], facing.inputs[1])
    grazing = op(t, "POWER", op(t, "SUBTRACT", 1.0, op(t, "ABSOLUTE", facing.outputs["Value"])), 5.0)
    mirror = op(t, "MINIMUM", op(t, "MULTIPLY", op(t, "ADD", 0.04, op(t, "MULTIPLY", grazing, 0.96)), 2.0), 1.0)
    place = new(t, "ShaderNodeNewGeometry").outputs["Position"]
    smudge = remap(t, grain(t, place, (3.0, 3.0, 3.0), 4, 0.6), 0.45, 0.75)
    specks = new(t, "ShaderNodeTexVoronoi")
    specks.inputs["Scale"].default_value = 260
    t.links.new(place, specks.inputs["Vector"])
    dust = op(t, "ADD", op(t, "MULTIPLY", smudge, 0.035), op(t, "MULTIPLY", remap(t, specks.outputs["Distance"], 0.03, 0.0), 0.25))
    clear = new(t, "ShaderNodeBsdfTransparent")
    clear.inputs["Color"].default_value = (0.84, 0.9, 0.87, 1)
    shine = new(t, "ShaderNodeBsdfAnisotropic")
    wire(t, op(t, "ADD", 0.02, op(t, "MULTIPLY", smudge, 0.12)), shine.inputs["Roughness"])
    mix = new(t, "ShaderNodeMixShader")
    t.links.new(mirror, mix.inputs[0])
    t.links.new(clear.outputs[0], mix.inputs[1])
    t.links.new(shine.outputs[0], mix.inputs[2])
    haze = new(t, "ShaderNodeBsdfDiffuse")
    haze.inputs["Color"].default_value = (0.8, 0.8, 0.78, 1)
    dirty = new(t, "ShaderNodeMixShader")
    t.links.new(dust, dirty.inputs[0])
    t.links.new(mix.outputs[0], dirty.inputs[1])
    t.links.new(haze.outputs[0], dirty.inputs[2])
    t.links.new(dirty.outputs[0], out.inputs["Surface"])
    return m


def keyed(objects, camera, frame):
    for obj in objects:
        obj.keyframe_insert("location", frame=frame)
        obj.keyframe_insert("rotation_euler", frame=frame)
    camera.keyframe_insert("lens", frame=frame)


def finish():
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    layers = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    for name, value in (("Threshold", 3.5), ("Strength", 0.22), ("Size", 0.5)):
        if name in glare.inputs:
            glare.inputs[name].default_value = value
    tree.links.new(layers.outputs["Image"], glare.inputs["Image"])
    out = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(glare.outputs[0], out.inputs["Image"])


def main():
    for obj in list(scene.collection.objects):
        if obj.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(obj)
    ladder_root = empty("ladder_root")
    for obj in ladder_parts:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj)
    ladder_root.location = LADDER_AT - Vector((0, 10, 0))
    sun_direction, sun_strength, sun_color = build_sky()
    before = set(scene.collection.objects)
    build_road()
    build_forest()
    build_sign()
    traffic = build_traffic()
    car = build_porsche()
    ground_set = [obj for obj in scene.collection.objects if obj not in before]
    layer, sea = build_clouds(START, LADDER_AT)
    embers = build_flame(ladder_root, (0.0, 9.76, 2.78))
    fire = lamp("firelight", "POINT", (255, 120, 40), 6.0, ladder_root, (-0.05, 9.5, 2.7), shadow_soft_size=0.15)
    build_ladder(ladder_root)
    door, hinge, spill = build_door(ladder_root)
    sky_set = list(ladder_root.children_recursive) + list(door.children_recursive)
    sun = lamp("sun", "SUN", (255, 146, 78), 3.0, angle=math.radians(0.7))

    soft = lamp("dash_fill", "AREA", (255, 206, 168), 1.5, car, (0.15, -0.55, 1.26), size=0.5)
    soft.rotation_euler = Vector((-0.1, 0.85, -0.52)).to_track_quat("-Z", "Y").to_euler()
    camera = bpy.data.cameras.new("view")
    camera.sensor_fit = "VERTICAL"
    camera.sensor_height = 36
    camera.clip_start = 0.02
    camera.clip_end = 6000
    camera.dof.use_dof = True
    camera.dof.focus_distance = 25.0
    camera.dof.aperture_fstop = 4.5
    cam = link_object(bpy.data.objects.new("view", camera))
    scene.camera = cam

    r = scene.render
    r.engine = "CYCLES"
    r.resolution_x, r.resolution_y = 540, 1170
    r.image_settings.file_format = "JPEG"
    r.image_settings.quality = 96
    r.use_persistent_data = True
    r.use_motion_blur = True
    r.motion_blur_shutter = 0.16
    c = scene.cycles
    c.samples = 48
    if os.environ.get("HIGH"):
        r.resolution_percentage = 200
        c.samples = 96
    if os.environ.get("PREVIEW"):
        r.resolution_percentage = 50
        c.samples = 16
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.04
    c.use_denoising = True
    c.max_bounces = 7
    c.diffuse_bounces = 3
    c.glossy_bounces = 4
    c.transmission_bounces = 4
    c.transparent_max_bounces = 32
    c.volume_bounces = 0
    c.volume_step_rate = 4.0
    c.volume_max_steps = 384
    c.sample_clamp_indirect = 6.0
    finish()
    moving = [cam, car, hinge]
    previous = {}

    def turn(obj, quaternion):
        euler = quaternion.to_euler("XYZ", previous[obj]) if obj in previous else quaternion.to_euler("XYZ")
        previous[obj] = euler.copy()
        obj.rotation_euler = euler

    def pose(t):
        pos, aim, lens = view(t)
        cam.location = pos
        turn(cam, (aim - pos).to_track_quat("-Z", "Y"))
        camera.lens = lens
        frame = car_frame(t)
        car.location = frame.translation
        for other, x, y, speed in traffic:
            other.location = (x, y + speed * t, 0)
        turn(car, frame.to_quaternion())
        high = span(t, 10.9, 11.7)
        NIGHT[1].outputs[0].default_value = high
        clear = t >= 11.35
        bloom = scene.node_tree.nodes["Glare"]
        for name, value in (("Threshold", 1.4 if clear else 3.5), ("Strength", 0.35 if clear else 0.22)):
            if name in bloom.inputs:
                bloom.inputs[name].default_value = value
        scene.view_settings.view_transform = "Khronos PBR Neutral" if clear else "AgX"
        scene.view_settings.look = "None" if clear else "AgX - Medium High Contrast"
        scene.view_settings.exposure = 0.0 if clear else 1.0
        PHASE[1].outputs[0].default_value = span(t, 8.75, 9.05) * (1 - span(t, 9.6, 10.25))
        CLOCK[1].outputs[0].default_value = t
        opening = span(t, 14.05, 14.95)
        OPEN[1].outputs[0].default_value = opening
        hinge.rotation_euler = (0, 0, -math.radians(108) * opening)
        spill.data.energy = 8 + 150 * opening
        warm = Vector(sun_color) * Vector((1.0, 0.95, 0.86))
        warm = warm / max(warm)
        cream = Vector((255, 232, 200)) / 255
        sun.data.color = tuple(warm.lerp(cream, high))
        sun.data.energy = sun_strength + (4.2 - sun_strength) * high
        direction = sun_direction.lerp(Vector((0.74, -0.40, 0.54)).normalized(), high).normalized()
        sun.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
        fire.data.energy = 6 * (0.85 + 0.15 * math.sin(t * 31) * math.sin(t * 17))
        for obj in sky_set:
            obj.hide_render = t < 11.2
        for obj in ground_set:
            obj.hide_render = t >= 11.6
        for obj in layer:
            obj.hide_render = t < 7.8 or t > 12.7
        for obj in sea:
            obj.hide_render = t < 11.2
        sea[-1].hide_render = t < 11.2 or pos.z < LADDER_AT.z - 12.4
        for ember, origin, phase, side, depth, reach in embers:
            age = (phase + t * 0.55) % 1.0
            ember.location = origin + Vector((side * age + 0.07 * math.sin(age * 17 + phase * 40), depth * age, 0.15 + reach * age))
            ember.hide_render = t < 11.2 or age > 0.9

    shard, shards = (int(a) for a in sys.argv[-2:])
    listed = os.path.join(HERE, "frames.txt")
    wanted = open(listed).read().strip() if os.path.exists(listed) else "all"
    frames = list(range(FRAMES)) if wanted == "all" else [int(v) for v in wanted.split(",")]
    def place(t, outside):
        pose(t)
        if outside:
            frame_of_car = car_frame(t)
            cam.location = frame_of_car @ Vector((3.4, 4.6, 1.8))
            turn(cam, (frame_of_car @ Vector((0.0, 0.3, 0.6)) - cam.location).to_track_quat("-Z", "Y"))
            camera.lens = 30

    for wanted_frame in frames[shard::shards]:
        started = time.time()
        outside, frame = wanted_frame < 0, abs(wanted_frame)
        name = ("outside%04d" if outside else "f%04d") % frame
        for obj in moving:
            obj.animation_data_clear()
        camera.animation_data_clear()
        previous.clear()
        for step in (-1, 0, 1):
            place((frame + step) / FPS, outside)
            keyed(moving, camera, frame + step)
        place(frame / FPS, outside)
        scene.frame_set(frame)
        r.filepath = os.path.join(OUT, name + ".jpg")
        bpy.ops.render.render(write_still=True)
        settings = r.image_settings
        settings.file_format = "OPEN_EXR"
        settings.color_depth = "16"
        settings.exr_codec = "DWAA"
        bpy.data.images["Render Result"].save_render(os.path.join(OUT, name + ".exr"), scene=scene)
        settings.file_format = "JPEG"
        settings.quality = 96
        print("frame %d %.1fs" % (frame, time.time() - started), flush=True)


main()

