import React from 'react';
import {AbsoluteFill, Audio, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig, spring, interpolate} from 'remotion';

type Word = {word: string; s: number; e: number};
export type JuraijProps = {
  hook: string;
  dialogueSrc: string;
  dialogueFrames: number;
  actionClips: string[];
  actionFrames: number[];
  words: Word[];
  songSrc: string;
  songTrimBefore: number; // frames trimmed off song start so its beat drop lands on beatDropFrame
  songDelay: number; // frames to wait before song starts (if drop is earlier in song than dialogue end)
  beatDropFrame: number; // == dialogueFrames (exact end of dialogue)
  durationInFrames: number;
};

const COLORS = ['#38BDF8', '#FB923C', '#F43F5E', '#FACC15', '#34D399', '#FFFFFF'];

// One beat-synced action clip with a spring zoom punch 1.0x -> 1.12x.
const ActionClip: React.FC<{src: string}> = ({src}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const punch = spring({frame, fps, config: {damping: 14, stiffness: 220}});
  const zoom = 1 + 0.12 * punch;
  return (
    <OffthreadVideo src={staticFile(src)} muted
      style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${zoom})`}} />
  );
};

export const JuraijEdit: React.FC<JuraijProps> = ({
  hook, dialogueSrc, dialogueFrames, actionClips, actionFrames, words,
  songSrc, songTrimBefore, songDelay, beatDropFrame,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const drop = beatDropFrame || dialogueFrames;
  const t = frame / fps;
  // Hook bar: first 6s only (short fade in the last 0.3s)
  const barOpacity = interpolate(frame, [0, 5.7 * fps, 6 * fps], [1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const flashFrames = Math.max(1, Math.round(0.12 * fps));

  // action sequences laid back-to-back right after the drop
  let cursor = drop;
  const seqs = actionClips.map((src, i) => {
    const len = Math.max(1, Math.round(actionFrames[i] || 0.6 * fps));
    const from = cursor;
    cursor += len;
    return {src, from, len};
  });

  const activeWord = frame < dialogueFrames ? words.findIndex((w) => t >= w.s && t <= w.e) : -1;

  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      {/* Dialogue build-up: original dialogue at 1.0 */}
      {dialogueSrc && dialogueFrames > 0 ? (
        <Sequence from={0} durationInFrames={dialogueFrames}>
          <OffthreadVideo src={staticFile(dialogueSrc)} volume={1}
            style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        </Sequence>
      ) : null}

      {/* Beat-drop action cuts (dialogue muted, music only) */}
      {seqs.map((s, i) => (
        <Sequence key={i} from={s.from} durationInFrames={s.len}>
          <ActionClip src={s.src} />
        </Sequence>
      ))}

      {/* 0.12s crisp white flash on the drop */}
      {frame >= drop && frame < drop + flashFrames && (
        <AbsoluteFill style={{backgroundColor: '#fff', zIndex: 30}} />
      )}

      {/* Top hook bar - first 6s */}
      {barOpacity > 0.01 && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: '8%',
          background: '#FFFFFF', opacity: barOpacity,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 20, boxShadow: '0 6px 16px rgba(0,0,0,0.35)',
        }}>
          <span style={{color: '#000', fontSize: 44, fontWeight: 800, fontFamily: 'sans-serif'}}>
            "{hook}"
          </span>
        </div>
      )}

      {/* Word-by-word captions, synced to whisper word timestamps */}
      {activeWord >= 0 && (() => {
        const w = words[activeWord];
        const color = COLORS[activeWord % COLORS.length];
        return (
          <div style={{
            position: 'absolute', bottom: '18%', left: 40, right: 40,
            textAlign: 'center', color, fontSize: 64, fontWeight: 900,
            textShadow: `0 0 22px ${color}, 0 0 8px ${color}, 0 6px 14px #000, 0 2px 4px #000`,
            fontFamily: 'sans-serif', letterSpacing: 1.2, zIndex: 25,
          }}>
            {w.word.toUpperCase()}
          </div>
        );
      })()}

      {/* RIYIO watermark */}
      <div style={{
        position: 'absolute', bottom: 36, left: 0, right: 0, textAlign: 'center',
        color: '#fff', fontSize: 30, fontFamily: 'serif', opacity: 0.75,
        textShadow: '0 0 14px #fff', zIndex: 15,
      }}>
        RIYIO
      </div>

      {/* Song: ducked 0.25 under dialogue, slams to 1.0 on the drop */}
      {songSrc ? (
        <Sequence from={Math.max(0, songDelay || 0)}>
          <Audio src={staticFile(songSrc)} trimBefore={Math.max(0, songTrimBefore || 0)}
            volume={(f) => (f + Math.max(0, songDelay || 0) >= drop ? 1 : 0.25)} />
        </Sequence>
      ) : null}
    </AbsoluteFill>
  );
};
