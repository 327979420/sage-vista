"""Strict internal execution wire framing; original business validators stay sole."""
from services.contracts.validation import (
    ContractError, PREPARATION_INPUT_MAX_BYTES, _m12_decode_base64,
    _m12_exact, _m12_json, _m12_preparation_identity,
)


def decode_execution_input(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= PREPARATION_INPUT_MAX_BYTES:
        raise ContractError('execution computation input size invalid')
    value = _m12_json(raw)
    _m12_exact(value, {'protocol', 'identity', 'snapshot', 'objects', 'request_bytes'}, 'execution computation input')
    if value['protocol'] != 'm12-execution-validation/1':
        raise ContractError('execution computation protocol invalid')
    if not isinstance(value['identity'], dict):
        raise ContractError('execution identity invalid')
    _m12_preparation_identity(value['identity'], {'code_commit': value['identity'].get('code_commit')})
    if not isinstance(value['snapshot'], dict) or not isinstance(value['objects'], dict):
        raise ContractError('execution computation readback invalid')
    value['objects'] = {key: _m12_decode_base64(item) for key, item in value['objects'].items()}
    value['request_bytes'] = _m12_decode_base64(value['request_bytes'])
    return value
