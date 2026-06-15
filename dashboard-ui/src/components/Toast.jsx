// Toast.jsx - Simple, modern toast overlay notifications matching the Discord style
import React from 'react';
import { X, CheckCircle2, AlertCircle, Info } from 'lucide-react';

export const Toast = ({ id, message, type = 'info', onClose }) => {
  const getIcon = () => {
    switch (type) {
      case 'success':
        return <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />;
      case 'error':
        return <AlertCircle className="w-5 h-5 text-discord-red shrink-0" />;
      case 'warning':
        return <Info className="w-5 h-5 text-discord-yellow shrink-0" />;
      default:
        return <Info className="w-5 h-5 text-discord-blurple shrink-0" />;
    }
  };

  const getBorderColor = () => {
    switch (type) {
      case 'success':
        return 'border-emerald-500/30 bg-emerald-950/20';
      case 'error':
        return 'border-discord-red/30 bg-red-950/20';
      case 'warning':
        return 'border-discord-yellow/30 bg-yellow-950/20';
      default:
        return 'border-discord-blurple/30 bg-discord-blurple/10';
    }
  };

  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-lg border shadow-lg backdrop-blur-md transition-all duration-300 transform translate-x-0 animate-slide-in text-discord-text-primary ${getBorderColor()} max-w-sm w-full`}
    >
      {getIcon()}
      <div className="flex-1 text-sm font-medium leading-5">{message}</div>
      <button
        onClick={() => onClose(id)}
        className="text-discord-text-muted hover:text-discord-text-primary transition-colors focus:outline-none shrink-0"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};

export const ToastContainer = ({ toasts, onClose }) => {
  return (
    <div className="fixed top-6 right-6 z-50 flex flex-col gap-3 w-full max-w-sm pointer-events-none">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <Toast
            id={toast.id}
            message={toast.message}
            type={toast.type}
            onClose={onClose}
          />
        </div>
      ))}
    </div>
  );
};
