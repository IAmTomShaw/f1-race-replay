import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

// Expose electronAPI from toolkit (optional)
contextBridge.exposeInMainWorld('electron', electronAPI)

// Expose your custom API
contextBridge.exposeInMainWorld('api', {
  runGetSchedule: (args: { year: number }) => ipcRenderer.send('runGetSchedule', args),
  runRaceReplay: (args: { year: number; round: number }) =>
    ipcRenderer.send('run-race-replay', args),
  onPythonOutput: (callback: (data: string) => void) =>
    ipcRenderer.on('python-output', (_, data) => callback(data)),
  readData: (callback: (data: JSON) => void) =>
    ipcRenderer.on('read-data', (_, data) => callback(data))
})
