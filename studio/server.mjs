import http from 'node:http';
import {mkdir,realpath,readFile,rename,stat,writeFile,chmod,readdir} from 'node:fs/promises';
import {buildCatalog} from './catalog.mjs';
import {createReadStream,createWriteStream,existsSync,readFileSync} from 'node:fs';
import {pipeline} from 'node:stream/promises';
import {spawn} from 'node:child_process';
import {randomUUID,createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
async function loadDotenv(){try{for(const raw of (await readFile(path.join(root,'.env'),'utf8')).split(/\r?\n/)){const line=raw.trim();if(!line||line.startsWith('#')||!line.includes('='))continue;const [key,...rest]=line.split('=');if(key&&!process.env[key])process.env[key]=rest.join('=').trim().replace(/^['"]|['"]$/g,'');}}catch{}}
await loadDotenv();

function readJsonSync(file,fallback={}){try{return JSON.parse(readFileSync(file,'utf8'))}catch{return fallback}}
function workspaceConfig(){const base=readJsonSync(path.join(root,'config','workspace.json')),local=readJsonSync(path.join(root,'config','workspace.local.json')),merge=(a,b)=>{const o={...a};for(const [k,v] of Object.entries(b)){o[k]=v&&typeof v==='object'&&!Array.isArray(v)&&a[k]&&typeof a[k]==='object'?merge(a[k],v):v}return o};return merge(base,local)}
function subtitlePreset(projectId){const brand=readJsonSync(path.join(root,'content',projectId,'content.json')).brand||workspaceConfig().defaultBrand;return readJsonSync(path.join(root,'config','brands',String(brand),'brand.json')).subtitlePreset||'creator'}
const ENV_FILE=path.join(root,'.env');
const KNOWN_ENV=[
 {key:'HIGGSFIELD_MODE',label:'Higgsfield transport',secret:false,group:'Higgsfield',type:'mode'},
 {key:'HF_API_KEY_ID',label:'Higgsfield API key ID',secret:true,group:'Higgsfield'},
 {key:'HF_API_KEY_SECRET',label:'Higgsfield API key secret',secret:true,group:'Higgsfield'},
 {key:'HF_MODEL',label:'Default video model',secret:false,group:'Higgsfield',hint:'bytedance/seedance-2.0/text-to-video'},
 {key:'HF_API_BASE_URL',label:'API base URL',secret:false,group:'Higgsfield',hint:'https://api.higgsfield.ai'},
 {key:'HF_POLL_INTERVAL_SECONDS',label:'Poll interval (s)',secret:false,group:'Higgsfield',hint:'10'},
 {key:'HF_MAX_WAIT_SECONDS',label:'Max wait (s)',secret:false,group:'Higgsfield',hint:'1800'},
 {key:'HEYGEN_MODE',label:'HeyGen transport',secret:false,group:'HeyGen',type:'mode'},
 {key:'HEYGEN_API_KEY',label:'HeyGen API key',secret:true,group:'HeyGen'}];
const isSecretName=k=>/KEY|SECRET|TOKEN|PASSWORD|PASS/i.test(k);
const unquote=v=>v.trim().replace(/^(['"])(.*)\1$/,'$2');
async function readEnvLines(){try{return (await readFile(ENV_FILE,'utf8')).split(/\r?\n/)}catch{return []}}
function envParse(lines){const out=new Map();for(const raw of lines){const line=raw.trim();if(!line||line.startsWith('#')||!line.includes('='))continue;const i=line.indexOf('=');out.set(line.slice(0,i).trim(),unquote(line.slice(i+1)))}return out}
async function settingsView(){const map=envParse(await readEnvLines()),known=new Set(KNOWN_ENV.map(x=>x.key));
 const entry=(k,meta)=>{const secret=meta?meta.secret:isSecretName(k),value=map.get(k);return {key:k,label:meta?.label||k,group:meta?.group||'Custom',secret,known:!!meta,hint:meta?.hint||'',type:meta?.type||'text',set:value!==undefined&&value!=='',value:secret?null:(meta?.type==='mode'?(value==='mcp'?'mcp':'api'):(value??''))}};
 return {file:'.env',exists:map.size>0||existsSync(ENV_FILE),entries:[...KNOWN_ENV.map(m=>entry(m.key,m)),...[...map.keys()].filter(k=>!known.has(k)).map(k=>entry(k,null))]}}
async function writeEnv(key,value){
 if(!/^[A-Z][A-Z0-9_]{0,63}$/.test(key))throw Error('Key must be UPPER_SNAKE_CASE.');
 if(/_MODE$/.test(key)&&value!==null&&!['api','mcp'].includes(value))throw Error('Mode must be api or mcp.');
 if(value!==null&&(typeof value!=='string'||/[\r\n]/.test(value)||value.length>4000))throw Error('Invalid value.');
 const lines=await readEnvLines(),re=new RegExp('^\\s*'+key+'\\s*='),idx=lines.findIndex(l=>re.test(l));
 if(value===null){if(idx>=0)lines.splice(idx,1);delete process.env[key]}
 else{const text=`${key}=${/[\s#'"]/.test(value)?JSON.stringify(value):value}`;if(idx>=0)lines[idx]=text;else{while(lines.length&&lines[lines.length-1]==='')lines.pop();lines.push(text)}process.env[key]=value}
 while(lines.length&&lines[lines.length-1]==='')lines.pop();
 const tmp=ENV_FILE+'.tmp';await writeFile(tmp,lines.join('\n')+'\n',{mode:0o600});await rename(tmp,ENV_FILE);await chmod(ENV_FILE,0o600);
}

async function mcpStatus(){
 return {higgsfield:'ChatGPT agent handles connection',heygen:'ChatGPT agent handles connection',checkedAt:new Date().toISOString()};
}
function providerMode(name){return freshEnv()[name==='heygen'?'HEYGEN_MODE':'HIGGSFIELD_MODE']==='mcp'?'mcp':'api'}
function requireApiMode(name){if(providerMode(name)==='mcp')throw Error(`${name==='heygen'?'HeyGen':'Higgsfield'} is set to MCP. Run this from the ChatGPT agent with its MCP tools, or switch it to API in Settings.`)}
const firstSeen=new Map();
function jobsList(){const now=Date.now();return [...jobs.values()].map(j=>{if(!firstSeen.has(j.id))firstSeen.set(j.id,now);return {id:j.id,kind:j.kind,state:j.state,contentId:j.contentId||j.projectId||null,releaseId:j.releaseId||null,error:j.error,log:(j.log||'').slice(-600),items:j.items?j.items.map(({id,state,detail})=>({id,state,detail})):undefined,startedAt:firstSeen.get(j.id)}}).sort((a,b)=>b.startedAt-a.startedAt)}
let allowed=new Map();
async function catalog(){const next=await buildCatalog(root);allowed=next.allowed;return next.results;}
const jobs=new Map();
const safeId=value=>typeof value==='string'&&/^[\w-]+$/.test(value);
const contentRoot=id=>path.join(root,'content',id);
function freshEnv(){const out={...process.env};try{for(const raw of readFileSync(path.join(root,'.env'),'utf8').split(/\r?\n/)){const line=raw.trim();if(!line||line.startsWith('#')||!line.includes('='))continue;const i=line.indexOf('=');const k=line.slice(0,i).trim();if(k)out[k]=line.slice(i+1).trim().replace(/^(['"])(.*)\1$/,'$2')}}catch{}return out}
function command(bin,args,job){return new Promise((resolve,reject)=>{const child=spawn(bin,args,{cwd:root,env:freshEnv()});let text='';const add=chunk=>{text+=(chunk||'').toString();if(text.length>8000)text=text.slice(-8000);job.log=text;};child.stdout.on('data',add);child.stderr.on('data',add);child.on('error',reject);child.on('close',code=>code===0?resolve(text):reject(Error(`${bin} exited with ${code}: ${text.slice(-1000)}`)));});}
async function body(req){let raw='';for await(const chunk of req){raw+=chunk;if(raw.length>25000)throw Error('Request too large');}try{return JSON.parse(raw);}catch{throw Error('Invalid JSON');}}
async function binaryBody(req,maxBytes=10*1024*1024){const chunks=[];let size=0;for await(const chunk of req){size+=chunk.length;if(size>maxBytes)throw Error('Cover image must be 10 MB or smaller.');chunks.push(chunk);}if(!size)throw Error('Choose a cover image.');return Buffer.concat(chunks);}
const languageId=value=>typeof value==='string'&&/^[a-z]{2}(?:-[A-Za-z0-9]+)*$/.test(value);
const coverType={
 'image/png':{ext:'.png',signature:data=>data.length>=8&&data.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))},
 'image/jpeg':{ext:'.jpg',signature:data=>data.length>=3&&data.subarray(0,3).equals(Buffer.from([255,216,255]))},
 'image/webp':{ext:'.webp',signature:data=>data.length>=12&&data.subarray(0,4).toString()==='RIFF'&&data.subarray(8,12).toString()==='WEBP'},
};
async function uploadLanguageCover(projectId,language,req){
 if(!safeId(projectId)||!languageId(language))throw Error('Invalid project or language.');
 const type=(req.headers['content-type']||'').split(';',1)[0].toLowerCase(),format=coverType[type];
 if(!format)throw Error('Use a PNG, JPEG, or WebP cover image.');
 const image=await binaryBody(req);
 if(!format.signature(image))throw Error('The uploaded file does not match its image type.');
 const project=path.join(root,'content',projectId),manifestPath=path.join(project,'deliverables.json');
 let manifest;
 try{manifest=JSON.parse(await readFile(manifestPath,'utf8'));}catch{throw Error('This project needs a valid deliverables.json before adding covers.');}
 if(manifest.schemaVersion!==1||!Array.isArray(manifest.releases))throw Error('This project has an unsupported deliverables manifest.');
 if(!manifest.releases.some(release=>release.language===language))throw Error('Create a release for this language before uploading its cover.');
 const filename=`cover-${Date.now()}-${randomUUID()}${format.ext}`,relative=path.posix.join('assets','cover',language,filename),target=path.join(project,...relative.split('/'));
 await mkdir(path.dirname(target),{recursive:true});await writeFile(target,image,{flag:'wx'});
 manifest.covers={...(manifest.covers||{}),[language]:relative};
 const temporary=manifestPath+'.tmp-'+randomUUID();
 await writeFile(temporary,JSON.stringify(manifest,null,2)+'\n','utf8');await rename(temporary,manifestPath);
 const next=await buildCatalog(root),topic=next.results.find(item=>item.id===projectId),localized=topic?.languageCovers?.[language];
 if(!localized)throw Error('Cover was saved but could not be registered. Refresh Studio and try again.');
 return {cover:localized};
}
async function releaseFor(projectId,releaseId){const next=await buildCatalog(root);allowed=next.allowed;const project=next.results.find(item=>item.id===projectId);const release=project?.versions.find(item=>item.id===releaseId);const video=release&&next.allowed.get(release.url);if(!project||!release||!video)throw Error('The selected Studio release is unavailable. Refresh and try again.');return {project,release,video};}
const deliveryStatuses=new Set(['draft','review','approved','archived']);
async function updateDeliveryStatus(projectId,releaseId,input){
 if(!safeId(projectId)||!safeId(releaseId)||!deliveryStatuses.has(input?.status))throw Error('Choose a valid Studio delivery status.');
 if(input.status==='approved'&&input.editorialApproval!==true)throw Error('Approved requires explicit editorial approval.');
 const manifestPath=path.join(projectRoot(projectId),'deliverables.json');let manifest;
 try{manifest=JSON.parse(await readFile(manifestPath,'utf8'));}catch{throw Error('This project needs a valid deliverables manifest.');}
 if(manifest.schemaVersion!==1||!Array.isArray(manifest.releases))throw Error('This project has an unsupported deliverables manifest.');
 const release=manifest.releases.find(item=>item.id===releaseId);if(!release)throw Error('Studio delivery not found.');
 release.status=input.status;
 if(input.makeCurrent===true)manifest.current={...(manifest.current||{}),[release.language]:release.id};
 const temporary=manifestPath+'.tmp-'+randomUUID();await writeFile(temporary,JSON.stringify(manifest,null,2)+'\n','utf8');await rename(temporary,manifestPath);
 return {id:release.id,status:release.status,isCurrent:manifest.current?.[release.language]===release.id};
}
async function startSubtitleJob(input){
 if(!safeId(input.projectId)||!safeId(input.releaseId))throw Error('Choose a Studio release.');
 const {release,video}=await releaseFor(input.projectId,input.releaseId);
 const job={id:randomUUID(),kind:'subtitles',state:'queued',projectId:input.projectId,releaseId:input.releaseId,log:'',result:null,error:null};jobs.set(job.id,job);
 void (async()=>{try{job.state='running';const work=path.join(root,'content',input.projectId,'edit','studio-jobs',job.id);await mkdir(work,{recursive:true});const words=path.join(work,'word-timed.srt'),reference=path.join(work,'qa-reference.srt'),subtitles=path.join(work,'subtitles.srt'),report=path.join(work,'speech-qa.json');
  await command('uv',['run','--with','faster-whisper','--with','av>=13,<16','python','skills/reel-subtitles/scripts/transcribe_words.py','--video',video,'--output',words,'--language',release.language,'--model','base'],job);
  await command('uv',['run','--with','faster-whisper','--with','av>=13,<16','python','skills/reel-subtitles/scripts/transcribe_words.py','--video',video,'--output',reference,'--language',release.language,'--model','small'],job);
  await command('python3',['scripts/build_spoken_subtitles.py','--words',words,'--expected-words',reference,'--output',subtitles,'--report',report],job);let deliverable=video;
  if(input.burn!==false){deliverable=path.join(work,'captioned.mp4');await command('python3',['skills/reel-subtitles/scripts/burn_subtitles.py','--video',video,'--subtitles',subtitles,'--output',deliverable,'--preset',subtitlePreset(input.projectId)],job);}const caption=release.caption||'';if(!caption)throw Error('The selected release has no post caption, so it cannot be registered safely.');
  await command('python3',['scripts/publish_to_studio.py',path.join('content',input.projectId),deliverable,'--language',release.language,'--caption',caption,'--subtitles',subtitles,'--label','Speech-to-Text subtitles — review','--notes','Phrase subtitles from word-timed STT. A second, more accurate STT pass is the automatic QA reference; inspect speech-qa.json before approval.'],job);const qa=JSON.parse(await readFile(report,'utf8'));job.result={alignmentRatio:qa.alignment_ratio,subtitleSource:'speech-to-text',qaReference:qa.qa_reference,burned:input.burn!==false,report:qa};job.state='completed';
 }catch(error){job.error=error.message;job.state='failed';}})();return job;}
const dubLanguages={fa:'Persian (Iran)',tr:'Turkish (Türkiye)',ar:'Arabic',...(workspaceConfig().dubbing?.languages||{})};
function jsonOutput(value){const first=value.indexOf('{'),last=value.lastIndexOf('}');if(first<0||last<first)throw Error('Provider returned no JSON response.');return JSON.parse(value.slice(first,last+1));}
function findVideoUrl(value){if(!value||typeof value!=='object')return null;if(typeof value.video_url==='string')return value.video_url;for(const child of Object.values(value)){const found=findVideoUrl(child);if(found)return found;}return null;}
function findProofreadId(value){const ids=value?.data?.proofread_ids||value?.proofread_ids;if(Array.isArray(ids)&&typeof ids[0]==='string')return ids[0];return findUrl(value,'proofread_id')||findUrl(value,'id');}
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const projectRoot=id=>path.join(root,'content',id);
async function download(url,target){const response=await fetch(url);if(!response.ok)throw Error(`Could not download provider file (${response.status}).`);await writeFile(target,Buffer.from(await response.arrayBuffer()));}
function findUrl(value,key){if(!value||typeof value!=='object')return null;if(typeof value[key]==='string')return value[key];for(const child of Object.values(value)){const found=findUrl(child,key);if(found)return found;}return null;}
async function duration(file,job){const output=await command('ffprobe',['-v','error','-show_entries','format=duration','-of','default=nokey=1:noprint_wrappers=1',file],job);const value=Number(output.trim());if(!Number.isFinite(value)||value<=0)throw Error(`Could not determine duration for ${path.basename(file)}.`);return value;}
async function sourceClip(source,start,end,target,job){await command('ffmpeg',['-y','-ss',String(start),'-to',String(end),'-i',source,'-map','0:v:0','-map','0:a?','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',target],job);}
function srtText(srt){return srt.split(/\r?\n/).filter(line=>line.trim()&&!/^\d+$/.test(line.trim())&&!/^\d\d:\d\d:\d\d[,\.]\d{3}\s+-->/.test(line.trim())).join(' ').replace(/\s+/g,' ').trim();}
function srtTime(value){const [h,m,tail]=value.split(':');const [s,ms]=tail.split(',');return Number(h)*3600000+Number(m)*60000+Number(s)*1000+Number(ms);}
function srtStamp(ms){const n=Math.max(0,Math.round(ms));const h=Math.floor(n/3600000),m=Math.floor(n%3600000/60000),s=Math.floor(n%60000/1000),r=n%1000;return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')},${String(r).padStart(3,'0')}`;}
function shiftSrt(srt,offsetSeconds,indexOffset=0){const blocks=srt.trim().split(/\r?\n\s*\r?\n/);return blocks.map((block,index)=>{const lines=block.split(/\r?\n/);const timing=lines.findIndex(line=>line.includes('-->'));if(timing<0)return '';const [start,end]=lines[timing].split(/\s+-->\s+/);lines[0]=String(indexOffset+index+1);lines[timing]=`${srtStamp(srtTime(start)+offsetSeconds*1000)} --> ${srtStamp(srtTime(end)+offsetSeconds*1000)}`;return lines.join('\n');}).filter(Boolean).join('\n\n');}
async function readPlan(projectId){const file=path.join(projectRoot(projectId),'dubbing-plan.json');const plan=JSON.parse(await readFile(file,'utf8'));if(plan?.schemaVersion!==1||!Array.isArray(plan.segments)||!plan.segments.length)throw Error('This project has no valid dubbing plan.');for(const segment of plan.segments){if(!safeId(segment.id)||!Number.isFinite(segment.start)||!Number.isFinite(segment.end)||segment.end<=segment.start||!Number.isInteger(segment.speakerCount)||segment.speakerCount<1)throw Error('The dubbing plan contains an invalid spoken segment.');}return plan;}
async function planSource(projectId,plan){const {project,release,video}=await releaseFor(projectId,plan.sourceRelease);if(release.language!==plan.sourceLanguage)throw Error('The dubbing plan source release has the wrong language.');if((await stat(video)).size>32*1024*1024)throw Error('HeyGen direct upload accepts a source video up to 32 MB.');return {project,release,video};}
async function waitForProofread(id,job){for(let attempt=0;attempt<120;attempt++){const result=jsonOutput(await command('heygen',['video-translate','proofreads','get',id],job));const data=result.data||result;if(data.status==='completed')return data;if(data.status==='failed')throw Error(data.failure_message||'HeyGen Proofread preparation failed.');await wait(attempt<12?10000:30000);}throw Error('HeyGen Proofread preparation did not finish within 60 minutes.');}
async function ensurePlan(input){
 try{return await readPlan(input.projectId)}catch(error){if(error.code!=='ENOENT')throw error}
 const {release,video}=await releaseFor(input.projectId,input.releaseId);
 const probe=await command('ffprobe',['-v','error','-show_entries','format=duration','-of','csv=p=0',video],{});
 const duration=Math.floor(parseFloat(probe)*100)/100;
 if(!Number.isFinite(duration)||duration<1)throw Error('Could not read the selected video duration to create a dubbing plan.');
 const plan={schemaVersion:1,sourceLanguage:release.language,sourceRelease:release.id,strategy:'proofread-per-spoken-beat',autoCreated:true,createdAt:new Date().toISOString(),
  notes:'Auto-created by Studio because no dubbing-plan.json existed: one segment over the whole selected video. Split it into spoken beats (and set the real speaker count) before paying for a multi-speaker or cut video.',
  segments:[{id:'full',start:0,end:duration,speakerCount:1,speaker:'speaker-1'}]};
 const file=path.join(projectRoot(input.projectId),'dubbing-plan.json'),tmp=file+'.tmp';
 await writeFile(tmp,JSON.stringify(plan,null,2)+'\n');await rename(tmp,file);
 return readPlan(input.projectId);
}
async function startProofreadDub(input){
 requireApiMode('heygen');
 if(!safeId(input.projectId)||!safeId(input.releaseId)||!Object.hasOwn(dubLanguages,input.language)||input.paidConfirmation!==true)throw Error('Choose a supported language and confirm the paid Proofread request.');
 const plan=await ensurePlan(input);const {release,video}=await planSource(input.projectId,plan);const job={id:randomUUID(),kind:'proofread-dubbing',state:'queued',projectId:input.projectId,releaseId:release.id,log:'',result:null,error:null};jobs.set(job.id,job);
 void (async()=>{try{job.state='running';const work=path.join(projectRoot(input.projectId),'edit','studio-jobs',job.id);await mkdir(work,{recursive:true});const prepared=[];
  for(const segment of plan.segments){const clip=path.join(work,`${segment.id}-source.mp4`);await sourceClip(video,segment.start,segment.end,clip,job);let proofreadId=typeof input.resumeProofreads?.[segment.id]==='string'?input.resumeProofreads[segment.id]:null;if(!proofreadId){const upload=jsonOutput(await command('heygen',['asset','create','--file',clip],job));const assetId=upload?.data?.asset_id;if(typeof assetId!=='string')throw Error(`HeyGen did not return an asset for ${segment.id}.`);const request={title:`${input.projectId}-${segment.id}-${input.language}-proofread`,video:{type:'asset_id',asset_id:assetId},output_languages:[dubLanguages[input.language]],mode:'precision',speaker_num:segment.speakerCount,enable_speech_enhancement:true,enable_video_stretching:true,keep_the_same_format:true};const requestFile=path.join(work,`${segment.id}-proofread-request.json`);await writeFile(requestFile,JSON.stringify(request,null,2)+'\n','utf8');const created=jsonOutput(await command('heygen',['video-translate','proofreads','create','--data',requestFile],job));await writeFile(path.join(work,`${segment.id}-proofread-created.json`),JSON.stringify(created,null,2)+'\n','utf8');proofreadId=findProofreadId(created);}if(!proofreadId)throw Error(`HeyGen did not return a Proofread ID for ${segment.id}.`);await waitForProofread(proofreadId,job);const srtResponse=jsonOutput(await command('heygen',['video-translate','proofreads','srt','get',proofreadId],job));const srtUrl=findUrl(srtResponse,'srt_url');if(!srtUrl)throw Error(`HeyGen did not return a target SRT for ${segment.id}.`);const srt=path.join(work,`${segment.id}.${input.language}.srt`);await download(srtUrl,srt);prepared.push({...segment,proofreadId,sourceClip:clip,srt});}
  const review={schemaVersion:1,projectId:input.projectId,sourceRelease:release.id,sourceVideo:video,language:input.language,createdAt:new Date().toISOString(),status:'awaiting-editorial-approval',strategy:plan.strategy,segments:prepared};const reviewFile=path.join(work,'proofread-review.json');await writeFile(reviewFile,JSON.stringify(review,null,2)+'\n','utf8');job.result={reviewId:job.id,segments:prepared.map(({id,proofreadId,srt})=>({id,proofreadId,srt:path.relative(root,srt)})),next:'Review the provider SRT files, then use Render approved dub.'};job.state='awaiting-approval';
 }catch(error){job.error=error.message;job.state='failed';}})();return job;
}
async function waitForTranslation(id,job){for(let attempt=0;attempt<120;attempt++){const result=jsonOutput(await command('heygen',['video-translate','get',id],job));const data=result.data||result;if(data.status==='completed')return data;if(data.status==='failed')throw Error(data.failure_message||'HeyGen translation rendering failed.');await wait(attempt<12?10000:30000);}throw Error('HeyGen translation did not finish within 60 minutes.');}
async function renderProofreadDub(input){
 requireApiMode('heygen');
 if(!safeId(input.projectId)||!safeId(input.reviewId)||input.paidConfirmation!==true)throw Error('Choose a valid Proofread review and confirm the paid final render.');
 const work=path.join(projectRoot(input.projectId),'edit','studio-jobs',input.reviewId);const review=JSON.parse(await readFile(path.join(work,'proofread-review.json'),'utf8'));if(review.status!=='awaiting-editorial-approval')throw Error('This Proofread review is not ready for final rendering.');const job={id:randomUUID(),kind:'approved-proofread-render',state:'queued',projectId:input.projectId,releaseId:review.sourceRelease,log:'',result:null,error:null};jobs.set(job.id,job);
 void (async()=>{try{job.state='running';const renderWork=path.join(work,'final-render-'+job.id);await mkdir(renderWork,{recursive:true});const sourceDuration=await duration(review.sourceVideo,job);const timeline=[];let cursor=0,subtitleOffset=0,subtitleIndex=0;let merged='';
  for(const segment of review.segments){if(segment.start>cursor+.01){const gap=path.join(renderWork,`gap-${timeline.length}.mp4`);await sourceClip(review.sourceVideo,cursor,segment.start,gap,job);timeline.push(gap);subtitleOffset+=await duration(gap,job);}const generated=jsonOutput(await command('heygen',['video-translate','proofreads','generate',segment.proofreadId,'--captions'],job));const translationId=findUrl(generated,'video_translation_id')||findUrl(generated,'id');if(!translationId)throw Error(`HeyGen did not start final rendering for ${segment.id}.`);const completed=await waitForTranslation(translationId,job);const videoUrl=findVideoUrl(completed);if(!videoUrl)throw Error(`HeyGen finished ${segment.id} without a video file.`);const localized=path.join(renderWork,`${segment.id}.${review.language}.mp4`);await download(videoUrl,localized);timeline.push(localized);const targetSrt=await readFile(segment.srt,'utf8');const shifted=shiftSrt(targetSrt,subtitleOffset,subtitleIndex);merged+=(merged?'\n\n':'')+shifted;subtitleIndex+=targetSrt.trim().split(/\r?\n\s*\r?\n/).filter(Boolean).length;subtitleOffset+=await duration(localized,job);cursor=segment.end;}
  if(cursor<sourceDuration-.01){const tail=path.join(renderWork,'tail.mp4');await sourceClip(review.sourceVideo,cursor,sourceDuration,tail,job);timeline.push(tail);}const list=path.join(renderWork,'timeline.txt');await writeFile(list,timeline.map(file=>`file '${file.replaceAll("'","'\\\\''")}'`).join('\n')+'\n','utf8');const assembled=path.join(renderWork,`reel-${review.language}.mp4`);await command('ffmpeg',['-y','-f','concat','-safe','0','-i',list,'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',assembled],job);const subtitles=path.join(renderWork,`subtitles.${review.language}.srt`);await writeFile(subtitles,merged+'\n','utf8');const caption=srtText(merged);const captioned=path.join(renderWork,`reel-${review.language}-subtitles.mp4`);await command('python3',['skills/reel-subtitles/scripts/burn_subtitles.py','--video',assembled,'--subtitles',subtitles,'--output',captioned,'--preset',subtitlePreset(input.projectId)],job);await command('python3',['scripts/publish_to_studio.py',path.join('content',input.projectId),captioned,'--language',review.language,'--caption',caption,'--subtitles',subtitles,'--label','HeyGen Proofread dub + provider subtitles — review','--notes',`Per-spoken-beat Precision lip-sync from ${review.sourceRelease}. Captions come from reviewed HeyGen target SRT files, not local Speech-to-Text. Listen to the full assembly before approval.`],job);review.status='rendered';review.renderJobId=job.id;await writeFile(path.join(work,'proofread-review.json'),JSON.stringify(review,null,2)+'\n','utf8');job.result={subtitleSource:'HeyGen Proofread target SRT',burned:true,segments:review.segments.length};job.state='completed';
 }catch(error){job.error=error.message;job.state='failed';}})();return job;
}
async function proofreadSrt(projectId,reviewId,segmentId){
 if(!safeId(projectId)||!safeId(reviewId)||!safeId(segmentId))throw Error('Invalid Proofread subtitle path.');
 const work=path.join(projectRoot(projectId),'edit','studio-jobs',reviewId);const review=JSON.parse(await readFile(path.join(work,'proofread-review.json'),'utf8'));const segment=review.segments?.find(item=>item.id===segmentId);if(!segment||typeof segment.srt!=='string')throw Error('Proofread subtitle not found.');const file=path.resolve(segment.srt);if(!file.startsWith(work+path.sep)||path.extname(file)!=='.srt')throw Error('Invalid Proofread subtitle path.');return file;
}
process.on('uncaughtException',e=>{console.error('uncaught',e);if(e&&e.code==='EADDRINUSE')process.exit(1)});process.on('unhandledRejection',e=>console.error('unhandled',e));

// ---------- Batch: inbox, bulk subtitles, dubbing queue ----------
const VIDEO_EXT=/\.(mp4|mov|m4v|webm)$/i,INBOX=path.join(root,'input','videos');
function localOnlyPost(req){const origin=req.headers.origin;if(origin&&!['http://localhost:8789','http://127.0.0.1:8789'].includes(origin))throw Error('Invalid origin');if(!(req.headers['content-type']||'').includes('application/json'))throw Error('JSON required');}
async function inboxList(){await mkdir(INBOX,{recursive:true});const out=[];for(const name of await readdir(INBOX)){if(!VIDEO_EXT.test(name))continue;const st=await stat(path.join(INBOX,name));out.push({name,bytes:st.size,modified:st.mtimeMs})}return out.sort((a,b)=>b.modified-a.modified)}
async function inboxUpload(req,rawName){const base=path.basename(String(rawName||'')).replace(/[^\w.\- ()؀-ۿ]+/g,'_');if(!VIDEO_EXT.test(base))throw Error('Only .mp4, .mov, .m4v or .webm files.');await mkdir(INBOX,{recursive:true});const ext=path.extname(base),stem=base.slice(0,-ext.length);let name=base,n=2;while(existsSync(path.join(INBOX,name)))name=`${stem}-${n++}${ext}`;const target=path.join(INBOX,name),tmp=target+'.part';
 let size=0;const limit=4*1024*1024*1024;req.on('data',c=>{size+=c.length;if(size>limit)req.destroy(Error('File larger than 4 GB.'))});
 try{await pipeline(req,createWriteStream(tmp,{flags:'wx'}));await rename(tmp,target)}catch(error){try{await (await import('node:fs/promises')).unlink(tmp)}catch{}throw error}
 return {name,bytes:size}}
function startIngestJob(){const job={id:randomUUID(),kind:'ingest-inbox',state:'queued',log:'',result:null,error:null};jobs.set(job.id,job);void(async()=>{try{job.state='running';const out=await command('python3',['scripts/content/ingest.py'],job);job.result={output:out.trim()};job.state='completed'}catch(error){job.error=error.message;job.state='failed'}})();return job}
async function subtitleCandidates(){const out=[];for(const id of await readdir(path.join(root,'content'))){const base=path.join(root,'content',id);let st;try{st=await stat(base)}catch{continue}if(!st.isDirectory())continue;let video=null;try{video=(await readdir(path.join(base,'source','video'))).find(n=>VIDEO_EXT.test(n))||null}catch{}
  let done=false;try{for(const d of await readdir(path.join(base,'edit','subtitles')))if(existsSync(path.join(base,'edit','subtitles',d,'result.json')))done=true}catch{}
  const script=['script.txt','script.md','source/script.txt'].some(f=>existsSync(path.join(base,f)));out.push({id,video,script,done})}return out}
function startBulkSubtitles(ids){if([...jobs.values()].some(j=>j.kind==='bulk-subtitles'&&['queued','running'].includes(j.state)))throw Error('A bulk subtitle run is already in progress.');
 const job={id:randomUUID(),kind:'bulk-subtitles',state:'queued',log:'',result:null,error:null,items:ids.map(id=>({id,state:'waiting',detail:''}))};jobs.set(job.id,job);
 void(async()=>{job.state='running';for(const item of job.items){item.state='running';try{const out=await command('python3',['scripts/content/subtitle_content.py','--content',path.join('content',item.id)],job);const line=out.trim().split('\n').filter(l=>l.startsWith('{')).pop(),r=line?JSON.parse(line):{};item.state=r.status==='ok'?'done':r.status==='needs-review'?'needs-review':r.status==='skipped'?'skipped':'failed';item.detail=r.reason||(r.language?`language ${r.language}, script check: ${r.scriptCheck}`:'');item.result=r}catch(error){item.state='failed';item.detail=String(error.message).slice(-300)}}
  job.state=job.items.some(i=>i.state==='failed')?'failed':'completed';job.result={done:job.items.filter(i=>i.state==='done').length,total:job.items.length}})();return job}

const QUEUE_FILE=path.join(root,'runtime','queue','dubbing.json');let dubQueue={items:[]},queueRunning=false;
async function queueLoad(){try{dubQueue=JSON.parse(await readFile(QUEUE_FILE,'utf8'));if(!Array.isArray(dubQueue.items))dubQueue={items:[]}}catch{dubQueue={items:[]}}
 for(const it of dubQueue.items)if(['running','rendering'].includes(it.state)){it.state='interrupted';it.error='Studio restarted while this was running. It was NOT resubmitted; check HeyGen for the job before adding it again.'}await queueSave()}
async function queueSave(){await mkdir(path.dirname(QUEUE_FILE),{recursive:true});const tmp=QUEUE_FILE+'.tmp';await writeFile(tmp,JSON.stringify(dubQueue,null,2)+'\n');await rename(tmp,QUEUE_FILE)}
async function queueAdd(input){requireApiMode('heygen');if(input.paidConfirmation!==true)throw Error('Confirm the paid Proofread step for these items.');if(!Array.isArray(input.items)||!input.items.length||input.items.length>50)throw Error('Add between 1 and 50 items.');
 const added=[];for(const x of input.items){if(!safeId(x.projectId)||!safeId(x.releaseId)||!Object.hasOwn(dubLanguages,x.language))throw Error('Invalid queue item.');
  if(dubQueue.items.some(i=>i.projectId===x.projectId&&i.releaseId===x.releaseId&&i.language===x.language&&['queued','running','awaiting-review','render-queued','rendering'].includes(i.state)))continue;
  const it={id:randomUUID(),projectId:x.projectId,releaseId:x.releaseId,language:x.language,state:'queued',reviewId:null,error:null,addedAt:Date.now(),updatedAt:Date.now(),confirmed:{proofread:true,render:false}};dubQueue.items.push(it);added.push(it)}
 await queueSave();void queueRun();return added}
async function queueRender(id,input){requireApiMode('heygen');const it=dubQueue.items.find(i=>i.id===id);if(!it)throw Error('Queue item not found.');if(it.state!=='awaiting-review')throw Error('Only an item awaiting review can be rendered.');if(input.paidConfirmation!==true)throw Error('Confirm the paid final render.');it.state='render-queued';it.confirmed.render=true;it.updatedAt=Date.now();await queueSave();void queueRun();return it}
async function queueCancel(id){const it=dubQueue.items.find(i=>i.id===id);if(!it)throw Error('Queue item not found.');if(!['queued','render-queued','awaiting-review','interrupted','failed'].includes(it.state))throw Error('A running item cannot be cancelled.');it.state='cancelled';it.updatedAt=Date.now();await queueSave();return it}
async function untilDone(job){while(!['completed','failed','awaiting-approval'].includes(job.state))await wait(2000);return job}
async function queueRun(){if(queueRunning)return;queueRunning=true;try{for(;;){const it=dubQueue.items.find(i=>i.state==='queued')||dubQueue.items.find(i=>i.state==='render-queued');if(!it)break;const render=it.state==='render-queued';it.state=render?'rendering':'running';it.error=null;it.updatedAt=Date.now();await queueSave();
  try{const job=render?await renderProofreadDub({projectId:it.projectId,reviewId:it.reviewId,paidConfirmation:true}):await startProofreadDub({projectId:it.projectId,releaseId:it.releaseId,language:it.language,paidConfirmation:true});it.jobId=job.id;await queueSave();await untilDone(job);
   if(job.state==='failed'){it.state='failed';it.error=job.error}else if(render){it.state='done'}else{it.state='awaiting-review';it.reviewId=job.result?.reviewId||job.id}}
  catch(error){it.state='failed';it.error=error.message}it.updatedAt=Date.now();await queueSave()}}finally{queueRunning=false}}
let balanceCache={at:0,value:null};
async function heygenBalance(){if(Date.now()-balanceCache.at<60000)return balanceCache.value;let v=null;try{const d=jsonOutput(await command('heygen',['auth','status'],{}));v=d?.data?.wallet?.remaining_balance??null}catch{}balanceCache={at:Date.now(),value:v};return v}
await queueLoad();
const server=http.createServer(async(req,res)=>{
 const json=(code,data)=>{res.writeHead(code,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(data));};
 if(!['localhost:8789','127.0.0.1:8789'].includes(req.headers.host))return json(403,{error:'Invalid host'});
 const p=new URL(req.url,'http://localhost:8789').pathname;
 try{
  const coverMatch=/^\/api\/covers\/([\w-]+)\/([a-z]{2}(?:-[A-Za-z0-9]+)*)$/.exec(p);
  if(req.method==='POST'&&coverMatch)return json(201,await uploadLanguageCover(coverMatch[1],coverMatch[2],req));
  const statusMatch=/^\/api\/deliverables\/([\w-]+)\/([\w-]+)\/status$/.exec(p);
  if(req.method==='POST'&&statusMatch)return json(200,await updateDeliveryStatus(statusMatch[1],statusMatch[2],await body(req)));
  if(req.method==='POST'&&p==='/api/jobs/subtitles'){const job=await startSubtitleJob(await body(req));return json(202,{id:job.id,state:job.state});}
  if(req.method==='POST'&&p==='/api/jobs/dubbing/proofread'){const job=await startProofreadDub(await body(req));return json(202,{id:job.id,state:job.state});}
  if(req.method==='POST'&&p==='/api/jobs/dubbing/render'){const job=await renderProofreadDub(await body(req));return json(202,{id:job.id,state:job.state});}
  const proofreadMatch=/^\/api\/projects\/([\w-]+)\/proofreads\/([\w-]+)\/([\w-]+)\.srt$/.exec(p);if(req.method==='GET'&&proofreadMatch){const file=await proofreadSrt(proofreadMatch[1],proofreadMatch[2],proofreadMatch[3]);res.writeHead(200,{'Content-Type':'application/x-subrip; charset=utf-8','Cache-Control':'no-store'});return res.end(await readFile(file));}
  if(p==='/api/inbox'&&req.method==='GET')return json(200,await inboxList());
  if(p==='/api/inbox/upload'&&req.method==='POST'){const o=req.headers.origin;if(o&&!['http://localhost:8789','http://127.0.0.1:8789'].includes(o))return json(403,{error:'Invalid origin'});return json(201,await inboxUpload(req,new URL(req.url,'http://localhost:8789').searchParams.get('name')));}
  if(p==='/api/inbox/ingest'&&req.method==='POST'){localOnlyPost(req);await body(req);const job=startIngestJob();return json(202,{id:job.id,state:job.state});}
  if(p==='/api/bulk/subtitles'&&req.method==='GET')return json(200,await subtitleCandidates());
  if(p==='/api/bulk/subtitles'&&req.method==='POST'){localOnlyPost(req);const b=await body(req);const all=await subtitleCandidates();const ids=(Array.isArray(b.contentIds)&&b.contentIds.length?b.contentIds:all.filter(x=>x.video&&!x.done).map(x=>x.id)).filter(id=>all.some(x=>x.id===id&&x.video));if(!ids.length)throw Error('No content with a source video to process.');const job=startBulkSubtitles(ids);return json(202,{id:job.id,state:job.state});}
  if(p==='/api/queue/dubbing'&&req.method==='GET')return json(200,{items:dubQueue.items,balance:await heygenBalance(),mode:providerMode('heygen'),languages:Object.keys(dubLanguages)});
  if(p==='/api/queue/dubbing'&&req.method==='POST'){localOnlyPost(req);return json(201,{added:await queueAdd(await body(req))});}
  const qm=/^\/api\/queue\/dubbing\/([\w-]+)\/(render|cancel)$/.exec(p);if(qm&&req.method==='POST'){localOnlyPost(req);const b=await body(req);return json(200,qm[2]==='render'?await queueRender(qm[1],b):await queueCancel(qm[1]))}
  if(p==='/api/settings'&&['GET','POST'].includes(req.method)){
   if(req.method==='POST'){const origin=req.headers.origin;if(origin&&!['http://localhost:8789','http://127.0.0.1:8789'].includes(origin))return json(403,{error:'Invalid origin'});if(!(req.headers['content-type']||'').includes('application/json'))return json(415,{error:'JSON required'});const b=await body(req);await writeEnv(String(b.key||''),b.remove?null:String(b.value??''));}
   return json(200,await settingsView());}
  if(req.method==='GET'&&p==='/api/workspace')return json(200,{defaultBrand:workspaceConfig().defaultBrand,dubLanguages});
  if(req.method==='GET'&&p==='/api/jobs')return json(200,jobsList());
  if(req.method==='GET'&&p==='/api/mcp-status')return json(200,await mcpStatus());
  if(req.method==='GET'&&p.startsWith('/api/jobs/')){const job=jobs.get(p.slice('/api/jobs/'.length));return job?json(200,job):json(404,{error:'Job not found'});}
  if(!['GET','HEAD'].includes(req.method))return json(405,{error:'Unsupported method'});
  if(req.method==='GET'&&p==='/api/frame'){if(!allowed.size)await catalog();const src=new URL(req.url,'http://localhost:8789').searchParams.get('src')||'',video=allowed.get(src);if(!video||!/\.(mp4|mov|m4v|webm)$/i.test(video))return json(404,{error:'Unknown video'});const dir=path.join(root,'runtime','studio','frames');await mkdir(dir,{recursive:true});const out=path.join(dir,createHash('sha1').update(video).digest('hex')+'.jpg');if(!existsSync(out)){for(const t of ['1.2','0'])try{await command('ffmpeg',['-y','-loglevel','error','-ss',t,'-i',video,'-frames:v','1','-vf','scale=720:-2','-q:v','3',out],{});if(existsSync(out))break}catch{}}if(!existsSync(out))return json(500,{error:'Could not extract a frame'});res.writeHead(200,{'Content-Type':'image/jpeg','Cache-Control':'public, max-age=3600'});const rs=createReadStream(out);rs.on('error',()=>res.destroy());return rs.pipe(res);}
  if(p==='/api/results')return json(200,await catalog());let file;
  if(['/studio','/studio/','/studio/index.html','/'].includes(p))file=path.join(root,'studio/index.html');else{if(!allowed.size)await catalog();file=allowed.get(p);}
  if(!file)return json(404,{error:'Not found'});const real=await realpath(file);if(!real.startsWith(root+path.sep)||real!==file)return json(403,{error:'Invalid asset'});
  const info=await stat(real),types={'.html':'text/html; charset=utf-8','.mp4':'video/mp4','.webm':'video/webm','.mov':'video/quicktime','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.txt':'text/plain; charset=utf-8','.srt':'application/x-subrip; charset=utf-8','.vtt':'text/vtt; charset=utf-8'};
  const headers={'Content-Type':types[path.extname(real)]||'application/octet-stream','Accept-Ranges':'bytes'};let start=0,end=info.size-1,code=200;
  if(req.headers.range){const m=/^bytes=(\d*)-(\d*)$/.exec(req.headers.range);if(!m||(!m[1]&&!m[2]))return res.writeHead(416).end();if(!m[1])start=Math.max(0,info.size-Number(m[2]));else{start=Number(m[1]);if(m[2])end=Math.min(end,Number(m[2]));}if(start>end||start>=info.size)return res.writeHead(416,{'Content-Range':`bytes */${info.size}`}).end();code=206;headers['Content-Range']=`bytes ${start}-${end}/${info.size}`;}
  headers['Content-Length']=end-start+1;res.writeHead(code,headers);if(req.method==='HEAD')return res.end();const stream=createReadStream(real,{start,end});stream.on('error',()=>res.destroy());res.on('close',()=>stream.destroy());stream.pipe(res);
 }catch(error){json(400,{error:error?.message||'Could not load results'});}
});
server.listen(8789,'127.0.0.1',()=>console.log('Results gallery: http://localhost:8789/studio/'));
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>server.close(()=>process.exit(0)));
