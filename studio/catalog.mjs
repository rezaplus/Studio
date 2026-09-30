import {readdir, readFile, realpath, stat} from 'node:fs/promises';
import path from 'node:path';

const languages = ['en', 'fa', 'tr', 'ar'];
const inside = (base, file) => file.startsWith(base + path.sep);
async function walk(dir) {
  try {
    const entries = await readdir(dir, {withFileTypes: true});
    return (await Promise.all(entries.map(e => e.isDirectory() ? walk(path.join(dir, e.name)) : e.isFile() ? [path.join(dir, e.name)] : []))).flat();
  } catch { return []; }
}

export async function buildCatalog(root) {
  root = await realpath(root);
  const allowed = new Map(), results = [];
  const contents = path.join(root, 'content');
  const entries = await readdir(contents, {withFileTypes: true});
  for (const entry of entries.sort((a,b) => a.name.localeCompare(b.name))) {
    if (!entry.isDirectory()) continue;
    const base = path.join(contents, entry.name), warnings = [];
    // Only explicit deliverables inside this project can be served, including
    // after symlink resolution. Never expose arbitrary paths from a manifest.
    async function asset(relative, extensions) {
      if (typeof relative !== 'string' || path.isAbsolute(relative)) throw Error('Invalid asset path');
      const file = path.resolve(base, relative);
      if (!inside(base, file) || !extensions.includes(path.extname(file).toLowerCase())) throw Error('Invalid asset path/type');
      const real = await realpath(file);
      if (!inside(base, real) || !(await stat(real)).isFile()) throw Error('Invalid asset target');
      const url = '/media/' + path.relative(root, file).split(path.sep).map(encodeURIComponent).join('/');
      allowed.set(url, real);
      return {url, file: real};
    }
    let meta = {};
    try { meta = JSON.parse(await readFile(path.join(base, 'project.json'), 'utf8')); } catch {}
    let manifest, manifestPresent = false;
    try {
      const raw = await readFile(path.join(base, 'deliverables.json'), 'utf8');
      manifestPresent = true;
      manifest = JSON.parse(raw);
      if (manifest.schemaVersion !== 1 || !Array.isArray(manifest.releases)) throw Error('Unsupported manifest schema');
    } catch (error) {
      if (error.code !== 'ENOENT') {manifestPresent = true; warnings.push('Invalid deliverables.json: ' + error.message);}
    }
    const versions = [];
    let cover = null;
    const languageCovers = {};
    if (manifestPresent) {
      if (manifest?.schemaVersion === 1 && Array.isArray(manifest.releases)) {
        if (manifest.covers && (typeof manifest.covers !== 'object' || Array.isArray(manifest.covers))) {
          warnings.push('Language covers must be an object');
        } else {
          for (const [language, coverPath] of Object.entries(manifest.covers || {})) {
            try {
              if (!/^[a-z]{2}(?:-[A-Za-z0-9]+)*$/.test(language)) throw Error('Invalid language');
              if (!coverPath.startsWith('assets/cover/')) throw Error('Language cover must be under assets/cover/');
              languageCovers[language] = (await asset(coverPath, ['.png', '.jpg', '.jpeg', '.webp'])).url;
            } catch { warnings.push(`${language}: language cover missing or invalid`); }
          }
        }
        const ids = new Set();
        for (const release of manifest.releases) {
          try {
            if (!/^[\w-]+$/.test(release.id || '') || ids.has(release.id)) throw Error('Invalid/duplicate release id');
            ids.add(release.id);
            if (!/^[a-z]{2}(?:-[A-Za-z0-9]+)*$/.test(release.language || '') || !Number.isInteger(release.version) || release.version < 1) throw Error('Invalid language/version');
            if (!['draft', 'review', 'approved', 'archived'].includes(release.status)) throw Error('Invalid status');
            if (!/^(drafts|releases|finals)\//.test(release.video || '')) throw Error('Video must be under drafts or releases/');
            const video = await asset(release.video, ['.mp4', '.webm', '.mov']);
            let caption = null, captionUrl = null, subtitlesUrl = null;
            if (release.caption) {
              try {if (!/^(drafts|releases|finals)\//.test(release.caption)) throw Error('Caption must be under drafts or releases/');const item = await asset(release.caption, ['.txt']); caption = (await readFile(item.file, 'utf8')).trim() || null; captionUrl = caption ? item.url : null;if (!caption) warnings.push(`${release.id}: empty caption`);}
              catch {warnings.push(`${release.id}: caption missing or invalid`);}
            }
            if (release.subtitles) {
              try {if (!/^(drafts|releases|finals)\//.test(release.subtitles)) throw Error('Subtitles must be under drafts or releases/');subtitlesUrl = (await asset(release.subtitles, ['.srt', '.vtt'])).url;}
              catch {warnings.push(`${release.id}: subtitles missing or invalid`);}
            }
            versions.push({id: release.id, language: release.language, version: 'v' + release.version,
              versionNumber: release.version, status: release.status, label: release.label || release.id,
              name: path.basename(release.video), url: video.url, caption, captionUrl, subtitlesUrl,
              notes: release.notes || '', cover: languageCovers[release.language] || null,
              isCurrent: manifest.current?.[release.language] === release.id});
          } catch (error) {warnings.push(`${release.id || 'release'}: ${error.message}`);}
        }
        for (const [language, id] of Object.entries(manifest.current || {})) {
          if (!versions.some(v => v.id === id && v.language === language)) warnings.push(`${language}: current release unavailable`);
        }
        if (manifest.cover) try {cover = (await asset(manifest.cover, ['.png', '.jpg', '.jpeg', '.webp'])).url;} catch {warnings.push('Cover unavailable');}
      }
    } else {
      // Legacy read-only discovery remains available until a project migrates.
      const files = (await walk(path.join(base, 'finals'))).sort();
      const candidates = [];
      for (const file of files.filter(f => /\.(mp4|webm|mov)$/i.test(f))) {
        try {
          const video = await asset(path.relative(base, file), ['.mp4', '.webm', '.mov']);
          const name = path.basename(file), language = name.match(/reel-(fa|tr|ar|en)(?:-|\.)/)?.[1] || 'en';
          let caption = null, captionUrl = null;
          try {const item = await asset(path.relative(base, path.join(path.dirname(file), 'caption.txt')), ['.txt']); caption = (await readFile(item.file, 'utf8')).trim() || null; captionUrl = caption ? item.url : null;} catch {}
          candidates.push({id: path.relative(base, file), name, language, version: name.match(/v\d+/)?.[0] || 'Export', versionNumber: Number(name.match(/v(\d+)/)?.[1] || 0), url: video.url, caption, captionUrl, status: 'review', isCurrent: true, label: 'Legacy export'});
        } catch {warnings.push('Unavailable legacy video: ' + path.basename(file));}
      }
      const score = v => v.versionNumber * 100 + (/timer/.test(v.name) ? 20 : 0) + (/subtitles/.test(v.name) ? 10 : 0);
      const latest = new Map();
      for (const v of candidates) if (!latest.has(v.language) || score(v) > score(latest.get(v.language))) latest.set(v.language, v);
      versions.push(...latest.values());
      const coverFile = (await walk(path.join(base, 'assets/cover'))).filter(f => /\.(png|jpg|jpeg|webp)$/i.test(f)).sort().at(-1) || files.find(f => /\.(png|jpg|jpeg|webp)$/i.test(f));
      if (coverFile) try {cover = (await asset(path.relative(base, coverFile), ['.png', '.jpg', '.jpeg', '.webp'])).url;} catch {}
    }
    versions.sort((a,b) => (languages.indexOf(a.language) < 0 ? 99 : languages.indexOf(a.language)) - (languages.indexOf(b.language) < 0 ? 99 : languages.indexOf(b.language)) || b.versionNumber - a.versionNumber || a.id.localeCompare(b.id));
    const sharedCover = cover;
    // The library card prefers an English language cover, then any other
    // available language cover, and finally the legacy shared project cover.
    const localizedCardCover = [...languages, ...Object.keys(languageCovers).filter(language => !languages.includes(language))]
      .find(language => languageCovers[language] && versions.some(version => version.language === language));
    if (localizedCardCover) cover = languageCovers[localizedCardCover];
    if (versions.length || warnings.length) results.push({id: entry.name, title: manifest?.title || meta.title || entry.name, cover, sharedCover, languageCovers, versions, warnings, source: manifestPresent ? 'manifest' : 'legacy'});
  }
  return {results, allowed};
}
