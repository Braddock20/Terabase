import express from "express";
import multer from "multer";
import fs from "node:fs/promises";
import crypto from "node:crypto";
import pinoHttp from "pino-http";
import {config} from "./config.js";
import {logger} from "./logger.js";
import {ensureDirs} from "./fs.js";
import {TeraBox} from "./terabox.js";
import {startupSmoke} from "./smoke.js";

const app=express();
app.disable("x-powered-by");
app.set("trust proxy",true);
app.use(express.json({limit:"1mb"}));
app.use(pinoHttp({logger}));
const upload=multer({dest:config.tmpDir,limits:{fileSize:config.uploadLimitBytes}});
const storage=new TeraBox();
let boot={ready:false,smoke:null,error:null};

function auth(req,res,next){
 if(!config.API_KEY)return next();
 const got=req.get("x-api-key")||req.get("authorization")?.replace(/^Bearer\s+/i,"");
 if(!got||got.length!==config.API_KEY.length||!crypto.timingSafeEqual(Buffer.from(got),Buffer.from(config.API_KEY)))
  return res.status(401).json({ok:false,error:"Unauthorized"});
 next();
}

app.get("/",(req,res)=>res.json({service:"terabox-playwright-render",version:"1.0.0",endpoints:["/health","/smoke","/session","/upload"]}));
app.get("/health",(req,res)=>res.status(boot.ready?200:503).json({
 ok:boot.ready,service:"terabox-playwright-render",smoke:boot.smoke,error:boot.error?.message
}));
app.get("/smoke",auth,(req,res)=>res.status(boot.smoke?.ok?200:503).json(boot.smoke||{ok:false,error:"Not run"}));
app.get("/session",auth,async(req,res)=>{
 if(!boot.ready)return res.status(503).json({ok:false,error:"Service not ready"});
 try{await storage.home();res.json({ok:true,authenticated:await storage.loggedIn(),url:storage.page.url()});}
 catch(e){res.status(502).json({ok:false,error:e.message});}
});
app.post("/upload",auth,upload.single("file"),async(req,res)=>{
 if(!boot.ready)return res.status(503).json({ok:false,error:"Service not ready",detail:boot.error?.message});
 if(!req.file)return res.status(400).json({ok:false,error:"multipart field 'file' is required"});
 try{
  const result=await storage.upload(req.file.path,req.body?.folder||"/");
  res.status(201).json({ok:true,...result});
 }catch(e){res.status(e.status||502).json({ok:false,error:e.message,code:e.code});}
 finally{await fs.unlink(req.file.path).catch(()=>{});}
});

const server=app.listen(config.PORT,"0.0.0.0",async()=>{
 try{
  await ensureDirs();
  await storage.init();
  boot.smoke=config.STARTUP_SMOKE?await startupSmoke(storage):{ok:true,skipped:true};
  boot.ready=true;
  if(!boot.smoke.ok)boot.error=new Error(boot.smoke.error||"Smoke test failed");
  logger.info({ready:boot.ready,smoke:boot.smoke},"service initialized");
 }catch(e){boot.error=e;logger.error({err:e},"startup failed");}
});
async function shutdown(sig){logger.info({sig},"shutdown");server.close();await storage.close();process.exit(0);}
process.on("SIGTERM",()=>shutdown("SIGTERM"));process.on("SIGINT",()=>shutdown("SIGINT"));
export {app,server};

