import path from 'path'
import fs from 'fs'
import os from 'os'

export function GetVenvPython(): string {
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
