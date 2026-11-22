import React from 'react';
import {AbsoluteFill, Audio, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig, spring, interpolate} from 'remotion';

// RIYIO reference style — see docs/REFERENCE_STYLE.md
type CapWord = {w: string; s: number; e: number};
type Caption = {start: number; end: number; words: CapWord[]; color: string; italic: boolean; key: number; stroke: number; punch: boolean};
export type JuraijProps = {
  hook: string;            // white top banner title (whole video)
  hookQuestion: string;    // first caption at 0s
  dialogueSrc: string;
  dialogueFrames: number;  // phase 1 length (ends on the first kick after the punch word)
  dropFrame: number;       // punch word start = beat drop
  actionClips: string[];
  actionFrames: number[];
  endFrames: number;
  captions: Caption[];
  bedSrc: string;
  bedVolume: number;
  dropSrc: string;
  dropTrimBefore: number;
  hitSrc: string;
  whooshSrc: string;
  durationInFrames: number;
};

const SERIF = '"Playfair Display", "P052", "Liberation Serif", "Nimbus Roman", "Times New Roman", serif';
const CURSIVE = '"Z003", "URW Chancery L", "Brush Script MT", cursive';

const ActionClip: React.FC<{src: string}> = ({src}) => {
  const frame = useCurrentFrame();
  const zoom = interpolate(frame, [0, 10], [1.1, 1.0], {extrapolateRight: 'clamp'});
  const flash = interpolate(frame, [0, 3], [0.6, 0], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill>
      <OffthreadVideo src={staticFile(src)} muted style={{width: '100%', height: '100%', transform: `scale(${zoom})`}} />
      {flash > 0 && <AbsoluteFill style={{backgroundColor: '#fff', opacity: flash}} />}
    </AbsoluteFill>
  );
};

const CaptionView: React.FC<{c: Caption; t: number; frame: number; fps: number}> = ({c, t, frame, fps}) => {
  const startF = Math.round(c.start * fps);
  const pop = spring({frame: frame - startF, fps, config: {damping: 12, stiffness: 260}, durationInFrames: 6});
  const scale = 1.2 - 0.2 * pop;
  const glow = `0 0 15px ${c.color}, 0 0 4px ${c.color}, 0 4px 10px rgba(0,0,0,0.95), 0 1px 2px #000`;
  const shake = c.punch ? `translate(${Math.sin(frame * 2.3) * 5}px, ${Math.cos(frame * 3.1) * 4}px)` : '';
  return (
    <div style={{
      position: 'absolute', top: '52%', left: 50, right: 50, textAlign: 'center',
      transform: `scale(${scale}) ${shake}`, zIndex: 25, lineHeight: 1.1,
      fontFamily: SERIF, fontWeight: 800, fontSize: c.punch ? 104 : 60, letterSpacing: 1.5,
      fontStyle: c.italic ? 'italic' : 'normal',
    }}>
      {c.words.map((w, i) => {
        const spoken = t >= w.s - 0.04;
        const isKey = i === c.key && c.words.length > 1;
        const isStroke = i === c.stroke;
        const text = c.italic ? w.w : w.w.toUpperCase();
        return (
          <span key={i} style={{
            opacity: spoken ? 1 : 0,
            color: isStroke ? 'transparent' : (c.punch ? '#F43F5E' : isKey ? c.color : '#FFFFFF'),
            WebkitTextStroke: isStroke ? '2.5px #EF4444' : undefined,
            textShadow: isStroke ? '0 0 12px rgba(239,68,68,0.8)' : glow,
            marginRight: 16, display: 'inline-block',
          }}>{text}</span>
        );
      })}
    </div>
  );
};

