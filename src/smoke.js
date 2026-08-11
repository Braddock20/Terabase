import {logger} from "./logger.js";
export async function startupSmoke(storage){
 try{
  const result=await storage.smoke();
  logger.info({smoke:result},"startup smoke test complete");
  return result;
 }catch(error){
  logger.error({err:error},"startup smoke test failed");
  return {ok:false,error:error.message,code:error.code};
 }
}

