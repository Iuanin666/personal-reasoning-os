import fs from 'node:fs';
import path from 'node:path';

const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,x)=>i%2?a:[...a,[v.replace(/^--/,''),x[i+1]]],[]));
if(!args.root||!args.output) throw new Error('Usage: node node_dependency_licenses.mjs --root <node_modules> --output <file>');
const manifests=[];
for(const entry of fs.readdirSync(args.root,{withFileTypes:true})){
 if(!entry.isDirectory()||entry.name==='.bin') continue;
 const base=path.join(args.root,entry.name);
 if(entry.name.startsWith('@')) for(const child of fs.readdirSync(base)){const p=path.join(base,child,'package.json');if(fs.existsSync(p))manifests.push(p);}
 else {const p=path.join(base,'package.json');if(fs.existsSync(p))manifests.push(p);}
}
const packages=manifests.map(p=>JSON.parse(fs.readFileSync(p,'utf8'))).sort((a,b)=>a.name.localeCompare(b.name));
const lines=['# Installed Node dependency license metadata','','Generated from the clean-install Defuddle dependency tree. Upstream license texts remain authoritative.','','| Package | Version | Declared license |','|---|---:|---|'];
for(const p of packages) lines.push(`| ${p.name} | ${p.version} | ${(p.license||'NOT DECLARED IN PACKAGE METADATA').replaceAll('|','\\|')} |`);
fs.writeFileSync(args.output,lines.join('\n')+'\n');console.log(JSON.stringify({packages:packages.length,output:path.basename(args.output)}));
