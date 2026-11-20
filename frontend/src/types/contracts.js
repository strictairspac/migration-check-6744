/** @typedef {{id:number,name:string,source_file:string,rows:object[],lab_id:number|null,lab_code:string|null,lab_name:string|null}} Batch */
/** @typedef {{id:number,name:string,batch_id:number,rules:object[],chunk_size:number,lab_id:number|null,batch_name:string|null}} Mapping */
/** @typedef {{id:number,name:string,status:'queued'|'running'|'completed'|'failed'|'cancelled',result:object|null}} Run */
/** @typedef {{id:number,code:string,name:string}} Lab */
/** @typedef {{request_id:string,batch_id:number,batch_name:string,moved:boolean,from_lab:Lab|null,to_lab:Lab,replayed?:boolean}} HandoverReceipt */
export {};
