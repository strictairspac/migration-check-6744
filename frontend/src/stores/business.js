import {batches,mappings,runs,labs,handovers} from '../api/business.js';
export const store={batches:[],mappings:[],runs:[],labs:[],handovers:[],user:null};
export async function refresh(){
 const [b,m,r]=await Promise.all([batches.list(),mappings.list(),runs.list()]);
 store.batches=b;store.mappings=m;store.runs=r;
 if(store.user?.role==='admin'){[store.labs,store.handovers]=await Promise.all([labs.list(),handovers.list()]);}
}
