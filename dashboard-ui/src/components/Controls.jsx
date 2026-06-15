// Controls.jsx - Playback Control Panel Component
import React from 'react';
import { Play, Pause, SkipForward, SkipBack, Shuffle, Repeat, Infinity } from 'lucide-react';

export default function Controls({
  status,
  loopMode,
  autoplay,
  onTogglePlay,
  onSkip,
  onPrevious,
  onShuffle,
  onLoopModeChange,
  onAutoplayChange
}) {
  const isPlaying = status === 'playing';

  // Loop mode states: 0 = Off, 1 = Repeat Track, 2 = Repeat Queue
  const getLoopModeLabel = () => {
    if (loopMode === 1) return 'Track';
    if (loopMode === 2) return 'Queue';
    return 'Off';
  };

  const cycleLoopMode = () => {
    const nextMode = (loopMode + 1) % 3;
    onLoopModeChange(nextMode);
  };

  return (
    <div className="bg-discord-card border border-white/5 rounded-lg p-6 flex flex-col gap-6 shadow-md">
      {/* Primary Media Command Row */}
      <div className="flex items-center justify-center gap-6">
        {/* Shuffle */}
        <button
          onClick={onShuffle}
          className="p-2.5 bg-discord-darkest-gray hover:bg-[#35373c] text-discord-text-muted hover:text-discord-text-primary rounded-md border border-white/5 transition-all duration-200 focus:outline-none"
          title="Shuffle Queue"
        >
          <Shuffle className="w-5 h-5" />
        </button>

        {/* Previous */}
        <button
          onClick={onPrevious}
          className="p-2.5 bg-discord-darkest-gray hover:bg-[#35373c] text-discord-text-muted hover:text-discord-text-primary rounded-md border border-white/5 transition-all duration-200 focus:outline-none"
          title="Previous Track"
        >
          <SkipBack className="w-5 h-5" />
        </button>

        {/* Play / Pause Toggle */}
        <button
          onClick={onTogglePlay}
          className="p-4 bg-discord-blurple hover:bg-discord-blurple-hover text-white rounded-full transition-all duration-200 focus:outline-none transform hover:scale-[1.04] active:scale-[0.96] shadow-md shadow-discord-blurple/10"
          title={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? <Pause className="w-6 h-6 fill-white" /> : <Play className="w-6 h-6 fill-white ml-0.5" />}
        </button>

        {/* Next / Skip */}
        <button
          onClick={onSkip}
          className="p-2.5 bg-discord-darkest-gray hover:bg-[#35373c] text-discord-text-muted hover:text-discord-text-primary rounded-md border border-white/5 transition-all duration-200 focus:outline-none"
          title="Skip Track"
        >
          <SkipForward className="w-5 h-5" />
        </button>

        {/* Repeat Cycle */}
        <button
          onClick={cycleLoopMode}
          className={`p-2.5 rounded-md border transition-all duration-200 focus:outline-none relative ${
            loopMode > 0
              ? 'bg-discord-blurple/15 border-discord-blurple text-discord-blurple'
              : 'bg-discord-darkest-gray border-white/5 text-discord-text-muted hover:text-discord-text-primary'
          }`}
          title={`Cycle Repeat (Current: ${getLoopModeLabel()})`}
        >
          <Repeat className="w-5 h-5" />
          {loopMode === 1 && (
            <span className="absolute -bottom-1 -right-1 bg-discord-blurple text-white text-[9px] font-bold rounded-full w-3.5 h-3.5 flex items-center justify-center border border-discord-card">
              1
            </span>
          )}
          {loopMode === 2 && (
            <span className="absolute -bottom-1 -right-1 bg-discord-blurple text-white text-[9px] font-bold rounded-full w-3.5 h-3.5 flex items-center justify-center border border-discord-card">
              Q
            </span>
          )}
        </button>
      </div>

      {/* Auxiliary Settings Panel (Loop mode text & Autoplay toggle) */}
      <div className="border-t border-white/5 pt-4 flex flex-col sm:flex-row items-center justify-between gap-4">
        {/* Loop mode text display */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-discord-text-muted uppercase tracking-wider">Repeat Mode:</span>
          <span className={`text-xs font-bold px-2 py-0.5 rounded-md border ${
            loopMode === 1 ? 'bg-indigo-950/30 text-indigo-400 border-indigo-500/20' :
            loopMode === 2 ? 'bg-emerald-950/30 text-emerald-400 border-emerald-500/20' :
            'bg-discord-darkest-gray text-discord-text-muted border-white/5'
          }`}>
            {getLoopModeLabel()}
          </span>
        </div>

        {/* Autoplay Slider Switch */}
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-discord-text-muted uppercase tracking-wider">Autoplay:</span>
          <button
            onClick={() => onAutoplayChange(!autoplay)}
            className={`w-11 h-6 rounded-full p-0.5 transition-colors duration-200 focus:outline-none relative border ${
              autoplay ? 'bg-discord-green border-discord-green' : 'bg-discord-darkest-gray border-white/10'
            }`}
          >
            <span
              className={`block w-4.5 h-4.5 rounded-full bg-white shadow-md transform transition-transform duration-200 ${
                autoplay ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
      </div>
    </div>
  );
}
