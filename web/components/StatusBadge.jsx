import React from "react";

export const StatusBadge = ({ label, active = false, color = "#e10600" }) => {
  return (
    <div
      className={`
        relative inline-flex items-center justify-center px-4 md:px-6 py-1 
        transform skew-x-[-12deg] border 
        transition-all duration-300
      `}
      style={{
        borderColor: active ? color : "#27272a", // zinc-800
        backgroundColor: active ? `${color}20` : "#18181b", // zinc-900 or color with opacity
        boxShadow: active ? `0 0 15px ${color}50` : "none",
      }}
    >
      <span
        className="transform skew-x-[12deg] text-[10px] md:text-xs font-bold tracking-widest uppercase font-race"
        style={{ color: active ? "white" : "#71717a" }}
      >
        {label}
      </span>

      {/* Dynamic Status Light */}
      <div
        className="absolute bottom-0 right-0 w-1 h-1 md:w-2 md:h-2"
        style={{ backgroundColor: active ? color : "transparent" }}
      ></div>
    </div>
  );
};
