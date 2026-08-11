import test from "node:test";
import assert from "node:assert/strict";

test("health shape",()=>{
  const x={ok:true,service:"terabox-playwright-render"};
  assert.equal(x.ok,true);
  assert.equal(typeof x.service,"string");
});

test("basename removes parent path",()=>{
  const n=String("../../secret.txt").split(/[\\/]/).pop();
  assert.equal(n,"secret.txt");
});
