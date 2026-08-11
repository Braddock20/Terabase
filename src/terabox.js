import {chromium} from "playwright";
import fs from "node:fs/promises";
import path from "node:path";
import {config} from "./config.js";
import {logger} from "./logger.js";

const loginUrl=/\/login(?:\/|$)|loginsetting/i;
const uploadSelectors=[
 'input[type="file"]',
 'button:has-text("Upload")',
 '[role="button"]:has-text("Upload")',
 'text=Upload'
];

const cleanName=n=>path.basename(String(n)).replace(/[^\w.\- ()[\]]+/g,"_").slice(0,180)||"upload.bin";

export class TeraBox{
 constructor(){this.browser=null;this.page=null;this.lock=Promise.resolve();this.state="created";this.lastError=null;}
 async init(){
  this.browser=await chromium.launchPersistentContext(config.profileDir,{
   headless:config.HEADLESS,
   acceptDownloads:true,
   downloadsPath:config.downloadDir,
   viewport:{width:1440,height:900},
   locale:"en-US",
   timezoneId:"Africa/Nairobi",
   args:["--disable-dev-shm-usage","--no-sandbox"]
  });
  this.page=this.browser.pages()[0]||await this.browser.newPage();
  this.page.setDefaultTimeout(config.REQUEST_TIMEOUT_MS);
  this.browser.on("page",p=>{p.setDefaultTimeout(config.REQUEST_TIMEOUT_MS);this.page=p;});
  this.state="browser_ready";
 }
 async close(){await this.browser?.close().catch(()=>{});this.browser=null;this.page=null;this.state="closed";}
 async home(){
  await this.page.goto(config.baseUrl,{waitUntil:"domcontentloaded",timeout:config.REQUEST_TIMEOUT_MS});
  await this.page.waitForLoadState("networkidle",{timeout:12000}).catch(()=>{});
  return {url:this.page.url(),title:await this.page.title()};
 }
 async loggedIn(){
  if(!this.page)return false;
  if(loginUrl.test(this.page.url()))return false;
  const password=await this.page.locator('input[type="password"]').first().isVisible().catch(()=>false);
  if(password)return false;
  return true;
 }
 async loginWithCredentials(){
  if(!config.TERABOX_EMAIL||!config.TERABOX_PASSWORD)
   throw new Error("TERABOX_EMAIL and TERABOX_PASSWORD are required for automatic Render login");
  await this.page.goto(config.baseUrl+"login",{waitUntil:"domcontentloaded",timeout:config.REQUEST_TIMEOUT_MS});
  const email=this.page.locator('input[type="email"],input[placeholder*="email" i]').first();
  const password=this.page.locator('input[type="password"],input[placeholder*="password" i]').first();
  await email.waitFor({state:"visible",timeout:15000});
  await email.fill(config.TERABOX_EMAIL);
  await password.fill(config.TERABOX_PASSWORD);
  const submit=this.page.locator('button:has-text("Login"),button:has-text("Log in"),button[type="submit"],text=Login').first();
  await submit.click();
  await this.page.waitForLoadState("networkidle",{timeout:20000}).catch(()=>{});
  await this.page.waitForTimeout(2500);
  if(!(await this.loggedIn())){
   throw Object.assign(new Error("TeraBox did not complete automatic login. It may require security verification/CAPTCHA or a different login method."),{code:"LOGIN_INCOMPLETE"});
  }
  await this.saveState();
  return true;
 }
 async saveState(){
  const state=await this.browser.storageState();
  await fs.writeFile(config.stateFile,JSON.stringify(state,null,2),{mode:0o600});
 }
 async ensureAuth(){
  await this.home();
  if(await this.loggedIn()){await this.saveState();return true;}
  if(config.AUTO_LOGIN){await this.loginWithCredentials();return true;}
  throw Object.assign(new Error("Not authenticated"),{code:"AUTH_REQUIRED",status:401});
 }
 async upload(localPath,folder="/"){
  const previous=this.lock;let release;this.lock=new Promise(r=>release=r);await previous;
  try{
   await this.ensureAuth();
   const name=cleanName(path.basename(localPath));
   const input=this.page.locator('input[type="file"]').first();
   if(await input.count()) await input.setInputFiles(localPath);
   else{
    const button=this.page.locator(uploadSelectors.slice(1).join(",")).first();
    if(!(await button.isVisible().catch(()=>false)))throw new Error("TeraBox upload control not found; UI changed");
    const chooser=this.page.waitForEvent("filechooser",{timeout:10000});
    await button.click();await (await chooser).setFiles(localPath);
   }
   await this.page.getByText(name,{exact:false}).first()
    .waitFor({state:"visible",timeout:Math.max(60000,config.REQUEST_TIMEOUT_MS)}).catch(()=>{});
   return {name,folder,uploaded:true,url:this.page.url()};
  }finally{release();}
 }
 async smoke(){
  const started=Date.now();
  const home=await this.home();
  const publicPage=!!home.title;
  let authenticated=false;
  let upload=null;
  if(await this.loggedIn())authenticated=true;
  else if(config.AUTO_LOGIN && config.TERABOX_EMAIL && config.TERABOX_PASSWORD){
   await this.loginWithCredentials();authenticated=true;
  }
  const smokeFile=path.join(config.tmpDir,`.terabox-smoke-${Date.now()}.txt`);
  await fs.writeFile(smokeFile,"TeraBox Playwright smoke test");
  try{
   if(authenticated)upload=await this.upload(smokeFile,"/");
   return {ok:publicPage&&authenticated&&!!upload,publicPage,authenticated,upload,durationMs:Date.now()-started};
  }finally{await fs.unlink(smokeFile).catch(()=>{});}
 }
}

