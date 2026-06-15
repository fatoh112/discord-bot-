// VolumeSlider.jsx - Volume Controller Component
import React, { useState, useRef } from 'react';
import { Volume2, Volume1, VolumeX } from 'lucide-react';

export default function VolumeSlider({ volume, onChange }) {
  const [previousVolume, setPreviousVolume] = useState(75);
  
  const handleVolumeChange = (e) => {
    const newVol = parseInt(e.target.value, 10);
    onChange(newVol);
  };

  const toggleMute = () => {
    if (volume > 0) {
      setPreviousVolume(volume);
      onChange(0);
    } else {
      onChange(previousVolume);
    }
  };

  const getVolumeIcon = () => {
    if (volume === 0) {
      return <VolumeX className="w-5 h-5 text-discord-red shrink-0" />;
    } else if (volume < 50) {
      return <Volume1 className="w-5 h-5 text-discord-text-muted shrink-0" />;
    } else {
      return <Volume2 className="w-5 h-5 text-discord-text-primary shrink-0" />;
    }
  };

  return (
    <div className="bg-discord-card border border-white/5 rounded-lg p-5 flex items-center gap-4 shadow-md">
      {/* Icon button for mute toggle */}
      <button
        onClick={toggleMute}
        className="p-2 bg-discord-darkest-gray hover:bg-[#35373c] rounded-md border border-white/5 text-discord-text-primary transition-all duration-200 focus:outline-none"
        title={volume === 0 ? 'Unmute' : 'Mute'}
      >
        {getVolumeIcon()}
      </button>

      {/* Slider Container */}
      <div className="flex-1 flex items-center gap-3">
        <input
          type="range"
          min="0"
          max="100"
          value={volume}
          onChange={handleVolumeChange}
          className="w-full h-1.5 bg-discord-darkest-gray rounded-full appearance-none cursor-pointer accent-discord-blurple focus:outline-none"
          style={{
            background: `linear-gradient(to right, #5865F2 0%, #5865F2 ${volume}%, #1e1f22 ${volume}%, #1e1f22 100%)`
          }}
        />
        
        {/* Numeric Readout */}
        <span className="text-xs font-bold text-discord-text-primary bg-discord-darkest-gray px-2 py-1 rounded w-11 text-center border border-white/5 select-none">
          {volume}%
        </span>
      </div>
    </div>
  );
}
