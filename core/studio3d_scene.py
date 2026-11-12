"""Validate a visual scene description before emitting calls to the supported CAD API."""
import json
import math

KINDS = ['ellipsoid', 'box', 'cylinder', 'cone', 'rotor_y', 'rotor_z']
STAGES = ['foundation', 'structure', 'mechanism', 'envelope', 'finishes']
MATERIALS = ['brushed_steel', 'titanium', 'iron_structure', 'copper', 'gold', 'stone',
             'concrete', 'wood', 'glass', 'carbon', 'ceramic', 'terracotta', 'slate', 'marine_paint']
VECTOR = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 3, 'maxItems': 3}
SCENE_SCHEMA = {'type': 'object', 'additionalProperties': False,
    'properties': {'title': {'type': 'string'}, 'parts': {'type': 'array', 'minItems': 6, 'maxItems': 20,
        'items': {'type': 'object', 'additionalProperties': False,
            'properties': {'name': {'type': 'string'}, 'kind': {'type': 'string', 'enum': KINDS},
                           'size': VECTOR, 'pos': VECTOR, 'rot': VECTOR,
                           'material': {'type': 'string', 'enum': MATERIALS},
                           'stage': {'type': 'string', 'enum': STAGES}},
            'required': ['name', 'kind', 'size', 'pos', 'rot', 'material', 'stage']}}},
    'required': ['title', 'parts']}


def visual_scene_code(raw):
    spec = json.loads(raw)
    parts = spec.get('parts') if isinstance(spec, dict) else None
    if not isinstance(parts, list) or not 6 <= len(parts) <= 20:
        raise ValueError('Scène visuelle incomplète : 6 à 20 volumes attendus.')

    def vector(value, positive=False):
        if not isinstance(value, list) or len(value) != 3:
            raise ValueError('Chaque volume doit avoir des dimensions, une position et une rotation explicites.')
        result = [float(v) for v in value]
        if any(not math.isfinite(v) or abs(v) > 15 or (positive and v <= 0) for v in result):
            raise ValueError('Dimensions ou coordonnées de scène invalides.')
        return result

    calls, positions = [], set()
    dump = lambda obj: json.dumps(obj, ensure_ascii=True, allow_nan=False)
    for part in parts:
        if not isinstance(part, dict) or part.get('kind') not in KINDS:
            raise ValueError('Type de volume inconnu.')
        size, pos, rot = vector(part.get('size'), True), vector(part.get('pos')), vector(part.get('rot'))
        positions.add(tuple(round(v, 2) for v in pos))
        material, stage = part.get('material'), part.get('stage')
        if material not in MATERIALS or stage not in STAGES:
            raise ValueError('Matériau ou étape inconnus.')
        opts = {'name': str(part.get('name', 'Volume'))[:100], 'pos': pos, 'rot': rot,
                'material': material, 'stage': stage, 'functionDesc': 'Volume illustratif guidé par références visuelles.',
                'historyNote': '', 'explode': [0, .3, .2]}
        kind = part['kind']
        if kind == 'box':
            method = 'box'; opts.update(w=size[0], h=size[1], d=size[2])
        elif kind == 'ellipsoid':
            method = 'sphere'; opts.update(r=1, scale=[v / 2 for v in size])
        elif kind in ('cylinder', 'cone'):
            method = kind; opts.update(r=1, h=1, scale=[size[0]/2, size[1], size[2]/2])
        else:
            method = 'propeller'
            axis = kind[-1]
            radius = max(size[0], size[2] if axis == 'y' else size[1]) / 2
            opts.update(axis=axis, blades=2, rOuter=radius, hubR=radius*.07,
                        bladeWidth=radius*.08, pitchAngle=.08)
        calls.append('cad.' + method + '(' + dump(opts) + ');')
    if len(positions) < 3:
        raise ValueError('Scène rejetée : les volumes sont superposés aux mêmes positions.')
    meta = {'title': str(spec.get('title', 'Étude visuelle'))[:120],
            'subtitle': 'RECONSTITUTION VISUELLE APPROXIMATIVE — NON COTÉE', 'unit': 'u'}
    return 'cad.setMeta(' + dump(meta) + ');\n' + '\n'.join(calls)
