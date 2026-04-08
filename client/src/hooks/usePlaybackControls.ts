import { useState } from 'react';

const PLAYBACK_SPEEDS = [0.25, 0.5, 1, 2, 4, 8, 16];

export function usePlaybackControls(
  currentFrame: number,
  totalFrames: number,
  totalLaps: number,
  lapFrameIndices: number[],
  playbackSpeed: number,
  onSpeedChange: (speed: number) => void,
  onSeek: (frame: number) => void,
  onSeekToLap: (lap: number) => void,
) {
  const [lapInputValue, setLapInputValue] = useState('');

  const currentLap = lapFrameIndices.length > 0
    ? getCurrentLap(currentFrame, lapFrameIndices)
    : null;

  const progress = totalFrames > 0 ? (currentFrame / totalFrames) * 100 : 0;

  const handleSpeedIncrease = () => {
    const i = PLAYBACK_SPEEDS.indexOf(playbackSpeed);
    if (i < PLAYBACK_SPEEDS.length - 1) onSpeedChange(PLAYBACK_SPEEDS[i + 1]);
  };

  const handleSpeedDecrease = () => {
    const i = PLAYBACK_SPEEDS.indexOf(playbackSpeed);
    if (i > 0) onSpeedChange(PLAYBACK_SPEEDS[i - 1]);
  };

  const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const percent = (e.clientX - rect.left) / rect.width;
    onSeek(Math.floor(percent * totalFrames));
  };

  const commitLap = (raw: string) => {
    const n = parseInt(raw, 10);
    if (!isNaN(n)) onSeekToLap(n);
    setLapInputValue('');
  };

  const handlePrevLap = () => { if (currentLap) onSeekToLap(currentLap - 1); };
  const handleNextLap = () => { if (currentLap) onSeekToLap(currentLap + 1); };

  const canDecreaseLap = currentLap !== null && currentLap > 1;
  const canIncreaseLap = currentLap !== null && currentLap < totalLaps;
  const canDecreaseSpeed = playbackSpeed === PLAYBACK_SPEEDS[0];
  const canIncreaseSpeed = playbackSpeed === PLAYBACK_SPEEDS[PLAYBACK_SPEEDS.length - 1];

  return {
    currentLap,
    progress,
    lapInputValue,
    setLapInputValue,
    commitLap,
    handleSpeedIncrease,
    handleSpeedDecrease,
    handleProgressClick,
    handlePrevLap,
    handleNextLap,
    canDecreaseLap,
    canIncreaseLap,
    canDecreaseSpeed,
    canIncreaseSpeed,
  };
}

function getCurrentLap(frameIdx: number, lapFrameIndices: number[]): number {
  let lap = 1;
  for (let i = 0; i < lapFrameIndices.length; i++) {
    if (frameIdx >= lapFrameIndices[i]) lap = i + 1;
    else break;
  }
  return lap;
}
