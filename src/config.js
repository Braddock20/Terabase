import path from "node:path";
import {z} from "zod";
const b=z.enum(["0","1"]).default("1").transform(v=>v==="1");
const env=z.object({
 PORT:z.coerce.number().int().min(1).max(65535).default(10000),
 TERABOX_BASE_URL:z.string().url().default("https://www.terabox.com/"),
 TERABOX_EMAIL:z.string().email().optional(),
 TERABOX_PASSWORD:z.string().min(1).optional(),
 TERABOX_PROFILE_DIR:z.string().default("/var/data/terabox-profile"),
 TERABOX_STATE_FILE:z.string().default("/var/data/terabox-state.json"),
 TERABOX_TMP_DIR:z.string().default("/var/data/tmp"),
 TERABOX_DOWNLOAD_DIR:z.string().default("/var/data/downloads"),
 API_KEY:z.string().min(16).optional(),
 MAX_UPLOAD_MB:z.coerce.number().int().min(1).max(10240).default(512),
 REQUEST_TIMEOUT_MS:z.coerce.number().int().min(5000).max(120000).default(45000),
 STARTUP_SMOKE:z.enum(["0","1"]).default("1").transform(v=>v==="1"),
 AUTO_LOGIN:z.enum(["0","1"]).default("1").transform(v=>v==="1"),
 HEADLESS:b,
 LOG_LEVEL:z.string().default("info")
}).parse(process.env);
export const config={
 ...env,
 baseUrl:env.TERABOX_BASE_URL.replace(/\/+$/,"")+"/",
 profileDir:path.resolve(env.TERABOX_PROFILE_DIR),
 stateFile:path.resolve(env.TERABOX_STATE_FILE),
 tmpDir:path.resolve(env.TERABOX_TMP_DIR),
 downloadDir:path.resolve(env.TERABOX_DOWNLOAD_DIR),
 uploadLimitBytes:env.MAX_UPLOAD_MB*1024*1024
};

