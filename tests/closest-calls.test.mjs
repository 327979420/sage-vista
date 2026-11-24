import assert from 'node:assert/strict';
import test from 'node:test';
import {loadTs} from './helpers/load-ts.mjs';
const {closeness} = loadTs('app/signals/board.tsx');

const row = over => ({id:'x', symbol:'X', week:'2026-10-23', pool:'main', status:'skipped', limit:10, stop:9, target:13, close:10, priceAsOf:null,
 breadth:.6, spyOk:true, shapePassed:22, shapeTotal:22, rr:2, rrOk:true, veto:false, gateOk:true, ruleOk:true, filled:false, ...over});

test('a closest call misses every failed check by under 10% and is ranked by total shortfall', () => {
 assert.equal(closeness(row({breadth:.488, gateOk:false})).toFixed(3), '0.024');
 assert.equal(closeness(row({rr:1.47, rrOk:false, ruleOk:false, breadth:.475, gateOk:false})).toFixed(2), '0.07');
 // Too far, vetoed, broken shape, SPY failing, already traded, or nothing failed: not a closest call.
 for (const over of [{breadth:.381, gateOk:false}, {rr:1.3, rrOk:false, ruleOk:false}, {veto:true, ruleOk:false, breadth:.49, gateOk:false},
  {shapePassed:21, ruleOk:false, breadth:.49, gateOk:false}, {spyOk:false, gateOk:false}, {status:'open'}, {}])
  assert.equal(closeness(row(over)), null, JSON.stringify(over));
});
