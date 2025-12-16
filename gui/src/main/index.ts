import { app, shell, BrowserWindow, ipcMain } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'
import { spawn } from 'child_process'
import path from 'path'
import fs from 'fs'
import os from 'os'

function createWindow(): void {
  // Create the browser window.
  const mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    show: false,
    autoHideMenuBar: true,
    ...(process.platform === 'linux' ? { icon } : {}),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true
    }
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // HMR for renderer base on electron-vite cli.
  // Load the remote URL for development or the local html file for production.
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.whenReady().then(() => {
  // Set app user model id for windows
  electronApp.setAppUserModelId('com.electron')

  // Default open or close DevTools by F12 in development
  // and ignore CommandOrControl + R in production.
  // see https://github.com/alex8088/electron-toolkit/tree/master/packages/utils
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // IPC test
  ipcMain.on('ping', () => console.log('pong'))

  createWindow()

  app.on('activate', function () {
    // On macOS it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

// Resolve the virtual environment folder (.venv or venv)
function getVenvPython(): string {
  const projectRoot = path.join(__dirname, '../../../')
  const venvFolders = ['.venv', 'venv']

  for (const folder of venvFolders) {
    const fullPath = path.join(projectRoot, folder)
    if (fs.existsSync(fullPath)) {
      if (os.platform() === 'win32') {
        // Windows
        return path.join(fullPath, 'Scripts', 'python.exe')
      } else {
        // Linux / macOS
        return path.join(fullPath, 'bin', 'python')
      }
    }
  }

  // Fallback to system Python if no venv found
  return 'python'
}

// Path to the Python script
const pythonScript = path.join(__dirname, '../../../main.py')

ipcMain.on('run-python', (event, args: { year: number; round: number }) => {
  const venvPython = getVenvPython()

  const pythonArgs = [pythonScript, '--year', String(args.year), '--round', String(args.round)]

  const python = spawn(venvPython, pythonArgs, {
    cwd: path.dirname(pythonScript)
  })

  python.stdout.on('data', (data) => {
    event.sender.send('python-output', data.toString())
  })

  python.stderr.on('data', (data) => {
    event.sender.send('python-output', `ERROR: ${data.toString()}`)
  })

  python.on('close', (code) => {
    event.sender.send('python-output', `Python script exited with code ${code}`)
  })
})

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and require them here.
