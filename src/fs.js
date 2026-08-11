import fs from "node:fs/promises";
import {config} from "./config.js";
export async function ensureDirs(){
 await Promise.all([
  fs.mkdir(config.profileDir,{recursive:true}),
  fs.mkdir(config.tmpDir,{recursive:true}),
  fs.mkdir(config.downloadDir,{recursive:true})
 ]);
}

