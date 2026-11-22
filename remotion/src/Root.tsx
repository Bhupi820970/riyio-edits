import {Composition, CalculateMetadataFunction} from 'remotion';
import {JuraijEdit, JuraijProps} from './JuraijEdit';

// Total length = exact sum of dialogue + montage frames (no end card) (computed by run_v2.py from ffprobe).
const calculateMetadata: CalculateMetadataFunction<JuraijProps> = ({props}) => {
  const sum = (props.dialogueFrames || 0) + (props.actionFrames || []).reduce((a, b) => a + b, 0) ;
  return {durationInFrames: Math.max(1, props.durationInFrames || sum)};
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="JuraijEdit"
      component={JuraijEdit}
      calculateMetadata={calculateMetadata}
      durationInFrames={1}
      fps={30}
      width={1080}
      height={1350}
      defaultProps={{
        hook: "",
        hookQuestion: "",
        dialogueSrc: "",
        dialogueFrames: 0,
        dropFrame: 0,
        actionClips: [],
        actionFrames: [],
        captions: [],
        captionFont: "anton",
        captionLook: "shadow",
        bedSrc: "",
        bedVolume: 0.28,
        dropSrc: "",
        picture: {x: 0, y: 0, w: 1080, h: 1350},
        wmSize: 40,
        hitSrc: "",
        whooshSrc: "",
        durationInFrames: 0,
      }}
    />
  );
};
