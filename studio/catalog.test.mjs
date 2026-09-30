import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, writeFile, symlink, rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {buildCatalog} from './catalog.mjs';

async function fixture(t) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'batimo-studio-test-'));
  t.after(() => rm(root, {recursive: true, force: true}));
  const base = path.join(root, 'content/topic');
  await mkdir(path.join(base, 'finals/tr'), {recursive: true});
  await writeFile(path.join(base, 'finals/tr/reel-tr-v1.mp4'), 'fixture');
  await writeFile(path.join(base, 'finals/tr/reel-tr-v2.mp4'), 'fixture');
  await writeFile(path.join(base, 'finals/tr/caption.txt'), 'Türkçe BİLGİ');
  const release = (id, version) => ({id, version, language:'tr', status:'review', video:`finals/tr/reel-tr-v${version}.mp4`, caption:'finals/tr/caption.txt'});
  return {root, base, release};
}
test('explicit current overrides highest version, history and captions retained', async t => {
  const f = await fixture(t);
  await writeFile(path.join(f.base, 'deliverables.json'), JSON.stringify({schemaVersion:1, current:{tr:'older'}, releases:[f.release('older',1),f.release('newer',2)]}));
  const {results} = await buildCatalog(f.root);
  assert.equal(results[0].versions.length, 2);
  assert.equal(results[0].versions.find(v=>v.isCurrent).id, 'older');
  assert.equal(results[0].versions[0].caption, 'Türkçe BİLGİ');
  assert.deepEqual(results[0].warnings, []);
});
test('legacy selects latest candidate and reads caption.txt', async t => {
  const f=await fixture(t), {results}=await buildCatalog(f.root);
  assert.equal(results[0].source,'legacy');
  assert.equal(results[0].versions[0].version,'v2');
});
test('invalid manifest reports warning without falling back to automatic final', async t => {
  const f=await fixture(t);
  await writeFile(path.join(f.base,'deliverables.json'), '{');
  const {results}=await buildCatalog(f.root);
  assert.equal(results[0].versions.length,0);
  assert.equal(results[0].warnings.length,1);
});
test('rejects missing video, traversal and symlink outside project', async t => {
  const f=await fixture(t);
  await writeFile(path.join(f.root,'secret.txt'),'private');
  await symlink(path.join(f.root,'secret.txt'),path.join(f.base,'finals/tr/leak.mp4'));
  const bad=[{...f.release('missing',9)}, {...f.release('traversal',1),video:'finals/../../../secret.txt'}, {...f.release('symlink',1),video:'finals/tr/leak.mp4'}];
  await writeFile(path.join(f.base,'deliverables.json'),JSON.stringify({schemaVersion:1,releases:bad}));
  const {results,allowed}=await buildCatalog(f.root);
  assert.equal(results[0].versions.length,0);
  assert.equal(results[0].warnings.length,3);
  assert.equal(allowed.size,0);
});
test('missing captions do not substitute another language', async t => {
  const f=await fixture(t);
  await writeFile(path.join(f.base,'deliverables.json'),JSON.stringify({schemaVersion:1,releases:[{...f.release('one',1),caption:'finals/tr/missing.txt'}]}));
  const {results}=await buildCatalog(f.root);
  assert.equal(results[0].versions[0].caption,null);
  assert.match(results[0].warnings[0],/caption/);
});
test('language-specific cover is exposed on its language release', async t => {
  const f=await fixture(t);
  await mkdir(path.join(f.base,'assets/cover/tr'),{recursive:true});
  await writeFile(path.join(f.base,'assets/cover/tr/cover.png'),'fixture');
  await writeFile(path.join(f.base,'deliverables.json'),JSON.stringify({
    schemaVersion:1,
    covers:{tr:'assets/cover/tr/cover.png'},
    releases:[f.release('one',1)]
  }));
  const {results}=await buildCatalog(f.root);
  assert.match(results[0].versions[0].cover,/assets\/cover\/tr\/cover\.png$/);
  assert.match(results[0].languageCovers.tr,/assets\/cover\/tr\/cover\.png$/);
});
test('registered drafts are safe to serve and retain their draft status', async t => {
  const f=await fixture(t);
  await mkdir(path.join(f.base,'drafts/tr/v001'),{recursive:true});
  await writeFile(path.join(f.base,'drafts/tr/v001/video.mp4'),'fixture');
  await writeFile(path.join(f.base,'deliverables.json'),JSON.stringify({schemaVersion:1,current:{tr:'draft-one'},releases:[{id:'draft-one',version:1,language:'tr',status:'draft',video:'drafts/tr/v001/video.mp4',notes:'Awaiting editorial review'}]}));
  const {results,allowed}=await buildCatalog(f.root);
  const draft=results[0].versions[0];
  assert.equal(draft.status,'draft');
  assert.equal(draft.isCurrent,true);
  assert.match(draft.url,/drafts\/tr\/v001\/video\.mp4$/);
  assert.equal(allowed.size,1);
});
