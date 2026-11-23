import React from 'react';
import {AbsoluteFill, Audio, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig, spring, interpolate, delayRender, continueRender} from 'remotion';

// RIYIO reference style — see docs/REFERENCE_STYLE.md
// Captions: speaker-side styles adapted from pro-edit (caption_patterns.py P01-P15 + vicestyle.py) and R00 glow.

type CapWord = {t: string; c: string; size: number; s: number};
type CapLine = {h: number; sp: number; words: CapWord[]};
type CapEvent = {start: number; end: number; x: number; y: number; w: number; h: number; pad: number;
  align: 'left' | 'right' | 'center'; zone: string; punch: boolean; lines: CapLine[]};
type Rect = {x: number; y: number; w: number; h: number};
export type JuraijProps = {
  hook: string;            // white top banner title (whole video)
  hookQuestion: string;    // first caption at 0s
  dialogueSrc: string;
  dialogueFrames: number;  // phase 1 ends when the punch word ends (character goes quiet)
  dropFrame: number;       // punch word start = beat drop
  actionClips: string[];
  actionFrames: number[];
  actionKinds?: string[];  // flurry | beat | hero
  captions: CapEvent[];
  captionFont: 'anton' | 'playfair';
  captionLook: 'shadow' | 'glow';
  bedSrc: string;
  bedVolume: number;
  dropSrc: string;
  hitSrc: string;
  whooshSrc: string;
  picture: Rect;           // movie picture inside the 4:5 frame
  wmSize: number;
  durationInFrames: number;
};

// Bundled OFL fonts (remotion/public/fonts) so the runner always has them.
const FONT_FACES: [string, string, FontFaceDescriptors][] = [
  ['RiyioAnton', 'fonts/Anton-Regular.ttf', {weight: '400'}],
  ['RiyioPlayfair', 'fonts/PlayfairDisplay.ttf', {weight: '400 900'}],
  ['RiyioPlayfair', 'fonts/PlayfairDisplay-Italic.ttf', {weight: '400 900', style: 'italic'}],
];
if (typeof document !== 'undefined') {
  const handle = delayRender('riyio-fonts');
  Promise.all(FONT_FACES.map(([fam, file, desc]) => new FontFace(fam, `url('${staticFile(file)}')`, desc).load()))
    .then((faces) => { faces.forEach((f) => (document.fonts as unknown as {add: (x: FontFace) => void}).add(f)); continueRender(handle); })
    .catch((e) => { console.error('font load failed', e); continueRender(handle); });
}
const FONT = {anton: '"RiyioAnton", "Anton", Impact, sans-serif', playfair: '"RiyioPlayfair", "Playfair Display", "P052", serif'};

const ActionClip: React.FC<{src: string; kind?: string}> = ({src, kind}) => {
  const frame = useCurrentFrame();
  // hard cuts on the beat (Skywalker style): punch-in on every cut, white flash only on hero shots
  const zoom = kind === 'hero'
    ? interpolate(frame, [0, 90], [1.0, 1.08], {extrapolateRight: 'clamp'})
    : interpolate(frame, [0, 6], [1.08, 1.0], {extrapolateRight: 'clamp'});
  const flash = kind === 'hero' ? interpolate(frame, [0, 3], [0.5, 0], {extrapolateRight: 'clamp'}) : 0;
  return (
    <AbsoluteFill>
      <OffthreadVideo src={staticFile(src)} muted style={{width: '100%', height: '100%', transform: `scale(${zoom})`}} />
      {flash > 0 && <AbsoluteFill style={{backgroundColor: '#fff', opacity: flash}} />}
    </AbsoluteFill>
  );
};

const Caption: React.FC<{ev: CapEvent; t: number; frame: number; fps: number; font: string; look: string}> = ({ev, t, frame, fps, font, look}) => {
  const f0 = Math.round(ev.start * fps);
  const glow = look === 'glow';
  // pro-edit pop 80% -> 100% (shadow looks); reference glow pops 1.2 -> 1.0
  const pop = spring({frame: frame - f0, fps, config: {damping: 13, stiffness: 280}, durationInFrames: glow ? 6 : 5});
  const scale = glow ? 1.2 - 0.2 * pop : 0.8 + 0.2 * pop;
  const shake = ev.punch ? `translate(${Math.sin(frame * 2.3) * 5}px, ${Math.cos(frame * 3.1) * 4}px)` : '';
  const origin = ev.align === 'left' ? 'left center' : ev.align === 'right' ? 'right center' : 'center';
  return (
    <div style={{position: 'absolute', left: ev.x, top: ev.y, width: ev.w, height: ev.h, padding: ev.pad, boxSizing: 'border-box',
      transform: `scale(${scale}) ${shake}`, transformOrigin: origin, zIndex: 25,
      display: 'flex', flexDirection: 'column', gap: 6, justifyContent: 'center'}}>
      {ev.lines.map((ln, li) => (
        <div key={li} style={{display: 'flex', alignItems: 'baseline', gap: ln.sp, height: ln.h,
          justifyContent: ev.align === 'left' ? 'flex-start' : ev.align === 'right' ? 'flex-end' : 'center'}}>
          {ln.words.map((w, wi) => {
            const spoken = t >= w.s - 0.04; // word-level reveal = lip sync
            const off = Math.max(3, Math.round(w.size / 16));
            const style: React.CSSProperties = glow
              ? {color: w.c, textShadow: `0 0 15px ${w.c}, 0 0 5px ${w.c}, 0 4px 10px rgba(0,0,0,0.95)`, fontWeight: 800}
              : {color: w.c, WebkitTextStroke: `${Math.max(2, Math.round(w.size / 28))}px #000`, paintOrder: 'stroke fill',
                 textShadow: `${off}px ${off}px 0 rgba(0,0,0,0.92)`};
            return (
              <span key={wi} style={{...style, fontFamily: font, fontSize: w.size, lineHeight: 1, whiteSpace: 'nowrap',
                opacity: spoken ? 1 : 0}}>{w.t}</span>
            );
          })}
        </div>
      ))}
    </div>
  );
};

