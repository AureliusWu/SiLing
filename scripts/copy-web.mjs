import {cpSync, mkdirSync, rmSync} from "node:fs";
const target = "services/voice/src/siling_voice/web";
rmSync(target, {recursive:true, force:true});
mkdirSync(target, {recursive:true});
cpSync("apps/desktop/dist", target, {recursive:true});
console.log("Copied frontend into voice package");
