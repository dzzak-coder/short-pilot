"""Isolated CAD assembly experiment. Executes validated data, never model-written code."""
import argparse
import itertools
import json
import math
import re
from pathlib import Path

import cadquery as cq
import numpy as np


STAGES = {'foundation', 'structure', 'mechanism', 'envelope', 'finishes'}


def positive(params, key, default, low=0.1, high=1000):
    value = float(params.get(key, default))
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'Invalid dimension: {key}')
    return value


def frame(z=0, angle=0):
    a = math.radians(angle)
    result = np.eye(4)
    result[:3, :3] = [[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]]
    result[2, 3] = z
    return result


def component(kind, p):
    """Small explicit library for the first complete-product experiment."""
    height = positive(p, 'height', 50, 10, 200)
    hole = positive(p, 'hole_radius', 3, 1, 10)
    if kind == 'hinge_leaf':
        side = p.get('side')
        if side not in ('left', 'right'):
            raise ValueError('hinge_leaf.side must be left or right')
        outer = hole + 2
        # Five interleaved knuckles with a small axial clearance.
        pitch, clearance = height / 5, .2
        wing_start = outer + .2
        wing = cq.Workplane('XY').box(30 - wing_start, 3, height, centered=(False, True, False)).translate((wing_start, 0, 0))
        for i in ([0, 2, 4] if side == 'left' else [1, 3]):
            sleeve = (cq.Workplane('XY').circle(outer).circle(hole)
                .extrude(pitch - clearance).translate((0, 0, i * pitch + clearance / 2)))
            bridge = (cq.Workplane('XY').box(wing_start - (outer - 2) + .5, 3, pitch - clearance,
                centered=(False, True, False)).translate((outer - 2, 0, i * pitch + clearance / 2)))
            wing = wing.union(sleeve).union(bridge)
        # Reusable mounting holes on each leaf, through its thickness.
        for z in (height * .22, height * .78):
            cutter = cq.Workplane('XZ').center(20, z).circle(2).extrude(10, both=True)
            wing = wing.cut(cutter)
        return wing.val(), {'axis': frame(angle=0 if side == 'left' else 180)}
    if kind == 'hinge_pin':
        radius = positive(p, 'radius', 2.8, .1, hole - .01)
        shaft = cq.Workplane('XY').circle(radius).extrude(height + 1).translate((0, 0, -1))
        head = cq.Workplane('XY').circle(hole + 2).extrude(2).translate((0, 0, -3))
        return shaft.union(head).val(), {'axis': frame()}
    if kind == 'washer':
        thickness = positive(p, 'thickness', 1, .1, 5)
        washer = cq.Workplane('XY').circle(hole + 2.5).circle(hole).extrude(-thickness)
        return washer.val(), {'seat': frame()}
    raise ValueError(f'Unknown component factory: {kind}')


def cq_location(matrix):
    return cq.Location(cq.Plane(origin=tuple(matrix[:3, 3]),
        xDir=tuple(matrix[:3, 0]), normal=tuple(matrix[:3, 2])))


