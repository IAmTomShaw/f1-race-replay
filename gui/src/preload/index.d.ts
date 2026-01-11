import { ElectronAPI } from '@electron-toolkit/preload'

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      runGetSchedule: (args: { year: number }) => void
      onPythonOutput: (callback: (data: string) => void) => void
      readData: (callback: (data: JSON) => void) => void
    }
  }
}
