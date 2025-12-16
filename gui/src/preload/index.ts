import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

// Expose electronAPI from toolkit (optional)
contextBridge.exposeInMainWorld('electron', electronAPI)

// Expose your custom API
contextBridge.exposeInMainWorld('api', {
  runPython: (args: { year: number; round: number }) => ipcRenderer.send('run-python', args),
  onPythonOutput: (callback: (data: string) => void) =>
    ipcRenderer.on('python-output', (_, data) => callback(data))
})
