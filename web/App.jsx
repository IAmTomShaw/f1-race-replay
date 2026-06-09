// web/App.js
import React, { useState, useEffect } from "react";
import Background from "./components/Background";
import { StatusBadge } from "./components/StatusBadge";
import { SystemStatus } from "./types";

// Custom Spinning Tyre Icon - Animation Preserved
const TyreIcon = ({ spinning }) => (
  <svg
    className={`w-12 h-12 text-zinc-500 group-hover:text-[#e10600] transition-colors ${
      spinning ? "animate-spin duration-700" : ""
    }`}
    viewBox="0 0 100 100"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    {/* Outer Tyre */}
    <circle cx="50" cy="50" r="40" stroke="currentColor" strokeWidth="12" />
    {/* Treads (Dashed Stroke) */}
    <circle
      cx="50"
      cy="50"
      r="40"
      stroke="#000"
      strokeWidth="14"
      strokeDasharray="8 12"
      strokeOpacity="0.8"
    />
    {/* Rim */}
    <circle cx="50" cy="50" r="20" stroke="currentColor" strokeWidth="4" />
    {/* Spokes */}
    <path d="M50 30L50 70" stroke="currentColor" strokeWidth="4" />
    <path d="M30 50L70 50" stroke="currentColor" strokeWidth="4" />
  </svg>
);

// Simplified F1 Logo - Text Only
const CustomF1Logo = () => (
  <div className="flex flex-col items-center justify-center select-none mb-4">
    <div className="flex items-baseline gap-1 border-b-4 border-[#e10600] pb-1 px-4">
      <span className="font-race font-black text-4xl md:text-5xl tracking-tighter italic text-white">
        FORMULA
      </span>
      <span className="font-race font-black text-4xl md:text-5xl tracking-tighter italic text-[#e10600] ml-2">
        1
      </span>
    </div>
  </div>
);

