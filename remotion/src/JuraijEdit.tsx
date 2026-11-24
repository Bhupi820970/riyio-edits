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
  hook: string;            // white top banner title (whole video). No opening question caption (removed Nov 24).
  // pro-edit timeline: intro montage -> dialogue (music ducked) -> drop on the punch word -> montage
  introClips?: string[];   // opening beat-cut montage, music at full level
  introFrames?: number[];
  dialogueSrc: string;
  dialogueFrom?: number;   // frame where the dialogue starts (= sum of introFrames)
  dialogueFrames: number;  // dialogue ends when the punch word ends (character goes quiet)
  dropFrame: number;       // absolute frame of the punch word start = beat drop
  actionClips: string[];   // post-drop montage
  actionFrames: number[];
  actionKinds?: string[];  // flurry | beat
  musicSrc?: string;       // one song for the whole video (drop beat on dropFrame)
  captions: CapEvent[];
  captionFont: 'anton' | 'playfair';
  captionLook: 'shadow' | 'glow';
  bedSrc: string;
  bedVolume: number;
  dropSrc: string;
  hitSrc: string;
  whooshSrc: string;
  hitFrames?: number[];    // hit SFX on the strongest cuts (drop + hero shots)
  whooshFrames?: number[]; // whoosh just before each hero cut
  picture: Rect;           // movie picture inside the 4:5 frame
  wmSize: number;
  wmOpacity?: number;      // glass-like RIYIO mark (~0.3)
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
  // pro-edit hard cuts on the beat with a slight 1.04 crop-in; the post-drop flurry gets a quick punch-in
  const zoom = kind === 'flurry'
    ? interpolate(frame, [0, 5], [1.1, 1.04], {extrapolateRight: 'clamp'})
    : 1.04;
  const flash = 0;
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
  const DF = p.dialogueFrom || 0;
  const D = p.dialogueFrames;
  const font = FONT[p.captionFont] || FONT.anton;
  const pic = p.picture || {x: 0, y: 0, w: 1080, h: 1350};

  // intro montage from frame 0, dialogue at DF, post-drop montage right after the dialogue (no end card)
  let icur = 0;
  const intro = (p.introClips || []).map((src, i) => {
    const len = Math.max(1, Math.round((p.introFrames || [])[i] || 0.45 * fps));
    const from = icur;
    icur += len;
    return {src, from, len};
  });
  let cursor = DF + D;
  const seqs = p.actionClips.map((src, i) => {
    const len = Math.max(1, Math.round(p.actionFrames[i] || 0.45 * fps));
    const from = cursor;
    cursor += len;
    return {src, from, len};
  });
  const inDialogue = frame >= DF && frame < DF + D;
  const tRel = (frame - DF) / fps;   // caption times are relative to the dialogue clip

  // captions only during the dialogue (no opening question / hook caption over the intro)
  const cap = inDialogue ? p.captions.find((c) => tRel >= c.start && tRel < c.end) : undefined;

  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      {/* Intro: beat-synced montage, music at full level */}
      {intro.map((s, i) => (
        <Sequence key={`i${i}`} from={s.from} durationInFrames={s.len}>
          <ActionClip src={s.src} kind="beat" />
        </Sequence>
      ))}

      {/* Middle: continuous dialogue scene (pre-graded, no crop, blurred fill), music ducked */}
      {p.dialogueSrc && D > 0 ? (
        <Sequence from={DF} durationInFrames={D}>
          <OffthreadVideo src={staticFile(p.dialogueSrc)} volume={1} style={{width: '100%', height: '100%'}} />
        </Sequence>
      ) : null}

      {/* After the drop: fast beat-synced montage, music only, to the end */}
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

      {/* Word-synced, speaker-side captions (phase 1 only) */}
      {cap ? <Caption ev={cap} t={tRel} frame={frame - DF} fps={fps} font={font} look={p.captionLook} /> : null}

      {/* RIYIO watermark INSIDE the picture, bottom-center: small and glass-like (very transparent white,
          thin bright edge + soft glow, no hard shadow) so it reads but never pulls the eye */}
      <div style={{position: 'absolute', left: pic.x, width: pic.w, top: pic.y + pic.h - pic.h * 0.05 - p.wmSize,
        height: p.wmSize * 1.2, textAlign: 'center', zIndex: 18, fontFamily: FONT.anton, fontSize: p.wmSize,
        lineHeight: 1.2, letterSpacing: Math.max(1, Math.round(p.wmSize * 0.12)),
        color: `rgba(255,255,255,${p.wmOpacity ?? 0.3})`,
        WebkitTextStroke: `0.5px rgba(255,255,255,${Math.min(0.5, (p.wmOpacity ?? 0.3) * 0.7)})`,
        textShadow: `0 0 ${Math.max(3, Math.round(p.wmSize * 0.3))}px rgba(255,255,255,0.14), 0 1px 2px rgba(0,0,0,0.12)`}}>
        RIYIO
      </div>

      {/* Audio: one song the whole video — full in the intro, ducked (bedVolume ~-11 dB) under the dialogue,
          back to full exactly on the punch word (drop) and through the montage */}
      {p.musicSrc ? (
        <Audio src={staticFile(p.musicSrc)}
          volume={(f) => {
            const duck = p.bedVolume;
            const a = interpolate(f, [Math.max(0, DF - 6), Math.max(1, DF)], [1, duck], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
            const back = f >= p.dropFrame ? interpolate(f, [p.dropFrame, p.dropFrame + 2], [duck, 1], {extrapolateRight: 'clamp'}) : a;
            const tail = interpolate(f, [durationInFrames - 6, durationInFrames], [1, 0.6], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
            return (DF > 0 ? back : (f >= p.dropFrame ? 1 : duck)) * tail;
          }} />
      ) : null}
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
      {/* hit SFX on the drop + hero cuts (strongest shots), whoosh into each hero cut */}
      {p.hitSrc ? (p.hitFrames && p.hitFrames.length ? p.hitFrames : [p.dropFrame]).map((f, i) => (
        <Sequence key={`h${i}`} from={f} durationInFrames={21}>
          <Audio src={staticFile(p.hitSrc)} volume={f === p.dropFrame ? 0.9 : 0.55} />
        </Sequence>
      )) : null}
      {p.whooshSrc ? (p.whooshFrames || []).map((f, i) => (
        <Sequence key={`w${i}`} from={Math.max(0, f)} durationInFrames={14}>
          <Audio src={staticFile(p.whooshSrc)} volume={0.35} />
        </Sequence>
      )) : null}
    </AbsoluteFill>
  );
};
