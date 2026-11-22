import {Composition} from 'remotion';
import {JuraijEdit} from './JuraijEdit';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="JuraijEdit"
      component={JuraijEdit}
      durationInFrames={900}
      fps={30}
      width={1080}
      height={1350}
      defaultProps={{
        hook: "Winter is finally here",
        dialogueSrc: "",
        actionClips: [],
        words: [],
        songSrc: "",
        beatDropFrame: 180,
      }}
    />
  );
};