const App = () => {
  // State Initialization
  const [status, setStatus] = useState(SystemStatus.IDLE);
  const [telemetry, setTelemetry] = useState({
    speed: 0,
    rpm: 0,
    gear: 0,
    drs: false,
    tireTemp: 90,
  });

  // Telemetry Simulation Loop
  useEffect(() => {
    let interval;

    if (status === SystemStatus.ACTIVE) {
      interval = setInterval(() => {
        setTelemetry((prev) => {
          // Smooth Acceleration Logic
          // Target speed ~340 km/h
          let newSpeed = prev.speed;

          if (newSpeed < 340) {
            newSpeed += 2.0; // Consistent acceleration
          } else {
            // Slight natural variance at top speed
            newSpeed = 340 + Math.sin(Date.now() / 200) * 1.5;
          }

          // Determine Gear based on fixed speed thresholds
          let gear = 1;
          const gearThresholds = [0, 60, 110, 160, 210, 260, 300, 330];
          for (let i = 0; i < gearThresholds.length; i++) {
            if (newSpeed >= gearThresholds[i]) gear = i + 1;
          }
          if (gear > 8) gear = 8;

          // Calculate RPM
          const currentBase = gearThresholds[gear - 1] || 0;
          const nextBase = gearThresholds[gear] || 360;
          const range = nextBase - currentBase;
          const progress = Math.max(0, (newSpeed - currentBase) / range);

          let newRpm = 10500 + progress * 4000;
          if (newRpm > 15000) newRpm = 14800 + Math.random() * 100;

          const drsActive = newSpeed > 280;

          return {
            speed: Math.floor(newSpeed),
            rpm: Math.floor(newRpm),
            gear: gear,
            drs: drsActive,
            tireTemp: 90 + newSpeed / 15,
          };
        });
      }, 50);
    } else {
      setTelemetry({ speed: 0, rpm: 0, gear: 0, drs: false, tireTemp: 90 });
    }

    return () => clearInterval(interval);
  }, [status]);

  const triggerDSA = async () => {
    setStatus(SystemStatus.ACTIVE);
    try {
      if (window.eel) {
        // Double execution ()() pattern for Eel
        const response = await window.eel.launch_dsa_module()();
        console.log("DSA Replay Finished:", response);
      } else {
        console.warn("Eel environment not detected. Mocking response.");
        await new Promise((resolve) => setTimeout(resolve, 10000));
      }
    } catch (error) {
      console.error("Failed to launch DSA Module:", error);
      setStatus(SystemStatus.ERROR);
    } finally {
      setStatus(SystemStatus.IDLE);
    }
  };

  return (
    <div className="relative min-h-screen w-full flex flex-col items-center justify-center text-white overflow-hidden selection:bg-[#e10600] selection:text-white">
      <Background />

      <main className="relative z-20 w-full max-w-7xl px-4 flex flex-col items-center h-screen justify-between py-12">
        {/* TOP BAR / HEADER - Fixed Height Section */}
        <header className="flex-none w-full flex flex-col items-center justify-center relative mb-8">
          <div className="absolute top-[-2rem] w-full h-[4px] bg-[#e10600] shadow-[0_0_20px_#e10600]"></div>

          <div className="flex flex-col items-center gap-2 mt-4">
            <div className="relative hover:scale-105 transition-transform duration-300">
              <CustomF1Logo />
            </div>

            <div className="flex flex-col justify-center text-center">
              <h2 className="text-sm font-bold tracking-[0.6em] text-[#e10600] uppercase mb-1 drop-shadow-md">
                Official Telemetry Console
              </h2>
              {/* Title with generous padding to prevent clipping of italic fonts */}
              <h1 className="text-5xl md:text-6xl font-race font-black tracking-tighter italic uppercase leading-none drop-shadow-2xl text-white pr-12">
                Sentinel{" "}
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-white to-[#e10600]">
                  Nexus
                </span>
              </h1>
            </div>
          </div>
        </header>

        {/* CENTER STAGE: THE BUTTON - Flexible Spacer to Separate from Header/Footer */}
        <div className="flex-1 w-full flex flex-col items-center justify-center relative z-30 my-8">
          <div className="relative group perspective-[1000px]">
            <div
              className={`absolute -inset-4 bg-[#e10600] opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-30 ${
                status === SystemStatus.ACTIVE ? "opacity-50 animate-pulse" : ""
              }`}
            ></div>

            <button
              onClick={triggerDSA}
              disabled={status === SystemStatus.ACTIVE}
              className="relative outline-none focus:outline-none"
            >
              <div
                className={`
                    w-[300px] h-[90px] md:w-[500px] md:h-[140px]
                    flex items-center justify-between px-10
                    transform skew-x-[-15deg]
                    border-2 border-zinc-600 bg-[#000000]/90 backdrop-blur-xl
                    transition-all duration-300 ease-out
                    group-hover:border-[#e10600] group-hover:bg-[#e10600]/10
                    group-hover:scale-105 group-hover:shadow-[0_0_50px_rgba(225,6,0,0.4)]
                    ${
                      status === SystemStatus.ACTIVE
                        ? "border-[#e10600] bg-[#e10600]/20 shadow-[0_0_60px_rgba(225,6,0,0.6)]"
                        : ""
                    }
                `}
              >
                {/* Left Icon Block - Tyre Animation */}
                <div className="flex flex-col items-center justify-center pr-4 transition-colors">
                  <TyreIcon spinning={status === SystemStatus.ACTIVE} />
                </div>

                {/* Text Content */}
                <div className="flex-1 flex flex-col items-center justify-center transform skew-x-[15deg]">
                  <span className="text-zinc-400 text-[11px] tracking-[0.3em] font-bold uppercase mb-2 group-hover:text-white transition-colors">
                    {status === SystemStatus.ACTIVE
                      ? "ANALYZING TELEMETRY"
                      : "AWAITING INPUT"}
                  </span>
                  <span
                    className={`text-2xl md:text-5xl font-race font-black italic tracking-wider uppercase transition-colors ${
                      status === SystemStatus.ACTIVE
                        ? "text-[#e10600]"
                        : "text-white"
                    }`}
                  >
                    {status === SystemStatus.ACTIVE ? "RUNNING" : "LAUNCH"}
                  </span>
                </div>

                {/* Decorative Element */}
                <div className="w-4"></div>
              </div>
            </button>
          </div>
        </div>

        {/* BOTTOM STATUS PANEL - LIVE TELEMETRY - Fixed Bottom Section */}
        <div className="flex-none w-full border-t-4 border-[#e10600] pt-6 flex flex-col xl:flex-row justify-between items-end xl:items-center gap-8 bg-[#000000]/90 p-8 rounded-t-xl backdrop-blur-md relative overflow-hidden shadow-[0_-10px_40px_rgba(0,0,0,0.8)] mt-8">
          {/* Status Block (Left) */}
          <div className="flex flex-col gap-4 z-10 w-full xl:w-auto">
            <span className="text-[10px] text-zinc-400 font-bold tracking-wider uppercase flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${
                  status === SystemStatus.ACTIVE
                    ? "bg-[#e10600] animate-ping"
                    : "bg-zinc-500"
                }`}
              ></span>
              {status === SystemStatus.ACTIVE
                ? "Live Data Stream Active"
                : "System Standby"}
            </span>
            <div className="flex gap-2">
              <StatusBadge label="SERVER" color="#e10600" active={true} />
              <StatusBadge
                label="UPLINK"
                color="#e10600"
                active={status !== SystemStatus.ERROR}
              />
              <StatusBadge
                label="SIM"
                color="#e10600"
                active={status === SystemStatus.ACTIVE}
              />
            </div>
          </div>

          {/* Telemetry Dashboard (Right) */}
          <div className="flex items-end justify-end gap-10 md:gap-16 z-10 w-full xl:w-auto">
            {/* GEAR BOX */}
            <div className="relative shrink-0 group">
              <div className="absolute -inset-2 bg-[#e10600] blur opacity-20 group-hover:opacity-40 transition-opacity"></div>
              <div className="w-20 h-24 border-[3px] border-[#e10600] rounded-lg bg-[#15151e] transform skew-x-[-12deg] flex items-center justify-center shadow-[0_0_20px_rgba(225,6,0,0.2)] relative z-10">
                <span className="text-6xl font-race font-black italic text-[#e10600] transform skew-x-[12deg]">
                  {status === SystemStatus.ACTIVE ? telemetry.gear : "N"}
                </span>
              </div>
            </div>

            {/* RPM GAUGE (Hidden on mobile) */}
            <div className="hidden md:flex flex-col items-end w-64 pb-2 shrink-0 space-y-2">
              {/* RPM Bars - Taller and clearer */}
              <div className="flex gap-[3px] h-6 w-full">
                {[...Array(20)].map((_, i) => {
                  let bgClass = "bg-[#1f1f23]";
                  if (status === SystemStatus.ACTIVE) {
                    const activeBars = Math.floor((telemetry.rpm / 15000) * 20);
                    if (i < activeBars) {
                      bgClass = i < 14 ? "bg-zinc-400" : "bg-[#e10600]";
                    }
                  }
                  return (
                    <div
                      key={i}
                      className={`flex-1 transform skew-x-[-15deg] ${bgClass}`}
                    ></div>
                  );
                })}
              </div>
              <div className="flex justify-between w-full text-zinc-500 font-mono text-[10px] tracking-widest px-1">
                <span>0</span>
                <span
                  className={status === SystemStatus.ACTIVE ? "text-white" : ""}
                >
                  {status === SystemStatus.ACTIVE ? telemetry.rpm : "00000"} RPM
                </span>
                <span>15000</span>
              </div>
            </div>

            {/* SPEEDOMETER */}
            <div className="flex items-baseline shrink-0 relative">
              {/* Speed Digits */}
              <div className="flex font-race font-black italic text-8xl leading-none tracking-tighter transform -skew-x-12 select-none">
                {/* Hundreds */}
                <span
                  className={`w-[0.6em] text-center ${
                    status === SystemStatus.ACTIVE && telemetry.speed >= 100
                      ? "text-white"
                      : "text-[#2a2a2a]"
                  }`}
                >
                  {Math.floor((telemetry.speed % 1000) / 100)}
                </span>
                {/* Tens */}
                <span
                  className={`w-[0.6em] text-center ${
                    status === SystemStatus.ACTIVE && telemetry.speed >= 10
                      ? "text-white"
                      : "text-[#2a2a2a]"
                  }`}
                >
                  {Math.floor((telemetry.speed % 100) / 10)}
                </span>
                {/* Ones */}
                <span
                  className={`w-[0.6em] text-center ${
                    status === SystemStatus.ACTIVE
                      ? "text-white"
                      : "text-[#2a2a2a]"
                  }`}
                >
                  {telemetry.speed % 10}
                </span>
              </div>
              {/* Unit Label */}
              <span className="text-xl text-[#e10600] font-bold italic ml-4 transform -skew-x-12 mb-2">
                KM/H
              </span>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default App;
