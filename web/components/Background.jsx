import React from "react";

const Background = () => {
  return (
    <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden bg-[#050505] flex items-center justify-center">
      {/* 1. Base Gradient - Deep Black/Red Vignette */}
      <div className="absolute inset-0 bg-gradient-to-b from-[#000000] via-[#0a0000] to-[#1a0000]"></div>

      {/* 2. "Wind Tunnel" Flow Lines - STRICT RED & BLACK THEME */}
      <div className="absolute inset-0 opacity-40">
        {/* Primary F1 Red Stream */}
        <div className="absolute top-[20%] -left-[20%] w-[140%] h-[200px] bg-gradient-to-r from-transparent via-[#e10600] to-transparent transform rotate-12 blur-[80px] animate-flow-slow"></div>

        {/* Secondary Dark Red/Grey Stream */}
        <div className="absolute bottom-[10%] -right-[20%] w-[140%] h-[200px] bg-gradient-to-l from-transparent via-[#400000] to-transparent transform -rotate-12 blur-[90px] animate-flow-reverse"></div>

        {/* Accent White/Grey Stream */}
        <div className="absolute top-[50%] left-[20%] w-[80%] h-[80px] bg-gradient-to-r from-transparent via-[#ffffff] to-transparent blur-[80px] opacity-20 animate-pulse-slow"></div>
      </div>

      {/* 3. Grid Floor - Red tint */}
      <div className="absolute inset-0 perspective-[1000px]">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(225,6,0,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(225,6,0,0.05)_1px,transparent_1px)] bg-[size:60px_60px] [transform-origin:center_bottom] [transform:rotateX(70deg)_scale(2)] animate-grid-scroll"></div>
      </div>

      {/* 4. Floating Embers */}
      <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/stardust.png')] opacity-20 animate-fade-in-out mix-blend-overlay"></div>

      <style>{`
        @keyframes flow-slow {
          0% { transform: rotate(12deg) translate(-50px, 0); opacity: 0.3; }
          50% { transform: rotate(12deg) translate(50px, 20px); opacity: 0.6; }
          100% { transform: rotate(12deg) translate(-50px, 0); opacity: 0.3; }
        }
        
        @keyframes flow-reverse {
          0% { transform: rotate(-12deg) translate(50px, 0); opacity: 0.3; }
          50% { transform: rotate(-12deg) translate(-50px, -20px); opacity: 0.5; }
          100% { transform: rotate(-12deg) translate(50px, 0); opacity: 0.3; }
        }

        @keyframes pulse-slow {
          0%, 100% { opacity: 0.1; }
          50% { opacity: 0.3; }
        }

        @keyframes grid-scroll {
          0% { background-position: 0 0; }
          100% { background-position: 0 60px; }
        }

        .animate-flow-slow { animation: flow-slow 8s ease-in-out infinite; }
        .animate-flow-reverse { animation: flow-reverse 12s ease-in-out infinite; }
        .animate-pulse-slow { animation: pulse-slow 6s ease-in-out infinite; }
        .animate-grid-scroll { animation: grid-scroll 1s linear infinite; }
      `}</style>
    </div>
  );
};

export default Background;
