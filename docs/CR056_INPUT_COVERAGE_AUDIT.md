# CR056 input coverage audit

Authorized purpose: the user requested implementation of the reviewed multifactor strategy and regeneration of rankings from current inputs. This isolated branch diagnoses existing input coverage while the execution thread implements the strategy.

Input: the existing main-branch EOD history cache and the published authoritative date. Output: counts, last-date distribution and six instruments' coverage metadata only. No market prices, credentials or raw cache are uploaded.

Owner: operations/review coordination. The workflow uses an existing dispatchable filename solely on this isolated branch; it is not intended for merging into main. It restores but never saves caches, has contents-read permission, no secrets, no provider calls, no commit/push, no deployment, and no notifications. It does not change strategy semantics or claim input counts equal eligible stocks.

Check: review workflow before branch push/dispatch; verify restored key and output scope. Insufficient cache remains a visible diagnostic result. Rollback: leave main unchanged and stop using this branch. One bounded operational work package.

## Reviewed ranking run extension

After the successful read-only inventory, this same isolated workflow runs the reviewed bounded recent-input repair (existing EODHD credential in that step only), then computes candidate rankings offline. The original cache is unchanged; repaired raw inputs stay under work/cr056-private and are not uploaded. Only derived rankings, summaries and repair metadata are exported. The earlier no-provider-call scope describes the initial inventory run, not this explicitly authorized ranking extension. No main merge, deployment or notification occurs.