export const JuraijEdit: React.FC<JuraijProps> = (p) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  const D = p.dialogueFrames;
  const font = FONT[p.captionFont] || FONT.anton;
  const pic = p.picture || {x: 0, y: 0, w: 1080, h: 1350};

  // montage cut layout right after phase 1 (no end card)
  let cursor = D;
  const seqs = p.actionClips.map((src, i) => {
    const len = Math.max(1, Math.round(p.actionFrames[i] || 0.45 * fps));
    const from = cursor;
    cursor += len;
    return {src, from, len};
  });
  const inDialogue = frame < D;

  // hook question = first caption at 0s (until the first spoken word)
  const firstCap = p.captions.length ? p.captions[0].start : 1;
  const hqEnd = Math.min(1.0, Math.max(0.5, firstCap));
  const showHQ = t < hqEnd && !!p.hookQuestion;
  const cap = inDialogue ? p.captions.find((c) => t >= c.start && t < c.end) : undefined;

  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      {/* Phase 1: continuous dialogue scene (pre-graded, no crop, blurred fill) */}
      {p.dialogueSrc && D > 0 ? (
        <Sequence from={0} durationInFrames={D}>
          <OffthreadVideo src={staticFile(p.dialogueSrc)} volume={1} style={{width: '100%', height: '100%'}} />
        </Sequence>
      ) : null}

      {/* Phase 2: beat-synced montage, music only */}
      {seqs.map((s, i) => (
        <Sequence key={i} from={s.from} durationInFrames={s.len}>
          <ActionClip src={s.src} kind={(p.actionKinds || [])[i]} />
        </Sequence>
      ))}

      {/* Drop flash on the punch word */}
      {frame >= p.dropFrame && frame < p.dropFrame + 4 && (
        <AbsoluteFill style={{backgroundColor: '#fff', zIndex: 30,
          opacity: interpolate(frame - p.dropFrame, [0, 4], [1, 0])}} />
      )}

      {/* White top hook banner, black bold title — whole video */}
      <div style={{position: 'absolute', top: 0, left: 0, right: 0, height: '10%', background: '#FFFFFF',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 20}}>
        <span style={{color: '#000', fontSize: 54, fontWeight: 800, fontFamily: FONT.playfair, padding: '0 30px', textAlign: 'center'}}>
          “{p.hook}”
        </span>
      </div>

      {/* Hook question (first caption) */}
      {showHQ && (
        <div style={{position: 'absolute', left: 60, right: 60, top: pic.y + pic.h * 0.5 - 50, textAlign: 'center', zIndex: 25,
          fontFamily: font, fontSize: 64, fontWeight: 800, color: '#fff', lineHeight: 1.05,
          WebkitTextStroke: p.captionLook === 'glow' ? undefined : '2px #000', paintOrder: 'stroke fill',
          textShadow: p.captionLook === 'glow' ? '0 0 15px #F43F5E, 0 4px 10px #000' : '4px 4px 0 rgba(0,0,0,0.92)'}}>
          {p.hookQuestion.toUpperCase()}
        </div>
      )}

      {/* Word-synced, speaker-side captions (phase 1 only) */}
      {cap && !showHQ ? <Caption ev={cap} t={t} frame={frame} fps={fps} font={font} look={p.captionLook} /> : null}

      {/* RIYIO watermark INSIDE the picture: small bold condensed sans, white ~65%, bottom-center (VICE CARTEL look) */}
      <div style={{position: 'absolute', left: pic.x, width: pic.w, top: pic.y + pic.h - pic.h * 0.055 - p.wmSize,
        height: p.wmSize * 1.2, textAlign: 'center', zIndex: 18, fontFamily: FONT.anton, fontSize: p.wmSize,
        lineHeight: 1.2, letterSpacing: 1, color: 'rgba(255,255,255,0.65)', textShadow: '1px 2px 3px rgba(0,0,0,0.25)'}}>
        RIYIO
      </div>

      {/* Audio: dark bed ~-11 dB under the whole dialogue -> drop at 0 dB exactly on the punch word */}
      {p.bedSrc ? (
        <Sequence from={0} durationInFrames={Math.max(1, p.dropFrame + 3)}>
          <Audio src={staticFile(p.bedSrc)}
            volume={(f) => p.bedVolume * interpolate(f, [0, Math.max(1, p.dropFrame), Math.max(2, p.dropFrame + 3)], [1, 1, 0], {extrapolateRight: 'clamp'})} />
        </Sequence>
      ) : null}
      {p.dropSrc ? (
        <Sequence from={p.dropFrame}>
          <Audio src={staticFile(p.dropSrc)}
            volume={(f) => interpolate(f + p.dropFrame, [durationInFrames - 6, durationInFrames], [1, 0.6], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})} />
        </Sequence>
      ) : null}
      {p.hitSrc ? (
        <Sequence from={p.dropFrame} durationInFrames={21}>
          <Audio src={staticFile(p.hitSrc)} volume={0.9} />
        </Sequence>
      ) : null}
      {p.whooshSrc ? seqs.filter((_, i) => i % 3 === 2).map((s, i) => (
        <Sequence key={`w${i}`} from={Math.max(0, s.from - 6)} durationInFrames={14}>
          <Audio src={staticFile(p.whooshSrc)} volume={0.35} />
        </Sequence>
      )) : null}
    </AbsoluteFill>
  );
};
