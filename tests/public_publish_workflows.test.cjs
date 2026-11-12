const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const load=name=>JSON.parse(fs.readFileSync(path.join(__dirname,'../tools/n8n',name),'utf8'));
const tiktok=load('shortpilot_tiktok_direct.json');
const youtube=load('shortpilot_youtube_public.json');
const main=load('shortpilot_direct_public.json');
async function code(flow,name,json,{lookup={},store={},runIndex=0,binary={}}={}){
  const item={json,binary};
  const context={...json,$json:json,$input:{first:()=>item,all:()=>json.items||[item]},
    $:name=>({first:()=>lookup[name]}),$getWorkflowStaticData:()=>store,$runIndex:runIndex};
  vm.createContext(context);
  const source=flow.nodes.find(n=>n.name===name).parameters.jsCode;
  return JSON.parse(JSON.stringify(await vm.runInContext(`(async()=>{${source}\n})()`,context)));
}
test('workflow graphs reference real nodes and direct posting never calls inbox upload',()=>{
  for(const flow of [tiktok,youtube,main]){
    const names=new Set(flow.nodes.map(n=>n.name));
    for(const [from,outputs] of Object.entries(flow.connections)){
      assert(names.has(from));
      for(const branch of outputs.main)for(const edge of branch)assert(names.has(edge.node));
    }
  }
  assert(!JSON.stringify(tiktok).includes('/inbox/'));
  assert(JSON.stringify(tiktok).includes('/v2/post/publish/video/init/'));
});
test('missing video.publish is blocked before reading or sending the video',async()=>{
  const out=await code(tiktok,'Preparer publication TikTok',{body:{video_id:'video'},tiktokScope:'video.upload'});
  assert.equal(out[0].json.ready,false);
  assert.equal(out[0].json.status,'blocked');
  assert.match(out[0].json.message,/video.publish/);
});
test('creator privacy and duration restrictions stop public init',async()=>{
  const lookup={'Preparer publication TikTok':{json:{body:{duration:180}},binary:{}}};
  for(const data of [{privacy_level_options:['SELF_ONLY']},
                      {privacy_level_options:['PUBLIC_TO_EVERYONE'],max_video_post_duration_sec:60}]){
    const out=await code(tiktok,'Verifier publication publique',{data,error:{code:'ok'}},{lookup});
    assert.equal(out[0].json.ready,false);
    assert.equal(out[0].json.status,'blocked');
  }
});
test('only a publicly available post id confirms a public TikTok',async()=>{
  const lookup={'Conserver identifiant TikTok':{json:{postKey:'video',publishId:'publish-1',tiktokAccessToken:'secret'}}};
  for(const [data,expected] of [
    [{status:'PUBLISH_COMPLETE',publicaly_available_post_id:['123']},'published'],
    [{status:'PUBLISH_COMPLETE',publicaly_available_post_id:[]},'pending'],
    [{status:'PROCESSING_UPLOAD'},'pending'],
    [{status:'FAILED',fail_reason:'duration_check_failed'},'failed'],
    [{status:'SEND_TO_USER_INBOX'},'failed'],
  ]){
    const store={};
    const out=await code(tiktok,'Interpreter statut TikTok',{data,error:{code:'ok'}},{lookup,store,runIndex:23});
    assert.equal(out[0].json.status,expected);
    assert.equal(out[0].json.public,expected==='published');
    assert(!JSON.stringify(store).includes('secret'));
    const safe=await code(tiktok,'Resultat TikTok',out[0].json);
    assert(!JSON.stringify(safe).includes('secret'));
  }
});
test('pending or completed receipts prevent a second upload',async()=>{
  for(const status of ['pending','published']){
    const out=await code(tiktok,'Preparer publication TikTok',{body:{video_id:'video'}},
      {store:{posts:{video:{platform:'tiktok',status,public:status==='published'}}}});
    assert.equal(out[0].json.ready,false);
    assert.equal(out[0].json.status,status);
  }
});
test('parent reports both platform results and never upgrades partial success',async()=>{
  const items=[{json:{platform:'youtube',status:'published',public:true}},
               {json:{platform:'tiktok',status:'blocked',public:false}}];
  const out=await code(main,'Confirmer les deux publications',{items});
  assert.equal(out[0].json.ok,false);
  assert.equal(out[0].json.youtube.status,'published');
  assert.equal(out[0].json.tiktok.status,'blocked');
});