def build(spec):
    if spec.get('unsupported'):
        raise ValueError('Objet non pris en charge par cette bibliothèque expérimentale : ' + str(spec.get('reason', ''))[:200])
    parts = spec.get('parts', [])
    if not 2 <= len(parts) <= 50:
        raise ValueError('Expected 2–50 distinct components')
    records = {}
    for p in parts:
        name = p['id']
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', name) or name in records or p['stage'] not in STAGES:
            raise ValueError('Invalid/duplicate component or assembly stage')
        shape, ports = component(p['factory'], p.get('parameters', {}))
        if not shape.isValid() or shape.Volume() <= 0:
            raise ValueError(f'Invalid CAD solid: {name}')
        records[name] = dict(spec=p, shape=shape, ports=ports)
    # The first library supports one complete hinge only. Never pretend an
    # unsupported product has been reconstructed from a collection of primitives.
    leaves = [p for p in parts if p['factory'] == 'hinge_leaf']
    pins = [p for p in parts if p['factory'] == 'hinge_pin']
    washers = [p for p in parts if p['factory'] == 'washer']
    if len(parts) != 4 or len(leaves) != 2 or len(pins) != 1 or len(washers) != 1:
        raise ValueError('Trial library requires a complete four-component hinge')
    if {p.get('parameters', {}).get('side') for p in leaves} != {'left', 'right'}:
        raise ValueError('Two complementary hinge leaves required')
    heights = [positive(p.get('parameters', {}), 'height', 50) for p in leaves + pins]
    if max(heights) - min(heights) > 1e-6:
        raise ValueError('Pin and hinge leaf heights are incompatible')
    root = spec['root']
    records[root]['transform'] = np.eye(4)
    pending = list(spec.get('mates', []))
    if len(pending) != len(parts) - 1:
        raise ValueError('Trial requires one connected assembly tree')
    while pending:
        progressed = False
        for mate in pending[:]:
            parent, child = records[mate['parent']], records[mate['child']]
            a, b = parent['ports'][mate['parent_port']], child['ports'][mate['child_port']]
            if 'transform' in parent and 'transform' not in child:
                child['transform'] = parent['transform'] @ a @ np.linalg.inv(b)
            elif 'transform' in child and 'transform' not in parent:
                parent['transform'] = child['transform'] @ b @ np.linalg.inv(a)
            elif 'transform' in parent and 'transform' in child:
                raise ValueError('Conflicting or cyclic component placement')
            else:
                continue
            pending.remove(mate)
            progressed = True
        if not progressed:
            raise ValueError('Disconnected assembly or cyclic constraints')
    if any('transform' not in r for r in records.values()):
        raise ValueError('Disconnected component')
    for record in records.values():
        record['placed'] = record['shape'].moved(cq_location(record['transform']))
    clashes = []
    for (a, ra), (b, rb) in itertools.combinations(records.items(), 2):
        volume = ra['placed'].intersect(rb['placed']).Volume()
        if volume > 1e-5:
            clashes.append(dict(parts=[a, b], volume_mm3=volume))
    if clashes:
        raise ValueError('Interpenetrations: ' + json.dumps(clashes))
    residuals = []
    for mate in spec['mates']:
        a, b = records[mate['parent']], records[mate['child']]
        fa = a['transform'] @ a['ports'][mate['parent_port']]
        fb = b['transform'] @ b['ports'][mate['child_port']]
        residuals.append(float(np.max(np.abs(fa - fb))))
    if max(residuals) > 1e-8:
        raise ValueError('Unsatisfied mating frames')
    return records, dict(valid_solids=len(records), connected=True, interpenetrations=[],
        max_mate_residual=max(residuals), note='Static geometric checks only; not manufacturing certification.')


def export(spec, records, report, output):
    output.mkdir(parents=True, exist_ok=True)
    assembly = cq.Assembly(name='cad_trial')
    arrays, points = {}, []
    for name, record in records.items():
        assembly.add(record['placed'], name=name)
        vertices, faces = record['placed'].tessellate(.15, .15)
        vertices = np.array([v.toTuple() for v in vertices])
        arrays[name] = (vertices, faces)
        points.extend(vertices)
    points = np.array(points)
    center = (points.min(axis=0) + points.max(axis=0)) / 2
    scale = 6 / float(np.ptp(points, axis=0).max())
    script = ['cad.setMeta(' + json.dumps(dict(title=spec['title'], subtitle='ESSAI CAO MULTIPIÈCE — CONTRÔLES GÉOMÉTRIQUES',
        code='CAD-TRIAL', scale='APERÇU', unit='u')) + ');']
    manifest = []
    for name, record in records.items():
        vertices, faces = arrays[name]
        part_center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2
        # CAD Z-up -> Three.js Y-up, preserving a right-handed frame.
        to_view = lambda xyz: [round(float(xyz[0]), 5), round(float(xyz[2]), 5), round(float(-xyz[1]), 5)]
        xyz = [to_view(v) for v in (vertices - part_center) * scale]
        positions = [x for face in faces for i in face for x in xyz[i]]
        p = record['spec']
        opts = dict(name=p['name'], stage=p['stage'], material=p.get('material', 'brushed_steel'),
            pos=to_view((part_center - center) * scale), functionDesc=p['name'],
            entry=[0, 2 if p['factory'] != 'washer' else -2, 0])
        script.append('{const g=new THREE.BufferGeometry();g.setAttribute("position",new THREE.Float32BufferAttribute('
            + json.dumps(positions, separators=(',', ':')) + ',3));g.computeVertexNormals();cad.customGeometry(g,'
            + json.dumps(opts, ensure_ascii=True) + ');}')
        cq.exporters.export(record['placed'], str(output / (name + '.step')))
        manifest.append(dict(id=name, name=p['name'], stage=p['stage'],
            transform=record['transform'].tolist(), volume_mm3=record['placed'].Volume(), triangles=len(faces)))
    assembly.export(str(output / 'assembly.step'))
    (output / 'assembly.holoscript.js').write_text('\n'.join(script), encoding='utf-8')
    (output / 'validation.json').write_text(json.dumps(dict(report=report, parts=manifest), indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('spec', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    specification = json.loads(args.spec.read_text(encoding='utf-8'))
    records, report = build(specification)
    export(specification, records, report, args.output)
    print(json.dumps(report))
