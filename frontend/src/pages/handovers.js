import {store} from '../stores/business.js';import {esc,json} from '../utils/html.js';import {table} from '../components/common/table.js';
const PENDING='handover-request';
export function requestIdFor(batchId,toLabId){
 // Keep the same request id until a receipt is received, so a lost response can
 // be retried safely without moving the batch twice. A different batch/lab pair
 // starts a fresh request.
 let saved=null;try{saved=JSON.parse(sessionStorage.getItem(PENDING)||'null');}catch(e){}
 if(saved&&saved.batchId===batchId&&saved.toLabId===toLabId)return saved.requestId;
 const requestId=(crypto.randomUUID?.()||('hb-'+Date.now()+'-'+Math.random().toString(16).slice(2)));
 sessionStorage.setItem(PENDING,JSON.stringify({batchId,toLabId,requestId}));
 return requestId;
}
export function handoverPage(){
 const options=store.batches.map(b=>`<option value="${b.id}">${esc(b.name)} · 当前：${esc(b.lab_name||'未领取（仅管理员）')}</option>`).join('');
 return `<div class="split"><section><h2>把旧批次交到实验室</h2><p>交接只改变归属；批次下的映射、运行与目标行整批随批次归入目标实验室。派发后原实验室已登录的会话立即失去查看与下载权限。</p><form id="handover-form"><label>批次<select name="batch_id" required>${options||'<option value="">没有可交接的批次</option>'}</select></label><label>目标实验室<select name="to_lab_id" required>${store.labs.map(l=>`<option value="${l.id}">${esc(l.name)} / ${esc(l.code)}</option>`).join('')}</select></label><small>重复点击或网络重试使用同一张回执；即使批次后来又转室，旧回执也不会再次转移。</small><button type="submit" ${store.batches.length&&store.labs.length?'':'disabled'}>交接批次 →</button></form><ol class="steps"><li>管理员核对批次与目标实验室</li><li>锁定该批次，写入归属与回执</li><li>整批历史按新归属落库，其余批次继续写入</li><li>失败保持原归属，可用同一回执安全重试</li></ol><aside class="note">旧批次在领取前仅管理员可见。交接回执与审计记录一并保存，便于双方复核。</aside></section><section><h2>交接回执 <em>${store.handovers.length}</em></h2>${table(['批次 / 时间','归属变化','结果'],store.handovers.map(h=>[`<b>${esc(h.batch_name||('#'+h.batch_id))}</b><small>${esc(h.occurred_at||h.created_at||'')}</small>`,`${esc(h.from_lab?.name||'未领取（管理员）')} → ${esc(h.to_lab?.name||'—')}`,`${h.moved?'已转移':'未移动'}${h.replayed?' · 重放回执':''}<small>${esc(h.actor||'')}<br>${esc(h.request_id||'')}</small>`]))}<details><summary>完整回执 JSON</summary><pre>${json(store.handovers.slice(0,10))}</pre></details></section></div>`;
}
