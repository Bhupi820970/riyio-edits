import React from 'react';
import {AbsoluteFill, staticFile, Audio, Img, Sequence, useCurrentFrame, useVideoConfig, spring, interpolate} from 'remotion';

type Word = {word: string; s: number; e: number};
type Props = {
  hook: string;
  dialogueSrc: string;
  actionClips: string[];
  words: Word[];
  songSrc: string;
  beatDropFrame: number;
};

const COLORS = ['#ffffff', '#00eeff', '#ffaa44', '#00ffaa', '#ff66aa'];

export const JuraijEdit: React.FC<Props> = ({hook, dialogueSrc, actionClips, words, songSrc, beatDropFrame}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const isDrop = frame >= beatDropFrame;
  const zoom = isDrop ? spring({frame: frame - beatDropFrame, fps, config: {damping: 12}}) * 0.1 + 1 : 1;

  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      {/* Top hook bar */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: '7%',
        background: 'rgba(255,255,255,0.92)',
        boxShadow: '0 8px 20px rgba(0,0,0,0.4)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 10,
      }}>
        <span style={{color: '#000', fontSize: 42, fontWeight: 800, fontFamily: 'sans-serif'}}>
          "{hook}"
        </span>
      </div>

      {/* Dialogue or action */}
      {!isDrop && dialogueSrc ? (
        <Sequence from={0}>
          <Img src={dialogueSrc ? staticFile(dialogueSrc) : undefined} style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${zoom})`}} />
        </Sequence>
      ) : null}
      {isDrop && actionClips.map((src, i) => (
        <Sequence key={i} from={beatDropFrame + i * 18} durationInFrames={18}>
          <Img src={src ? staticFile(src) : undefined} style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${zoom})`}} />
        </Sequence>
      ))}

      {/* Word captions */}
      {words.map((w, i) => {
        const start = Math.floor(w.s * fps);
        const end = Math.floor(w.e * fps);
        if (frame < start || frame > end) return null;
        const color = COLORS[i % COLORS.length];
        return (
          <div key={i} style={{
            position: 'absolute', bottom: '22%', left: 0, right: 0,
            textAlign: 'center', color, fontSize: 52, fontWeight: 900,
            textShadow: `0 0 18px ${color}, 0 2px 8px #000`,
            fontFamily: 'sans-serif', letterSpacing: 1,
          }}>
            {w.word.toUpperCase()}
          </div>
        );
      })}

      {/* RIYIO watermark */}
      <div style={{
        position: 'absolute', bottom: 40, left: 0, right: 0, textAlign: 'center',
        color: '#fff', fontSize: 28, fontFamily: 'serif', opacity: 0.7,
        textShadow: '0 0 12px #fff',
      }}>
        RIYIO
      </div>

      {/* Audio */}
      {songSrc && <Audio src={songSrc ? staticFile(songSrc) : undefined} volume={isDrop ? 1 : 0.25} />}
    </AbsoluteFill>
  );
};
