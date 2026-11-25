// Only user-edited fields are drafts; remote changes to untouched fields stay visible.
export class FormDrafts {
 constructor(){this.forms=new Map();}
 edit(key,field){
  if(!field.name||field.type==='password'||field.readOnly)return;
  if(!this.forms.has(key))this.forms.set(key,new Map());
  this.forms.get(key).set(field.name,field.type==='checkbox'?field.checked:field.value);
 }
 has(key,name){return this.forms.get(key)?.has(name)||false;}
 restore(key,fields){for(const field of fields){if(!this.has(key,field.name))continue;const value=this.forms.get(key).get(field.name);if(field.type==='checkbox')field.checked=value;else field.value=value;}}
 clear(key){if(key===undefined)this.forms.clear();else this.forms.delete(key);}
 delete(key){this.clear(key);}
}
