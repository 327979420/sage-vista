import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import ts from 'typescript';
const require=createRequire(import.meta.url),cache=new Map();
export function loadTs(file){
 file=path.resolve(file instanceof URL?fileURLToPath(file):file);
 if(cache.has(file))return cache.get(file).exports;
 if(file.endsWith('.json'))return JSON.parse(fs.readFileSync(file,'utf8'));
 const loadedModule={exports:{}};cache.set(file,loadedModule);
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 new Function('require','exports','module',code)(id=>{
  if(!id.startsWith('.'))return require(id);
  const base=path.resolve(path.dirname(file),id);
  const target=['','.tsx','.ts','.mjs'].map(ext=>base+ext).find(f=>fs.existsSync(f)&&fs.statSync(f).isFile());
  if(!target)throw Error(`Cannot resolve ${id} from ${file}`);
  return loadTs(target);
 },loadedModule.exports,loadedModule);
 return loadedModule.exports;
}
