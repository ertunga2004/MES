// Observation must look and behave read-only. The server separately enforces the workspace.
export function makeReadOnly(root){
 if(!root)return;
 root.dataset.readOnly='true';
 root.querySelectorAll('input,textarea,select,button').forEach(control=>{
  if(control.id==='packing-order'||control.dataset.action==='order-detail')return;
  control.disabled=true;
  if(control.matches('button[data-action],form button'))control.hidden=true;
 });
}
