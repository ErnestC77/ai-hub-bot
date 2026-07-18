#!/usr/bin/env node
/**
 * build-media.mjs — разовая (идемпотентная) оптимизация превью-медиа мини-аппа.
 *
 * Делает две вещи, устраняющие «секундный прогруз» при перезаходе:
 *   1. Постер-кадр (лёгкий WebP) для каждого превью-видео — показывается мгновенно
 *      как атрибут <video poster>, пока тело видео догружается/декодируется.
 *   2. Сжатие самих превью-видео (H.264, масштаб под реальный размер карточек) —
 *      было ~30 МБ на 36 трендов, крупные ролики до 2.4 МБ.
 *
 * Запускается ЛОКАЛЬНО один раз; результат коммитится в git и едет на сервер
 * как обычная статика (ffmpeg на проде не нужен). Требует ffmpeg/ffprobe:
 *   winget install Gyan.FFmpeg
 * Пути к бинарям берутся из env FFMPEG / FFPROBE, иначе из PATH.
 *
 * Идемпотентность: обработанные видео помечаются в public/trends/.media-manifest.json
 * (по имени + исходному размеру), повторный прогон их пропускает — иначе сжатие
 * уже сжатого деградирует качество. Постеры регенерируются всегда (дёшево, тот же кадр).
 */
import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const FFMPEG = process.env.FFMPEG || "ffmpeg";
const FFPROBE = process.env.FFPROBE || "ffprobe";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PUB = join(ROOT, "frontend-next", "public");
const TRENDS = join(PUB, "trends");
const POSTERS = join(TRENDS, "posters");
const ACTIONS = join(PUB, "actions");
const MANIFEST = join(TRENDS, ".media-manifest.json");

// Карточка тренда 132×172, actions ещё мельче. 480p по высоте с запасом на
// ретину; постер 344px (~172 @2x). Превью немые -> звук выкидываем (-an).
const POSTER_HEIGHT = 344;
const VIDEO_HEIGHT = 480;
const CRF = "30"; // превью: качество не критично, вес важнее

function run(bin, args) {
  return execFileSync(bin, args, { stdio: ["ignore", "pipe", "pipe"] });
}
function kb(p) {
  return Math.round(statSync(p).size / 1024);
}
function loadManifest() {
  try {
    return JSON.parse(readFileSync(MANIFEST, "utf8"));
  } catch {
    return {};
  }
}

/** Первый кадр -> WebP постер (в родном аспекте видео; CSS впишет по месту). */
function makePoster(mp4, outWebp) {
  run(FFMPEG, [
    "-y", "-ss", "0", "-i", mp4,
    "-frames:v", "1",
    "-vf", `scale=-2:${POSTER_HEIGHT}`,
    "-c:v", "libwebp", "-quality", "80",
    outWebp,
  ]);
}

/** Сжатие видео на месте. Заменяет оригинал только если реально стало легче. */
function compressVideo(mp4) {
  const tmp = `${mp4}.tmp.mp4`;
  run(FFMPEG, [
    "-y", "-i", mp4,
    "-vf", `scale=-2:${VIDEO_HEIGHT}`,
    "-c:v", "libx264", "-crf", CRF, "-preset", "veryfast",
    "-pix_fmt", "yuv420p",
    "-an",
    "-movflags", "+faststart",
    tmp,
  ]);
  const before = kb(mp4);
  const after = kb(tmp);
  if (after < before) {
    renameSync(tmp, mp4);
    return { before, after, replaced: true };
  }
  rmSync(tmp);
  return { before, after, replaced: false };
}

function processDir(label, dir, videoNames) {
  if (!existsSync(dir)) return;
  const manifest = loadManifest();
  let posterCount = 0;
  let savedKb = 0;

  for (const name of videoNames) {
    const mp4 = join(dir, name);
    if (!existsSync(mp4)) continue;
    const slug = basename(name, ".mp4");

    // Постер (всегда): /trends/posters/<slug>.webp или /actions/<slug>-poster.webp
    const posterOut =
      dir === TRENDS ? join(POSTERS, `${slug}.webp`) : join(dir, `${slug}-poster.webp`);
    makePoster(mp4, posterOut);
    posterCount++;

    // Сжатие (один раз): guard по имени + исходному размеру
    const key = `${label}/${name}`;
    const curSize = statSync(mp4).size;
    if (manifest[key]?.done && manifest[key]?.optSize === curSize) {
      console.log(`  = ${name} (уже сжато, ${kb(mp4)} КБ)`);
      continue;
    }
    const r = compressVideo(mp4);
    manifest[key] = { done: true, origSize: r.before * 1024, optSize: statSync(mp4).size };
    if (r.replaced) {
      savedKb += r.before - r.after;
      console.log(`  ↓ ${name}: ${r.before} → ${r.after} КБ`);
    } else {
      console.log(`  = ${name}: ${r.before} КБ (сжатие не уменьшило, оставлено)`);
    }
    writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2));
  }
  console.log(`${label}: постеров ${posterCount}, экономия ~${Math.round(savedKb / 1024)} МБ`);
}

function main() {
  // Проверка бинарей заранее — понятная ошибка вместо стектрейса из execFileSync.
  try {
    run(FFMPEG, ["-version"]);
    run(FFPROBE, ["-version"]);
  } catch {
    console.error(
      `ffmpeg/ffprobe не найдены. Установите (winget install Gyan.FFmpeg) или задайте FFMPEG/FFPROBE.`,
    );
    process.exit(1);
  }

  mkdirSync(POSTERS, { recursive: true });

  const trendVideos = readdirSync(TRENDS).filter((f) => f.endsWith(".mp4"));
  processDir("trends", TRENDS, trendVideos);

  const actionVideos = existsSync(ACTIONS)
    ? readdirSync(ACTIONS).filter((f) => f.endsWith(".mp4"))
    : [];
  processDir("actions", ACTIONS, actionVideos);

  console.log("Готово.");
}

main();
