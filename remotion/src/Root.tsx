import {Composition, CalculateMetadataFunction} from 'remotion';
import {JuraijEdit, JuraijProps} from './JuraijEdit';

// Total length = exact sum of dialogue + action clip frames (sent by run_v2.py from ffprobe).
const calculateMetadata: CalculateMetadataFunction<JuraijProps> = ({props}) => {
  const sum = (props.dialogueFrames || 0) + (props.actionFrames || []).reduce((a, b) => a + b, 0);
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
        hook: "Winter is finally here",
        dialogueSrc: "",
        dialogueFrames: 0,
        actionClips: [],
        actionFrames: [],
        words: [],
        songSrc: "",
        songTrimBefore: 0,
        songDelay: 0,
        beatDropFrame: 0,
        durationInFrames: 0,
      }}
    />
  );
};
