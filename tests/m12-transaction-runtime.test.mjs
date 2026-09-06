import test from 'node:test';
import assert from 'node:assert/strict';
import { Miniflare } from 'miniflare';

test('local SQLite DO rolls back successful nested transaction when enclosing transaction fails', async () => {
  const mf = new Miniflare({ modules: true, compatibilityDate: '2026-05-22',
    durableObjects: { TEST: { className: 'Test', useSQLite: true } }, script: `
import { DurableObject } from 'cloudflare:workers';
export class Test extends DurableObject {
  fetch() {
    const s = this.ctx.storage;
    s.sql.exec('CREATE TABLE IF NOT EXISTS t (v INTEGER)');
    s.transactionSync(() => {
      s.sql.exec('INSERT INTO t VALUES (1)');
      s.transactionSync(() => s.sql.exec('INSERT INTO t VALUES (2)'));
    });
    try {
      s.transactionSync(() => {
        s.transactionSync(() => s.sql.exec('INSERT INTO t VALUES (3)'));
        throw Error('rollback');
      });
    } catch {}
    return Response.json(s.sql.exec('SELECT v FROM t ORDER BY v').toArray());
  }
}
export default { fetch(r, e) { return e.TEST.get(e.TEST.idFromName('test')).fetch(r); } };
` });
  try {
    const response = await mf.dispatchFetch('http://localhost/');
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), [{ v: 1 }, { v: 2 }]);
  } finally { await mf.dispose(); }
});
