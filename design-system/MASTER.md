# MASTER DESIGN SYSTEM: F1 Race Replay

## 🏛️ Core Principles
- **Clarity Above All**: In high-speed replays, data must be legible at a glance.
- **Broadcast Standard**: Mimic the official F1 TV aesthetic for immersion.
- **Data Density**: Efficient use of space for telemetry and leaderboard.

## 🎨 Palette (Dark Mode OLED)
| Role | Hex Code | Purpose |
| :--- | :--- | :--- |
| **Primary** | `#FF1801` | F1 Red, Branding, Critical Alerts |
| **Background** | `#15151E` | Main Window, Sidebar backgrounds |
| **Card BG** | `#1F1F2B` | Interactive elements, rows |
| **Accent Blue** | `#3B82F6` | Trust, Technical data |
| **Accent Green**| `#22C55E` | DRS On, Pitstop entry, Gap reduction |
| **Text Primary**| `#FFFFFF` | Headings, Driver Codes |
| **Text Secondary**| `#8E8E93` | Metadata, Intervals, Settings |

## 🔠 Typography
- **Heading**: `Segoe UI` (System) or `Fira Sans` (Data)
- **Data**: `Fira Code` or Mono-spaced for telemetry digits (prevents layout shift on change).

## 🖱️ Interaction Rules
- **Cursor**: All clickable elements MUST have `cursor-pointer` (Hand cursor in OS).
- **Transitions**: 200ms ease-in-out for hover states.
- **Feedback**: Background shift or border highlight on hover.

## 🚫 Anti-Patterns
- Emojis as UI icons (Use SVGs).
- Pure #000 black with bright white text (Too much contrast, use high-mid dark shades).
- Layout shifts when data updates.

## 🏁 Components
- **Leaderboard**: Team color bar (left), Position (bold), Code (bold), Interval (muted).
- **Cards**: Soft border (`#383845`), slight shadow, hover elevation.
