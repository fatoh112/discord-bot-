// NowPlaying.jsx - Now Playing Card Component
import React from 'react';
import { Music, Radio, Disc } from 'lucide-react';

export default function NowPlaying({ currentTrack, elapsedTime, playerStatus, voiceChannel }) {
  // Format seconds to MM:SS
  const formatTime = (seconds) => {
    if (isNaN(seconds) || seconds === null || seconds === undefined) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const isPlaying = playerStatus === 'playing';
  const duration = currentTrack?.duration || 0;
  const progressPercent = duration > 0 ? (elapsedTime / duration) * 100 : 0;

  return (
    <div className="bg-discord-card border border-white/5 rounded-lg p-6 flex flex-col justify-between h-full shadow-lg relative overflow-hidden transition-all duration-300">
      {/* Background Subtle Blur Glow */}
      {currentTrack?.thumbnail && (
        <div 
          className="absolute inset-0 bg-cover bg-center opacity-[0.03] blur-xl pointer-events-none scale-110"
          style={{ backgroundImage: `url(${currentTrack.thumbnail})` }}
        />
      )}

      {/* Track info header */}
      <div className="flex flex-col md:flex-row gap-5 items-center relative z-10">
        {/* Cover Art / Generic Music Icon */}
        <div className="relative group shrink-0">
          {currentTrack?.thumbnail ? (
            <img
              src={currentTrack.thumbnail}
              alt={currentTrack.title}
              className={`w-32 h-32 md:w-28 md:h-28 rounded-md object-cover shadow-md transition-transform duration-500 border border-white/10 ${isPlaying ? 'scale-[1.02]' : ''}`}
            />
          ) : (
            <div className="w-32 h-32 md:w-28 md:h-28 rounded-md bg-discord-darkest-gray flex items-center justify-center border border-white/10">
              <Music className="w-12 h-12 text-discord-text-muted" />
            </div>
          )}
          {/* Animated Disc Indicator */}
          {isPlaying && (
            <div className="absolute -top-1.5 -right-1.5 bg-discord-blurple p-1.5 rounded-full shadow-md animate-spin" style={{ animationDuration: '4s' }}>
              <Disc className="w-4 h-4 text-white" />
            </div>
          )}
        </div>

        {/* Text descriptions */}
        <div className="text-center md:text-left overflow-hidden flex-1 w-full">
          <div className="flex items-center justify-center md:justify-start gap-2 text-2xs font-semibold text-discord-blurple uppercase tracking-wider mb-1.5">
            <span className="relative flex h-2 w-2">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${isPlaying ? 'bg-discord-blurple' : 'bg-discord-text-muted'}`}></span>
              <span className={`relative inline-flex rounded-full h-2 w-2 ${isPlaying ? 'bg-discord-blurple' : 'bg-discord-text-muted'}`}></span>
            </span>
            <span>{playerStatus === 'idle' ? 'Nothing Playing' : isPlaying ? 'Now Playing' : 'Paused'}</span>
          </div>

          <h2 className="text-xl font-bold text-discord-text-primary truncate leading-tight tracking-wide" title={currentTrack?.title || 'No track playing'}>
            {currentTrack?.title || 'No Track Selected'}
          </h2>
          
          <p className="text-sm text-discord-text-muted mt-1 truncate">
            {currentTrack?.artist || '—'}
          </p>

          {/* Connected Voice Channel */}
          {voiceChannel && (
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 mt-3 bg-discord-darkest-gray rounded text-2xs font-medium text-discord-text-primary border border-white/5">
              <Radio className="w-3.5 h-3.5 text-discord-green" />
              <span>VC: {voiceChannel}</span>
            </div>
          )}
        </div>
      </div>

      {/* Progress slider (Display-only for v1) */}
      <div className="mt-8 relative z-10">
        <div className="w-full">
          {/* Timeline Bar */}
          <div className="relative w-full h-1.5 bg-discord-darkest-gray rounded-full overflow-hidden group border border-white/5">
            <div
              className="absolute h-full bg-discord-blurple rounded-full transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          
          {/* Timestamps */}
          <div className="flex justify-between items-center mt-2 text-xs font-semibold text-discord-text-muted select-none">
            <span>{formatTime(elapsedTime)}</span>
            <span>{formatTime(duration)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
