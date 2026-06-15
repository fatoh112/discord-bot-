// ServerSelector.jsx - Guild selector dropdown matching the Discord theme
import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Server, Users, Radio } from 'lucide-react';

export default function ServerSelector({ guilds, activeGuildId, onSelectGuild, isConnected }) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  const activeGuild = guilds.find((g) => g.id === activeGuildId) || guilds[0];

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const getInitials = (name) => {
    return name
      .split(' ')
      .map((word) => word[0])
      .join('')
      .slice(0, 3)
      .toUpperCase();
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between w-64 px-4 py-2.5 bg-discord-darkest-gray hover:bg-[#35373c] text-discord-text-primary rounded-md border border-white/5 transition-colors focus:outline-none"
      >
        <div className="flex items-center gap-3 overflow-hidden">
          {activeGuild?.icon ? (
            <img
              src={activeGuild.icon}
              alt={activeGuild.name}
              className="w-7 h-7 rounded-full object-cover shrink-0"
            />
          ) : (
            <div className="w-7 h-7 bg-discord-blurple text-discord-text-primary text-xs font-bold rounded-full flex items-center justify-center shrink-0">
              {activeGuild ? getInitials(activeGuild.name) : <Server className="w-4 h-4" />}
            </div>
          )}
          <div className="text-left overflow-hidden">
            <div className="font-semibold text-sm truncate leading-4">
              {activeGuild ? activeGuild.name : 'Select Guild'}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5 text-2xs text-discord-text-muted">
              <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-discord-green' : 'bg-discord-red'}`}></span>
              <span>{isConnected ? 'Sync Connected' : 'Offline'}</span>
            </div>
          </div>
        </div>
        <ChevronDown className={`w-4 h-4 text-discord-text-muted transition-transform duration-200 shrink-0 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute left-0 mt-1.5 w-64 bg-discord-darkest-gray border border-white/10 rounded-md shadow-xl z-50 py-1.5 animate-fade-in">
          <div className="px-3 py-1 text-2xs font-semibold text-discord-text-muted uppercase tracking-wider mb-1">
            Active Servers
          </div>
          <div className="max-h-60 overflow-y-auto">
            {guilds.map((guild) => (
              <button
                key={guild.id}
                onClick={() => {
                  onSelectGuild(guild.id);
                  setIsOpen(false);
                }}
                className={`w-full flex items-center justify-between px-3 py-2 text-left transition-colors focus:outline-none ${
                  guild.id === activeGuildId
                    ? 'bg-discord-blurple text-discord-text-primary'
                    : 'text-discord-text-muted hover:bg-discord-card hover:text-discord-text-primary'
                }`}
              >
                <div className="flex items-center gap-2.5 overflow-hidden">
                  {guild.icon ? (
                    <img
                      src={guild.icon}
                      alt={guild.name}
                      className="w-6 h-6 rounded-full object-cover shrink-0"
                    />
                  ) : (
                    <div className={`w-6 h-6 text-2xs font-bold rounded-full flex items-center justify-center shrink-0 ${
                      guild.id === activeGuildId ? 'bg-white/20 text-white' : 'bg-discord-dark-gray text-discord-text-primary'
                    }`}>
                      {getInitials(guild.name)}
                    </div>
                  )}
                  <span className="text-sm font-medium truncate">{guild.name}</span>
                </div>
                <div className="flex items-center gap-1 text-2xs shrink-0 pl-2 opacity-80">
                  <Users className="w-3.5 h-3.5" />
                  <span>{guild.member_count}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
