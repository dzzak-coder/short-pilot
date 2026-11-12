"""Ask the installed local model for assembly data; never accept generated Python."""
import json
import sys
from pathlib import Path

import requests

CATALOG = '''This trial library ONLY supports a four-component mechanical hinge, not arbitrary products.
hinge_leaf: parameters side=left or right, height=50, hole_radius=3. One real leaf with interleaved
knuckles and mounting holes. Exposes an axis mating frame. Left and right leaves have complementary
knuckles. Their axis frames are coincident in the assembled configuration (the right wing is flipped).
hinge_pin: parameters height=50, hole_radius=3, radius=2.8. Exposes axis frame.
washer: parameters hole_radius=3, thickness=1. Exposes seat frame; sits between the pin head and leaves.
Use one left leaf (foundation), one right leaf (structure), one pin (mechanism), one washer (finishes).
Choose the left leaf as root. Connect each other part to its axis frame using its corresponding frame.
Preserve distinct parts. Dimensions must be compatible. Do not output coordinates or code.
If the user asks for an object unsupported by this library, return {"unsupported":true,"reason":"..."}.
For supported requests return ONLY JSON with title, root, parts and mates.
parts entries: id, name, factory, parameters, stage.
mates entries: parent, parent_port, child, child_port.
Port names are EXACTLY "axis" for leaves and pin and "seat" for washer.
Connect left leaf axis to right leaf axis, left leaf axis to pin axis,
and left leaf axis to washer seat. Use the actual part ids in each mate.
Write human-readable part names and title in French.
'''

SCHEMA = {'anyOf': [
    {'type': 'object', 'properties': {'unsupported': {'const': True}, 'reason': {'type': 'string'}},
     'required': ['unsupported', 'reason'], 'additionalProperties': False},
    {'type': 'object', 'additionalProperties': False,
     'properties': {'title': {'type': 'string'}, 'root': {'type': 'string'},
        'parts': {'type': 'array', 'minItems': 2, 'maxItems': 10, 'items': {
            'type': 'object', 'additionalProperties': False,
            'properties': {'id': {'type': 'string'}, 'name': {'type': 'string'},
                'factory': {'enum': ['hinge_leaf', 'hinge_pin', 'washer']},
                'stage': {'enum': ['foundation', 'structure', 'mechanism', 'envelope', 'finishes']},
                'parameters': {'type': 'object', 'additionalProperties': False, 'properties': {
                    'side': {'enum': ['left', 'right']},
                    **{key: {'type': 'number'} for key in ('height', 'hole_radius', 'radius', 'thickness')}}}},
            'required': ['id', 'name', 'factory', 'stage', 'parameters']}},
        'mates': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
            'properties': {'parent': {'type': 'string'}, 'child': {'type': 'string'},
                'parent_port': {'enum': ['axis', 'seat']}, 'child_port': {'enum': ['axis', 'seat']}},
            'required': ['parent', 'parent_port', 'child', 'child_port']}}},
     'required': ['title', 'root', 'parts', 'mates']}]}

if __name__ == '__main__':
    subject, target = sys.argv[1], Path(sys.argv[2])
    with requests.Session() as session:
        session.trust_env = False
        response = session.post('http://127.0.0.1:11434/api/chat', json={
            'model': 'qwen2.5-coder:14b', 'stream': False, 'format': SCHEMA, 'keep_alive': 0,
            'messages': [{'role': 'system', 'content': CATALOG}, {'role': 'user', 'content': subject}],
            'options': {'temperature': 0, 'num_predict': 1800, 'num_ctx': 4096}}, timeout=180)
        response.raise_for_status()
        result = response.json()
    if result.get('done_reason') == 'length':
        raise RuntimeError('Assembly plan was truncated; rejected.')
    data = json.loads(result['message']['content'])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Local plan saved; requires CAD validation before use.')
