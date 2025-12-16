import { ElectronAPI } from '@electron-toolkit/preload'

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      runPython: (args: { year: number; round: number }) => void
      onPythonOutput: (callback: (data: string) => void) => void
    }
  }
}
