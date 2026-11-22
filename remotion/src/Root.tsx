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
      height={1920}
      defaultProps={{
        hook: "She read him cold",
        dialogueSrc: "",
        actionClips: [],
        words: [],
        songSrc: "",
        beatDropFrame: 600,
      }}
    />
  );
};
