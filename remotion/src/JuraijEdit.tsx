import React from 'react';
import {AbsoluteFill, Audio, Img, Sequence, staticFile, useCurrentFrame, useVideoConfig, spring, interpolate} from 'remotion';

type Word = {word: string; s: number; e: number};
type Props = {
  hook: string;
  dialogueSrc: string;
  actionClips: string[];
  words: Word[];
  songSrc: string;
  beatDropFrame: number;
};

const COLORS = ['#38BDF8', '#FB923C', '#F43F5E', '#FACC15', '#34D399', '#FFFFFF'];

export const JuraijEdit: React.FC<Props> = ({hook, dialogueSrc, actionClips, words, songSrc, beatDropFrame}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const isDrop = frame >= beatDropFrame;
  const barOpacity = interpolate(frame, [0, 6*fps, 7*fps], [1, 1, 0], {extrapolateRight: 'clamp'});
  const zoom = isDrop ? spring({frame: frame - beatDropFrame, fps, config: {damping: 14}}) * 0.12 + 1 : 1;

  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
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

      {/* Dialogue build-up */}
      {!isDrop && dialogueSrc ? (
        <Img src={staticFile(dialogueSrc)} style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${zoom})`}} />
      ) : null}

      {/* Beat-drop action cuts */}
      {isDrop && actionClips.map((src, i) => (
        <Sequence key={i} from={beatDropFrame + i * 20} durationInFrames={20}>
          <Img src={staticFile(src)} style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${zoom})`}} />
        </Sequence>
      ))}

      {/* White flash on drop */}
      {isDrop && frame < beatDropFrame + 4 && (
        <AbsoluteFill style={{backgroundColor: '#fff', opacity: 0.9}} />
      )}

      {/* Word captions */}
      {words.map((w, i) => {
        const start = Math.floor(w.s * fps);
        const end = Math.floor(w.e * fps);
        if (frame < start || frame > end) return null;
        const color = COLORS[i % COLORS.length];
        return (
          <div key={i} style={{
            position: 'absolute', bottom: '18%', left: 40, right: 40,
            textAlign: 'center', color, fontSize: 56, fontWeight: 900,
            textShadow: `0 0 22px ${color}, 0 4px 12px #000`,
            fontFamily: 'sans-serif', letterSpacing: 1.2,
          }}>
            {w.word.toUpperCase()}
          </div>
        );
      })}

      {/* RIYIO watermark */}
      <div style={{
        position: 'absolute', bottom: 36, left: 0, right: 0, textAlign: 'center',
        color: '#fff', fontSize: 30, fontFamily: 'serif', opacity: 0.75,
        textShadow: '0 0 14px #fff', zIndex: 15,
      }}>
        RIYIO
      </div>

      {/* Audio */}
      {songSrc ? <Audio src={staticFile(songSrc)} volume={isDrop ? 1 : 0.25} /> : null}
    </AbsoluteFill>
  );
};