export const JuraijEdit: React.FC<JuraijProps> = (p) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  const D = p.dialogueFrames;
  const flashLen = 4;

  // montage cut layout right after phase 1
  let cursor = D;
  const seqs = p.actionClips.map((src, i) => {
    const len = Math.max(1, Math.round(p.actionFrames[i] || 0.45 * fps));
    const from = cursor;
    cursor += len;
    return {src, from, len};
  });
  const endFrom = cursor;
  const inDialogue = frame < D;
  const inEnd = frame >= endFrom;

  // hook question = first caption at 0s
  const firstCap = p.captions.length ? p.captions[0].start : 2;
  const hqEnd = Math.min(2.6, Math.max(1.3, firstCap));
  const showHQ = t < hqEnd && !!p.hookQuestion;
  const cap = inDialogue && !showHQ ? p.captions.find((c) => t >= c.start && t < c.end) : undefined;

  // small cursive watermark fades in/out
  const wmCycle = (frame % (8 * fps)) / fps;
  const wmOpacity = interpolate(wmCycle, [0, 1, 4, 5, 8], [0, 0.55, 0.55, 0, 0], {extrapolateRight: 'clamp'});

  const endF = frame - endFrom;
  const endPop = spring({frame: endF, fps, config: {damping: 14}});

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
          <ActionClip src={s.src} />
        </Sequence>
      ))}

      {/* Drop flash on the punch word */}
      {frame >= p.dropFrame && frame < p.dropFrame + flashLen && (
        <AbsoluteFill style={{backgroundColor: '#fff', zIndex: 30,
          opacity: interpolate(frame - p.dropFrame, [0, flashLen], [1, 0])}} />
      )}

      {/* End card */}
      {inEnd && (
        <AbsoluteFill style={{backgroundColor: '#050505', alignItems: 'center', justifyContent: 'center', zIndex: 26}}>
          <div style={{
            fontFamily: SERIF, fontWeight: 800, fontSize: 84, color: '#fff', letterSpacing: 6,
            textShadow: '0 0 18px #fff, 0 0 42px #38BDF8, 0 0 80px #38BDF8',
            transform: `scale(${0.85 + 0.15 * endPop})`, opacity: endPop,
          }}>MADE BY RIYIO</div>
        </AbsoluteFill>
      )}

      {/* White top hook banner, black bold title — whole video */}
      {!inEnd && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: '10%', background: '#FFFFFF',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 20,
        }}>
          <span style={{color: '#000', fontSize: 54, fontWeight: 800, fontFamily: SERIF, padding: '0 30px', textAlign: 'center'}}>
            “{p.hook}”
          </span>
        </div>
      )}

      {/* Hook question (first caption) */}
      {showHQ && (
        <CaptionView c={{start: 0, end: hqEnd, words: p.hookQuestion.split(' ').map((w) => ({w, s: 0, e: hqEnd})),
          color: '#F43F5E', italic: false, key: -1, stroke: -1, punch: false}} t={t} frame={frame} fps={fps} />
      )}

      {/* Word-synced captions (phase 1 only) */}
      {cap ? <CaptionView c={cap} t={t} frame={frame} fps={fps} /> : null}

      {/* Small RIYIO watermark */}
      {!inEnd && (
        <div style={{
          position: 'absolute', bottom: 70, right: 60, color: '#fff', fontSize: 40, fontFamily: CURSIVE,
          opacity: wmOpacity, textShadow: '0 0 10px rgba(255,255,255,0.8)', zIndex: 15,
        }}>Riyio</div>
      )}

      {/* Audio: dark bed ducked ~-11dB under dialogue -> drop at 0dB on the punch word */}
      {p.bedSrc ? (
        <Sequence from={0} durationInFrames={Math.max(1, p.dropFrame + 3)}>
          <Audio src={staticFile(p.bedSrc)}
            volume={(f) => p.bedVolume * interpolate(f, [0, 15, Math.max(16, p.dropFrame - 2), Math.max(17, p.dropFrame + 3)], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})} />
        </Sequence>
      ) : null}
      {p.dropSrc ? (
        <Sequence from={p.dropFrame}>
          <Audio src={staticFile(p.dropSrc)} trimBefore={Math.max(0, p.dropTrimBefore)}
            volume={(f) => interpolate(f + p.dropFrame, [durationInFrames - fps, durationInFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})} />
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
      {p.whooshSrc ? (
        <Sequence from={Math.max(0, endFrom - 8)} durationInFrames={14}>
          <Audio src={staticFile(p.whooshSrc)} volume={0.5} />
        </Sequence>
      ) : null}
    </AbsoluteFill>
  );
};
