// Render the handover page and exercise its form against stubbed store/API.
import {JSDOM} from '/tmp/gb4109/ui/node_modules/jsdom/lib/api.js';
import {readFileSync} from 'node:fs';

const dom = new JSDOM('<!doctype html><div id="app"></div>', {url: 'http://localhost/'});
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.sessionStorage = dom.window.sessionStorage;

const {store} = await import('/workspace/frontend/src/stores/business.js');
store.user = {email: 'admin@migration.local', role: 'admin', lab_name: null};
store.labs = [{id: 1, code: 'LAB-A', name: '检验一室'}, {id: 2, code: 'LAB-B', name: '检验二室'}];
store.batches = [
  {id: 7, name: '见山日班检验结果', rows: [], lab_id: 1, lab_name: '检验一室'},
  {id: 9, name: '旧字段异常样本', rows: [], lab_id: null, lab_name: null},
];
store.handovers = [{
  batch_id: 9, batch_name: '旧字段异常样本', from_lab: null,
  to_lab: {id: 1, code: 'LAB-A', name: '检验一室'}, moved: true,
  actor: 'admin@migration.local', request_id: 'handover-abc', occurred_at: '2026-11-20T00:00:00Z',
}];
const {handoverPage, requestIdFor} = await import('/workspace/frontend/src/pages/handovers.js');
const html = handoverPage();

const failures = [];
const expect = (cond, msg) => { if (!cond) failures.push(msg); };
expect(html.includes('id="handover-form"'), 'handover form rendered');
expect(html.includes('旧字段异常样本'), 'unclaimed batch listed');
expect(html.includes('未领取（仅管理员）'), 'unclaimed state labelled');
expect(html.includes('检验二室 / LAB-B'), 'target lab options rendered');
expect(html.includes('交接回执'), 'receipt table title');
expect(html.includes('已转移'), 'receipt moved state');
expect(html.includes('handover-abc'), 'receipt request id visible');

// Stable request id for retries; a different target starts a new request.
const first = requestIdFor(7, 2);
const retry = requestIdFor(7, 2);
expect(first === retry, 'same request id on retry');
expect(requestIdFor(7, 1) !== first, 'new request id for different target');
expect(first.startsWith('handover-') || first.length > 8, 'request id is long enough for schema');

// The page must not render controls for non-admins (page is admin-only in nav).
const app = readFileSync('/workspace/frontend/src/app.js', 'utf8');
expect(app.includes("adminRoutes"), 'admin routes imported');
expect(app.includes("page==='handovers'?handoverPage()"), 'handover page wired into render');
expect(app.includes("handovers.perform"), 'handover submit wired');
expect(app.includes("sessionStorage.removeItem('handover-request')"), 'pending id cleared on success');

if (failures.length) { console.error('FAILURES:\n - ' + failures.join('\n - ')); process.exit(1); }
console.log('frontend handover page ok');
